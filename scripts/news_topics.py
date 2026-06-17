#!/usr/bin/env python3
"""抓多分類最新新聞（國際/台灣/財經/科技/AI/動漫/電玩...，可自訂），寫進角色的主動說話 prompt。

設計：她主動說話用的 prompts/utils/proactive_speak_prompt.txt 是後端每次觸發都重讀的
（conversation_handler load_util，無快取），所以這支腳本直接把「人設指示 + 最新新聞清單」
覆寫進那個檔。她被觸發時就看到最新新聞、挑一則用自己口吻聊。

純 stdlib（urllib），不用 LLM、不裝套件。

兩種用法：
1. CLI / 排程：`python scripts/news_topics.py` 直接重寫 prompt（人設 + 新聞），向後相容舊 cron。
2. 被 import：app 內的「主動話題」設定頁與背景排程 import
   `fetch_news_blocks()` / `compose_content()`，共用同一份抓取 + 組裝邏輯，不重寫 RSS。

抓失敗就只寫人設指示（改聊自己的好奇），不會留下壞檔。
"""
import datetime
import html
import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_PATH = os.path.join(ROOT, "prompts", "utils", "proactive_speak_prompt.txt")
# 「已端出過的新聞標題」永續記錄，用來去重避免同一則時事一直重複端給她。
SEEN_PATH = os.path.join(ROOT, "prompts", "utils", "seen_news.json")

# seen 汰舊上限：同時用「筆數上限」與「時間窗」兩道把關，避免無限膨脹。
SEEN_MAX = 500  # 最多保留幾筆（超過淘汰最舊）
SEEN_TTL_DAYS = 14  # 超過幾天的記錄淘汰

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
# 主題 -> Google News 查詢字的「查詢提示對照」（繁中、台灣）。
# 統一話題模型下，UI 不再有固定分類勾選；這份對照只當「精選關鍵字 -> 更好的查詢字」
# 提示用（例如 AI -> AI 人工智慧）。任何沒列在這裡的主題字串，會直接被當成自己的
# Google News 查詢字抓。topics_route.py 透過 import 取用這份對照（mapping.get）。
CATEGORIES = [
    ("國際", "國際 新聞"),
    ("台灣", "台灣"),
    ("財經", "財經 股市"),
    ("科技", "科技"),
    ("AI", "AI 人工智慧"),
    ("科學", "科學"),
    ("動漫", "動漫 新番"),
    ("電玩", "電玩 遊戲"),
    ("娛樂", "娛樂"),
    ("電影", "電影"),
    ("音樂", "音樂"),
    ("體育", "體育"),
    ("健康", "健康"),
    ("生活", "生活"),
    ("美食", "美食"),
    ("旅遊", "旅遊"),
    ("汽車", "汽車"),
    ("時尚", "時尚"),
]
PER_CAT = 4  # 每類取幾則

INSTRUCTION = """使用者已經有一段時間沒講話了。請你（這個 AI 角色）主動開口找他聊，自然地打破沉默。
你可以從下面這些最近的新聞裡挑「一則」你覺得有趣的，用你自己的角度聊起來（拋個看法、問他怎麼看）；也可以不聊新聞，改聊一個冷知識、突然的好奇、或關心他在忙什麼。
如果下面沒有「最近的新聞」這個區塊（代表目前沒有新鮮時事），就用你自己的知識、或從上面的主題清單自由發揮、或單純關心他最近過得如何，別硬去重複講舊話題、也不要卡住——一定要開口講點什麼。
不要每次都聊新聞、不要像在念稿或報新聞，要像朋友隨口提起。用你設定的角色口吻。只說一到兩句、口語、每次都不一樣。
不要說明你在「主動發言」，也不要提到新聞清單、系統或任何機制。直接把要講的話講出來。"""


def normalize_title(t: str) -> str:
    """把標題正規化成穩定的比對鍵：去掉「 - 來源」/「 | 來源」尾綴 + strip。

    fetch_titles 端出的標題本來就已去尾綴，但這裡再做一次，讓 seen 的比對對
    「有尾綴 / 沒尾綴」兩種寫法都成立（例如直接餵進來自舊檔的原始標題也比得到）。
    """
    s = html.unescape(str(t or "")).strip()
    for sep in (" - ", " | "):
        if sep in s:
            s = s.rsplit(sep, 1)[0].strip()
    return s


def load_seen() -> dict:
    """讀「已端出新聞標題」記錄，回傳 {normalized_title: iso_timestamp}。

    fail-soft：檔案不存在 / 壞檔 / 格式不符一律當成空 dict，不讓壞檔卡住抓新聞。
    順手做汰舊（時間窗 + 筆數上限），所以讀進來的就是已修剪過的乾淨集合。
    """
    raw = {}
    if os.path.exists(SEEN_PATH):
        try:
            with open(SEEN_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # 只收 str -> str（標題 -> 時間戳）的條目，其餘忽略。
                for k, v in data.items():
                    if isinstance(k, str) and k.strip():
                        raw[k] = v if isinstance(v, str) else ""
        except Exception as e:  # noqa: BLE001 - fail-soft：壞檔當空
            print(f"[news_topics] seen_news.json unreadable, treating as empty: {e}",
                  file=sys.stderr)
            raw = {}
    return _prune_seen(raw)


def _prune_seen(seen: dict) -> dict:
    """汰舊：先丟掉超過 SEEN_TTL_DAYS 的條目，再把總數壓到 SEEN_MAX（保留最新的）。"""
    if not seen:
        return {}
    now = datetime.datetime.now().astimezone()
    cutoff = now - datetime.timedelta(days=SEEN_TTL_DAYS)
    kept = {}
    for title, ts in seen.items():
        when = _parse_ts(ts)
        # 沒有 / 壞掉的時間戳當成「現在」保留（下次寫回會補正常時間戳）。
        if when is None or when >= cutoff:
            kept[title] = ts if isinstance(ts, str) and ts else now.isoformat(timespec="seconds")
    if len(kept) > SEEN_MAX:
        # 依時間戳由新到舊排序，留前 SEEN_MAX 筆。
        ordered = sorted(
            kept.items(),
            key=lambda kv: (_parse_ts(kv[1]) or now),
            reverse=True,
        )
        kept = dict(ordered[:SEEN_MAX])
    return kept


def _parse_ts(ts) -> "datetime.datetime | None":
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.datetime.fromisoformat(ts)
    except Exception:  # noqa: BLE001
        return None
    # 統一成 aware，方便和 aware 的 cutoff 比較。
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def save_seen(seen: dict) -> None:
    """原子寫回 seen_news.json（temp + os.replace）。寫前再修剪一次保險。"""
    seen = _prune_seen(seen)
    os.makedirs(os.path.dirname(SEEN_PATH), exist_ok=True)
    tmp_path = SEEN_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, SEEN_PATH)


def mark_seen(seen: dict, titles) -> dict:
    """把這輪真正端出的標題寫進 seen（正規化後當 key、時間戳當 value）。回傳同一個 dict。"""
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    for t in titles or []:
        key = normalize_title(t)
        if key:
            seen[key] = now
    return seen


def fetch_titles(query: str, limit: int) -> list:
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = r.read()
    root = ET.fromstring(data)
    titles = []
    for item in root.iterfind(".//item"):
        t = item.findtext("title") or ""
        t = html.unescape(t).strip()
        if not t:
            continue
        # Google News 標題格式為「標題 - 來源」或「標題 | 來源」，去掉尾端來源讓她念起來自然
        for sep in (" - ", " | "):
            if sep in t:
                t = t.rsplit(sep, 1)[0].strip()
        if t and t not in titles:
            titles.append(t)
        if len(titles) >= limit:
            break
    return titles


def fetch_news_blocks(categories=CATEGORIES, per_cat: int = PER_CAT,
                      seen=None, new_titles=None):
    """抓多個分類的新聞，回傳 (blocks, got_any)。

    blocks 是一串「分類標籤:\n- 標題\n- 標題」的字串清單；got_any 表示至少抓到一則。
    純 stdlib、不呼叫任何 LLM、不需具備網路搜尋能力的模型——這支自己用 Google News RSS 抓。
    跨分類去重。任一分類抓失敗只略過該類、不中斷其他類（鏡像舊 main() 行為）。

    categories 可傳 [(label, query), ...] 子集以只抓使用者勾選的分類。

    去重新增「跨輪持久去重」：
    - seen：傳入「已端出過標題」的記錄（dict 或 set，比對前一律 normalize）。命中的標題
      會被排除，不再重複端出。
    - new_titles：若傳入 list，這輪真正端出的（去尾綴後）標題會 append 進去，讓呼叫端寫回
      seen 永續記錄。
    兩者皆 None 時行為和舊版完全一致（只做單次跨分類去重），向後相容。
    """
    # 把 seen 正規化成一組可快速比對的鍵集合。
    seen_keys = set()
    if isinstance(seen, dict):
        seen_keys = {normalize_title(k) for k in seen.keys()}
    elif isinstance(seen, (set, list, tuple)):
        seen_keys = {normalize_title(k) for k in seen}

    blocks = []
    got_any = False
    batch_seen = set()  # 跨類去重，避免同一則新聞出現在多個分類（本輪內）
    for label, query in categories:
        try:
            # 多抓一些緩衝：被 seen 過濾掉一批後仍湊得齊 per_cat 筆新料。
            candidates = fetch_titles(query, per_cat + 8)
        except Exception as e:
            print(f"[news_topics] fetch failed for {label}: {e}", file=sys.stderr)
            candidates = []
        titles = []
        for t in candidates:
            key = normalize_title(t)
            if not key or key in batch_seen:
                continue
            batch_seen.add(key)
            if key in seen_keys:
                continue  # 跨輪去重：之前端過的標題不再端
            titles.append(t)
            if isinstance(new_titles, list):
                new_titles.append(t)
            if len(titles) >= per_cat:
                break
        if titles:
            got_any = True
            lines = "\n".join(f"- {t}" for t in titles)
            blocks.append(f"{label}：\n{lines}")
    return blocks, got_any


def compose_content(manual_topics=None, news_blocks=None, got_any: bool = False) -> str:
    """組出要寫進 proactive_speak_prompt.txt 的完整內容。

    統一話題模型：manual_topics 是唯一一份「主動話題」清單，同時驅動兩種模式——
      - 新聞關閉：只附這份話題清單（她從自己的知識聊起，不抓網路）。
      - 新聞開啟：每個話題各抓一則 Google News，news_blocks 帶進「最近的新聞」區塊。
    兩種模式用的是同一份清單，差別只在 news_blocks 有沒有東西。

    一律保留人設指示（INSTRUCTION）開頭——這是「別像念稿/別提機制」的護欄，不能掉。
    話題清單非空 -> 附「你可以聊的主題」區塊。
    新聞有抓到（got_any 且 news_blocks 非空）-> 附「最近的新聞」區塊。
    都沒有 -> 只回人設指示（永不留下壞檔，鏡像舊 main() 全失敗分支）。
    """
    manual_topics = manual_topics or []
    news_blocks = news_blocks or []

    parts = [INSTRUCTION]

    manual_clean = [str(t).strip() for t in manual_topics if str(t).strip()]
    if manual_clean:
        topic_lines = "\n".join(f"- {t}" for t in manual_clean)
        parts.append(
            "【你可以聊的主題（挑一個自然聊起即可，不必全提）】\n" + topic_lines
        )

    if got_any and news_blocks:
        news = "\n\n".join(news_blocks)
        parts.append(
            "【最近的新聞（僅供參考，挑一則自然聊起即可，不必全提）】\n" + news
        )

    return "\n\n".join(parts) + "\n"


def write_prompt(content: str) -> None:
    """原子寫入 proactive_speak_prompt.txt（temp + os.replace）。"""
    os.makedirs(os.path.dirname(PROMPT_PATH), exist_ok=True)
    tmp_path = PROMPT_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, PROMPT_PATH)


def main() -> int:
    seen = load_seen()
    new_titles = []
    blocks, got_any = fetch_news_blocks(seen=seen, new_titles=new_titles)
    content = compose_content(manual_topics=None, news_blocks=blocks, got_any=got_any)
    write_prompt(content)
    # 只有真的端出新標題才寫回 seen（抓全失敗 / 全被過濾 -> 不動 seen）。
    if new_titles:
        try:
            save_seen(mark_seen(seen, new_titles))
        except Exception as e:  # noqa: BLE001 - seen 寫失敗不該擋住已寫好的 prompt
            print(f"[news_topics] save_seen failed: {e}", file=sys.stderr)
    print(
        f"[news_topics] wrote {PROMPT_PATH} ({len(content)} chars, "
        f"news={got_any}, new={len(new_titles)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
