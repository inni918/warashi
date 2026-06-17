# Custom / cloned voice (GPT-SoVITS)

**Scenario:** You want your character to speak in a **custom or cloned voice** (for
example a specific character's voice) instead of the default free **edge-tts** voice.
Warashi can do this through **GPT-SoVITS**, a separate voice-synthesis service that you
run yourself.

## Prerequisites

- **A machine with a GPU or Apple Silicon.** GPT-SoVITS is a neural TTS engine; it needs
  roughly **6 GB of VRAM** on an NVIDIA GPU, or an Apple Silicon Mac. It can be the same
  computer as Warashi, or another computer on your network.
- **GPT-SoVITS installed by you.** It is **not bundled** with Warashi — you install and
  run it separately. Get it here: <https://github.com/RVC-Boss/GPT-SoVITS>
- GPT-SoVITS exposes an HTTP API, by default on **port `9880`**.

## The most important concept: who holds what

This is the part people get wrong, so read it first. The voice setup is split across
**two** programs:

| Thing | Lives in | Why |
|------|----------|-----|
| **Voice model weights** — the GPT model (`.ckpt`) and the SoVITS model (`.pth`) | **GPT-SoVITS** | They are the actual neural model; GPT-SoVITS is the program that loads and runs them. |
| **Reference audio file + its transcript** | **Warashi** (`conf.yaml`) | Every time it needs speech, Warashi calls GPT-SoVITS and has to tell it *which short reference clip to imitate* and *what that clip says*. So those go in Warashi's config. |

In short: **load the voice-pack weights into GPT-SoVITS; tell Warashi the reference clip
and its transcript.** Warashi is the *client* that asks GPT-SoVITS for audio on each
reply.

## Step-by-step

### 1. Install, start, and load your voice into GPT-SoVITS

1. Install and start the GPT-SoVITS API server (it listens on `:9880` by default).
2. For a **custom voice**, load that voice pack's **weights** into GPT-SoVITS. You do this
   **on the GPT-SoVITS side**, by either:
   - calling its `/set_gpt_weights` (the `.ckpt` GPT model) and `/set_sovits_weights`
     (the `.pth` SoVITS model) endpoints, **or**
   - editing GPT-SoVITS's own `tts_infer.yaml` so it loads those weights at startup.

   (Refer to the GPT-SoVITS docs for the exact endpoint/config details — those belong to
   that project, not to Warashi.)

### 2. In Warashi: pick GPT-SoVITS and fill the two panel fields

Open Warashi → **Settings → Performance / Hardware (效能/硬體)** → **TTS engine**:

1. Set the **TTS engine** to **GPT-SoVITS** (`gpt_sovits_tts`). The other choice is the
   default `edge_tts`.
2. Fill **Service address** (`api_url`) — where GPT-SoVITS is reachable. Default is:

   ```
   http://localhost:9880/tts
   ```

   If GPT-SoVITS runs on another computer on your network, use that machine's IP instead
   of `localhost`, e.g. `http://192.168.1.50:9880/tts`.
3. Fill **Reference audio path** (`ref_audio_path`) — the path to the short reference clip
   whose voice you want copied. This path must be valid **from GPT-SoVITS's point of
   view** (it's the program that reads the file).

> The settings panel exposes **only** these GPT-SoVITS fields: the engine selector,
> `api_url`, and `ref_audio_path`. The remaining required fields are not in the panel yet
> — set them in `conf.yaml` (next step).

### 3. Fill the remaining required fields in `conf.yaml`

Open `conf.yaml`, find the `gpt_sovits_tts` block (under `character_config` →
`tts_config`), and fill these. They are **required** for GPT-SoVITS to produce sound:

```yaml
gpt_sovits_tts:
  api_url: 'http://localhost:9880/tts'   # also settable in the panel
  text_lang: 'all_ja'                    # language of the text being spoken
  ref_audio_path: ''                     # also settable in the panel
  prompt_lang: 'ja'                      # language spoken in your reference clip
  prompt_text: ''                        # the exact words spoken in your reference clip
  text_split_method: 'cut5'              # leave as-is unless you know otherwise
  batch_size: '1'
  media_type: 'wav'
  streaming_mode: 'false'
```

The three you almost always need to set yourself:

- **`prompt_text`** — type out, **word for word**, exactly what is said in your reference
  audio clip. This is **required**; GPT-SoVITS uses it to align the reference voice.
- **`prompt_lang`** — the language spoken in the reference clip (e.g. `ja`, `zh`, `en`).
- **`text_lang`** — the language the character will actually *speak*. (Note: Warashi
  translates replies before sending them to TTS, so this is the language of the text that
  finally reaches GPT-SoVITS — the default value is `all_ja`.)

### 4. Restart Warashi

Engine and TTS changes are read when Warashi starts, so **restart it** (close and reopen)
for the new voice to take effect. The settings panel itself also tells you a restart is
required after a TTS change.

## FAQ / troubleshooting

- **No sound / TTS errors after switching?** Check, in order: (1) GPT-SoVITS is actually
  running and reachable at your `api_url`; (2) the voice weights are loaded in GPT-SoVITS;
  (3) `ref_audio_path` points to a file GPT-SoVITS can read; (4) `prompt_text` is filled
  in and matches the reference clip.
- **Key limitation — `prompt_text` is mandatory.** Leaving it blank is the most common
  cause of failure. GPT-SoVITS needs the reference clip's transcript to clone the voice.
- **Wrong-sounding language?** Make sure `prompt_lang` matches your reference clip and
  `text_lang` matches what you want spoken.
- **GPT-SoVITS on another PC?** Put that PC's IP in `api_url`, and remember
  `ref_audio_path` is resolved **on that PC**, not on the Warashi machine.
- **Want to go back to free voices?** Set the TTS engine back to **edge-tts** and restart.
- **Legal note:** cloning a real person's voice is **your** legal responsibility — only
  use voices you have the right to use.

---

## 繁體中文

**情境：** 你想讓角色用**自訂或克隆的聲音**（例如某個角色的聲音）說話，取代預設免費的
**edge-tts**。Warashi 可以透過 **GPT-SoVITS** 做到——那是一個**你自己另外安裝、自己跑**的
語音合成服務。

### 前提

- **一台有 GPU 或 Apple Silicon 的機器。** GPT-SoVITS 是神經網路語音引擎，NVIDIA 顯卡大約需要
  **6 GB 顯示記憶體**，或用 Apple Silicon 的 Mac。它可以跟 Warashi 同一台，也可以是同網路的
  另一台電腦。
- **GPT-SoVITS 要你自己裝。** 它**沒有內建**在 Warashi 裡，要另外安裝、另外啟動。
  專案在這：<https://github.com/RVC-Boss/GPT-SoVITS>
- GPT-SoVITS 會開一個 HTTP API，預設在 **連接埠 `9880`**。

### 最重要的觀念：什麼東西放哪邊（最容易搞錯）

這段是最多人弄錯的，先看。聲音設定拆在**兩個**程式裡：

| 東西 | 放在 | 為什麼 |
|------|------|--------|
| **聲線「模型權重」**——GPT 模型（`.ckpt`）與 SoVITS 模型（`.pth`） | **GPT-SoVITS 那邊** | 它們就是真正的神經網路模型，GPT-SoVITS 才是負責載入與運算的程式。 |
| **參考音檔 + 逐字稿** | **Warashi 這邊**（`conf.yaml`） | Warashi 每次要語音時都會去呼叫 GPT-SoVITS，必須告訴它「**模仿哪一段短參考音色**」以及「**那段在講什麼**」，所以這些填在 Warashi 的設定裡。 |

一句話：**聲音包的權重載進 GPT-SoVITS；參考音檔和逐字稿填在 Warashi。** Warashi 是每次回覆時
去跟 GPT-SoVITS 要語音的「客戶端」。

### 操作步驟

1. **安裝、啟動 GPT-SoVITS，並把你的聲音載進去。**
   - 啟動 GPT-SoVITS 的 API 服務（預設監聽 `:9880`）。
   - 要用**自訂聲音**，就把那個聲音包的**權重**載進 GPT-SoVITS——這一步**在 GPT-SoVITS 那邊
     做**：呼叫它的 `/set_gpt_weights`（`.ckpt` GPT 模型）和 `/set_sovits_weights`
     （`.pth` SoVITS 模型），或改它自己的 `tts_infer.yaml` 讓它開機就載入。
     （確切的端點/設定細節請查 GPT-SoVITS 的文件，那是它的範疇，不是 Warashi。）

2. **在 Warashi：選 GPT-SoVITS，填面板上的兩個欄位。** 打開 Warashi →
   **設定 → 效能/硬體 → TTS 引擎**：
   - 把 **TTS 引擎**設成 **GPT-SoVITS**（`gpt_sovits_tts`），另一個選項是預設的 `edge_tts`。
   - 填**服務位址**（`api_url`）——GPT-SoVITS 在哪裡。預設是 `http://localhost:9880/tts`；
     若 GPT-SoVITS 跑在同網路的另一台機器，把 `localhost` 換成那台的 IP，例如
     `http://192.168.1.50:9880/tts`。
   - 填**參考音檔路徑**（`ref_audio_path`）——你想被模仿的那段短參考音檔的路徑。這個路徑要從
     **GPT-SoVITS 的角度**看是有效的（讀檔的是它）。

   > 面板上**只有**這幾個 GPT-SoVITS 欄位：引擎選擇、`api_url`、`ref_audio_path`。其餘必填欄位
   > 目前面板沒有，要到 `conf.yaml` 填（下一步）。

3. **在 `conf.yaml` 填其餘必填欄位。** 打開 `conf.yaml`，找到 `gpt_sovits_tts` 區塊
   （在 `character_config` → `tts_config` 底下），這些是 GPT-SoVITS 出聲的**必填**項：

   - **`prompt_text`**——把參考音檔裡**一字不差**講的那句話打出來。**必填**，GPT-SoVITS 靠它對齊
     參考聲音。空白是最常見的失敗原因。
   - **`prompt_lang`**——參考音檔講的語言（如 `ja`、`zh`、`en`）。
   - **`text_lang`**——角色實際要**說出來**的語言。（注意：Warashi 會先把回覆翻譯過再送進 TTS，
     所以這是最後到達 GPT-SoVITS 的文字語言，預設值是 `all_ja`。）

4. **重啟 Warashi。** 引擎與 TTS 變更是在 Warashi 啟動時讀取的，所以要**關掉再開**才會生效；
   面板在你改完 TTS 後也會提示需要重啟。

### 常見問題

- **切換後沒聲音／TTS 報錯？** 依序檢查：(1) GPT-SoVITS 真的有在跑、`api_url` 連得到；
  (2) 聲音權重有載進 GPT-SoVITS；(3) `ref_audio_path` 指向 GPT-SoVITS 讀得到的檔；
  (4) `prompt_text` 有填且跟參考音檔一致。
- **關鍵限制——`prompt_text` 必填。** 留空是最常見的失敗原因。
- **語言聽起來不對？** 確認 `prompt_lang` 跟參考音檔一致、`text_lang` 跟你想說的語言一致。
- **GPT-SoVITS 在另一台電腦？** `api_url` 填那台的 IP，並記得 `ref_audio_path` 是在**那台**上
  解析，不是 Warashi 這台。
- **想換回免費聲音？** TTS 引擎切回 **edge-tts** 再重啟即可。
- **法律提醒：** 克隆真人聲音的法律責任由**你自己**承擔，只用你有權使用的聲音。
