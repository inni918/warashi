"""
Long-term (core) memory settings endpoints.
==========================================
Localhost-only REST endpoints that let a non-technical user manage the active
character's long-term memory WITHOUT touching YAML by hand:

- GET  /api/memory?conf_uid=<uid>  -> on/off flag + current core memory content
- POST /api/memory        {conf_uid, content}   -> overwrite the core memory (manual edit)
- POST /api/memory/toggle {conf_uid, enabled}  -> flip long_term_memory_enabled
- POST /api/memory/clear  {conf_uid}            -> empty (forget) the core memory

Memory is per-character (chat_history/<conf_uid>/core_memory.md), so every endpoint
is keyed by conf_uid. The frontend already tracks the active conf_uid (from the
WS 'set-model-and-conf' message), so it passes it explicitly. If omitted, we fall
back to the base conf.yaml character_config.conf_uid.

Design notes (mirror translator_route / character_route conventions):
- The localhost+proxy guard is REUSED verbatim (``_is_local_request`` / ``_forbidden``).
- conf_uid is VALIDATED against the set of known conf_uids (base + every override
  file) before it ever builds a chat_history/<conf_uid>/core_memory.md path, to
  prevent path traversal / arbitrary file truncation.
- The on/off flag lives at character_config.long_term_memory_enabled in conf.yaml
  (per-character, default True). Toggling surgically rewrites that one bool leaf,
  preserving comments (same line-surgical + atomic-write + one-time .bak machinery
  as the LLM/translator wizards). A full ruamel re-dump would churn the file.
- CLEAR truncates core_memory.md to '' (does NOT delete the file or the rest of the
  character's chat history) so the AI "forgets" without losing conversation logs.
- Toggling reports restart_required:True honestly because the agent's system prompt
  is baked at init; the phase-1.5 refresh makes turning memory OFF stop new
  injection next turn, and consolidation gating is immediate next turn.
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

# REUSE the surgical conf.yaml write machinery from translator_route.
from .translator_route import (
    _find_block_extent,
    _rewrite_bool_leaf,
    _backup_once,
    _atomic_write,
    CONF_PATH,
)

# REUSE conf_uid discovery (path-traversal guard) + memory helpers.
from .character_route import _existing_conf_uids
from .config_manager.utils import read_yaml
from . import memory_core
from . import memory_fts


# --------------------------------------------------------------------------- #
# Read helpers
# --------------------------------------------------------------------------- #

def _load_conf_plain() -> Any:
    """Round-trip load conf.yaml (only for reading scalar values)."""
    yaml = _make_yaml()
    with open(CONF_PATH, "r", encoding="utf-8") as f:
        return yaml.load(f)


def _base_conf_uid() -> Optional[str]:
    """The base character's conf_uid from conf.yaml (fallback when none supplied)."""
    try:
        data = read_yaml(CONF_PATH) or {}
        u = data.get("character_config", {}).get("conf_uid")
        return str(u) if u else None
    except Exception:
        return None


def _memory_enabled_from_conf() -> bool:
    """Read character_config.long_term_memory_enabled from base conf.yaml (default True)."""
    try:
        data = read_yaml(CONF_PATH) or {}
        v = data.get("character_config", {}).get("long_term_memory_enabled")
        # Missing key -> default enabled (matches the Pydantic default).
        return True if v is None else bool(v)
    except Exception:
        return True


def _cap_from_conf() -> int:
    """Read character_config.core_memory_max_chars from base conf.yaml.

    Missing/invalid -> the module default (memory_core.CAP_CHARS = 1500), bounded
    to [CAP_MIN, CAP_MAX] so the UI never shows an out-of-range value.
    """
    try:
        data = read_yaml(CONF_PATH) or {}
        v = data.get("character_config", {}).get("core_memory_max_chars")
        if v is None:
            return memory_core.CAP_CHARS
        return memory_core._clamp_cap(v)
    except Exception:
        return memory_core.CAP_CHARS


def _interval_from_conf() -> int:
    """Read character_config.memory_consolidation_interval (clamped to {1,3,5}).

    Missing/invalid -> the module default (1 = every turn). Surfaced so the UI shows
    the saved value, single-sourced from memory_core's choices.
    """
    try:
        data = read_yaml(CONF_PATH) or {}
        v = data.get("character_config", {}).get("memory_consolidation_interval")
        if v is None:
            return memory_core.CONSOLIDATE_INTERVAL_DEFAULT
        return memory_core._clamp_interval(v)
    except Exception:
        return memory_core.CONSOLIDATE_INTERVAL_DEFAULT


def _fts_from_conf() -> tuple[bool, int]:
    """Read (fts_memory_enabled, fts_memory_top_k) from base conf.yaml.

    Missing/invalid -> (False, 3), matching the Pydantic defaults. top_k is bounded
    to [1, 10].
    """
    enabled = False
    top_k = 3
    try:
        data = read_yaml(CONF_PATH) or {}
        cc = data.get("character_config", {}) or {}
        v = cc.get("fts_memory_enabled")
        if v is not None:
            enabled = bool(v)
        k = cc.get("fts_memory_top_k")
        if k is not None:
            try:
                top_k = max(1, min(10, int(k)))
            except (TypeError, ValueError):
                top_k = 3
    except Exception:
        pass
    return enabled, top_k


def _resolve_conf_uid(supplied: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Validate a client-supplied conf_uid against the known set, else fall back to base.

    Returns ``(conf_uid, error)``. ``error`` is non-None when the supplied uid is
    unknown (rejected to prevent arbitrary-path access). A falsy ``supplied`` falls
    back to the base conf_uid without error.
    """
    if supplied is not None and str(supplied).strip():
        uid = str(supplied).strip()
        # Hard reject obvious traversal even before the known-set check.
        if os.sep in uid or "/" in uid or "\\" in uid or ".." in uid:
            return None, "Invalid conf_uid."
        known = _existing_conf_uids()
        if uid not in known:
            return None, "Unknown conf_uid."
        return uid, None
    # Fallback: the active base character.
    base = _base_conf_uid()
    if not base:
        return None, "No conf_uid available."
    return base, None


# --------------------------------------------------------------------------- #
# Surgical write of the long_term_memory_enabled bool leaf
# --------------------------------------------------------------------------- #

def _write_memory_enabled(enabled: bool) -> bool:
    """Surgically flip character_config.long_term_memory_enabled, preserving comments.

    The leaf must already exist in conf.yaml (added by hand). Atomic + one-time .bak.
    Returns True on success.
    """
    with open(CONF_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    cc_re = re.compile(r"^(\s*)character_config:\s*(#.*)?$")
    cc_start, _, cc_end = _find_block_extent(lines, cc_re)
    if cc_start is None:
        raise KeyError("character_config: line not found in conf.yaml")

    # Only target the DIRECT child leaf of character_config (not any nested key) by
    # scanning the whole block; long_term_memory_enabled is unique within it.
    if not _rewrite_bool_leaf(
        lines, cc_start + 1, cc_end, "long_term_memory_enabled", enabled
    ):
        raise KeyError("long_term_memory_enabled leaf not found in character_config")

    _backup_once()
    _atomic_write(lines)
    return True


def _rewrite_int_leaf(lines: list, start: int, end: int, key: str, value: int) -> bool:
    """Rewrite an INTEGER leaf 'key: 1500' (bare literal) preserving indent + comment.

    translator_route._rewrite_leaf single-quotes scalars (would store the int as a
    STRING and fail Pydantic int parse), and _rewrite_bool_leaf writes True/False — so
    integers need this dedicated writer. Same structure as _rewrite_bool_leaf. Returns
    True if the leaf was found and rewritten.
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
            lines[j] = f"{indent_ws}{key}: {int(value)}{comment}\n"
            return True
    return False


def _character_config_extent(lines: list) -> tuple[int, int]:
    """Return (start_after_header, end) line range of the character_config block.

    Raises KeyError if character_config: is not found.
    """
    cc_re = re.compile(r"^(\s*)character_config:\s*(#.*)?$")
    cc_start, _, cc_end = _find_block_extent(lines, cc_re)
    if cc_start is None:
        raise KeyError("character_config: line not found in conf.yaml")
    return cc_start + 1, cc_end


def _write_core_memory_cap(cap: int) -> bool:
    """Surgically rewrite character_config.core_memory_max_chars (bare int).

    The leaf must already exist in conf.yaml. Atomic + one-time .bak. Returns True.
    """
    with open(CONF_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    cc_start, cc_end = _character_config_extent(lines)
    if not _rewrite_int_leaf(lines, cc_start, cc_end, "core_memory_max_chars", cap):
        raise KeyError("core_memory_max_chars leaf not found in character_config")
    _backup_once()
    _atomic_write(lines)
    return True


def _write_fts_settings(
    enabled: Optional[bool], top_k: Optional[int]
) -> bool:
    """Surgically rewrite fts_memory_enabled (bool) and/or fts_memory_top_k (int).

    Only the leaves explicitly supplied (non-None) are rewritten, so a partial POST
    never clobbers the other. Leaves must already exist in conf.yaml. Atomic + .bak.
    """
    with open(CONF_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    cc_start, cc_end = _character_config_extent(lines)
    if enabled is not None:
        if not _rewrite_bool_leaf(
            lines, cc_start, cc_end, "fts_memory_enabled", enabled
        ):
            raise KeyError("fts_memory_enabled leaf not found in character_config")
    if top_k is not None:
        if not _rewrite_int_leaf(
            lines, cc_start, cc_end, "fts_memory_top_k", top_k
        ):
            raise KeyError("fts_memory_top_k leaf not found in character_config")
    _backup_once()
    _atomic_write(lines)
    return True


def _write_consolidation_interval(interval: int) -> bool:
    """Surgically rewrite character_config.memory_consolidation_interval (bare int).

    The leaf must already exist in conf.yaml. Atomic + one-time .bak. Returns True.
    (perf_route exposes the same setting via /api/perf/consolidation; this mirror lets
    the memory tab save it through the memory namespace the FE already calls.)
    """
    with open(CONF_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    cc_start, cc_end = _character_config_extent(lines)
    if not _rewrite_int_leaf(
        lines, cc_start, cc_end, "memory_consolidation_interval", interval
    ):
        raise KeyError(
            "memory_consolidation_interval leaf not found in character_config"
        )
    _backup_once()
    _atomic_write(lines)
    return True


# --------------------------------------------------------------------------- #
# Route factory
# --------------------------------------------------------------------------- #

def init_memory_route() -> APIRouter:
    """REST endpoints for the in-app long-term-memory settings panel. Localhost-only.

    - GET  /api/memory?conf_uid=<uid>  -> enabled + core memory content
    - POST /api/memory                 -> overwrite the active character's core memory
    - POST /api/memory/toggle          -> set long_term_memory_enabled
    - POST /api/memory/clear           -> empty the active character's core memory
    """
    router = APIRouter()

    @router.get("/api/memory")
    async def get_memory(request: Request):
        if not _is_local_request(request):
            return _forbidden()

        supplied = request.query_params.get("conf_uid")
        conf_uid, err = _resolve_conf_uid(supplied)
        if err:
            return JSONResponse(status_code=400, content={"error": err})

        content = memory_core.load_core_memory(conf_uid)
        path = memory_core.core_memory_path(conf_uid)
        fts_enabled, fts_top_k = _fts_from_conf()
        return JSONResponse(
            {
                "conf_uid": conf_uid,
                "enabled": _memory_enabled_from_conf(),
                "content": content,
                "exists": os.path.isfile(path),
                "char_count": len(content),
                # Per-conf configurable cap (default 1500). Surfaced so the UI shows
                # the saved value, not the hardcoded module default.
                "cap": _cap_from_conf(),
                "cap_min": memory_core.CAP_MIN,
                "cap_max": memory_core.CAP_MAX,
                # Opt-in deep-recall (FTS5 full-history retrieval) state.
                "fts_enabled": fts_enabled,
                "fts_top_k": fts_top_k,
                # Single-sourced bounds so the UI label can show "1–10" from the server.
                "fts_top_k_min": 1,
                "fts_top_k_max": 10,
                "fts_indexed": memory_fts.index_exists(conf_uid),
                # Consolidation throttle (every N turns); choices single-sourced.
                "consolidation_interval": _interval_from_conf(),
                "consolidation_interval_choices": list(
                    memory_core.CONSOLIDATE_INTERVAL_CHOICES
                ),
            }
        )

    @router.post("/api/memory")
    async def save_memory(request: Request):
        """Overwrite the active character's core memory with user-edited content.

        Lets a non-technical user fix what the AI mis-remembered / doesn't want kept,
        straight from the memory tab. Localhost-only, conf_uid validated against the
        known set (path-traversal guard), same as every other handler here. Content
        over the per-conf cap is stored as-is (the next consolidation compacts it);
        memory_core.save_core_memory logs a warning rather than truncating mid-word.
        """
        if not _is_local_request(request):
            return _forbidden()
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Invalid JSON body."}
            )
        if not isinstance(body, dict) or "content" not in body:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Missing 'content' string."},
            )

        conf_uid, err = _resolve_conf_uid(body.get("conf_uid"))
        if err:
            return JSONResponse(status_code=400, content={"ok": False, "error": err})

        content = body.get("content")
        if not isinstance(content, str):
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "'content' must be a string."},
            )

        cap = _cap_from_conf()
        ok = await asyncio.to_thread(
            memory_core.save_core_memory, conf_uid, content, cap
        )
        if not ok:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not save core memory."},
            )

        # Read back what was actually stored so the UI's char count is honest.
        stored = memory_core.load_core_memory(conf_uid)
        logger.info(f"core memory manually saved (conf_uid={conf_uid})")
        return JSONResponse(
            {
                "ok": True,
                "conf_uid": conf_uid,
                "char_count": len(stored),
                "cap": cap,
                # Memory already injected into the running agent's system prompt is
                # baked at init; the edited content fully applies after a character
                # re-select / restart. Saved to disk + next consolidation reads it
                # immediately.
                "restart_required": True,
            }
        )

    @router.post("/api/memory/toggle")
    async def toggle_memory(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Invalid JSON body."}
            )
        if not isinstance(body, dict) or "enabled" not in body:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Missing 'enabled' boolean."},
            )

        # conf_uid is validated for response shape, but the flag itself is per the
        # base character_config in conf.yaml (the only place the running config reads).
        conf_uid, err = _resolve_conf_uid(body.get("conf_uid"))
        if err:
            return JSONResponse(status_code=400, content={"ok": False, "error": err})

        enabled = bool(body.get("enabled"))
        try:
            await asyncio.to_thread(_write_memory_enabled, enabled)
        except Exception as e:
            logger.error(f"memory toggle write failed: {type(e).__name__}: {e}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write config file."},
            )

        logger.info(f"memory toggle saved (enabled={enabled})")
        return JSONResponse(
            {
                "ok": True,
                "conf_uid": conf_uid,
                "enabled": enabled,
                # The agent's system prompt is baked at init; dropping already-injected
                # memory fully applies after a character re-select / restart. New
                # injection stops next turn (phase-1.5) and consolidation gating is
                # immediate next turn.
                "restart_required": True,
            }
        )

    @router.post("/api/memory/clear")
    async def clear_memory(request: Request):
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

        conf_uid, err = _resolve_conf_uid(body.get("conf_uid"))
        if err:
            return JSONResponse(status_code=400, content={"ok": False, "error": err})

        ok = await asyncio.to_thread(memory_core.clear_core_memory, conf_uid)
        if not ok:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not clear core memory."},
            )

        logger.info(f"core memory cleared (conf_uid={conf_uid})")
        return JSONResponse({"ok": True, "conf_uid": conf_uid, "cleared": True})

    @router.post("/api/memory/cap")
    async def set_cap(request: Request):
        """Set character_config.core_memory_max_chars (bounded [500, 8000])."""
        if not _is_local_request(request):
            return _forbidden()
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Invalid JSON body."}
            )
        if not isinstance(body, dict) or "cap" not in body:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Missing 'cap' integer."},
            )

        conf_uid, err = _resolve_conf_uid(body.get("conf_uid"))
        if err:
            return JSONResponse(status_code=400, content={"ok": False, "error": err})

        try:
            raw = int(body.get("cap"))
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "'cap' must be an integer."},
            )
        if raw < memory_core.CAP_MIN or raw > memory_core.CAP_MAX:
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error": (
                        f"'cap' must be between {memory_core.CAP_MIN} and "
                        f"{memory_core.CAP_MAX}."
                    ),
                },
            )

        try:
            await asyncio.to_thread(_write_core_memory_cap, raw)
        except Exception as e:
            logger.error(f"memory cap write failed: {type(e).__name__}: {e}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write config file."},
            )

        logger.info(f"core memory cap saved (cap={raw})")
        return JSONResponse(
            {
                "ok": True,
                "conf_uid": conf_uid,
                "cap": raw,
                # The running character_config is baked at init; the new cap applies to
                # consolidation after a character re-select / restart. GET reads live
                # conf so the UI shows the saved value immediately.
                "restart_required": True,
            }
        )

    @router.post("/api/memory/consolidation")
    async def set_consolidation(request: Request):
        """Set character_config.memory_consolidation_interval (one of {1,3,5}).

        Mirrors /api/perf/consolidation but on the memory namespace the FE's memory
        hook calls. 1 = consolidate every turn (default); 3/5 halve the consolidation
        LLM calls for weak/local models.
        """
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

        conf_uid, err = _resolve_conf_uid(body.get("conf_uid"))
        if err:
            return JSONResponse(status_code=400, content={"ok": False, "error": err})

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
            logger.error(f"memory consolidation write failed: {type(e).__name__}: {e}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write config file."},
            )

        logger.info(f"memory consolidation interval saved (interval={raw})")
        return JSONResponse(
            {
                "ok": True,
                "conf_uid": conf_uid,
                "consolidation_interval": raw,
                # Gating reads context.character_config, baked at init.
                "restart_required": True,
            }
        )

    @router.post("/api/memory/fts")
    async def set_fts(request: Request):
        """Set fts_memory_enabled (bool) and/or fts_memory_top_k (int, [1,10])."""
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
        if "enabled" not in body and "top_k" not in body:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Provide 'enabled' and/or 'top_k'."},
            )

        conf_uid, err = _resolve_conf_uid(body.get("conf_uid"))
        if err:
            return JSONResponse(status_code=400, content={"ok": False, "error": err})

        enabled = bool(body.get("enabled")) if "enabled" in body else None
        top_k = None
        if "top_k" in body:
            try:
                top_k = int(body.get("top_k"))
            except (TypeError, ValueError):
                return JSONResponse(
                    status_code=400,
                    content={"ok": False, "error": "'top_k' must be an integer."},
                )
            if top_k < 1 or top_k > 10:
                return JSONResponse(
                    status_code=400,
                    content={"ok": False, "error": "'top_k' must be between 1 and 10."},
                )

        try:
            await asyncio.to_thread(_write_fts_settings, enabled, top_k)
        except Exception as e:
            logger.error(f"memory fts write failed: {type(e).__name__}: {e}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write config file."},
            )

        logger.info(f"memory fts saved (enabled={enabled}, top_k={top_k})")
        # Echo the resulting effective values (read back from conf for honesty).
        eff_enabled, eff_top_k = _fts_from_conf()
        return JSONResponse(
            {
                "ok": True,
                "conf_uid": conf_uid,
                "fts_enabled": eff_enabled,
                "fts_top_k": eff_top_k,
                # FTS gating + retrieval read the running character_config, which is
                # baked at init; the new value fully applies after re-select / restart.
                "restart_required": True,
            }
        )

    @router.post("/api/memory/reindex")
    async def reindex(request: Request):
        """Rebuild this character's FTS5 full-history index from scratch."""
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

        conf_uid, err = _resolve_conf_uid(body.get("conf_uid"))
        if err:
            return JSONResponse(status_code=400, content={"ok": False, "error": err})

        try:
            indexed_count = await asyncio.to_thread(
                memory_fts.rebuild_index, conf_uid
            )
        except Exception as e:
            # memory_fts is fail-soft internally, but guard the endpoint too — never
            # leak a path/stack to the client.
            logger.error(f"memory reindex failed: {type(e).__name__}: {e}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not rebuild index."},
            )

        logger.info(f"fts reindex done (conf_uid={conf_uid}, n={indexed_count})")
        return JSONResponse(
            {"ok": True, "conf_uid": conf_uid, "indexed_count": indexed_count}
        )

    return router
