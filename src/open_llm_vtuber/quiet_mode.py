"""睡眠勿擾：使用者說「晚安」後，抑制主動說話（ai-speak-signal），直到說「早安」恢復。
她仍會回應你主動的發話，只是不再主動開口。

狀態用旗標檔 chat_history/<conf_uid>/.quiet_mode 記錄（存在=勿擾中），重啟後仍保留。
"""
import os

from loguru import logger


def _path(conf_uid: str) -> str:
    return os.path.join("chat_history", conf_uid, ".quiet_mode")


def set_quiet(conf_uid: str, on: bool) -> None:
    """晚安→on（建立旗標）/ 早安→off（移除旗標）。"""
    try:
        p = _path(conf_uid)
        if on:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write("quiet")
            logger.info(f"[quiet_mode] ON（晚安，暫停主動說話）for {conf_uid}")
        elif os.path.isfile(p):
            os.remove(p)
            logger.info(f"[quiet_mode] OFF（早安，恢復主動說話）for {conf_uid}")
    except Exception as e:
        logger.warning(f"[quiet_mode] set failed for {conf_uid}: {e}")


def is_quiet(conf_uid: str) -> bool:
    """目前是否在勿擾（晚安~早安）期間。"""
    try:
        return os.path.isfile(_path(conf_uid))
    except Exception:
        return False
