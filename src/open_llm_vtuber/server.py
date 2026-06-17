"""
Open-LLM-VTuber Server
========================
This module contains the WebSocket server for Open-LLM-VTuber, which handles
the WebSocket connections, serves static files, and manages the web tool.
It uses FastAPI for the server and Starlette for static file serving.
"""

import os
import shutil

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response
from starlette.staticfiles import StaticFiles as StarletteStaticFiles

from .routes import init_client_ws_route, init_webtool_routes, init_proxy_route
from .llm_config_route import init_llm_config_route
from .character_route import init_character_route
from .translator_route import init_translator_route
from .memory_route import init_memory_route
from .perf_route import init_perf_route
from .topics_route import (
    init_topics_route,
    start_news_refresh_task,
    stop_news_refresh_task,
)
from .service_context import ServiceContext
from .config_manager.utils import Config


# Create a custom StaticFiles class that adds CORS headers
class CORSStaticFiles(StarletteStaticFiles):
    """
    Static files handler that adds CORS headers to all responses.
    Needed because Starlette StaticFiles might bypass standard middleware.
    """

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)

        # Add CORS headers to all responses
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"

        if path.endswith(".js"):
            response.headers["Content-Type"] = "application/javascript"

        # Don't cache HTML: avoids edits getting stuck behind a stale browser cache (especially
        # for remote devices). Decided by content-type because a request for "/" has an empty
        # path (StaticFiles serves index.html internally). Hash-named .js/.css can still cache long.
        if "text/html" in response.headers.get("content-type", ""):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"

        return response


class AvatarStaticFiles(CORSStaticFiles):
    """
    Avatar files handler with security restrictions and CORS headers
    """

    async def get_response(self, path: str, scope):
        allowed_extensions = (".jpg", ".jpeg", ".png", ".gif", ".svg")
        if not any(path.lower().endswith(ext) for ext in allowed_extensions):
            return Response("Forbidden file type", status_code=403)
        response = await super().get_response(path, scope)
        return response


class WebSocketServer:
    """
    API server for Open-LLM-VTuber. This contains the websocket endpoint for the client, hosts the web tool, and serves static files.

    Creates and configures a FastAPI app, registers all routes
    (WebSocket, web tools, proxy) and mounts static assets with CORS.

    Args:
        config (Config): Application configuration containing system settings.
        default_context_cache (ServiceContext, optional):
            Pre‑initialized service context for sessions' service context to reference to.
            **If omitted, `initialize()` method needs to be called to load service context.**

    Notes:
        - If default_context_cache is omitted, call `await initialize()` to load service context cache.
        - Use `clean_cache()` to clear and recreate the local cache directory.
    """

    def __init__(self, config: Config, default_context_cache: ServiceContext = None):
        self.app = FastAPI(title="Open-LLM-VTuber Server")  # Added title for clarity
        self.config = config
        self.default_context_cache = (
            default_context_cache or ServiceContext()
        )  # Use provided context or initialize a new empty one waiting to be loaded
        # It will be populated during the initialize method call

        # Add global CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Include routes, passing the context instance
        # The context will be populated during the initialize step
        self.app.include_router(
            init_client_ws_route(default_context_cache=self.default_context_cache),
        )
        self.app.include_router(
            init_webtool_routes(default_context_cache=self.default_context_cache),
        )

        # First-run BYO-LLM setup endpoints (localhost-only). Reads/writes conf.yaml
        # directly, so no ServiceContext is needed. Registered BEFORE the static
        # mounts below so the /api/* routes resolve ahead of the "/" catch-all.
        self.app.include_router(init_llm_config_route())

        # Character Manager endpoints (localhost-only). Create/edit/switch/delete
        # companion characters (override YAMLs in characters/) + scan/auto-register
        # Live2D skins + list edge-tts voices. Same /api/* placement (before "/").
        self.app.include_router(init_character_route())

        # Cross-language voice + translated-subtitle toggle (localhost-only). Reads/
        # writes tts_preprocessor_config.translator_config + base edge_tts voice in
        # conf.yaml. Same /api/* placement (before "/").
        self.app.include_router(init_translator_route())

        # Long-term (core) memory settings endpoints (localhost-only). Read/clear the
        # active character's core memory + toggle long_term_memory_enabled in
        # conf.yaml. Same /api/* placement (before "/").
        self.app.include_router(init_memory_route())

        # Performance / hardware settings endpoints (localhost-only). ASR/TTS engine
        # selector + cloud creds, ollama keep_alive, memory consolidation interval, and
        # one-click performance presets. Reads/writes conf.yaml surgically. Same /api/*
        # placement (before "/").
        self.app.include_router(init_perf_route())

        # Proactive topic-pool endpoints (localhost-only). Manage the manual topic
        # pool + optional Google-News auto-topics that compose into
        # proactive_speak_prompt.txt. Same /api/* placement (before "/").
        self.app.include_router(init_topics_route())

        # Start the in-app periodic news-refresh task on server startup, and cancel
        # it on shutdown. This replaces an OS cron: when news auto-topics are enabled
        # it re-fetches every interval_hours and recomposes the proactive prompt.
        # Cancel-safe + exception-swallowing (a fetch error never kills the loop).
        @self.app.on_event("startup")
        async def _start_topics_refresh():  # noqa: D401
            try:
                start_news_refresh_task()
            except Exception as e:
                # Never let the background task break server startup.
                from loguru import logger as _logger

                _logger.warning(
                    f"could not start news-refresh task: {type(e).__name__}: {e}"
                )

        @self.app.on_event("shutdown")
        async def _stop_topics_refresh():  # noqa: D401
            try:
                await stop_news_refresh_task()
            except Exception:
                pass

        # Initialize and include proxy routes if proxy is enabled
        system_config = config.system_config
        if hasattr(system_config, "enable_proxy") and system_config.enable_proxy:
            # Construct the server URL for the proxy
            host = system_config.host
            port = system_config.port
            server_url = f"ws://{host}:{port}/client-ws"
            self.app.include_router(
                init_proxy_route(server_url=server_url),
            )

        # Mount cache directory first (to ensure audio file access)
        if not os.path.exists("cache"):
            os.makedirs("cache")
        self.app.mount(
            "/cache",
            CORSStaticFiles(directory="cache"),
            name="cache",
        )

        # Mount static files with CORS-enabled handlers
        self.app.mount(
            "/live2d-models",
            CORSStaticFiles(directory="live2d-models"),
            name="live2d-models",
        )
        self.app.mount(
            "/bg",
            CORSStaticFiles(directory="backgrounds"),
            name="backgrounds",
        )
        self.app.mount(
            "/avatars",
            AvatarStaticFiles(directory="avatars"),
            name="avatars",
        )

        # Mount web tool directory separately from frontend
        self.app.mount(
            "/web-tool",
            CORSStaticFiles(directory="web_tool", html=True),
            name="web_tool",
        )

        # Mount main frontend last (as catch-all)
        self.app.mount(
            "/",
            CORSStaticFiles(directory="frontend", html=True),
            name="frontend",
        )

    async def initialize(self):
        """Asynchronously load the service context from config.
        Calling this function is needed if default_context_cache was not provided to the constructor."""
        await self.default_context_cache.load_from_config(self.config)

    @staticmethod
    def clean_cache():
        """Clean the cache directory by removing and recreating it."""
        cache_dir = "cache"
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            os.makedirs(cache_dir)
