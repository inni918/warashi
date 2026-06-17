# config_manager/character.py
from pydantic import Field, field_validator
from typing import Dict, ClassVar
from .i18n import I18nMixin, Description
from .asr import ASRConfig
from .tts import TTSConfig
from .vad import VADConfig
from .tts_preprocessor import TTSPreprocessorConfig

from .agent import AgentConfig


class CharacterConfig(I18nMixin):
    """Character configuration settings."""

    conf_name: str = Field(..., alias="conf_name")
    conf_uid: str = Field(..., alias="conf_uid")
    live2d_model_name: str = Field(..., alias="live2d_model_name")
    character_name: str = Field(default="", alias="character_name")
    human_name: str = Field(default="Human", alias="human_name")
    avatar: str = Field(default="", alias="avatar")
    persona_prompt: str = Field(..., alias="persona_prompt")
    agent_config: AgentConfig = Field(..., alias="agent_config")
    asr_config: ASRConfig = Field(..., alias="asr_config")
    tts_config: TTSConfig = Field(..., alias="tts_config")
    vad_config: VADConfig = Field(..., alias="vad_config")
    tts_preprocessor_config: TTSPreprocessorConfig = Field(
        ..., alias="tts_preprocessor_config"
    )
    # Long-term (core) memory master switch. Default True preserves existing
    # behavior for confs that don't set this key. When False: skip consolidation
    # AND skip injecting core memory into the system prompt.
    long_term_memory_enabled: bool = Field(
        default=True, alias="long_term_memory_enabled"
    )
    # Core-memory character cap. Default 1500 preserves existing behavior for confs
    # that don't set this key. Bigger = remembers more but more tokens/turn + slower
    # + lossier consolidation. Bounded to [500, 8000] by the validator below.
    core_memory_max_chars: int = Field(
        default=1500, alias="core_memory_max_chars"
    )
    # OPT-IN full-history FTS5 retrieval (default OFF / lightweight). When on, each
    # user turn searches THIS character's full past transcripts for relevant snippets
    # and injects them alongside core memory. Pure-stdlib trigram FTS5, no model.
    fts_memory_enabled: bool = Field(default=False, alias="fts_memory_enabled")
    # How many past snippets to pull in per turn. Bounded to [1, 10] by the validator.
    fts_memory_top_k: int = Field(default=3, alias="fts_memory_top_k")
    # Consolidation throttle: run core-memory consolidation every N turns. Default 1
    # (every turn) preserves existing behavior. 3/5 halve+ the "tidy-up" LLM calls for
    # weak/local models. Clamped to {1,3,5} by the validator below (fail-soft -> 1).
    memory_consolidation_interval: int = Field(
        default=1, alias="memory_consolidation_interval"
    )

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "conf_name": Description(
            en="Name of the character configuration", zh="角色配置名称"
        ),
        "conf_uid": Description(
            en="Unique identifier for the character configuration",
            zh="角色配置唯一标识符",
        ),
        "live2d_model_name": Description(
            en="Name of the Live2D model to use", zh="使用的Live2D模型名称"
        ),
        "character_name": Description(
            en="Name of the AI character in conversation", zh="对话中AI角色的名字"
        ),
        "persona_prompt": Description(
            en="Persona prompt. The persona of your character.", zh="角色人设提示词"
        ),
        "agent_config": Description(
            en="Configuration for the conversation agent", zh="对话代理配置"
        ),
        "asr_config": Description(
            en="Configuration for Automatic Speech Recognition", zh="语音识别配置"
        ),
        "tts_config": Description(
            en="Configuration for Text-to-Speech", zh="语音合成配置"
        ),
        "vad_config": Description(
            en="Configuration for Voice Activity Detection", zh="语音活动检测配置"
        ),
        "tts_preprocessor_config": Description(
            en="Configuration for Text-to-Speech Preprocessor",
            zh="语音合成预处理器配置",
        ),
        "human_name": Description(
            en="Name of the human user in conversation", zh="对话中人类用户的名字"
        ),
        "avatar": Description(
            en="Avatar image path for the character", zh="角色头像图片路径"
        ),
        "long_term_memory_enabled": Description(
            en="Enable long-term (core) memory: consolidation + injection",
            zh="啟用長期（核心）記憶：整理 + 注入",
        ),
        "core_memory_max_chars": Description(
            en="Core memory size cap in characters (500-8000, default 1500). "
            "Bigger = more tokens/turn + slower + lossier consolidation.",
            zh="核心記憶字數上限（500–8000，預設 1500）。"
            "越大越能記、但每輪 token 越多、整理舊記憶更易遺漏。",
        ),
        "fts_memory_enabled": Description(
            en="Enable opt-in full-history retrieval (FTS5 trigram, off by default). "
            "Searches this character's past chats and injects relevant snippets.",
            zh="啟用全歷史深度回憶（FTS5 trigram，預設關閉）。"
            "在此角色全部過去對話裡找相關片段帶進提示詞。",
        ),
        "fts_memory_top_k": Description(
            en="How many past snippets to retrieve per turn (1-10, default 3).",
            zh="每輪取用幾段過去對話片段（1–10，預設 3）。",
        ),
        "memory_consolidation_interval": Description(
            en="Consolidate core memory every N turns (1/3/5, default 1=every turn). "
            "3/5 cut the tidy-up LLM calls roughly in half for weak/local models.",
            zh="每幾輪整理一次核心記憶（1/3/5，預設 1=每輪）。"
            "3/5 可把整理用的 LLM 呼叫省一半以上，適合弱機或本地模型。",
        ),
    }

    @field_validator("core_memory_max_chars")
    def clamp_core_memory_max_chars(cls, v):
        # Mirror memory_core._clamp_cap so conf-load and runtime agree; fail-soft to
        # the default on any bad value rather than rejecting the whole config.
        try:
            n = int(v)
        except (TypeError, ValueError):
            return 1500
        return max(500, min(8000, n))

    @field_validator("fts_memory_top_k")
    def clamp_fts_memory_top_k(cls, v):
        try:
            n = int(v)
        except (TypeError, ValueError):
            return 3
        return max(1, min(10, n))

    @field_validator("memory_consolidation_interval")
    def clamp_memory_consolidation_interval(cls, v):
        # Clamp to the allowed set {1,3,5}; fail-soft to 1 (= every turn, original
        # behavior) on any bad value rather than rejecting the whole config.
        try:
            n = int(v)
        except (TypeError, ValueError):
            return 1
        return n if n in (1, 3, 5) else 1

    @field_validator("persona_prompt")
    def check_default_persona_prompt(cls, v):
        if not v:
            raise ValueError(
                "Persona_prompt cannot be empty. Please provide a persona prompt."
            )
        return v

    @field_validator("character_name")
    def set_default_character_name(cls, v, info):
        # Empty character_name falls back to conf_name (validated earlier, so it's
        # in info.data). pydantic v2 passes a ValidationInfo, not a values dict.
        if not v:
            return info.data.get("conf_name", v)
        return v
