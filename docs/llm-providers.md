# LLM 서비스 제공자 설정 가이드

이 문서는 처음 설정하는 사용자를 위해 LLM 설정 방식을 고르는 법, 웹 설정 페이지 「AI 模型配置」(AI 모델 설정)의 프리셋을 `.env` / GitHub Actions에 옮기는 법, 자주 나오는 검사 오류를 처리하는 법을 설명합니다.

> 이 페이지는 새로운 외부 provider, 모델 이름, Base URL 호환 동작을 도입하지 않으며, 설정 참고 자료와 공식 출처만 정리합니다. 실제 호환성은 저장소의 현재 실행 의존성과 테스트 결과를 기준으로 합니다.

> - 실행 기반: `requirements.txt`는 현재 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`으로 고정되어 있으며, 호환 의미는 이 버전 제약 아래의 구현을 기준으로 합니다.
> - 검증: 시스템 설정 경로의 회귀 테스트는 `tests/test_system_config_service.py`와 `tests/test_system_config_api.py`를, `Web` 쪽 설정 페이지 동작의 회귀 테스트는 기존 컴포넌트 테스트를 보세요.
> - 되돌리기: 예전 변수는 자동으로 옮기지 않고 그대로 둡니다. Web/데스크톱에서 백업을 내보낸 뒤 `POST /api/v1/system/config/import`로 되돌리거나, 과거의 `LLM_*` / `LITELLM_*` / `AGENT_*` / `VISION_MODEL` 설정을 직접 복원할 수 있습니다.

실제로 쓸 수 있는 모델, 사용 한도, 지역 제한, 가격은 각 서비스 제공자의 콘솔을 기준으로 합니다. 모델 목록을 불러오지 못하면 웹에서 모델 이름을 직접 입력할 수 있습니다. 웹 설정 페이지에 보이는 provider 기능 태그, 공식 출처 링크, 설정 주의 사항은 정적 provider template에서 온 것으로, 설정 참고용일 뿐 실행 시 기능이 검증되었다는 뜻은 아닙니다.

## 먼저 설정 방식 고르기

| 방식 | 이런 분께 | 주요 변수 | 설명 |
| --- | --- | --- | --- |
| 최소 legacy | 모델 하나만 빨리 돌려 보고 싶은 사용자 | `LITELLM_MODEL` + 해당 provider key | 변수가 가장 적어 로컬에서 빨리 시작하기 좋습니다. 복잡한 fallback에는 맞지 않습니다. |
| Channels | 여러 provider, 여러 key, fallback이 필요한 사용자 | `LLM_CHANNELS` + `LLM_<CHANNEL>_*` | 기본으로 권장하는 방식입니다. 웹 설정 페이지가 저장하는 것도 이 단계의 설정입니다. |
| YAML | LiteLLM 라우팅, 부하 분산, 기업 게이트웨이에 익숙한 사용자 | `LITELLM_CONFIG` / `LITELLM_CONFIG_YAML` | 우선순위가 가장 높습니다. 일단 유효하게 적용되면 이번 요청에는 Channels와 legacy가 쓰이지 않습니다. |

우선순위는 그대로입니다: `LITELLM_CONFIG` / `LITELLM_CONFIG_YAML` > `LLM_CHANNELS` > legacy provider keys. P4는 문서만 보완하며, 예전 설정을 옮기거나 지우거나 몰래 고쳐 쓰지 않습니다.

Generation backend 설정은 그보다 바깥쪽에서 실행 방식을 고르는 계약입니다. Phase 4는 `GENERATION_BACKEND=litellm|codex_cli|claude_code_cli|opencode_cli`를 지원하지만, 로컬 CLI backend는 LiteLLM provider가 아닙니다. `LITELLM_MODEL=codex_cli/...`, `LITELLM_MODEL=claude_code_cli/...`, `LITELLM_MODEL=opencode_cli/...`처럼 설정하지 마세요. `codex_cli` preset은 `codex --ask-for-approval never exec --sandbox read-only --output-last-message <temp-file> -`를 쓰며, 무인 실행 승인 정책을 고정하고 읽기 전용 범위를 유지합니다. `claude_code_cli` preset은 `claude --safe-mode --tools "" --disallowedTools "mcp__*" --strict-mcp-config --no-session-persistence --output-format json -p <static instruction>`를 쓰며, 전체 DSA prompt는 stdin으로 넘기고 JSON envelope의 `result/success` 필드에서만 최종 텍스트를 꺼냅니다. 매개변수 근거는 [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)를 보세요. `opencode_cli` preset은 `opencode --pure run --format json [--model <OPENCODE_CLI_MODEL>] <static instruction> --file <temp prompt file>`을 쓰며, `OPENCODE_CLI_MODEL`을 명시했을 때만 `--model`을 붙입니다. 전체 DSA prompt는 권한이 제한된 임시 파일로 넘기고, 도구 이벤트가 없는 JSON event text 출력에서만 최종 텍스트를 꺼냅니다. 매개변수 근거는 [OpenCode CLI reference](https://opencode.ai/docs/cli), 설정 병합 의미는 [OpenCode config reference](https://opencode.ai/docs/config)를 보세요. 진단용 stdout/stderr와 최종 응답은 함께 `GENERATION_BACKEND_MAX_OUTPUT_BYTES` 총량 제한을 받으며, 넘으면 구조화된 `output_too_large`를 돌려줍니다. `GENERATION_FALLBACK_BACKEND=`를 빈 값으로 두면 로컬 `.env`에서 backend 단위 fallback이 꺼지고, 설정하지 않으면 기본으로 `litellm`으로 돌아갑니다. 기본 GitHub Actions workflow는 이 변수가 없으면 명시적으로 `litellm`을 씁니다. fallback을 끄려면 primary backend와 같은 값으로 두어 아무 일도 하지 않게(self no-op) 하면 됩니다. Agent 도구 호출은 여전히 LiteLLM을 씁니다. 웹 설정 페이지에는 `AGENT_GENERATION_BACKEND=auto|litellm`만 나오며, 직접 `codex_cli|claude_code_cli|opencode_cli`를 써 넣어도 text-only Agent mode가 켜지지 않고 tool-calling을 지원하지 않는다는 명확한 진단만 돌아옵니다.

생성 backend 상태 API와 웹 패널은 가벼운 검사와 연기 테스트(smoke test)를 나눠 보여 줍니다. 빠른 검사는 저장된 `.env`, 실행 시 대체 값, 현재 초안만 읽으며, 설정을 쓰거나 실행 환경을 다시 불러오거나 실제 모델 요청을 보내지 않습니다. JSON 연기 테스트만 고정된 JSON 프롬프트와 schema로 실제 요청을 보냅니다. `health_status`와 `last_error_code/message`는 이번 계산 결과이며, 과거의 마지막 오류를 뜻하지 않습니다. 로컬 CLI preset의 `supports_tools=false`는 DSA Agent 도구 호출 경로를 지원하지 않는다는 뜻일 뿐, 일반 텍스트 생성을 못 한다는 뜻은 아닙니다.

Phase 6a Tool Surface는 공용 내부 도구 경계를 유지합니다. 통일된 DSA 도구 schema, public descriptor, MCP-compatible descriptor, scope guard, 구조화된 오류, 감사 요약, 민감 정보를 가린 진단이 여기에 포함됩니다. stock-scoped 도구 호출은 반드시 `ToolAccessContext.stock_scope`를 명시해야 하며, `stock_code` 매개변수가 있는데 stock scope를 선언하지 않은 도구는 fail-closed합니다. 이 공용 경계는 그대로 두며, `codex_cli` generation backend, MCP server, SDK, 최종 텍스트 fallback은 Agent 도구 성공으로 치지 않습니다.

## Codex App Server 종목 질문 기능 종료

Codex App Server 종목 질문(问股) backend는 제거되었습니다. `AGENT_BACKEND`는 `auto`(권장, 기본 LiteLLM 유지)나 `litellm`만 지원합니다. 예전 `codex_app_server` 값은 불러오고, 표시하고, 내보낼 수는 있지만, 실행 요청은 준비와 제출 수락 전에 `backend_removed`를 돌려주며 모델, 계정, provider를 자동으로 바꾸지 않습니다. 「设置 → Agent 设置 → 问股生成方式」(설정 → Agent 설정 → 종목 질문 생성 방식)에서 올바른 값을 직접 골라 저장하세요. 예전 값이 남아 있어도 관계없는 설정 저장은 막지 않지만, 예전 값을 명시적으로 저장하거나 가져오면 거부하며 일부만 기록하지도 않습니다. 상태와 초안 미리 보기는 설정만 확인하며, Codex 명령이나 schema/version 확인을 실행하지 않고 모델도 호출하지 않습니다. 과거 대화, 종목 식별, Skill, 단일/다중 Agent, provider trace는 원래 계약을 유지합니다. 별도의 `GENERATION_BACKEND=codex_cli` 일반 리포트와 그 밖의 generation-only 기능은 이번 제거와 관계없으며, 여전히 각자의 CLI와 원래 의존성이 필요합니다.

## 웹 설정 페이지에서 설정하기

Channels 설정은 웹 설정 페이지에서 하는 것을 우선 권장합니다.

1. 설정 페이지의 「AI 模型配置」(AI 모델 설정)를 엽니다.
2. 「快速添加渠道」(빠른 채널 추가)에서 서비스 제공자 프리셋을 고릅니다.
3. API Key를 넣고, 필요하면 「获取模型」(모델 가져오기)을 누릅니다.
4. 기본 모델, Agent 기본 모델, 예비 모델, Vision 모델을 고른 뒤 저장합니다.
5. 「测试连接」(연결 테스트)을 눌러 인증, 모델 이름, 사용 한도, 응답 형식이 정상인지 확인합니다.
6. JSON / tools / stream / vision 기능을 확인하려면 「运行时能力检测」(실행 시 기능 검사)을 직접 체크한 뒤 실행합니다. 이 검사는 실제 LLM 요청을 보내며, 결과는 현재 계정, 모델, endpoint에 대한 한 번의 best-effort 검사일 뿐입니다. `.env`에 기록되지 않으며 저장을 막지도 않습니다.

## Channels 예시

### Modelflare

[Modelflare에 가입](https://modelflare.dev/sign-up?utm_source=github&utm_campaign=daily_stock_analysis)하고 API Key를 만든 뒤 OpenAI-compatible 채널로 씁니다.

```env
MODELFLARE_KEY=sk-xxx
```

`MODELFLARE_KEY`만 넣으면 백엔드가 Modelflare를 자동으로 켭니다. 기본 주소는 `https://modelflare.dev/v1`, 모델은 `openai/gpt-6.1-sol`이며, 채널 이름, 주소, 모델을 따로 넣지 않아도 됩니다. 명시적인 YAML이나 `LLM_CHANNELS`가 우선하며, Modelflare 채널을 명시해 넣은 Key가 이 줄임 설정보다 우선합니다. Key를 비우거나 채널을 끄면 쓰지 않게 됩니다. 이 추론은 저장된 설정을 고쳐 쓰지 않습니다.

`modelflare` 채널 하나만 선언하고 채널 모델 목록을 비워 두었다면, 기본 모델을 설정하지 않았을 때 `openai/gpt-6.1-sol`을 씁니다. 기본 모델을 설정했다면 백엔드는 `LITELLM_MODEL`과 `openai/` 접두사가 붙은 예비 모델을 재사용하며, 기본 모델은 `openai/<모델 이름>`을 씁니다. 명시적인 `LLM_MODELFLARE_MODELS`가 우선하며, 여러 채널을 쓸 때는 채널마다 모델을 따로 선언해야 합니다. 이 추론은 저장된 설정이나 모델 선택을 고쳐 쓰지 않습니다.

채널 이름이 `modelflare`이면 비워 두거나 넣지 않은 접속 주소에는 자동으로 `https://modelflare.dev/v1`을 씁니다. 명시적인 `LLM_MODELFLARE_BASE_URL`이 우선합니다. 이 주소는 기본으로 `openai` 프로토콜로 인식되고, API는 기본으로 `chat_completions`입니다. `LITELLM_MODEL`을 설정하지 않으면 첫 번째 채널 모델을 씁니다. 기본 모델도 계정에 접근 권한이 있어야 하며, API Key를 자동으로 채워 주지는 않습니다.

`gpt-6.1-sol`은 이 프로젝트의 Modelflare 기본 모델입니다. 실제 모델 목록과 사용 가능 여부는 계정 권한, 콘솔, 웹 설정 페이지 「测试连接」(연결 테스트) 결과를 기준으로 합니다. 채널 템플릿은 새 설정의 초깃값만 정하며, 저장된 채널, 기본 모델, fallback을 고쳐 쓰지 않습니다.

### DeepSeek 공식 채널

```env
LLM_CHANNELS=deepseek
LLM_DEEPSEEK_PROTOCOL=deepseek
LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_DEEPSEEK_API_KEY=sk-xxx
LLM_DEEPSEEK_MODELS=deepseek-v4-flash,deepseek-v4-pro
LITELLM_MODEL=deepseek/deepseek-v4-flash
```

### OpenAI-compatible 통합 서비스 또는 사용자 정의 게이트웨이

```env
LLM_CHANNELS=my_proxy
LLM_MY_PROXY_PROTOCOL=openai
LLM_MY_PROXY_API_SURFACE=chat_completions
LLM_MY_PROXY_BASE_URL=https://your-proxy.example.com/v1
LLM_MY_PROXY_API_KEY=sk-xxx
LLM_MY_PROXY_MODELS=gpt-5.5,claude-sonnet-4-6
```

OpenAI-compatible Base URL에는 서비스 제공자의 호환 진입점까지만 넣고, `/chat/completions`를 덧붙이지 마세요. 로컬 `.env`, Docker, 자체 호스팅 스크립트에서는 사용자 정의 channel을 바로 쓸 수 있습니다. GitHub Actions에서는 workflow가 같은 이름의 `LLM_MY_PROXY_*` 변수를 명시적으로 넘겨줘야 합니다.
샤오미 MiMo 예시도 마찬가지입니다. 로컬 `.env`, Docker, 자체 호스팅 스크립트에 맞으며, GitHub Actions에서 `LLM_CHANNELS=mimo`를 쓰려면 workflow에 `LLM_MIMO_*` 매핑을 직접 추가해야 적용됩니다.

### Anspire Responses API(GPT-5.6 이름은 관측 예시)

Anspire 공식 연결 페이지는 `https://open-gateway.anspire.cn/v6/responses` 호출 방법을 공개하고 있습니다: <https://open.anspire.cn/model?link=sample&tab=models>. 실시간 `/models`, 서비스 제공자 설명, 연결 테스트로 대상 모델이 Responses를 쓴다는 것을 확인했다면, 모델을 같은 채널에 두고 API Surface를 명시적으로 `responses`로 설정할 수 있습니다. 아래 `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`는 현재 게이트웨이에서 관측한 예시이며, 장기적인 모델 목록으로 약속하지 않습니다.

```env
LLM_CHANNELS=anspire
LLM_ANSPIRE_PROTOCOL=openai
LLM_ANSPIRE_API_SURFACE=responses
LLM_ANSPIRE_BASE_URL=https://open-gateway.anspire.cn/v6
LLM_ANSPIRE_API_KEY=sk-xxx
LLM_ANSPIRE_MODELS=gpt-5.6-sol,gpt-5.6-terra,gpt-5.6-luna
LITELLM_MODEL=openai/gpt-5.6-sol
LITELLM_FALLBACK_MODELS=openai/gpt-5.6-terra,openai/gpt-5.6-luna
```

이 기능은 `gpt-5.6-*`라는 이름에 의존하지 않습니다. 서비스 제공자가 Responses 전용이라고 밝힌 모델이라면 같은 방식으로 설정할 수 있습니다. 모델 목록과 계정 권한은 바뀔 수 있으니 서비스 제공자의 `/models` 응답, 공식 설명, 실제 연결 테스트를 기준으로 하세요. 채널 하나에는 API Surface 한 가지만 쓸 수 있습니다. Anspire의 Chat Completions 모델도 함께 쓰려면 그 모델들을 위한 OpenAI-compatible 채널을 따로 만들고, 두 종류의 모델을 한 채널에 섞지 마세요. 웹 설정 페이지의 「测试连接」(연결 테스트)은 현재 고른 Surface를 쓰며, 실행 중 실패해도 다른 endpoint로 몰래 바꾸지 않습니다.

## 자주 쓰는 서비스 제공자 프리셋

| 서비스 제공자 | 채널 이름 | 프로토콜 | Base URL | 모델 예시 |
| --- | --- | --- | --- | --- |
| Modelflare | `modelflare` | `openai` | `https://modelflare.dev/v1` | `gpt-6.1-sol`(계정에서 쓸 수 있는 모델 기준) |
| AIHubmix | `aihubmix` | `openai` | `https://aihubmix.com/v1` | `gpt-5.5,claude-sonnet-4-6,gemini-3.1-pro-preview` |
| OpenAI | `openai` | `openai` | `https://api.openai.com/v1` | `gpt-5.5,gpt-5.4-mini` |
| DeepSeek | `deepseek` | `deepseek` | `https://api.deepseek.com` | `deepseek-v4-flash,deepseek-v4-pro` |
| Gemini | `gemini` | `gemini` | 비워 둠 | `gemini-3.1-pro-preview,gemini-3-flash-preview` |
| Anthropic Claude | `anthropic` | `anthropic` | 비워 둠 | `claude-sonnet-4-6,claude-opus-4-7` |
| Kimi / Moonshot | `moonshot` | `openai` | `https://api.moonshot.cn/v1` | `kimi-k2.6,kimi-k2.5` |
| 통이첸원(Qwen) / DashScope | `dashscope` | `openai` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.6-plus,qwen3.6-flash` |
| Zhipu(즈푸) GLM | `zhipu` | `openai` | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.1,glm-4.7-flash` |
| MiniMax | `minimax` | `openai` | `https://api.minimax.io/v1` | `MiniMax-M3.1-Flash,MiniMax-M3` |
| 샤오미 MiMo | `mimo` | `openai` | 공식 콘솔에서 제공(Actions 기본 매핑 없음) | 공식 문서/콘솔 기준 |
| Volcengine Ark(훠산팡저우) / Doubao | `volcengine` | `openai` | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-1-6-251015,doubao-seed-1-6-thinking-251015` |
| SiliconFlow | `siliconflow` | `openai` | `https://api.siliconflow.cn/v1` | `deepseek-ai/DeepSeek-V3.2,Qwen/Qwen3-235B-A22B-Thinking-2507` |
| OpenRouter | `openrouter` | `openai` | `https://openrouter.ai/api/v1` | `~anthropic/claude-sonnet-latest,~openai/gpt-latest` |
| Requesty | `requesty` | `openai` | `https://router.requesty.ai/v1`(EU: `https://router.eu.requesty.ai/v1`) | `claude-sonnet-4-6,gpt-5.4` |
| Anspire Open(호환) | `anspire` | `openai` | `https://open-gateway.anspire.cn/v6`(예시) | `Doubao-Seed-2.0-lite,Doubao-Seed-2.0-pro,qwen3.5-flash`(예시) |
| Ollama | `ollama` | `ollama` | `http://127.0.0.1:11434` | `llama3.2,qwen2.5` |

<a id="官方来源与兼容性"></a>

## 공식 출처와 호환성

| 서비스 제공자 | 공식 출처 | 호환 안내 |
| --- | --- | --- |
| Modelflare | [빠른 시작](https://docs.modelflare.dev/quickstart/), [접속 endpoint](https://docs.modelflare.dev/guides/endpoints/), [모델과 그룹](https://docs.modelflare.dev/guides/models-and-groups/) | OpenAI-compatible Base URL `https://modelflare.dev/v1`과 표준 `LLM_MODELFLARE_*` 채널 설정을 씁니다. 이 프로젝트의 기본 모델은 `gpt-6.1-sol`이며, 모델 목록은 계정 권한과 콘솔을 기준으로 합니다. |
| OpenAI | [모델 목록](https://platform.openai.com/docs/models) | 공식 모델 페이지는 `gpt-5.5`부터 시작하길 권하며, 지연 시간이나 비용을 줄이려면 `gpt-5.4-mini`나 `gpt-5.4-nano`를 씁니다. |
| DeepSeek | [빠른 시작](https://api-docs.deepseek.com/) | 공식 OpenAI Base URL은 `https://api.deepseek.com`입니다. `deepseek-chat` / `deepseek-reasoner`는 2026-07-24에 지원이 중단되므로, 현재 템플릿은 `deepseek-v4-flash` / `deepseek-v4-pro`를 바로 씁니다. |
| Gemini | [모델 목록](https://ai.google.dev/gemini-api/docs/models) | Gemini 3.1 Pro / Gemini 3 Flash는 아직 preview입니다. 운영 안정성이 필요하면 콘솔에서 2.5 안정 모델로 되돌릴 수 있습니다. |
| Anthropic Claude | [모델 개요](https://docs.anthropic.com/en/docs/about-claude/models/all-models) | Claude의 현재 API ID에는 `claude-sonnet-4-6`, `claude-opus-4-7`이 있습니다. 가성비 면에서 Sonnet이 기본 선택으로 더 알맞습니다. |
| Kimi / Moonshot | [Kimi K2.6 빠른 시작](https://platform.kimi.com/docs/guide/kimi-k2-6-quickstart), [모델 목록](https://platform.kimi.com/docs/models) | 공식 권장 모델은 `kimi-k2.6`입니다. `kimi-k2` 계열은 2026-05-25에 종료되며, 예전 `moonshot-v1-*`는 안정적인 기존 작업용으로만 남아 있습니다. |
| 통이첸원(Qwen) / DashScope | [텍스트 생성](https://help.aliyun.com/zh/model-studio/text-generation-model/) | Bailian(百炼)은 `qwen3.6-plus`를 권장하며, 결과를 확인한 뒤 `qwen3.6-flash`로 비용을 줄일 수 있습니다. |
| Zhipu(즈푸) GLM | [모델 개요](https://docs.bigmodel.cn/cn/guide/start/model-overview), [GLM-5.1](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.1) | `glm-5.1`이 현재 대표 모델이며, `glm-4.7-flash`는 경량/무료 모델 예시입니다. |
| MiniMax | [Chat API](https://platform.minimax.io/docs/api-reference/text-chat), [Models](https://platform.minimax.io/docs/guides/models-intro), [Pricing](https://platform.minimax.io/docs/guides/pricing-paygo) | New channels recommend `MiniMax-M3.1-Flash` first, then `MiniMax-M3`, using `https://api.minimax.io/v1`. Discovery hides older MiniMax text recommendations without rewriting saved or manual IDs. Flash supports image input, 1,000,000 context tokens and 524,288 output tokens; standard input/output/cache-read prices are $0.15/$0.60/$0.015 per million tokens. Flash uses adaptive thinking by default: do not disable thinking or request effort `none`; supported effort values are `low`, `medium`, `high`, `xhigh`, `max` (default). M3 fallback estimates use the standard <=512K rate ($0.30/$1.20/$0.06); longer prompts and priority requests cost more and are not tiered by this fallback estimator. Legacy pricing remains for saved configurations. Subscription and regional access must be checked with the provider. |
| 샤오미 MiMo | 공식 문서 / 콘솔 | 현재 OpenAI-compatible 방식으로 연결하며, Base URL, 모델 이름, 권한은 MiMo 공식 문서/콘솔을 기준으로 합니다. `mimo` 채널은 저장소 기본 workflow에 명시적으로 매핑되어 있지 않으므로, Actions에서 쓰려면 이 문서의 "GitHub Actions 설정"에 따라 사용자 정의 매핑을 추가하세요. |
| Volcengine Ark(훠산팡저우) / Doubao | [온라인 추론(일반)](https://www.volcengine.com/docs/82379/2121998), [모델 목록](https://www.volcengine.com/docs/82379/1949118) | 공식 예시는 `https://ark.cn-beijing.volces.com/api/v3`와 `doubao-seed-1-6-251015`를 씁니다. Coding Plan을 쓴다면 그 전용 Base URL과 모델 이름으로 바꾸고, 이 표의 온라인 추론 템플릿을 그대로 쓰지 마세요. |
| SiliconFlow | [모델 목록](https://docs.siliconflow.cn/quickstart/models), [모델 목록 조회 API](https://docs.siliconflow.cn/cn/api-reference/models/get-model-list) | 플랫폼 모델은 실시간으로 바뀌며 `/models`에는 API Key가 필요합니다. 템플릿은 흔한 최신 모델 예시만 담고 있으니, 저장하기 전에 웹 설정 페이지에서 「获取模型」(모델 가져오기)을 눌러 계정에서 보이는지 확인하세요. |
| OpenRouter | [Models API](https://openrouter.ai/docs/api/api-reference/models/get-models) | OpenRouter는 `~anthropic/claude-sonnet-latest`, `~openai/gpt-latest` 같은 latest router alias를 지원합니다. 2026-05-03의 한 차례 수동 live smoke에서 Claude Sonnet latest를 기본 예시로 통과했으며, GPT latest는 계정 권한에 따라 바꿔 쓸 수 있는 대안으로 남겨 두었습니다. |
| Requesty | [Models API](https://docs.requesty.ai/api-reference/endpoint/models-list), [EU Routing](https://docs.requesty.ai/features/eu-routing) | 템플릿 예시는 슬래시 없는 managed 모델 ID이며, 실행 시 `openai/<model>`로 라우팅됩니다. Base URL이 `requesty.ai` 도메인이면 웹 「获取模型」(모델 가져오기)이 돌려준 vendor/model ID를 `openai/<vendor>/<model>`로 저장하고(예: `openai/openai/gpt-4o-mini`, `openai/anthropic/claude-sonnet-4-6`), 직접 입력한 `anthropic/...`, `vertex/...`에도 `openai/` 게이트웨이 라우팅을 자동으로 붙여 전체 ID를 그대로 Requesty에 보냅니다. `openai/`로 시작하는 ID만 LiteLLM 라우팅 접두사와 이름이 겹치므로, 직접 입력할 때는 `openai/openai/gpt-4o-mini`처럼 써야 합니다. 같은 API Key로 EU endpoint `https://router.eu.requesty.ai/v1`도 쓸 수 있습니다. |
| Anspire Open(호환) | [Anspire Open](https://open.anspire.cn/dsa?share_code=QFBC0FYC) | `ANSPIRE_API_KEYS`는 우선순위가 더 높은 OpenAI-compatible 소스를 설정하지 않았을 때 LLM 게이트웨이와 검색에 쓸 수 있습니다. 호환 예시는 `openai/Doubao-Seed-2.0-lite` + `https://open-gateway.anspire.cn/v6`이며, 사용 가능 여부는 콘솔과 모델 권한을 기준으로 합니다. |
| LiteLLM | [OpenAI-Compatible Endpoints](https://docs.litellm.ai/docs/providers/openai_compatible) | OpenAI-compatible endpoint는 실행 시 모델을 `openai/<model>`로 써야 하며, Base URL에는 서비스 제공자의 호환 진입점까지만 넣고 `/chat/completions`를 덧붙이지 않습니다. |

이 페이지의 프리셋은 설정 형태가 현재 의존성의 OpenAI-compatible 라우팅 규칙과 맞는다는 것만 보장합니다. 실제 연결 여부는 여전히 서비스 제공자 계정 권한, 지역, 사용 한도, 모델 개통 상태에 달려 있습니다. 현재 LiteLLM 버전 제약은 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`(`requirements.txt` 참고)입니다. 과거 최소 버전을 유지하고, PyPI 사고 버전을 명시적으로 빼며, 상한을 검증된 `<1.99.0`으로 좁혀 앞으로의 메이저 버전이 자동으로 들어오지 않게 합니다.

## OpenAI-compatible과 LiteLLM 규칙

- OpenAI-compatible provider의 channel `protocol`은 보통 `openai`입니다.
- `LLM_<CHANNEL>_API_SURFACE`의 기본값은 `chat_completions`이며, Responses 전용 모델은 명시적으로 `responses`로 설정합니다. Responses 채널은 프로토콜과 각 모델의 실제 LiteLLM provider가 모두 `openai`여야 합니다. 직접 연결 provider 목록은 현재 설치된 LiteLLM registry에서 가져오며, 시스템 설정 API가 이를 웹 편집기에 돌려줘 같은 기준으로 씁니다. 그래서 명시적인 `anthropic/`, `gemini/`, `xai/`와 앞으로 생길 충돌 접두사는 모든 설정 경로에서 똑같이 인식되며, 게이트웨이 고유의 `deepseek-ai/...`, `Qwen/...` 같은 슬래시 포함 모델 ID는 `openai/<model>`로 정규화됩니다. 같은 정규화 공개 alias를 채널마다 Chat과 Responses로 섞어 쓰면 안 됩니다. Router가 서로 다른 Surface의 deployment 사이에서 부하를 나누는 일을 막기 위해서입니다. 실행 시에는 공개 모델 별칭 `openai/<model>`을 유지하고, LiteLLM의 `openai/responses/<model>` 연결을 통해 `/responses`를 호출합니다.
- 이 설계는 주요 프로젝트의 명시적 라우팅 방식과 같습니다. [LiteLLM](https://github.com/BerriAI/litellm/blob/main/litellm/responses/main.py)은 Chat-to-Responses bridge를 제공하고, [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/models/)는 Responses/Chat 모델 클래스를 따로 쓰며, [LangChain](https://docs.langchain.com/oss/python/integrations/chat/openai)은 `use_responses_api`로 명시적으로 고르고 알려진 조건에서만 자동 라우팅합니다. DSA는 요청이 실패한 뒤 endpoint를 추측하지 않으며, 이중 요청, 중복 과금, 실제 서버 오류가 가려지는 일을 막습니다.
- 실행 시 모델 이름은 보통 `openai/<model>`로 씁니다. 예를 들어 사용자 정의 게이트웨이의 `gpt-5.5`는 `openai/gpt-5.5`로 LiteLLM이 라우팅할 수 있습니다.
- `Qwen/...`, `deepseek-ai/...` 같은 것은 서비스 제공자나 모델 저장소 조직 이름 접두사이며, LiteLLM provider prefix와 다릅니다. 슬래시가 들어 있다고 `provider/model` 라우팅으로 착각하지 마세요.
- Base URL에는 공식 또는 게이트웨이가 알려 준 호환 진입점만 넣습니다. 보통 `/v1`, `/api/v3`, 또는 제조사 문서가 지정한 경로까지입니다. `/chat/completions`를 직접 덧붙이지 마세요.
- YAML 모드를 쓴다면 LiteLLM `model_list` / `litellm_params`의 원래 의미대로 설정합니다. YAML이 유효하면 Channels보다 우선합니다.

## GitHub Actions 설정

저장소에 들어 있는 `.github/workflows/00-daily-analysis.yml`은 workflow에 명시적으로 적힌 환경 변수만 넘겨줍니다. Modelflare를 Key 하나로 연결하려면 Secrets에 `MODELFLARE_KEY`만 설정하면 됩니다. 명시적 채널 모드를 쓴다면 먼저 Repository Variables나 Secrets에 `LLM_CHANNELS`를 설정하고, 채널 이름에 맞춰 `LLM_<CHANNEL>_*`를 채웁니다.

| 필드 | 권장 위치 | 설명 |
| --- | --- | --- |
| `MODELFLARE_KEY` | Secrets | Modelflare Key 하나로 연결하며, 기본 주소와 모델을 자동으로 채웁니다. |
| `LLM_CHANNELS` | Variables 또는 Secrets | 쉼표로 구분한 채널 이름. 예: `deepseek,minimax,volcengine`. |
| `LLM_<CHANNEL>_PROTOCOL` | Variables 또는 Secrets | 민감하지 않으며, 보통 `openai`, `deepseek`, `gemini`, `anthropic`, `ollama`입니다. |
| `LLM_<CHANNEL>_API_SURFACE` | Variables 또는 Secrets | 선택. `chat_completions`(기본값) 또는 `responses`. Responses는 현재 `openai` 프로토콜만 지원합니다. |
| `LLM_<CHANNEL>_BASE_URL` | Variables 또는 Secrets | 민감하지 않으면 Variables를 우선 씁니다. 비공개 게이트웨이 주소는 Secrets에 둘 수 있습니다. |
| `LLM_<CHANNEL>_MODELS` | Variables 또는 Secrets | 민감하지 않은 모델 목록, 쉼표로 구분. |
| `LLM_<CHANNEL>_ENABLED` | Variables 또는 Secrets | 선택. 설정하지 않으면 기본으로 켜지며, `false`로 두면 그 채널을 건너뜁니다. |
| `LLM_<CHANNEL>_API_KEY` / `LLM_<CHANNEL>_API_KEYS` | Secrets | 키 필드는 반드시 Repository Secrets에 둬야 합니다. 같은 이름의 Variables는 workflow가 읽지 않습니다. |
| `LLM_<CHANNEL>_EXTRA_HEADERS` | Secrets 또는 Variables | JSON 문자열. 인증, 테넌트, 조직, 비공개 게이트웨이 정보가 들어 있으면 Secrets에 둬야 합니다. |
| `LITELLM_CONFIG` | Variables 또는 Secrets | YAML 파일 경로. `LITELLM_CONFIG_YAML`과 함께 쓰면 workflow가 이 경로에 파일을 씁니다. |
| `LITELLM_CONFIG_YAML` | Secrets 우선 | YAML 내용 자체에 비공개 게이트웨이나 header가 들어 있을 수 있으니 Secrets를 권장합니다. |
| `LLM_USAGE_HMAC_SECRET` | Secrets | 선택. 여러 배포 사이에서 usage message HMAC을 비교해야 할 때만 같은 고엔트로피 무작위 키를 설정합니다. 예: `openssl rand -hex 32`. Variables에 두거나 버전 관리에 커밋하지 마세요. |
| `LLM_USAGE_HMAC_KEY_VERSION` | Variables 또는 Secrets | 선택. `LLM_USAGE_HMAC_SECRET`을 교체할 때 버전 태그도 함께 바꿔, 서로 다른 키로 만든 HMAC을 잘못 비교하지 않게 합니다. |

기본 workflow는 `modelflare`, `primary`, `secondary`, `aihubmix`, `anspire`, `deepseek`, `dashscope`, `zhipu`, `moonshot`, `minimax`, `volcengine`, `siliconflow`, `openrouter`, `requesty`, `gemini`, `anthropic`, `openai`, `ollama`, `hermes`를 명시적으로 매핑합니다. `mimo`는 기본 workflow에 매핑되어 있지 않습니다. `mimo`(또는 목록에 없는 다른 채널 이름)를 쓰려면 Variables/Secrets에 같은 이름의 `LLM_<CHANNEL>_*`를 설정하는 것 말고도 workflow에 해당 env 매핑을 함께 추가해야 합니다. 로컬 `.env`, Docker, 자체 호스팅 스크립트에는 이 제한이 없습니다.

HMAC 텔레메트리 명시 설정을 되돌리려면 `LLM_USAGE_HMAC_SECRET`을 지우고 `LLM_USAGE_HMAC_KEY_VERSION`을 복원하거나 지우면 됩니다. 비워 두면 시스템은 로컬에서 `.llm_usage_hmac_secret`을 만드는 기본 동작으로 돌아갑니다.

Ollama 기본 Base URL `http://127.0.0.1:11434`는 주로 로컬, Docker, 또는 이 서비스에 접근할 수 있는 self-hosted runner용입니다. GitHub-hosted runner에는 보통 로컬 Ollama 서비스가 없으므로, `LLM_CHANNELS=ollama`를 그대로 설정하면 연결에 실패할 가능성이 큽니다.

### Hermes 로컬 HTTP generation(Phase 3)

Hermes는 예약된(reserved) 로컬 HTTP generation preset이며, `LLM_CHANNELS=hermes`로만 켤 수 있습니다. 기본 프로토콜은 `openai`, 기본 주소는 `http://127.0.0.1:8642/v1`, 기본 모델은 `hermes-agent`입니다.

```env
LLM_CHANNELS=hermes
LLM_HERMES_PROTOCOL=openai
LLM_HERMES_BASE_URL=http://127.0.0.1:8642/v1
LLM_HERMES_API_KEY=sk-local-hermes
LLM_HERMES_MODELS=hermes-agent
LITELLM_MODEL=openai/hermes-agent
```

Phase 3은 일반 분석 / JSON generation만 지원하며, stream/SSE, tools, Vision, Agent tools, 원격 Hermes, 프로세스 수명 주기 관리는 지원하지 않습니다. `LLM_HERMES_API_KEY`는 로컬 `.env`, 실행 시 설정, GitHub Secrets에서 와야 하며 저장소에 쓰면 안 됩니다. Hermes는 loopback `/v1` endpoint만 허용하며, `localhost`는 `127.0.0.1`로 정규화됩니다. `LLM_HERMES_API_KEYS`와 `LLM_HERMES_EXTRA_HEADERS`는 지원하지 않습니다. 웹 설정 페이지에서 예약된 Hermes 채널을 저장하면 이 두 예전 필드를 비우고 warning을 보여 줍니다. 예전 값을 되돌리려면 `.env` 백업, Git 기록, 데스크톱 앱 내보내기 백업을 쓰세요. 다만 비어 있지 않은 다중 Key / Extra Headers는 여전히 백엔드가 거부합니다.

GitHub Actions에서 GitHub-hosted runner의 `127.0.0.1`은 runner 자신이지 사용자 컴퓨터가 아닙니다. self-hosted runner나 같은 컴퓨터의 서비스만 로컬 Hermes에 접근할 수 있으며, 그렇지 않으면 연결에 실패합니다.

## 자주 나오는 오류와 대처 방법

| `details.reason` / 증상 | 흔한 원인 | 권장 조치 |
| --- | --- | --- |
| `missing_api_key` | API Key가 비어 있거나, `API_KEYS`를 쉼표로 나눴을 때 비어 있지 않은 조각이 하나도 없습니다. | 유효한 key를 하나 이상 넣으세요. 로컬 Ollama나 localhost 호환 서비스는 예외입니다. |
| `api_key_rejected` | 서비스 제공자가 401 / 403을 돌려줌. key가 잘못되었거나 권한이 부족하거나 프로젝트가 개통되지 않았습니다. | key를 다시 복사하고, 계정 프로젝트, 조직, 지역, 모델 권한을 확인하세요. |
| `insufficient_balance` | 잔액 부족, 결제 미개통, 요금제 한도 소진. | 서비스 제공자 콘솔에서 잔액, 결제 상태, 모델 요금제를 확인하세요. |
| `quota_exceeded` | 계정이나 조직 할당량 소진. | 요금제, 프로젝트 한도, 조직 한도, 결제 페이지를 확인하세요. |
| `rate_limit` | RPM / TPM / 동시 요청 제한에 걸림. | 동시 요청을 줄이거나, 가벼운 모델로 바꾸거나, 콘솔에서 한도를 올리세요. |
| `timeout` | 요청 시간 초과. 네트워크가 느리거나, 서비스 제공자 응답이 느리거나, 로컬 서비스가 응답하지 않을 수 있습니다. | 프록시, 방화벽, Base URL, 모델 콜드 스타트, timeout 설정을 확인하세요. |
| `dns_error` | 도메인을 찾을 수 없음. | Base URL 철자, DNS, 프록시, 실행 환경의 네트워크를 확인하세요. |
| `tls_error` | TLS 인증서, 프록시, 중간자 인증서 이상. | HTTPS 인증서 체인, 회사 프록시, 자체 서명 인증서, 시스템 시각을 확인하세요. |
| `connection_refused` | 대상 포트에 서비스가 없거나 로컬 서비스가 실행되지 않음. | Base URL, 포트, 방화벽을 확인하세요. Ollama는 이 컴퓨터나 runner에서 서비스에 접근할 수 있는지 확인하세요. |
| `endpoint_not_found` | `/models`나 chat endpoint 경로가 없음. | Base URL을 호환 진입점까지 넣었는지, 제조사가 요구하는 경로를 더하거나 빼먹지 않았는지 확인하세요. |
| `invalid_url` | base_url에 지원하지 않는 형태(공백/제어 문자, 백슬래시, `userinfo@host` 등)가 있거나 해석 의미가 안전하지 않음. | `LLM_<CHANNEL>_BASE_URL`을 정리하고(먼저 비우거나 변수를 지우는 것을 권장) provider 기본 진입점을 유지하세요. 게이트웨이를 고정하려면 공식 호환 예시대로 넣으세요. |
| `model_access_denied` | 관측된 provider 문구를 바탕으로 한 best-effort 모델 사용 가능성 분류: 모델이 비활성화되었거나, 개통되지 않았거나, 계정에서 보이지 않거나, 현재 key에 접근 권한이 없을 수 있습니다. | 테스트 결과의 "本次测试模型"(이번 테스트 모델)을 먼저 보고, 서비스 제공자 콘솔에서 그 모델이 개통되었는지 확인하세요. 필요하면 모델 순서를 바꾸거나 쓸 수 없는 모델을 빼거나, 「获取模型」(모델 가져오기)으로 계정에서 보이는 모델을 확인하세요. |
| `provider_blocked` | 서비스 제공자나 중계 게이트웨이가 이번 요청을 명시적으로 막음. 계정 위험 관리, 지역, 요청 출처, 모델 권한, 대리점 정책, 콘텐츠 안전 정책 때문일 수 있습니다. | 테스트 결과의 "本次测试模型"(이번 테스트 모델)과 서비스 제공자 콘솔 로그를 먼저 보세요. Base URL, TLS, 로컬 네트워크보다 계정/프로젝트 상태, 지역이나 출처 제한, 게이트웨이 정책, 콘텐츠 안전 규칙을 먼저 확인하세요. |
| `provider_prefix_mismatch` | LiteLLM provider prefix가 채널 프로토콜과 맞지 않음. | OpenAI-compatible 채널은 보통 `openai/<model>`을 씁니다. `Qwen/...`, `deepseek-ai/...`를 provider prefix로 착각하지 마세요. |
| `non_json` | 서비스 제공자가 JSON이 아닌 응답을 주거나, 프록시가 HTML / 텍스트 오류 페이지를 돌려줌. | Base URL, 게이트웨이 경로, 프록시 오류 페이지, Chat Completions 호환 진입점을 확인하세요. |
| `null_response` | LiteLLM이 해석할 수 있는 응답 객체를 돌려주지 않음. | provider가 Chat Completions와 호환되는지 확인하고, 필요하면 모델이나 endpoint를 바꿔 다시 시도하세요. |
| `null_content` | Chat completion은 성공했지만 `content`가 비어 있음. | 텍스트 출력과 호환되는 모델로 바꾸거나, tool / vision 응답을 강제하고 있지 않은지 확인하세요. |
| `malformed_choices` | 응답에 호환되는 `choices` 구조가 없음. | endpoint가 Embeddings, Responses, 다른 프로토콜 진입점이 아니라 Chat Completions 호환 API인지 확인하세요. |
| `capability_unsupported` | JSON / tools / stream / vision smoke 매개변수를 현재 모델이나 endpoint가 지원하지 않음. | 그 기능을 지원하는 모델로 바꾸거나, 결과를 현재 계정·모델·endpoint에 대한 한 번의 기능 진단으로 보세요. provider 전체가 지원하지 않는다는 뜻은 아닙니다. |
| `unknown_error` | 서비스 제공자나 클라이언트가 세분화하지 못한 예외를 던짐. | 먼저 `details.message` / 로그의 원래 오류를 보고, 네트워크, 인증, 모델 이름, 사용 한도 순서로 하나씩 확인하세요. |

전체 분류 로직은 `src/services/system_config_service.py`의 오류 분류 구현을 기준으로 합니다.

`model_access_denied`는 여러 provider에 걸친 공식 오류 코드 대응이 아닙니다. 이 분류의 확인 가능한 근거는 다음과 같습니다.

- SiliconFlow 공식 오류 처리 문서는 API 오류를 조사할 때 HTTP 오류 코드와 `message`를 기록하라고 하며, 403은 잔액 부족이나 권한 부족을 뜻하고, 그 밖의 경우는 오류 `message`를 참고하며, 다른 모델로 바꿔 문제가 계속되는지 확인하라고 권합니다(중국어: <https://docs.siliconflow.cn/cn/faqs/error-code>, 영어: <https://docs.siliconflow.cn/en/faqs/error-code>).
- Issue #1208의 실제(민감 정보 가림) 사례는 SiliconFlow / OpenAI Compatible 채널 테스트에서 나왔으며, LiteLLM이 `litellm.APIError: APIError: OpenAIException - Model disabled.`를 돌려주었습니다.
- 온라인 재확인 기록(2026-05-06T16:21:21Z): `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0` 제약 아래, 로컬 검증 환경은 Python `3.13.12`, LiteLLM `1.82.3`, Base URL `https://api.siliconflow.cn/v1`, 모델 `Qwen/Qwen3-235B-A22B-Thinking-2507`이었습니다. SiliconFlow Chat Completions에 직접 연결하자 HTTP `403`과 응답 본문 `{"code":30003,"message":"Model disabled.","data":null}`이 돌아왔고, 같은 모델을 LiteLLM `completion(model="openai/Qwen/Qwen3-235B-A22B-Thinking-2507")`으로 호출하자 `APIError: OpenAIException - Model disabled.`가 돌아왔습니다.

그래서 현재 실행 환경은 이렇게 관측된 provider `message`를 best-effort 모델 사용 가능성 진단으로 쓰며, 이를 여러 provider에 걸친 공식 오류 코드라고 선언하지 않습니다. 구현은 오류 텍스트에 `model`과 명확한 권한, 비활성화, 사용 불가 신호가 함께 있을 때만 이 진단으로 들어갑니다. 다루지 않았거나 의미가 다른 provider 문구는 기존 대체 진단으로 갑니다. `provider_blocked`도 명확한 차단 문구에 기댄 best-effort 진단으로, 서비스 제공자/게이트웨이 정책 차단을 로컬 네트워크, TLS, 모델 사용 불가 문제와 구분하는 데 씁니다.

## 실행 시 기능 검사의 한계

- JSON / tools / stream / vision smoke는 반드시 웹에서 명시적으로 실행해야 합니다.
- 검사는 실제 LLM 요청을 보내므로 token / 이미지 입력 비용, RPM/TPM 제한, 잔액 부족, 시간 초과가 생길 수 있습니다.
- 검사 결과는 현재 계정, 모델, endpoint에 대한 한 번의 best-effort 실행 결과일 뿐입니다.
- 검사 결과는 `.env`에 기록되지 않으며 설정 저장을 막지도 않습니다.
- 기능 검사가 실패했다고 provider 전체가 지원하지 않는 것은 아닙니다. 계정 권한, 모델 미개통, endpoint 지역, 잔액, 서비스 제공자 호환 계층, LiteLLM 변환 경로 때문일 수 있습니다.
- 현재 구현은 모든 실제 provider에 대해 온라인 smoke를 하지 않았습니다. 호환성 근거는 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`(`requirements.txt` 참고), [LiteLLM Python SDK / OpenAI I/O format](https://docs.litellm.ai/), [LiteLLM OpenAI-compatible 라우팅](https://docs.litellm.ai/docs/providers/openai_compatible), 그리고 OpenAI Chat Completions의 [JSON mode](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat), [tool calling](https://platform.openai.com/docs/guides/function-calling?api-mode=chat), [streaming](https://platform.openai.com/docs/guides/streaming-responses?api-mode=chat), [vision input](https://platform.openai.com/docs/guides/images-vision?api-mode=chat) 요청 형식입니다.

## 롤백 방법

- 웹 설정 페이지: 해당 channel을 지우거나 끄고, 예전 기본 모델 / Agent 모델 / fallback을 다시 고릅니다.
- `.env`: 백업에 있는 `LLM_*`, `LITELLM_MODEL`, `AGENT_LITELLM_MODEL`, `VISION_MODEL`, `LITELLM_FALLBACK_MODELS`를 복원합니다.
- Channels에서 legacy로 돌아가기: `LLM_CHANNELS`를 지우거나 비우고, legacy provider key와 `LITELLM_MODEL`은 남겨 둡니다.
- YAML에서 Channels / legacy로 돌아가기: `LITELLM_CONFIG` / `LITELLM_CONFIG_YAML`을 지우면 다시 시작한 뒤 아래 단계 설정이 다시 적용됩니다.
- WebUI / 데스크톱 앱: 시스템 설정에서 내보낸 설정 백업으로 복원합니다.
- PR 롤백: 해당 docs PR을 revert합니다. P4는 설정, 데이터, 코드 마이그레이션을 포함하지 않습니다.
