# Warashi

> 一个免费、开源、对新手友好的**桌面 AI 伙伴**，带 Live2D 形象 —— 长期记忆、主动聊天、自然语音，还有睡眠模式。自带你的 LLM，其余一切开箱即用。

**语言:** [English](./README.md) | [繁體中文](./README.md#繁體中文) | [日本語](./README.JP.md) | [한국어](./README.KR.md) | **简体中文**

![License](https://img.shields.io/badge/license-MIT%20core%20%2B%20bundled%20terms-blue)
![Built on Open-LLM-VTuber](https://img.shields.io/badge/built%20on-Open--LLM--VTuber-orange)
![Platforms](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey)

---

## 这是什么？

**Warashi** 把屏幕上的一个 Live2D 角色变成你真的会去聊天的 AI 伙伴 —— 它记得你、会自己开启对话、你说话时它会听、你说晚安它就安静下来。

它是把优秀的开源项目 [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) **重新打包成对新手友好**的版本。我们站在它的肩膀上：上游提供稳定可靠的 Live2D + 语音识别/合成 + LLM 底层；这个 fork 则把它包装成「**下载 → 双击 → 开聊**」的体验，面向非技术用户，并加上了记忆系统、主动对话、自然插话语音、角色管理、应用内设置向导，以及完整的中英双语（English / 繁體中文）界面。

**我们的原则 —— 以及我们刻意不做的事：**

- **免费开源，可选捐款。** 没有付费档位，没有付费墙。
- **不做手机版。** 只做桌面（macOS / Windows）。
- **不做模型市集 / 不附带有版权的角色。** 借此避开 Live2D 商用授权的陷阱 —— 我们只附带中性的免费默认资源；角色、语音、LLM 都由你自己带。

> 本项目构建于 Open-LLM-VTuber 之上。完整致谢与各组件许可证见 [`NOTICE`](./NOTICE)，原项目文档保留在 [`README.upstream.md`](./README.upstream.md)。

---

## 功能特性

- **长期记忆** —— 它记得你是谁、你在忙什么，并随时间越来越了解你。每个角色都有一份精选的「核心记忆」注入人设；每轮对话结束后，由 LLM 决定哪些值得保存。更新即时生效（无需重启）。记忆上限可调。
- **深度回想（FTS5 trigram）** —— 可选开启，对你说过的全部历史做全文搜索，完整支持中日韩文字。
- **主动话题** —— 沉默一段时间后，它会自己开启一个话题。可选拉取最新的 AI / 科技 / 动漫 / 游戏新闻来聊（纯标准库实现的小工具，**无需 API key**）。
- **自然插话语音对话** —— 随时都能开口，不必等麦克风，也能像真人对话那样中途打断它。
- **睡眠 / 免打扰模式** —— 说一句「晚安」它就停止主动发话；下次你跟它说话时恢复。关键词可配置。
- **角色管理** —— 创建 / 编辑 / 切换 / 删除角色：名称 + 人设 + Live2D 皮肤 + 语音 + 各自独立的记忆。
- **首次启动设置向导** —— 粘贴一个 API key（OpenAI / Claude / Gemini），或选一个本地 Ollama 模型。向导在保存前会先做一次快速测试调用。
- **LLM 设置标签页** —— 粘贴一个 API key，或选择／手动输入一个 Ollama 模型（本地模型，或通过 Ollama 提供的云端模型）。
- **性能预设** —— 轻量 / 标准 / 高性能三档，一键搭配好 ASR/TTS 引擎选择 + 记忆整理频率 + 模型常驻。
- **跨语言翻译** —— 可选的字幕 / 语音翻译（默认关闭）。
- **开箱即用** —— 内置示例 Live2D 模型 + 免费云端 TTS（edge-tts）+ 自动下载的语音识别（ASR）模型（约 1GB，仅在第一次启动时下载一次、需要几分钟）。你只需要插上一个 LLM。
- **完整双语界面** —— 繁体中文（zh）与英文（en）。

---

## 截图

![Warashi —— 运行中的 Live2D AI 伙伴](assets/warashi-hero.png)

*Warashi 在桌面上运行：一个你真的会去聊天的 Live2D 形象。*

---

## 快速开始（下载 → 双击 → 开聊）

最简单的路径 —— **完全不用终端。**

> **开始前先准备好：你需要一颗 AI「大脑」（LLM）。**
> Warashi 是**身体和脸** —— 形象、声音、记忆都有了。真正会思考、会说话的**大脑**，是一个另外的 AI，由*你*来提供。你会在首次启动向导里设置它。下面按从易到难列出选项：
> - **（推荐 —— 免费、私密、跑在你自己的电脑上）通过 Ollama 用本地模型。** 安装免费的 **[Ollama](https://ollama.com)** 应用，然后在终端里运行 `ollama pull qwen2.5:3b`（一个约 1.9 GB 的小模型）。Warashi 的默认本来就指向它，所以直接就能用 —— **不用账号、不用 API key、零费用、可离线，而且你的对话永远不会离开你的电脑。** 一般 8–16 GB 的笔记本就跑得动。（想要更聪明的回复、内存也够？拉一个更大的模型，例如 `qwen2.5:7b`，再到设置里选它。）
> - **（可选 —— 电脑较弱时质量更好）Ollama Cloud 免费方案。** Ollama 可以在*它的*服务器上免费跑一个更大的模型（有额度限制）。需要一个免费账号 —— 见下方**方案 B**；你必须先 `ollama pull` 那个云端模型。
> - **（可选 —— 免费里质量最好）免费的云端 API key。** Google AI Studio（Gemini）、Cerebras 或 Groq 提供免费 key（免绑信用卡）。免费选项里质量最好，但需要账号 + key，而且你的对话会送到该服务商。见**方案 C**。
> - **（如果你本来就有付费的）云端 API key**：来自 OpenAI／Claude／Gemini —— 顶级质量，一次聊天几分钱。见**方案 D**。

1. **下载 Warashi。** 到 [**Releases 页面**](https://github.com/inni918/warashi/releases/latest) 下载最新的 `Warashi-*.zip`，然后解压（例如解到桌面）。_（或者在 repo 主页点绿色的 **`<> Code`** 按钮 → **Download ZIP**。）_
2. **双击解压后文件夹里的启动器**：
   - **macOS：** `start-companion.command`
   - **Windows：** `start-companion.bat`
   - 第一次启动会安装所有东西（先 `uv`，再依赖项），可能要几分钟。**那个窗口别关 —— 它就是服务器本体。**
3. 浏览器会自动打开 **http://localhost:12393**。第一次运行会出现**设置向导**：**粘贴一个 API key**（OpenAI / Claude / Gemini），**或者选一个本地 Ollama 模型**。向导会先测试你的选择，再保存。

   ![Warashi 首次启动设置向导](assets/warashi-setup.png)

   *首次启动的设置向导，在这里接上你的 AI「大脑」。*

4. **重启一次，新的大脑才会接上。** 退出方式是**把第 2 步那个启动器 / 终端窗口关掉**（这会停掉服务器），然后**再双击一次启动器**重新启动，让新的 LLM 生效。（应用里也会提示，LLM 的变更「会在重启之后生效 —— 或者切换一次角色之后生效」。）然后就能开始聊天；在页面上点一下以解锁音频。

> **macOS Gatekeeper（仅第一次启动）：** 双击时可能出现「**无法打开，因为它来自身份不明的开发者**」。这对一个未签名的开源应用来说是正常的。请对 `start-companion.command` **右键点击** → **打开** → 在对话框里再点 **打开**。允许一次之后，往后就能直接双击了。（我们不提供签名 / 公证版本 —— 这是免费档位。）

> **Windows SmartScreen（仅第一次启动）：** 双击时可能出现蓝色的「**Windows 已保护你的电脑**」窗口。这对一个未签名的开源应用来说是正常的。点 **更多信息** → **仍要运行**。允许一次之后就不会再问了。

开箱即用，它使用内置的 **mao** 示例 Live2D 模型和 **edge-tts**（免费云端语音，无需显卡）。第一次运行还会自动下载一个语音转文字模型 —— 它大约 **1GB**，所以**第一次启动会做一次性的下载 + 解压，可能要好几分钟**。这期间启动器窗口看起来像卡住了，其实没有，**请别关掉、让它跑完**；这只会发生一次。

### 更喜欢用终端？（进阶）

大多数人用上面的 **Download ZIP** 路径就好。如果你熟悉终端，也可以改用 clone 来获取项目。需要 **Python ≥ 3.10、< 3.13** 与 [`uv`](https://github.com/astral-sh/uv)。

```bash
git clone https://github.com/inni918/warashi.git && cd warashi
uv sync                  # installs dependencies
uv run run_server.py     # start the server
# open http://localhost:12393  → setup wizard → chat
```

向导会替你把 LLM 的选择写进 `conf.yaml`。你仍然可以手动编辑它（见下文）。

---

## 启动、关闭、开机自动启动

**怎么开（启动「主机」）：**

- **Windows：** 双击 **`start-companion.bat`**
- **macOS：** 双击 **`start-companion.command`** —— 第一次系统可能会拦，对文件右键 → **打开** → 再点一次 **打开**；之后正常双击就行。

会弹出一个黑色命令窗口 —— **那个窗口就是服务器，聊天期间要一直开着。** 等它准备好，会自己用浏览器打开 app（`http://localhost:12393`）。可以这样想：**命令窗口是引擎，浏览器标签页只是画面。**

> 仅限第一次启动：会下载约 1GB 的语音模型、要等几分钟，窗口看起来像卡住其实没有 —— 让它开着跑完即可。

**怎么关：**

- **关掉那个黑色命令窗口**（或在里面按 **Ctrl + C**），角色就完全停止。
- 只关**浏览器标签页**只是隐藏画面，服务器还在跑；要真的停掉请关命令窗口。
- 如果你装了 **Ollama** 跑本地大脑，它会在后台持续运行。空闲时很省，可以不管；想关就从任务栏（Windows）／菜单栏（macOS）的图标 Quit。

**之后要再开：** 再运行同一个启动器即可（它也是你的日常启动器）。

**让它在电脑开机时自动启动（可选）：**

- **Windows**
  1. 对 **`start-companion.bat`** 右键 → **创建快捷方式**。
  2. 按 **Win + R**，输入 **`shell:startup`**，按 **Enter** —— 会打开「启动」文件夹。
  3. 把快捷方式拖进那个文件夹。以后每次登录都会自动启动。*（要取消：把该快捷方式从文件夹删掉。）*

- **macOS**
  1. 打开 **系统设置 → 通用 → 登录项与扩展**。
  2. 在 **登录时打开** 下点 **+**，选 **`start-companion.command`**（或把文件拖进列表）。
  *（要取消：选中它后点 **−**。）*

两种方式都会在登录时自动弹出命令窗口（接着是浏览器）。提醒：每次开机弹出一个终端窗口是正常的，那就是引擎在启动。如果你用本地 Ollama 大脑，Ollama 装好后本来就会开机自启，所以整套会自己起来。

---

## LLM 设置（必做）

你需要**二者择一**：一个云端 LLM 的 API key，**或**一个正在运行的本地 LLM。陪伴聊天用便宜的模型就足够了 —— 不需要旗舰级。

#### 方案 A —— 本地 Ollama（推荐：免费、私密、不用账号）
安装 [Ollama](https://ollama.com/download)，然后在终端里运行 `ollama pull qwen2.5:3b`（约 1.9 GB）。Warashi 的默认本来就用 `qwen2.5:3b`，所以下载完成后、下次重启就能用 —— 不用 API key、不用账号、没有云端费用、完全离线，而且你的对话都留在你的电脑上。一般 8–16 GB 的笔记本就跑得很顺。想要更聪明的回复，可以拉一个更大的模型（例如 `qwen2.5:7b`），再到 LLM 设置标签页里选它。

#### 方案 B —— 通过 Ollama 使用云端模型（免费账号；电脑较弱时很合适）
Ollama 可以在它自己的服务器上跑一个*更大的*模型，所以慢的电脑也能得到不错的回复。免费方案，但需要一个账号，而且你必须先把模型拉下来：
1. 从 [ollama.com/download](https://ollama.com/download) 安装 Ollama（v0.12+）。
2. 到 [ollama.com](https://ollama.com) 注册一个免费账号，然后在终端里运行 `ollama signin`。
3. **运行 `ollama pull gpt-oss:20b-cloud` —— 必须先拉下来才能用。**（只在设置里填名字是不够的。）
4. 在 LLM 设置标签页里选 Ollama，把模型设成 `gpt-oss:20b-cloud`。

`gpt-oss:20b-cloud` 是最适合免费额度的轻量模型；`qwen3.5:cloud` 或 `minimax-m3:cloud` 更强，但会更快用掉免费额度。

> **关于「免费」，老实说：** 免绑信用卡、完全 $0，只要一个免费账号 —— 但属于*轻量使用*等级：一次只能跑一个云端模型，会话额度约每 5 小时重置一次、外加每周额度，而且 Ollama 没有公布确切数字，所以聊太多可能会碰到额度上限、要等重置。推理跑在 **Ollama 的服务器上**，所以不要发送你想完全保密的内容。云端模型还处于 preview 阶段 —— **依赖它之前，先确认它真的能回一次。**

#### 方案 C —— 免费的云端 API key（Gemini / Cerebras / Groq）
免费选项里聊天质量最好。注册一个免费账号（免绑信用卡），创建一个 API key，到 LLM 设置标签页粘贴 key 并填对应的 base URL：
- **Google AI Studio（Gemini）：** `https://generativelanguage.googleapis.com/v1beta/openai/` —— 免费额度大方；注意 Google 可能会用免费方案的对话来改进它的产品。
- **Cerebras：** `https://api.cerebras.ai/v1` —— 很快，每天约 100 万 token 免费（免费方案的 context window 较短）。
- **Groq：** `https://api.groq.com/openai/v1` —— 很快，有每日 token 上限。

请用各服务商文档里目前可用的模型名。你的对话会送到该服务商，而且免费方案有速率限制。

#### 方案 D —— 付费的云端 API key（OpenAI / Claude / Gemini）
如果你本来就有付费的，把 key 粘贴进向导即可。质量最高；用小模型通常一次聊天只要几分钱。

### ⚠️ 不支持思考型（reasoning）模型

像 **`glm-4.7:cloud`** 这类思考型模型，会把答案放在一个单独的 `reasoning` 字段里，而把正常的 `content` 字段留**空**。这个应用只读 `content`，所以思考型模型会显示成**空白回复** —— 而且既然没有内容可念，**也就没有语音**。

**建议：** 选一个正常的（非思考型）对话模型。一个小而快的模型反而能给你更自然、延迟更低的陪伴。

> 手动编辑：LLM 配置位于 `conf.yaml` 中的 `character_config → agent_config → llm_configs → openai_compatible_llm`。文件里的注释会告诉你如何用自己的 key 指向 OpenAI / Claude / Gemini。编辑后重启启动器。

---

## 其他设置

### 记忆（核心 + 深度回想）
默认开启。每个角色把自己的记忆保存在 `chat_history/<conf_uid>/core_memory.md` —— 既有注入人设的核心记忆，也有每轮由 LLM 进行的整理（模型决定要保留什么）。可选开启 **FTS5 trigram 深度回想**，在你需要更长期记忆时搜索你的全部历史。记忆上限可在设置里调。

### 角色
在应用里创建 / 编辑 / 切换 / 删除角色 —— 每个角色有自己的名称、人设、Live2D 皮肤、语音，以及**独立的记忆**。要添加你自己的 Live2D 模型，把它放到 `live2d-models/<name>/` 下，在 `model_dict.json` 里加一条记录，然后选中它。**不要把有版权的角色模型 commit 进公开 repo。**

#### 更多角色（可选）
为了授权安全，Warashi 只内置 **3 个免费的 Live2D 原创角色**（`mao_pro`、`haru`、`hiyori`）。想要更多 —— 包括男管家角色 **Natori（名取）**？你可以自己从官方页面下载免费的官方 Live2D 示例模型再放进来。请从 **[Live2D 示例模型页面](https://www.live2d.com/en/learn/sample/)** 按 Live2D 自己的授权下载 —— 我们不代为分发。具体做法见 [`docs/add-live2d-character.md`](docs/add-live2d-character.md)。

### 性能预设
**轻量 / 标准 / 高性能** 预设打包了 ASR/TTS 引擎选择、记忆整理频率，以及模型常驻。机器一般就选轻量，硬件够强就选高性能。

### 主动话题与新闻
伙伴会在空闲一段时间后开启话题。可选用内置的新闻小工具（`scripts/news_topics.py`）用当前头条刷新这些话题 —— 纯标准库，无需 API key —— 并给它设定时（cron / launchd / 任务计划程序），例如每隔几小时一次。

### 睡眠 / 安静模式
说一句「晚安」它就停止主动发话；下次你发消息时恢复。关键词可配置。

### 翻译
可选的跨语言字幕 / 语音翻译，**默认关闭**（`conf.yaml` 中的 `tts_preprocessor_config → translator_config`）。

### 语音
默认是 **edge-tts**（免费，无需硬件）。要高质量的本地 / 自定义语音，可以把 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) 作为一个服务运行，并把配置指向它（需要显卡或 Apple Silicon）。克隆真人声音的法律责任由你自负。

---

## 教程

- [从手机 / 平板使用（Tailscale）](docs/remote-access-tailscale.md) —— 即使不在家里的网络，也能从另一台设备连上你的伙伴。
- [用 GPT-SoVITS 自定义语音](docs/custom-voice-gpt-sovits.md) —— 给你的角色一个克隆或自定义的声音。
- [添加你自己的 Live2D 角色](docs/add-live2d-character.md) —— 放一个模型进来并切换到它。

## 致谢与许可证

没有它所构建于的上游工作，就不会有这个项目。也请去 **star 并支持 [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)**。

- **上游：** [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) —— 其服务器端代码为 MIT，Copyright (c) 2025 Yi-Ting Chiu。
- **本 fork 新增的部分**（记忆、主动话题、插话、安静模式、角色管理、设置向导、性能预设、双语界面）—— MIT。
- **内置网页前端** —— `frontend/` 里编译好的网页包是 Open-LLM-VTuber-Web 前端，采用 **Open-LLM-VTuber License 1.0**（Apache-2.0 + 附加条款）。允许免费、非商业的使用与再分发；商业改名、付费托管 / SaaS，或嵌入付费产品，则需向 Open-LLM-VTuber 团队另取商业授权。本 fork 免费且非商业，属于该许可证允许的范围。见 [`NOTICE`](./NOTICE)。
- **Live2D Cubism 与内置示例模型** —— 内置的 **mao_pro** / **haru** / **hiyori** 模型是 Live2D Inc. 的示例数据，依 **Live2D 免费素材许可协议**使用（见 [`LICENSE-Live2D.md`](./LICENSE-Live2D.md)）。必须保留的致谢句：
  > This content uses sample data owned and copyrighted by Live2D Inc.

  它们以**未修改**的形式作为免费默认资源附带。**任何付费 / 商用版本都必须替换**成你自己的 CC0 / 已授权 / 委托制作的模型。
- **其他组件**（各自的许可证见 [`NOTICE`](./NOTICE)）：GPT-SoVITS（MIT，可选 TTS）、sherpa-onnx（Apache-2.0，ASR 引擎 —— SenseVoice 模型有自己的许可证；或改用 Whisper）、Silero VAD（MIT）、edge-tts（使用微软的在线 TTS 服务）、DeepLX（非官方 DeepL 端点 —— 正式环境请改用官方 DeepL API）。

**不要分发有版权的角色、美术、语音或训练过的语音模型。** 本 repo 只附带中性默认资源；其余自己带。

### License

本 fork 自己的源代码以 **MIT 许可证**发布，构建于 Open-LLM-VTuber 同为 MIT 许可的服务器端代码之上（Copyright (c) 2025 Yi-Ting Chiu）。但是，**整个项目并非单纯的 MIT**：`frontend/` 里内置的编译后网页前端采用 **Open-LLM-VTuber License 1.0**（Apache-2.0 + 附加条款），而内置的 Live2D 示例模型另有其 Live2D 条款。完整、准确的全貌见 [`LICENSE`](./LICENSE)、[`NOTICE`](./NOTICE) 与 [`LICENSE-Live2D.md`](./LICENSE-Live2D.md)。

---

## 支持本项目

这是一个免费、开源的项目 —— 没有付费墙。如果它对你有用，欢迎打赏，但绝非必须：

- **Ko-fi:** [ko-fi.com/leonhsueh](https://ko-fi.com/leonhsueh)
- **GitHub Sponsors:** 即将开放

也请支持本项目所构建于的上游 —— [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)。

---

## 贡献指南

欢迎提 issue 和 pull request。

- bug 与功能想法请在 **Issues** 里提。
- 代码变更请开一个 **Pull Request**，并写清楚说明。
- **请不要**添加有版权的角色、美术、语音或训练过的语音模型 —— 让这个 repo 保持可发布的中性默认状态。
