"""
Proactive topic-pool endpoints + in-app news auto-refresh.
==========================================================
Localhost-only REST endpoints that let a non-technical user control WHAT the
companion proactively talks about when the idle timer fires.

Background (confirmed in conversation_handler.py / news_topics.py):
- After idle, the frontend sends an ``ai-speak-signal`` WebSocket message.
- The backend loads ``prompts/utils/proactive_speak_prompt.txt`` FRESH every time
  (prompt_loader.load_util, no cache) and uses it as the per-trigger user_input.
- So overwriting that .txt takes effect on the NEXT proactive trigger with no restart.

Unified topics model (single list drives both modes):
  - ONE free-text ``topics`` list is the user's "主動話題" pool.
  - A single ``news.enabled`` boolean decides whether each topic is ALSO fetched as a
    Google-News query via scripts/news_topics.py (RSS, pure stdlib — it fetches news
    itself, so it needs NO web-search-capable LLM; works with any player LLM).
  - news OFF  -> compose persona + the topic list; the AI riffs from its own training
                 knowledge, no network fetch.
  - news ON   -> each topic is run as a Google-News query; the fetched headlines are
                 appended per topic. SAME list — only the fetch differs.

There is no fixed-category concept any more (the old manual_topics + news.categories
split is gone). A small SUGGESTIONS list is exposed for the frontend's quick-add chips
only — it is NEVER persisted and NEVER force-injected.

State lives in a small JSON file the server owns (NOT conf.yaml — avoids comment
churn and keeps user content separate). Composition reuses ONE helper
(``news_topics.compose_content``) shared by the CLI, the refresh endpoint, and the
periodic loop — so the persona-instruction line + "never write a broken file"
guarantee live in exactly one place.

Design notes:
- Reuses the localhost+proxy guard verbatim (``_is_local_request`` / ``_forbidden``).
- All writes atomic (temp + os.replace).
- The news fetch is blocking urllib, so it always runs via ``asyncio.to_thread``.
- An asyncio background task (started by the server lifespan) re-fetches every
  ``interval_hours`` when news is enabled. It is cancel-safe and swallows exceptions
  so a single fetch failure never kills the loop. NOT an OS cron.
"""

import os
import json
import asyncio
import datetime
import importlib.util
from typing import Any, Optional

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse
from loguru import logger

# REUSE the localhost+proxy guard — do not diverge.
from .llm_config_route import _is_local_request, _forbidden


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# State store. Kept under prompts/utils/ next to the prompt it composes.
STATE_PATH = os.path.join("prompts", "utils", "proactive_topics.json")

# Limits (validation caps so a bad/huge POST can't bloat the prompt or fan out into
# too many blocking RSS fetches when news is on).
MAX_TOPICS = 30
MAX_TOPIC_LEN = 200
MIN_INTERVAL_HOURS = 1
MAX_INTERVAL_HOURS = 24
DEFAULT_INTERVAL_HOURS = 6

# Quick-add SUGGESTION chips for the frontend only. NOT persisted, NOT force-injected
# into anyone's topic list — purely a convenience so a brand-new list isn't empty. The
# user can type any topic; these are just one-click starters.
SUGGESTIONS = ["科技", "AI", "動漫", "電玩", "國際", "娛樂", "財經", "體育"]


# --------------------------------------------------------------------------- #
# Lazy import of the shared fetch/compose logic from scripts/news_topics.py
# --------------------------------------------------------------------------- #
# scripts/ is not an installed package; the server runs from the project root, so we
# load the module by its file path once and cache it. This keeps ONE fetch+compose
# implementation shared by the CLI, the refresh endpoint, and the periodic loop.

_news_mod = None


def _get_news_module():
    global _news_mod
    if _news_mod is not None:
        return _news_mod
    # Resolve relative to this file: <root>/src/open_llm_vtuber/topics_route.py
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))  # up out of src/open_llm_vtuber
    candidates = [
        os.path.join(root, "scripts", "news_topics.py"),
        os.path.join(os.getcwd(), "scripts", "news_topics.py"),
    ]
    path = next((p for p in candidates if os.path.exists(p)), None)
    if path is None:
        raise FileNotFoundError("scripts/news_topics.py not found")
    spec = importlib.util.spec_from_file_location("news_topics", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _news_mod = mod
    return mod


# --------------------------------------------------------------------------- #
# State store (atomic JSON)
# --------------------------------------------------------------------------- #

def _default_state() -> dict:
    return {
        "topics": [],
        "news": {
            "enabled": False,
            "interval_hours": DEFAULT_INTERVAL_HOURS,
        },
        "last_news_refresh": None,
    }


def _load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return _default_state()
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_state()
    except Exception as e:
        logger.warning(f"proactive_topics.json unreadable, using defaults: {type(e).__name__}")
        return _default_state()
    # Merge onto defaults so missing keys are tolerated.
    state = _default_state()

    # ----------------------------------------------------------------------- #
    # MIGRATION from the old split model -> the unified single list.
    # Old files held manual_topics:[...] + news.categories:[...]. Merge BOTH into
    # the single `topics` list (manual first, then categories) so existing users
    # keep what they saved. The new `topics` key (if present) wins over the legacy
    # pair. Dedupe preserves first-seen order.
    # ----------------------------------------------------------------------- #
    raw_topics = data.get("topics")
    if isinstance(raw_topics, list):
        state["topics"] = _sanitize_topics(raw_topics)
    else:
        legacy: list = []
        if isinstance(data.get("manual_topics"), list):
            legacy.extend(str(t) for t in data["manual_topics"])
        old_news = data.get("news")
        if isinstance(old_news, dict) and isinstance(old_news.get("categories"), list):
            legacy.extend(str(c) for c in old_news["categories"])
        state["topics"] = _sanitize_topics(legacy)

    news = data.get("news")
    if isinstance(news, dict):
        if isinstance(news.get("enabled"), bool):
            state["news"]["enabled"] = news["enabled"]
        ih = news.get("interval_hours")
        if isinstance(ih, (int, float)):
            state["news"]["interval_hours"] = _clamp_interval(ih)
    if data.get("last_news_refresh"):
        state["last_news_refresh"] = str(data["last_news_refresh"])
    return state


def _write_state(state: dict) -> None:
    conf_dir = os.path.dirname(os.path.abspath(STATE_PATH)) or "."
    os.makedirs(conf_dir, exist_ok=True)
    tmp_path = os.path.join(conf_dir, ".proactive_topics.json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, STATE_PATH)


def _clamp_interval(v: Any) -> int:
    try:
        n = int(round(float(v)))
    except Exception:
        return DEFAULT_INTERVAL_HOURS
    return max(MIN_INTERVAL_HOURS, min(MAX_INTERVAL_HOURS, n))


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def _sanitize_topics(raw: Any) -> list:
    """Sanitize the single unified topics list.

    Each entry is trimmed; empties dropped; length capped at MAX_TOPIC_LEN and the
    overall count capped at MAX_TOPICS so the prompt + (news-on) RSS fan-out stays
    bounded. Order is preserved and duplicates removed.

    CRITICAL: an empty input returns [] — there is NO default injection. This is the
    whole point of the redesign: the old `or DEFAULT_CATEGORIES` fallback is what made
    the 4 defaults un-removable. Empty MUST stay empty.
    """
    if not isinstance(raw, list):
        return []
    seen = set()
    out = []
    for t in raw:
        if not isinstance(t, str):
            continue
        s = t.strip()
        if not s:
            continue
        s = s[:MAX_TOPIC_LEN]
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= MAX_TOPICS:
            break
    return out


# --------------------------------------------------------------------------- #
# Composition + fetch (shared via news_topics)
# --------------------------------------------------------------------------- #

def _fetch_blocks_for(topics: list, seen=None, new_titles=None):
    """Blocking fetch: run each topic as its own Google-News query. Returns (blocks, got_any).

    Each topic is resolved to a (label, query) pair:
    - a topic that happens to match a curated query-hint key -> the module's mapped
      query (e.g. "AI" -> "AI 人工智慧") for a better search.
    - any other free-text topic -> used directly as its own query, with label == query,
      so the user's term IS the Google News search.
    Order follows the user's list.

    Cross-run de-dup: ``seen`` (a persisted record of already-served headlines) is passed
    through so previously-served titles are excluded; ``new_titles`` (a list) collects the
    titles actually served this round so the caller can write them back to ``seen``.

    EMPTY -> fetches NOTHING (returns [], False). There is deliberately no fallback to
    the full curated set; an empty topic list with news on must not surprise-fetch
    defaults (see the redesign).
    """
    nt = _get_news_module()
    mapping = {pair[0]: pair[1] for pair in nt.CATEGORIES}
    chosen = []
    chosen_seen = set()
    for topic in topics:
        if not isinstance(topic, str):
            continue
        c = topic.strip()
        if not c or c in chosen_seen:
            continue
        chosen_seen.add(c)
        query = mapping.get(c, c)  # curated hint -> mapped query; else -> itself
        chosen.append((c, query))
    if not chosen:
        return [], False
    return nt.fetch_news_blocks(
        categories=chosen, per_cat=nt.PER_CAT, seen=seen, new_titles=new_titles
    )


def _compose_and_write(state: dict, *, news_blocks=None, got_any: bool = False) -> str:
    """Compose proactive_speak_prompt.txt from the unified topics list (+ optional news).

    The SAME topics list drives both modes; news_blocks is empty when news is off.
    Always keeps the persona-instruction line (news_topics.compose_content does that).
    Returns the composed content.
    """
    nt = _get_news_module()
    content = nt.compose_content(
        manual_topics=state.get("topics", []),
        news_blocks=news_blocks or [],
        got_any=got_any,
    )
    nt.write_prompt(content)
    return content


async def _refresh(state: dict) -> dict:
    """Recompose the prompt. If news enabled, fetch fresh news first (in a thread).

    Returns {composed, news_ok, news_count}. Never raises for a fetch failure — on
    failure it composes persona + topic list only (never a broken file).

    Cross-run de-dup: already-served headlines are loaded from seen_news.json and excluded;
    the titles actually served this round are written back. When EVERY topic comes back
    empty (all filtered as already-seen, or the fetch failed), got_any is False, the news
    block is omitted, and the persona instruction tells her to free-riff from her own
    knowledge / the topic list instead of repeating stale news — she never gets stuck.
    """
    nt = _get_news_module()
    news_cfg = state.get("news", {})
    news_blocks, got_any, news_count = [], False, 0
    new_titles: list = []
    if news_cfg.get("enabled"):
        try:
            seen = await asyncio.to_thread(nt.load_seen)
        except Exception as e:
            logger.warning(f"seen_news load failed, treating as empty: {type(e).__name__}: {e}")
            seen = {}
        try:
            news_blocks, got_any = await asyncio.to_thread(
                _fetch_blocks_for, state.get("topics", []), seen, new_titles
            )
            news_count = sum(b.count("\n- ") for b in news_blocks)
        except Exception as e:
            logger.warning(f"news fetch failed: {type(e).__name__}: {e}")
            news_blocks, got_any, new_titles = [], False, []
        # Persist only the headlines actually served this round; don't touch seen when
        # nothing new came out (all-filtered / fetch failed).
        if new_titles:
            try:
                await asyncio.to_thread(nt.save_seen, nt.mark_seen(seen, new_titles))
            except Exception as e:
                logger.warning(f"seen_news save failed: {type(e).__name__}: {e}")
    await asyncio.to_thread(_compose_and_write, state, news_blocks=news_blocks, got_any=got_any)
    return {"news_ok": got_any, "news_count": news_count}


# --------------------------------------------------------------------------- #
# In-app periodic refresh task (NOT OS cron)
# --------------------------------------------------------------------------- #

_refresh_task: Optional[asyncio.Task] = None


async def _news_refresh_loop():
    """Periodically re-fetch news + recompose the prompt when news is enabled.

    Cancel-safe + exception-swallowing: a fetch error logs + continues, never kills
    the loop. Sleeps interval_hours between cycles; when news is disabled it idles
    (re-checking each interval) so toggling on takes effect within one cycle.
    """
    logger.info("[topics] news auto-refresh loop started")
    # small initial delay so startup isn't blocked by a network call
    try:
        await asyncio.sleep(30)
    except asyncio.CancelledError:
        return
    while True:
        try:
            state = await asyncio.to_thread(_load_state)
            news_cfg = state.get("news", {})
            interval = _clamp_interval(news_cfg.get("interval_hours", DEFAULT_INTERVAL_HOURS))
            if news_cfg.get("enabled"):
                result = await _refresh(state)
                state["last_news_refresh"] = _now_iso()
                await asyncio.to_thread(_write_state, state)
                logger.info(
                    f"[topics] auto-refresh done (news_ok={result['news_ok']}, "
                    f"count={result['news_count']}), next in {interval}h"
                )
            else:
                interval = 1  # idle: re-check hourly so enabling takes effect soon
        except asyncio.CancelledError:
            logger.info("[topics] news auto-refresh loop cancelled")
            return
        except Exception as e:
            logger.warning(f"[topics] auto-refresh cycle error: {type(e).__name__}: {e}")
            interval = 1
        try:
            await asyncio.sleep(max(1, interval) * 3600)
        except asyncio.CancelledError:
            logger.info("[topics] news auto-refresh loop cancelled")
            return


def start_news_refresh_task() -> None:
    """Start the periodic task once (guard against double-start)."""
    global _refresh_task
    if _refresh_task is not None and not _refresh_task.done():
        return
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    _refresh_task = loop.create_task(_news_refresh_loop())


async def stop_news_refresh_task() -> None:
    """Cancel the periodic task on shutdown."""
    global _refresh_task
    if _refresh_task is not None:
        _refresh_task.cancel()
        try:
            await _refresh_task
        except (asyncio.CancelledError, Exception):
            pass
        _refresh_task = None


# --------------------------------------------------------------------------- #
# Route factory
# --------------------------------------------------------------------------- #

def init_topics_route() -> APIRouter:
    """REST endpoints for the proactive topic pool. Localhost-only.

    - GET  /api/proactive-topics         -> current topic list + news config + suggestions
    - POST /api/proactive-topics         -> save topic list + news config, recompose prompt
    - POST /api/proactive-topics/refresh -> 立即更新: fetch news + recompose prompt
    """
    router = APIRouter()

    @router.get("/api/proactive-topics")
    async def get_topics(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            state = await asyncio.to_thread(_load_state)
        except Exception as e:
            logger.error(f"proactive-topics read failed: {type(e).__name__}")
            return JSONResponse(status_code=500, content={"error": "could not read state"})
        return JSONResponse(
            {
                "topics": state["topics"],
                "news": state["news"],
                "last_news_refresh": state["last_news_refresh"],
                "suggestions": SUGGESTIONS,
            }
        )

    @router.post("/api/proactive-topics")
    async def save_topics(request: Request):
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

        state = await asyncio.to_thread(_load_state)
        if "topics" in body:
            state["topics"] = _sanitize_topics(body.get("topics"))
        news_in = body.get("news")
        if isinstance(news_in, dict):
            if "enabled" in news_in:
                state["news"]["enabled"] = bool(news_in.get("enabled"))
            if "interval_hours" in news_in:
                state["news"]["interval_hours"] = _clamp_interval(
                    news_in.get("interval_hours")
                )

        try:
            await asyncio.to_thread(_write_state, state)
        except Exception as e:
            logger.error(f"proactive-topics write failed: {type(e).__name__}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write state file."},
            )

        # Recompose the prompt from the saved topic list. Does NOT force a network
        # fetch here (that's what refresh-now is for); composing from the topic list
        # keeps persona + topics current immediately. When news is enabled the periodic
        # task / refresh-now is what re-fetches and appends fresh headlines.
        try:
            await asyncio.to_thread(
                _compose_and_write, state, news_blocks=[], got_any=False
            )
            composed = True
        except Exception as e:
            logger.error(f"prompt recompose failed: {type(e).__name__}")
            composed = False

        return JSONResponse(
            {
                "ok": True,
                "composed": composed,
                "topics": state["topics"],
                "news": state["news"],
                "last_news_refresh": state["last_news_refresh"],
            }
        )

    # Accept both the spec path (/refresh) and the frontend bundle path
    # (/refresh-now) so the built UI and CLI/tests line up.
    @router.post("/api/proactive-topics/refresh")
    @router.post("/api/proactive-topics/refresh-now")
    async def refresh_now(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        state = await asyncio.to_thread(_load_state)
        try:
            result = await _refresh(state)
        except Exception as e:
            logger.error(f"refresh-now failed: {type(e).__name__}: {e}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Refresh failed."},
            )
        if state.get("news", {}).get("enabled"):
            state["last_news_refresh"] = _now_iso()
            try:
                await asyncio.to_thread(_write_state, state)
            except Exception as e:
                logger.warning(f"could not persist last_news_refresh: {type(e).__name__}")
        return JSONResponse(
            {
                "ok": True,
                "news_enabled": bool(state.get("news", {}).get("enabled")),
                "news_ok": result["news_ok"],
                "news_count": result["news_count"],
                "last_news_refresh": state["last_news_refresh"],
            }
        )

    return router
