"""
Character Manager endpoints.
==========================================
Localhost-only REST endpoints that let a non-technical user create / edit /
switch / delete companion characters WITHOUT touching YAML by hand.

A "character" is an override YAML in ``characters/`` with a ``character_config``
block; switching deep-merges it over the base ``conf.yaml`` (unset fields inherit
base). The actual SWITCH is already wired over WebSocket (``switch-config``) — this
router only manages the files + scans skins/voices for the editor UI.

Design notes:
- The localhost+proxy guard is REUSED verbatim from llm_config_route
  (``_is_local_request`` / ``_forbidden``); never re-implement it divergently.
- New character files have no meaningful comments to preserve, so we serialize the
  whole ``character_config`` block via ruamel.yaml (allow_unicode) — NEVER sed/perl
  on Chinese display names. base conf.yaml is READ-ONLY here and never rewritten.
- Skins: we can only BUNDLE the 2 free Live2D samples; the scanner AUTO-DETECTS
  whatever is in ``live2d-models/`` and auto-registers any unregistered model into
  ``model_dict.json`` (minimal neutral emotionMap + the model's real idle motion
  group) so a switch to it can actually show the avatar (set_model raises KeyError
  otherwise, which init_live2d silently swallows).
- conf_uid drives ``chat_history/<conf_uid>/core_memory.md`` (independent memory),
  so conf_uid == slug == filename stem, and is immutable on edit (changing it would
  orphan the character's memory).
- Filenames are ASCII slugs (e.g. ``mili.yaml``) to sidestep URL/path-join edge
  cases; the Chinese display name lives in ``conf_name``.
"""

import os
import re
import json
import uuid
import glob
import socket
import asyncio
import subprocess
from typing import Optional

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, Response
from loguru import logger

# REUSE the localhost+proxy guard from the LLM wizard router — do not diverge.
from .llm_config_route import _is_local_request, _forbidden, _make_yaml
from .config_manager.utils import read_yaml


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

CONF_PATH = "conf.yaml"
CHARACTERS_DIR = "characters"
LIVE2D_DIR = "live2d-models"
MODEL_DICT_PATH = "model_dict.json"
AVATARS_DIR = "avatars"

# Slug must be ascii-safe so the filename + URL never hit encoding edge cases.
SLUG_RE = re.compile(r"^[a-z0-9_-]{1,40}$")

# Avatar uploads: only these image types are accepted (mirrors AvatarStaticFiles
# in server.py, which 403s anything else when serving). Maps an extension to keep
# the stored filename predictable + safe.
AVATAR_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"}
# A data-URL mime -> extension map for the JSON {data: dataURL} upload path.
AVATAR_MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}
# Cap the decoded avatar so a huge upload can never fill the disk. Generous enough
# for a normal portrait (the frontend already nudges users toward small images).
AVATAR_MAX_BYTES = 4 * 1024 * 1024  # 4 MB decoded

# Recursion cap for finding a *.model3.json inside a model folder (depth ~3).
MODEL3_GLOB_DEPTHS = ("*.model3.json", "*/*.model3.json", "*/*/*.model3.json")


# --------------------------------------------------------------------------- #
# Curated edge-tts voice list (robust / offline / instant)
# --------------------------------------------------------------------------- #
# ShortName is exactly what goes into tts_config.edge_tts.voice. zh-TW first
# because the UI default is Traditional Chinese (Taiwan).

CURATED_VOICES = [
    # zh-TW（台灣國語）
    {"value": "zh-TW-HsiaoChenNeural", "label": "曉臻（台灣國語・女）", "locale": "zh-TW", "gender": "Female"},
    {"value": "zh-TW-HsiaoYuNeural", "label": "曉雨（台灣國語・女）", "locale": "zh-TW", "gender": "Female"},
    {"value": "zh-TW-YunJheNeural", "label": "雲哲（台灣國語・男）", "locale": "zh-TW", "gender": "Male"},
    # en（English）
    {"value": "en-US-AvaNeural", "label": "Ava（English US・F）", "locale": "en-US", "gender": "Female"},
    {"value": "en-US-AndrewNeural", "label": "Andrew（English US・M）", "locale": "en-US", "gender": "Male"},
    {"value": "en-GB-SoniaNeural", "label": "Sonia（English UK・F）", "locale": "en-GB", "gender": "Female"},
    {"value": "en-US-AshleyNeural", "label": "Ashley（English US・F）", "locale": "en-US", "gender": "Female"},
    # ja（日本語）
    {"value": "ja-JP-NanamiNeural", "label": "Nanami（日本語・女）", "locale": "ja-JP", "gender": "Female"},
    {"value": "ja-JP-KeitaNeural", "label": "Keita（日本語・男）", "locale": "ja-JP", "gender": "Male"},
]

LIST_VOICES_TIMEOUT = 6.0  # seconds, for the optional ?full=1 live edge-tts call

# Voice-sample (試聽) preview ---------------------------------------------------
# Synthesizing one short line should be quick; cap it so a region-block / slow
# network can never hang the settings drawer.
VOICE_SAMPLE_TIMEOUT = 12.0  # seconds
# A voice ShortName is ascii letters/digits/hyphens (e.g. "zh-TW-HsiaoChenNeural").
VOICE_SHORTNAME_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
# Short, locale-appropriate preview line keyed by the voice's locale prefix.
VOICE_SAMPLE_TEXTS = {
    "zh-TW": "你好，很高興認識你。",
    "zh-CN": "你好，很高兴认识你。",
    "ja": "こんにちは、はじめまして。",
    "en": "Hi, nice to meet you.",
}
VOICE_SAMPLE_DEFAULT_TEXT = "Hi, nice to meet you."
VOICE_SAMPLE_MAX_TEXT = 120  # cap any caller-supplied text length


# --------------------------------------------------------------------------- #
# Slug helpers
# --------------------------------------------------------------------------- #

def _slugify(raw: str) -> str:
    """Reduce a string to [a-z0-9_-]; spaces -> '_'; drop everything else.

    Returns '' when nothing ascii-usable remains (e.g. an all-Chinese name) —
    the caller then falls back to a generated id.
    """
    if not raw:
        return ""
    s = str(raw).strip().lower()
    s = s.replace(" ", "_")
    s = re.sub(r"[^a-z0-9_-]", "", s)
    s = s.strip("_-")
    return s[:40]


def _derive_slug(requested_slug: Optional[str], conf_name: str) -> str:
    """Pick a valid ascii slug from the client slug, else the name, else a uuid."""
    for candidate in (requested_slug, conf_name):
        s = _slugify(candidate or "")
        if s and SLUG_RE.match(s):
            return s
    return "char_" + uuid.uuid4().hex[:8]


def _existing_conf_uids(exclude_filename: Optional[str] = None) -> set:
    """Collect conf_uid values already in use across base + every override file."""
    uids = set()
    try:
        base = read_yaml(CONF_PATH) or {}
        bu = base.get("character_config", {}).get("conf_uid")
        if bu:
            uids.add(str(bu))
    except Exception:
        pass
    for path in _list_character_files():
        if exclude_filename and os.path.basename(path) == exclude_filename:
            continue
        try:
            data = read_yaml(path) or {}
            u = data.get("character_config", {}).get("conf_uid")
            if u:
                uids.add(str(u))
        except Exception:
            # Tolerate a single hand-broken file rather than failing the whole op.
            continue
    return uids


def _unique_slug(slug: str, taken_uids: set) -> str:
    """Ensure slug doesn't collide with an existing file OR conf_uid; suffix if so."""
    def _conflict(s: str) -> bool:
        return os.path.exists(os.path.join(CHARACTERS_DIR, f"{s}.yaml")) or s in taken_uids

    if not _conflict(slug):
        return slug
    for i in range(2, 1000):
        cand = f"{slug}_{i}"[:40]
        if not _conflict(cand):
            return cand
    # Extremely unlikely; fall back to a guaranteed-unique id.
    return "char_" + uuid.uuid4().hex[:8]


# --------------------------------------------------------------------------- #
# Path-guard for character files (mirror handle_config_switch's check)
# --------------------------------------------------------------------------- #

def _safe_character_path(filename: str) -> Optional[str]:
    """Resolve ``filename`` under characters/ and confirm it stays inside.

    Returns the normalized path, or None if the path escapes the directory or the
    name is not a bare .yaml basename. Never permits ``conf.yaml`` here.
    """
    if not filename or filename == CONF_PATH:
        return None
    # Reject anything with path separators — must be a bare basename.
    if os.path.basename(filename) != filename:
        return None
    if not filename.endswith(".yaml"):
        return None
    path = os.path.normpath(os.path.join(CHARACTERS_DIR, filename))
    # normpath could still escape via '..'; verify the prefix.
    base = os.path.normpath(CHARACTERS_DIR)
    if not (path == base or path.startswith(base + os.sep)):
        return None
    return path


def _list_character_files() -> list:
    """Absolute-free list of characters/*.yaml (top-level only, mirrors scan)."""
    files = []
    if not os.path.isdir(CHARACTERS_DIR):
        return files
    for root, _, names in os.walk(CHARACTERS_DIR):
        for name in names:
            if name.endswith(".yaml"):
                files.append(os.path.join(root, name))
    return files


# --------------------------------------------------------------------------- #
# Skin scan + auto-register
# --------------------------------------------------------------------------- #

def _find_model3(model_dir: str) -> Optional[str]:
    """Find the first *.model3.json inside a model folder (depth-capped)."""
    for pattern in MODEL3_GLOB_DEPTHS:
        matches = sorted(glob.glob(os.path.join(model_dir, pattern)))
        if matches:
            return matches[0]
    return None


def _detect_idle_group(model3_path: str) -> str:
    """Read FileReferences.Motions and pick the idle group ('Idle' preferred)."""
    try:
        with open(model3_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        motions = data.get("FileReferences", {}).get("Motions", {})
        if isinstance(motions, dict):
            if "Idle" in motions:
                return "Idle"
            for key in motions.keys():
                if key:  # first non-empty key
                    return key
    except Exception as e:
        logger.debug(f"idle-group detect failed for {model3_path}: {type(e).__name__}")
    # Frontend tolerates a missing group; 'Idle' is the safe default.
    return "Idle"


def _load_model_dict() -> list:
    if not os.path.exists(MODEL_DICT_PATH):
        return []
    try:
        with open(MODEL_DICT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"model_dict.json read failed: {type(e).__name__}")
        return []


def _write_model_dict_atomic(entries: list) -> None:
    """Atomic write of model_dict.json (temp + os.replace), UTF-8, preserve Chinese."""
    conf_dir = os.path.dirname(os.path.abspath(MODEL_DICT_PATH)) or "."
    tmp_path = os.path.join(conf_dir, ".model_dict.json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=4, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp_path, MODEL_DICT_PATH)


# Filenames a player can drop into their model folder to give it a picker preview
# (checked in order; <name>.png is also tried). No rendering needed — the bundled
# skins ship their own /thumbnails/<name>.png, custom skins use this convention.
_THUMB_NAMES = (
    "thumbnail.png", "thumbnail.jpg", "thumbnail.jpeg", "thumbnail.webp",
    "preview.png", "preview.jpg", "icon.png",
)


def _find_skin_thumbnail(folder: str, name: str) -> Optional[str]:
    """Web URL for a player-supplied thumbnail inside the model folder, or None.
    Lets a user give their own Live2D model a picker preview by dropping a
    thumbnail.png next to the model3.json."""
    for fn in (*_THUMB_NAMES, f"{name}.png", f"{name}.jpg"):
        if os.path.isfile(os.path.join(folder, fn)):
            return f"/{LIVE2D_DIR}/{name}/{fn}"
    return None


def scan_and_register_skins() -> dict:
    """Scan live2d-models/, auto-register any unregistered valid model, return list.

    Returns ``{"skins": [{"name","registered","thumbnail"}...], "newly_registered": [...]}``.
    A model is VALID iff its top-level folder contains a *.model3.json (recursive,
    depth-capped). The folder name IS the value used in live2d_model_name AND the
    model_dict ``name``. Idempotent: only writes model_dict.json when something is
    missing.
    """
    model_dict = _load_model_dict()
    registered_names = {m.get("name") for m in model_dict if isinstance(m, dict)}

    newly_registered = []
    found_skins = []  # preserve discovery order, dedupe by name
    thumb_by_name: dict = {}  # name -> player-supplied thumbnail URL (or None)

    if os.path.isdir(LIVE2D_DIR):
        for entry in sorted(os.listdir(LIVE2D_DIR)):
            folder = os.path.join(LIVE2D_DIR, entry)
            if not os.path.isdir(folder):
                continue
            model3 = _find_model3(folder)
            if not model3:
                continue  # not a valid Live2D model folder
            name = entry  # top-level folder name
            found_skins.append(name)
            thumb_by_name[name] = _find_skin_thumbnail(folder, name)

            if name not in registered_names:
                # Build the web-served URL relative to LIVE2D_DIR.
                rel = os.path.relpath(model3, LIVE2D_DIR).replace(os.sep, "/")
                idle_group = _detect_idle_group(model3)
                entry_obj = {
                    "name": name,
                    "description": "自動偵測並註冊的 Live2D 模型",
                    "url": f"/{LIVE2D_DIR}/{rel}",
                    "kScale": 0.5,
                    "initialXshift": 0,
                    "initialYshift": 0,
                    "idleMotionGroupName": idle_group,
                    "emotionMap": {"neutral": 0},  # MUST be non-empty (set_model KeyErrors otherwise)
                    "tapMotions": {},
                }
                model_dict.append(entry_obj)
                registered_names.add(name)
                newly_registered.append(name)

    if newly_registered:
        _write_model_dict_atomic(model_dict)
        logger.info(f"Auto-registered Live2D skins: {newly_registered}")

    skins = [
        {"name": n, "registered": True, "thumbnail": thumb_by_name.get(n)}
        for n in dict.fromkeys(found_skins)
    ]
    return {"skins": skins, "newly_registered": newly_registered}


# --------------------------------------------------------------------------- #
# Character read / write
# --------------------------------------------------------------------------- #

def _read_character_fields(path: str, *, is_base: bool) -> Optional[dict]:
    """Read one config file -> editable-field dict, or None if unreadable."""
    try:
        data = read_yaml(path) or {}
    except Exception as e:
        logger.warning(f"skip unreadable character file {path}: {type(e).__name__}")
        return None
    cc = data.get("character_config", {}) or {}
    voice = None
    try:
        voice = cc.get("tts_config", {}).get("edge_tts", {}).get("voice")
    except AttributeError:
        voice = None
    filename = os.path.basename(path)
    slug = None if is_base else (filename[:-5] if filename.endswith(".yaml") else filename)
    return {
        "filename": filename,
        "slug": slug,
        "is_base": is_base,
        "conf_name": cc.get("conf_name"),
        "character_name": cc.get("character_name"),
        "avatar": cc.get("avatar"),
        "conf_uid": cc.get("conf_uid"),
        "live2d_model_name": cc.get("live2d_model_name"),
        "persona_prompt": cc.get("persona_prompt"),
        "voice": voice,
    }


def _build_character_config(
    *,
    conf_name: str,
    conf_uid: str,
    persona_prompt: str,
    live2d_model_name: str,
    voice: Optional[str],
    character_name: Optional[str],
    avatar: Optional[str],
) -> dict:
    """Assemble the minimal character_config dict the manager owns.

    Only these fields are written; everything else (agent/llm/asr/vad) inherits
    base via deep_merge on switch. tts_config is OMITTED when voice is unset so the
    character re-inherits the base voice.
    """
    cc: dict = {
        "conf_name": conf_name,
        "conf_uid": conf_uid,
        "live2d_model_name": live2d_model_name,
        "persona_prompt": persona_prompt,
    }
    # Always set a display name so the chat bubble / group name shows THIS
    # character, not the base character it deep-merges from. The UI doesn't always
    # send an explicit character_name; fall back to conf_name so a created
    # character never inherits the base's name (e.g. a new "Hiyori" showing 紅莉栖).
    cc["character_name"] = character_name or conf_name
    if avatar:
        cc["avatar"] = avatar
    if voice:
        cc["tts_config"] = {
            "tts_model": "edge_tts",
            "edge_tts": {"voice": voice},
        }
    return cc


def _write_character_yaml(path: str, character_config: dict) -> None:
    """Serialize {character_config: ...} to an alt file atomically (UTF-8, Unicode).

    These alt files have no comments worth preserving, so a plain ruamel dump is
    fine. allow_unicode keeps Chinese conf_name readable; multi-line persona keeps
    block style. Atomic temp + os.replace.
    """
    yaml = _make_yaml()
    yaml.allow_unicode = True

    # Use a literal block scalar for the (typically multi-line) persona so it stays
    # human-editable instead of a folded one-liner.
    from ruamel.yaml.scalarstring import LiteralScalarString

    cc = dict(character_config)
    persona = cc.get("persona_prompt")
    if isinstance(persona, str):
        # ensure trailing newline so ruamel emits a clean '|' block
        cc["persona_prompt"] = LiteralScalarString(
            persona if persona.endswith("\n") else persona + "\n"
        )

    payload = {"character_config": cc}

    conf_dir = os.path.dirname(os.path.abspath(path)) or "."
    tmp_path = os.path.join(conf_dir, "." + os.path.basename(path) + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.dump(payload, f)
    os.replace(tmp_path, path)


# --------------------------------------------------------------------------- #
# Body parsing (tolerate both spec field names)
# --------------------------------------------------------------------------- #

def _extract_body_fields(body: dict) -> dict:
    """Accept either {conf_name,persona_prompt,live2d_model_name,voice,slug}
    or the shorthand {name,persona,skin,voice,file}. Returns normalized dict."""
    conf_name = body.get("conf_name") or body.get("name")
    persona = body.get("persona_prompt")
    if persona is None:
        persona = body.get("persona")
    skin = body.get("live2d_model_name") or body.get("skin")
    voice = body.get("voice")
    slug = body.get("slug")
    character_name = body.get("character_name")
    avatar = body.get("avatar")
    return {
        "conf_name": (conf_name or "").strip() if isinstance(conf_name, str) else conf_name,
        "persona_prompt": persona,
        "live2d_model_name": (skin or "").strip() if isinstance(skin, str) else skin,
        "voice": (voice.strip() if isinstance(voice, str) else voice),
        "slug": slug,
        "character_name": character_name,
        "avatar": (avatar.strip() if isinstance(avatar, str) else avatar),
    }


def _bad_request(msg: str) -> JSONResponse:
    return JSONResponse(status_code=400, content={"ok": False, "error": msg})


# --------------------------------------------------------------------------- #
# Avatar upload helpers
# --------------------------------------------------------------------------- #

def _safe_avatar_filename(conf_uid: Optional[str], ext: str) -> str:
    """Build a path-safe avatar filename: <slug-or-random><ext>.

    The base is the slugified conf_uid when usable (so re-uploading for the same
    character overwrites instead of littering), else a random hex. ``ext`` is one
    of AVATAR_ALLOWED_EXTS and already includes the leading dot.
    """
    base = _slugify(conf_uid or "")
    if not base or not SLUG_RE.match(base):
        base = "char_" + uuid.uuid4().hex[:8]
    return f"{base}{ext}"


def _decode_data_url(data: str) -> Optional[tuple]:
    """Decode a ``data:<mime>;base64,<payload>`` URL -> (raw_bytes, ext) or None.

    Accepts only the image mimes in AVATAR_MIME_EXT. Tolerates a bare base64
    payload only when paired with a known extension elsewhere (not here) — a plain
    data-URL must carry its mime so we can pick a safe extension.
    """
    import base64

    if not isinstance(data, str) or not data.startswith("data:"):
        return None
    try:
        header, payload = data.split(",", 1)
    except ValueError:
        return None
    # header looks like "data:image/png;base64"
    meta = header[len("data:"):]
    mime = meta.split(";", 1)[0].strip().lower()
    ext = AVATAR_MIME_EXT.get(mime)
    if ext is None:
        return None
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception:
        return None
    if not raw or len(raw) > AVATAR_MAX_BYTES:
        return None
    return raw, ext


def _write_avatar_atomic(filename: str, raw: bytes) -> None:
    """Write avatar bytes into AVATARS_DIR atomically (temp + os.replace)."""
    os.makedirs(AVATARS_DIR, exist_ok=True)
    dest = os.path.join(AVATARS_DIR, filename)
    tmp_path = os.path.join(AVATARS_DIR, "." + filename + ".tmp")
    with open(tmp_path, "wb") as f:
        f.write(raw)
    os.replace(tmp_path, dest)


# --------------------------------------------------------------------------- #
# Network info (for the "open on another device" QR helper)
# --------------------------------------------------------------------------- #

def _is_cgnat(ip: str) -> bool:
    """True for Tailscale's 100.64.0.0/10 range (100.64.x – 100.127.x)."""
    if not ip or not ip.startswith("100."):
        return False
    try:
        second = int(ip.split(".")[1])
        return 64 <= second <= 127
    except (ValueError, IndexError):
        return False


def _lan_ip() -> Optional[str]:
    """Best-effort primary LAN IPv4 — the address other devices on the same
    network would use. Standard UDP-connect trick: no packet is sent, it just
    makes the OS pick the outbound interface."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        return ip if ip and not ip.startswith("127.") else None
    except Exception:
        return None
    finally:
        s.close()


def _tailscale_ip() -> Optional[str]:
    """Best-effort Tailscale IPv4 (100.64.0.0/10). Tries the `tailscale` CLI in
    its usual locations, then scans local addresses for the CGNAT range."""
    for exe in (
        "tailscale",
        "/usr/local/bin/tailscale",
        "/opt/homebrew/bin/tailscale",
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    ):
        try:
            out = subprocess.run(
                [exe, "ip", "-4"], capture_output=True, text=True, timeout=3
            )
            lines = (out.stdout or "").strip().splitlines()
            ip = lines[0].strip() if lines else ""
            if _is_cgnat(ip):
                return ip
        except Exception:
            continue
    try:
        for res in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = res[4][0]
            if _is_cgnat(ip):
                return ip
    except Exception:
        pass
    return None


def _tailscale_serve_https_url(port: Optional[int]) -> Optional[str]:
    """If Tailscale Serve proxies HTTPS to our port, return that https:// URL —
    the mic-capable one. Matches the serve handler whose proxy target port equals
    our server port, so we never hand back a URL pointing at a different app."""
    if not port:
        return None
    for exe in (
        "tailscale",
        "/usr/local/bin/tailscale",
        "/opt/homebrew/bin/tailscale",
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    ):
        try:
            out = subprocess.run(
                [exe, "serve", "status", "--json"],
                capture_output=True, text=True, timeout=3,
            )
            data = json.loads(out.stdout or "{}")
            web = data.get("Web") or {}
            for host, cfg in web.items():
                for _path, h in (cfg.get("Handlers") or {}).items():
                    proxy = (h.get("Proxy") or "").rstrip("/")
                    if proxy.endswith(f":{port}"):
                        return f"https://{host}"
            return None  # tailscale ran but nothing maps to our port
        except Exception:
            continue
    return None


def _server_bound_localhost_only() -> bool:
    """True if the server listens only on loopback (conf system_config.host is
    localhost/127.0.0.1), so the LAN / Tailscale-IP URLs are NOT reachable from
    other devices. The UI uses this to guide the user instead of showing dead
    URLs. (Tailscale Serve still works in this mode — it proxies from loopback.)"""
    try:
        conf = read_yaml(CONF_PATH) or {}
        host = str((conf.get("system_config") or {}).get("host", "")).strip()
        return host in ("localhost", "127.0.0.1", "::1")
    except Exception:
        return False


def _collect_network_urls(request: Request) -> dict:
    """Reachable URLs other devices can use to open this companion: the LAN URL
    (same Wi-Fi), the Tailscale URL (anywhere), and — if Tailscale Serve is
    proxying HTTPS to this port — the secure HTTPS URL the microphone needs."""
    scheme = request.url.scheme or "http"
    port = request.url.port
    default_port = 443 if scheme == "https" else 80

    def make_url(ip: str) -> str:
        if port and port != default_port:
            return f"{scheme}://{ip}:{port}"
        return f"{scheme}://{ip}"

    urls = []
    lan = _lan_ip()
    if lan:
        urls.append({"type": "lan", "ip": lan, "url": make_url(lan)})
    ts = _tailscale_ip()
    if ts:
        urls.append({"type": "tailscale", "ip": ts, "url": make_url(ts)})

    https_url = _tailscale_serve_https_url(port) if scheme != "https" else None

    return {
        "urls": urls,
        "port": port,
        "scheme": scheme,
        # The secure URL the microphone needs, auto-detected from Tailscale Serve
        # (null when Serve isn't proxying HTTPS to this port).
        "https_url": https_url,
        # True when the server only listens on loopback — the LAN/Tailscale-IP
        # URLs above won't connect, so the UI shows setup guidance instead.
        "localhost_only": _server_bound_localhost_only(),
        # Microphone capture needs a secure context (HTTPS) on a remote host;
        # plain-IP http works for text but not the mic. Tailscale Serve = HTTPS.
        "mic_needs_https": scheme != "https",
    }


# --------------------------------------------------------------------------- #
# Route factory
# --------------------------------------------------------------------------- #

def init_character_route() -> APIRouter:
    """REST endpoints for the in-app Character Manager. Localhost-only.

    - GET    /api/characters          -> list with editable fields
    - GET    /api/live2d-skins        -> scan + auto-register + list
    - GET    /api/voices              -> curated edge-tts voices (?full=1 -> live)
    - GET    /api/voice-sample        -> synth a short preview of a voice (試聽)
    - POST   /api/characters          -> create a new override YAML
    - POST   /api/character/avatar    -> upload an AI avatar image, return filename
    - PUT    /api/characters/{file}   -> update an existing override YAML
    - DELETE /api/characters/{file}   -> delete an override YAML
    """
    router = APIRouter()

    # ------------------------------------------------------------------ #
    @router.get("/api/characters")
    async def list_characters(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        characters = []
        # base conf.yaml first
        base = _read_character_fields(CONF_PATH, is_base=True)
        if base is not None:
            characters.append(base)
        # then every override file
        for path in sorted(_list_character_files()):
            fields = _read_character_fields(path, is_base=False)
            if fields is not None:
                characters.append(fields)
        return JSONResponse({"characters": characters})

    # ------------------------------------------------------------------ #
    @router.get("/api/live2d-skins")
    async def list_skins(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            result = await asyncio.to_thread(scan_and_register_skins)
        except Exception as e:
            logger.error(f"skin scan failed: {type(e).__name__}")
            return JSONResponse(
                status_code=500, content={"error": "skin scan failed"}
            )
        return JSONResponse(result)

    # ------------------------------------------------------------------ #
    @router.get("/api/network-info")
    async def network_info(request: Request):
        # Deliberately NOT localhost-gated: a device that already reached this
        # server may want the other reachable URLs (e.g. to hand to a tablet).
        # Only non-secret LAN/Tailscale addresses + the port are returned.
        info = await asyncio.to_thread(_collect_network_urls, request)
        return JSONResponse(info)

    # ------------------------------------------------------------------ #
    @router.get("/api/voices")
    async def list_voices(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        full = request.query_params.get("full")
        if full in ("1", "true", "yes"):
            voices = await _live_edge_voices()
            if voices is not None:
                return JSONResponse({"voices": voices, "source": "edge_tts"})
            # fall through to curated on any failure/timeout
        return JSONResponse({"voices": CURATED_VOICES, "source": "curated"})

    # ------------------------------------------------------------------ #
    @router.get("/api/voice-sample")
    async def voice_sample(request: Request):
        """Synthesize a short preview of a voice (試聽). Returns audio/mpeg bytes.

        Localhost-only (reused guard). Validates the voice ShortName charset to
        avoid arbitrary input; returns 502 on edge-tts failure/region-block so a
        blocked network surfaces a clean error instead of hanging.
        """
        if not _is_local_request(request):
            return _forbidden()
        voice = (request.query_params.get("voice") or "").strip()
        if not voice or not VOICE_SHORTNAME_RE.match(voice):
            return _bad_request("Invalid or missing voice.")
        text = (request.query_params.get("text") or "").strip()
        if not text:
            text = _sample_text_for_voice(voice)
        else:
            text = text[:VOICE_SAMPLE_MAX_TEXT]
        audio = await _synth_voice_sample(voice, text)
        if not audio:
            return JSONResponse(
                status_code=502,
                content={
                    "ok": False,
                    "error": "Could not synthesize the voice sample "
                    "(edge-tts may be blocked or slow).",
                },
            )
        return Response(
            content=audio,
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )

    # ------------------------------------------------------------------ #
    @router.post("/api/characters")
    async def create_character(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            body = await request.json()
        except Exception:
            return _bad_request("Invalid JSON body.")
        if not isinstance(body, dict):
            return _bad_request("Invalid JSON body.")

        fields = _extract_body_fields(body)
        conf_name = fields["conf_name"]
        persona = fields["persona_prompt"]
        skin = fields["live2d_model_name"]
        voice = fields["voice"] or None

        if not conf_name:
            return _bad_request("Missing display name (conf_name).")
        if not persona or not str(persona).strip():
            return _bad_request("Missing persona_prompt.")
        if not skin:
            return _bad_request("Missing live2d_model_name (skin).")

        # Ensure the chosen skin is scanned + registered before validating it.
        try:
            await asyncio.to_thread(scan_and_register_skins)
        except Exception as e:
            logger.warning(f"pre-create skin scan failed: {type(e).__name__}")
        registered = {m.get("name") for m in _load_model_dict()}
        if skin not in registered:
            return _bad_request(
                f"Skin '{skin}' is not a registered Live2D model. "
                "Drop it into live2d-models/ then rescan."
            )

        taken_uids = _existing_conf_uids()
        slug = _derive_slug(fields["slug"], conf_name)
        # If the CLIENT supplied an explicit (valid) slug, honor it exactly and
        # 409 on collision so the UI can prompt for a different one. Only a
        # SERVER-derived slug (e.g. from an all-Chinese name) is auto-suffixed so
        # the user is never blocked by an implicit-name clash.
        client_slug = _slugify(fields["slug"] or "")
        client_supplied = bool(client_slug) and SLUG_RE.match(client_slug) is not None
        if not client_supplied:
            slug = _unique_slug(slug, taken_uids)
        filename = f"{slug}.yaml"
        path = _safe_character_path(filename)
        if path is None:
            return _bad_request("Could not derive a safe filename.")
        if os.path.exists(path) or slug in taken_uids:
            return JSONResponse(
                status_code=409,
                content={"ok": False, "error": f"{filename} already exists."},
            )

        cc = _build_character_config(
            conf_name=conf_name,
            conf_uid=slug,
            persona_prompt=str(persona),
            live2d_model_name=skin,
            voice=voice,
            character_name=fields["character_name"],
            avatar=fields["avatar"] or None,
        )
        try:
            await asyncio.to_thread(_write_character_yaml, path, cc)
        except Exception as e:
            logger.error(f"character write failed (slug={slug}): {type(e).__name__}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write character file."},
            )

        logger.info(f"character created: slug={slug} file={filename}")
        return JSONResponse(
            {
                "ok": True,
                "filename": filename,
                "conf_uid": slug,
                "conf_name": conf_name,
                "restart_required": False,
            }
        )

    # ------------------------------------------------------------------ #
    @router.post("/api/character/avatar")
    async def upload_avatar(request: Request):
        """Persist an uploaded AI-character avatar image; return its filename.

        Localhost-only (reused guard). Accepts either:
          - JSON  {"data": "data:image/png;base64,...", "conf_uid": "<slug>"}
          - multipart/form-data with a ``file`` field (+ optional ``conf_uid``)

        The image is saved under ``avatars/`` with a path-safe name (conf_uid slug
        or random hex + the real extension). The returned {filename} is what the
        client writes into the character's ``avatar`` field; the chat UI then serves
        it from ``/avatars/<filename>``. This is server-side persistence on purpose:
        chat history is loaded from the backend, so AI avatars must survive there
        (NOT only in localStorage like the user's own avatar).
        """
        if not _is_local_request(request):
            return _forbidden()

        raw: Optional[bytes] = None
        ext: Optional[str] = None
        conf_uid: Optional[str] = None

        content_type = (request.headers.get("content-type") or "").lower()
        if content_type.startswith("multipart/form-data"):
            try:
                form = await request.form()
            except Exception:
                return _bad_request("Invalid multipart body.")
            upload = form.get("file")
            conf_uid = form.get("conf_uid") if isinstance(form.get("conf_uid"), str) else None
            if upload is None or not hasattr(upload, "read"):
                return _bad_request("Missing 'file' field.")
            # Pick the extension from the uploaded filename, validated against the allowlist.
            up_name = getattr(upload, "filename", "") or ""
            up_ext = os.path.splitext(up_name)[1].lower()
            if up_ext not in AVATAR_ALLOWED_EXTS:
                return _bad_request("Unsupported image type.")
            ext = up_ext
            try:
                raw = await upload.read()
            except Exception:
                return _bad_request("Could not read the uploaded file.")
            if not raw or len(raw) > AVATAR_MAX_BYTES:
                return _bad_request("Image is empty or too large (max 4 MB).")
        else:
            try:
                body = await request.json()
            except Exception:
                return _bad_request("Invalid JSON body.")
            if not isinstance(body, dict):
                return _bad_request("Invalid JSON body.")
            conf_uid = body.get("conf_uid") if isinstance(body.get("conf_uid"), str) else None
            decoded = _decode_data_url(body.get("data") or "")
            if decoded is None:
                return _bad_request(
                    "Invalid image data (expect a data:image/...;base64 URL "
                    "under 4 MB)."
                )
            raw, ext = decoded

        filename = _safe_avatar_filename(conf_uid, ext)
        # _safe_avatar_filename never produces separators, but double-check the
        # final name can't escape AVATARS_DIR.
        if os.path.basename(filename) != filename:
            return _bad_request("Could not derive a safe filename.")
        try:
            await asyncio.to_thread(_write_avatar_atomic, filename, raw)
        except Exception as e:
            logger.error(f"avatar write failed: {type(e).__name__}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not save the avatar."},
            )

        logger.info(f"avatar uploaded: {filename} ({len(raw)} bytes)")
        return JSONResponse({"ok": True, "filename": filename})

    # ------------------------------------------------------------------ #
    @router.put("/api/characters/{filename}")
    async def update_character(filename: str, request: Request):
        if not _is_local_request(request):
            return _forbidden()
        if filename == CONF_PATH:
            return _bad_request("Cannot edit the base character (conf.yaml).")
        path = _safe_character_path(filename)
        if path is None:
            return _bad_request("Invalid character filename.")
        if not os.path.exists(path):
            return JSONResponse(
                status_code=404, content={"ok": False, "error": "Character not found."}
            )

        try:
            body = await request.json()
        except Exception:
            return _bad_request("Invalid JSON body.")
        if not isinstance(body, dict):
            return _bad_request("Invalid JSON body.")

        # conf_uid / slug / filename are IMMUTABLE — keep the existing conf_uid so
        # we never orphan chat_history/<conf_uid>/core_memory.md.
        try:
            existing = read_yaml(path) or {}
        except Exception:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Existing file is unreadable."},
            )
        existing_cc = existing.get("character_config", {}) or {}
        conf_uid = existing_cc.get("conf_uid") or filename[:-5]

        fields = _extract_body_fields(body)
        conf_name = fields["conf_name"]
        persona = fields["persona_prompt"]
        skin = fields["live2d_model_name"]
        voice = fields["voice"] or None

        if not conf_name:
            return _bad_request("Missing display name (conf_name).")
        if not persona or not str(persona).strip():
            return _bad_request("Missing persona_prompt.")
        if not skin:
            return _bad_request("Missing live2d_model_name (skin).")

        try:
            await asyncio.to_thread(scan_and_register_skins)
        except Exception as e:
            logger.warning(f"pre-update skin scan failed: {type(e).__name__}")
        registered = {m.get("name") for m in _load_model_dict()}
        if skin not in registered:
            return _bad_request(
                f"Skin '{skin}' is not a registered Live2D model."
            )

        cc = _build_character_config(
            conf_name=conf_name,
            conf_uid=conf_uid,  # immutable
            persona_prompt=str(persona),
            live2d_model_name=skin,
            voice=voice,  # None -> tts_config omitted -> re-inherits base voice
            character_name=fields["character_name"]
            if fields["character_name"] is not None
            else existing_cc.get("character_name"),
            # Avatar: an explicit "" clears it (re-inherit base / show initial);
            # an absent key (None) preserves whatever was on disk.
            avatar=fields["avatar"]
            if fields["avatar"] is not None
            else existing_cc.get("avatar"),
        )
        try:
            await asyncio.to_thread(_write_character_yaml, path, cc)
        except Exception as e:
            logger.error(f"character update failed ({filename}): {type(e).__name__}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write character file."},
            )

        logger.info(f"character updated: file={filename} conf_uid={conf_uid}")
        return JSONResponse(
            {
                "ok": True,
                "filename": filename,
                "conf_uid": conf_uid,
                "conf_name": conf_name,
                # Editing the CURRENTLY-ACTIVE character only applies after re-select.
                "restart_required": False,
            }
        )

    # ------------------------------------------------------------------ #
    @router.delete("/api/characters/{filename}")
    async def delete_character(filename: str, request: Request):
        if not _is_local_request(request):
            return _forbidden()
        if filename == CONF_PATH:
            return _bad_request("Cannot delete the base character (conf.yaml).")
        path = _safe_character_path(filename)
        if path is None:
            return _bad_request("Invalid character filename.")
        if not os.path.exists(path):
            return JSONResponse(
                status_code=404, content={"ok": False, "error": "Character not found."}
            )

        try:
            # Prefer trash (recoverable) if available; fall back to os.remove.
            try:
                from send2trash import send2trash

                send2trash(path)
            except Exception:
                os.remove(path)
        except Exception as e:
            logger.error(f"character delete failed ({filename}): {type(e).__name__}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not delete character file."},
            )

        # NOTE: we intentionally do NOT delete chat_history/<conf_uid> — keep memory.
        logger.info(f"character deleted: file={filename}")
        return JSONResponse({"ok": True, "filename": filename})

    return router


# --------------------------------------------------------------------------- #
# Voice-sample synthesis (試聽 preview)
# --------------------------------------------------------------------------- #

def _sample_text_for_voice(voice: str) -> str:
    """Pick a short locale-appropriate preview line from the voice ShortName."""
    v = voice.lower()
    if v.startswith("zh-tw"):
        return VOICE_SAMPLE_TEXTS["zh-TW"]
    if v.startswith("zh-cn") or v.startswith("zh-hk") or v.startswith("zh"):
        return VOICE_SAMPLE_TEXTS["zh-CN"]
    if v.startswith("ja"):
        return VOICE_SAMPLE_TEXTS["ja"]
    return VOICE_SAMPLE_TEXTS["en"]


async def _synth_voice_sample(voice: str, text: str) -> Optional[bytes]:
    """Stream one short edge-tts utterance into memory; None on any failure.

    Mirrors the live engine (edge_tts.Communicate) but collects the mp3 bytes in
    memory instead of writing a file, so the endpoint can return them directly.
    """
    try:
        import edge_tts

        async def _collect() -> bytes:
            communicate = edge_tts.Communicate(text, voice)
            buf = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    buf += chunk["data"]
            return bytes(buf)

        data = await asyncio.wait_for(_collect(), timeout=VOICE_SAMPLE_TIMEOUT)
        return data or None
    except Exception as e:
        # edge-tts can be region-blocked or slow; never raise to the caller.
        logger.warning(
            f"voice-sample synth failed (voice={voice}): {type(e).__name__}. "
            "edge-tts may be blocked in your region."
        )
        return None


# --------------------------------------------------------------------------- #
# Optional live edge-tts voice list (network, behind ?full=1)
# --------------------------------------------------------------------------- #

def _build_live_voice_label(v: dict) -> str:
    friendly = v.get("FriendlyName") or v.get("ShortName", "")
    locale = v.get("Locale", "")
    gender = v.get("Gender", "")
    return f"{friendly}（{locale}・{gender}）" if locale else friendly


async def _live_edge_voices() -> Optional[list]:
    """Attempt edge_tts.list_voices() with a short timeout; None on any failure."""
    try:
        import edge_tts

        raw = await asyncio.wait_for(
            edge_tts.list_voices(), timeout=LIST_VOICES_TIMEOUT
        )
        voices = []
        for v in raw:
            short = v.get("ShortName")
            if not short:
                continue
            voices.append(
                {
                    "value": short,
                    "label": _build_live_voice_label(v),
                    "locale": v.get("Locale", ""),
                    "gender": v.get("Gender", ""),
                }
            )
        # zh-TW first to match the curated ordering / UI default.
        voices.sort(key=lambda x: (not x["locale"].startswith("zh-TW"), x["locale"]))
        return voices or None
    except Exception as e:
        logger.debug(f"live edge_tts.list_voices failed: {type(e).__name__}")
        return None
