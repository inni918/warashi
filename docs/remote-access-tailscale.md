# Use Warashi from another device (Tailscale)

**Scenario:** You installed Warashi on one computer (your "host"), and now you want to
open your character from your phone or tablet — even when you're away from home, on a
different Wi-Fi or on mobile data. This guide uses **Tailscale** so your devices can
reach each other privately, without exposing anything to the public internet.

## What is Tailscale?

Tailscale is a **mesh VPN**. After you install it and log in on each device, all the
devices on the same account join one small private network (a "tailnet"). They can then
talk to each other directly using a stable name or IP, **no matter what network each one
is on** — home Wi-Fi, office, mobile data, anywhere. Nothing is published to the public
internet; only your own logged-in devices can connect. It's free for personal use.

Get it from <https://tailscale.com/download>.

## Before you start

Open `conf.yaml` in your Warashi folder and look at the top `system_config` block. The
relevant lines are:

```yaml
system_config:
  host: 'localhost'   # which network interface the server listens on
  port: 12393         # which port the server listens on
```

- **`host`** defaults to `localhost` (also written `127.0.0.1`). This means the server
  only accepts connections **from the same computer** — that's why another device can't
  reach it yet.
- **`port`** defaults to `12393`. (Some older builds used `12393` — check your own file
  and use whatever number you actually see there. Throughout this guide, replace
  `<port>` with that number.)

## Step-by-step

### 1. Install Tailscale on both devices and log in to the *same* account

Install Tailscale on the **host computer** and on your **phone/tablet**, then sign in to
**the same Tailscale account** on both. They will now appear in your tailnet. In the
Tailscale app you'll see each device's name (e.g. `my-mac`) and its Tailscale IP (a
`100.x.x.x` address).

### 2. Make the Warashi backend reachable from your other device

You have two options. **Option A (Tailscale Serve, HTTPS) is strongly recommended** — it
is the only way the microphone / voice features will work remotely (see the limit below).

#### Option A — Tailscale Serve over HTTPS (recommended, voice works)

`tailscale serve` proxies your local Warashi port and serves it over **HTTPS** at your
device's tailnet name, something like:

```
https://<machine-name>.<your-tailnet>.ts.net
```

The general idea is to tell Tailscale Serve to forward HTTPS traffic to your local
Warashi port. On a recent Tailscale, a single command of this shape does it:

```bash
# Run this ON THE HOST computer. Replace <port> with your conf.yaml port (e.g. 12393).
tailscale serve <port>
```

Older or newer versions use slightly different wording (for example an explicit
`https / --bg / --set-path` form). **The exact `tailscale serve` syntax changes between
versions, so check the official Tailscale Serve docs for your version:**
<https://tailscale.com/kb/1242/tailscale-serve>

When it's running, Tailscale will print the public-to-your-tailnet HTTPS URL (the
`https://<machine-name>.<your-tailnet>.ts.net` address). With Option A you can usually
**leave `host` as `localhost`**, because Tailscale Serve is connecting to Warashi locally
on the host and only re-exposing it over HTTPS to your tailnet.

#### Option B — plain HTTP over the Tailscale IP (text only, no microphone)

If you don't want to set up Serve, you can make Warashi listen on all interfaces and
reach it by its Tailscale IP:

1. In `conf.yaml`, change `host` to listen on all interfaces:

   ```yaml
   system_config:
     host: '0.0.0.0'
     port: 12393
   ```

2. Restart Warashi (close it and start it again) so the new `host` takes effect.
3. From your phone/tablet, open:

   ```
   http://<host-Tailscale-IP>:<port>
   ```

   e.g. `http://100.101.102.103:12393`

This works for **typing**, but the **microphone will NOT work** — see the limit below.

### 3. Open the address on your phone/tablet

In your mobile browser, open the HTTPS URL from Option A (or the `http://IP:port` from
Option B). Your character loads and you can chat from anywhere your devices have a
connection.

## Key limitation (please read)

**Browsers only allow microphone access over HTTPS or on `localhost`.** This is a
hard browser security rule, not a Warashi setting.

- **Remote + voice** → you **must** use **Tailscale Serve (HTTPS)** — Option A. This is
  the whole reason Option A is recommended.
- **Plain `http://<IP>:<port>`** (Option B) → the browser will block the mic, so you get
  **text chat only**.
- On the **host computer itself**, the mic works at `http://localhost:<port>` because
  `localhost` is exempt from the rule.

## FAQ / troubleshooting

- **Page won't load at all?** Confirm both devices show as "Connected" in the Tailscale
  app and are on the same account. For Option B, double-check you changed `host` to
  `0.0.0.0` **and restarted** Warashi.
- **Loads but the mic button does nothing?** You're almost certainly on plain HTTP. Switch
  to the Tailscale Serve HTTPS URL (Option A).
- **Which port?** Whatever is in your `conf.yaml` `system_config.port`. Default is `12393`.
- **Is this exposed to the internet?** No. Tailscale only lets your own logged-in devices
  connect. Tailscale Serve stays inside your tailnet (it is not the same as "Funnel",
  which *would* publish to the internet — you do **not** need Funnel for this).

---

## 繁體中文

**情境：** 你已經在一台電腦（「主機」）裝好 Warashi，現在想用手機或平板打開你的角色——
就算人不在家、用的是不同的 Wi-Fi 或行動網路也能用。這份教學用 **Tailscale** 讓你的裝置之間
私密互連，完全不會把東西暴露到公開的網際網路上。

### Tailscale 是什麼？

Tailscale 是一種 **mesh VPN（網狀虛擬私人網路）**。你在每台裝置裝好並用同一個帳號登入後，
這些裝置就會組成一個小型私人網路（叫 tailnet）。之後它們就能用固定的名稱或 IP 互相連線，
**不管各自接的是哪個網路**——家裡 Wi-Fi、公司、行動網路都行。整個過程不會公開到網際網路上，
只有你自己登入的裝置連得到。個人使用免費。

下載：<https://tailscale.com/download>

### 開始之前

打開 Warashi 資料夾裡的 `conf.yaml`，看最上面的 `system_config` 區塊：

```yaml
system_config:
  host: 'localhost'   # 伺服器監聽哪個網路介面
  port: 12393         # 伺服器監聽哪個連接埠
```

- **`host`** 預設是 `localhost`（也就是 `127.0.0.1`），代表伺服器**只接受同一台電腦的連線**，
  所以別台裝置現在還連不到。
- **`port`** 預設是 `12393`。（有些舊版本用的是 `12393`——請看你自己檔案裡實際的數字，
  下面凡是寫 `<port>` 的地方都換成它。）

### 操作步驟

1. **兩台裝置都裝 Tailscale，並登入同一個帳號。** 主機電腦、手機/平板都裝好後，用**同一個
   Tailscale 帳號**登入。它們就會出現在你的 tailnet 裡，App 裡會看到每台裝置的名稱（例如
   `my-mac`）和它的 Tailscale IP（`100.x.x.x` 開頭）。

2. **讓 Warashi 後端能被另一台裝置連到。** 有兩種做法，**強烈建議用方案 A（Tailscale Serve，
   走 HTTPS）**——因為只有它能讓遠端的麥克風/語音功能正常運作（見下方「關鍵限制」）。

   - **方案 A — Tailscale Serve，走 HTTPS（建議，語音可用）：** `tailscale serve` 會把你本機的
     Warashi 連接埠用 **HTTPS** 代理出來，網址長得像
     `https://<機器名>.<你的 tailnet>.ts.net`。概念就是叫 Tailscale Serve 把 HTTPS 流量轉發到
     你本機的 Warashi 連接埠。較新的 Tailscale 用一行類似這樣的指令（**在主機上跑**，`<port>`
     換成你 `conf.yaml` 的連接埠，例如 12393）：

     ```bash
     tailscale serve <port>
     ```

     不同版本的寫法略有差異（有些要明確寫 `https / --bg / --set-path`）。**`tailscale serve` 的
     確切語法會隨版本改變，請依你的版本查官方 Serve 文件：**
     <https://tailscale.com/kb/1242/tailscale-serve>。跑起來後 Tailscale 會印出那個
     `https://<機器名>.<你的 tailnet>.ts.net` 網址。用方案 A 時通常**可以把 `host` 維持
     `localhost`**，因為 Tailscale Serve 是在主機本機連 Warashi，再用 HTTPS 重新分享給你的 tailnet。

   - **方案 B — 純 HTTP + Tailscale IP（只能打字，麥克風不能用）：** 把 `conf.yaml` 的 `host`
     改成 `0.0.0.0`，**重啟 Warashi**，然後在手機/平板開
     `http://<主機的 Tailscale IP>:<port>`（例如 `http://100.101.102.103:12393`）。
     這樣可以打字，但**麥克風不能用**（原因見下方）。

3. **在手機/平板打開那個網址。** 用手機瀏覽器打開方案 A 的 HTTPS 網址（或方案 B 的
   `http://IP:port`），角色就會載入，你就能遠端開聊了。

### 關鍵限制（務必看）

**瀏覽器規定：麥克風只在 HTTPS 或 `localhost` 才能用。** 這是瀏覽器的安全規則，不是 Warashi
的設定能改的。

- **遠端又要語音** → **一定**要用 **Tailscale Serve（HTTPS）**，也就是方案 A。這就是建議用
  方案 A 的全部理由。
- **純 `http://<IP>:<port>`**（方案 B）→ 瀏覽器會擋麥克風，所以**只能打字**。
- 在**主機電腦本機**用 `http://localhost:<port>` 麥克風是可以用的，因為 `localhost` 不受這條
  規則限制。

### 常見問題

- **頁面完全打不開？** 確認兩台裝置在 Tailscale App 裡都顯示「已連線」且是同一帳號。方案 B
  還要確認 `host` 改成 `0.0.0.0` **而且重啟過** Warashi。
- **能打開但麥克風按了沒反應？** 幾乎可以確定你用的是純 HTTP，改用 Tailscale Serve 的 HTTPS
  網址（方案 A）。
- **連接埠是哪個？** 就是 `conf.yaml` 裡 `system_config.port` 的值，預設 `12393`。
- **這會被暴露到網際網路嗎？** 不會。Tailscale 只讓你自己登入的裝置連得到。Tailscale Serve
  只在你的 tailnet 內（它跟會公開到網際網路的「Funnel」不一樣——這個用途**不需要** Funnel）。
