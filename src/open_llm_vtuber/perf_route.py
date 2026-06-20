"""
Performance / hardware settings endpoints (the "可高可低" core).
================================================================
Localhost-only REST endpoints that let a non-technical user pick their ASR/TTS
ENGINE, throttle memory consolidation, tune the local-Ollama keep_alive, and apply
one-click performance PRESETS — all WITHOUT hand-editing YAML. Lightweight defaults
stay unchanged; everything here is opt-in so the app scales low->high across machines.

What this owns (vs. neighbouring routers):
- ASR ENGINE selector (asr_config.asr_model) + the cloud sub-blocks' credentials.
  NOTE: the existing "ASR" settings tab is CLIENT-SIDE VAD/mic only — it does NOT
  touch the backend engine. The engine selector belongs HERE.
- TTS ENGINE selector (tts_config.tts_model) + gpt_sovits_tts api_url / ref_audio_path.
- ollama_llm.keep_alive (local model RAM-residency seconds).
- memory_consolidation_interval (delegated to memory_route's writer is also fine, but
  exposed here too for the unified 效能/硬體 tab + preset bundles).

Design notes (mirror memory_route / translator_route / llm_config_route conventions):
- The localhost+proxy guard is REUSED verbatim (``_is_local_request`` / ``_forbidden``).
- conf.yaml is heavily commented, so writes are SURGICAL line edits (reusing
  translator_route's _find_block_extent / _rewrite_leaf / _rewrite_bool_leaf +
  memory_route's _rewrite_int_leaf), NOT a ruamel re-dump (which would normalize
  True->true / null across the hand-edited file). Atomic write + one-time .bak.
- Every nested write is scoped to the SPECIFIC sub-block's extent (nested
  _find_block_extent), never a flat scan — several *_asr / *_tts blocks share leaf
  names like api_key, so a flat rewrite would clobber the wrong engine.
- Cloud ASR keys (groq/azure) are masked on read (_mask_key) and NEVER logged.
- restart_required is honestly True for ALL engine/perf changes: ASRConfig / TTSConfig
  / ollama keep_alive / asr_model / tts_model are baked into CharacterConfig at server
  init (conf.yaml loads once); changes apply only after a restart or character re-select.
"""

import re
import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse
from loguru import logger

# REUSE the localhost+proxy guard + yaml helper + key masker — do not diverge.
from .llm_config_route import _is_local_request, _forbidden, _mask_key

# REUSE the surgical conf.yaml write machinery.
from .translator_route import (
    _find_block_extent,
    _rewrite_leaf,
    _backup_once,
    _atomic_write,
    CONF_PATH,
)
from .memory_route import _rewrite_int_leaf

from .config_manager.utils import read_yaml
from . import memory_core


# --------------------------------------------------------------------------- #
# Single source of truth for new bounds / allow-lists
# --------------------------------------------------------------------------- #

# ASR engines the UI accepts. faster_whisper needs an extra `pip install
# faster-whisper` (+ ctranslate2 / model download) that isn't bundled. We still
# ACCEPT it here (rather than 400-ing the existing UI, whose preset/dropdown still
# offer it) because it is now SAFE at runtime: service_context.init_asr falls back
# to the bundled sherpa_onnx_asr if the chosen engine can't load, so picking
# faster_whisper without it installed quietly uses sherpa instead of bricking.
ASR_MODELS = {"sherpa_onnx_asr", "faster_whisper", "groq_whisper_asr", "azure_asr"}
# TTS engines the UI offers.
TTS_MODELS = {"edge_tts", "gpt_sovits_tts"}

# keep_alive: -1 = pin in RAM forever; 0 = unload immediately; otherwise seconds.
KEEP_ALIVE_MIN = -1
KEEP_ALIVE_MAX = 86400  # 24h hard ceiling


# Performance presets — curated bundles applied via the EXISTING guarded writers.
# Each preset is a STARTING POINT; individual controls stay adjustable after.
# Lightweight conf.yaml DEFAULTS are unchanged; presets only mutate on explicit click.
PRESETS: dict[str, dict[str, Any]] = {
    # 輕量：弱機 / 共用機。最省。
    "light": {
        "asr_model": "sherpa_onnx_asr",
        "tts_model": "edge_tts",
        "core_memory_max_chars": 1000,
        "fts_memory_enabled": False,
        "memory_consolidation_interval": 3,
        "keep_alive": 300,
    },
    # 標準：預設值（基本等於出廠的輕量預設）。
    "standard": {
        "asr_model": "sherpa_onnx_asr",
        "tts_model": "edge_tts",
        "core_memory_max_chars": 1500,
        "fts_memory_enabled": False,
        "memory_consolidation_interval": 1,
        "keep_alive": 1800,
    },
    # 高效能：強機。ASR 維持內建的 sherpa_onnx_asr（離線、零額外相依）——不換成
    # faster_whisper，因為它的相依沒打包進來、換了一重開就起不來。「高效能」差別在
    # 記憶體 / FTS / keep_alive 這些旋鈕。TTS 也不自動換 gpt_sovits（需外部服務 + 參考音檔）。
    "high": {
        "asr_model": "sherpa_onnx_asr",
        "tts_model": "edge_tts",
        "core_memory_max_chars": 3000,
        "fts_memory_enabled": True,
        "memory_consolidation_interval": 1,
        "keep_alive": 3600,
    },
}


# --------------------------------------------------------------------------- #
# Read helpers (round-trip load, scalar reads only)
# --------------------------------------------------------------------------- #

def _load_plain() -> Any:
    return read_yaml(CONF_PATH) or {}


def _asr_from_conf() -> dict:
    """Read asr_config.asr_model + cloud creds (masked) from base conf.yaml."""
    out = {
        "asr_model": "sherpa_onnx_asr",
        "groq_api_key_masked": "",
        "azure_api_key_masked": "",
        "azure_region": "",
    }
    try:
        data = _load_plain()
        asr = (data.get("character_config", {}) or {}).get("asr_config", {}) or {}
        m = asr.get("asr_model")
        if m is not None:
            out["asr_model"] = str(m)
        groq = asr.get("groq_whisper_asr", {}) or {}
        out["groq_api_key_masked"] = _mask_key(groq.get("api_key"))
        azure = asr.get("azure_asr", {}) or {}
        out["azure_api_key_masked"] = _mask_key(azure.get("api_key"))
        if azure.get("region") is not None:
            out["azure_region"] = str(azure.get("region"))
    except Exception:
        pass
    return out


def _tts_from_conf() -> dict:
    """Read tts_config.tts_model + gpt_sovits_tts api_url / ref_audio_path."""
    out = {
        "tts_model": "edge_tts",
        "gpt_sovits_api_url": "",
        "gpt_sovits_ref_audio_path": "",
    }
    try:
        data = _load_plain()
        tts = (data.get("character_config", {}) or {}).get("tts_config", {}) or {}
        m = tts.get("tts_model")
        if m is not None:
            out["tts_model"] = str(m)
        gs = tts.get("gpt_sovits_tts", {}) or {}
        if gs.get("api_url") is not None:
            out["gpt_sovits_api_url"] = str(gs.get("api_url"))
        if gs.get("ref_audio_path") is not None:
            out["gpt_sovits_ref_audio_path"] = str(gs.get("ref_audio_path"))
    except Exception:
        pass
    return out


def _keep_alive_from_conf() -> int:
    """Read character_config.agent_config.llm_configs.ollama_llm.keep_alive."""
    try:
        data = _load_plain()
        ka = (
            data.get("character_config", {})
            .get("agent_config", {})
            .get("llm_configs", {})
            .get("ollama_llm", {})
            .get("keep_alive")
        )
        if ka is None:
            return 1800
        return int(ka)
    except Exception:
        return 1800


def _interval_from_conf() -> int:
    """Read character_config.memory_consolidation_interval (clamped to {1,3,5})."""
    try:
        data = _load_plain()
        v = (data.get("character_config", {}) or {}).get(
            "memory_consolidation_interval"
        )
        if v is None:
            return memory_core.CONSOLIDATE_INTERVAL_DEFAULT
        return memory_core._clamp_interval(v)
    except Exception:
        return memory_core.CONSOLIDATE_INTERVAL_DEFAULT


# --------------------------------------------------------------------------- #
# Surgical writers (scoped to the specific sub-block extent — never a flat scan)
# --------------------------------------------------------------------------- #

def _asr_config_extent(lines: list) -> tuple[int, int]:
    """Return [start_after_header, end) of the character_config.asr_config block."""
    asr_re = re.compile(r"^(\s*)asr_config:\s*(#.*)?$")
    start, _, end = _find_block_extent(lines, asr_re)
    if start is None:
        raise KeyError("asr_config: line not found in conf.yaml")
    return start + 1, end


def _tts_config_extent(lines: list) -> tuple[int, int]:
    """Return [start_after_header, end) of the character_config.tts_config block."""
    tts_re = re.compile(r"^(\s*)tts_config:\s*(#.*)?$")
    start, _, end = _find_block_extent(lines, tts_re)
    if start is None:
        raise KeyError("tts_config: line not found in conf.yaml")
    return start + 1, end


def _sub_block_extent(
    lines: list, parent_start: int, parent_end: int, sub_key: str
) -> tuple[Optional[int], Optional[int]]:
    """Find a named sub-block ('sub_key:') strictly INSIDE [parent_start, parent_end).

    Returns (start_after_header, end) or (None, None). Scoping to the parent extent is
    what prevents clobbering a same-named leaf (api_key/model) in a sibling engine block.
    """
    sub_re = re.compile(r"^(\s*)" + re.escape(sub_key) + r":\s*(#.*)?$")
    s, _, e = _find_block_extent(lines, sub_re, start_from=parent_start)
    if s is None or s >= parent_end:
        return None, None
    # Clamp the sub-block's end to the parent extent (defensive).
    return s + 1, min(e, parent_end)


def _write_asr(
    asr_model: Optional[str],
    groq_api_key: Optional[str],
    azure_api_key: Optional[str],
    azure_region: Optional[str],
) -> bool:
    """Surgically rewrite asr_config.asr_model + the relevant cloud sub-block creds.

    Only non-None args are written. Leaves must already exist in conf.yaml. Atomic+.bak.
    """
    with open(CONF_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    asr_start, asr_end = _asr_config_extent(lines)

    if asr_model is not None:
        # asr_model is a single-quoted scalar (matches existing 'sherpa_onnx_asr').
        if not _rewrite_leaf(lines, asr_start, asr_end, "asr_model", asr_model):
            raise KeyError("asr_model leaf not found in asr_config")

    if groq_api_key is not None:
        gs, ge = _sub_block_extent(lines, asr_start, asr_end, "groq_whisper_asr")
        if gs is None:
            raise KeyError("groq_whisper_asr sub-block not found in asr_config")
        if not _rewrite_leaf(lines, gs, ge, "api_key", groq_api_key):
            raise KeyError("api_key leaf not found in groq_whisper_asr")

    if azure_api_key is not None or azure_region is not None:
        azs, aze = _sub_block_extent(lines, asr_start, asr_end, "azure_asr")
        if azs is None:
            raise KeyError("azure_asr sub-block not found in asr_config")
        if azure_api_key is not None:
            if not _rewrite_leaf(lines, azs, aze, "api_key", azure_api_key):
                raise KeyError("api_key leaf not found in azure_asr")
        if azure_region is not None:
            if not _rewrite_leaf(lines, azs, aze, "region", azure_region):
                raise KeyError("region leaf not found in azure_asr")

    _backup_once()
    _atomic_write(lines)
    return True


def _write_tts(
    tts_model: Optional[str],
    gpt_sovits_api_url: Optional[str],
    gpt_sovits_ref_audio_path: Optional[str],
) -> bool:
    """Surgically rewrite tts_config.tts_model + gpt_sovits_tts api_url/ref_audio_path."""
    with open(CONF_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    tts_start, tts_end = _tts_config_extent(lines)

    if tts_model is not None:
        if not _rewrite_leaf(lines, tts_start, tts_end, "tts_model", tts_model):
            raise KeyError("tts_model leaf not found in tts_config")

    if gpt_sovits_api_url is not None or gpt_sovits_ref_audio_path is not None:
        gs, ge = _sub_block_extent(lines, tts_start, tts_end, "gpt_sovits_tts")
        if gs is None:
            raise KeyError("gpt_sovits_tts sub-block not found in tts_config")
        if gpt_sovits_api_url is not None:
            if not _rewrite_leaf(lines, gs, ge, "api_url", gpt_sovits_api_url):
                raise KeyError("api_url leaf not found in gpt_sovits_tts")
        if gpt_sovits_ref_audio_path is not None:
            if not _rewrite_leaf(
                lines, gs, ge, "ref_audio_path", gpt_sovits_ref_audio_path
            ):
                raise KeyError("ref_audio_path leaf not found in gpt_sovits_tts")

    _backup_once()
    _atomic_write(lines)
    return True


def _write_keep_alive(keep_alive: int) -> bool:
    """Surgically rewrite the deep-nested ollama_llm.keep_alive (bare int).

    Path: character_config.agent_config.llm_configs.ollama_llm.keep_alive. Reached via
    chained _find_block_extent so the rewrite is scoped to ollama_llm only (other
    sub-blocks could contain a keep_alive-ish leaf). Atomic + .bak.
    """
    with open(CONF_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    agent_re = re.compile(r"^(\s*)agent_config:\s*(#.*)?$")
    a_start, _, a_end = _find_block_extent(lines, agent_re)
    if a_start is None:
        raise KeyError("agent_config: line not found in conf.yaml")

    llmc_re = re.compile(r"^(\s*)llm_configs:\s*(#.*)?$")
    l_start, _, l_end = _find_block_extent(lines, llmc_re, start_from=a_start + 1)
    if l_start is None or l_start >= a_end:
        raise KeyError("llm_configs: line not found in agent_config")
    l_end = min(l_end, a_end)

    oll_re = re.compile(r"^(\s*)ollama_llm:\s*(#.*)?$")
    o_start, _, o_end = _find_block_extent(lines, oll_re, start_from=l_start + 1)
    if o_start is None or o_start >= l_end:
        raise KeyError("ollama_llm: line not found in llm_configs")
    o_end = min(o_end, l_end)

    # keep_alive is a BARE int (e.g. 1800, can be -1) -> use the int writer.
    if not _rewrite_int_leaf(lines, o_start + 1, o_end, "keep_alive", keep_alive):
        raise KeyError("keep_alive leaf not found in ollama_llm")

    _backup_once()
    _atomic_write(lines)
    return True


def _write_consolidation_interval(interval: int) -> bool:
    """Surgically rewrite character_config.memory_consolidation_interval (bare int)."""
    from .memory_route import _character_config_extent

    with open(CONF_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    cc_start, cc_end = _character_config_extent(lines)
    if not _rewrite_int_leaf(
        lines, cc_start, cc_end, "memory_consolidation_interval", interval
    ):
        raise KeyError("memory_consolidation_interval leaf not found in character_config")
    _backup_once()
    _atomic_write(lines)
    return True


# --------------------------------------------------------------------------- #
# Route factory
# --------------------------------------------------------------------------- #

def init_perf_route() -> APIRouter:
    """REST endpoints for the 效能/硬體 settings panel. Localhost-only.

    - GET  /api/perf                  -> ASR/TTS engine + creds(masked) + keep_alive + interval
    - POST /api/perf/asr              -> set asr_model + cloud creds
    - POST /api/perf/tts              -> set tts_model + gpt_sovits fields
    - POST /api/perf/keep-alive       -> set ollama keep_alive
    - POST /api/perf/consolidation    -> set memory_consolidation_interval
    - POST /api/perf/preset           -> apply a named preset bundle (atomic, one write)
    """
    router = APIRouter()

    @router.get("/api/perf")
    async def get_perf(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        asr = _asr_from_conf()
        tts = _tts_from_conf()
        return JSONResponse(
            {
                **asr,
                **tts,
                "keep_alive": _keep_alive_from_conf(),
                "keep_alive_min": KEEP_ALIVE_MIN,
                "keep_alive_max": KEEP_ALIVE_MAX,
                "consolidation_interval": _interval_from_conf(),
                "consolidation_interval_choices": list(
                    memory_core.CONSOLIDATE_INTERVAL_CHOICES
                ),
                "asr_models": sorted(ASR_MODELS),
                "tts_models": sorted(TTS_MODELS),
                "presets": sorted(PRESETS.keys()),
            }
        )

    @router.post("/api/perf/asr")
    async def set_asr(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Invalid JSON body."}
            )
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Invalid JSON body."}
            )

        asr_model = None
        if "asr_model" in body:
            asr_model = str(body.get("asr_model") or "").strip()
            if asr_model not in ASR_MODELS:
                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "error": f"asr_model must be one of {sorted(ASR_MODELS)}.",
                    },
                )
        # Credentials: only persisted when a fresh (non-empty) value is supplied, so a
        # masked round-trip never overwrites the stored key. Region may be set freely.
        groq_api_key = None
        if body.get("groq_api_key"):
            groq_api_key = str(body.get("groq_api_key"))
        azure_api_key = None
        if body.get("azure_api_key"):
            azure_api_key = str(body.get("azure_api_key"))
        azure_region = None
        if "azure_region" in body and body.get("azure_region") is not None:
            azure_region = str(body.get("azure_region")).strip()

        if (
            asr_model is None
            and groq_api_key is None
            and azure_api_key is None
            and azure_region is None
        ):
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Nothing to update."},
            )

        try:
            await asyncio.to_thread(
                _write_asr, asr_model, groq_api_key, azure_api_key, azure_region
            )
        except Exception as e:
            logger.error(f"perf asr write failed: {type(e).__name__}: {e}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write config file."},
            )

        # NEVER echo raw keys — read back masked.
        logger.info(f"perf asr saved (asr_model={asr_model})")
        return JSONResponse(
            {"ok": True, **_asr_from_conf(), "restart_required": True}
        )

    @router.post("/api/perf/tts")
    async def set_tts(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Invalid JSON body."}
            )
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Invalid JSON body."}
            )

        tts_model = None
        if "tts_model" in body:
            tts_model = str(body.get("tts_model") or "").strip()
            if tts_model not in TTS_MODELS:
                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "error": f"tts_model must be one of {sorted(TTS_MODELS)}.",
                    },
                )
        api_url = None
        if "gpt_sovits_api_url" in body and body.get("gpt_sovits_api_url") is not None:
            api_url = str(body.get("gpt_sovits_api_url")).strip()
        ref_audio = None
        if (
            "gpt_sovits_ref_audio_path" in body
            and body.get("gpt_sovits_ref_audio_path") is not None
        ):
            ref_audio = str(body.get("gpt_sovits_ref_audio_path")).strip()

        if tts_model is None and api_url is None and ref_audio is None:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Nothing to update."},
            )

        try:
            await asyncio.to_thread(_write_tts, tts_model, api_url, ref_audio)
        except Exception as e:
            logger.error(f"perf tts write failed: {type(e).__name__}: {e}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write config file."},
            )

        logger.info(f"perf tts saved (tts_model={tts_model})")
        return JSONResponse(
            {"ok": True, **_tts_from_conf(), "restart_required": True}
        )

    @router.post("/api/perf/keep-alive")
    async def set_keep_alive(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Invalid JSON body."}
            )
        if not isinstance(body, dict) or "keep_alive" not in body:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Missing 'keep_alive' integer."},
            )
        try:
            raw = int(body.get("keep_alive"))
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "'keep_alive' must be an integer."},
            )
        if raw < KEEP_ALIVE_MIN or raw > KEEP_ALIVE_MAX:
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error": (
                        f"'keep_alive' must be between {KEEP_ALIVE_MIN} and "
                        f"{KEEP_ALIVE_MAX}."
                    ),
                },
            )

        try:
            await asyncio.to_thread(_write_keep_alive, raw)
        except Exception as e:
            logger.error(f"perf keep_alive write failed: {type(e).__name__}: {e}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write config file."},
            )

        logger.info(f"perf keep_alive saved (keep_alive={raw})")
        return JSONResponse(
            {"ok": True, "keep_alive": raw, "restart_required": True}
        )

    @router.post("/api/perf/consolidation")
    async def set_consolidation(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Invalid JSON body."}
            )
        if not isinstance(body, dict) or "interval" not in body:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Missing 'interval' integer."},
            )
        try:
            raw = int(body.get("interval"))
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "'interval' must be an integer."},
            )
        if raw not in memory_core.CONSOLIDATE_INTERVAL_CHOICES:
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error": (
                        "'interval' must be one of "
                        f"{list(memory_core.CONSOLIDATE_INTERVAL_CHOICES)}."
                    ),
                },
            )

        try:
            await asyncio.to_thread(_write_consolidation_interval, raw)
        except Exception as e:
            logger.error(f"perf consolidation write failed: {type(e).__name__}: {e}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write config file."},
            )

        logger.info(f"perf consolidation interval saved (interval={raw})")
        return JSONResponse(
            {
                "ok": True,
                "consolidation_interval": raw,
                # Gating reads context.character_config, which is baked at init.
                "restart_required": True,
            }
        )

    @router.post("/api/perf/preset")
    async def apply_preset(request: Request):
        """Apply a named preset bundle (輕量/標準/高效能) in ONE atomic conf write.

        All leaves the preset touches already exist in conf.yaml, so a single pass
        rewrites them together — no partial-apply window. The preset is a starting
        point; every individual control stays adjustable after.
        """
        if not _is_local_request(request):
            return _forbidden()
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Invalid JSON body."}
            )
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Invalid JSON body."}
            )
        name = str(body.get("name") or "").strip().lower()
        if name not in PRESETS:
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error": f"name must be one of {sorted(PRESETS.keys())}.",
                },
            )

        bundle = PRESETS[name]
        try:
            await asyncio.to_thread(_apply_preset_bundle, bundle)
        except Exception as e:
            logger.error(f"perf preset apply failed: {type(e).__name__}: {e}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write config file."},
            )

        logger.info(f"perf preset applied (name={name})")
        return JSONResponse(
            {
                "ok": True,
                "preset": name,
                "applied": bundle,
                "restart_required": True,
            }
        )

    return router


def _apply_preset_bundle(bundle: dict) -> bool:
    """Write all leaves of a preset bundle in a SINGLE atomic conf.yaml pass.

    Reads the file once, rewrites every targeted leaf in-place (scoped to the right
    block extent), then one atomic write — so there is no partial-apply window. All
    leaves pre-exist in conf.yaml (validated by the surgical writers, which raise
    KeyError if a leaf is missing -> the whole apply fails cleanly, nothing written).
    """
    from .memory_route import _character_config_extent
    from .translator_route import _rewrite_bool_leaf

    with open(CONF_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # --- character_config direct-child leaves ---
    cc_start, cc_end = _character_config_extent(lines)
    if "core_memory_max_chars" in bundle:
        if not _rewrite_int_leaf(
            lines, cc_start, cc_end, "core_memory_max_chars",
            int(bundle["core_memory_max_chars"]),
        ):
            raise KeyError("core_memory_max_chars leaf not found")
    if "fts_memory_enabled" in bundle:
        if not _rewrite_bool_leaf(
            lines, cc_start, cc_end, "fts_memory_enabled",
            bool(bundle["fts_memory_enabled"]),
        ):
            raise KeyError("fts_memory_enabled leaf not found")
    if "memory_consolidation_interval" in bundle:
        if not _rewrite_int_leaf(
            lines, cc_start, cc_end, "memory_consolidation_interval",
            int(bundle["memory_consolidation_interval"]),
        ):
            raise KeyError("memory_consolidation_interval leaf not found")

    # --- asr_model (re-find extent on the current lines; line count unchanged) ---
    if "asr_model" in bundle:
        asr_start, asr_end = _asr_config_extent(lines)
        if not _rewrite_leaf(
            lines, asr_start, asr_end, "asr_model", str(bundle["asr_model"])
        ):
            raise KeyError("asr_model leaf not found")

    # --- tts_model ---
    if "tts_model" in bundle:
        tts_start, tts_end = _tts_config_extent(lines)
        if not _rewrite_leaf(
            lines, tts_start, tts_end, "tts_model", str(bundle["tts_model"])
        ):
            raise KeyError("tts_model leaf not found")

    # --- ollama keep_alive (deep nested) ---
    if "keep_alive" in bundle:
        agent_re = re.compile(r"^(\s*)agent_config:\s*(#.*)?$")
        a_start, _, a_end = _find_block_extent(lines, agent_re)
        if a_start is None:
            raise KeyError("agent_config not found")
        llmc_re = re.compile(r"^(\s*)llm_configs:\s*(#.*)?$")
        l_start, _, l_end = _find_block_extent(lines, llmc_re, start_from=a_start + 1)
        if l_start is None or l_start >= a_end:
            raise KeyError("llm_configs not found")
        l_end = min(l_end, a_end)
        oll_re = re.compile(r"^(\s*)ollama_llm:\s*(#.*)?$")
        o_start, _, o_end = _find_block_extent(lines, oll_re, start_from=l_start + 1)
        if o_start is None or o_start >= l_end:
            raise KeyError("ollama_llm not found")
        o_end = min(o_end, l_end)
        if not _rewrite_int_leaf(
            lines, o_start + 1, o_end, "keep_alive", int(bundle["keep_alive"])
        ):
            raise KeyError("keep_alive leaf not found")

    _backup_once()
    _atomic_write(lines)
    return True
