from typing import Type
from .asr_interface import ASRInterface
from loguru import logger


class ASRFactory:
    @staticmethod
    def get_asr_system(system_name: str, **kwargs) -> ASRInterface:
        asr_instance = None

        if system_name == "faster_whisper":
            from .faster_whisper_asr import VoiceRecognition as FasterWhisperASR

            asr_instance = FasterWhisperASR(
                model_path=kwargs.get("model_path"),
                download_root=kwargs.get("download_root"),
                language=kwargs.get("language"),
                device=kwargs.get("device"),
                compute_type=kwargs.get("compute_type"),
                prompt=kwargs.get("prompt", None),
            )
        elif system_name == "whisper_cpp":
            from .whisper_cpp_asr import VoiceRecognition as WhisperCPPASR

            asr_instance = WhisperCPPASR(**kwargs)
        elif system_name == "whisper":
            from .openai_whisper_asr import VoiceRecognition as WhisperASR

            asr_instance = WhisperASR(**kwargs)
        elif system_name == "fun_asr":
            from .fun_asr import VoiceRecognition as FunASR

            asr_instance = FunASR(
                model_name=kwargs.get("model_name"),
                vad_model=kwargs.get("vad_model"),
                punc_model=kwargs.get("punc_model"),
                ncpu=kwargs.get("ncpu"),
                hub=kwargs.get("hub"),
                device=kwargs.get("device"),
                language=kwargs.get("language"),
                use_itn=kwargs.get("use_itn"),
            )
        elif system_name == "azure_asr":
            from .azure_asr import VoiceRecognition as AzureASR

            asr_instance = AzureASR(
                subscription_key=kwargs.get("api_key"),
                region=kwargs.get("region"),
                languages=kwargs.get("languages", ["en-US", "zh-CN"]),
            )
        elif system_name == "groq_whisper_asr":
            from .groq_whisper_asr import VoiceRecognition as GroqWhisperASR

            asr_instance = GroqWhisperASR(
                api_key=kwargs.get("api_key"),
                model=kwargs.get("model"),
                lang=kwargs.get("lang"),
            )
        elif system_name == "sherpa_onnx_asr":
            from .sherpa_onnx_asr import VoiceRecognition as SherpaOnnxASR

            asr_instance = SherpaOnnxASR(**kwargs)
        else:
            raise ValueError(f"Unknown ASR system: {system_name}")

        # Verification check
        if not isinstance(asr_instance, ASRInterface):
            logger.warning(
                f"System '{system_name}' created instance of type {type(asr_instance).__name__}, which does not implement {ASRInterface.__name__}."
            )

        return asr_instance
