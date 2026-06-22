# Warashi

> A free, open-source, beginner-friendly **desktop AI companion** with a Live2D avatar — long-term memory, proactive chat, natural voice, and a sleep mode. Bring your own LLM; everything else works out of the box.

**Language:** **English** | [繁體中文](#繁體中文) | [日本語](./README.JP.md) | [한국어](./README.KR.md) | [简体中文](./README.CN.md)

![License](https://img.shields.io/badge/license-MIT%20core%20%2B%20bundled%20terms-blue)
![Built on Open-LLM-VTuber](https://img.shields.io/badge/built%20on-Open--LLM--VTuber-orange)
![Platforms](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey)

---

## What is this?

**Warashi** turns an on-screen Live2D character into an AI companion you actually talk to — it remembers you, starts conversations on its own, listens while you speak, and goes quiet when you say goodnight.

It is a **friendly re-packaging** of the excellent [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) project. We stand on its shoulders: upstream provides the rock-solid Live2D + ASR/TTS + LLM plumbing; this fork wraps it into a **download → double-click → chat** experience for non-technical users, and adds a memory system, proactive conversation, natural barge-in voice, character management, an in-app setup wizard, and a fully bilingual (English / 繁體中文) UI.

**Our principles — and what we deliberately do NOT do:**

- **Free and open source, with optional donations.** No paid tier, no paywall.
- **No mobile version.** Desktop only (macOS / Windows).
- **No model marketplace / bundled copyrighted characters.** This avoids the Live2D commercial-licensing trap — we ship only neutral free defaults; you bring your own character, voice, and LLM.

> Built on Open-LLM-VTuber. See [`NOTICE`](./NOTICE) for full attribution and component licenses, and [`README.upstream.md`](./README.upstream.md) for the original project's docs.

---

## Features

- **Long-term memory** — it remembers who you are and what you're working on, and gets to know you over time. A curated per-character "core memory" is injected into the persona; after each turn the LLM decides what's worth saving. Updates take effect immediately (no restart). Tunable memory cap.
- **Deep recall (FTS5 trigram)** — opt-in full-history search across everything you've ever said, with proper CJK support.
- **Proactive topics** — after a stretch of silence it opens a topic on its own. Optionally pull the latest AI / tech / anime / gaming news to chat about (pure stdlib helper, **no API key needed**).
- **Natural barge-in voice chat** — talk any time; you don't have to wait for the mic, and you can cut it off mid-sentence like a real conversation.
- **Sleep / do-not-disturb mode** — say "晚安" (goodnight) and it stops initiating; it resumes the next time you talk to it. The keyword is configurable.
- **Character management** — create / edit / switch / delete characters: name + persona + Live2D skin + voice + its own separate memory.
- **First-run setup wizard** — paste an API key (OpenAI / Claude / Gemini) or pick a local Ollama model. The wizard runs a quick test call before saving.
- **LLM settings tab** — paste an API key, or pick/type an Ollama model (a local model, or a cloud model served through Ollama).
- **Performance presets** — Light / Standard / High-performance, bundling ASR/TTS engine choice + memory-consolidation frequency + model keep-alive.
- **Cross-language translation** — optional subtitle / voice translation (off by default).
- **Works out of the box** — bundled sample Live2D model + free cloud TTS (edge-tts) + an auto-downloaded speech-to-text model (~1GB; a one-time, several-minute download on the very first launch). You only have to plug in an LLM.
- **Fully bilingual UI** — Traditional Chinese (zh) and English (en).

---

## Screenshots

![Warashi — your Live2D AI companion in action](assets/warashi-hero.png)

*Warashi running on the desktop: a Live2D avatar you actually talk to.*

---

## Quick start (download → double-click → chat)

The easy path — **no terminal needed.**

> **Before you start: you'll need an AI "brain" (LLM).**
> Warashi is the **body and face** — the avatar, the voice, the memory. The **brain** that actually thinks and talks is a separate AI that *you* provide. You set it up in the first-run wizard. Options, easiest first:
> - **(Recommended — free, private, runs on your own machine) A local model via Ollama.** Install the free **[Ollama](https://ollama.com)** app, then run `ollama pull qwen2.5:3b` in a terminal (a small ~1.9 GB model). Warashi's default already points to it, so it just works — **no account, no API key, no cost, works offline, and your chats never leave your computer.** Fine on a normal 8–16 GB laptop. (Want sharper replies and have the RAM? Pull a bigger model like `qwen2.5:7b` and pick it in Settings.)
> - **(Optional — better quality if your PC is weak) Ollama Cloud free tier.** Ollama can run a bigger model on *its* servers for free (with limits). Needs a free account — see **Option B** below; you must `ollama pull` the cloud model first.
> - **(Optional — best free quality) A free hosted API key.** Google AI Studio (Gemini), Cerebras, or Groq give a free key (no credit card). Best quality of the free options, but needs an account + key and your chats go to that provider. See **Option C**.
> - **(If you already pay for one) A cloud API key** from OpenAI / Claude / Gemini — top quality, a few pennies per chat. See **Option D**.

1. **Download Warashi.** Go to the [**Releases page**](https://github.com/inni918/warashi/releases/latest) and download the latest `Warashi-*.zip`, then unzip it (e.g. to your Desktop). _(Alternatively, on the main repo page click the green **`<> Code`** button → **Download ZIP**.)_
2. **Double-click the launcher** inside the unzipped folder:
   - **macOS:** `start-companion.command`
   - **Windows:** `start-companion.bat`
   - The first launch installs everything (`uv`, then dependencies) and can take a few minutes. **Leave that window open — it's the server.**
3. Your browser opens to **http://localhost:12393**. On first run a **setup wizard** appears: either **paste an API key** (OpenAI / Claude / Gemini) **or** **pick a local Ollama model**. The wizard tests your choice before saving.

   ![Warashi first-run setup wizard](assets/warashi-setup.png)

   *The first-run setup wizard, where you plug in your AI "brain".*

4. **Restart so your new brain kicks in.** Quit by **closing that same launcher/terminal window from step 2** (that stops the server), then **double-click the launcher again** to start it back up with your new LLM. (The app also notes that an LLM change "takes effect after a restart — or after switching the character once.") Then start chatting; click once on the page to enable audio.

> **macOS Gatekeeper (first launch only):** double-clicking may show *"can't be opened because it is from an unidentified developer."* This is normal for an unsigned open-source app. **Right-click** `start-companion.command` → **Open** → **Open** in the dialog. After you allow it once, double-clicking works from then on. (We don't ship a signed/notarized build — this is the free tier.)

> **Windows SmartScreen (first launch only):** double-clicking may show a blue **"Windows protected your PC"** box. This is normal for an unsigned open-source app. Click **More info** → **Run anyway**. After you allow it once, it won't ask again.

Out of the box it uses the bundled **mao** sample Live2D model and **edge-tts** (free cloud voice, no GPU needed). The first run also downloads a speech-to-text model automatically — it's roughly **~1GB**, so the **very first launch does a one-time download + extract that can take several minutes**. The launcher window may look frozen during this — it isn't, so **leave it open and let it finish**; this only happens once.

### Prefer the terminal? (advanced)

Most people should use the **Download ZIP** path above. If you're comfortable with a terminal, you can clone the repo instead. Requires **Python ≥ 3.10, < 3.13** and [`uv`](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/inni918/warashi.git && cd warashi
uv sync                  # installs dependencies
uv run run_server.py     # start the server
# open http://localhost:12393  → setup wizard → chat
```

The wizard writes your LLM choice into `conf.yaml` for you. You can still edit it by hand (see below).

---

## Starting, stopping, and auto-start

**To start it (open the "host"):**

- **Windows:** double-click **`start-companion.bat`**
- **macOS:** double-click **`start-companion.command`** — the very first time macOS may block it, so right-click the file → **Open** → **Open**; after that a normal double-click works.

A black command window opens — **that window *is* the server; keep it open while you chat.** Once it's ready it opens the app in your browser by itself (`http://localhost:12393`). Think of it as two parts: the **command window is the engine**, the **browser tab is just the screen**.

> First launch only: it downloads a ~1GB speech model and can take a few minutes — the window may look frozen but isn't. Leave it open and let it finish.

**To stop it:**

- **Close the black command window** (or press **Ctrl + C** inside it). That fully shuts the companion down.
- Closing the **browser tab** only hides the screen — the server keeps running. Close the command window to actually stop it.
- If you installed **Ollama** for a local brain, it keeps running quietly in the background. You can leave it (it's light when idle) or quit it from the system-tray (Windows) / menu-bar (macOS) icon.

**To open it again later:** just run the same launcher again — it's also your daily launcher.

**Start it automatically when your computer turns on (optional):**

- **Windows**
  1. Right-click **`start-companion.bat`** → **Create shortcut**.
  2. Press **Win + R**, type **`shell:startup`**, press **Enter** — this opens your Startup folder.
  3. Drag the shortcut into that folder. Warashi now starts at every login. *(To undo: delete the shortcut from that folder.)*

- **macOS**
  1. Open **System Settings → General → Login Items & Extensions**.
  2. Under **Open at Login**, click **+** and choose **`start-companion.command`** (or drag the file into the list).
  *(To undo: select it and click **−**.)*

Either way the command window (and then the browser) pops up on its own at login. Heads-up: a terminal window appearing every boot is normal — that's the engine starting. If you use a local Ollama brain, the Ollama app already auto-starts after you install it, so the whole companion comes up by itself.

---

## LLM setup (required)

You need **either** an API key for a cloud LLM **or** a running local LLM. A cheap model is plenty for companion chat — you do not need a flagship.

#### Option A — Local Ollama (recommended: free, private, no account)
Install [Ollama](https://ollama.com/download), then run `ollama pull qwen2.5:3b` in a terminal (~1.9 GB). Warashi's default already uses `qwen2.5:3b`, so once the download finishes it works after the next restart — no API key, no account, no cloud cost, fully offline, and your chats stay on your computer. Runs comfortably on a typical 8–16 GB laptop. For sharper replies, pull a bigger model (e.g. `qwen2.5:7b`) and set it in the LLM settings tab.

#### Option B — Cloud models through Ollama (free account; good if your PC is weak)
Ollama can run a *bigger* model on its own servers, so a slow computer still gets good replies. Free tier, but it needs an account and you must pull the model first:
1. Install Ollama from [ollama.com/download](https://ollama.com/download) (v0.12+).
2. Create a free account at [ollama.com](https://ollama.com), then run `ollama signin` in a terminal.
3. **Run `ollama pull gpt-oss:20b-cloud` — you must pull it before it works.** (Just typing the name in Settings is not enough.)
4. In the LLM settings tab, choose Ollama and set the model to `gpt-oss:20b-cloud`.

`gpt-oss:20b-cloud` is the lightest free-tier-friendly model; `qwen3.5:cloud` or `minimax-m3:cloud` are stronger but use up the free limits faster.

> **Honest about "free":** $0 with no credit card, just a free account — but a *light-usage* tier: one cloud model at a time, session limits that reset ~every 5 hours plus weekly limits, and Ollama doesn't publish exact numbers, so heavy chatting can hit a limit until it resets. Inference runs on **Ollama's servers**, so don't send anything you want kept fully private. Cloud models are in preview — **confirm it answers once before relying on it.**

#### Option C — Free hosted API key (Gemini / Cerebras / Groq)
The best chat quality of the free options. Make a free account (no credit card), create an API key, and paste it in the LLM settings tab with the matching base URL:
- **Google AI Studio (Gemini):** `https://generativelanguage.googleapis.com/v1beta/openai/` — generous free tier; note Google may use free-tier chats to improve its products.
- **Cerebras:** `https://api.cerebras.ai/v1` — very fast, ~1M tokens/day free (short context window on the free tier).
- **Groq:** `https://api.groq.com/openai/v1` — very fast, with daily token caps.

Use a current model name from each provider's docs. Your chats go to that provider, and free tiers have rate limits.

#### Option D — Paid cloud API key (OpenAI / Claude / Gemini)
If you already pay for one, paste the key in the wizard. Highest quality; a small model is typically just pennies per chat.

### ⚠️ Reasoning ("thinking") models are NOT supported

Reasoning models such as **`glm-4.7:cloud`** put their answer in a separate `reasoning` field and leave the normal `content` field **empty**. This app reads only `content`, so a reasoning model will show up as a **blank reply** — and since there's nothing to read aloud, **no voice either**.

**Recommendation:** pick a normal (non-reasoning) chat model. A small, fast model gives a more natural, lower-latency companion anyway.

> Manual edit: the LLM config lives under `character_config → agent_config → llm_configs → openai_compatible_llm` in `conf.yaml`. Comments in the file show how to point at OpenAI / Claude / Gemini with your own key. Restart the launcher after editing.

---

## Other settings

### Memory (core + deep recall)
On by default. Each character keeps its own memory at `chat_history/<conf_uid>/core_memory.md` — persona-injected core memory plus per-turn LLM consolidation (the model decides what to keep). Opt-in **FTS5 trigram deep recall** searches your full history when you want longer-term memory. Tune the memory cap in settings.

### Characters
Create / edit / switch / delete characters in the app — each has its own name, persona, Live2D skin, voice, and **separate memory**. To add your own Live2D model, drop it under `live2d-models/<name>/`, add an entry in `model_dict.json`, and select it. **Do not commit copyrighted character models to a public repo.**

#### More characters (optional)
For licensing safety, Warashi bundles only **3 free Live2D Original Characters** (`mao_pro`, `haru`, `hiyori`). Want more — including the male butler character **Natori**? You can download free official Live2D sample models yourself from the official page and drop them in. Get them from **[Live2D's sample models page](https://www.live2d.com/en/learn/sample/)** under Live2D's own license — we don't redistribute them. See [`docs/add-live2d-character.md`](docs/add-live2d-character.md) for the how-to.

### Performance presets
**Light / Standard / High-performance** presets bundle the ASR/TTS engine choice, memory-consolidation frequency, and model keep-alive. Pick Light on a modest machine, High-performance if you have the hardware.

### Proactive topics & news
The companion opens topics after idle time. Optionally refresh those topics with current headlines via the bundled news helper (`scripts/news_topics.py`) — pure stdlib, no API key — and schedule it (cron / launchd / Task Scheduler), e.g. every few hours.

### Sleep / quiet mode
Say "晚安" to stop it initiating; it resumes on your next message. The keyword is configurable.

### Translation
Optional cross-language subtitle/voice translation, **off by default** (`tts_preprocessor_config → translator_config` in `conf.yaml`).

### Voice
Default is **edge-tts** (free, no hardware). For a high-quality local/custom voice, run [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) as a service and point the config at it (needs a GPU or Apple Silicon). Voice-cloning a real person's voice is your legal responsibility.

---

## Guides

- [Use it from your phone / tablet (Tailscale)](docs/remote-access-tailscale.md) — reach your companion from another device, even off your home network.
- [Custom voice with GPT-SoVITS](docs/custom-voice-gpt-sovits.md) — give your character a cloned or custom voice.
- [Add your own Live2D character](docs/add-live2d-character.md) — drop a model in and switch to it.

## Credits & license

This project would not exist without the upstream work it builds on. Please **star and support [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)** too.

- **Upstream:** [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) — its server-side code is MIT, Copyright (c) 2025 Yi-Ting Chiu.
- **This fork's additions** (memory, proactive topics, barge-in, quiet mode, character management, setup wizard, performance presets, bilingual UI) — MIT.
- **Bundled web frontend** — the compiled web bundle in `frontend/` is the Open-LLM-VTuber-Web frontend, under the **Open-LLM-VTuber License 1.0** (Apache-2.0 + additional conditions). Free, non-commercial use and redistribution is permitted; commercial rebranding, paid hosting/SaaS, or embedding in a paid product needs a separate commercial license from the Open-LLM-VTuber org. This fork is free and non-commercial, which the license permits. See [`NOTICE`](./NOTICE).
- **Live2D Cubism & bundled sample models** — the bundled **mao_pro** / **haru** / **hiyori** models are Live2D Inc. sample data, used under the **Live2D Free Material License** (see [`LICENSE-Live2D.md`](./LICENSE-Live2D.md)). Required attribution:
  > This content uses sample data owned and copyrighted by Live2D Inc.

  They are bundled **unmodified** as a free default. **For any paid/commercial build, replace them** with your own CC0 / licensed / commissioned model.
- **Other components** (see [`NOTICE`](./NOTICE) for each license): GPT-SoVITS (MIT, optional TTS), sherpa-onnx (Apache-2.0, ASR engine — the SenseVoice model has its own license; or use Whisper), Silero VAD (MIT), edge-tts (uses Microsoft's online TTS service), DeepLX (unofficial DeepL endpoint — use the official DeepL API for production).

**Do not ship copyrighted characters, artwork, voices, or trained voice models.** This repo ships only neutral defaults; bring your own.

### License

This fork's own source code is released under the **MIT License**, on top of Open-LLM-VTuber's MIT-licensed server code (Copyright (c) 2025 Yi-Ting Chiu). However, **the whole project is not simply MIT**: the bundled compiled web frontend in `frontend/` is under the **Open-LLM-VTuber License 1.0** (Apache-2.0 + additional conditions), and the bundled Live2D sample models carry their own Live2D terms. See [`LICENSE`](./LICENSE), [`NOTICE`](./NOTICE), and [`LICENSE-Live2D.md`](./LICENSE-Live2D.md) for the full, accurate picture.

---

## Support this project

This is a free, open-source project — no paywall. If it's useful to you, a tip is appreciated but never required:

- **Ko-fi:** [ko-fi.com/leonhsueh](https://ko-fi.com/leonhsueh)
- **GitHub Sponsors:** coming soon

And please support the upstream project this is built on — [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber).

---

## Contributing

Issues and pull requests are welcome.

- File bugs and feature ideas in **Issues**.
- For code changes, open a **Pull Request** with a clear description.
- Please **do not** add copyrighted characters, artwork, voices, or trained voice models — keep the repo shippable as neutral defaults only.

---
---

# 繁體中文

**語言：** [English](#warashi) | **繁體中文** | [日本語](./README.JP.md) | [한국어](./README.KR.md) | [简体中文](./README.CN.md)

## 這是什麼？

**Warashi** 把一個 Live2D 角色變成你真的會去聊天的 AI 桌面陪伴：它記得你、會自己開話題、你說話時它會聽、你說「晚安」它就安靜下來。

它是把優秀的開源專案 [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) 重新打包成**對小白友善**的版本。我們站在它的肩膀上：上游提供穩定的 Live2D + 語音辨識/合成 + LLM 底層，這個 fork 則把它包成「**下載 → 雙擊 → 開聊**」的體驗，並加上長期記憶、主動話題、自然插話語音、角色管理、首次啟動設定精靈，以及完整的中英雙語介面。

**我們的原則 — 以及我們刻意不做的事：**

- **免費開源 + 捐款**：沒有付費版、沒有付費牆。
- **不做手機版**：只做桌面（macOS / Windows）。
- **不做模型市集、不附帶有版權的角色**：藉此避開 Live2D 商用授權的陷阱 — 我們只附中性的免費預設，角色、語音、LLM 都由你自己帶。

> 本專案建構於 Open-LLM-VTuber 之上。完整致謝與各元件授權見 [`NOTICE`](./NOTICE)，原專案文件保留於 [`README.upstream.md`](./README.upstream.md)。

## 功能亮點

- **長期記憶**：它會記得你是誰、你在忙什麼，並隨時間越來越了解你。每個角色有一份「核心記憶」注入人設；每輪結束後由 LLM 決定哪些值得存下來。更新即時生效，不用重啟。記憶上限可調。
- **深度回想（FTS5 trigram）**：可選開啟，全歷史搜尋你說過的每句話，完整支援中日韓文字。
- **主動話題**：沉默一段時間後它會自己開話題。可選擇抓最新的 AI／科技／動漫／遊戲新聞來聊（純標準函式庫，**不需要 API key**）。
- **自然插話語音對話**：隨時都能開口，不必等麥克風，也能像真人對話一樣中途打斷它。
- **睡眠／勿擾模式**：說「晚安」它就停止主動發話，下次你跟它說話時恢復。關鍵字可改。
- **角色管理**：建立／編輯／切換／刪除角色 — 名稱＋人設＋Live2D 皮＋語音＋各自獨立的記憶。
- **首次啟動設定精靈**：貼上 API key（OpenAI／Claude／Gemini）或選本地 Ollama 模型，存檔前會先做一次測試呼叫。
- **LLM 設定分頁**：貼上 API key，或選擇／手動填入一個 Ollama 模型（本地模型，或透過 Ollama 提供的雲端模型）。
- **效能預設**：輕量／標準／高效能三檔，一鍵搭配好 ASR/TTS 引擎＋記憶整理頻率＋模型常駐。
- **跨語言翻譯**：可選的字幕／語音翻譯（預設關閉）。
- **開箱即用**：內建範例 Live2D 模型＋免費雲端語音（edge-tts）＋自動下載的語音辨識模型（約 1GB，僅在第一次啟動時下載一次、需數分鐘），你只要插上一個 LLM。
- **完整中英雙語介面**：繁體中文（zh）與英文（en）。

## 截圖

![Warashi — 你的 Live2D AI 陪伴實際運作畫面](assets/warashi-hero.png)

*Warashi 在桌面上運作：一個你真的會去聊天的 Live2D 角色。*

## 快速開始（下載 → 雙擊 → 開聊）

最簡單的路徑，**完全不用終端機。**

> **開始前先準備好：你需要一顆 AI「大腦」（LLM）。**
> Warashi 是**身體和臉** — 角色外型、聲音、記憶都有了。但真正會思考、會講話的**大腦**，是一個另外的 AI，要由**你**來提供。你會在首次啟動精靈裡設定它。選項由簡到繁：
> - **（推薦 — 免費、私密、跑在你自己的電腦上）透過 Ollama 用本地模型。** 安裝免費的 **[Ollama](https://ollama.com)** app，然後在終端機執行 `ollama pull qwen2.5:3b`（一個約 1.9 GB 的小模型）。Warashi 的預設本來就指向它，所以直接就能用 — **不用帳號、不用 API key、零費用、可離線、而且你的對話永遠不會離開你的電腦。** 一般 8–16 GB 的筆電就跑得動。（想要更聰明的回覆、記憶體也夠？拉一個更大的模型，例如 `qwen2.5:7b`，再到設定裡選它。）
> - **（選用 — 電腦較弱時品質更好）Ollama Cloud 免費方案。** Ollama 可以在*它的*伺服器上免費跑一個更大的模型（有額度限制）。需要一個免費帳號 — 見下方**方案 B**；你必須先 `ollama pull` 那個雲端模型。
> - **（選用 — 免費中品質最好）免費的雲端 API key。** Google AI Studio（Gemini）、Cerebras 或 Groq 提供免費 key（免綁信用卡）。免費選項中品質最好，但需要帳號 + key，而且你的對話會送到該供應商。見**方案 C**。
> - **（如果你本來就有付費的）雲端 API key**：來自 OpenAI／Claude／Gemini — 頂級品質，一次聊天幾分錢。見**方案 D**。

1. **下載 Warashi。** 到 [**Releases 頁面**](https://github.com/inni918/warashi/releases/latest) 下載最新的 `Warashi-*.zip`，然後解壓縮（例如解到桌面）。_（或者在 repo 主頁點綠色 **`<> Code`** 按鈕 → **Download ZIP**。）_
2. **雙擊資料夾裡的啟動器**：
   - **macOS：** `start-companion.command`
   - **Windows：** `start-companion.bat`
   - 第一次啟動會自動安裝所有東西（先 `uv`，再相依套件），可能要幾分鐘。**那個視窗別關，它就是伺服器本體。**
3. 瀏覽器會自動開到 **http://localhost:12393**。第一次會出現**設定精靈**：**貼上 API key**（OpenAI／Claude／Gemini），**或**選一個本地 **Ollama 模型**。精靈會先測試再存檔。

   ![Warashi 首次啟動設定精靈](assets/warashi-setup.png)

   *首次啟動的設定精靈，在這裡接上你的 AI「大腦」。*

4. **重啟一次，新的大腦才會接上。** 請**把步驟 2 那個啟動器／終端機視窗關掉**結束它（這會停掉伺服器），再**重新雙擊一次啟動器**，讓新的 LLM 接上。（app 裡也會提示，LLM 的變更「會在重啟之後生效 — 或切換一次角色之後生效」。）接著就能開始聊天；點一下頁面以解鎖音訊。

> **macOS Gatekeeper（僅第一次）：** 雙擊時可能跳出「**無法打開，因為來自未識別的開發者**」。這對未簽章的開源 app 是正常的。請對 `start-companion.command` **按右鍵 → 打開 → 打開**。允許一次之後，往後就能直接雙擊了。（我們不提供簽章／公證版本 — 這是免費版。）

> **Windows SmartScreen（僅第一次）：** 雙擊時可能跳出藍色的「**Windows 已保護您的電腦**」視窗。這對未簽章的開源 app 是正常的。請點 **其他資訊** → **仍要執行**。允許一次之後就不會再問了。

開箱使用內建的 **mao** 範例 Live2D 模型與 **edge-tts**（免費雲端語音，不需顯卡）。第一次啟動也會自動下載一個語音辨識模型 —— 它大約 **1GB**，所以**第一次啟動會做一次性的下載＋解壓，可能要好幾分鐘**。這段期間啟動器視窗看起來像卡住了，其實沒有，**請別關掉、讓它跑完**；這只會發生一次。

### 習慣用終端機？（進階）

大多數人用上面的 **Download ZIP** 路徑就好。如果你熟悉終端機，也可以改用 clone 取得專案。需要 **Python ≥ 3.10、< 3.13** 與 [`uv`](https://github.com/astral-sh/uv)。

```bash
git clone https://github.com/inni918/warashi.git && cd warashi
uv sync                  # 安裝相依套件
uv run run_server.py     # 啟動伺服器
# 開 http://localhost:12393  → 設定精靈 → 開聊
```

## 開啟、關閉、開機自動啟動

**怎麼開（啟動「主機」）：**

- **Windows：** 雙擊 **`start-companion.bat`**
- **macOS：** 雙擊 **`start-companion.command`** —— 第一次系統可能會擋，對檔案按右鍵 → **打開** → 再按一次 **打開**；之後正常雙擊就行。

會跳出一個黑色命令視窗 —— **那個視窗就是伺服器，聊天期間要一直開著。** 等它準備好，會自己用瀏覽器打開 app（`http://localhost:12393`）。可以這樣想：**命令視窗是引擎，瀏覽器分頁只是畫面。**

> 僅限第一次啟動：會下載約 1GB 的語音模型、要等幾分鐘，視窗看起來像卡住其實沒有 —— 讓它開著跑完即可。

**怎麼關：**

- **關掉那個黑色命令視窗**（或在裡面按 **Ctrl + C**），角色就完全停止。
- 只關**瀏覽器分頁**只是隱藏畫面，伺服器還在跑；要真的停掉請關命令視窗。
- 若你裝了 **Ollama** 跑本地大腦，它會在背景持續執行。閒置時很省，可以不管；想關就從工作列（Windows）／選單列（macOS）的圖示 Quit。

**之後要再開：** 再執行同一個啟動器即可（它也是你的日常啟動器）。

**讓它在電腦開機時自動啟動（選配）：**

- **Windows**
  1. 對 **`start-companion.bat`** 按右鍵 → **建立捷徑**。
  2. 按 **Win + R**，輸入 **`shell:startup`**，按 **Enter** —— 會打開「啟動」資料夾。
  3. 把捷徑拖進那個資料夾。以後每次登入都會自動開啟。*（要取消：把該捷徑從資料夾刪掉。）*

- **macOS**
  1. 打開 **系統設定 → 一般 → 登入項目與擴充功能**。
  2. 在 **登入時開啟** 下按 **+**，選 **`start-companion.command`**（或把檔案拖進清單）。
  *（要取消：選取它後按 **−**。）*

兩種方式都會在登入時自動跳出命令視窗（接著是瀏覽器）。提醒：每次開機會跳出一個終端機視窗是正常的，那就是引擎在啟動。若你用本地 Ollama 大腦，Ollama 裝好後本來就會開機自啟，所以整套會自己起來。

## LLM 設定（必做）

你需要**擇一**：雲端 LLM 的 API key，**或**一個本地 LLM。陪伴聊天用便宜的模型就很夠，不需要旗艦級。

#### 方案 A — 本地 Ollama（推薦：免費、私密、不用帳號）
安裝 [Ollama](https://ollama.com/download)，然後在終端機執行 `ollama pull qwen2.5:3b`（約 1.9 GB）。Warashi 的預設本來就用 `qwen2.5:3b`，所以下載完成後、下次重啟就能用 —— 不用 API key、不用帳號、零雲端費用、完全離線，而且你的對話都留在你的電腦上。一般 8–16 GB 的筆電就跑得很順。想要更聰明的回覆，可以拉一個更大的模型（例如 `qwen2.5:7b`），再到 LLM 設定分頁裡選它。

#### 方案 B — 透過 Ollama 用雲端模型（免費帳號；電腦較弱時很適合）
Ollama 可以在它自己的伺服器上跑一個*更大的*模型，所以慢的電腦也能得到不錯的回覆。免費方案，但需要一個帳號、而且你必須先把模型拉下來：
1. 從 [ollama.com/download](https://ollama.com/download) 安裝 Ollama（v0.12+）。
2. 到 [ollama.com](https://ollama.com) 開一個免費帳號，然後在終端機執行 `ollama signin`。
3. **執行 `ollama pull gpt-oss:20b-cloud` —— 必須先拉下來才能用。**（只在設定裡填名字是不夠的。）
4. 在 LLM 設定分頁選 Ollama，把模型設成 `gpt-oss:20b-cloud`。

`gpt-oss:20b-cloud` 是最適合免費額度的輕量模型；`qwen3.5:cloud` 或 `minimax-m3:cloud` 更強，但會更快用掉免費額度。

> **誠實說明「免費」：** 完全 $0、免綁信用卡，只要一個免費帳號 —— 但屬於「輕量使用」等級：一次只能跑一個雲端模型，session 額度每約 5 小時重置一次、外加每週額度，而且 Ollama 沒有公布確切數字，所以聊太多可能會碰到額度上限、要等重置。運算跑在 **Ollama 的伺服器上**，所以不要傳你想完全保密的內容。雲端模型還在 preview 階段 —— **依賴它之前，先確認它真的能回一次。**

#### 方案 C — 免費的雲端 API key（Gemini／Cerebras／Groq）
免費選項中聊天品質最好。開一個免費帳號（免綁信用卡），建立一把 API key，到 LLM 設定分頁貼上 key 並填對應的 base URL：
- **Google AI Studio（Gemini）：** `https://generativelanguage.googleapis.com/v1beta/openai/` —— 免費額度大方；注意 Google 可能會用免費方案的對話來改進它的產品。
- **Cerebras：** `https://api.cerebras.ai/v1` —— 很快，每天約 1M token 免費（免費方案的 context window 較短）。
- **Groq：** `https://api.groq.com/openai/v1` —— 很快，有每日 token 上限。

請用各供應商文件裡目前可用的模型名。你的對話會送到該供應商，而且免費方案有速率限制。

#### 方案 D — 付費的雲端 API key（OpenAI／Claude／Gemini）
如果你本來就有付費的，把 key 貼進精靈即可。品質最高；用小模型通常一次聊天只要幾分錢。

### ⚠️ 思考型（reasoning）模型不適用

像 **`glm-4.7:cloud`** 這類思考型模型，會把答案放在另一個 `reasoning` 欄位，而一般的 `content` 欄位是**空的**。這個 app 只讀 `content`，所以思考型模型會顯示成**空白回覆** — 沒有文字可念，**語音也不會出聲**。

**建議：** 選一個一般（非思考型）的對話模型。小而快的模型反而讓陪伴更自然、延遲更低。

## 其他設定

- **記憶（核心＋深度回想）**：預設開啟，每個角色記憶獨立存在 `chat_history/<conf_uid>/core_memory.md`，每輪由 LLM 決定要存什麼；可選開啟 **FTS5 深度回想**搜尋全歷史。記憶上限可在設定調整。
- **角色**：在 app 內建立／編輯／切換／刪除，每個角色有獨立的名稱、人設、Live2D 皮、語音與記憶。要加自己的模型，放到 `live2d-models/<name>/` 並在 `model_dict.json` 加一筆。**不要把有版權的角色模型 commit 進公開 repo。**
  - **想要更多角色（選用）**：為了授權安全，Warashi 只內建 **3 個免費的 Live2D 原創角色**（`mao_pro`、`haru`、`hiyori`）。想要更多 — 包含男管家角色 **Natori（名取）**？你可以自己到官方頁面下載免費的官方 Live2D 範例模型再放進來。請從 **[Live2D 範例模型頁面](https://www.live2d.com/en/learn/sample/)** 依 Live2D 自己的授權下載 — 我們不代為散布。作法見 [`docs/add-live2d-character.md`](docs/add-live2d-character.md)。
- **效能預設**：輕量／標準／高效能，一鍵搭好引擎、整理頻率與模型常駐。
- **主動話題與新聞**：可用 `scripts/news_topics.py`（純標準函式庫、不需 key）定時更新話題。
- **睡眠／勿擾**：說「晚安」停止主動發話，下次對話恢復，關鍵字可改。
- **翻譯**：可選的跨語言字幕／語音翻譯，預設關閉。
- **語音**：預設 edge-tts（免費、不需硬體）；要高品質本地／自訂語音可接 GPT-SoVITS（需顯卡或 Apple Silicon）。克隆真人聲音的法律責任由你自負。

## 教學

- [從手機／平板遠端使用（Tailscale）](docs/remote-access-tailscale.md) — 即使不在家，也能從別的裝置開啟你的虛擬角色。
- [用 GPT-SoVITS 自訂聲音](docs/custom-voice-gpt-sovits.md) — 讓角色用克隆或自訂的聲音說話。
- [自己加 Live2D 角色](docs/add-live2d-character.md) — 把模型放進來並切換使用。

## 致謝與授權

沒有上游就沒有這個專案，也請去 **star 並支持 [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)**。

- **上游：** [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) — 其伺服器端程式碼為 MIT，Copyright (c) 2025 Yi-Ting Chiu。
- **本 fork 新增的部分**（記憶、主動話題、插話、勿擾、角色管理、設定精靈、效能預設、雙語介面）— MIT。
- **內建前端：** `frontend/` 裡的編譯後網頁是 Open-LLM-VTuber-Web 前端，採 **Open-LLM-VTuber License 1.0**（Apache-2.0 + 額外條款）。免費、非商業的使用與再散布是被允許的；商業改名、付費託管／SaaS、或內嵌進付費產品，則需向 Open-LLM-VTuber 團隊另取商業授權。本 fork 免費且非商業，符合該授權允許的範圍。見 [`NOTICE`](./NOTICE)。
- **Live2D Cubism 與內建範例模型：** 內建的 **mao_pro** / **haru** / **hiyori** 為 Live2D Inc. 範例資料，依 **Live2D 無償提供材料授權**使用（見 [`LICENSE-Live2D.md`](./LICENSE-Live2D.md)），必須保留致謝句：
  > This content uses sample data owned and copyrighted by Live2D Inc.

  它們以**未修改**形式作為免費預設附帶。**任何付費／商用版本都必須替換**成你自己的 CC0／已授權／委託製作的模型。
- **其他元件**（各授權見 [`NOTICE`](./NOTICE)）：GPT-SoVITS（MIT，選用 TTS）、sherpa-onnx（Apache-2.0，ASR 引擎；SenseVoice 模型另有授權，或改用 Whisper）、Silero VAD（MIT）、edge-tts（使用微軟線上語音服務）、DeepLX（非官方 DeepL 端點，正式環境請改用官方 DeepL API）。

**請勿散布有版權的角色、美術、語音或訓練過的語音模型。** 本 repo 只附中性預設，其餘自己帶。

### License

本 fork 自己寫的程式碼以 **MIT 授權**釋出，建構於 Open-LLM-VTuber 同為 MIT 授權的伺服器端程式碼之上（Copyright (c) 2025 Yi-Ting Chiu）。但**整個專案並非單純的 MIT**：`frontend/` 裡內建的編譯後網頁前端採 **Open-LLM-VTuber License 1.0**（Apache-2.0 + 額外條款），而內建的 Live2D 範例模型另有其 Live2D 授權條款。完整且準確的內容見 [`LICENSE`](./LICENSE)、[`NOTICE`](./NOTICE) 與 [`LICENSE-Live2D.md`](./LICENSE-Live2D.md)。

## 支持本專案

這是免費開源專案，沒有付費牆。如果它對你有幫助，歡迎（但絕非必須）小額贊助：

- **Ko-fi:** [ko-fi.com/leonhsueh](https://ko-fi.com/leonhsueh)
- **GitHub Sponsors:** 即將開放

也請支持本專案所建構於的上游 — [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)。

## 貢獻指南

歡迎開 issue 與 pull request。

- bug 與功能想法請開 **Issue**。
- 程式碼變更請開 **Pull Request** 並清楚說明。
- 請**不要**加入有版權的角色、美術、語音或訓練過的語音模型，讓 repo 維持可發布的中性預設狀態。
