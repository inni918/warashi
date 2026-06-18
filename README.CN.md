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
- **LLM 设置标签页** —— Ollama 模式允许你手动输入模型名，因此也能用云端模型（例如 `gpt-oss:cloud`）。
- **性能预设** —— 轻量 / 标准 / 高性能三档，一键搭配好 ASR/TTS 引擎选择 + 记忆整理频率 + 模型常驻。
- **跨语言翻译** —— 可选的字幕 / 语音翻译（默认关闭）。
- **开箱即用** —— 内置示例 Live2D 模型 + 免费云端 TTS（edge-tts）+ 自动下载的小型 ASR 模型。你只需要插上一个 LLM。
- **完整双语界面** —— 繁体中文（zh）与英文（en）。

---

## 截图

![Warashi —— 运行中的 Live2D AI 伙伴](assets/warashi-hero.png)

*Warashi 在桌面上运行：一个你真的会去聊天的 Live2D 形象。*

---

## 快速开始（下载 → 双击 → 开聊）

最简单的路径 —— **完全不用终端。**

> **开始前先准备好：你需要一颗 AI「大脑」（LLM）。**
> Warashi 是**身体和脸** —— 形象、声音、记忆都有了。真正会思考、会说话的**大脑**，是一个另外的 AI，由*你*来提供。你二选一即可，而且可以在设置向导里再设置（现在不用把所有事都决定好）：
> - **（A）用付费的云端 AI** —— 去 [OpenAI](https://platform.openai.com/api-keys)、Claude 或 Gemini 拿一个 API key 粘贴进去。用小模型的话，通常**一次聊天只要几分钱**。
> - **（B）跑免费的本地 AI** —— 安装免费的 **[Ollama](https://ollama.com)** 应用，它就在你自己的电脑上跑一颗大脑。**完全免费**，但需要一台还算够力的电脑。
>
> 现在还不用先下载任何东西 —— 只要在等下面的安装跑完之前，心里有个方向就好。

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

开箱即用，它使用内置的 **mao** 示例 Live2D 模型和 **edge-tts**（免费云端语音，无需显卡）。第一次运行还会自动下载一个小型语音转文字模型。

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

## LLM 设置（必做）

你需要**二者择一**：一个云端 LLM 的 API key，**或**一个正在运行的本地 LLM。陪伴聊天用便宜的模型就足够了 —— 不需要旗舰级。

### 方案 A —— 云端 API key（OpenAI / Claude / Gemini）

最简单。在**首次启动设置向导**（或之后的 **LLM 设置标签页**）里，粘贴你的 OpenAI、Claude 或 Gemini 的 API key。向导会用一次快速测试调用来验证它，然后写进 `conf.yaml`。**保存后重启启动器**，新的 LLM 才会生效。

### 方案 B —— 本地 Ollama

安装 [Ollama](https://ollama.com)，拉一个模型（例如 `ollama pull qwen2.5`），然后在向导 / 设置标签页里选 Ollama。完全本地，不用 API key，没有云端费用。

### 方案 C —— 通过 Ollama 使用云端模型（例如 `gpt-oss:cloud`）

Ollama 也能代理某些**云端**模型。在 **Ollama 模式下你可以手动输入模型名**，包括以 `:cloud` 结尾的云端名称（例如 `gpt-oss:cloud`）。

> **重要：** 通过 Ollama 使用云端模型，需要你先登录 —— 在终端里运行 **`ollama signin`** 之后再用，否则调用会失败。

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
