# config_manager/translate.py
from typing import Literal, Optional, Dict, ClassVar
from pydantic import ValidationInfo, Field, model_validator
from .i18n import I18nMixin, Description

# --- Sub-models for specific Translator providers ---


class DeepLXConfig(I18nMixin):
    """Configuration for DeepLX translation service."""

    deeplx_target_lang: str = Field(..., alias="deeplx_target_lang")
    deeplx_api_endpoint: str = Field(..., alias="deeplx_api_endpoint")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "deeplx_target_lang": Description(
            en="Target language code for DeepLX translation",
            zh="DeepLX 翻译的目标语言代码",
        ),
        "deeplx_api_endpoint": Description(
            en="API endpoint URL for DeepLX service", zh="DeepLX 服务的 API 端点 URL"
        ),
    }


class TencentConfig(I18nMixin):
    """Configuration for tencent translation service."""

    secret_id: str = Field(..., description="Tencent Secret ID")
    secret_key: str = Field(..., description="Tencent Secret Key")
    region: str = Field(..., description="Region for Tencent Service")
    source_lang: str = Field(
        ..., description="Source language code for tencent translation"
    )
    target_lang: str = Field(
        ..., description="Target language code for tencent translation"
    )

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "secret_id": Description(en="Tencent Secret ID", zh="腾讯服务的Secret ID"),
        "secret_key": Description(en="Tencent Secret Key", zh="腾讯服务的Secret Key"),
        "region": Description(en="Region for Tencent Service", zh="腾讯服务使用的区域"),
        "source_lang": Description(
            en="Source language code for tencent translation", zh="腾讯翻译的源语言代码"
        ),
        "target_lang": Description(
            en="Target language code for tencent translation",
            zh="腾讯翻译的目标语言代码",
        ),
    }


class LLMTranslateConfig(I18nMixin):
    """Configuration for LLM-based translation (OpenAI-compatible endpoint)."""

    api_endpoint: str = Field(..., alias="api_endpoint")
    model: str = Field(..., alias="model")
    target_lang: str = Field(..., alias="target_lang")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "api_endpoint": Description(
            en="OpenAI-compatible chat completions endpoint",
            zh="OpenAI 相容的 chat completions 端點",
        ),
        "model": Description(en="Model name to use for translation", zh="翻譯用的模型名稱"),
        "target_lang": Description(
            en="Target language to translate into", zh="翻譯的目標語言"
        ),
    }


# --- Main TranslatorConfig model ---


class TranslatorConfig(I18nMixin):
    """Configuration for translation services."""

    translate_audio: bool = Field(..., alias="translate_audio")
    translate_provider: Literal["deeplx", "tencent", "llm"] = Field(
        ..., alias="translate_provider"
    )
    # Display-only subtitle translation. Independent of translate_audio: the AUDIO
    # path translates tts_text for the VOICE, while this translates the reply text
    # for the on-screen SUBTITLE only (the canonical reply R, used for
    # memory/history, is never mutated). Default off = show 原文 R verbatim.
    translate_subtitle: bool = Field(default=False, alias="translate_subtitle")
    subtitle_target_lang: Optional[str] = Field(
        default=None, alias="subtitle_target_lang"
    )
    deeplx: Optional[DeepLXConfig] = Field(None, alias="deeplx")
    tencent: Optional[TencentConfig] = Field(None, alias="tencent")
    llm: Optional[LLMTranslateConfig] = Field(None, alias="llm")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "translate_audio": Description(
            en="Enable audio translation (requires DeepLX deployment)",
            zh="启用音频翻译（需要部署 DeepLX）",
        ),
        "translate_provider": Description(
            en="Translation service provider to use", zh="要使用的翻译服务提供者"
        ),
        "translate_subtitle": Description(
            en="Enable display-only subtitle translation (does not affect memory/history)",
            zh="啟用僅顯示用的字幕翻譯（不影響記憶/歷史）",
        ),
        "subtitle_target_lang": Description(
            en="Target language for the translated subtitle (label for llm / code for deeplx)",
            zh="字幕翻譯的目標語言（llm 用語言標籤、deeplx 用語言代碼）",
        ),
        "deeplx": Description(
            en="Configuration for DeepLX translation service", zh="DeepLX 翻译服务配置"
        ),
        "tencent": Description(
            en="Configuration for TenCent translation service", zh="腾讯 翻译服务配置"
        ),
    }

    @model_validator(mode="after")
    def check_translator_config(cls, values: "TranslatorConfig", info: ValidationInfo):
        translate_audio = values.translate_audio
        translate_provider = values.translate_provider

        if translate_audio:
            if translate_provider == "deeplx" and values.deeplx is None:
                raise ValueError(
                    "DeepLX configuration must be provided when translate_audio is True and translate_provider is 'deeplx'"
                )
            elif translate_provider == "tencent" and values.tencent is None:
                raise ValueError(
                    "Tencent configuration must be provided when translate_audio is True and translate_provider is 'tencent'"
                )
            elif translate_provider == "llm" and values.llm is None:
                raise ValueError(
                    "LLM configuration must be provided when translate_audio is True and translate_provider is 'llm'"
                )

        # Display-only subtitle translation reuses the SAME provider sub-block as the
        # audio path (deeplx / llm), so when it is enabled the matching block must be
        # present and a target language must be set.
        if values.translate_subtitle:
            if not (values.subtitle_target_lang or "").strip():
                raise ValueError(
                    "subtitle_target_lang must be provided when translate_subtitle is True"
                )
            if translate_provider == "deeplx" and values.deeplx is None:
                raise ValueError(
                    "DeepLX configuration must be provided when translate_subtitle is True and translate_provider is 'deeplx'"
                )
            elif translate_provider == "tencent" and values.tencent is None:
                raise ValueError(
                    "Tencent configuration must be provided when translate_subtitle is True and translate_provider is 'tencent'"
                )
            elif translate_provider == "llm" and values.llm is None:
                raise ValueError(
                    "LLM configuration must be provided when translate_subtitle is True and translate_provider is 'llm'"
                )

        return values


class TTSPreprocessorConfig(I18nMixin):
    """Configuration for TTS preprocessor."""

    remove_special_char: bool = Field(..., alias="remove_special_char")
    ignore_brackets: bool = Field(default=True, alias="ignore_brackets")
    ignore_parentheses: bool = Field(default=True, alias="ignore_parentheses")
    ignore_asterisks: bool = Field(default=True, alias="ignore_asterisks")
    ignore_angle_brackets: bool = Field(default=True, alias="ignore_angle_brackets")
    translator_config: TranslatorConfig = Field(..., alias="translator_config")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "remove_special_char": Description(
            en="Remove special characters from the input text",
            zh="从输入文本中删除特殊字符",
        ),
        "translator_config": Description(
            en="Configuration for translation services", zh="翻译服务的配置"
        ),
    }
