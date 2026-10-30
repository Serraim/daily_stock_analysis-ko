# LLM(대형 언어 모델) 설정 가이드

환영합니다! AI를 처음 접하는 입문자든 여러 API를 능숙하게 다루는 숙련자든, 이 가이드를 따라 하면 대형 언어 모델(LLM)을 빠르게 연결할 수 있습니다.

이 프로젝트는 AI 모델 연결 방식을 하나로 통일해 제공하며, 주요 공식 API, OpenAI 호환 플랫폼, 로컬 모델을 지원합니다. 내부는 [LiteLLM](https://docs.litellm.ai/)으로 동작하지만, 대부분의 사용자는 "서비스 제공자 선택, API Key 입력, 주 모델·채널 선택"이라는 기본 경로만 알면 됩니다. 사용자의 단계에 맞춰 "3단계 우선순위" 설정을 마련했으니, 필요에 맞는 방식을 고르면 됩니다.

구체적인 서비스 제공자를 고르거나, GitHub Actions Secrets / Variables를 설정하거나, `details.reason` 오류를 해결하거나, 설정 롤백을 준비하고 있다면 먼저 [LLM 서비스 제공자 설정 가이드](./llm-providers.md)를 보십시오. 이 문서에서 provider 프리셋, Actions 변수 대응표, 런타임 기능 점검 범위, 자주 나는 오류의 처리 방법을 한곳에서 관리합니다.

> 이 페이지의 provider/model/Base URL 설명은 이번에 새 외부 호환 동작을 추가한 것이 아니라, 현재 운영 중인 규칙을 맞춰 적은 것입니다. 실제 호환 여부는 여전히 현재 저장소가 고정한 의존성과 런타임 구현을 따릅니다.
> - 의존성 범위: `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`(`requirements.txt`와 같음).
> - 호환성 검증 진입점: `tests/test_system_config_service.py`, `tests/test_system_config_api.py`, 기존 프런트엔드 모델 설정 페이지 회귀 테스트.
> - 롤백 경로: `.env` 설정 백업 + `POST /api/v1/system/config/import`로 복원하는 방법을 우선 사용합니다. 재시작 전에 예전 `LITELLM_MODEL` / `LLM_*` / `AGENT_LITELLM_MODEL` / `VISION_MODEL` / `LLM_TEMPERATURE` / `LLM_USAGE_HMAC_*` 값을 직접 되돌려 넣어도 됩니다.

> **참고**: 이 페이지의 provider/model/base URL 설명은 현재 의존성 제약과 기존 규칙을 그대로 따르는 문서 보완일 뿐이며, 새로운 런타임 provider, 모델, Base URL 동작 변경을 도입하지 않습니다.

---

## 빠른 안내: 어느 절을 보면 될까요?

1. **[입문자]** "일단 프로그램을 빨리 실행하고 싶어요. 간단할수록 좋아요!" -> [[방식 1: 가장 간단한 단일 모델 설정]으로 이동](#방식-1-가장-간단한-단일-모델-설정-입문자용)
2. **[중급 사용자]** "Key가 여러 개 있고, 예비 모델도 설정하고, 사용자 지정 주소(Base URL)도 바꾸고 싶어요." -> [[방식 2: 채널(Channels) 모드 설정]으로 이동](#방식-2-채널channels-모드-설정-중급자-여러-모델-사용-시)
3. **[숙련자]** "복잡한 부하 분산, 요청 라우팅, 여러 이종 플랫폼에 걸친 고가용성까지 하고 싶어요!" -> [[방식 3: YAML 고급 설정]으로 이동](#방식-3-yaml-고급-설정-숙련자-맞춤형)
4. **[로컬 모델]** "Ollama 로컬 모델을 쓰고 싶어요!" -> [[예시 4: Ollama 로컬 모델 사용]으로 이동](#예시-4-ollama-로컬-모델-사용)
5. **[비전 모델]** "이미지에서 종목 코드를 인식하고 싶어요!" -> [[확장 기능: 이미지 인식 모델(Vision) 설정]으로 이동](#확장-기능-이미지-인식-모델-vision-설정)

---

## Generation Backend (Phase 4)

Generation backend는 일반 분석, 시장 리뷰, `generate_text()`가 바깥에서 사용하는 런타임 선택입니다. 기본값은 여전히 `litellm`이며, 아무것도 설정하지 않았을 때의 동작은 예전과 같습니다. `codex_cli` / `claude_code_cli` / `opencode_cli`는 명시적으로 켜야(opt-in) 하는 로컬 CLI backend이며, 현재 **experimental/limited**(실험적·제한적)로 표시돼 있습니다.

```env
GENERATION_BACKEND=litellm
GENERATION_FALLBACK_BACKEND=litellm
GENERATION_BACKEND_TIMEOUT_SECONDS=300
GENERATION_BACKEND_MAX_OUTPUT_BYTES=1048576
GENERATION_BACKEND_MAX_CONCURRENCY=1
LOCAL_CLI_BACKEND_MAX_CONCURRENCY=1
# 선택: 비워 두면 이 컴퓨터의 OpenCode 기본 모델을 사용합니다. 값을 넣으면 --model 덮어쓰기 값으로 OpenCode에 전달합니다.
# OPENCODE_CLI_MODEL=provider/model
AGENT_BACKEND=auto
AGENT_GENERATION_BACKEND=auto
```

- `GENERATION_BACKEND=litellm|codex_cli|claude_code_cli|opencode_cli`. 로컬 CLI backend는 generation backend이지 LiteLLM provider가 아닙니다. `LITELLM_MODEL=codex_cli/...`, `LITELLM_MODEL=claude_code_cli/...`, `LITELLM_MODEL=opencode_cli/...`처럼 쓰지 마십시오.
- `GENERATION_BACKEND=opencode_cli`이면 기본적으로 `--model`을 넘기지 않고, 이 컴퓨터의 OpenCode가 자체 기본 모델 설정을 씁니다. `OPENCODE_CLI_MODEL`은 선택적인 덮어쓰기 값일 뿐이며, 값을 넣었을 때만 `--model` 인자 하나로 OpenCode에 넘깁니다. provider 인증, 계정, 모델 사용 가능 여부는 이 컴퓨터의 OpenCode 설정이 맡으며, DSA는 이를 관리하지 않습니다.
- `GENERATION_FALLBACK_BACKEND`를 설정하지 않으면 기본값은 `litellm`입니다. 로컬 `.env`에 명시적으로 빈 값 `GENERATION_FALLBACK_BACKEND=`를 쓰면 backend 수준 fallback을 끕니다. primary와 fallback이 같으면 아무 일도 하지 않는 것(no-op)으로 해석합니다. 저장소에 포함된 GitHub Actions workflow는 이 변수가 설정되지 않았으면 명시적으로 `litellm`을 내보냅니다. Actions에서 backend fallback을 끄려면 fallback을 primary backend와 같게 설정하십시오. 예: `GENERATION_BACKEND=codex_cli` + `GENERATION_FALLBACK_BACKEND=codex_cli`.
- `GENERATION_BACKEND=codex_cli|claude_code_cli`이고 Gemini/OpenAI/Anthropic/DeepSeek API Key가 없어도, 일반 분석과 시장 리뷰는 로컬 CLI backend를 시도합니다. 해당 실행 파일이 없으면 "API Key가 설정되지 않음"이 아니라 구조화된 `command_not_found`를 반환합니다.
- 현재 `codex_cli` 프리셋은 `codex --ask-for-approval never exec --sandbox read-only --output-last-message <temp-file> -`를 사용합니다. 일반 분석은 사람이 지켜보지 않는 생성 작업이므로 `never`로 고정해 비대화형 실행이 사람의 승인 요청에서 멈추지 않게 하고, `read-only`로 읽기 전용 범위를 유지합니다. DSA는 임시 파일에서 최종 응답을 읽습니다. Codex CLI가 stdout에도 같이 출력한 중복 내용은 진단 미리보기와 출력 크기 계산에서 빼며, 주 분석 JSON 파싱에도 쓰지 않습니다. 공식 근거는 [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive)와 [Codex CLI command line options](https://developers.openai.com/codex/cli/reference)입니다. 이 저장소에서 실제로 검증한 버전은 `codex-cli 0.144.3`이며, 그보다 넓은 최소 버전은 보장하지 않습니다. CLI 버전이 프리셋 인자를 지원하지 않으면 DSA는 구조화된 `capability_unsupported` / `cli_contract_unsupported` 진단을 반환하고, backend fallback이 설정돼 있으면 `litellm`으로 대체합니다.
- 현재 `claude_code_cli` 프리셋은 `claude --safe-mode --tools "" --disallowedTools "mcp__*" --strict-mcp-config --no-session-persistence --output-format json -p <static instruction>`를 사용하며, 전체 DSA prompt는 stdin으로 전달합니다. DSA는 Claude JSON envelope의 `result/success` 최종 필드에서만 텍스트를 꺼냅니다. 나중에 `--json-schema`를 켜면 schema 모드는 `structured_output`을 꺼내야 하며, 그 뒤에도 DSA의 기존 JSON validator, minimal parser contract, `_parse_response()`, integrity retry, placeholder fill, usage telemetry를 그대로 거칩니다. 인자 근거는 [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)이며, 이 PR의 smoke 검증 버전은 `claude 2.1.177 (Claude Code)`입니다. 그보다 넓은 최소 버전은 보장하지 않습니다.
- 현재 `opencode_cli` 프리셋은 `opencode --pure run --format json [--model <OPENCODE_CLI_MODEL>] <static instruction> --file <temp prompt file>`을 사용합니다. `OPENCODE_CLI_MODEL`을 명시적으로 설정했을 때만 `--model`을 덧붙입니다. 전체 DSA prompt는 권한이 제한된 임시 파일에 쓰며 argv에는 넣지 않습니다. DSA는 OpenCode JSON event 출력 중 도구 이벤트가 없는 `text` 내용만 파싱하고, 정상적인 `step_finish`를 요구합니다. `tool_use`, `error`, `question`, `permission` 등의 이벤트가 나오면 구조화된 실패로 처리합니다. 인자 근거는 [OpenCode CLI reference](https://opencode.ai/docs/cli), 프로젝트 설정 병합 방식은 [OpenCode config reference](https://opencode.ai/docs/config)이며, 이 PR의 smoke 검증 버전은 `opencode 1.17.11`입니다. 그보다 넓은 최소 버전은 보장하지 않습니다.
- 로컬 CLI backend는 streaming을 지원하지 않습니다. stream을 요청하면 자동으로 non-stream으로 낮추며, 이 때문에 `capability_unsupported`를 반환하지는 않습니다.
- 로컬 CLI의 usage 정보는 보통 얻을 수 없으며, 시스템은 가짜 0 token, 가짜 비용, 가짜 cache telemetry를 기록하지 않습니다.
- 로컬 CLI 실행에는 엄격한 상한이 있습니다. `GENERATION_BACKEND_TIMEOUT_SECONDS` 최대 `3600`, `GENERATION_BACKEND_MAX_OUTPUT_BYTES` 최대 `33554432`, `GENERATION_BACKEND_MAX_CONCURRENCY` 최대 `16`, `LOCAL_CLI_BACKEND_MAX_CONCURRENCY` 최대 `4`입니다. 진단용 stdout/stderr와 최종 응답의 합이 출력 상한을 넘으면 구조화된 `output_too_large`를 반환합니다. `--output-last-message` 프리셋의 경우 stdout에 중복으로 찍힌 최종 응답은 두 번 계산하지 않으며, `stdout_preview`로도 노출하지 않습니다.
- 로컬 CLI의 `stdout_preview` / `stderr_preview`는 구조화된 diagnostics에 기록하기 전에 짧은 자격 증명 값 대입을 가립니다(마스킹). 값의 길이에 의존하지 않습니다. 대문자 환경 변수 대입은 child-env의 fail-closed 민감 이름 판정을 그대로 쓰고, JSON과 YAML·일반 로그의 스칼라 대입은 더 좁은 자격 증명 필드 allowlist를 쓰며, URL은 별도의 userinfo / webhook / 민감 파라미터 규칙을 계속 씁니다. `token_budget`, `session_id`, `sort_key` 같은 일반 문제 해결용 필드는 `token`, `session`, `key`라는 부분 문자열이 들어 있다는 이유만으로 지워지지 않습니다. 다만 따옴표 없는 YAML 민감 스칼라는 같은 줄 안에서 믿을 만한 경계가 없으므로, 그 값부터 줄 끝까지 fail-closed로 가리며 같은 줄의 뒤쪽 필드도 남기지 않습니다.
- 로컬 CLI의 기본 동시 실행 수는 1입니다. 실제 동시 실행 수는 `min(LOCAL_CLI_BACKEND_MAX_CONCURRENCY, GENERATION_BACKEND_MAX_CONCURRENCY)`이며, `MAX_WORKERS`를 따르지 않습니다.
- `AGENT_GENERATION_BACKEND=auto`는 `GENERATION_BACKEND`의 local CLI 값을 따르지 않으며, Agent 도구 호출은 계속 LiteLLM을 사용합니다. Web 설정 페이지는 `auto|litellm`만 보여 줍니다. `AGENT_GENERATION_BACKEND=codex_cli|claude_code_cli|opencode_cli`를 직접 써 넣어도 text-only Agent 모드는 구현돼 있지 않으며, 지원하지 않는 tool-calling이라는 명확한 진단을 반환합니다.
- Phase 6a의 DSA Tool Surface는 도구 schema, 권한 메타데이터, scope guard, 구조화된 오류, 감사·마스킹 기능을 유지합니다. 기본 LiteLLM은 원래의 registry/runner를 계속 쓰며, runtime 제거 때문에 도구 진입점이 바뀌지 않습니다. `codex_cli` / `claude_code_cli` / `opencode_cli`는 여전히 generation 전용이며 Agent tool fallback으로 쓸 수 없습니다.
- Web 설정 페이지의 생성 백엔드 빠른 점검은 저장된 `.env`, 런타임 기본값, 저장하지 않은 초안만 읽습니다. 설정을 쓰거나 런타임을 다시 불러오지 않으며, 실제 모델 요청도 보내지 않습니다. `available`은 현재 설정이 실행을 시도할 수 있는 조건을 갖췄다는 뜻일 뿐입니다. JSON 스모크 테스트는 별도로 명시적으로 실행하는 작업이며, 서버에 고정된 JSON 프롬프트와 schema로 실제 생성 백엔드 요청을 한 번 보내 추출기, JSON 계약, 시간 제한, 출력 제한, usage-unavailable 동작을 확인합니다.
- `GET /api/v1/system/config/generation-backends/status`는 저장된 설정만 읽습니다. 저장하지 않은 초안은 `POST /api/v1/system/config/generation-backends/status/preview` 또는 `POST /api/v1/system/config/generation-backends/smoke-test`를 호출해야 합니다. 가려진 키 필드는 저장된 값을 계속 사용합니다. `health_status`와 `last_error_code/message`는 이번 계산 결과일 뿐이며, 과거부터 저장된 상태가 아닙니다.

<a id="问股会话状态与升级"></a>
### 종목 질문(Ask) 세션 상태와 업그레이드

서버가 주요 논의 대상과 세션 Skill을 한곳에서 저장합니다. LiteLLM single과 기존 multi는 같은 수락 시점 스냅샷을 사용합니다. Skill을 생략하거나 `null`로 보내면 저장된 선택을 그대로 씁니다(선택한 적이 없으면 설정의 기본값). 명시적으로 `[]`를 보내면 선택을 비운 상태로 저장하고 내장 기본값을 쓰며, 설정에 있는 비어 있지 않은 Skill은 켜지 않습니다. 이름은 서버 측 인덱스에서 유일하게 일치할 때만 확정합니다. 비교 질문은 종목을 바꾸지 않으며, 모델 실패나 중지가 이미 수락된 상태를 되돌리지 않습니다. 동시 요청이나 세션 인스턴스 충돌이 나면 직접 새로고침한 뒤 다시 시도하십시오. 페이지는 입력 내용과 아직 보내지 않은 선택을 유지하며, 자동으로 다시 보내지 않습니다.

예전 세션은 명확한 코드만 복원하며, 과거 종목명으로 새 사실을 만들어 내지 않습니다. “分析600519 → 改看宁德时代 → 风险呢”(600519 분석 → 닝더스다이(CATL)로 바꿔 보기 → 리스크는?) 같은 흐름은 다시 확인이 필요하며, 600519를 계속 쓰면 안 됩니다. 업그레이드는 상태 컬럼을 자동으로 추가하며, 메시지·Skill·리포트를 지우지 않습니다. 업그레이드나 롤백 전에는 백엔드를 멈추고, SQLite backup이나 서비스를 멈춘 상태의 전체 백업을 사용하십시오(WAL이 활성 상태일 때 주 파일만 복사하면 안 됩니다). 원래 설정, 데이터베이스 위치, 데이터 디렉터리는 그대로 두고, 짝이 맞는 백엔드·Web을 업데이트한 뒤 재시작합니다. 테이블이나 컬럼을 손으로 지우지 마십시오. 롤백할 때는 추가된 컬럼을 그대로 두며, 예전 코드도 메시지와 Skill을 계속 쓸 수 있습니다. 다시 업그레이드했을 때 롤백 기간에 새로 들어온 사용자 메시지가 있으면, 먼저 미확인으로 표시하고 사용자가 대상을 명확히 확인하게 합니다. 예전·새 쓰기 프로세스를 섞어 실행하는 것은 지원하지 않습니다. 백엔드와 Web을 따로 배포한 경우, 업그레이드는 백엔드 먼저·Web 나중, 롤백은 Web 먼저·백엔드 나중입니다.

(이 절의 따옴표나 코드 형식으로 적힌 중국어 문장은 사용자가 채팅창에 입력하는 예시이며, 프로그램이 이 문장을 그대로 해석하므로 원문대로 둡니다. 괄호 안은 한국어 뜻입니다.)

코드와 종목명을 섞어 쓰면 비교 범위에 둘 다 들어갑니다. 바로 붙어 있는 명확한 코드는 같은 이름의 다른 상장지와의 모호함을 없앨 수 있습니다(예: `688981中芯国际`, 688981 SMIC). `从600519改看300750`(600519에서 300750으로 바꿔 보기) / `把600519换成300750`(600519를 300750으로 바꾸기)은 동작 단어에 연결된 목적지인 300750을 확정합니다. 지금 대상이 이미 300750이거나 같은 메시지를 다시 보내도 600519로 거꾸로 돌아가지 않으며, 수락될 때마다 메시지를 저장하고 버전을 올립니다. 명확한 종목 전환은 새 대상의 도구 범위만 열고, 맞지 않는 예전 리포트 안내는 지웁니다. 목적지에 후보가 여러 개 있으면 확인 질문을 해야 하며, 마지막 후보를 임의로 고르거나 현재 대상을 빼고 추측해서 고르면 안 됩니다.

이미 주요 대상이 있을 때 `看看近期走势`(최근 흐름 보기) / `分析一下财务状况`(재무 상태 분석) / `分析风险`(리스크 분석)은 그대로 분석을 이어 가며, 원래의 확인 출처와 시각을 유지합니다. `分析300750`(300750 분석)이나 유일하게 일치하는 종목명으로는 여전히 새 대상을 확정할 수 있습니다. 단독으로 쓴 “分析／看看”(분석/보기) 뒤에 다른 글이 붙어 있다고 해서 종목 전환이 증명되지는 않습니다. 명확하지만 확정할 수 없는 “改看…”(…으로 바꿔 보기)는 확인 질문이 필요하며 분석을 시작하지 않습니다. 예전 기록도 같은 방향·동작 판정을 따르지만, 사실을 세우는 데는 유효하고 명확한 코드만 씁니다. 일반 후속 질문은 후보를 유지하고, 확정할 수 없는 새 전환은 예전 후보를 무효로 만들며, 이후 후속 질문으로 그 후보를 되살릴 수 없습니다. 나중에 명확한 코드를 쓰면 다시 세울 수 있습니다. 과거 종목명은 대상이 바뀌었다는 증거로만 쓰며, 확인된 사실을 지어 내지 않습니다. 복원 결과를 읽을 때 종목을 다시 쓰거나 버전을 올리지 않습니다.

부정, 질문, 조건, 인용 속의 전환은 긍정적인 확정으로 보지 않습니다. `不要改看300750，继续分析600519`(300750으로 바꾸지 말고 600519 분석을 계속해 줘)는 600519를 유지합니다. `是否改看300750？`(300750으로 바꿔 볼까요?)는 대상을 유지한 채 확인 질문을 하며, 300750을 열지 않습니다. 코드와 종목명은 실제로 나온 위치에 따라 해석합니다. 예전 기록에서는 목적지 위치에 있는 유효한 코드만 확정할 수 있고, 문장의 다른 곳에 있는 같은 코드가 과거 종목명 대신 사실을 만들어 줄 수는 없습니다. 처음에 유효한 코드나 유일한 종목명을 단독으로 입력하면 여전히 확정할 수 있지만, 아무 글 속에 유일한 언급이 있다고 자동으로 확정하지는 않습니다.

`如果600519下跌，就改看300750`(600519가 내리면 300750으로 바꿔 봐)처럼 조건과 결과가 붙어 있으면, 쉼표로 나뉘어 있어도 질문만 저장하고 확인 질문을 하며, 바로 종목을 바꾸거나 분석을 시작하지 않습니다. 예전 기록 복원에서도 이것을 새 확정으로 보지 않습니다. 부정된 강·약·선택 비교는 참여 대상을 늘리지 않습니다. 예를 들어 `不要研究600519和300750的区别，继续分析600519`(600519와 300750의 차이는 보지 말고 600519 분석을 계속해 줘)는 600519를 그대로 분석하며, 도구 범위에는 600519만 있습니다. 별도 문장에 있는 긍정 요청은 메시지 전체의 조건이나 부정 때문에 가려지지 않습니다.

종목 질문의 개별 종목 백테스트 도구는 요약, 상세, 총수, 페이지 나누기 모두 guard가 검증한 시장 정보를 함께 씁니다. 올바른 접두사·접미사와 기존 CN(중국 본토) 기록기의 숫자 저장 키를 모두 읽을 수 있으며, 숫자만 있는 코드 인덱스로 다른 시장을 다시 고르지 않습니다. 숫자 키는 검증된 SH·SZ·BJ 대상에서만 원래 기록 규칙대로 만듭니다. 상세는 같은 대상의 분석 출처와 연결돼야 하며, 출처에 명시된 다른 시장은 가져오지 않습니다. 숫자 요약은 같은 백테스트 구간·엔진의 같은 대상 상세가 근거로 있어야 하며, 충돌하는 숫자 출처가 있으면 그 요약을 가져오지 않습니다. 소속을 증명할 수 있는 데이터가 없으면 정상적으로 "데이터 없음"을 반환합니다. 시장 필드가 없는 정상적인 예전 CN 분석은 원래의 숫자 코드 저장 규칙을 따르며, 숫자 키를 일괄 제외하지 않습니다. 엄격한 대상을 주지 않은 원래 service·repository 진입점은 legacy 동작을 유지하며, 과거 데이터를 옮기거나 고쳐 쓰지 않습니다. 이 내부 대상 인자는 기존 도구의 요약·상세 읽기에만 쓰며, 날짜·phase별 동적 집계는 지원하지 않습니다. 지원하지 않는 조합을 명시적으로 요청하면 오류를 내며, 식별 제약을 버리지 않습니다.

일반 후속 질문에서 지나가듯 언급한 종목은 도구 범위를 넓히지 않습니다. 엄격한 Chat의 기존 종목 도구는 식별, scope, 적용 가능성 검사를 함께 쓰며, 이번 도구 호출에서 검증한 대상으로 캐시를 읽고 데이터 소스를 고릅니다. 일봉, 기술적 분석, 실시간 시세는 주식과 지수를 구분해 유지하며, 캐시가 없어도 같은 코드의 주식으로 바꿔 조회하지 않습니다. 실행 전에 필요한 식별 정보가 무효가 되면 영향받는 대상만 거부하고, 여전히 확정할 수 있는 다른 scope 구성원까지 막지 않습니다. 검증이 끝난 뒤 같은 호출 안에서 레지스트리를 다시 읽어 재분류하지 않습니다. 매물대(가격대별 보유 물량) 분포, 회사 정보, 자금 흐름, 개별 종목 백테스트는 지수를 지원하지 않으며 명확히 "지원하지 않음"을 반환합니다. 원래의 시장 조건과 ETF 조건은 그대로입니다. 엄격한 사용자 정의 도구가 적용 대상 유형을 선언하지 않았으면 그 호출만 거부합니다. 뉴스 대상은 이미 확정된 식별 정보·종목명으로 정하며, 모델이 추측한 다른 종목명을 쓰지 않습니다.

같은 이름 세션에서는 현재 Bot과 Web이 번갈아 질문해도 됩니다. Web에서 대상을 확정한 뒤 Bot의 일반 후속 질문은 그 대상의 엄격한 도구 범위를 쓰며, 올바른 비교 질문은 이번 턴에만 비교 대상을 추가합니다. 둘 다 Web의 주요 대상과 그 확인 출처·시각을 유지하며, 종목 상태 버전을 올리지 않습니다. Bot은 새 주요 대상을 따로 저장하지 않습니다. 명확한 종목 전환이 있거나 예전 대상을 안전하게 유지할 수 없으면 Web 상태는 재확인 대기로 바뀌며, 예전 대상을 믿을 수 있다고 계속 주장할 수 없습니다. 실제 예전 코드나 롤백 기간에 들어온 알 수 없는 사용자 쓰기는 여전히 재확인이 필요하며, 현재 상태를 아는 Bot으로 간주할 수 없습니다. 현재 Bot의 제출은 준비 시점 스냅샷의 인스턴스, 버전, 최신 사용자 메시지 기준점을 확인합니다. 그 사이에 새로 수락된 것이 있으면 예전 제출을 거부하며, 예전 질문을 덧붙이거나 모델을 자동으로 다시 호출하지 않습니다. 답변, provider trace, 요약은 계속 그 읽기 시점의 세션 인스턴스와 실제 메시지 출처에 묶이며, 삭제 후 다시 만든 세션은 예전 인스턴스의 늦은 쓰기를 받지 않습니다. Web에 늦게 도착한 초기 목록은 목록 표시를 갱신할 수 있지만, 새 요청이나 새로 수락된 인스턴스를 비우거나 그 stream을 취소할 수는 없습니다. 세션이 없을 때의 정상 복원, 전환, 새로 만들기는 기존 로직을 그대로 씁니다.

세션 상태 계약은 모델 라우팅이나 Phase 2의 generation 전용 기능을 바꾸지 않습니다. Codex App Server 종목 질문 백엔드는 제거됐으며, Gate 해제를 기다리는 실행 진입점도 더 이상 제공하지 않습니다. 과거 Gate 0B의 BLOCKED 기록이 이 때문에 통과로 바뀌지는 않습니다. 통제된 실행 환경에서의 상태 검증도 실제 실행 계층이나 모든 플랫폼의 업그레이드가 통과했음을 증명하지 못합니다.

### Codex App Server 종목 질문 백엔드 폐기

Codex App Server 종목 질문 백엔드는 제거됐습니다. `AGENT_BACKEND`는 `auto`(권장, 기본 LiteLLM 유지) 또는 `litellm`만 지원합니다. 예전 값 `codex_app_server`는 불러오기, 표시, 내보내기는 되지만, 실행 요청은 준비와 수락 커밋 전에 `backend_removed`를 반환하며, 모델·계정·provider를 자동으로 바꾸지 않습니다. 「설정 → Agent 설정 → 종목 질문 생성 방식」(「设置 → Agent 设置 → 问股生成方式」)에서 올바른 값을 직접 골라 저장하십시오. 예전 값이 남아 있어도 관계없는 설정의 저장은 막지 않지만, 예전 값을 명시적으로 저장하거나 가져오면 거부하며 일부만 쓰지도 않습니다. 상태 확인과 초안 미리보기는 설정만 검사하며, Codex 명령이나 schema/version 탐침을 실행하지 않고 모델도 호출하지 않습니다. 과거 세션, 종목 식별, Skill, 단일·다중 Agent, provider trace는 원래 계약을 유지합니다. 별도의 `GENERATION_BACKEND=codex_cli` 일반 리포트와 그 밖의 generation 전용 기능은 이번 제거의 영향을 받지 않으며, 여전히 각자의 CLI와 원래 의존성이 필요합니다.

### Local CLI 로컬 backend의 개인정보와 범위

- 로컬 CLI Backend는 오프라인 모델과 같은 것이 아닙니다. Codex / Claude Code / OpenCode 뒤의 서비스가 종목 코드, 뉴스, 보유 종목 정보, 분석 prompt, 리포트 초안 등을 처리할 수 있습니다.
- Docker, 클라우드 서버, CI는 원래 내 컴퓨터의 CLI 로그인 상태를 갖고 있지 않습니다.
- GitHub Actions는 설정값을 전달할 뿐, 로컬 CLI를 설치하거나 로그인하지 않습니다. Actions에서 local CLI backend를 켰는데 runner에 실행 파일이나 로그인 상태가 없으면 구조화된 실패를 보게 됩니다.
- DSA는 Codex/Claude/OpenCode의 자격 증명 파일을 읽지 않지만, 자식 프로세스는 CLI 자체의 로그인 상태를 읽을 수 있습니다.
- macOS에서 Finder/Dock으로 데스크톱 앱을 실행하면 셸 PATH를 물려받지 않습니다. 패키징된 데스크톱 앱은 백엔드를 시작할 때 자주 쓰는 Homebrew 경로(`/opt/homebrew/bin`, `/usr/local/bin` 등)를 추가합니다. 설정 점검에서 여전히 CLI 실행 파일을 찾을 수 없다고 나오면 DSA를 완전히 종료한 뒤 다시 여십시오. CLI 대화형 창을 여는 것만으로는 이미 실행 중인 백엔드의 PATH가 바뀌지 않습니다.
- DSA는 기본적으로 최소한의 실행 환경만 물려주며, `CLAUDE_*`, `ANTHROPIC_*`, `OPENCODE_*`, `OPENAI_*`, `GOOGLE_*`, `GEMINI_*`, `AWS_*`, `AZURE_*`, `VERTEX_*`, `*_API_KEY`, `*_AUTH_TOKEN`, `*_ACCESS_TOKEN`, `*_SECRET`, `*_PASSWORD`를 와일드카드로 물려주는 것을 거부합니다. DSA API key, provider token, webhook token이 새어 나갈 위험을 줄이기 위해서입니다. `CODEX_HOME`은 기존 Codex CLI 로그인 디렉터리와의 호환을 위해 남긴 정확한 예외이며, `CODEX_CLI_*` 와일드카드는 되살리지 않습니다.
- `opencode_cli`는 임시 cwd에 최소한의 프로젝트 `opencode.json`을 써서 공유, 자동 업데이트, 스냅샷, 자주 쓰는 도구 권한을 끕니다. 하지만 OpenCode가 최종 해석한 설정에는 사용자 컴퓨터의 전역 설정이 여전히 들어갈 수 있습니다. 런타임 안전 범위는 `--pure`, env denylist, prompt 파일 권한, event extractor의 fail-closed 처리에 함께 의존합니다.
- Web 설정 페이지는 안전한 프리셋만 보여 주며, 임의의 command / argv / shell 문자열 제출을 허용하지 않습니다.
- `codex_cli` / `claude_code_cli` / `opencode_cli`는 여전히 experimental/limited로 표시돼 있습니다. 사용 중인 CLI 버전이 이 저장소에서 검증한 비대화형 출력 계약을 지원하지 않으면 DSA는 구조화된 `capability_unsupported`, `cli_contract_unsupported`, `invalid_json`, `schema_validation_failed` 또는 해당 backend 오류를 반환하고, backend fallback이 설정돼 있으면 `litellm`으로 대체합니다. 이런 버전 변화의 위험을 감수할 수 없다면 `GENERATION_BACKEND=litellm`을 유지하십시오.
- `opencode_cli`는 OpenCode serve / web / ACP / MCP / attach / `--dangerously-skip-permissions`를 지원하지 않습니다. DSA는 OpenCode의 최종 텍스트를 Agent tool 성공으로 취급하지 않습니다.

## 방식 1: 가장 간단한 단일 모델 설정 (입문자용)

**목표:** API Key와 해당 모델 이름만 넣으면 바로 쓸 수 있게 합니다. 복잡한 개념을 익힐 필요가 없습니다.

모델 하나만 쓸 생각이라면 가장 빠른 방법입니다. 프로젝트 루트 폴더의 `.env` 파일을 여십시오(없다면 `.env.example`을 복사해 이름을 `.env`로 바꿉니다).

Modelflare는 표준 Channels 설정을 사용하므로 아래의 [Modelflare 예시](#예시-modelflare)를 보십시오. 이 절은 단일 모델 legacy 설정을 그대로 남겨 두며, 기존 설정은 옮길 필요가 없습니다.

### 예시 1: 일반 서드파티 플랫폼 사용 (OpenAI 형식 호환, 권장)

현재 대부분의 서드파티 통합 플랫폼(예: SiliconFlow(硅基流动), AIHubmix, 알리바바 Bailian(阿里百炼), Zhipu(智谱) 등)은 OpenAI 인터페이스 형식과 호환됩니다. 플랫폼이 API Key와 Base URL을 제공한다면 아래 형식대로 그대로 설정하면 됩니다.

```env
# 플랫폼이 발급한 API Key를 넣습니다
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
# 플랫폼의 API 주소를 넣습니다 (매우 중요: 보통 끝에 /v1이 반드시 붙어야 합니다)
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
# 해당 플랫폼의 구체적인 모델 이름을 넣습니다 (매우 중요: 시스템이 알아보도록 앞에 openai/ 접두사를 꼭 붙이십시오)
LITELLM_MODEL=openai/deepseek-ai/DeepSeek-V3 
```

### 예시 2: DeepSeek 공식 API 사용
```env
# DeepSeek 공식 플랫폼에서 발급받은 API Key를 넣습니다
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```
*호환 안내: 이 한 줄만 넣으면 시스템은 여전히 기본으로 `deepseek/deepseek-chat`을 사용하며, 로그에 설정을 옮기라는 안내를 남깁니다.*
`deepseek-chat` / `deepseek-reasoner`는 예전 설정과의 호환을 위해 아직 쓸 수 있지만, DeepSeek 공식적으로 2026/07/24 이후 폐기 대상으로 표시돼 있습니다. 새 설정은 Web 빠른 채널이나 명시적인 `LITELLM_MODEL=deepseek/deepseek-v4-flash`로 `deepseek-v4-flash` / `deepseek-v4-pro`로 옮기는 것을 권장합니다.

### 예시 3: Gemini 무료 API 사용
```env
# 발급받은 Google Gemini Key를 넣습니다
GEMINI_API_KEY=AIzac...
```

<a id="示例-4使用-ollama-本地模型"></a>
### 예시 4: Ollama 로컬 모델 사용
```env
# Ollama는 API Key가 필요 없습니다. 로컬에서 ollama serve를 실행하면 바로 쓸 수 있습니다
OLLAMA_API_BASE=http://localhost:11434
LITELLM_MODEL=ollama/qwen3:8b
```

> **중요**: Ollama는 반드시 `OLLAMA_API_BASE`로 설정해야 합니다. `OPENAI_BASE_URL`을 쓰면 **안 됩니다**. 그러면 시스템이 URL을 잘못 이어 붙입니다(예: 404, `api/generate/api/show`). 원격 Ollama를 쓸 때는 `OLLAMA_API_BASE`를 실제 주소(예: `http://192.168.1.100:11434`)로 설정합니다. 현재 의존성 제약은 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`입니다(requirements.txt와 같음).

### Anspire Open legacy 호환 예시

기존의 Anspire 검색과 LLM이 Key를 함께 쓰는 호환 경로는 그대로 유지됩니다. 아래는 설정 예시이며, 모델과 게이트웨이를 쓸 수 있는지는 계정 권한과 Anspire 콘솔을 기준으로 합니다. Web 설정 페이지에서 "연결 테스트"(“测试连接”)를 눌러 확인할 수 있습니다.

```env
# Anspire Open API Keys (여러 개 지원, 쉼표로 구분)
# 발급: https://open.anspire.cn/dsa?share_code=QFBC0FYC
# 기본 우선순위 조건을 만족하면 시스템이 이 Key로 검색과 LLM을 함께 처리합니다 (예시의 최후 대체 경로에 한함).
# 예시 모델: Doubao-Seed-2.0-lite, 예시 게이트웨이: https://open-gateway.anspire.cn/v6
ANSPIRE_API_KEYS=sk-xxxxxxxxxxxxxxxx
# 선택: 콘솔에서 쓸 수 있는 것에 맞춰 모델이나 게이트웨이를 바꿉니다
# ANSPIRE_LLM_MODEL=Doubao-Seed-2.0-pro
# ANSPIRE_LLM_BASE_URL=https://open-gateway.anspire.ai/v6
```

> **축하합니다! 입문자는 여기까지 읽었으면 프로그램을 실행해도 됩니다!**
> 연결이 되는지 확인하고 싶다면, 프로젝트 폴더에서 명령줄(Windows는 PowerShell 또는 명령 프롬프트)을 열고 `python scripts/check_env.py --llm`을 입력하십시오.

---

<a id="方式二渠道channels模式配置适合进阶多模型"></a>
## 방식 2: 채널(Channels) 모드 설정 (중급자, 여러 모델 사용 시)

**목표:** 여러 플랫폼의 Key를 섞어 쓰고 싶고, 주 모델이 멈추거나 네트워크가 끊기면 예비 모델로 자동 전환되기를 원합니다.

**웹 화면에서 바로 설정할 수 있습니다:** 프로그램을 실행한 뒤 **Web UI의 "시스템 설정 -> AI 모델 -> AI 모델 연결"**(“系统设置 -> AI 模型 -> AI 模型接入”)에서 아주 직관적으로 화면을 보며 설정할 수 있습니다!

> **새 편집 화면 보충 설명**: DeepSeek, 알리바바 Bailian(DashScope), 그 밖에 OpenAI `/v1/models`와 호환되는 채널은 이제 설정 페이지에서 "모델 가져오기"(“获取模型”)를 바로 눌러 `{base_url}/models`에서 쓸 수 있는 모델을 불러와 여러 개 고를 수 있습니다. 저장은 여전히 예전과 같은 `LLM_{CHANNEL}_MODELS=model1,model2` 쉼표 형식으로 합니다. 채널이 이 인터페이스를 지원하지 않거나, 인증에 실패하거나, 잠시 연결되지 않아도 모델 목록을 직접 입력할 수 있으며 저장에는 영향이 없습니다.

### 첫 실행 설정 상태

백엔드는 읽기 전용 상태 API `GET /api/v1/system/config/setup/status`를 제공합니다. 첫 실행 과정에서 가장 기본적인 설정, 즉 LLM 주 채널, Agent 채널, 관심 종목, 알림 채널, 로컬 저장소가 준비됐는지 판단하는 데 씁니다. 이 API는 저장된 `.env`와 현재 프로세스 환경 변수만 읽으며, 런타임 설정을 다시 불러오거나, `.env`에 쓰거나, 실제 모델을 테스트하거나, 데이터베이스 파일을 만들지 않습니다. 프런트엔드 설정 마법사와 이후의 smoke run은 이 API를 바탕으로 단계적으로 연결할 수 있습니다.

### Web 채널 편집기의 호환성 / 마이그레이션 / 롤백 규칙

- 프리셋에 있는 provider / API Surface / Base URL / 예시 모델은 **폼 초기값**으로만 씁니다. 실제로 저장되는 값은 여전히 지금 입력한 `LLM_{CHANNEL}_PROTOCOL`, `LLM_{CHANNEL}_API_SURFACE`, `LLM_{CHANNEL}_BASE_URL`, `LLM_{CHANNEL}_MODELS`, `LLM_{CHANNEL}_API_KEY(S)`이며, 뒤에서 몰래 다른 provider 이름, Surface, URL로 바꾸지 않습니다.
- `LLM_{CHANNEL}_API_SURFACE`는 `chat_completions`(기본값) 또는 `responses`를 고를 수 있습니다. Responses는 현재 OpenAI 호환 프로토콜만 지원하며, 채널 안 모든 모델의 실제 LiteLLM provider가 `openai`여야 합니다. 시스템은 현재 설치된 LiteLLM provider registry에서 직접 연결 접두사를 식별하고, `GET /api/v1/system/config`의 `llm_model_providers`로 Web 편집기에 돌려줍니다. 프런트엔드와 백엔드가 각자 provider 표를 따로 관리하지 않습니다. 그래서 `anthropic/claude-*`, `xai/grok-*`, 그리고 앞으로 LiteLLM에 새로 추가될 직접 연결 provider가 로컬 허용 목록이 늦게 갱신됐다는 이유로 OpenAI route로 잘못 감싸지지 않습니다. 충돌하는 설정은 저장, 시작, 상태 진단, 필터 진입점에서 모두 똑같이 거부하며, `anthropic/responses/...`를 만들지 않습니다. `deepseek-ai/DeepSeek-V3`, `Qwen/...`처럼 registry에 없는 게이트웨이 자체 모델 ID는 `openai/<게이트웨이 모델 ID>`로 정규화합니다. 같은 채널의 모델은 같은 Surface를 써야 하고, 같은 정규화 route alias를 채널을 넘나들며 Chat과 Responses에 섞어 쓸 수 없습니다. 그렇지 않으면 Router가 같은 공개 alias 호출을 잘못된 endpoint로 보낼 수 있습니다. 두 Surface가 모두 필요하면 서로 다른 별칭을 써야 합니다. 설정 페이지의 "모델 가져오기"는 여전히 `{base_url}/models`만 호출합니다. "연결 테스트"는 선택한 Surface로 모델 목록의 첫 항목에 최소한의 요청을 한 번 보내고 `resolved_model`과 `resolved_api_surface`를 보여 주며, 실패 후 다른 endpoint로 몰래 다시 시도하지 않습니다. `details.reason=model_access_denied`가 반환되면(예: Issue #1208에서 관찰된, SiliconFlow / OpenAI Compatible이 LiteLLM을 거쳐 `Model disabled`를 반환한 경우), provider 문구를 바탕으로 한 best-effort 모델 사용 가능 여부 진단으로 보십시오. 먼저 그 모델이 현재 계정·키에서 열려 있는지 확인하고, 필요하면 모델 순서를 바꾸거나 쓸 수 없는 모델을 빼고 다시 시도하십시오. 다루지 않거나 의미가 다른 provider 문구는 계속 일반 진단으로 처리합니다. 선택 기능인 "런타임 기능 점검"은 사용자가 명시적으로 골랐을 때만 실행되며, 추가로 JSON / tools / stream / vision smoke 요청을 보냅니다. 결과는 현재 계정, 모델, endpoint에 대한 한 번의 best-effort 점검일 뿐입니다. 이 점검이 반환하는 구조화된 진단 필드는 `.env`에 **다시 쓰지 않으며**, 저장을 막지도 않습니다.
- `details.reason=provider_blocked`가 반환되면 서비스 제공자나 중계 게이트웨이가 이번 요청을 명시적으로 막았다는 뜻입니다. 로컬 네트워크 / TLS 오류나 `model_access_denied`와는 다르며, 계정 보안 정책, 지역이나 요청 출처 제한, 모델 권한, 대행사 게이트웨이 정책, 콘텐츠 안전 정책을 먼저 확인해야 합니다.
- 런타임 기능 점검은 실제 LLM 요청을 보내므로 token / 이미지 입력 비용, RPM/TPM 제한, 잔액 부족, 시간 초과가 생길 수 있습니다. 점검 실패의 원인은 계정 권한, 모델 미개통, endpoint 지역, 잔액, 서비스 제공자 호환 계층, LiteLLM 변환 경로일 수 있으며, 그 provider가 해당 기능을 전혀 지원하지 않는다는 뜻은 아닙니다. P3에서는 모든 실제 provider에 대해 온라인 smoke를 하지 않았습니다. 호환성 근거는 현재 의존성 제약 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`에서의 LiteLLM `completion()` / OpenAI I/O format / streaming / exception mapping, 그리고 OpenAI Chat Completions의 JSON mode, tool calling, streaming, vision input 형식입니다.
- 관련 외부 자료: LiteLLM Python SDK / OpenAI I/O format / streaming / exception mapping: <https://docs.litellm.ai/>, LiteLLM OpenAI-compatible 라우팅: <https://docs.litellm.ai/docs/providers/openai_compatible>, OpenAI Chat Completions: <https://platform.openai.com/docs/api-reference/chat/create>, JSON mode: <https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat>, tool calling: <https://platform.openai.com/docs/guides/function-calling?api-mode=chat>, streaming: <https://platform.openai.com/docs/guides/streaming-responses?api-mode=chat>, vision input: <https://platform.openai.com/docs/guides/images-vision?api-mode=chat>.
- 채널을 저장할 때는 이번에 제출한 key만 갱신합니다. 채널 모드로 바꿨다는 이유로 예전 설정 전체를 몰래 옮기지 않습니다. 함께 **정리되는** 것은 런타임 모델 참조뿐입니다. `LITELLM_MODEL`, `AGENT_LITELLM_MODEL`, `VISION_MODEL`, `LITELLM_FALLBACK_MODELS`가 현재 켜진 채널에 더 이상 없는 모델을 가리키면, 설정 페이지가 저장 전에 이 무효 참조를 비우거나 지워서 런타임이 무효 모델을 계속 가리키지 않게 합니다. 현재 켜진 채널에 고를 수 있는 모델이 하나도 없어도, legacy Key가 뒷받침하지 않는 관리형 provider의 예전 값은 정리합니다. `cohere/*`, `google/*`, `xai/*` 같은 직접 연결 모델은 과거 `direct-env` 호환으로 남겨 두는 동작을 설명하기 위한 것일 뿐, 쓸 수 있다는 약속이 아닙니다. 실제로 쓸 수 있는지는 각 회사의 공식 모델·API 문서를 보고 직접 확인하십시오.
- 백엔드 일관성 근거: 설정 검증 경로는 `SystemConfigService._validate_llm_runtime_selection`(`src/services/system_config_service.py`)에서 `_uses_direct_env_provider`(`src/config.py`)로 런타임 출처를 판단합니다. 현재 `gemini`, `vertex_ai`, `anthropic`, `openai`, `deepseek`만 관리형 key provider이며, `cohere`, `google`, `xai`는 이 허용 목록에 없으므로 직접 연결 모델로 남습니다.
- 롤백 방법도 최소한으로 유지합니다. 해당 채널의 모델 목록을 되돌린 뒤 주 모델 / fallback을 다시 고르거나, 데스크톱 앱에서 내보낸 백업이나 직접 `.env`로 예전 `LLM_*`, `LITELLM_MODEL`, `AGENT_LITELLM_MODEL`, `VISION_MODEL`, `LLM_TEMPERATURE`, `LLM_USAGE_HMAC_*`를 되돌리면 됩니다. 별도의 마이그레이션 스크립트를 돌릴 필요는 없습니다. Web에서 설정을 복원하려면 관리자 인증(`ADMIN_AUTH_ENABLED=true`)을 켠 뒤 `POST /api/v1/system/config/import`로 롤백할 수도 있습니다.
- 이 경로에 대한 현재 저장소의 의존성 제약은 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`입니다(`requirements.txt` 참고). 회귀 테스트는 `tests/test_system_config_service.py`, `tests/test_system_config_api.py`, `apps/dsa-web/src/components/settings/__tests__/LLMChannelEditor.test.tsx`가 다룹니다.

> **외부 provider 예시 모델 안내**: `cohere/*`, `google/*`, `xai/*` 등의 provider 접두사 값은 현재 저장 시 정리 동작을 설명하기 위한 것일 뿐이며, **이 의존성 제약 안에서 모델별로 쓸 수 있다는 보장이 아닙니다**. 문서나 테스트의 구체적인 모델 이름은 모두 설정 유지 동작의 예시일 뿐, 실제 운영 추천이 아닙니다. 실제로 쓸 수 있는지는 해당 공식 모델 문서를 기준으로 하고, 저장소 의존성 제약 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`과 함께 다시 확인하십시오.

### 롤백과 호환성 근거

- 의존성 제약과 자동 정리 범위: `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`에서 저장은 무효가 된 runtime 모델 참조(`LITELLM_MODEL`, `AGENT_LITELLM_MODEL`, `VISION_MODEL`, `LITELLM_FALLBACK_MODELS`)만 정리하며, `cohere/*`, `google/*`, `xai/*` 등 채널에 속하지 않은 직접 연결 모델은 남겨 둡니다.
- 롤백 방법: 데스크톱 앱에서 내보낸 백업을 `POST /api/v1/system/config/import`로 바로 복원할 수 있습니다. `.env`에 예전 `LITELLM_* / AGENT_LITELLM_MODEL / VISION_MODEL / LLM_TEMPERATURE / LLM_USAGE_HMAC_*` 값을 직접 되돌려 넣고 재시작해도 적용됩니다. Web에서 가져오기를 하기 전에 먼저 관리자 인증(`ADMIN_AUTH_ENABLED=true`)을 켜십시오.
- 롤백 회귀 근거: `tests/test_system_config_service.py::test_import_desktop_env_restores_runtime_models_after_cleanup`가 "정리 후 데스크톱 내보내기 백업으로 runtime 참조 복원"을 다룹니다.
- 직접 연결 provider 회귀 근거: `tests/test_system_config_service.py::SystemConfigServiceTestCase::test_validate_accepts_minimax_model_as_direct_env_provider`, `test_validate_accepts_cohere_model_as_direct_env_provider`, `test_validate_accepts_google_model_as_direct_env_provider`, `test_validate_accepts_xai_model_as_direct_env_provider`가 직접 연결 provider 유지 동작을 다룹니다.
- 프런트엔드 회귀 명령: `cd apps/dsa-web && npm run lint && npm run build && npm run test -- src/components/settings/__tests__/LLMChannelEditor.test.tsx`.
- 권장 롤백 순서(설정 페이지 새로고침 포함): 먼저 데스크톱 백업을 내보내고, `POST /api/v1/system/config/import`로 가져온 뒤, `GET /api/v1/system/config`로 페이지 설정을 새로고침하고, `LITELLM_MODEL / AGENT_LITELLM_MODEL / VISION_MODEL / LLM_TEMPERATURE / LLM_USAGE_HMAC_*`가 모델 목록과 맞는지 확인한 다음 계속 사용합니다.

<a id="常用官方文档来源用于核对预设-provider--base-url--模型命名"></a>
### 자주 쓰는 공식 문서 (프리셋 provider / Base URL / 모델 이름 확인용)

- Modelflare: [빠른 시작](https://docs.modelflare.dev/quickstart/), [접속 엔드포인트](https://docs.modelflare.dev/guides/endpoints/), [모델과 그룹](https://docs.modelflare.dev/guides/models-and-groups/)
- OpenAI Compatible 규격(LiteLLM): <https://docs.litellm.ai/docs/providers/openai_compatible>
- OpenAI 공식: <https://platform.openai.com/docs/api-reference/chat>
- DeepSeek 공식: <https://api-docs.deepseek.com/>
- Anspire Open: <https://open.anspire.cn/dsa?share_code=QFBC0FYC>
- 알리바바 Bailian DashScope 호환 모드: <https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope>
- Moonshot / Kimi 공식: <https://platform.moonshot.ai/docs/guide/compatibility>
- Anthropic 공식: <https://docs.anthropic.com/en/api/messages>
- Gemini 공식: <https://ai.google.dev/gemini-api/docs/openai>
- Cohere 공식: <https://docs.cohere.com/>
- Cohere API 참고: <https://docs.cohere.com/reference/>
- Cohere LiteLLM Provider: <https://docs.litellm.ai/docs/providers/cohere>
- Google Gemini API와 모델: <https://ai.google.dev/gemini-api/docs/openai>, <https://ai.google.dev/gemini-api/docs/models>
- Google LiteLLM Provider: <https://docs.litellm.ai/docs/providers/gemini>
- xAI 공식: <https://docs.x.ai/docs>
- xAI LiteLLM Provider: <https://docs.litellm.ai/docs/providers/xai>
- Ollama 공식: <https://github.com/ollama/ollama/blob/main/docs/api.md>

웹 화면을 쓰기 어렵다면 `.env` 파일에서 설정해도 아주 편하며, 여러 서드파티 플랫폼을 함께 관리할 수 있습니다. 규칙은 다음과 같습니다.

1. **먼저 채널이 몇 개인지 선언합니다**: `LLM_CHANNELS=채널이름1,채널이름2`
2. **채널마다 따로 설정을 적습니다**(모두 대문자로 씁니다): `LLM_{채널이름}_XXX`

<a id="示例modelflare"></a>
### 예시: Modelflare

[Modelflare 가입](https://modelflare.dev/sign-up?utm_source=github&utm_campaign=daily_stock_analysis) 후 콘솔에서 API Key를 만들고 다음과 같이 설정합니다.

```env
MODELFLARE_KEY=sk-xxx
```

`MODELFLARE_KEY`만 넣으면 백엔드가 Modelflare를 자동으로 켭니다. 기본 주소는 `https://modelflare.dev/v1`, 모델은 `openai/gpt-6.1-sol`이며, 채널 이름, 주소, 모델을 따로 쓸 필요가 없습니다. 명시적인 YAML이나 `LLM_CHANNELS`가 우선하고, Modelflare 채널에 명시적으로 넣은 Key가 이 간단한 방식보다 우선합니다. Key를 비우거나 채널을 끄면 사용이 중단됩니다. 이 자동 추론은 저장된 설정을 고쳐 쓰지 않습니다.

`modelflare` 채널 하나만 선언하고 채널 모델 목록을 비워 두었다면, 주 모델을 설정하지 않았을 때 기본으로 `openai/gpt-6.1-sol`을 씁니다. 주 모델을 설정하면 백엔드는 `LITELLM_MODEL`과 `openai/` 접두사가 붙은 예비 모델을 그대로 쓰며, 주 모델은 `openai/<모델 이름>` 형식을 씁니다. 명시적인 `LLM_MODELFLARE_MODELS`가 우선하며, 채널이 여러 개라면 여전히 각각 모델을 선언해야 합니다. 이 자동 추론은 저장된 설정이나 모델 선택을 고쳐 쓰지 않습니다.

채널 이름이 `modelflare`이면, 접속 주소를 적지 않았거나 비워 두었을 때 자동으로 `https://modelflare.dev/v1`을 씁니다. 명시적인 `LLM_MODELFLARE_BASE_URL`이 우선합니다. 이 주소는 기본으로 `openai` 프로토콜로 인식하며, 인터페이스 기본값은 `chat_completions`입니다. `LITELLM_MODEL`을 설정하지 않았으면 첫 번째 채널 모델을 씁니다. 기본 모델도 계정에 접근 권한이 있어야 하며, API Key를 자동으로 채워 주지는 않습니다.

`gpt-6.1-sol`은 이 프로젝트의 Modelflare 기본 모델입니다. 계정 권한에 맞춰 실제로 쓸 수 있는 모델을 고르고, Web의 「모델 가져오기」와 「연결 테스트」로 확인하십시오. Base URL에 `/chat/completions`를 붙이지 마십시오. Modelflare는 새 채널을 만들 때 가장 먼저 나오는 템플릿이며, 이미 저장된 채널과 주 모델은 템플릿 순서가 바뀌어도 달라지지 않습니다. Anspire Search는 여전히 `ANSPIRE_API_KEYS`로 따로 설정합니다.

클라이언트의 빠른 추가 버튼과 채널 설명에 있는 「Modelflare 전용 가입」 링크는 app UTM을, README는 github UTM을 씁니다. 새로 만든 채널에 아직 Key를 넣지 않았거나, 주 모델·예비 모델이 현재 켜진 채널에 속하지 않으면 상태 미리보기가 「설정 조정 필요」(「配置需要调整」)를 표시하고 해당 필드를 나열합니다. Key를 채우거나, 쓸 수 있는 모델을 고르거나, 무효인 예비 모델을 비운 뒤 다시 시도하십시오. 미리보기는 저장된 설정을 자동으로 고쳐 쓰지 않습니다.

### 호환 예시: Anspire Responses API (GPT-5.6 이름은 관찰된 예시)

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

Anspire 공식 연결 안내 페이지에 `https://open-gateway.anspire.cn/v6/responses` 호출 방법이 공개돼 있습니다: <https://open.anspire.cn/model?link=sample&tab=models>. Responses 라우팅은 모델 이름으로 고정하지 않습니다. 위의 GPT-5.6 이름은 현재 게이트웨이에서 관찰한 예시일 뿐, 장기적인 모델 목록을 약속하지 않습니다. 모델, Surface, 계정 권한은 채널의 실시간 `/models` 응답, 서비스 제공자 안내, 연결 테스트를 기준으로 하십시오.

### 예시: DeepSeek와 중계 플랫폼을 함께 설정하고 예비 전환 지정
```env
# 1. 채널 모드를 켜고, 채널 두 개(deepseek, aihubmix)를 선언합니다
LLM_CHANNELS=deepseek,aihubmix

# 2. 채널 1: DeepSeek 공식 설정
LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_DEEPSEEK_API_KEY=sk-1111111111111
LLM_DEEPSEEK_MODELS=deepseek-v4-flash,deepseek-v4-pro

# 3. 채널 2: 자주 쓰는 통합 중계 API 설정
LLM_AIHUBMIX_BASE_URL=https://api.aihubmix.com/v1
LLM_AIHUBMIX_API_KEY=sk-2222222222222
LLM_AIHUBMIX_MODELS=gpt-5.5,claude-sonnet-4-6

# 4. [핵심] 주 모델과 예비 모델 목록을 지정합니다
# 평소에는 deepseek 모델을 우선 사용합니다:
LITELLM_MODEL=deepseek/deepseek-v4-flash
# 선택: Agent 종목 질문용 주 모델을 따로 지정합니다 (비워 두면 주 모델을 따름)
AGENT_LITELLM_MODEL=deepseek/deepseek-v4-pro
# 주 모델이 실패하면 아래 두 예비 모델을 차례로 바로 시도합니다:
LITELLM_FALLBACK_MODELS=openai/gpt-5.4-mini,anthropic/claude-sonnet-4-6
```

### 예시: Ollama 채널 모드 (로컬 모델, API Key 불필요)
```env
# 1. 채널 모드를 켜고 ollama 채널을 선언합니다
LLM_CHANNELS=ollama

# 2. Ollama 주소를 설정합니다 (로컬 기본 포트 11434)
LLM_OLLAMA_BASE_URL=http://localhost:11434
LLM_OLLAMA_MODELS=qwen3:8b,llama3.2

# 3. 주 모델을 지정합니다
LITELLM_MODEL=ollama/qwen3:8b
```

### 예시: Hermes 로컬 HTTP Generation (Phase 3)
```env
LLM_CHANNELS=hermes
LLM_HERMES_PROTOCOL=openai
LLM_HERMES_BASE_URL=http://127.0.0.1:8642/v1
LLM_HERMES_API_KEY=sk-local-hermes
LLM_HERMES_MODELS=hermes-agent
LITELLM_MODEL=openai/hermes-agent
```

Hermes는 예약된 채널 이름이며, 이 컴퓨터의 loopback `/v1` OpenAI-compatible generation만 지원합니다. Phase 3에서는 일반 분석과 JSON 출력만 검증했습니다. Stream/SSE, Tools, Vision, Agent tools, 원격 Hermes, 프로세스 수명 관리는 지원하지 않습니다. Hermes API Key는 `LLM_HERMES_API_KEY` 하나만 쓸 수 있으며, `LLM_HERMES_API_KEYS`나 `LLM_HERMES_EXTRA_HEADERS`는 설정하지 마십시오. Hermes 설정이 잘못되면 시스템이 legacy provider로 조용히 대체되는 것을 막아, 실수로 외부 모델을 쓰지 않게 합니다. Web 설정 페이지에서 예약된 Hermes 채널을 저장하면 예전 `LLM_HERMES_API_KEYS` / `LLM_HERMES_EXTRA_HEADERS`를 명시적으로 비우고 경고를 반환합니다. 예전 값을 되살려야 한다면 `.env` 백업, Git 기록, 데스크톱 앱 내보내기 백업에서 직접 복원하십시오. 다만 Phase 3는 비어 있지 않은 다중 Key / Extra Headers 설정을 여전히 거부합니다.

### MiniMax 채널 모델 입력 방법

- 공식 OpenAI 호환 MiniMax 채널에는 `MiniMax-M3.1-Flash,MiniMax-M3`를 쓰십시오. `minimax/MiniMax-M3.1-Flash`처럼 provider 접두사가 붙은 채 명시적으로 저장된 ID도 계속 지원합니다.
- Web 설정 페이지의 주 모델, Agent 주 모델, Fallback, Vision 드롭다운은 이 값을 그대로 보여 주며, 더 이상 `openai/minimax/<모델 이름>`으로 잘못 고쳐 쓰지 않습니다.

### 기본 모델 종목 질문 / LiteLLM 설정 호환 안내

- `AGENT_BACKEND=auto|litellm`이면 종목 질문 Agent는 일반 분석과 같은 3단계 우선순위를 따릅니다: `LITELLM_CONFIG`(LiteLLM YAML) > `LLM_CHANNELS` > legacy provider keys. 위 단계의 설정이 유효하게 적용되면 아래 단계 설정은 이번 요청에 참여하지 않습니다.
- YAML 모드에서는 Agent가 LiteLLM `model_list` / `model_name` 라우팅 의미를 그대로 씁니다. 채널 모드에서는 `AGENT_LITELLM_MODEL`을 먼저 읽고, 비어 있으면 `LITELLM_MODEL`을 따르며, 이어서 `LITELLM_FALLBACK_MODELS` 순서로 fallback합니다.
- YAML / Channels를 켜지 않았고 `AGENT_LITELLM_MODEL`도 비어 있지만 로컬에 legacy 환경 변수가 남아 있다면, 종목 질문 Agent는 여전히 예전 설정을 따릅니다: `GEMINI_API_KEY + GEMINI_MODEL` -> `gemini/<model>`, `OPENAI_API_KEY + OPENAI_MODEL` -> `openai/<model>`, `ANTHROPIC_API_KEY + ANTHROPIC_MODEL` -> `anthropic/<model>`.
- 이 호환 로직은 "실패할 때 백엔드의 실제 오류 원인을 유지"하고 "LLM이 설정되지 않았을 때 더 구체적인 진단을 주는" 기능만 강화합니다. 기존 `GEMINI_*` / `OPENAI_*` / `ANTHROPIC_*` / `LITELLM_*` 설정을 조용히 지우거나, 비우거나, 옮기거나, 고쳐 쓰지 **않습니다**.
- 현재 환경에 유효한 Agent 모델 경로가 하나도 없으면, 종목 질문 페이지는 계속 실패로 응답하며 백엔드의 실제 설정 진단을 그대로 보여 줍니다. 유효한 모델 출처를 하나라도 채우면 복구되며, 별도의 설정 마이그레이션 스크립트를 실행할 필요는 없습니다.
- 새 설정에 권장하는 방법은 여전히 `LITELLM_MODEL` / `AGENT_LITELLM_MODEL`을 명시적으로 설정하거나 `LLM_CHANNELS`를 쓰는 것입니다. legacy provider keys는 현재 호환용 대체 경로로 남아 있어, 예전 `.env`, 로컬 macOS 개발 환경, 과거 배포가 그대로 계속 돌아가게 합니다.

<a id="问股可见对话上下文压缩"></a>
### 종목 질문의 보이는 대화 컨텍스트 압축

기본적으로 종목 질문은 예전처럼 최근 20개의 보이는 대화만 넣습니다. 기본 모델로 긴 대화를 할 때 token을 아끼려면 다음을 켤 수 있습니다.

```env
AGENT_CONTEXT_COMPRESSION_ENABLED=true
AGENT_CONTEXT_COMPRESSION_PROFILE=balanced
# 비워 두면 profile 프리셋을 따릅니다
AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS=
AGENT_CONTEXT_PROTECTED_TURNS=
```

압축은 `session_id` 아래 사용자에게 보이는 `user` / `assistant` 텍스트 기록만 처리합니다. provider trace, thinking blocks, tool calls, tool results는 처리하지 않으며, 같은 턴의 도구 호출 전달도 바꾸지 않습니다. 세 가지 프리셋은 `cost`(6000 tokens / 2턴 보호), `balanced`(12000 / 4), `long_context_raw_first`(24000 / 6)입니다. trigger / protected를 비워 두면 현재 profile을 따르고, 명시적으로 값을 넣으면 profile을 덮어씁니다.

종목 질문 single-agent 경로는 DeepSeek V4 thinking + tool-call의 턴 간 프로토콜 재생을 위해 provider-aware trace 경로를 따로 하나 더 관리합니다. 같은 턴에 `tool_calls`와 `reasoning_content`가 함께 나왔을 때만, 현재 `session_id + provider + model` 기준으로 최근 3개의 최소 프로토콜 자료를 저장하고, 다음 턴에서 원래 시간 순서대로 해당 보이는 assistant 답변 앞에 다시 끼워 넣습니다. 이 trace는 그대로 유지하거나 통째로 버릴 수만 있으며, 요약에 쓰지 않고, Web 세션 메시지에 기록하지 않으며, `.env` 설정도 추가하지 않습니다. model/provider가 맞지 않거나, 기준점이 이미 summary에 덮였거나, 예산이 부족하면 통째로 건너뜁니다. Claude extended thinking은 이번에는 adapter/storage 수준의 opaque `thinking` / `redacted_thinking` / `signature` blocks 전달 구조와 오프라인 fixture만 다루며, 운영 환경 end-to-end 지원은 선언하지 않습니다. multi-agent trace 주입은 후속 작업입니다. 외부 프로토콜 근거는 DeepSeek thinking mode 문서(<https://api-docs.deepseek.com/guides/thinking_mode>)와 Anthropic Claude extended thinking 문서(<https://platform.claude.com/docs/en/docs/build-with-claude/extended-thinking>)이며, LiteLLM 호환 범위는 여전히 `requirements.txt`의 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`을 기준으로 합니다.

### temperature가 엄격한 모델의 호환 안내

- Moonshot 공식 문서에 따르면 Kimi API는 OpenAI 인터페이스와 호환되며, Base URL은 `https://api.moonshot.ai/v1`을 씁니다: <https://platform.kimi.ai/docs/guide/kimi-k2-6-quickstart>
- LiteLLM 공식 문서는 OpenAI Compatible 채널 모델 이름에 `openai/` 접두사를 쓰도록 요구합니다: <https://docs.litellm.ai/docs/providers/openai_compatible>
- Moonshot 공식 호환성 문서는 두 가지 고정값을 구분합니다. **thinking 모드는 `1.0`, non-thinking 모드는 `0.6`으로 고정**이며, 다른 값을 보내면 API가 거부합니다: <https://platform.moonshot.ai/docs/guide/compatibility#parameters-differences-in-request-body>
- OpenAI Chat Completions 규격에서 `temperature`는 선택 파라미터입니다. GPT-5 / o 시리즈처럼 기본 온도만 받는 모델에 대해서는, 이 프로젝트가 `LLM_TEMPERATURE`를 고쳐 쓰지 않고 요청 단계에서 `temperature`를 빼서 서버가 기본값을 쓰게 합니다: <https://platform.openai.com/docs/api-reference/chat/create>
- 현재 저장소의 런타임 의존성 제약은 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`입니다(`requirements.txt` 참고). 이번 호환 로직은 이 제약에서 주 분석, 시장 리뷰, Agent의 LiteLLM 직접 연결, 시스템 설정 페이지의 채널 연결 테스트를 회귀 검증했습니다.
- 그래서 이 프로젝트는 요청을 보내기 전에 **실제 요청 모드**에 따라 `kimi-k2.6`과 그 `kimi-k2.6-*` 변형을 정규화합니다. 기본 / thinking 경로는 `temperature=1.0`을 씁니다. LiteLLM YAML 라우트 별칭에 `litellm_params.extra_body.thinking.type: disabled`(또는 같은 의미의 non-thinking 설정)를 명시적으로 써 두었다면 자동으로 `temperature=0.6`으로 바꿉니다. `.env`나 Web 설정에 저장한 `LLM_TEMPERATURE`는 고쳐 쓰지 않습니다.
- 호환 플랫폼이 아직 등록되지 않은 새 모델에 대해 명확한 파라미터 오류(예: `temperature` 미지원, 기본값 `1.0`만 허용, `top_p` 미지원)를 반환하면, 런타임은 **현재 요청**의 파라미터를 한 번 고쳐 다시 시도합니다. 다시 시도가 성공했을 때만 그 방식을 현재 프로세스 안에 캐시합니다. 이 캐시는 `.env`에 쓰지 않으며, 서비스를 재시작하면 설정과 적용 규칙에 따라 다시 판단합니다.
- 이미 일부 내용을 내보낸 스트리밍 응답은 출력 도중에 파라미터를 바꾸지 않습니다. 대신 기존의 "같은 모델로 비스트리밍 재시도 / fallback 모델"이라는 안정적인 경로를 그대로 써서, 어긋난 답변이 이어 붙지 않게 합니다.
- `SystemConfigService`는 Web 설정 저장 / 데스크톱 앱 `.env` 가져오기 때 제출한 key만 갱신하며, temperature가 엄격한 모델로 바꿨다는 이유로 기존 `LLM_TEMPERATURE`를 조용히 비우거나, 옮기거나, 고쳐 쓰지 않습니다. 채널 테스트 요청에 쓴 임시 파라미터 방식도 설정 파일에 다시 쓰지 않습니다.
- 엄격하지 않은 주 모델, 엄격하지 않은 fallback, 그리고 일반 모델로 돌아간 뒤의 요청은 계속 설정한 온도를 씁니다. 즉 예전 설정을 옮길 필요가 없으며, 모델만 바꾸면 원래 동작이 자동으로 돌아옵니다.
- 이 저장소의 호환성 회귀 테스트: `tests/test_llm_channel_config.py`, `tests/test_market_analyzer_generate_text.py`, `tests/test_agent_pipeline.py`, `tests/test_system_config_service.py`.
- 최소 롤백 방법: 이번 LLM 파라미터 적용 관련 변경만 되돌리면 되며, 기존 `LLM_TEMPERATURE` 설정을 따로 옮길 필요는 없습니다.

### 호환성과 롤백 점검 목록 (PR 리뷰 기준)

- 런타임 의존성 제약: `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`(`requirements.txt`와 같음).
- 회귀 검증 진입점:
  - 채널 모델 탐색과 연결: `tests/test_llm_channel_config.py`
  - 런타임 출처 정리와 복원(데스크톱 내보내기 백업 경로 포함): `tests/test_system_config_service.py`
  - API 검증과 문제 안내 필드: `tests/test_system_config_api.py`
  - 설정 페이지 동작과 저장 후 안내: `apps/dsa-web/src/components/settings/__tests__/LLMChannelEditor.test.tsx`
- 예전 설정 롤백 경로: `데스크톱 앱 내보내기 백업 -> /api/v1/system/config/import`, 또는 `LLM_* / LITELLM_* / AGENT_LITELLM_MODEL / VISION_MODEL / LLM_TEMPERATURE / LLM_USAGE_HMAC_*`를 직접 복원합니다. Web에서 백업을 가져오기 전에도 `ADMIN_AUTH_ENABLED=true`가 필요하며, 그렇지 않으면 403을 반환합니다.

> **꼭 피해야 할 실수**: `LLM_CHANNELS`를 켰다면 바깥에 직접 적은 `DEEPSEEK_API_KEY`나 `OPENAI_API_KEY`는 **모두 무효(시스템이 전부 무시)**가 됩니다! 둘 중 **하나만 고르십시오**. 입문자 모드와 채널 모드를 함께 적어서 충돌이 나는 일이 없도록 하십시오.
> **Docker 주의**: `docker compose environment:`나 `docker run -e`에서 `LITELLM_MODEL`, `LLM_CHANNELS`, `LLM_DEEPSEEK_MODELS` 등의 변수를 명시적으로 넘기면, 컨테이너를 재시작할 때 이 환경 변수가 Web 설정 페이지가 기록한 `.env`를 덮어씁니다. 배포 설정도 함께 고쳐야 합니다.

### 호환 근거와 롤백 감사 안내 (이번 PR 적용 설명)

- 공식·런타임 호환 근거는 두 단계입니다. 첫째는 공식 인터페이스 의미(LiteLLM OpenAI-compatible 라우팅, OpenAI Chat Completions, Moonshot/Kimi 문서와 공식 모델 설명)이고, 둘째는 이 저장소의 현재 런타임 의미(`litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`)에서의 실제 오류 분류입니다.
- 이번 호환 복구는 "로컬 런타임 오류 분류 + 요청 단위 수정 재시도 + 프로세스 내 캐시" 방식만 쓰며, `.env`에 쓰거나 설정을 옮기지 않습니다. 실행 경로에서만 지원하지 않는 파라미터(`temperature`, `top_p`, `presence_penalty`, `frequency_penalty`, `seed`)를 동적으로 피합니다. 되돌리려면 별도 마이그레이션 명령 없이 예전 값을 복원하면 됩니다.
- 회귀 테스트와 근거: `tests/test_llm_param_recovery.py`, `tests/test_system_config_service.py`, `tests/test_llm_channel_config.py`, `tests/test_system_config_api.py`, `tests/test_market_analyzer_generate_text.py`, `tests/test_agent_pipeline.py`. 데스크톱 가져오기와 런타임 정리 롤백은 `test_import_desktop_env_restores_runtime_models_after_cleanup`가 직접 다룹니다.

---

### LLM usage HMAC 원격 측정

P0a usage telemetry는 실제로 보낸 message마다 HMAC-SHA256 지문을 만들어, 나중에 같은 prompt/message 앞부분이 안정적인지 판단하는 데 씁니다. 이 기능은 로컬 `llm_usage` 기록에만 쓰며, prompt, provider 파라미터, cache hint, 모델 출력, fallback 순서를 바꾸지 않습니다.

Usage 출처는 세 단계 순서로 읽습니다.

- 먼저 provider / LiteLLM 공개 응답 필드 `usage`를 읽습니다.
- 다음으로 LiteLLM 공개 응답 필드 `usage_metadata`를 읽습니다.
- 마지막으로만 `_hidden_params["usage"]`를 읽습니다. 이것은 LiteLLM private/internal best-effort fallback이며 안정적인 공개 계약이 아닙니다. 없더라도 usage/cache telemetry가 불완전할 수 있다는 뜻일 뿐, 모델 요청이 실패했다는 뜻은 아닙니다.

Cache token 정규화는 허용 목록(allowlist)에 있는 값만 best-effort로 정규화합니다. 공식적인 안정 계약, LiteLLM의 현재 정규화 동작, 이 저장소의 호환 allowlist를 섞어 이해하지 않도록 외부 필드 근거와 런타임 범위를 아래와 같이 정리합니다.

| Provider / 출처 | 읽는 필드 | 근거와 범위 | 검증 범위 |
| --- | --- | --- | --- |
| OpenAI | `usage.prompt_tokens_details.cached_tokens` | 공식 Prompt Caching 문서에 따르면 1024 tokens 미만에서도 `cached_tokens=0`을 반환합니다: <https://developers.openai.com/api/docs/guides/prompt-caching> | unit/mock 검증. 이 PR에서는 OpenAI live smoke를 하지 않음 |
| Anthropic | `cache_creation_input_tokens` / `cache_read_input_tokens` / `input_tokens` | 공식 Prompt Caching 문서가 `total_input_tokens = cache_read_input_tokens + cache_creation_input_tokens + input_tokens`로 정의합니다: <https://platform.claude.com/docs/en/build-with-claude/prompt-caching> | unit/mock 검증. 이 PR에서는 Anthropic live smoke를 하지 않음 |
| Gemini / Vertex AI | 공식 필드는 `UsageMetadata.cachedContentTokenCount`입니다. 런타임은 LiteLLM이 노출하는 snake_case / 정규화 필드, 예를 들어 `cached_content_token_count`, `cache_read_input_tokens`, `prompt_tokens_details.cached_tokens`를 사용합니다 | Gemini `UsageMetadata` 공식 필드는 <https://ai.google.dev/api/generate-content#UsageMetadata>에 있습니다. 이 저장소는 native camelCase 런타임 fallback을 추가하지 않으며, 런타임 범위는 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`을 기준으로 합니다 | unit/mock 검증. 이 PR에서는 Gemini / Vertex live smoke를 하지 않음 |
| DeepSeek | `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` | DeepSeek Chat Completion 문서에 따르면 `prompt_tokens = prompt_cache_hit_tokens + prompt_cache_miss_tokens`입니다: <https://api-docs.deepseek.com/api/create-chat-completion> | unit/mock 검증. 이 PR에서는 마스킹한 DeepSeek smoke를 한 번만 했으며 전체 응답은 저장하지 않음 |
| GLM / OpenAI-compatible / StepFun 등 호환 플랫폼 | 모델링된 token/cache count allowlist 중 통일 필드로 대응시킬 수 있는 값 | 공식적인 안정 cache telemetry 계약을 선언하지 않습니다. 현재 LiteLLM / OpenAI-compatible 형식에서 best-effort 정규화를 한다는 뜻일 뿐이며, 모델링되지 않은 metadata는 저장하지 않습니다 | unit/fixture/mock 검증. 이 PR에서는 이 provider들의 live smoke를 하지 않음 |
| LiteLLM 공개 응답 형식 | `usage` / `usage_metadata` | 현재 의존성 범위 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`의 response / `Usage` 객체 형식을 따릅니다. LiteLLM 2.x 호환을 약속하지 않습니다 | Analyzer / Agent / usage 테스트로 검증 |
| LiteLLM private fallback | `_hidden_params["usage"]` | private/internal best-effort fallback이며 LiteLLM의 안정적인 공개 계약이 아닙니다. 공개 usage가 0뿐이거나 신호가 없는 좁은 경우에만 streaming usage를 보충하며, provider 요청 파라미터는 바꾸지 않습니다 | unit/mock 검증. 없더라도 telemetry 완전성에만 영향이 있으며 모델 요청 실패를 뜻하지 않음 |

```env
LLM_USAGE_HMAC_SECRET=
LLM_USAGE_HMAC_KEY_VERSION=local-v1
```

- `LLM_USAGE_HMAC_SECRET`를 비워 두면 시스템이 데이터 디렉터리에 `.llm_usage_hmac_secret`을 만듭니다. 한 배포 안에서 로컬로 비교할 때 적합합니다.
- 여러 배포 사이에서 HMAC을 비교해야 할 때만, 같은 고엔트로피 무작위 키를 명시적으로 설정하십시오. `openssl rand -hex 32`로 만드는 것을 권장합니다.
- `.llm_usage_hmac_secret`은 로컬 비밀 파일이며, `.gitignore`에서 파일 이름으로 무시하도록 돼 있습니다.
- 키를 바꿀 때는 `LLM_USAGE_HMAC_KEY_VERSION`도 함께 바꿔, 서로 다른 키로 만든 HMAC을 잘못 비교하지 않게 하십시오.
- 로그인 session secret을 재사용하지 말고, 실제 키를 버전 관리에 커밋하거나 issue, 로그, 스크린샷에 노출하지 마십시오.

### Provider prompt cache 설정 (P1 / P1.5)

Prompt cache 설정은 이 프로젝트가 cache usage / diagnostics를 기록할지, 그리고 주 분석 경로가 검증된 provider별 hint를 직접 보낼지만 정합니다. OpenAI, Gemini, DeepSeek 등 provider의 implicit / provider-managed cache는 제어하지 않습니다.

```env
LLM_PROMPT_CACHE_TELEMETRY_ENABLED=true
LLM_PROMPT_CACHE_HINTS_ENABLED=false
LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL=off
```

- `LLM_PROMPT_CACHE_TELEMETRY_ENABLED=false`이면 provider raw usage JSON, 정규화된 cache 필드, cache decision diagnostics를 저장하지 않습니다. 기본 token usage 기록은 그대로 호환됩니다.
- `LLM_PROMPT_CACHE_HINTS_ENABLED=true`는 주 분석 / analyzer LiteLLM 경로가 registry에서 검증됐거나 smoke 테스트를 거친 provider / route에만 `prompt_cache_key`, `cache_control`, `user_id` 등의 hint를 보내도록 허용합니다. 종목 질문 Agent 경로는 현재 capability / usage diagnostics만 기록하며, provider별 hint를 직접 보내지 않습니다. 알 수 없는 OpenAI-compatible gateway는 기본적으로 telemetry만 합니다.
- `LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL=basic`은 debug 로그와 테스트에서 관찰할 수 있는 객체에만 provider, api surface, verification status, hint applied / disabled reason 같은 민감하지 않은 열거값을 제공합니다. `debug`는 같은 범위에서 HMAC 기반 route/cache diagnostics와 일치한 caps id를 추가로 제공하지만, raw prompt, request body, message content, 종목·사용자 원문, webhook, API key는 여전히 금지합니다. 이 진단 정보는 공개 Usage API나 일반 설정 페이지 출력이 아닙니다.
- Provider Cache Capability Registry는 `src/llm/provider_cache.py`에 있는, 코드 수준에서 손으로 관리하는 기능 표입니다. 각 항목에는 `doc_sources`, `last_verified_at`, `verification_status`가 있으며, provider를 추가하거나 LiteLLM을 업그레이드한 뒤에는 항목과 테스트를 함께 갱신해야 합니다.
- Prompt cache key, route key, DeepSeek session isolation은 `LLM_USAGE_HMAC_SECRET` / `.llm_usage_hmac_secret`을 재사용해 도메인을 분리한 HMAC을 만들며, prompt cache 전용 비밀 키를 따로 추가하지 않습니다.

### Legacy message 안정성 감사 (P0.5a)

P0.5a는 일반 개별 종목 분석 경로의 legacy `[system, user]` message에 내부 안정성 감사 필드를 덧붙여, 계속 로컬 `llm_usage`에 기록합니다. 위의 message HMAC을 재사용하며, prompt 내용, message 순서, provider 요청 파라미터, cache hint, 모델 출력, fallback 순서를 바꾸지 않고, 공개 Usage API나 Web 페이지도 확장하지 않습니다.

새 필드는 유지보수자의 진단용으로만 씁니다.

- `language`, `market_group`, `analysis_mode`, `legacy_prompt_mode`, `provider`, `transport`, `message_count`는 이번 일반 개별 종목 분석 호출의 저민감 라우팅 맥락을 설명합니다.
- `skill_config_hmac`은 해석된 skill prompt 조각, 기본 skill 정책, legacy prompt 모드로 만든 HMAC-SHA256이며, system message가 skill 설정에 따라 바뀌는지 판단하는 데 씁니다. skill 원문은 저장하지 않습니다.
- `known_dynamic_marker_positions`는 JSON 문자열이며 `marker_name`, `message_role`, `char_offset`만 기록합니다. 종목 코드, 종목명, 날짜, 뉴스 본문, 시세 값, headers, response text, prompt 조각은 저장하지 않습니다.
- `estimated_total_prompt_tokens`, `approx_common_prefix_chars`, `approx_common_prefix_tokens`는 프로젝트 안의 안정적인 canonical render를 기준으로 추정합니다. message 순서대로 `role + "\n" + content`를 이어 붙이고 고정 구분자로 연결합니다. 이 기준이 provider의 실제 전송 바이트와 같다고 주장하지 않습니다.
- `char_offset`은 해당 message `content` 안에서 marker의 위치입니다. `approx_common_prefix_chars`는 canonical render 시작부터 처음 알려진 동적 marker 앞까지의 문자 수입니다. marker가 없으면 common-prefix 필드는 `NULL`입니다.
- token 추정은 `ceil(chars / 3)`을 쓰며 diagnostics 용도일 뿐입니다. provider usage를 대신하지 않고 cache 기준값 판단에도 쓰지 않습니다. 중국어 문장에서는 낮게 추정될 수 있습니다.

P0.5a는 PromptBlock IR, `block_id`, `stability_class`, `static_prefix_hash`, `dynamic_context_hash`를 도입하지 않습니다. Agent, research, market review 경로는 아직 이 감사에 연결하지 않습니다.

---

<a id="方式三litellm-原生-yaml-配置适合专家或复杂路由"></a>
## 방식 3: YAML 고급 설정 (숙련자 맞춤형)

**목표:** 배우는 수고는 상관없고, 최대한의 제어권을 갖고 원래 규칙 그대로 기업 수준의 고가용성을 구성하고 싶습니다!

이 단계는 내부의 LiteLLM 라우팅 기능에 그대로 대응하며, 높은 동시 처리, 자동 재시도, RPM/TPM 기반 부하 분산 등을 지원합니다.

### 로컬 실행 / Docker 배포 모드 설정 안내

1. `.env`에는 경로를 가리키는 한 줄만 남깁니다.
   ```env
   LITELLM_CONFIG=./litellm_config.yaml
   ```
2. 프로젝트 루트 폴더에 `litellm_config.yaml`을 만듭니다(저장소에 포함된 `docs/examples/litellm_config.example.yaml`을 참고하면 됩니다).

예시 `litellm_config.yaml`:
```yaml
model_list:
  - model_name: my-smart-model
    litellm_params:
      model: deepseek/deepseek-v4-flash
      api_base: https://api.deepseek.com
      api_key: "os.environ/MY_CUSTOM_SECRET_KEY"  # 환경 변수에서 Key를 읽어 유출을 막습니다

  # Ollama 로컬 모델 (api_key 불필요)
  - model_name: ollama/qwen3:8b
    litellm_params:
      model: ollama/qwen3:8b
      api_base: http://localhost:11434
```

### GitHub Actions 설정 안내

1. `Settings` → `Secrets and variables` → `Actions`로 이동합니다. 민감하지 않은 설정(모델 이름, 스위치, Base URL 등)은 `Secret`이나 `Variables` 어느 쪽에 두어도 됩니다. `*_API_KEY` / `*_API_KEYS`, 그리고 `LLM_<NAME>_API_KEY` / `LLM_<NAME>_API_KEYS` 같은 비밀 키 필드는 모두 `Secret` 탭의 `New repository secret`에 넣으십시오.

2. 아래 표대로 설정합니다. 필수 설정을 모두 올바르게 넣어야만 YAML 고급 설정 모드가 적용됩니다. YAML 설정 파일 작성법은 저장소에 포함된 `docs/examples/litellm_config.example.yaml`을 참고하십시오.

| Secret 이름 | 설명 | 필수 여부 |
|------------|------|:----:|
| `LITELLM_CONFIG` | 고급 모델 라우팅 설정 파일 경로이며, 보통 `./litellm_config.yaml`로 설정합니다 | 필수 |
| `LITELLM_MODEL` | 기본 주 모델 이름 또는 라우트 별칭 | 필수 |
| `LITELLM_CONFIG_YAML` | YAML 설정 파일 내용을 담습니다. 이렇게 하면 실제 파일을 저장소에 커밋하지 않아도 됩니다 | 선택 |
| `LITELLM_API_KEY` | API Key를 저장하며, 설정 파일에서 환경 변수 참조 방식으로 쓸 수 있습니다. GitHub Actions는 가져올 환경 변수를 미리 지정해야 하므로, 로컬 실행처럼 환경 변수 이름을 자유롭게 정할 수 없습니다 | 선택, 반드시 repository secret에 설정 |
| `ANTHROPIC_API_KEY` | API Key가 여러 개 필요하면 이 변수 이름도 쓸 수 있습니다 | 선택, 반드시 repository secret에 설정 |
| `OPENAI_API_KEY` | 위와 같으며, API Key 저장에 쓸 수 있습니다 | 선택, 반드시 repository secret에 설정 |

채널 모드는 YAML 파일을 올릴 필요가 없습니다. 저장소에 포함된 `00-daily-analysis.yml`은 다음과 같은 자주 쓰는 필드를 명시적으로 전달합니다.

- 런타임 선택: `GENERATION_BACKEND`, `GENERATION_FALLBACK_BACKEND`, `GENERATION_BACKEND_TIMEOUT_SECONDS`, `GENERATION_BACKEND_MAX_OUTPUT_BYTES`, `GENERATION_BACKEND_MAX_CONCURRENCY`, `LOCAL_CLI_BACKEND_MAX_CONCURRENCY`, `AGENT_GENERATION_BACKEND`, `LLM_CHANNELS`, `LITELLM_MODEL`, `LITELLM_FALLBACK_MODELS`, `AGENT_LITELLM_MODEL`, `VISION_MODEL`, `VISION_PROVIDER_PRIORITY`, `LLM_TEMPERATURE`, `LLM_USAGE_HMAC_SECRET`, `LLM_USAGE_HMAC_KEY_VERSION`, `LLM_PROMPT_CACHE_TELEMETRY_ENABLED`, `LLM_PROMPT_CACHE_HINTS_ENABLED`, `LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL`
- 다중 Key: `GEMINI_API_KEYS`, `ANTHROPIC_API_KEYS`, `OPENAI_API_KEYS`, `DEEPSEEK_API_KEYS`(현재 workflow는 repository secrets에서만 가져오며, 같은 이름의 Variables는 읽지 않습니다)
- 자주 쓰는 채널 이름: `modelflare`, `primary`, `secondary`, `aihubmix`, `anspire`, `deepseek`, `dashscope`, `zhipu`, `moonshot`, `minimax`, `volcengine`, `siliconflow`, `openrouter`, `requesty`, `gemini`, `anthropic`, `openai`, `ollama`, `hermes`

예를 들어 GitHub Actions에서 `LLM_CHANNELS=primary,deepseek`로 설정하면 `LLM_PRIMARY_*` / `LLM_DEEPSEEK_*`도 함께 설정해야 합니다. 그중 `LLM_<NAME>_API_KEY` / `LLM_<NAME>_API_KEYS`는 현재 repository secrets에서만 가져옵니다. 이 값을 Variables에 넣으면 런타임에 적용되지 않습니다. 사용자 정의 채널 이름(예: `my_proxy`)을 쓰면 GitHub Actions에서는 workflow `env:`에 해당 `LLM_MY_PROXY_*` 대응을 명시적으로 추가해야 합니다. 로컬 `.env`와 Docker에는 이 제한이 없습니다.


> **3단계 설정 상호 배타 원칙**: YAML의 우선순위가 가장 높습니다! YAML을 설정하면 **채널 모드**와 **입문자 간단 모드**는 모두 무시됩니다. 시스템 우선순위는 `YAML 설정 > 채널 모드 > 단일 모델 간단 설정`입니다.

---

<a id="扩展功能看图模型-vision-配置"></a>
## 확장 기능: 이미지 인식 모델 (Vision) 설정

시스템의 일부 기능(예: 증권 앱 스크린샷을 올리면 AI가 그 안의 종목 코드를 뽑아 관심 종목 목록에 넣는 기능)에는 반드시 "시각 능력"이 있는 모델이 필요합니다. `.env`에서 이미지를 이해하는 모델을 따로 지정해야 합니다.

```env
# 이미지 인식 전용 모델 이름을 지정합니다
VISION_MODEL=openai/gpt-5.5
# 해당 제공자의 API KEY도 꼭 넣으십시오. OpenAI 호환 채널이라면 OPENAI_API_KEY를 넣습니다:
# OPENAI_API_KEY=xxx
```

**예비 이미지 인식 방식:** 가끔 작동하지 않는 경우에 대비해 시스템에 전환 방식이 들어 있습니다. 주 비전 모델 호출이 실패하면 아래 순서대로 다른 이미지 인식 모델의 Key가 있는지 찾아 시도합니다.
```env
# 기본 예비 순서:
VISION_PROVIDER_PRIORITY=gemini,anthropic,openai
```

---

## 점검과 문제 해결 (Troubleshooting)

설정은 했는데 맞게 했는지 불안하다면, 명령줄(Terminal, Windows는 PowerShell 또는 명령 프롬프트)에 아래 명령을 입력해 점검해 보십시오.

- `python scripts/check_env.py --config`: `.env` 설정 파일의 내용이 논리적으로 맞는지, 빠뜨린 것은 없는지만 점검합니다. (결과가 바로 나오며, 네트워크를 쓰지 않고 로컬 텍스트만 확인합니다)
- `python scripts/check_env.py --llm`: 시스템이 실제로 모델에 인사말을 한 번 보내고, 그 답을 직접 보여 줍니다. **네트워크가 연결되는지, 계정 잔액이 남아 있는지**를 확실히 확인할 수 있습니다.

### 자주 겪는 문제와 해결

| 어떤 오류가 났나요? | 원인은 무엇일까요? | 어떻게 해결하나요? |
|----------------------|----------------------|------------------|
| **화면에 주 모델이 설정되지 않았다고 나옴** | 시스템이 어느 회사의 어떤 모델을 쓰려는지 모릅니다 | `.env`에 분명하게 한 줄 적으십시오: `LITELLM_MODEL=provider/모델이름`. 예: `openai/gpt-5.5` |
| **여러 회사의 Key를 적었는데 왜 하나만 적용되나요? 고쳐도 소용이 없어요** | **간단 모드**와 **채널 모드**를 섞어 적었습니다! | 한 가지 방식만 정해서 끝까지 쓰십시오. 간단하게 쓰려면 `LLM_CHANNELS`로 시작하는 줄을 지우고, 예비 전환을 넉넉히 쓰려면 모두 `LLM_CHANNELS` 아래 설정으로 옮기십시오. |
| **오류 코드 400, 401 또는 Invalid API Key** | API Key를 잘못 넣었거나, 일부만 복사했거나, 충전이 아직 반영되지 않았거나, 모델 이름을 잘못 입력했습니다(아주 흔합니다). | 1. 복사한 Key 앞뒤에 공백이 들어갔는지 확인합니다.<br> 2. Base URL 끝에 `/v1`이 빠지지 않았는지 확인합니다.<br> 3. 모델 이름에 `openai/` 같은 접두사가 빠지지 않았는지 확인합니다! |
| **Kimi K2.6에서 `invalid temperature` 오류(`1.0` 또는 `0.6`만 허용한다고 나올 수 있음)** | 이 모델은 thinking / non-thinking 모드에 따라 정해진 temperature를 요구하는데, 예전 설정이나 호출 진입점이 아직 `0.7`을 보내고 있을 수 있습니다. | 업그레이드하면 시스템이 `kimi-k2.6` 기본 / thinking 요청에 자동으로 `temperature=1.0`을 씁니다. LiteLLM YAML 라우트에서 thinking을 명시적으로 껐다면 자동으로 `0.6`을 씁니다. 모델 이름은 `openai/kimi-k2.6`으로 쓰고, Moonshot이나 통합 플랫폼의 OpenAI 호환 Base URL과 API Key를 함께 쓰는 것을 권장합니다. Kimi가 아닌 fallback은 계속 설정한 `LLM_TEMPERATURE`를 씁니다. |
| **GPT-5 / o 시리즈에서 `temperature` 미지원 또는 기본값만 허용 오류** | 이런 모델은 서버 기본 샘플링 파라미터만 받는데, 예전 호출 진입점이 `0.7`을 명시적으로 보냅니다. | 업그레이드하면 요청 단계에서 `temperature`를 빼고 서버가 기본값을 쓰게 합니다. `.env` / Web 설정의 `LLM_TEMPERATURE`는 고쳐 쓰지 않으며, 일반 모델로 돌아가면 원래 값을 그대로 보냅니다. |
| **로딩만 계속되다가 결국 Timeout / ConnectionRefused 등의 오류** | 1. 중국 본토에서 해외 원본 서비스(Google, OpenAI 등)를 프록시 없이 쓰다가 차단됐습니다.<br>2. 구매한 클라우드 서버가 아예 해외로 나가는 연결을 할 수 없습니다. | 네트워크 환경에 맞는 **공식 서비스**(중국 본토라면 DeepSeek, 알리바바 등)나 **OpenAI 호환 통합 중계 API**를 쓰는 것을 적극 권장합니다. 중계 서비스가 네트워크 문제를 대신 해결해 주기 때문입니다. (한국에서는 해외 서비스에 보통 바로 연결됩니다.) |
| **Ollama에서 404, `Could not get model info` 또는 `api/generate/api/show` 오류** | Ollama를 `OPENAI_BASE_URL`로 잘못 설정해서 시스템이 URL을 잘못 이어 붙였습니다 | `OLLAMA_API_BASE=http://localhost:11434`를 쓰거나 채널 모드(`LLM_CHANNELS=ollama` + `LLM_OLLAMA_BASE_URL`)로 바꾸십시오 |

*숙련자의 조언: **Agent(깊은 추론 + 웹 검색 종목 질문) 모드**를 켰다면, 경험상 `deepseek-v4-pro`처럼 논리 추론 능력이 더 강한 모델을 고르는 것을 권장합니다. 비용을 아끼려고 아주 작은 모델로 Agent를 돌리면 논리 능력이 따라가지 못할 가능성이 높아, 기대한 결과를 얻지 못할 뿐 아니라 쓸모없는 과정만 잔뜩 돌게 됩니다.*
