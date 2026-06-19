"""
Cross-language voice + translated-subtitle endpoints.
=====================================================
Localhost-only REST endpoints that let a non-technical user turn on cross-language
voice AND a display-only translated subtitle without hand-editing YAML.

How the mechanism works (confirmed in service_context.py / conversation_utils.py):
- AUDIO (``translator_config.translate_audio``): when True, the reply text is run
  through a translate engine (``deeplx`` or ``llm``) to the target language BEFORE
  TTS, then the chosen edge_tts voice (e.g. a ja-JP voice) speaks the translation.
- SUBTITLE (``translator_config.translate_subtitle`` + ``subtitle_target_lang``):
  when True, the reply text is ALSO translated — but for the on-screen subtitle ONLY.
  This is display-only: the canonical reply (used for memory/history) is NEVER
  mutated, so what the AI "remembers" stays in the persona's reply language.
  A SEPARATE subtitle translate engine is built in service_context.init_translate
  (same provider, target = subtitle_target_lang). Default off = show 原文 verbatim.
- The two paths are INDEPENDENT: audio-only, subtitle-only, both, or neither. With
  the 'llm' engine, enabling BOTH (and different targets) translates each sentence
  TWICE -> roughly doubled per-sentence latency (deeplx is fast). The UI discloses
  this. This router owns the toggles for both, exposed to the settings UI.

Design notes (mirrors llm_config_route / character_route conventions):
- The localhost+proxy guard is REUSED verbatim (``_is_local_request`` / ``_forbidden``).
- conf.yaml is heavily commented, so writes are SURGICAL line edits (not a ruamel
  re-dump, which would normalize True->true / null across the hand-edited file — the
  exact churn llm_config_route documents). ruamel is used only to VALIDATE structure.
- The Pydantic validator (config_manager/tts_preprocessor.py) REQUIRES the matching
  provider sub-block (llm / deeplx / tencent) be non-None when translate_audio=True.
  The conf.yaml already has all three populated, so we NEVER blank them — we only flip
  ``translate_audio`` / ``translate_provider`` and rewrite leaf values inside the
  existing blocks. Removing a block would crash startup validation.
- The 'llm' engine reuses the player's already-configured LLM with zero extra setup:
  on enable we default the translator llm.api_endpoint + llm.model from the active
  openai_compatible_llm block (base_url + '/chat/completions', model).
- conf.yaml is loaded once at startup, BUT the translate engine is rebuilt by
  ``init_translate`` whenever a character is (re-)selected over WebSocket (switch-config
  re-reads conf.yaml from disk -> load_from_config -> init_translate). So the honest
  status is: re-selecting the character (or restarting) applies the change; the POST
  response signals ``restart_required: True`` as the safe baseline and the UI also
  tells the user a character re-switch hot-applies it.
- All writes atomic (temp + os.replace) + one-time conf.yaml.bak, like llm_config_route.
"""

import os
import re
import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse
from loguru import logger

# REUSE the localhost+proxy guard + yaml helper — do not diverge.
from .llm_config_route import _is_local_request, _forbidden, _make_yaml


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

CONF_PATH = "conf.yaml"

# Default ja-JP voice. The translator no longer SETS a base voice (the per-character
# voice in Character Manager decides spoken language); this is still surfaced in GET as
# an informational hint ("default_jp_voice") only.
DEFAULT_JP_VOICE = "ja-JP-NanamiNeural"
# A voice ShortName is ascii letters/digits/hyphens (e.g. "ja-JP-NanamiNeural").
# Retained for reference; no longer used now that POST does not validate/set a voice.
VOICE_SHORTNAME_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")

VALID_ENGINES = {"llm", "deeplx"}
DEFAULT_DEEPLX_ENDPOINT = "http://localhost:1188/v2/translate"
DEFAULT_DEEPLX_TARGET = "JA"
DEFAULT_LLM_TARGET = "日文"


# --------------------------------------------------------------------------- #
# Read helpers (ruamel round-trip)
# --------------------------------------------------------------------------- #

def _load_conf() -> Any:
    yaml = _make_yaml()
    with open(CONF_PATH, "r", encoding="utf-8") as f:
        return yaml.load(f)


def _get_translator_block(data: Any) -> Optional[Any]:
    try:
        return data["character_config"]["tts_preprocessor_config"]["translator_config"]
    except (KeyError, TypeError):
        return None


def _get_edge_tts_voice(data: Any) -> Optional[str]:
    try:
        voice = data["character_config"]["tts_config"]["edge_tts"]["voice"]
        return str(voice) if voice is not None else None
    except (KeyError, TypeError):
        return None


def _get_openai_llm(data: Any) -> Optional[Any]:
    try:
        return data["character_config"]["agent_config"]["llm_configs"][
            "openai_compatible_llm"
        ]
    except (KeyError, TypeError):
        return None


def _derive_llm_endpoint(base_url: Optional[str]) -> Optional[str]:
    """Turn an openai_compatible base_url into a chat/completions endpoint.

    e.g. 'http://localhost:11434/v1' -> 'http://localhost:11434/v1/chat/completions'.
    The translator's LLMTranslate posts to a full chat/completions URL (it does NOT
    append the path itself, see llm_translate.py), so we build it here.
    """
    if not base_url:
        return None
    b = str(base_url).rstrip("/")
    if b.endswith("/chat/completions"):
        return b
    return b + "/chat/completions"


# --------------------------------------------------------------------------- #
# Surgical write (preserve comments). Mirrors llm_config_route._write_openai_block.
# --------------------------------------------------------------------------- #

def _quote_yaml_scalar(value: str) -> str:
    """Single-quote a scalar for YAML; escape embedded single quotes."""
    return "'" + str(value).replace("'", "''") + "'"


def _find_block_extent(lines: list, key_re: re.Pattern, start_from: int = 0):
    """Locate a 'key:' line and the [start, end) extent of its indented block.

    Returns (key_index, block_indent, end_index) or (None, None, None).
    The block runs to the next line at <= the key's indentation (blanks/comments
    inside are treated as belonging to the block).
    """
    start = None
    block_indent = None
    for i in range(start_from, len(lines)):
        m = key_re.match(lines[i])
        if m:
            start = i
            block_indent = len(m.group(1))
            break
    if start is None:
        return None, None, None

    end = len(lines)
    for j in range(start + 1, len(lines)):
        raw = lines[j]
        if raw.strip() == "" or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent <= block_indent:
            end = j
            break
    return start, block_indent, end


def _rewrite_leaf(lines: list, start: int, end: int, key: str, new_val: str) -> bool:
    """Within lines[start:end], rewrite 'key: value' preserving indent + inline comment.

    Returns True if the leaf was found and rewritten.
    """
    for j in range(start, end):
        line = lines[j]
        stripped = line.lstrip()
        if stripped.startswith(key + ":"):
            indent_ws = line[: len(line) - len(stripped)]
            comment = ""
            m_comment = re.search(r"(\s+#.*?)\s*$", line.rstrip("\n"))
            if m_comment:
                comment = m_comment.group(1)
            lines[j] = f"{indent_ws}{key}: {_quote_yaml_scalar(new_val)}{comment}\n"
            return True
    return False


def _validate_translator_path() -> None:
    """Fail loudly (before any write) if the translator_config block is missing."""
    data = _load_conf()
    if _get_translator_block(data) is None:
        raise KeyError(
            "translator_config block not found in conf.yaml "
            "(character_config.tts_preprocessor_config.translator_config)"
        )


def _backup_once() -> None:
    if not os.path.exists(CONF_PATH + ".bak"):
        try:
            import shutil

            shutil.copy2(CONF_PATH, CONF_PATH + ".bak")
        except Exception as e:
            logger.warning(f"Could not create conf.yaml.bak: {type(e).__name__}")


def _atomic_write(lines: list) -> None:
    conf_dir = os.path.dirname(os.path.abspath(CONF_PATH)) or "."
    tmp_path = os.path.join(conf_dir, ".conf.yaml.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.replace(tmp_path, CONF_PATH)


def _rewrite_bool_leaf(lines: list, start: int, end: int, key: str, value: bool) -> bool:
    """Rewrite a BOOL leaf 'key: True/False' (unquoted) preserving indent + comment.

    _rewrite_leaf single-quotes scalars, which is wrong for YAML bools (they'd become
    strings). This writes the bare True/False literal instead. Returns True if found.
    """
    for j in range(start, end):
        line = lines[j]
        stripped = line.lstrip()
        if stripped.startswith(key + ":"):
            indent_ws = line[: len(line) - len(stripped)]
            comment = ""
            m = re.search(r"(\s+#.*?)\s*$", line.rstrip("\n"))
            if m:
                comment = m.group(1)
            lines[j] = f"{indent_ws}{key}: {'True' if value else 'False'}{comment}\n"
            return True
    return False


def _write_translator_config(
    *,
    enabled: bool,
    engine: str,
    speak_voice: Optional[str],
    deeplx_endpoint: Optional[str],
    deeplx_target_lang: Optional[str],
    llm_target_lang: Optional[str],
    llm_api_endpoint: Optional[str],
    llm_model: Optional[str],
    subtitle_enabled: Optional[bool] = None,
    subtitle_target_lang: Optional[str] = None,
) -> dict:
    """Surgically rewrite the translator_config leaves (+ optional base edge_tts.voice).

    NEVER deletes/blanks the llm / deeplx / tencent sub-blocks (validator requires the
    active provider's block be non-None when translate_audio=True). Only flips
    translate_audio + translate_provider (+ optional display-only subtitle leaves) and
    rewrites the requested leaf values inside the EXISTING blocks. Atomic write +
    one-time backup.

    Returns a dict of what was written (for the response / logging).
    """
    _validate_translator_path()

    with open(CONF_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 1. translator_config block extent.
    tc_re = re.compile(r"^(\s*)translator_config:\s*(#.*)?$")
    tc_start, tc_indent, tc_end = _find_block_extent(lines, tc_re)
    if tc_start is None:
        raise KeyError("translator_config: line not found in conf.yaml")

    written = {}

    # 2. Top-level leaves of translator_config: translate_audio + translate_provider.
    #    These live at tc_indent + step; rewrite via _rewrite_leaf scanned across the
    #    whole block but only those exact keys at the block's direct child indent.
    #    (translate_audio / translate_provider are unique within the block.)
    #    translate_audio is a bool -> write the bare True/False literal (not quoted).
    if not _rewrite_bool_leaf(lines, tc_start + 1, tc_end, "translate_audio", enabled):
        raise KeyError("translate_audio leaf not found in translator_config")
    written["translate_audio"] = enabled

    if not _rewrite_leaf(lines, tc_start + 1, tc_end, "translate_provider", engine):
        raise KeyError("translate_provider leaf not found in translator_config")
    written["translate_provider"] = engine

    # 2b. Display-only subtitle leaves (independent of translate_audio). Bool +
    #     quoted string. If a leaf is ABSENT (an older conf.yaml / template that
    #     predates the subtitle feature), INSERT it at the top of the
    #     translator_config block rather than failing the whole save with a
    #     KeyError -> "Could not write config file". tc_end is bumped so the later
    #     llm/deeplx block lookups (which guard on `< tc_end`) stay correct.
    if subtitle_enabled is not None:
        if not _rewrite_bool_leaf(
            lines, tc_start + 1, tc_end, "translate_subtitle", subtitle_enabled
        ):
            lines.insert(
                tc_start + 1,
                f"{' ' * (tc_indent + 2)}translate_subtitle: "
                f"{'True' if subtitle_enabled else 'False'}\n",
            )
            tc_end += 1
        written["translate_subtitle"] = subtitle_enabled
    if subtitle_target_lang is not None:
        if not _rewrite_leaf(
            lines, tc_start + 1, tc_end, "subtitle_target_lang", subtitle_target_lang
        ):
            lines.insert(
                tc_start + 1,
                f"{' ' * (tc_indent + 2)}subtitle_target_lang: "
                f"{_quote_yaml_scalar(subtitle_target_lang)}\n",
            )
            tc_end += 1
        written["subtitle_target_lang"] = subtitle_target_lang

    # 3. Nested llm block leaves (re-find extent after edits don't change line count).
    llm_re = re.compile(r"^(\s*)llm:\s*(#.*)?$")
    llm_start, _, llm_end = _find_block_extent(lines, llm_re, start_from=tc_start + 1)
    # Only touch the llm block if it's still inside translator_config's extent.
    if llm_start is not None and llm_start < tc_end:
        if llm_target_lang:
            _rewrite_leaf(lines, llm_start + 1, llm_end, "target_lang", llm_target_lang)
            written["llm.target_lang"] = llm_target_lang
        if llm_api_endpoint:
            _rewrite_leaf(lines, llm_start + 1, llm_end, "api_endpoint", llm_api_endpoint)
            written["llm.api_endpoint"] = llm_api_endpoint
        if llm_model:
            _rewrite_leaf(lines, llm_start + 1, llm_end, "model", llm_model)
            written["llm.model"] = llm_model

    # 4. Nested deeplx block leaves.
    deeplx_re = re.compile(r"^(\s*)deeplx:\s*(#.*)?$")
    dx_start, _, dx_end = _find_block_extent(lines, deeplx_re, start_from=tc_start + 1)
    if dx_start is not None and dx_start < tc_end:
        if deeplx_target_lang:
            _rewrite_leaf(lines, dx_start + 1, dx_end, "deeplx_target_lang",
                          deeplx_target_lang)
            written["deeplx.deeplx_target_lang"] = deeplx_target_lang
        if deeplx_endpoint:
            _rewrite_leaf(lines, dx_start + 1, dx_end, "deeplx_api_endpoint",
                          deeplx_endpoint)
            written["deeplx.deeplx_api_endpoint"] = deeplx_endpoint

    # 5. Optional: set the BASE edge_tts voice (separate top-level block).
    if speak_voice:
        edge_re = re.compile(r"^(\s*)edge_tts:\s*(#.*)?$")
        e_start, _, e_end = _find_block_extent(lines, edge_re)
        if e_start is not None:
            if _rewrite_leaf(lines, e_start + 1, e_end, "voice", speak_voice):
                written["edge_tts.voice"] = speak_voice
            else:
                logger.warning("edge_tts.voice leaf not found; voice not changed.")
        else:
            logger.warning("edge_tts block not found; voice not changed.")

    _backup_once()
    _atomic_write(lines)
    return written


# --------------------------------------------------------------------------- #
# Route factory
# --------------------------------------------------------------------------- #

def init_translator_route() -> APIRouter:
    """REST endpoints for the cross-language voice + translated-subtitle toggle.

    - GET  /api/translator-config -> current translator_config + base voice
    - POST /api/translator-config -> enable/disable + provider + target lang + voice
    """
    router = APIRouter()

    @router.get("/api/translator-config")
    async def get_translator_config(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            data = _load_conf()
        except Exception as e:
            logger.error(f"translator-config read failed: {type(e).__name__}")
            return JSONResponse(
                status_code=500, content={"error": "could not read config"}
            )

        block = _get_translator_block(data)
        if block is None:
            return JSONResponse(
                status_code=500,
                content={"error": "translator_config block missing in conf.yaml"},
            )

        def _sub(name: str, key: str, default=""):
            try:
                sub = block.get(name)
                if sub is None:
                    return default
                v = sub.get(key)
                return str(v) if v is not None else default
            except Exception:
                return default

        engine = str(block.get("translate_provider") or "llm")
        # The UI only offers llm / deeplx; if conf is set to tencent, fall back to
        # showing 'llm' as the selected engine but keep enabled state honest.
        ui_engine = engine if engine in VALID_ENGINES else "llm"

        subtitle_target = block.get("subtitle_target_lang")
        return JSONResponse(
            {
                "enabled": bool(block.get("translate_audio")),
                "engine": ui_engine,
                "raw_provider": engine,
                "llm_target_lang": _sub("llm", "target_lang", DEFAULT_LLM_TARGET),
                "llm_endpoint": _sub("llm", "api_endpoint"),
                "llm_model": _sub("llm", "model"),
                "deeplx_target_lang": _sub(
                    "deeplx", "deeplx_target_lang", DEFAULT_DEEPLX_TARGET
                ),
                "deeplx_endpoint": _sub(
                    "deeplx", "deeplx_api_endpoint", DEFAULT_DEEPLX_ENDPOINT
                ),
                "speak_voice": _get_edge_tts_voice(data) or "",
                "default_jp_voice": DEFAULT_JP_VOICE,
                # Display-only subtitle translation (independent of audio).
                "translate_subtitle": bool(block.get("translate_subtitle")),
                "subtitle_target_lang": (
                    str(subtitle_target) if subtitle_target is not None else ""
                ),
            }
        )

    @router.post("/api/translator-config")
    async def save_translator_config(request: Request):
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

        # Audio translation is now AUTOMATIC (per-sentence V != R decision), so there is
        # no user on/off toggle. translate_audio is an internal auto-on flag: default to
        # True when the body omits "enabled" so the frontend no longer needs to send it
        # and the engine stays built. (If a caller explicitly sends enabled=False we
        # still honor it for backward compat / manual override.)
        enabled = bool(body.get("enabled", True))
        engine = str(body.get("engine", "llm")).strip().lower()
        if engine not in VALID_ENGINES:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "engine must be 'llm' or 'deeplx'."},
            )

        # Display-only subtitle translation (optional; independent of audio). Only
        # written when the caller supplies the key, so a partial POST never clobbers
        # an existing subtitle setting.
        subtitle_enabled = None
        subtitle_target_lang = None
        if "translate_subtitle" in body:
            subtitle_enabled = bool(body.get("translate_subtitle"))
        if "subtitle_target_lang" in body:
            stl = body.get("subtitle_target_lang")
            subtitle_target_lang = str(stl).strip() if stl is not None else ""
        # Guard the validator: enabling subtitle translation requires a target lang.
        if subtitle_enabled:
            effective_target = subtitle_target_lang
            if effective_target is None:
                # caller flipped subtitle on without sending a target this time:
                # read the currently-stored one so we don't fail the validator.
                try:
                    cur = _get_translator_block(_load_conf())
                    cur_t = cur.get("subtitle_target_lang") if cur else None
                    effective_target = str(cur_t).strip() if cur_t else ""
                except Exception:
                    effective_target = ""
            if not effective_target:
                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "error": "subtitle_target_lang is required when "
                        "translate_subtitle is enabled.",
                    },
                )

        # Voice is NO LONGER set here. The spoken voice is chosen ONCE per character in
        # the Character Manager (edge_tts.voice). The translator only flips translate_audio
        # + provider + target lang. We pass speak_voice=None so _write_translator_config
        # SKIPS touching edge_tts.voice (it is guarded by `if speak_voice:`), leaving the
        # per-character voice intact. Any speak_voice in the body is ignored.
        speak_voice = None

        deeplx_endpoint = body.get("deeplx_endpoint")
        deeplx_endpoint = str(deeplx_endpoint).strip() if deeplx_endpoint else None
        deeplx_target = body.get("deeplx_target_lang")
        deeplx_target = (
            str(deeplx_target).strip() if deeplx_target else DEFAULT_DEEPLX_TARGET
        )
        llm_target = body.get("llm_target_lang")
        llm_target = str(llm_target).strip() if llm_target else DEFAULT_LLM_TARGET

        # For the 'llm' engine: default the translator's endpoint + model from the
        # player's already-configured LLM so it works with zero extra setup, UNLESS
        # the caller explicitly supplied them.
        llm_api_endpoint = body.get("llm_endpoint")
        llm_api_endpoint = str(llm_api_endpoint).strip() if llm_api_endpoint else None
        llm_model = body.get("llm_model")
        llm_model = str(llm_model).strip() if llm_model else None
        if engine == "llm" and (not llm_api_endpoint or not llm_model):
            try:
                data = _load_conf()
                openai_block = _get_openai_llm(data)
                if openai_block is not None:
                    if not llm_api_endpoint:
                        llm_api_endpoint = _derive_llm_endpoint(
                            openai_block.get("base_url")
                        )
                    if not llm_model:
                        m = openai_block.get("model")
                        llm_model = str(m) if m is not None else None
            except Exception as e:
                logger.warning(
                    f"could not derive llm translator defaults: {type(e).__name__}"
                )

        try:
            written = await asyncio.to_thread(
                _write_translator_config,
                enabled=enabled,
                engine=engine,
                speak_voice=speak_voice,  # always None now: do not touch edge_tts.voice
                deeplx_endpoint=deeplx_endpoint,
                deeplx_target_lang=deeplx_target,
                llm_target_lang=llm_target,
                llm_api_endpoint=llm_api_endpoint,
                llm_model=llm_model,
                subtitle_enabled=subtitle_enabled,
                subtitle_target_lang=subtitle_target_lang,
            )
        except Exception as e:
            logger.error(f"translator-config write failed: {type(e).__name__}: {e}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write config file."},
            )

        logger.info(
            f"translator-config saved (audio={enabled}, engine={engine}, "
            f"subtitle={subtitle_enabled})"
        )
        return JSONResponse(
            {
                "ok": True,
                "enabled": enabled,
                "engine": engine,
                "translate_subtitle": (
                    subtitle_enabled
                    if subtitle_enabled is not None
                    else bool(written.get("translate_subtitle"))
                ),
                "subtitle_target_lang": (
                    subtitle_target_lang if subtitle_target_lang is not None else ""
                ),
                # The translator no longer sets a base voice; the per-character voice
                # (Character Manager) decides the spoken language. Kept as "" for
                # response-shape stability — the UI no longer reads it.
                "speak_voice": "",
                "written": written,
                # conf.yaml loads once at startup; the translate engine is rebuilt on
                # init_translate (server start or character re-select). Safe baseline:
                # signal restart_required; the UI also says re-selecting hot-applies it.
                "restart_required": True,
            }
        )

    @router.get("/api/player-language")
    async def get_player_language(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            data = _load_conf()
            sysblk = data.get("system_config") or {}
            lang = sysblk.get("player_language")
            return JSONResponse({"language": str(lang) if lang is not None else ""})
        except Exception as e:
            logger.error(f"player-language read failed: {type(e).__name__}")
            return JSONResponse(status_code=500, content={"error": "could not read config"})

    @router.get("/api/default-background")
    async def get_default_background(request: Request):
        """Server-configured default background (system_config.default_background).
        The frontend applies it once per browser so the background can be set
        server-side — works in Safari, where the per-browser picker is unreliable."""
        if not _is_local_request(request):
            return _forbidden()
        try:
            data = _load_conf()
            sysblk = data.get("system_config") or {}
            bg = sysblk.get("default_background")
            return JSONResponse({"background": str(bg) if bg is not None else ""})
        except Exception as e:
            logger.error(f"default-background read failed: {type(e).__name__}")
            return JSONResponse(status_code=500, content={"error": "could not read config"})

    @router.post("/api/player-language")
    async def save_player_language(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid JSON body."})
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid JSON body."})
        lang = body.get("language")
        lang = str(lang).strip() if lang is not None else ""

        def _write_player_language(value: str) -> None:
            with open(CONF_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            sc_re = re.compile(r"^(\s*)system_config:\s*(#.*)?$")
            sc_start, sc_indent, sc_end = _find_block_extent(lines, sc_re)
            if sc_start is None:
                raise KeyError("system_config: line not found in conf.yaml")
            if not _rewrite_leaf(lines, sc_start + 1, sc_end, "player_language", value):
                lines.insert(sc_start + 1, f"{' ' * (sc_indent + 2)}player_language: {_quote_yaml_scalar(value)}\n")
            _backup_once()
            _atomic_write(lines)

        try:
            await asyncio.to_thread(_write_player_language, lang)
        except Exception as e:
            logger.error(f"player-language write failed: {type(e).__name__}: {e}")
            return JSONResponse(status_code=500, content={"ok": False, "error": "Could not write config file."})

        logger.info(f"player-language saved (language={lang!r})")
        return JSONResponse({"ok": True, "language": lang, "restart_required": True})

    @router.get("/api/player-prompt")
    async def get_player_prompt(request: Request):
        """Global player-context directive (system_config.player_prompt). Injected into
        EVERY character's system prompt by service_context.construct_system_prompt."""
        if not _is_local_request(request):
            return _forbidden()
        try:
            data = _load_conf()
            sysblk = data.get("system_config") or {}
            prompt = sysblk.get("player_prompt")
            return JSONResponse({"prompt": str(prompt) if prompt is not None else ""})
        except Exception as e:
            logger.error(f"player-prompt read failed: {type(e).__name__}")
            return JSONResponse(status_code=500, content={"error": "could not read config"})

    @router.post("/api/player-prompt")
    async def save_player_prompt(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid JSON body."})
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid JSON body."})
        prompt = body.get("prompt")
        prompt = str(prompt) if prompt is not None else ""
        # player_prompt is a SHORT single-line directive. Collapse any newlines (and the
        # surrounding whitespace) to single spaces before writing so it stays a one-line
        # YAML scalar — avoids multi-line/block-scalar churn in the hand-edited conf.yaml.
        prompt = re.sub(r"\s*\n\s*", " ", prompt).strip()

        def _write_player_prompt(value: str) -> None:
            with open(CONF_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            sc_re = re.compile(r"^(\s*)system_config:\s*(#.*)?$")
            sc_start, sc_indent, sc_end = _find_block_extent(lines, sc_re)
            if sc_start is None:
                raise KeyError("system_config: line not found in conf.yaml")
            if not _rewrite_leaf(lines, sc_start + 1, sc_end, "player_prompt", value):
                lines.insert(sc_start + 1, f"{' ' * (sc_indent + 2)}player_prompt: {_quote_yaml_scalar(value)}\n")
            _backup_once()
            _atomic_write(lines)

        try:
            await asyncio.to_thread(_write_player_prompt, prompt)
        except Exception as e:
            logger.error(f"player-prompt write failed: {type(e).__name__}: {e}")
            return JSONResponse(status_code=500, content={"ok": False, "error": "Could not write config file."})

        logger.info(f"player-prompt saved (len={len(prompt)})")
        return JSONResponse({"ok": True, "prompt": prompt, "restart_required": True})

    @router.get("/api/agent-config/use-mcpp")
    async def get_use_mcpp(request: Request):
        """use_mcpp (MCP Plus = web search / tools) toggle. Nested leaf:
        character_config.agent_config.agent_settings.basic_memory_agent.use_mcpp.
        Default False when absent."""
        if not _is_local_request(request):
            return _forbidden()
        try:
            data = _load_conf()
            bma = (
                ((data.get("character_config") or {}).get("agent_config") or {})
                .get("agent_settings") or {}
            ).get("basic_memory_agent") or {}
            return JSONResponse({"use_mcpp": bool(bma.get("use_mcpp", False))})
        except Exception as e:
            logger.error(f"use-mcpp read failed: {type(e).__name__}")
            return JSONResponse(status_code=500, content={"error": "could not read config"})

    @router.post("/api/agent-config/use-mcpp")
    async def save_use_mcpp(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid JSON body."})
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid JSON body."})
        use_mcpp = bool(body.get("use_mcpp"))

        def _write_use_mcpp(value: bool) -> None:
            with open(CONF_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            # Drill: agent_settings block -> basic_memory_agent block -> use_mcpp bool.
            as_re = re.compile(r"^(\s*)agent_settings:\s*(#.*)?$")
            as_start, as_indent, as_end = _find_block_extent(lines, as_re)
            if as_start is None:
                raise KeyError("agent_settings: line not found in conf.yaml")
            bma_re = re.compile(r"^(\s*)basic_memory_agent:\s*(#.*)?$")
            bma_start, bma_indent, bma_end = _find_block_extent(
                lines, bma_re, start_from=as_start + 1
            )
            if bma_start is None or bma_start >= as_end:
                raise KeyError(
                    "basic_memory_agent: line not found inside agent_settings"
                )
            # use_mcpp is a YAML bool -> write literal True/False, never quoted.
            if not _rewrite_bool_leaf(lines, bma_start + 1, bma_end, "use_mcpp", value):
                lines.insert(
                    bma_start + 1,
                    f"{' ' * (bma_indent + 2)}use_mcpp: {'True' if value else 'False'}\n",
                )
            _backup_once()
            _atomic_write(lines)

        try:
            await asyncio.to_thread(_write_use_mcpp, use_mcpp)
        except Exception as e:
            logger.error(f"use-mcpp write failed: {type(e).__name__}: {e}")
            return JSONResponse(status_code=500, content={"ok": False, "error": "Could not write config file."})

        logger.info(f"use-mcpp saved (use_mcpp={use_mcpp})")
        return JSONResponse({"ok": True, "use_mcpp": use_mcpp, "restart_required": True})

    return router
