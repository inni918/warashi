"""
First-run BYO-LLM setup endpoints.
=================================
Localhost-only REST endpoints that let the first-run setup wizard read/write the
active LLM credentials in conf.yaml, validate a chosen provider with one cheap
test call, and probe a local Ollama install for available models.

Design notes (cheap-tier, "semi-beginner" layer):
- The active provider is ALWAYS ``openai_compatible_llm`` (the selector at
  ``character_config.agent_config.agent_settings.basic_memory_agent.llm_provider``
  is kept unchanged). OpenAI / Claude / Gemini / Ollama all work through that one
  OpenAI-API-compatible block by varying ``base_url`` + ``model`` + ``llm_api_key``.
- conf.yaml is heavily commented, so writes go through ruamel.yaml round-trip mode
  to preserve comments + structure. We do NOT reuse config_manager/utils.py (it
  uses plain PyYAML and would drop every comment).
- The API key is NEVER logged and is masked on any read-back.
- Saving does NOT hot-reload the running server (run_server.py loads conf.yaml
  once at startup), so the POST response signals ``restart_required``.
"""

import os
import re
import asyncio
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse
from loguru import logger
from ruamel.yaml import YAML


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

CONF_PATH = "conf.yaml"

OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"

# Test/validate timeout for the cheap call and the Ollama probe (seconds).
TEST_CALL_TIMEOUT = 12.0
OLLAMA_PROBE_TIMEOUT = 4.0

# Provider -> default base_url. The wizard may pass an explicit base_url; if it
# omits it we fall back to these. Anthropic and Gemini both expose an
# OpenAI-compatible endpoint, so they all flow through openai_compatible_llm.
PROVIDER_DEFAULT_BASE_URL = {
    "openai": "https://api.openai.com/v1",
    "claude": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "ollama": OLLAMA_DEFAULT_BASE_URL,
}

# Known placeholder / non-real key values that mean "not configured yet".
PLACEHOLDER_KEYS = {
    "YOUR API KEY HERE",
    "Your Open AI API key",
    "Your Gemini API Key",
    "your api key here",
    "ollama",
    "",
}

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}

# Forwarding headers are added by proxies (reverse proxy / Tailscale Serve), which
# can make request.client.host appear local even for a remote user. A genuine
# first-run browser->localhost request carries none of these, so their presence
# means "proxied -> do not trust the apparently-local client.host".
_FORWARD_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-real-ip", "forwarded")


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def _allow_remote_config() -> bool:
    """Opt-in escape hatch: when system_config.allow_remote_config is true, the
    localhost-only admin guard below is relaxed so settings (LLM / character /
    translation) can be changed remotely — e.g. via Tailscale Serve from another
    device. Default FALSE. Only enable on a network you fully trust, since it lets
    anyone who can reach the server change these settings (there is no password)."""
    try:
        with open(CONF_PATH, encoding="utf-8") as f:
            data = YAML(typ="safe").load(f) or {}
        return bool((data.get("system_config") or {}).get("allow_remote_config", False))
    except Exception:
        return False


def _is_local_request(request: Request) -> bool:
    """True only if the request originates DIRECTLY from the local machine.

    Requires both a local client.host AND the absence of any proxy/forwarding
    header — so a reverse proxy or Tailscale Serve in front of a localhost-bound
    server cannot pass off a remote user as local. The system_config
    allow_remote_config flag (default false) overrides this for a trusted network.
    """
    if _allow_remote_config():
        return True
    client = request.client
    if client is None or client.host not in LOCAL_HOSTS:
        return False
    for h in _FORWARD_HEADERS:
        if request.headers.get(h):
            return False
    return True


def _forbidden() -> JSONResponse:
    return JSONResponse(status_code=403, content={"error": "forbidden"})


def _mask_key(key: Any) -> str:
    """Mask an API key for read-back: first 3-4 chars + '****'. Never the raw key."""
    if key is None:
        return ""
    key = str(key)
    if not key:
        return ""
    # Don't reveal the whole short placeholder either; show a hint only.
    visible = key[:4] if len(key) > 6 else key[:2]
    return f"{visible}****"


def _make_yaml() -> YAML:
    yaml = YAML()  # round-trip mode preserves comments + structure
    yaml.preserve_quotes = True
    yaml.width = 4096  # avoid line-wrapping/reflow of long scalar values
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def _load_conf() -> Any:
    yaml = _make_yaml()
    with open(CONF_PATH, "r", encoding="utf-8") as f:
        return yaml.load(f)


def _get_openai_block(data: Any) -> Optional[Any]:
    """Return the active openai_compatible_llm block, or None if path is missing."""
    try:
        return data["character_config"]["agent_config"]["llm_configs"][
            "openai_compatible_llm"
        ]
    except (KeyError, TypeError):
        return None


def _get_system_host(data: Any) -> Optional[str]:
    try:
        return str(data["system_config"]["host"])
    except (KeyError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# Ollama probe (server-side, avoids browser CORS / mixed-content)
# --------------------------------------------------------------------------- #

async def _probe_ollama_models() -> dict:
    """
    Hit the local Ollama /api/tags endpoint and return its model list.

    Returns ``{"available": True, "models": [...]}`` on success, or
    ``{"available": False}`` if Ollama is not reachable.
    """
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_PROBE_TIMEOUT) as client:
            resp = await client.get(OLLAMA_TAGS_URL)
            resp.raise_for_status()
            payload = resp.json()
        models = [
            m.get("name")
            for m in payload.get("models", [])
            if isinstance(m, dict) and m.get("name")
        ]
        return {"available": True, "models": models}
    except Exception as e:
        # Connection refused / timeout / bad payload => Ollama not usable.
        logger.debug(f"Ollama probe failed: {type(e).__name__}")
        return {"available": False, "models": []}


# --------------------------------------------------------------------------- #
# "is configured" heuristic
# --------------------------------------------------------------------------- #

async def _is_configured(block: Optional[Any]) -> bool:
    """
    Decide whether the LLM is genuinely usable out of the box.

    Not configured (show wizard) if the key is a placeholder, OR if it still
    points at the local Ollama default but Ollama is not actually running.
    """
    if block is None:
        return False

    api_key = block.get("llm_api_key")
    base_url = block.get("base_url")
    model = block.get("model")

    key_is_placeholder = (api_key is None) or (str(api_key) in PLACEHOLDER_KEYS)

    base_url_str = str(base_url) if base_url is not None else ""
    is_ollama = base_url_str.rstrip("/").startswith(
        OLLAMA_DEFAULT_BASE_URL.rstrip("/")
    ) or ":11434" in base_url_str

    if not is_ollama:
        # A cloud endpoint with a real (non-placeholder) key counts as configured.
        return not key_is_placeholder

    # Ollama path: 'ollama' is a real value only if Ollama is actually serving the
    # chosen model. Probe to confirm.
    probe = await _probe_ollama_models()
    if not probe.get("available"):
        return False
    if model is None:
        return False
    model_str = str(model)
    # Cloud models (e.g. "minimax-m3:cloud") are served by Ollama Cloud and never
    # appear in the local /api/tags list, so membership can't be checked here —
    # treat a reachable daemon + a cloud-suffixed name as configured.
    if model_str.endswith(":cloud") or model_str.endswith("-cloud"):
        return True
    return model_str in probe.get("models", [])


# --------------------------------------------------------------------------- #
# Cheap validation call (OpenAI-compatible chat/completions)
# --------------------------------------------------------------------------- #

def _test_call_sync(base_url: str, model: str, api_key: str) -> tuple[bool, str]:
    """
    Make ONE minimal OpenAI-compatible chat completion to validate the combo.

    Runs in a thread (blocking openai client). Returns ``(ok, error_message)``.
    The error message is sanitized and NEVER contains the api_key.
    """
    from openai import OpenAI

    try:
        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=TEST_CALL_TIMEOUT,
            max_retries=0,
        )
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            # Small budget (not 1) so a normal chat model returns real content.
            # NOTE: we deliberately do NOT reject on empty content. Empty replies
            # are not a reliable signal of a reasoning model — free cloud models
            # (e.g. minimax-m3:cloud) intermittently return empty on a trivial
            # ping, while adaptive reasoning models (e.g. glm-4.7) answer "ping"
            # directly and would pass anyway. The real protection for reasoning
            # models lives at the streaming layer (openai_compatible_llm falls
            # back to the reasoning field when content is empty), so a wizard
            # pre-check that hard-rejects on empty content only false-rejects
            # normal-but-terse models. Here we just confirm the call succeeds.
            max_tokens=32,
        )
        return True, ""
    except Exception as e:
        # Sanitize: surface the exception type + a short status hint, never the key.
        msg = _sanitize_error(e, api_key)
        return False, msg


def _sanitize_error(exc: Exception, api_key: str) -> str:
    """Build a user-facing error string that never echoes the API key."""
    text = str(exc)
    if api_key:
        # Belt-and-suspenders: strip the key if it ever leaked into the message.
        text = text.replace(api_key, "<redacted>")
    # Map common cases to friendly hints.
    lowered = text.lower()
    if "401" in text or "unauthor" in lowered or "invalid_api_key" in lowered:
        return "Authentication failed — the API key was rejected. Check the key."
    if "404" in text or "not found" in lowered or "model" in lowered and "exist" in lowered:
        return "The model was not found at this endpoint. Check the model name."
    if "connect" in lowered or "timeout" in lowered or "refused" in lowered:
        return "Could not reach the endpoint. Check the URL (and that the server is running)."
    if "rate" in lowered and "limit" in lowered:
        return "Rate limited by the provider. Try again in a moment."
    # Generic fallback: include exception type only, not full body.
    return f"Test call failed ({type(exc).__name__}). Check the URL, model, and key."


async def _validate_combo(base_url: str, model: str, api_key: str) -> tuple[bool, str]:
    return await asyncio.to_thread(_test_call_sync, base_url, model, api_key)


# --------------------------------------------------------------------------- #
# Atomic conf.yaml write (preserves comments via ruamel round-trip)
# --------------------------------------------------------------------------- #

def _quote_yaml_scalar(value: str) -> str:
    """
    Single-quote a scalar for YAML, matching the file's existing style (the
    openai_compatible_llm values are single-quoted). Escapes embedded quotes.
    """
    return "'" + str(value).replace("'", "''") + "'"


def _validate_path_with_ruamel() -> None:
    """
    Confirm the openai_compatible_llm block exists at the expected path before we
    touch the file. Uses ruamel round-trip load (per spec) so a malformed/missing
    structure fails loudly instead of corrupting the config.
    """
    yaml = _make_yaml()
    with open(CONF_PATH, "r", encoding="utf-8") as f:
        data = yaml.load(f)
    if _get_openai_block(data) is None:
        raise KeyError(
            "openai_compatible_llm block not found in conf.yaml "
            "(character_config.agent_config.llm_configs.openai_compatible_llm)"
        )


def _write_openai_block(base_url: str, model: str, api_key: str) -> None:
    """
    Surgically rewrite ONLY the three scalar leaves (base_url / model /
    llm_api_key) inside the active openai_compatible_llm block, preserving every
    other line, all inline comments, boolean casing, and `null` literals exactly
    as the user authored them. Written atomically (temp file + os.replace).

    ruamel round-trip is used to VALIDATE the path first (per spec). The write
    itself is a targeted line edit because a full ruamel re-dump normalizes
    unrelated scalars across this heavily hand-edited file (True->true,
    null->empty), which would churn dozens of lines the wizard must not touch.
    """
    # 1. Validate structure via ruamel before mutating anything.
    _validate_path_with_ruamel()

    with open(CONF_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 2. Locate the `openai_compatible_llm:` key line.
    block_re = re.compile(r"^(\s*)openai_compatible_llm:\s*(#.*)?$")
    start = None
    block_indent = None
    for i, line in enumerate(lines):
        m = block_re.match(line)
        if m:
            start = i
            block_indent = len(m.group(1))
            break
    if start is None:
        raise KeyError("openai_compatible_llm: line not found in conf.yaml")

    # 3. Determine the block's extent: contiguous lines more-indented than the key.
    end = len(lines)
    for j in range(start + 1, len(lines)):
        raw = lines[j]
        if raw.strip() == "" or raw.lstrip().startswith("#"):
            continue  # blanks/comments belong to the block
        indent = len(raw) - len(raw.lstrip())
        if indent <= block_indent:
            end = j
            break

    targets = {
        "base_url": base_url,
        "model": model,
        "llm_api_key": api_key,
    }
    found = set()
    # key: value  with optional trailing inline comment we must keep.
    for j in range(start + 1, end):
        line = lines[j]
        stripped = line.lstrip()
        for key, new_val in targets.items():
            if stripped.startswith(key + ":"):
                indent_ws = line[: len(line) - len(stripped)]
                # Preserve a trailing inline comment if present.
                comment = ""
                m_comment = re.search(r"(\s+#.*?)\s*$", line.rstrip("\n"))
                if m_comment:
                    comment = m_comment.group(1)
                lines[j] = (
                    f"{indent_ws}{key}: {_quote_yaml_scalar(new_val)}{comment}\n"
                )
                found.add(key)
                break

    missing = set(targets) - found
    if missing:
        raise KeyError(
            f"Could not locate keys {sorted(missing)} in openai_compatible_llm block"
        )

    # 4. One-time safety backup (consistent with the repo's conf.yaml.backup habit).
    if not os.path.exists(CONF_PATH + ".bak"):
        try:
            import shutil

            shutil.copy2(CONF_PATH, CONF_PATH + ".bak")
        except Exception as e:
            logger.warning(f"Could not create conf.yaml.bak: {type(e).__name__}")

    # 5. Atomic write: temp file in the same dir, then os.replace().
    conf_dir = os.path.dirname(os.path.abspath(CONF_PATH)) or "."
    tmp_path = os.path.join(conf_dir, ".conf.yaml.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.replace(tmp_path, CONF_PATH)


# --------------------------------------------------------------------------- #
# Route factory
# --------------------------------------------------------------------------- #

def init_llm_config_route() -> APIRouter:
    """
    REST endpoints for the first-run BYO-LLM setup wizard. Localhost-only.

    - GET  /api/llm-config                -> current config, masked + is_configured
    - POST /api/llm-config                -> validate then save (ruamel round-trip)
    - GET  /api/llm-config/ollama-models  -> server-side Ollama probe
    """
    router = APIRouter()

    @router.get("/api/llm-config")
    async def get_llm_config(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        try:
            data = _load_conf()
        except Exception as e:
            logger.error(f"llm-config read failed: {type(e).__name__}")
            return JSONResponse(
                status_code=500, content={"error": "could not read config"}
            )

        block = _get_openai_block(data)
        if block is None:
            return JSONResponse(
                status_code=500,
                content={"error": "openai_compatible_llm block missing in conf.yaml"},
            )

        configured = await _is_configured(block)
        return JSONResponse(
            {
                "provider": "openai_compatible_llm",
                "base_url": (
                    str(block.get("base_url")) if block.get("base_url") is not None else ""
                ),
                "model": str(block.get("model")) if block.get("model") is not None else "",
                "api_key_masked": _mask_key(block.get("llm_api_key")),
                "is_configured": configured,
            }
        )

    @router.post("/api/llm-config")
    async def save_llm_config(request: Request):
        if not _is_local_request(request):
            return _forbidden()

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Invalid JSON body."}
            )

        provider = str(body.get("provider", "")).strip().lower()
        api_key = body.get("api_key")
        model = body.get("model")
        base_url = body.get("base_url")

        # Map provider -> base_url default when omitted.
        if not base_url:
            base_url = PROVIDER_DEFAULT_BASE_URL.get(provider)
        if provider == "ollama" and not api_key:
            api_key = "ollama"

        # Required-field validation.
        if provider not in PROVIDER_DEFAULT_BASE_URL:
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error": "Unknown provider. Use openai, claude, gemini, or ollama.",
                },
            )
        if not base_url:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Missing base_url."},
            )
        if not model:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Missing model name."},
            )
        if not api_key:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Missing API key."},
            )

        base_url = str(base_url).strip()
        model = str(model).strip()
        api_key = str(api_key)

        # VALIDATE with one cheap call BEFORE writing anything.
        ok, err = await _validate_combo(base_url, model, api_key)
        if not ok:
            # err is already sanitized (no key). Do not log the key.
            logger.info(f"llm-config validation failed for provider={provider}")
            return JSONResponse(status_code=400, content={"ok": False, "error": err})

        # Persist via ruamel round-trip (comments preserved), atomically.
        try:
            await asyncio.to_thread(_write_openai_block, base_url, model, api_key)
        except Exception as e:
            logger.error(f"llm-config write failed: {type(e).__name__}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Could not write config file."},
            )

        logger.info(f"llm-config saved (provider={provider}, model={model})")
        return JSONResponse(
            {
                "ok": True,
                "provider": "openai_compatible_llm",
                "model": model,
                "base_url": base_url,
                "api_key_masked": _mask_key(api_key),
                # Server loads conf.yaml once at startup; a live save needs a restart.
                "restart_required": True,
            }
        )

    @router.get("/api/llm-config/ollama-models")
    async def get_ollama_models(request: Request):
        if not _is_local_request(request):
            return _forbidden()
        result = await _probe_ollama_models()
        return JSONResponse(result)

    return router
