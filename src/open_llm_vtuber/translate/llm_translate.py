import httpx
from loguru import logger
from .translate_interface import TranslateInterface


class LLMTranslate(TranslateInterface):
    """Translate via an OpenAI-compatible LLM endpoint (e.g. Ollama, OpenAI, Claude).

    Used to read subtitles in one language while TTS speaks another, without
    needing a dedicated translation service like DeepLX.
    """

    def __init__(self, api_endpoint: str, model: str, target_lang: str):
        self.api_endpoint = api_endpoint
        self.model = model
        self.target_lang = target_lang

    def translate(self, text: str) -> str:
        try:
            prompt = (
                f"你是翻譯器。把下面的繁體中文翻譯成自然、口語的{self.target_lang}。"
                f"這是一個 AI 角色的台詞，語氣自然口語。只輸出譯文本身，"
                f"不要任何解釋、引號、羅馬拼音或附加文字。\n\n{text}"
            )
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "stream": False,
            }
            resp = httpx.post(self.api_endpoint, json=payload, timeout=30)
            res = resp.json()["choices"][0]["message"]["content"].strip()
            if not res:
                # empty translation (e.g. reasoning model returned nothing in
                # content): fall back to the original text, same as the except
                # branch, rather than passing an empty string downstream.
                logger.warning(f"LLM translate returned empty for '{text}', using original")
                return text
            logger.info(f"LLM translate: '{text}' -> '{res}'")
            return res
        except Exception as e:
            logger.critical(f"LLM translate error '{text}'. Error: {e}")
            # fallback: 回原文，避免對話中斷
            return text
