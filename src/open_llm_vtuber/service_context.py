import os
import json
from typing import Callable
from loguru import logger
from fastapi import WebSocket

from prompts import prompt_loader
from .live2d_model import Live2dModel
from .asr.asr_interface import ASRInterface
from .tts.tts_interface import TTSInterface
from .vad.vad_interface import VADInterface
from .agent.agents.agent_interface import AgentInterface
from .translate.translate_interface import TranslateInterface

from .mcpp.server_registry import ServerRegistry
from .mcpp.tool_manager import ToolManager
from .mcpp.mcp_client import MCPClient
from .mcpp.tool_executor import ToolExecutor
from .mcpp.tool_adapter import ToolAdapter

from .asr.asr_factory import ASRFactory
from .tts.tts_factory import TTSFactory
from .vad.vad_factory import VADFactory
from .agent.agent_factory import AgentFactory
from .translate.translate_factory import TranslateFactory

from .config_manager import (
    Config,
    AgentConfig,
    CharacterConfig,
    SystemConfig,
    ASRConfig,
    TTSConfig,
    VADConfig,
    TranslatorConfig,
    read_yaml,
    validate_config,
)


class ServiceContext:
    """Initializes, stores, and updates the asr, tts, and llm instances and other
    configurations for a connected client."""

    def __init__(self):
        self.config: Config = None
        self.system_config: SystemConfig = None
        self.character_config: CharacterConfig = None

        self.live2d_model: Live2dModel = None
        self.asr_engine: ASRInterface = None
        self.tts_engine: TTSInterface = None
        self.agent_engine: AgentInterface = None
        # translate_engine can be none if translation is disabled
        self.vad_engine: VADInterface | None = None
        self.translate_engine: TranslateInterface | None = None
        # Voice language (V) the current audio translate_engine was built to target.
        # Tracked so the audio engine is rebuilt when V changes on a character switch
        # even if the translator_config block itself is unchanged.
        self._audio_translate_voice_lang: str | None = None
        # display-only subtitle translation engine; None when disabled
        self.subtitle_translate_engine: TranslateInterface | None = None

        self.mcp_server_registery: ServerRegistry | None = None
        self.tool_adapter: ToolAdapter | None = None
        self.tool_manager: ToolManager | None = None
        self.mcp_client: MCPClient | None = None
        self.tool_executor: ToolExecutor | None = None

        # the system prompt is a combination of the persona prompt and live2d expression prompt
        self.system_prompt: str = None

        # Store the generated MCP prompt string (if MCP enabled)
        self.mcp_prompt: str = ""

        self.history_uid: str = ""  # Add history_uid field

        self.send_text: Callable = None
        self.client_uid: str = None

    def __str__(self):
        return (
            f"ServiceContext:\n"
            f"  System Config: {'Loaded' if self.system_config else 'Not Loaded'}\n"
            f"    Details: {json.dumps(self.system_config.model_dump(), indent=6) if self.system_config else 'None'}\n"
            f"  Live2D Model: {self.live2d_model.model_info if self.live2d_model else 'Not Loaded'}\n"
            f"  ASR Engine: {type(self.asr_engine).__name__ if self.asr_engine else 'Not Loaded'}\n"
            f"    Config: {json.dumps(self.character_config.asr_config.model_dump(), indent=6) if self.character_config.asr_config else 'None'}\n"
            f"  TTS Engine: {type(self.tts_engine).__name__ if self.tts_engine else 'Not Loaded'}\n"
            f"    Config: {json.dumps(self.character_config.tts_config.model_dump(), indent=6) if self.character_config.tts_config else 'None'}\n"
            f"  LLM Engine: {type(self.agent_engine).__name__ if self.agent_engine else 'Not Loaded'}\n"
            f"    Agent Config: {json.dumps(self.character_config.agent_config.model_dump(), indent=6) if self.character_config.agent_config else 'None'}\n"
            f"  VAD Engine: {type(self.vad_engine).__name__ if self.vad_engine else 'Not Loaded'}\n"
            f"    Agent Config: {json.dumps(self.character_config.vad_config.model_dump(), indent=6) if self.character_config.vad_config else 'None'}\n"
            f"  System Prompt: {self.system_prompt or 'Not Set'}\n"
            f"  MCP Enabled: {'Yes' if self.mcp_client else 'No'}"
        )

    # ==== Initializers

    async def _init_mcp_components(self, use_mcpp, enabled_servers):
        """Initializes MCP components based on configuration, dynamically fetching tool info."""
        logger.debug(
            f"Initializing MCP components: use_mcpp={use_mcpp}, enabled_servers={enabled_servers}"
        )

        # Reset MCP components first
        self.mcp_server_registery = None
        self.tool_manager = None
        self.mcp_client = None
        self.tool_executor = None
        self.json_detector = None
        self.mcp_prompt = ""

        if use_mcpp and enabled_servers:
            # 1. Initialize ServerRegistry
            self.mcp_server_registery = ServerRegistry()
            logger.info("ServerRegistry initialized or referenced.")

            # 2. Use ToolAdapter to get the MCP prompt and tools
            if not self.tool_adapter:
                logger.error(
                    "ToolAdapter not initialized before calling _init_mcp_components."
                )
                self.mcp_prompt = "[Error: ToolAdapter not initialized]"
                return  # Exit if ToolAdapter is mandatory and not initialized

            try:
                (
                    mcp_prompt_string,
                    openai_tools,
                    claude_tools,
                ) = await self.tool_adapter.get_tools(enabled_servers)
                # Store the generated prompt string
                self.mcp_prompt = mcp_prompt_string
                logger.info(
                    f"Dynamically generated MCP prompt string (length: {len(self.mcp_prompt)})."
                )
                logger.info(
                    f"Dynamically formatted tools - OpenAI: {len(openai_tools)}, Claude: {len(claude_tools)}."
                )

                # 3. Initialize ToolManager with the fetched formatted tools

                _, raw_tools_dict = await self.tool_adapter.get_server_and_tool_info(
                    enabled_servers
                )
                self.tool_manager = ToolManager(
                    formatted_tools_openai=openai_tools,
                    formatted_tools_claude=claude_tools,
                    initial_tools_dict=raw_tools_dict,
                )
                logger.info("ToolManager initialized with dynamically fetched tools.")

            except Exception as e:
                logger.error(
                    f"Failed during dynamic MCP tool construction: {e}", exc_info=True
                )
                # Ensure dependent components are not created if construction fails
                self.tool_manager = None
                self.mcp_prompt = "[Error constructing MCP tools/prompt]"

            # 4. Initialize MCPClient
            if self.mcp_server_registery:
                self.mcp_client = MCPClient(
                    self.mcp_server_registery, self.send_text, self.client_uid
                )
                logger.info("MCPClient initialized for this session.")
            else:
                logger.error(
                    "MCP enabled but ServerRegistry not available. MCPClient not created."
                )
                self.mcp_client = None  # Ensure it's None

            # 5. Initialize ToolExecutor
            if self.mcp_client and self.tool_manager:
                self.tool_executor = ToolExecutor(self.mcp_client, self.tool_manager)
                logger.info("ToolExecutor initialized for this session.")
            else:
                logger.warning(
                    "MCPClient or ToolManager not available. ToolExecutor not created."
                )
                self.tool_executor = None  # Ensure it's None

            logger.info("StreamJSONDetector initialized for this session.")

        elif use_mcpp and not enabled_servers:
            logger.warning(
                "use_mcpp is True, but mcp_enabled_servers list is empty. MCP components not initialized."
            )
        else:
            logger.debug(
                "MCP components not initialized (use_mcpp is False or no enabled servers)."
            )

    async def close(self):
        """Clean up resources, especially the MCPClient."""
        logger.info("Closing ServiceContext resources...")
        if self.mcp_client:
            logger.info(f"Closing MCPClient for context instance {id(self)}...")
            await self.mcp_client.aclose()
            self.mcp_client = None
        if self.agent_engine and hasattr(self.agent_engine, "close"):
            await self.agent_engine.close()  # Ensure agent resources are also closed
        logger.info("ServiceContext closed.")

    async def load_cache(
        self,
        config: Config,
        system_config: SystemConfig,
        character_config: CharacterConfig,
        live2d_model: Live2dModel,
        asr_engine: ASRInterface,
        tts_engine: TTSInterface,
        vad_engine: VADInterface,
        agent_engine: AgentInterface,
        translate_engine: TranslateInterface | None,
        mcp_server_registery: ServerRegistry | None = None,
        tool_adapter: ToolAdapter | None = None,
        send_text: Callable = None,
        client_uid: str = None,
        subtitle_translate_engine: TranslateInterface | None = None,
    ) -> None:
        """
        Load the ServiceContext with the reference of the provided instances.
        Pass by reference so no reinitialization will be done.
        """
        if not character_config:
            raise ValueError("character_config cannot be None")
        if not system_config:
            raise ValueError("system_config cannot be None")

        self.config = config
        self.system_config = system_config
        self.character_config = character_config
        self.live2d_model = live2d_model
        self.asr_engine = asr_engine
        self.tts_engine = tts_engine
        self.vad_engine = vad_engine
        self.agent_engine = agent_engine
        self.translate_engine = translate_engine
        # Unknown which V a cached engine was built for; force a rebuild on the next
        # load_from_config so the audio target matches the active character's V.
        self._audio_translate_voice_lang = None
        self.subtitle_translate_engine = subtitle_translate_engine
        # Load potentially shared components by reference
        self.mcp_server_registery = mcp_server_registery
        self.tool_adapter = tool_adapter
        self.send_text = send_text
        self.client_uid = client_uid

        # Initialize session-specific MCP components
        await self._init_mcp_components(
            self.character_config.agent_config.agent_settings.basic_memory_agent.use_mcpp,
            self.character_config.agent_config.agent_settings.basic_memory_agent.mcp_enabled_servers,
        )

        logger.debug(f"Loaded service context with cache: {character_config}")

    async def load_from_config(self, config: Config) -> None:
        """
        Load the ServiceContext with the config.
        Reinitialize the instances if the config is different.

        Parameters:
        - config (Dict): The configuration dictionary.
        """
        if not self.config:
            self.config = config

        if not self.system_config:
            self.system_config = config.system_config

        if not self.character_config:
            self.character_config = config.character_config

        # update all sub-configs

        # init live2d from character config
        self.init_live2d(config.character_config.live2d_model_name)

        # init asr from character config
        self.init_asr(config.character_config.asr_config)

        # init tts from character config
        self.init_tts(config.character_config.tts_config)

        # init vad from character config
        self.init_vad(config.character_config.vad_config)

        # Initialize shared ToolAdapter if it doesn't exist yet
        if (
            not self.tool_adapter
            and config.character_config.agent_config.agent_settings.basic_memory_agent.use_mcpp
        ):
            if not self.mcp_server_registery:
                logger.info(
                    "Initializing shared ServerRegistry within load_from_config."
                )
                self.mcp_server_registery = ServerRegistry()
            logger.info("Initializing shared ToolAdapter within load_from_config.")
            self.tool_adapter = ToolAdapter(server_registery=self.mcp_server_registery)

        # Initialize MCP Components before initializing Agent
        await self._init_mcp_components(
            config.character_config.agent_config.agent_settings.basic_memory_agent.use_mcpp,
            config.character_config.agent_config.agent_settings.basic_memory_agent.mcp_enabled_servers,
        )

        # init agent from character config
        await self.init_agent(
            config.character_config.agent_config,
            config.character_config.persona_prompt,
        )

        # Derive the NEW character's voice language V from the config being loaded
        # (self.character_config is still the OLD one here — it's assigned below).
        # The audio translate engine targets V so the spoken voice always matches the
        # character's voice language regardless of the reply (player) language.
        from .conversations.conversation_utils import derive_voice_lang

        self.init_translate(
            config.character_config.tts_preprocessor_config.translator_config,
            voice_lang=derive_voice_lang(config.character_config),
        )

        # store typed config references
        self.config = config
        self.system_config = config.system_config or self.system_config
        self.character_config = config.character_config

    def init_live2d(self, live2d_model_name: str) -> None:
        logger.info(f"Initializing Live2D: {live2d_model_name}")
        try:
            self.live2d_model = Live2dModel(live2d_model_name)
            self.character_config.live2d_model_name = live2d_model_name
        except Exception as e:
            logger.critical(f"Error initializing Live2D: {e}")
            logger.critical("Try to proceed without Live2D...")

    def init_asr(self, asr_config: ASRConfig) -> None:
        # 系統層級「玩家語言」推導 ASR 辨識語言（best-effort）。目前 active 模型
        # sense_voice 只支援 zh/en/ja/ko/yue；clamp 後落在這個集合才覆寫 sherpa 的
        # language leaf，集合外（如法/德/西）回 'auto'，等於不強制 ＝ 維持原本辨識行為。
        # 語音路徑（translate_audio）完全不動。只動 sherpa_onnx_asr 這一個 engine。
        player_language = (
            getattr(self.system_config, "player_language", "") or ""
        ).strip()
        if player_language and asr_config.asr_model == "sherpa_onnx_asr":
            sherpa_block = getattr(asr_config, "sherpa_onnx_asr", None)
            if sherpa_block is not None:
                from .asr.sherpa_onnx_asr import VoiceRecognition as _SherpaASR

                derived = _SherpaASR._clamp_sense_voice_language(player_language)
                if derived != getattr(sherpa_block, "language", "auto"):
                    sherpa_block.language = derived
        if not self.asr_engine or (self.character_config.asr_config != asr_config):
            logger.info(f"Initializing ASR: {asr_config.asr_model}")
            self.asr_engine = ASRFactory.get_asr_system(
                asr_config.asr_model,
                **getattr(asr_config, asr_config.asr_model).model_dump(),
            )
            # saving config should be done after successful initialization
            self.character_config.asr_config = asr_config
        else:
            logger.info("ASR already initialized with the same config.")

    def init_tts(self, tts_config: TTSConfig) -> None:
        if not self.tts_engine or (self.character_config.tts_config != tts_config):
            logger.info(f"Initializing TTS: {tts_config.tts_model}")
            self.tts_engine = TTSFactory.get_tts_engine(
                tts_config.tts_model,
                **getattr(tts_config, tts_config.tts_model.lower()).model_dump(),
            )
            # saving config should be done after successful initialization
            self.character_config.tts_config = tts_config
        else:
            logger.info("TTS already initialized with the same config.")

    def init_vad(self, vad_config: VADConfig) -> None:
        if vad_config.vad_model is None:
            logger.info("VAD is disabled.")
            self.vad_engine = None
            return

        if not self.vad_engine or (self.character_config.vad_config != vad_config):
            logger.info(f"Initializing VAD: {vad_config.vad_model}")
            self.vad_engine = VADFactory.get_vad_engine(
                vad_config.vad_model,
                **getattr(vad_config, vad_config.vad_model.lower()).model_dump(),
            )
            # saving config should be done after successful initialization
            self.character_config.vad_config = vad_config
        else:
            logger.info("VAD already initialized with the same config.")

    async def init_agent(self, agent_config: AgentConfig, persona_prompt: str) -> None:
        """Initialize or update the LLM engine based on agent configuration."""
        logger.info(f"Initializing Agent: {agent_config.conversation_agent_choice}")

        if (
            self.agent_engine is not None
            and agent_config == self.character_config.agent_config
            and persona_prompt == self.character_config.persona_prompt
        ):
            logger.debug("Agent already initialized with the same config.")
            return

        system_prompt = await self.construct_system_prompt(persona_prompt)

        # Pass avatar to agent factory
        avatar = self.character_config.avatar or ""  # Get avatar from config

        try:
            self.agent_engine = AgentFactory.create_agent(
                conversation_agent_choice=agent_config.conversation_agent_choice,
                agent_settings=agent_config.agent_settings.model_dump(),
                llm_configs=agent_config.llm_configs.model_dump(),
                system_prompt=system_prompt,
                live2d_model=self.live2d_model,
                tts_preprocessor_config=self.character_config.tts_preprocessor_config,
                character_avatar=avatar,
                system_config=self.system_config.model_dump(),
                tool_manager=self.tool_manager,
                tool_executor=self.tool_executor,
                mcp_prompt_string=self.mcp_prompt,
            )

            logger.debug(f"Agent choice: {agent_config.conversation_agent_choice}")
            logger.debug(f"System prompt: {system_prompt}")

            # Save the current configuration
            self.character_config.agent_config = agent_config
            self.system_prompt = system_prompt

        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            raise

    def init_translate(
        self, translator_config: TranslatorConfig, voice_lang: str | None = None
    ) -> None:
        """Initialize or update the translation engine(s) based on the configuration.

        Two independent engines are built from the SAME translator_config:
        - ``translate_engine``: AUDIO path (translates tts_text for the spoken voice).
          AUTOMATIC: this engine is now ALWAYS built (``translate_audio`` is an internal
          auto-on flag, not a user toggle). Whether a given sentence is actually
          translated is decided PER-SENTENCE in handle_sentence_output, by comparing the
          character's voice language V against the detected reply language R — translate
          only when V != R. So the engine being present no longer means "translate
          everything"; it just means the capability is ready.
          Its TARGET is now V (``voice_lang`` — the CHARACTER's voice language), mapped
          to the provider's expected format, so a reply in any language is spoken in the
          character's own voice language. The global per-conf target_lang stays only as
          a FALLBACK when V can't be derived. Rebuilt per character switch (this method
          re-runs on switch), so a new character's V takes effect immediately.
        - ``subtitle_translate_engine``: DISPLAY-ONLY path (translates the reply text
          for the on-screen subtitle). Built only when ``translate_subtitle`` is True.
          It targets ``subtitle_target_lang`` and NEVER mutates the canonical reply
          (memory/history stay on the original reply R).
        Subtitle may be disabled independently; disabled -> its engine is reset to None.
        """
        config_changed = (
            self.character_config.tts_preprocessor_config.translator_config
            != translator_config
        )
        # Rebuild the audio engine whenever V changes too, even if translator_config is
        # otherwise identical (e.g. two characters that share a translator block but
        # have different voice languages).
        voice_lang_changed = voice_lang != self._audio_translate_voice_lang

        # --- AUDIO translation engine (now ALWAYS built; gate is per-sentence) ---
        # translate_audio is kept as an internal auto-on flag (always True in conf), so
        # the engine is always available; the V != R decision happens per sentence.
        if not translator_config.translate_audio:
            # Defensive: only if a user manually forces translate_audio=False in conf.
            logger.debug("Audio translation engine disabled (translate_audio=False).")
            self.translate_engine = None
            self._audio_translate_voice_lang = None
        elif not self.translate_engine or config_changed or voice_lang_changed:
            provider = translator_config.translate_provider
            # Copy the provider block and override its target leaf with V (mapped per
            # provider). If V can't be derived/mapped, keep the conf's global target.
            audio_cfg = getattr(translator_config, provider).model_dump()
            mapped = self._map_voice_lang_to_provider_target(voice_lang, provider)
            if mapped is not None:
                if provider == "deeplx":
                    audio_cfg["deeplx_target_lang"] = mapped
                else:  # llm / tencent both use 'target_lang'
                    audio_cfg["target_lang"] = mapped
                logger.info(
                    f"Initializing audio Translator: {provider} -> "
                    f"V={voice_lang} (target={mapped})"
                )
            else:
                logger.info(
                    f"Initializing audio Translator: {provider} -> "
                    f"global target_lang (V={voice_lang} not mappable)"
                )
            self.translate_engine = TranslateFactory.get_translator(provider, audio_cfg)
            self._audio_translate_voice_lang = voice_lang
        else:
            logger.info("Audio translation already initialized with the same config.")

        # --- SUBTITLE translation engine (display-only) ---
        if not translator_config.translate_subtitle:
            logger.debug("Subtitle translation is disabled.")
            self.subtitle_translate_engine = None
        elif not self.subtitle_translate_engine or config_changed:
            logger.info(
                "Initializing subtitle Translator: "
                f"{translator_config.translate_provider} -> "
                f"{translator_config.subtitle_target_lang}"
            )
            self.subtitle_translate_engine = self._build_subtitle_translator(
                translator_config
            )
        else:
            logger.info(
                "Subtitle translation already initialized with the same config."
            )

        # Persist the (possibly updated) translator_config reference once.
        self.character_config.tts_preprocessor_config.translator_config = (
            translator_config
        )

    def _build_subtitle_translator(
        self, translator_config: TranslatorConfig
    ) -> TranslateInterface | None:
        """Build a SEPARATE translate engine for the display-only subtitle path.

        Reuses the SAME provider as the audio path but overrides only the target
        language with ``subtitle_target_lang`` so the subtitle can differ from the
        spoken voice. The canonical reply is never touched by this engine; on any
        runtime error LLMTranslate already returns the original text (fail-soft).
        Returns None if it cannot be built (subtitle then falls back to the
        original reply R at call sites).
        """
        provider = translator_config.translate_provider
        target = (translator_config.subtitle_target_lang or "").strip()
        if not target:
            logger.warning(
                "translate_subtitle is on but subtitle_target_lang is empty; "
                "subtitle translation disabled."
            )
            return None
        sub_block = getattr(translator_config, provider, None)
        if sub_block is None:
            logger.warning(
                f"translate_subtitle is on but provider '{provider}' block is "
                "missing; subtitle translation disabled."
            )
            return None
        # Copy the provider config and override only its target-language leaf.
        # The stored subtitle target is a HUMAN-READABLE name (e.g. '德文') so the
        # llm engine can use it verbatim in its prompt. DeepL needs a target CODE,
        # so for deeplx we map the name -> code (resolver passes a real code
        # through unchanged, keeping hand-edited conf.yaml values working).
        cfg = sub_block.model_dump()
        if provider == "deeplx":
            from .translate.deeplx import resolve_deepl_target_lang

            cfg["deeplx_target_lang"] = resolve_deepl_target_lang(target)
        else:  # llm / tencent both use 'target_lang'
            cfg["target_lang"] = target
        try:
            return TranslateFactory.get_translator(provider, cfg)
        except Exception as e:
            logger.warning(
                f"Could not build subtitle translator ({provider}): "
                f"{type(e).__name__}: {e}"
            )
            return None

    @staticmethod
    def _map_voice_lang_to_provider_target(
        voice_lang: str | None, provider: str
    ) -> str | None:
        """Map a short voice-language bucket V ('ja'/'zh'/'en'/'ko') to the target
        value the given provider expects. Returns None when V is empty/unknown so the
        caller falls back to the conf's global target_lang (fail-soft).

        - deeplx: needs a target CODE. Reuse the SAME name->code resolver the subtitle
          translator uses (resolve_deepl_target_lang); a plain code like 'JA' passes
          through unchanged.
        - llm: takes a HUMAN-READABLE label dropped into a Chinese prompt -> 日文/中文/...
        - tencent: takes a lowercase language code -> ja/zh/en/ko (== V already).
        """
        if not voice_lang:
            return None
        v = str(voice_lang).strip().lower()
        if v not in ("ja", "zh", "en", "ko"):
            return None
        provider = (provider or "").lower()
        if provider == "deeplx":
            # uppercased short codes; all in resolve_deepl_target_lang's known set
            from .translate.deeplx import resolve_deepl_target_lang

            return resolve_deepl_target_lang(v.upper())
        elif provider == "llm":
            return {"ja": "日文", "zh": "中文", "en": "English", "ko": "韓文"}[v]
        elif provider == "tencent":
            return v  # tencent uses lowercase codes
        return None

    # ==== utils

    async def construct_system_prompt(self, persona_prompt: str) -> str:
        """
        Append tool prompts to persona prompt.

        Parameters:
        - persona_prompt (str): The persona prompt.

        Returns:
        - str: The system prompt with all tool prompts appended.
        """
        logger.debug(f"constructing persona_prompt: '''{persona_prompt}'''")

        for prompt_name, prompt_file in self.system_config.tool_prompts.items():
            if (
                prompt_name == "group_conversation_prompt"
                or prompt_name == "proactive_speak_prompt"
            ):
                continue

            prompt_content = prompt_loader.load_util(prompt_file)

            if prompt_name == "live2d_expression_prompt":
                prompt_content = prompt_content.replace(
                    "[<insert_emomap_keys>]", self.live2d_model.emo_str
                )

            if prompt_name == "mcp_prompt":
                continue

            persona_prompt += prompt_content

        # 注入核心記憶（關於使用者的長期記憶，跨對話累積。見 MEMORY_SYSTEM_DESIGN.md）
        # 長期記憶關閉時（long_term_memory_enabled=False）完全不注入。
        if getattr(self.character_config, "long_term_memory_enabled", True):
            from .memory_core import load_core_memory

            core_mem = load_core_memory(self.character_config.conf_uid)
            if core_mem:
                persona_prompt += (
                    "\n\n## 你對使用者的長期記憶（之前對話累積下來的，自然運用、不要生硬複述）\n"
                    + core_mem
                )

        # 系統層級「玩家語言」指令：設定後，無論輸入是什麼語言，所有角色都用玩家語言回覆。
        # 這是 system-level（套用所有角色），不寫進任何角色人設。放在最後讓它有最高權威性。
        # 正規回覆（= 字幕 + 對話紀錄 + 記憶）因此都會是玩家語言；語音另由 translate_audio 路徑
        # 翻成各角色 voice 語言（此處不動語音行為）。
        player_language = getattr(self.system_config, "player_language", "") or ""
        player_language = player_language.strip()
        if player_language:
            persona_prompt += (
                f"\n\n## Output language (system-level, overrides everything above)\n"
                f"Always write your reply in {player_language}, regardless of the "
                f"language the user speaks or types in. This applies to the entire "
                f"reply text. Do not switch languages even if the user uses another "
                f"language."
            )

        logger.debug("\n === System Prompt ===")
        logger.debug(persona_prompt)

        return persona_prompt

    async def handle_config_switch(
        self,
        websocket: WebSocket,
        config_file_name: str,
    ) -> None:
        """
        Handle the configuration switch request.
        Change the configuration to a new config and notify the client.

        Parameters:
        - websocket (WebSocket): The WebSocket connection.
        - config_file_name (str): The name of the configuration file.
        """
        try:
            new_character_config_data = None

            if config_file_name == "conf.yaml":
                # Load base config
                new_character_config_data = read_yaml("conf.yaml").get(
                    "character_config"
                )
            else:
                # Load alternative config and merge with base config.
                # Mirror character_route._safe_character_path: reject path
                # separators / non-.yaml names, then confirm the normalized path
                # stays inside config_alts_dir (blocks '../' escapes).
                characters_dir = self.system_config.config_alts_dir
                if (
                    not config_file_name
                    or os.path.basename(config_file_name) != config_file_name
                    or not config_file_name.endswith(".yaml")
                ):
                    raise ValueError("Invalid configuration file path")

                base = os.path.normpath(os.path.abspath(characters_dir))
                file_path = os.path.normpath(
                    os.path.abspath(os.path.join(characters_dir, config_file_name))
                )
                if not (file_path == base or file_path.startswith(base + os.sep)):
                    raise ValueError("Invalid configuration file path")

                alt_config_data = read_yaml(file_path).get("character_config")

                # A character override that sets conf_name but NOT character_name
                # must show ITS OWN name in chat, not inherit the base
                # character_name through the merge below. The Character Manager now
                # always writes character_name, but characters created before that
                # fix lack it on disk; default it to the override's own conf_name so
                # they render correctly without rewriting the file.
                if (
                    isinstance(alt_config_data, dict)
                    and alt_config_data.get("conf_name")
                    and not alt_config_data.get("character_name")
                ):
                    alt_config_data["character_name"] = alt_config_data["conf_name"]

                # Start with original config data and perform a deep merge
                new_character_config_data = deep_merge(
                    self.config.character_config.model_dump(), alt_config_data
                )

            if new_character_config_data:
                new_config = {
                    "system_config": self.system_config.model_dump(),
                    "character_config": new_character_config_data,
                }
                new_config = validate_config(new_config)
                await self.load_from_config(new_config)  # Await the async load
                logger.debug(f"New config: {self}")
                logger.debug(
                    f"New character config: {self.character_config.model_dump()}"
                )

                # Send responses to client
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "set-model-and-conf",
                            "model_info": self.live2d_model.model_info,
                            "conf_name": self.character_config.conf_name,
                            "conf_uid": self.character_config.conf_uid,
                        }
                    )
                )

                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "config-switched",
                            "message": f"Switched to config: {config_file_name}",
                        }
                    )
                )

                logger.info(f"Configuration switched to {config_file_name}")
            else:
                raise ValueError(
                    f"Failed to load configuration from {config_file_name}"
                )

        except Exception as e:
            logger.error(f"Error switching configuration: {e}")
            logger.debug(self)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"Error switching configuration: {str(e)}",
                    }
                )
            )
            raise e


def deep_merge(dict1, dict2):
    """
    Recursively merges dict2 into dict1, prioritizing values from dict2.
    """
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
