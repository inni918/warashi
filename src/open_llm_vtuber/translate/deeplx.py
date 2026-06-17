import json
import httpx
from loguru import logger
from .translate_interface import TranslateInterface


# --------------------------------------------------------------------------- #
# Human language-name -> DeepL target-code resolver.
#
# The subtitle path stores `subtitle_target_lang` as a HUMAN-READABLE name (e.g.
# '日文', '德文') so the SAME value also works for the llm engine (which drops the
# name into its prompt). DeepL/DeepLX, however, wants a target CODE ('JA', 'DE').
# This table maps the frontend's language-name values (use-translator-settings.ts
# SUBTITLE_LANG_OPTIONS) to DeepL target codes. Keep the KEYS in sync with that
# list. Codes follow DeepL's target-language set.
#
# `resolve_deepl_target_lang` is tolerant: an already-valid code (e.g. 'JA' or
# 'EN-US') passes straight through, so a hand-edited conf.yaml that used a code
# still works.
# --------------------------------------------------------------------------- #

LANG_NAME_TO_DEEPL_CODE = {
    # original 4 (backward compatible)
    "繁體中文": "ZH-HANT",
    "日文": "JA",
    "英文": "EN-US",
    "韓文": "KO",
    # rest of DeepL's supported target languages
    "保加利亞文": "BG",
    "捷克文": "CS",
    "丹麥文": "DA",
    "德文": "DE",
    "希臘文": "EL",
    "西班牙文": "ES",
    "愛沙尼亞文": "ET",
    "芬蘭文": "FI",
    "法文": "FR",
    "匈牙利文": "HU",
    "印尼文": "ID",
    "義大利文": "IT",
    "立陶宛文": "LT",
    "拉脫維亞文": "LV",
    "挪威文": "NB",
    "荷蘭文": "NL",
    "波蘭文": "PL",
    "葡萄牙文": "PT-PT",
    "羅馬尼亞文": "RO",
    "俄文": "RU",
    "斯洛伐克文": "SK",
    "斯洛維尼亞文": "SL",
    "瑞典文": "SV",
    "土耳其文": "TR",
    "烏克蘭文": "UK",
    "簡體中文": "ZH-HANS",
    # a couple of common aliases / Simplified-Chinese spellings, just in case
    "繁体中文": "ZH-HANT",
    "简体中文": "ZH-HANS",
    "中文": "ZH",
}

# Recognised DeepL target codes (upper-cased) so a value that is ALREADY a code
# passes through untouched.
_KNOWN_DEEPL_CODES = {
    "BG", "CS", "DA", "DE", "EL", "EN", "EN-GB", "EN-US", "ES", "ET", "FI",
    "FR", "HU", "ID", "IT", "JA", "KO", "LT", "LV", "NB", "NL", "PL", "PT",
    "PT-BR", "PT-PT", "RO", "RU", "SK", "SL", "SV", "TR", "UK", "ZH",
    "ZH-HANS", "ZH-HANT", "JP",
}


def resolve_deepl_target_lang(value: str) -> str:
    """Map a stored subtitle/target language value to a DeepL target code.

    - A human language name from SUBTITLE_LANG_OPTIONS (e.g. '德文') -> its code.
    - An already-valid DeepL code (e.g. 'JA', 'EN-US') -> returned as-is (upper).
    - Anything unknown -> returned unchanged so DeepLX can decide (and the caller's
      existing fail-soft path handles a rejection). We never raise here.
    """
    if value is None:
        return value
    v = str(value).strip()
    if not v:
        return v
    if v in LANG_NAME_TO_DEEPL_CODE:
        return LANG_NAME_TO_DEEPL_CODE[v]
    if v.upper() in _KNOWN_DEEPL_CODES:
        return v.upper()
    return v


class DeepLXTranslate(TranslateInterface):
    api_endpoint: str = "http://127.0.0.1:1188/v2/translate"
    target_lang: str = "JP"

    def __init__(self, api_endpoint: str, target_lang: str):
        self.api_endpoint = api_endpoint
        self.target_lang = target_lang

    # translate v2 endpoint from DeepLX
    def translate(self, text: str) -> str:
        try:
            data = {"text": [text], "target_lang": self.target_lang}
            # 用 json= 讓 httpx 自動帶 Content-Type: application/json，否則 DeepLX 回 400
            req = httpx.post(url=self.api_endpoint, json=data).text
            res = json.loads(req)["translations"]
            res = " ".join([d["text"] for d in res])
        except Exception as e:
            logger.critical(f"Error translating text '{text}'. Error message: {e}")
            logger.critical(f"Response: {req}")
            raise e

        return res
