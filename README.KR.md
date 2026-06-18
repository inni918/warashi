# Warashi

> Live2D 아바타를 가진 무료 오픈소스 입문자 친화 **데스크톱 AI 컴패니언** — 장기 기억, 능동적 대화, 자연스러운 음성, 그리고 수면 모드까지. LLM만 직접 준비하면, 나머지는 설치하자마자 바로 작동합니다.

**언어:** [English](./README.md) | [繁體中文](./README.md#繁體中文) | [日本語](./README.JP.md) | **한국어** | [简体中文](./README.CN.md)

![License](https://img.shields.io/badge/license-MIT%20core%20%2B%20bundled%20terms-blue)
![Built on Open-LLM-VTuber](https://img.shields.io/badge/built%20on-Open--LLM--VTuber-orange)
![Platforms](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey)

---

## 이게 뭔가요?

**Warashi**는 화면 위의 Live2D 캐릭터를, 진짜로 대화하게 되는 AI 컴패니언으로 만들어 줍니다 — 당신을 기억하고, 스스로 먼저 말을 걸고, 당신이 말하는 동안 귀 기울여 듣고, 당신이 잘 자라고 인사하면 조용해집니다.

이건 훌륭한 [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) 프로젝트를 **친절하게 다시 포장한** 버전입니다. 우리는 그 어깨 위에 서 있습니다: 상류(upstream) 프로젝트가 탄탄한 Live2D + ASR/TTS + LLM 기반을 제공하고, 이 fork는 그것을 비개발자도 쓸 수 있는 **다운로드 → 더블클릭 → 대화** 경험으로 감싸면서, 기억 시스템, 능동적 대화, 자연스러운 끼어들기(barge-in) 음성, 캐릭터 관리, 앱 내 설정 마법사, 그리고 완전한 이중 언어(English / 繁體中文) UI를 더했습니다.

**우리의 원칙 — 그리고 우리가 의도적으로 하지 않는 것:**

- **무료 오픈소스, 기부는 선택.** 유료 등급도, 페이월(paywall)도 없습니다.
- **모바일 버전 없음.** 데스크톱 전용입니다 (macOS / Windows).
- **모델 마켓플레이스 / 저작권 있는 캐릭터 번들 없음.** 이렇게 해서 Live2D 상업 라이선스의 함정을 피합니다 — 우리는 중립적인 무료 기본값만 제공하고, 캐릭터·음성·LLM은 당신이 직접 가져옵니다.

> Open-LLM-VTuber 위에 만들어졌습니다. 전체 출처 표기와 구성 요소별 라이선스는 [`NOTICE`](./NOTICE)를, 원본 프로젝트 문서는 [`README.upstream.md`](./README.upstream.md)를 참고하세요.

---

## 기능

- **장기 기억** — 당신이 누구인지, 무엇을 하고 있는지 기억하고, 시간이 지날수록 당신을 더 알아 갑니다. 캐릭터별로 정리된 "핵심 기억"이 페르소나에 주입되며, 매 대화 차례마다 LLM이 무엇을 저장할 가치가 있는지 판단합니다. 변경 사항은 즉시 적용됩니다(재시작 불필요). 기억 용량 상한은 조절 가능합니다.
- **심층 회상 (FTS5 trigram)** — 선택적으로 켤 수 있으며, 당신이 지금까지 말한 모든 내용에 대한 전체 기록 검색을 제공합니다. CJK(한중일) 문자도 제대로 지원합니다.
- **능동적 화제** — 한동안 조용하면 스스로 화제를 꺼냅니다. 선택적으로 최신 AI / 기술 / 애니메이션 / 게임 뉴스를 가져와 대화 소재로 삼을 수 있습니다(순수 표준 라이브러리 헬퍼, **API 키 불필요**).
- **자연스러운 끼어들기 음성 대화** — 언제든 말할 수 있습니다. 마이크를 기다릴 필요가 없고, 실제 대화처럼 말하는 도중에 끊을 수도 있습니다.
- **수면 / 방해 금지 모드** — "晚安"(잘 자)이라고 말하면 먼저 말 거는 것을 멈춥니다. 다음에 당신이 다시 말을 걸면 재개됩니다. 키워드는 설정으로 바꿀 수 있습니다.
- **캐릭터 관리** — 캐릭터를 생성 / 편집 / 전환 / 삭제할 수 있습니다: 이름 + 페르소나 + Live2D 스킨 + 음성 + 각자 분리된 기억.
- **첫 실행 설정 마법사** — API 키(OpenAI / Claude / Gemini)를 붙여넣거나 로컬 Ollama 모델을 고릅니다. 마법사는 저장하기 전에 빠른 테스트 호출을 한 번 실행합니다.
- **LLM 설정 탭** — Ollama 모드에서는 모델 이름을 직접 입력할 수 있어, 클라우드 모델도 쓸 수 있습니다(예: `gpt-oss:cloud`).
- **성능 프리셋** — 경량 / 표준 / 고성능, ASR/TTS 엔진 선택 + 기억 정리 빈도 + 모델 keep-alive를 한 번에 묶어 둡니다.
- **다국어 번역** — 선택적인 자막 / 음성 번역(기본값 꺼짐).
- **설치하자마자 작동** — 샘플 Live2D 모델 + 무료 클라우드 TTS(edge-tts) + 자동으로 내려받는 음성 인식(ASR) 모델(약 1GB이며, 맨 처음 실행할 때 한 번만 내려받고 몇 분 걸립니다)을 기본 제공합니다. 당신은 LLM만 연결하면 됩니다.
- **완전한 이중 언어 UI** — 번체 중국어(zh)와 영어(en).

---

## 스크린샷

![Warashi — 실제로 작동하는 당신의 Live2D AI 컴패니언](assets/warashi-hero.png)

*데스크톱에서 실행 중인 Warashi: 진짜로 대화하게 되는 Live2D 아바타.*

---

## 빠른 시작 (다운로드 → 더블클릭 → 대화)

가장 쉬운 길 — **터미널이 필요 없습니다.**

> **시작하기 전에: AI "두뇌"(LLM)가 필요합니다.**
> Warashi는 **몸과 얼굴**입니다 — 아바타, 음성, 기억. 실제로 생각하고 말하는 **두뇌**는 *당신*이 직접 준비하는 별도의 AI입니다. 설정 마법사를 진행하면서 설정할 수 있습니다(지금 당장 전부 결정할 필요는 없습니다). 쉬운 순서대로 선택지는 다음과 같습니다:
> - **(가장 쉬움, 추천) Ollama Cloud 무료 등급 사용** — API 키 불필요, 결제 불필요, 고성능 PC도 불필요. 무료 앱 **[Ollama](https://ollama.com)**를 설치하고 `ollama signin`으로 무료 계정(신용카드 불필요)을 만들면 `gpt-oss:20b-cloud` 같은 쓸 만한 클라우드 모델을 쓸 수 있습니다. Ollama의 서버에서 돌아가므로 당신의 컴퓨터가 빠를 필요가 없습니다. **$0**이지만, 가벼운 사용용 한도가 있습니다(아래 옵션 C 참고).
> - **(A) 유료 클라우드 AI 사용** — [OpenAI](https://platform.openai.com/api-keys), Claude, 또는 Gemini에서 API 키를 받아 붙여넣습니다. 작은 모델이라면 보통 **대화 한 번에 몇 원 수준**의 비용밖에 들지 않습니다.
> - **(B) 무료 로컬 AI 실행** — 무료 앱 **[Ollama](https://ollama.com)**를 설치하면 두뇌를 당신의 컴퓨터에서 직접 돌립니다. **비용은 무료**지만, 어느 정도 성능이 되는 컴퓨터가 필요합니다.
>
> 아직 아무것도 다운로드할 필요는 없습니다 — 아래 설치가 끝나기를 기다리는 동안, 어느 쪽으로 마음이 기우는지만 알아 두세요.

1. **Warashi 다운로드.** [**Releases 페이지**](https://github.com/inni918/warashi/releases/latest)로 가서 최신 `Warashi-*.zip`을 받은 뒤 압축을 풉니다(예: 바탕화면에). _(또는 메인 repo 페이지에서 초록색 **`<> Code`** 버튼 → **Download ZIP**.)_
2. 압축을 푼 폴더 안에서 **런처를 더블클릭**합니다:
   - **macOS:** `start-companion.command`
   - **Windows:** `start-companion.bat`
   - 첫 실행 때 모든 것을 설치하며(`uv` 다음에 의존성), 몇 분 걸릴 수 있습니다. **그 창은 닫지 마세요 — 그게 바로 서버입니다.**
3. 브라우저가 **http://localhost:12393**으로 열립니다. 첫 실행 시 **설정 마법사**가 나타납니다: **API 키 붙여넣기**(OpenAI / Claude / Gemini) **또는** **로컬 Ollama 모델 선택** 중 하나를 합니다. 마법사는 저장하기 전에 당신의 선택을 테스트합니다.

   ![Warashi 첫 실행 설정 마법사](assets/warashi-setup.png)

   *첫 실행 설정 마법사, 여기서 당신의 AI "두뇌"를 연결합니다.*

4. **새 두뇌가 작동하도록 재시작하세요.** 2단계의 **바로 그 런처/터미널 창을 닫아** 종료하면(서버가 멈춥니다), **다시 런처를 더블클릭**해서 새 LLM과 함께 다시 시작합니다. (앱도 LLM 변경은 "재시작 후 — 또는 캐릭터를 한 번 전환한 후 적용됩니다"라고 안내합니다.) 그런 다음 대화를 시작하세요. 오디오를 켜려면 페이지를 한 번 클릭합니다.

> **macOS Gatekeeper (첫 실행에만):** 더블클릭하면 *"확인되지 않은 개발자가 배포했기 때문에 열 수 없습니다"*라고 나올 수 있습니다. 서명되지 않은 오픈소스 앱에서는 정상입니다. `start-companion.command`를 **마우스 오른쪽 클릭** → **열기** → 대화상자에서 **열기**를 누르세요. 한 번 허용하고 나면 그 다음부터는 더블클릭으로 됩니다. (우리는 서명/공증된 빌드를 제공하지 않습니다 — 무료 등급이니까요.)

> **Windows SmartScreen (첫 실행에만):** 더블클릭하면 파란색 **"Windows의 PC 보호"** 상자가 나올 수 있습니다. 서명되지 않은 오픈소스 앱에서는 정상입니다. **추가 정보** → **실행**을 누르세요. 한 번 허용하면 다시 묻지 않습니다.

설치하자마자 기본으로 제공되는 **mao** 샘플 Live2D 모델과 **edge-tts**(무료 클라우드 음성, GPU 불필요)를 사용합니다. 첫 실행 때 음성-텍스트 변환(STT) 모델도 자동으로 내려받는데 —— 이 모델은 약 **1GB**라서, **맨 처음 실행에서는 한 번만 일어나는 다운로드 + 압축 해제에 몇 분이 걸릴 수 있습니다**. 이 동안 런처 창이 멈춘 것처럼 보일 수 있지만 멈춘 게 아닙니다. **닫지 말고 끝날 때까지 기다리세요.** 이건 처음 한 번만 일어납니다.

### 터미널이 더 편하신가요? (고급)

대부분의 사람은 위의 **Download ZIP** 경로를 쓰면 됩니다. 터미널이 익숙하다면 대신 repo를 clone할 수 있습니다. **Python ≥ 3.10, < 3.13**과 [`uv`](https://github.com/astral-sh/uv)가 필요합니다.

```bash
git clone https://github.com/inni918/warashi.git && cd warashi
uv sync                  # installs dependencies
uv run run_server.py     # start the server
# open http://localhost:12393  → setup wizard → chat
```

마법사가 당신의 LLM 선택을 `conf.yaml`에 대신 기록해 줍니다. 물론 직접 손으로 편집할 수도 있습니다(아래 참고).

---

## LLM 설정 (필수)

클라우드 LLM용 API 키 **또는** 실행 중인 로컬 LLM, **둘 중 하나**가 필요합니다. 컴패니언 대화에는 저렴한 모델로도 충분하며, 최상급 모델이 필요하지 않습니다.

### 옵션 A — 클라우드 API 키 (OpenAI / Claude / Gemini)

가장 쉽습니다. **첫 실행 설정 마법사**(또는 나중에 **LLM 설정 탭**)에서 OpenAI, Claude, 또는 Gemini의 API 키를 붙여넣습니다. 마법사가 빠른 테스트 호출로 키를 검증한 뒤 `conf.yaml`에 기록합니다. 새 LLM이 적용되도록 **저장 후 런처를 재시작**하세요.

### 옵션 B — 로컬 Ollama

[Ollama](https://ollama.com)를 설치하고, 모델을 받은 뒤(예: `ollama pull qwen2.5`), 마법사 / 설정 탭에서 Ollama를 고릅니다. 완전히 로컬이며, API 키도, 클라우드 비용도 없습니다.

### 옵션 C — Ollama를 통한 클라우드 모델 (가장 쉬움·추천, 예: `gpt-oss:20b-cloud`)

**비기술 사용자에게 API 키가 필요 없는 가장 쉬운 길입니다.** Ollama는 자사 서버에서 돌아가는 강력한 **클라우드** 모델을 프록시하므로, 당신의 컴퓨터가 빠를 필요가 없습니다 — 게다가 무료 등급은 **$0, 신용카드 불필요**입니다. 설정:

1. [ollama.com/download](https://ollama.com/download)에서 Ollama를 설치합니다.
2. 터미널에서 **`ollama signin`**을 실행해 무료 계정(카드 불필요)을 만듭니다.
3. **`ollama pull gpt-oss:20b-cloud`**를 실행해 추천 모델을 받습니다.
4. Warashi의 **Ollama 모드**에서 모델 이름 `gpt-oss:20b-cloud`를 입력합니다.

받아 온 클라우드 모델은 Warashi가 이미 쓰는 동일한 로컬 Ollama 엔드포인트(OpenAI 호환, `localhost:11434`)를 통해 제공되므로, Warashi의 기존 Ollama 모드가 그대로 동작합니다.

**추천 모델:** `gpt-oss:20b-cloud` — "Low Usage"로 표시되어 무료 한도를 가장 잘 견딥니다. 더 강력한 `qwen3.5:cloud`나 `minimax-m3:cloud`는 성능은 더 좋지만 한도를 더 빨리 소진합니다.

> **무료 등급에 대해 솔직히:** 정말로 **$0, 신용카드 불필요, 무료 계정만** 있으면 됩니다 — 다만 *가벼운 사용*용 등급입니다. Ollama는 **한 번에 클라우드 모델 하나**만 허용하며, 세션 한도는 약 5시간마다, 주간 한도는 7일마다 초기화됩니다. Ollama는 정확한 수치를 **공개하지 않으므로**, 많이 대화하면 일시적으로 한도에 도달해 초기화될 때까지 기다려야 할 수 있습니다. 추론이 **Ollama의 서버(당신의 기기가 아님)**에서 돌아가므로, 완전히 비공개로 두고 싶은 내용은 보내지 마세요.

> **중요:** Ollama를 통한 클라우드 모델은 먼저 로그인되어 있어야 합니다 — 사용하기 전에 터미널에서 **`ollama signin`**을 실행하세요. 그렇지 않으면 호출이 실패합니다.

### ⚠️ 추론("thinking") 모델은 지원되지 않습니다

**`glm-4.7:cloud`** 같은 추론 모델은 답변을 별도의 `reasoning` 필드에 넣고, 일반 `content` 필드는 **비워 둡니다**. 이 앱은 `content`만 읽기 때문에, 추론 모델은 **빈 응답**으로 나타납니다 — 그리고 읽어 줄 내용이 없으니 **음성도 나오지 않습니다**.

**권장:** 일반(비추론) 대화 모델을 고르세요. 작고 빠른 모델이 어차피 더 자연스럽고 지연이 적은 컴패니언을 만들어 줍니다.

> 수동 편집: LLM 설정은 `conf.yaml`의 `character_config → agent_config → llm_configs → openai_compatible_llm` 아래에 있습니다. 파일 안의 주석이 자신의 키로 OpenAI / Claude / Gemini를 가리키는 방법을 보여 줍니다. 편집 후에는 런처를 재시작하세요.

---

## 기타 설정

### 기억 (핵심 + 심층 회상)
기본으로 켜져 있습니다. 각 캐릭터는 `chat_history/<conf_uid>/core_memory.md`에 자신의 기억을 보관합니다 — 페르소나에 주입되는 핵심 기억에 더해, 매 대화 차례마다 LLM이 정리합니다(무엇을 남길지는 모델이 판단). 선택적으로 켤 수 있는 **FTS5 trigram 심층 회상**은 더 긴 기간의 기억이 필요할 때 전체 기록을 검색합니다. 기억 용량 상한은 설정에서 조절하세요.

### 캐릭터
앱 안에서 캐릭터를 생성 / 편집 / 전환 / 삭제합니다 — 각자 고유한 이름, 페르소나, Live2D 스킨, 음성, 그리고 **분리된 기억**을 가집니다. 자신의 Live2D 모델을 추가하려면 `live2d-models/<name>/` 아래에 넣고, `model_dict.json`에 항목을 추가한 뒤 선택하면 됩니다. **저작권 있는 캐릭터 모델을 공개 repo에 commit하지 마세요.**

#### 더 많은 캐릭터 (선택)
라이선스 안전을 위해, Warashi는 **무료 Live2D 오리지널 캐릭터 3개**(`mao_pro`, `haru`, `hiyori`)만 기본 제공합니다. 더 많이 원하시나요 — 남성 집사 캐릭터 **Natori**까지 포함해서? 무료 공식 Live2D 샘플 모델을 직접 공식 페이지에서 받아 넣을 수 있습니다. **[Live2D 샘플 모델 페이지](https://www.live2d.com/en/learn/sample/)**에서 Live2D 자체 라이선스에 따라 받으세요 — 우리는 그것들을 재배포하지 않습니다. 방법은 [`docs/add-live2d-character.md`](docs/add-live2d-character.md)를 참고하세요.

### 성능 프리셋
**경량 / 표준 / 고성능** 프리셋은 ASR/TTS 엔진 선택, 기억 정리 빈도, 모델 keep-alive를 한 번에 묶어 둡니다. 사양이 낮은 컴퓨터에서는 경량을, 하드웨어가 충분하면 고성능을 고르세요.

### 능동적 화제 & 뉴스
컴패니언은 일정 시간 동안 조용하면 화제를 꺼냅니다. 선택적으로, 번들된 뉴스 헬퍼(`scripts/news_topics.py`)로 최신 헤드라인을 가져와 그 화제를 갱신할 수 있고 — 순수 표준 라이브러리, API 키 불필요 — 이를 일정에 맞춰(cron / launchd / Task Scheduler) 예를 들어 몇 시간마다 실행할 수 있습니다.

### 수면 / 조용 모드
"晚安"이라고 말하면 먼저 말 거는 것을 멈춥니다. 다음 메시지에서 재개됩니다. 키워드는 설정으로 바꿀 수 있습니다.

### 번역
선택적인 다국어 자막/음성 번역, **기본값은 꺼짐**입니다(`conf.yaml`의 `tts_preprocessor_config → translator_config`).

### 음성
기본값은 **edge-tts**(무료, 하드웨어 불필요)입니다. 고품질의 로컬/맞춤 음성을 원하면 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)를 서비스로 실행하고 설정이 그것을 가리키게 하세요(GPU 또는 Apple Silicon 필요). 실제 사람의 목소리를 음성 복제(voice-cloning)하는 것에 대한 법적 책임은 당신에게 있습니다.

---

## 가이드

- [휴대폰 / 태블릿에서 사용하기 (Tailscale)](docs/remote-access-tailscale.md) — 집 네트워크 밖에서도 다른 기기에서 컴패니언에 접속할 수 있습니다.
- [GPT-SoVITS로 맞춤 음성 만들기](docs/custom-voice-gpt-sovits.md) — 캐릭터에게 복제하거나 맞춤 제작한 음성을 입혀 보세요.
- [자신의 Live2D 캐릭터 추가하기](docs/add-live2d-character.md) — 모델을 넣고 그것으로 전환하세요.

## 크레딧 & 라이선스

이 프로젝트는 그것이 기반으로 삼은 상류(upstream) 작업 없이는 존재할 수 없었습니다. [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)에도 **star를 누르고 후원해** 주세요.

- **상류(Upstream):** [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) — 그 서버 측 코드는 MIT이며, Copyright (c) 2025 Yi-Ting Chiu입니다.
- **이 fork가 추가한 것**(기억, 능동적 화제, 끼어들기, 조용 모드, 캐릭터 관리, 설정 마법사, 성능 프리셋, 이중 언어 UI) — MIT.
- **번들된 웹 프론트엔드** — `frontend/`에 있는 컴파일된 웹 번들은 Open-LLM-VTuber-Web 프론트엔드이며, **Open-LLM-VTuber License 1.0**(Apache-2.0 + 추가 조건) 하에 있습니다. 무료, 비상업적 사용 및 재배포는 허용됩니다. 상업적 리브랜딩, 유료 호스팅/SaaS, 또는 유료 제품에 임베드하는 경우에는 Open-LLM-VTuber 조직으로부터 별도의 상업 라이선스를 받아야 합니다. 이 fork는 무료이고 비상업적이므로 해당 라이선스가 허용하는 범위 안에 있습니다. [`NOTICE`](./NOTICE)를 참고하세요.
- **Live2D Cubism & 번들된 샘플 모델** — 번들된 **mao_pro** / **haru** / **hiyori** 모델은 Live2D Inc.의 샘플 데이터이며, **Live2D Free Material License** 하에 사용됩니다(자세한 내용은 [`LICENSE-Live2D.md`](./LICENSE-Live2D.md)). 필수 출처 표기:
  > This content uses sample data owned and copyrighted by Live2D Inc.

  이들은 무료 기본값으로 **수정 없이** 번들되어 있습니다. **유료/상업 빌드에서는 반드시** 자신의 CC0 / 라이선스를 받은 / 의뢰 제작한 모델로 **교체하세요.**
- **기타 구성 요소**(각 라이선스는 [`NOTICE`](./NOTICE) 참고): GPT-SoVITS (MIT, 선택적 TTS), sherpa-onnx (Apache-2.0, ASR 엔진 — SenseVoice 모델은 자체 라이선스가 있음; 또는 Whisper 사용), Silero VAD (MIT), edge-tts (Microsoft의 온라인 TTS 서비스 사용), DeepLX (비공식 DeepL 엔드포인트 — 프로덕션에는 공식 DeepL API 사용).

**저작권 있는 캐릭터, 아트워크, 음성, 또는 학습된 음성 모델을 배포하지 마세요.** 이 repo는 중립적인 기본값만 제공합니다. 나머지는 직접 가져오세요.

### License

이 fork 자체의 소스 코드는 **MIT License** 하에 공개되며, Open-LLM-VTuber의 MIT 라이선스 서버 코드(Copyright (c) 2025 Yi-Ting Chiu) 위에 올라가 있습니다. 다만 **프로젝트 전체가 단순히 MIT인 것은 아닙니다**: `frontend/`에 번들된 컴파일 웹 프론트엔드는 **Open-LLM-VTuber License 1.0**(Apache-2.0 + 추가 조건) 하에 있고, 번들된 Live2D 샘플 모델은 각자의 Live2D 조건을 따릅니다. 완전하고 정확한 내용은 [`LICENSE`](./LICENSE), [`NOTICE`](./NOTICE), 그리고 [`LICENSE-Live2D.md`](./LICENSE-Live2D.md)를 참고하세요.

---

## 이 프로젝트 후원하기

이건 무료 오픈소스 프로젝트입니다 — 페이월은 없습니다. 도움이 되었다면 후원은 감사하지만, 절대 필수는 아닙니다:

- **Ko-fi:** [ko-fi.com/leonhsueh](https://ko-fi.com/leonhsueh)
- **GitHub Sponsors:** 곧 공개

그리고 이 프로젝트가 기반으로 삼은 상류 프로젝트 — [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)도 후원해 주세요.

---

## 기여하기

Issue와 pull request를 환영합니다.

- 버그와 기능 아이디어는 **Issues**에 올려 주세요.
- 코드 변경은 명확한 설명과 함께 **Pull Request**를 열어 주세요.
- 저작권 있는 캐릭터, 아트워크, 음성, 또는 학습된 음성 모델은 **추가하지 말아 주세요** — repo가 중립적인 기본값만으로 배포 가능한 상태를 유지하도록 해 주세요.
