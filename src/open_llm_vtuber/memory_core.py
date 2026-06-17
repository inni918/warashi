"""
AI 角色核心記憶（長期記憶）模組。
設計見專案根 MEMORY_SYSTEM_DESIGN.md。採常見的「核心記憶 + consolidation」兩層模式（如 MemGPT / Generative Agents）。

階段一：核心記憶（精選、注入）+ 對話結束背景整理（consolidation）。
- 存在 chat_history/<conf_uid>/core_memory.md，每個角色一份、跨對話延續。
- 注入：construct_system_prompt 把它附到 persona。
- 整理：每輪對話後背景跑 LLM，判斷有沒有值得記進核心的新資訊（write triggers），有才更新。
"""

import os
import httpx
from loguru import logger

CAP_CHARS = 1500  # 核心記憶上限「預設值」，撞上限 LLM 自行提煉合併
CAP_MIN = 500     # 可調下限（太小記不住）
CAP_MAX = 8000    # 可調上限（太大每輪 token 暴增、整理更易遺漏）

# Single source of truth for the consolidation-throttle setting:
# 每幾輪整理一次核心記憶。1 = 每輪（預設，行為與原本相同）。
# 弱機 / 本地模型設 3 或 5 可少一半以上「整理用」的 LLM 呼叫。
CONSOLIDATE_INTERVAL_DEFAULT = 1
CONSOLIDATE_INTERVAL_CHOICES = (1, 3, 5)


def _clamp_interval(v) -> int:
    """把 memory_consolidation_interval 夾到允許集合 {1,3,5}。

    任何壞值（None / 非數字 / 不在集合）一律 fail-soft 退回 1（= 每輪整理，
    最保守、不改變原本行為），確保 garbage 設定值不會讓整理悄悄停掉。
    """
    try:
        n = int(v)
    except (TypeError, ValueError):
        return CONSOLIDATE_INTERVAL_DEFAULT
    if n in CONSOLIDATE_INTERVAL_CHOICES:
        return n
    return CONSOLIDATE_INTERVAL_DEFAULT


def _clamp_cap(v) -> int:
    """把使用者/設定檔給的字數上限夾到 [CAP_MIN, CAP_MAX]。

    任何壞值（None / 非數字 / 超界）一律 fail-soft 退回預設 CAP_CHARS，
    確保 garbage 設定值不會弄壞 consolidation。
    """
    try:
        n = int(v)
    except (TypeError, ValueError):
        return CAP_CHARS
    if n < CAP_MIN:
        return CAP_MIN
    if n > CAP_MAX:
        return CAP_MAX
    return n


def _path(conf_uid: str) -> str:
    return os.path.join("chat_history", conf_uid, "core_memory.md")


def load_core_memory(conf_uid: str) -> str:
    """讀核心記憶（給 construct_system_prompt 注入）。沒有就回空字串。"""
    try:
        p = _path(conf_uid)
        if os.path.isfile(p):
            return open(p, encoding="utf-8").read().strip()
    except Exception as e:
        logger.warning(f"[core_memory] load failed for {conf_uid}: {e}")
    return ""


def core_memory_path(conf_uid: str) -> str:
    """核心記憶檔路徑（給 route 層用，不外洩內部 _path 命名）。"""
    return _path(conf_uid)


def clear_core_memory(conf_uid: str) -> bool:
    """清空（忘記）某角色的核心記憶。

    安全做法：把 core_memory.md 內容截斷成空字串，而不是刪檔（house rule 不硬刪；
    截斷後 load_core_memory 回空、注入也就沒東西）。檔案不存在視為已清空。
    回傳 True 表示清空成功（或本就沒有記憶）。
    """
    try:
        p = _path(conf_uid)
        if os.path.isfile(p):
            with open(p, "w", encoding="utf-8") as f:
                f.write("")
            logger.info(f"[core_memory] cleared for {conf_uid}")
        return True
    except Exception as e:
        logger.warning(f"[core_memory] clear failed for {conf_uid}: {e}")
        return False


def save_core_memory(conf_uid: str, content: str, cap: int = CAP_CHARS) -> bool:
    """覆寫某角色的核心記憶（給使用者在記憶分頁手動修正錯記/不想要的內容用）。

    安全做法沿用 clear_core_memory / consolidate_core_memory：os.makedirs 補目錄、
    plain ``open("w")`` 覆寫整份 core_memory.md。``content`` 為 None 視為空字串。

    ``cap``：核心記憶字數上限（預設 CAP_CHARS=1500，由呼叫端從 conf 讀 per-角色設定
    傳進來，這裡再夾一次界 fail-soft）。**手動編輯採「照存但記 warning」策略**（不截斷）：
    使用者明確打的字尊重原樣寫入，只在超過 cap 時記一筆 warning 提醒；下一輪 consolidation
    本來就會把過長內容合併提煉回 cap 內。這比偷偷截斷少掉使用者一半句子來得不意外。

    回傳 True 表示寫入成功。
    """
    try:
        text = (content or "").strip()
        cap = _clamp_cap(cap)
        if len(text) > cap:
            logger.warning(
                f"[core_memory] manual save for {conf_uid} exceeds cap "
                f"({len(text)} > {cap} chars); stored as-is, will be compacted "
                "on next consolidation"
            )
        p = _path(conf_uid)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        logger.info(f"[core_memory] manually saved for {conf_uid} ({len(text)} chars)")
        return True
    except Exception as e:
        logger.warning(f"[core_memory] save failed for {conf_uid}: {e}")
        return False


async def consolidate_core_memory(
    conf_uid: str,
    user_input: str,
    ai_response: str,
    base_url: str,
    model: str,
    cap: int = CAP_CHARS,
    api_key: str = "",
) -> None:
    """對話一輪後背景跑（fire-and-forget，不阻塞使用者）：
    叫 LLM 依 write triggers 判斷這輪有沒有值得記的，有才更新 core_memory.md。

    ``cap``：核心記憶字數上限（預設 CAP_CHARS=1500）。由呼叫端從 conf 讀 per-角色設定
    傳進來；這裡再夾一次界（fail-soft 退回 1500），確保壞設定值不會弄壞整理。

    ``api_key``：對話用 LLM 的 API key（由呼叫端從 conf 同源傳進來）。非空且非 'ollama'
    佔位時才帶 Authorization header；空字串／'ollama' 維持本機 Ollama 相容（不帶 header）。
    """
    try:
        if not user_input or not user_input.strip():
            return
        cap = _clamp_cap(cap)
        current = load_core_memory(conf_uid)
        prompt = (
            "你是這個 AI 角色的記憶管理員。根據下面這輪對話，維護一份「關於使用者的長期記憶」。\n\n"
            "規則（嚴格遵守）：\n"
            "- 只記這些：使用者的事實（身分／職業／正在做的事）、偏好與習慣、希望被怎麼稱呼、重要事件或對話結論。\n"
            "- 絕不記這些：一次性閒聊、寒暄、問候、沒有新資訊的對話、AI 自己說的話。\n"
            "- 用簡短條列，每條一行，繁體中文，台灣用語。\n"
            "- 如果這輪對話沒有任何值得記的新資訊，就原封不動輸出現有記憶，一個字都不要改。\n"
            f"- 總長度控制在 {cap} 字元內；若超過，合併或提煉舊條目（保留最關鍵、刪掉過時細節）。\n\n"
            f"現有記憶：\n{current or '（目前還沒有任何記憶）'}\n\n"
            f"這輪對話：\n使用者說：{user_input}\nAI 回：{ai_response}\n\n"
            "請輸出「更新後的完整記憶內容」本身，不要任何解釋、前言或標題。"
        )
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "stream": False,
        }
        # API key：非空且非 'ollama' 佔位才帶 Authorization header
        # （空字串／'ollama' 維持本機 Ollama 相容、不帶 header）。
        headers = None
        if api_key and api_key != "ollama":
            headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            new_mem = r.json()["choices"][0]["message"]["content"].strip()
        # 防呆：LLM 可能回空或加引號
        new_mem = new_mem.strip().strip("`").strip()
        if new_mem and new_mem != current and len(new_mem) < int(cap * 1.5):
            os.makedirs(os.path.dirname(_path(conf_uid)), exist_ok=True)
            with open(_path(conf_uid), "w", encoding="utf-8") as f:
                f.write(new_mem)
            logger.info(f"[core_memory] updated for {conf_uid} ({len(new_mem)} chars)")
    except Exception as e:
        logger.warning(f"[core_memory] consolidate failed for {conf_uid}: {e}")
