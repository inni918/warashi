import httpx
from loguru import logger

from .translate_interface import TranslateInterface


class GoogleTranslate(TranslateInterface):
    api_endpoint: str = "https://translation.googleapis.com/language/translate/v2"

    def __init__(self, api_key: str, target_lang: str, source_lang: str = ""):
        self.api_key = api_key
        self.target_lang = target_lang
        self.source_lang = source_lang

    def translate(self, text: str) -> str:
        if not self.api_key:
            logger.error(
                "Google Translate API key is missing. Set 'api_key' under "
                "translator_config.google in conf.yaml. Using original text."
            )
            return text

        data = {"q": text, "target": self.target_lang, "format": "text"}
        if self.source_lang:
            data["source"] = self.source_lang

        try:
            resp = httpx.post(
                self.api_endpoint, params={"key": self.api_key}, data=data
            )
            resp.raise_for_status()
            res = resp.json()
            return res["data"]["translations"][0]["translatedText"]
        except httpx.HTTPStatusError as e:
            # 400/403 from this API almost always mean a missing/invalid/unauthorized
            # key rather than a transient failure, so call that out explicitly.
            if e.response.status_code in (400, 403):
                logger.error(
                    f"Google Translate rejected the request (likely a missing or "
                    f"invalid API key): {e}. Using original text."
                )
            else:
                logger.warning(
                    f"Google Translate failed for '{text[:40]}': {e}. "
                    "Using original text."
                )
            return text
        except Exception as e:
            # Best-effort: any network/parsing failure falls back to the ORIGINAL
            # text instead of raising. A failed translation must never break the
            # whole reply.
            logger.warning(
                f"Google Translate failed for '{text[:40]}': {e}. Using original text."
            )
            return text
