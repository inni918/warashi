"""
Opt-in full-history retrieval via SQLite FTS5 (trigram tokenizer).
==================================================================
A lightweight, INSTALL-FREE "deep recall" layer that augments — never replaces —
the always-on core memory (memory_core.py). Default OFF; when a character turns it
on, each user turn searches THIS character's entire past transcript for relevant
snippets and injects the top-K into the prompt (clearly labelled).

Design (mirrors memory_core.py house style):
- Pure stdlib ``sqlite3`` with FTS5 + the ``trigram`` tokenizer. No model, no
  embeddings, no extra deps. trigram handles Chinese (no whitespace word
  boundaries) by indexing 3-char windows — verified available in this venv.
- Per-character: one SQLite DB at ``chat_history/<conf_uid>/fts_index.db``, so
  characters never see each other's history (same separation as core_memory.md).
- Incremental: each transcript *.json is (re)indexed only when its mtime changes.
- Fail-soft EVERYWHERE: any error (missing DB, FTS5 syntax, corrupt file) is logged
  and treated as "no hit" / "off". This module must NEVER raise into the chat loop.

CRITICAL trigram constraint (verified): a MATCH query must be >= 3 characters or it
returns nothing. ``search`` guards short queries (returns []) and only builds terms
that are >= 3 chars.
"""

import os
import re
import json
import sqlite3
from typing import List, Optional, Tuple

from loguru import logger

from .chat_history_manager import _sanitize_path_component

# Per-snippet length cap (chars) to bound prompt token growth.
_SNIPPET_MAX = 200
# Label that prefixes the injected retrieval block (per spec).
RETRIEVAL_LABEL = "## 可能相關的過去對話"
# trigram tokenizer needs >= 3 chars to match anything.
_MIN_TERM = 3
# Hard cap on the number of OR-terms in one MATCH expression. Bounds SQL / token
# bloat when a long CJK query is exploded into sliding 3-char windows.
_MAX_OR_TERMS = 16
# CJK + kana + hangul. The SenseVoice ASR is zh-en-ja-ko-yue, so any of these
# scripts means "no whitespace word boundaries" -> use sliding-trigram OR.
_CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")


def _has_cjk(s: str) -> bool:
    """True if the string contains any CJK / kana / hangul character."""
    return bool(_CJK_RE.search(s or ""))


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

def _conf_dir(conf_uid: str) -> str:
    """chat_history/<sanitized conf_uid>/ — reuse the existing path-traversal guard."""
    safe = _sanitize_path_component(conf_uid)
    return os.path.join("chat_history", safe)


def _db_path(conf_uid: str) -> str:
    return os.path.join(_conf_dir(conf_uid), "fts_index.db")


def index_exists(conf_uid: str) -> bool:
    """True if a non-empty FTS index DB exists for this character (best-effort)."""
    try:
        p = _db_path(conf_uid)
        if not os.path.isfile(p):
            return False
        conn = sqlite3.connect(p)
        try:
            row = conn.execute("SELECT count(*) FROM snippets").fetchone()
            return bool(row and row[0] > 0)
        finally:
            conn.close()
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #

def _ensure_schema(conn: sqlite3.Connection) -> None:
    # Contentless-ish: store the snippet text directly (transcripts are small).
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS snippets "
        "USING fts5(text, role UNINDEXED, ts UNINDEXED, src UNINDEXED, "
        "tokenize='trigram')"
    )
    # Track which transcript files (+ mtime) are already indexed for incremental refresh.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS indexed_files("
        "path TEXT PRIMARY KEY, mtime REAL, n INTEGER)"
    )


def _open(conf_uid: str) -> sqlite3.Connection:
    """Open (creating the dir + schema) the per-character index DB."""
    d = _conf_dir(conf_uid)
    os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(_db_path(conf_uid))
    _ensure_schema(conn)
    return conn


# --------------------------------------------------------------------------- #
# Parsing transcripts -> snippet rows
# --------------------------------------------------------------------------- #

def _parse_transcript(path: str) -> List[Tuple[str, str, str]]:
    """Return [(text, role, ts), ...] for indexable human/ai messages in a transcript.

    Skips metadata + system entries and empty content (mirrors get_history's filter).
    """
    rows: List[Tuple[str, str, str]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"[fts] could not read transcript {path}: {e}")
        return rows
    if not isinstance(data, list):
        return rows
    for msg in data:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in ("human", "ai"):
            continue
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        ts = msg.get("timestamp")
        rows.append((content.strip(), role, str(ts) if ts is not None else ""))
    return rows


def _list_transcripts(conf_uid: str) -> List[str]:
    """All *.json transcripts for a character, EXCLUDING our own index file."""
    d = _conf_dir(conf_uid)
    out: List[str] = []
    try:
        for name in os.listdir(d):
            if name.endswith(".json"):
                out.append(os.path.join(d, name))
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"[fts] could not list transcripts for {conf_uid}: {e}")
    return out


# --------------------------------------------------------------------------- #
# Index build / refresh
# --------------------------------------------------------------------------- #

def ensure_index(conf_uid: str) -> int:
    """Incrementally (re)build the index. Returns total indexed snippet count.

    Cheap when nothing changed (just stats each file). For any file whose mtime
    differs from what's recorded, delete its old rows and re-insert. Fail-soft: any
    error -> log + return whatever count we can read (or 0).
    """
    try:
        conn = _open(conf_uid)
    except Exception as e:
        logger.warning(f"[fts] open index failed for {conf_uid}: {e}")
        return 0
    try:
        known = {}
        for path, mtime in conn.execute("SELECT path, mtime FROM indexed_files"):
            known[path] = mtime
        current_paths = set()
        for path in _list_transcripts(conf_uid):
            current_paths.add(path)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if known.get(path) == mtime:
                continue  # unchanged -> skip
            rows = _parse_transcript(path)
            conn.execute("DELETE FROM snippets WHERE src = ?", (path,))
            conn.executemany(
                "INSERT INTO snippets(text, role, ts, src) VALUES (?, ?, ?, ?)",
                [(t, r, ts, path) for (t, r, ts) in rows],
            )
            conn.execute(
                "INSERT INTO indexed_files(path, mtime, n) VALUES (?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, n=excluded.n",
                (path, mtime, len(rows)),
            )
        # Drop rows for transcripts that no longer exist (deleted histories).
        stale = [p for p in known if p not in current_paths]
        for path in stale:
            conn.execute("DELETE FROM snippets WHERE src = ?", (path,))
            conn.execute("DELETE FROM indexed_files WHERE path = ?", (path,))
        conn.commit()
        total = conn.execute("SELECT count(*) FROM snippets").fetchone()[0]
        return int(total)
    except Exception as e:
        logger.warning(f"[fts] ensure_index failed for {conf_uid}: {e}")
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def rebuild_index(conf_uid: str) -> int:
    """DROP + recreate the index from scratch (backs the 重建索引 button).

    Returns the indexed snippet count. Fail-soft -> 0 on error.
    """
    try:
        conn = _open(conf_uid)
        try:
            conn.execute("DROP TABLE IF EXISTS snippets")
            conn.execute("DROP TABLE IF EXISTS indexed_files")
            _ensure_schema(conn)
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[fts] rebuild drop failed for {conf_uid}: {e}")
        return 0
    return ensure_index(conf_uid)


# --------------------------------------------------------------------------- #
# Query building + search
# --------------------------------------------------------------------------- #

def _quote_phrase(s: str) -> str:
    """Double-quote a string as an FTS5 phrase, escaping embedded quotes (doubling)."""
    return '"' + s.replace('"', '""') + '"'


def _cjk_trigrams(chunk: str) -> List[str]:
    """Sliding 3-char windows (step 1) over a CJK chunk, e.g. '我吃蘋果' ->
    ['我吃蘋','吃蘋果']. Each window is exactly 3 chars (>= trigram minimum), so a
    keyword like 蘋果 embedded anywhere is captured by some window. Returns [] for
    chunks shorter than 3 chars (cannot form a window / trigram can't match anyway).
    """
    return [chunk[i : i + 3] for i in range(len(chunk) - 2)]


def _build_match_query(query: str) -> Optional[str]:
    """Turn raw user input into a safe FTS5 MATCH expression, or None if unusable.

    trigram matches substrings, so we OR together >= 3-char chunks of the input. Every
    term is wrapped in double quotes (FTS5 phrase) so punctuation / operator words
    (AND, OR, NOT, *, parentheses) can never trigger a syntax error. Returns None when
    nothing >= 3 chars survives (caller then treats it as no-hit).

    CJK note: a CJK query has no whitespace word boundaries, so the WHOLE string would
    otherwise become one phrase that only matches a contiguous run. To let an embedded
    keyword (e.g. 蘋果 inside "我中午吃了蘋果") match a differently-worded transcript,
    we ALSO OR in every sliding 3-char window of each CJK chunk. English / whitespace
    queries keep the original word-boundary behavior (no trigram explosion, which would
    over-match short words). Capped at _MAX_OR_TERMS and fully fail-soft.
    """
    cleaned = (query or "").strip()
    if len(cleaned) < _MIN_TERM:
        return None
    # Split on whitespace first; keep word-ish chunks, then ensure each is >= 3 chars.
    raw_chunks = re.split(r"\s+", cleaned)
    terms: List[str] = []
    seen = set()

    def _add(term_text: str) -> None:
        """Quote + dedupe (via seen) a candidate term, preserving first-seen order."""
        if term_text in seen:
            return
        seen.add(term_text)
        terms.append(_quote_phrase(term_text))

    # 1. Original word-ish chunks first (longer / fuller matches rank higher).
    has_word_chunk = False
    cjk_chunks: List[str] = []
    for chunk in raw_chunks:
        c = chunk.strip()
        if len(c) < _MIN_TERM:
            continue
        # Cap a single term's length so one huge paste doesn't make a giant phrase.
        c = c[:64]
        has_word_chunk = True
        _add(c)
        if _has_cjk(c):
            cjk_chunks.append(c)

    # 1b. No whitespace chunk survived (typical CJK): fall back to the whole cleaned
    #     string as the base chunk so contiguous matches still work + it seeds trigrams.
    if not has_word_chunk:
        c = cleaned[:64]
        _add(c)
        if _has_cjk(c):
            cjk_chunks.append(c)

    # 2. CJK sliding-trigram OR terms (fail-soft: any error -> skip, keep base terms).
    try:
        for c in cjk_chunks:
            for win in _cjk_trigrams(c):
                _add(win)
    except Exception as e:  # pragma: no cover - defensive only
        logger.warning(f"[fts] trigram expansion failed, using base terms: {e}")

    if not terms:
        return None
    # Cap total OR-terms to bound SQL / token bloat (base chunks kept first).
    return " OR ".join(terms[:_MAX_OR_TERMS])


def _format_snippet(text: str, role: str) -> str:
    who = "使用者" if role == "human" else "她"
    t = text.strip().replace("\n", " ")
    if len(t) > _SNIPPET_MAX:
        t = t[:_SNIPPET_MAX].rstrip() + "…"
    return f"「{who}：{t}」"


def search(conf_uid: str, query: str, k: int = 3) -> List[str]:
    """Return up to ``k`` labelled past-conversation snippets relevant to ``query``.

    Fully fail-soft: returns [] on a short query, no index, FTS5 error, or anything
    else. Never raises — the chat turn must proceed on core memory alone if this fails.
    """
    try:
        try:
            k = int(k)
        except (TypeError, ValueError):
            k = 3
        if k < 1:
            return []
        if k > 50:
            k = 50  # hard sanity cap regardless of conf
        if not isinstance(query, str):
            return []
        match = _build_match_query(query)
        if match is None:
            return []
        # Lazily make sure the index reflects the latest transcripts on disk.
        ensure_index(conf_uid)
        p = _db_path(conf_uid)
        if not os.path.isfile(p):
            return []
        conn = sqlite3.connect(p)
        try:
            cur = conn.execute(
                "SELECT text, role FROM snippets WHERE snippets MATCH ? "
                "ORDER BY rank LIMIT ?",
                (match, k),
            )
            rows = cur.fetchall()
        finally:
            conn.close()
        out: List[str] = []
        seen_text = set()
        for text, role in rows:
            if not text or not str(text).strip():
                continue
            key = str(text).strip()
            if key in seen_text:
                continue
            seen_text.add(key)
            out.append(_format_snippet(str(text), str(role)))
        return out
    except Exception as e:
        logger.warning(f"[fts] search failed for {conf_uid}: {e}")
        return []
