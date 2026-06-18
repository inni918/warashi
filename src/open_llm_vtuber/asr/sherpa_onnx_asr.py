import os
import numpy as np
import sherpa_onnx
from loguru import logger
from .asr_interface import ASRInterface
from .utils import download_and_extract, check_and_extract_local_file
import onnxruntime

# 簡轉繁（含台灣用語轉換，例：软件->軟體）。sense_voice ASR 輸出簡體，這裡轉繁體。
# lazy-init + fail-soft：opencc 初始化或轉換失敗時直接回傳原文，不讓 ASR 整個掛掉。
_s2t_converter = None
_s2t_converter_failed = False


def _to_traditional(text: str) -> str:
    """把 ASR 輸出的簡體中文轉成繁體（台灣用語）；英文／其他語言原樣通過。失敗時回傳原文。"""
    global _s2t_converter, _s2t_converter_failed
    if not text or _s2t_converter_failed:
        return text
    try:
        if _s2t_converter is None:
            import opencc

            _s2t_converter = opencc.OpenCC("s2twp")
        return _s2t_converter.convert(text)
    except Exception as e:  # noqa: BLE001 — 轉換失敗不該影響辨識結果
        _s2t_converter_failed = True
        logger.warning(f"opencc s2twp 簡轉繁失敗，改用原始辨識文字：{e}")
        return text


class VoiceRecognition(ASRInterface):
    def __init__(
        self,
        model_type: str = "paraformer",  # or "transducer", "nemo_ctc", "wenet_ctc", "whisper", "tdnn_ctc", "sense_voice", "fire_red_asr"
        encoder: str = None,  # Path to the encoder model, used with transducer
        decoder: str = None,  # Path to the decoder model, used with transducer
        joiner: str = None,  # Path to the joiner model, used with transducer
        paraformer: str = None,  # Path to the model.onnx from Paraformer
        nemo_ctc: str = None,  # Path to the model.onnx from NeMo CTC
        wenet_ctc: str = None,  # Path to the model.onnx from WeNet CTC
        tdnn_model: str = None,  # Path to the model.onnx for the tdnn model of the yesno recipe
        whisper_encoder: str = None,  # Path to whisper encoder model
        whisper_decoder: str = None,  # Path to whisper decoder model
        sense_voice: str = None,  # Path to the model.onnx from SenseVoice
        fire_red_asr_encoder: str = None,  # Path to FireRedASR encoder model
        fire_red_asr_decoder: str = None,  # Path to FireRedASR decoder model
        tokens: str = None,  # Path to tokens.txt
        hotwords_file: str = "",  # Path to hotwords file
        hotwords_score: float = 1.5,  # Hotwords score
        modeling_unit: str = "",  # Modeling unit for hotwords
        bpe_vocab: str = "",  # Path to bpe vocabulary, used with hotwords
        num_threads: int = 1,  # Number of threads for neural network computation
        whisper_language: str = "",  # Language for whisper model
        whisper_task: str = "transcribe",  # Task for whisper model (transcribe or translate)
        whisper_tail_paddings: int = -1,  # Tail padding frames for whisper model
        blank_penalty: float = 0.0,  # Penalty for blank symbol
        decoding_method: str = "greedy_search",  # Decoding method (greedy_search or modified_beam_search)
        debug: bool = False,  # Show debug messages
        sample_rate: int = 16000,  # Sample rate
        feature_dim: int = 80,  # Feature dimension
        use_itn: bool = True,  # Use ITN for SenseVoice models
        provider: str = "cpu",  # Provider for inference (cpu or cuda)
        language: str = "auto",  # SenseVoice decode-language hint: auto|zh|en|ja|ko|yue
    ) -> None:
        self.model_type = model_type
        self.encoder = encoder
        self.decoder = decoder
        self.joiner = joiner
        self.paraformer = paraformer
        self.nemo_ctc = nemo_ctc
        self.wenet_ctc = wenet_ctc
        self.tdnn_model = tdnn_model
        self.whisper_encoder = whisper_encoder
        self.whisper_decoder = whisper_decoder
        self.sense_voice: str = sense_voice
        self.fire_red_asr_encoder = fire_red_asr_encoder
        self.fire_red_asr_decoder = fire_red_asr_decoder
        self.tokens = tokens
        self.hotwords_file = hotwords_file
        self.hotwords_score = hotwords_score
        self.modeling_unit = modeling_unit
        self.bpe_vocab = bpe_vocab
        self.num_threads = num_threads
        self.whisper_language = whisper_language
        self.whisper_task = whisper_task
        self.whisper_tail_paddings = whisper_tail_paddings
        self.blank_penalty = blank_penalty
        self.decoding_method = decoding_method
        self.debug = debug
        self.SAMPLE_RATE = sample_rate
        self.feature_dim = feature_dim
        self.use_itn = use_itn
        # SenseVoice decode-language hint, driven by player_language. Clamped to the
        # set the active sense_voice model actually supports: {auto,zh,en,ja,ko,yue}.
        # Anything outside that set falls back to 'auto' (best-effort) — sense_voice
        # physically cannot recognize e.g. French/German regardless of this value.
        self.language = self._clamp_sense_voice_language(language)

        # we need to find a way to get cuda version of sherpa-onnx before we can
        # use the gpu provider.
        self.provider = provider
        if self.provider == "cuda":
            try:
                if "CUDAExecutionProvider" not in onnxruntime.get_available_providers():
                    logger.warning(
                        "CUDA provider not available for ONNX. Falling back to CPU."
                    )
                    self.provider = "cpu"
            except ImportError:
                logger.warning("ONNX Runtime not installed. Falling back to CPU.")
                self.provider = "cpu"
        logger.info(f"Sherpa-Onnx-ASR: Using {self.provider} for inference")

        self.recognizer = self._create_recognizer()

    @staticmethod
    def _clamp_sense_voice_language(language: str) -> str:
        """Map a player_language label/code to a SenseVoice-supported decode hint.

        Valid sense_voice values are exactly {auto, zh, en, ja, ko, yue}. We map the
        common BCP-47-ish labels onto them; anything outside the set degrades to
        'auto' (best-effort multilingual) instead of forcing Chinese.

        NOTE: zh-* maps to 'zh' (not 'auto') on purpose — SenseVoice auto-detect
        mis-fires on short Chinese clips (e.g. 中文 -> "Sainging the."), so keeping
        the explicit 'zh' lock preserves that robustness for Chinese players.
        sense_voice only supports zh/en/ja/ko/yue; other languages need a different
        ASR engine (e.g. faster_whisper).
        """
        if not language:
            return "auto"
        code = str(language).strip().lower()
        if not code:
            return "auto"
        if code in ("auto", "zh", "en", "ja", "ko", "yue"):
            return code
        # zh-HK / yue-* -> Cantonese; other zh-* (zh-TW / zh-CN / zh-Hant ...) -> zh.
        if code in ("zh-hk",) or code.startswith("yue"):
            return "yue"
        if code.startswith("zh"):
            return "zh"
        if code.startswith("en"):
            return "en"
        if code.startswith("ja"):
            return "ja"
        if code.startswith("ko"):
            return "ko"
        return "auto"

    def _create_recognizer(self):
        if self.model_type == "transducer":
            recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=self.encoder,
                decoder=self.decoder,
                joiner=self.joiner,
                tokens=self.tokens,
                num_threads=self.num_threads,
                sample_rate=self.SAMPLE_RATE,
                feature_dim=self.feature_dim,
                decoding_method=self.decoding_method,
                hotwords_file=self.hotwords_file,
                hotwords_score=self.hotwords_score,
                modeling_unit=self.modeling_unit,
                bpe_vocab=self.bpe_vocab,
                blank_penalty=self.blank_penalty,
                debug=self.debug,
                provider=self.provider,
            )
        elif self.model_type == "paraformer":
            recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
                paraformer=self.paraformer,
                tokens=self.tokens,
                num_threads=self.num_threads,
                sample_rate=self.SAMPLE_RATE,
                feature_dim=self.feature_dim,
                decoding_method=self.decoding_method,
                debug=self.debug,
                provider=self.provider,
            )
        elif self.model_type == "nemo_ctc":
            recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
                model=self.nemo_ctc,
                tokens=self.tokens,
                num_threads=self.num_threads,
                sample_rate=self.SAMPLE_RATE,
                feature_dim=self.feature_dim,
                decoding_method=self.decoding_method,
                debug=self.debug,
                provider=self.provider,
            )
        elif self.model_type == "wenet_ctc":
            recognizer = sherpa_onnx.OfflineRecognizer.from_wenet_ctc(
                model=self.wenet_ctc,
                tokens=self.tokens,
                num_threads=self.num_threads,
                sample_rate=self.SAMPLE_RATE,
                feature_dim=self.feature_dim,
                decoding_method=self.decoding_method,
                debug=self.debug,
                provider=self.provider,
            )
        elif self.model_type == "whisper":
            recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=self.whisper_encoder,
                decoder=self.whisper_decoder,
                tokens=self.tokens,
                num_threads=self.num_threads,
                decoding_method=self.decoding_method,
                debug=self.debug,
                language=self.whisper_language,
                task=self.whisper_task,
                tail_paddings=self.whisper_tail_paddings,
                provider=self.provider,
            )
        elif self.model_type == "tdnn_ctc":
            recognizer = sherpa_onnx.OfflineRecognizer.from_tdnn_ctc(
                model=self.tdnn_model,
                tokens=self.tokens,
                sample_rate=self.SAMPLE_RATE,
                feature_dim=self.feature_dim,
                num_threads=self.num_threads,
                decoding_method=self.decoding_method,
                debug=self.debug,
                provider=self.provider,
            )
        elif self.model_type == "sense_voice":
            if not self.sense_voice or not os.path.isfile(self.sense_voice):
                if self.sense_voice.startswith(
                    "./models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
                ):
                    logger.warning(
                        "SenseVoice model not found. Downloading the model..."
                    )

                    url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2"
                    output_dir = "./models"
                    # check the local file first before download
                    local_result = check_and_extract_local_file(url, output_dir)

                    if local_result is None:
                        logger.info("Local file not found. Downloading...")
                        download_and_extract(url, output_dir)
                    else:
                        logger.info("Local file found. Using existing file.")
                    # download_and_extract(
                    #     url="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2",
                    #     output_dir="./models",
                    # )
                else:
                    logger.critical(
                        "The SenseVoice model is missing. Please provide the path to the model.onnx file."
                    )
            recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=self.sense_voice,
                tokens=self.tokens,
                num_threads=self.num_threads,
                use_itn=self.use_itn,
                language=self.language,  # driven by player_language; clamped to {auto,zh,en,ja,ko,yue}. zh-* keeps the explicit 'zh' lock (auto-detect mis-fires on short 中文 clips).
                debug=self.debug,
                provider=self.provider,
            )
        elif self.model_type == "fire_red_asr":
            recognizer = sherpa_onnx.OfflineRecognizer.from_fire_red_asr(
                encoder=self.fire_red_asr_encoder,
                decoder=self.fire_red_asr_decoder,
                tokens=self.tokens,
                num_threads=self.num_threads,
                decoding_method=self.decoding_method,
                debug=self.debug,
                provider=self.provider,
            )
        else:
            raise ValueError(f"Invalid model type: {self.model_type}")

        return recognizer

    def transcribe_np(self, audio: np.ndarray) -> str:
        stream = self.recognizer.create_stream()
        stream.accept_waveform(self.SAMPLE_RATE, audio)
        self.recognizer.decode_streams([stream])
        return _to_traditional(stream.result.text)
