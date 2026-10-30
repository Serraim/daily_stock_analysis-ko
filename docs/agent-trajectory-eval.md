# Agent Trajectory 평가(최소 버전, Refs #1956)

## 목적

`evals/agent_trajectory/`는 **오프라인으로 실행할 수 있는 최소 궤적(trajectory) 평가 파이프라인**을 제공합니다. 실제 `tool_calls_log + AgentResult`로 golden 예제를 실행하고, 구조화된 JSON 리포트와 짧게 읽을 수 있는 텍스트 요약을 출력합니다. 평가 결과는 **gate가 아니라 reporter**입니다. 지표 위반은 리포트에만 나타나며, 프로세스를 실패시키지 않고 CI 관문에도 들어가지 않습니다.

- 지표 계층(`metrics.py`)은 순수 함수입니다. 궤적 로그와 golden 예제만 사용하며, `src/`를 import하지 않고, 네트워크에 접속하거나 LLM을 호출하지 않아 오프라인 단위 테스트가 가능합니다.
- 진입점(`run_eval.py`)은 `build_agent_executor()`로 실제 실행기를 만들고, `src/core/pipeline.py`와 같은 실행 캡처 훅을 써서 실제 결과물을 사용합니다.
- 진입점은 **단일 agent와 다중 Agent 실행**(`AGENT_ARCH=single|multi`, 기본값은 여전히 single)을 지원합니다. 다중 Agent 결과는 기존의 평평한 `tool_calls_log` 지표를 유지하면서, 명시적인 `stage_trajectories` 스냅샷으로 단계 상태와 단계별/누적 단계 수 리포트를 더합니다. 단계 스냅샷이 없으면 단일 agent 명령과 JSON 구조는 그대로입니다.
- 진입점은 실제 도구 레지스트리로 golden을 검증합니다. `expected_tools`에 오타가 있거나 오래된 이름이면, 조용히 낮은 적중률로 점수를 매기는 대신 잘못된 예제로 판정합니다(종료 코드 1).
- 이번에는 **최소 지표 계약**을 고정합니다. 종목 guard, Codex `arguments_summary` 같은 확장 의미는 이후 PR로 명확히 넘깁니다(문서 끝 「범위 밖」 참고).

## 빠른 시작

```bash
# 예제 하나 실행(실제 LLM 사용, 로컬에 설정된 모델 필요)
python evals/agent_trajectory/run_eval.py --sample 600519_technical

# 모든 예제를 실행하고 구조화된 JSON 출력(예제 id를 키로 사용)
python evals/agent_trajectory/run_eval.py --all --json-out eval_report.json
```

매개변수:

| 매개변수 | 설명 |
| --- | --- |
| `--sample ID` / `--all` | 둘 중 하나는 반드시 지정: golden 예제 하나 또는 전체 실행 |
| `--golden-path PATH` | 사용자 지정 golden JSON 경로(기본값은 모듈 옆 `golden_samples.json`) |
| `--json-out PATH` | 구조화된 JSON 리포트 기록(`--all`이면 키로 묶인 객체) |

종료 코드: `0`은 실행 성공(위반 포함). `1`은 golden 로드 실패(`expected_tools`가 실제 도구 레지스트리에 없는 경우 포함) / 예제 선택 실패 / 도구 레지스트리 로드 실패 / 실행기 생성 실패 / 실행 실패(실행기가 `success=false`를 돌려준 경우 포함. 예: provider 미설정, LLM 오류, 타임아웃, max_steps 소진, dashboard 파싱 실패). `2`는 사용법 오류입니다. 다중 Agent 결과가 실패하면서 단계 스냅샷을 가지고 있으면, 진입점은 먼저 확인 가능한 실패 궤적 리포트를 출력하고 기록한 뒤 종료 코드 `1`로 실행 실패를 알립니다. 단일 Agent 실패 동작은 바뀌지 않습니다.

## 고정된 최소 지표 계약

각 `tool_calls_log`(runner 계약: 항목마다 `step / tool / arguments / success / duration / result_length / cached`를 포함하고, 선택적으로 `timeout` / `guarded`)에 대해 다음만 집계합니다.

| 지표 | 정의 |
| --- | --- |
| `expected_hit_rate` / `missing_expected` | 기대한 도구를 **도구 이름** 기준으로 적중했는지(이번 버전은 종목 단위 판정을 하지 않음). `expected_total`은 중복을 뺀 기대 개수 |
| `optional_tools_used` | 기대 목록 밖에서 실제로 호출한 도구. `allow_optional_tools=false`이면 위반으로 기록 |
| `redundant_calls` | 같은 (tool, args-key) 쌍이 처음 나온 뒤 다시 나온 모든 경우(성공 여부와 무관). args-key = `json.dumps(arguments, sort_keys=True, default=str)`이며, 실행 시 캐시 키와 같은 방식 |
| `retries` | **실패** 바로 뒤에 같은 (tool, args-key) 쌍을 다시 시도한 경우. `retries ⊆ redundant_calls`. 성공하면 그 쌍의 실패 상태가 지워지므로 `fail → success → success`는 retry 1번만 셉니다(뒤의 success는 중복으로만 셈) |
| `failed_calls` | `success=false`인 항목 수 |
| `cached_calls` | `cached=true`인 항목 수(runner 의미: 다시 시도할 수 없는 실패 결과를 재사용) |
| `distinct_steps` / `max_steps_touched` | 로그의 step과 `AgentResult.total_steps` 중 큰 값(마지막 순수 답변 차례는 도구 호출이 없어 로그가 적게 셈). `max_steps_touched`는 `max(step) >= allowed_max_steps`인지 보는 추정 기준 |

## 다중 Agent 단계 궤적

실행기 결과에 비어 있지 않은 `stage_trajectories`가 있으면, 진입점은 위의 도구 지표 외에 `stage_metrics`도 출력합니다. 각 단계 스냅샷은 안정적인 JSON-safe 허용 목록 객체입니다.

| 필드 | 설명 |
| --- | --- |
| `stage_name` | 단계 또는 specialist 이름 |
| `status` | `completed` / `failed` / `skipped` 등 단계 상태 |
| `total_steps` | 그 단계 자체의 agent-loop 단계 수이며, 전체 단계 개수가 아님 |
| `tool_calls_log` | 그 단계의 원본 도구 호출 로그. 로그가 비어 있어도 단계는 유지 |
| `failure_reason` | `stage_failure` / `timeout` / `budget_skip` 등 기능 저하 원인 |

평가 계층은 스냅샷 목록 순서대로 단계별 단계 수를 더해 `cumulative_steps`를 만들므로, 단계마다 1부터 다시 세어도 겹치지 않습니다. 이 누적값은 전체 다중 Agent 궤적의 agent-loop 단계 수로 최상위 지표에도 전달됩니다. `AgentResult.total_steps`는 orchestrator에서 기존의 단계 개수 의미를 유지하며, 궤적 loop 예산 채점에는 쓰지 않습니다. 리포트에는 기대 단계 적중률, 누락/추가 단계, 완료/실패/건너뜀 개수, 단계별 상태, 실패 원인, 단계별/누적 단계 수, 도구 호출/실패/재시도 지표가 함께 들어갑니다. 단계의 `tool_metrics`는 그 단계 로그 안의 호출 수, 도구 이름, 중복, 캐시, 실패, 재시도만 세며, 기대 도구 적중률, 누락 도구, 기대 밖 도구 위반, max-steps 위반은 포함하지 않습니다. Golden의 `expected_tools`, `allow_optional_tools`, `allowed_max_steps`는 예제 전체에 속하므로 합산된 도구 궤적에 대해 한 번만 평가합니다. 지금은 단계별 도구 규정 기대값을 정의할 수 없습니다. 핵심 단계가 실패해도 이미 돌아온 스냅샷으로 단계 리포트를 만듭니다. `expected_stages`를 설정했다면 아직 실행되지 않은 이후 단계는 누락 단계로 올라갑니다. specialist를 동시에 실행한 뒤의 스냅샷은 scheduler가 선택 순서로 되돌리며, 완료 순서에 의존하지 않습니다.

golden 예제에는 선택적으로 `expected_stages` 필드를 넣을 수 있습니다.

```json
{
  "expected_stages": ["technical", "intel", "decision"]
}
```

설정하지 않아도 실제 단계와 상태는 보고하지만, 단계 적중률은 미설정으로 표시됩니다. 기존 단일 agent 예제의 JSON 필드는 바뀌지 않습니다.

## Golden 예제 schema

`golden_samples.json`은 배열이며, 필드는 다음과 같습니다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | 고유한 예제 id(필수) |
| `task_description` | string | 실행기에 넘길 작업 텍스트(필수) |
| `stock_code` | string | runner context(`{"stock_code": ...}`)에 그대로 전달. 빈 문자열 = context 없음. 채점에는 쓰지 않음 |
| `expected_tools` | string[] | 기대 도구 이름(필수, 비어 있으면 안 되고 중복 없음) |
| `allowed_max_steps` | int | 단계 수 예산 추정 기준(기본값 10, 1 이상) |
| `allow_optional_tools` | bool | 기대 밖 도구를 허용할지(기본값 true) |
| `expected_stages` | string[] | 다중 Agent 기대 단계 목록(선택, 이름은 비어 있지 않고 중복 없음). 적중 단계와 누락 단계 집계에 사용 |

검증: 로드 경로(`load_golden_samples`)는 잘못된 예제를 바로 거부합니다. 직접 생성 경로(`compute_trajectory_metrics`)는 validator와 완전히 같은 문구로 위반을 하나씩 보고하므로, 두 경로의 계약은 구조적으로 일치합니다. `known_tool_names`로 실제 도구 레지스트리를 주입해 멤버 여부를 검사할 수 있으며(metrics 계층 자체는 `src/`를 import하지 않음), `run_eval.py` 진입점은 실제 도구 레지스트리를 자동으로 주입합니다.

## JSON 리포트 schema

예제 하나:

```json
{
  "sample_id": "600519_technical",
  "task_description": "…",
  "stock_code": "600519",
  "metrics": { "expected_hit_rate": …, "expected_total": …, "…": "… 共 11 个字段" },
  "violations": ["…"]
}
```

(위 예시의 `"… 共 11 个字段"`는 "필드가 모두 11개"라는 뜻의 자리 표시 문구입니다.)

`--all --json-out`이면 바깥쪽은 `{sample_id: <위 객체>}` 형태의 키로 묶인 객체입니다.

단계 스냅샷이 있는 다중 Agent 리포트는 위 객체에 `run_status`(`completed` / `failed`)와 `stage_metrics` 필드를 더합니다. 기존 `metrics` 필드는 계속 평평한 도구 궤적 지표를 뜻합니다. 실행이 실패했어도 단계 스냅샷이 있으면 JSON 리포트는 여전히 기록되며, 프로세스 종료 코드는 1입니다.

## 범위 밖(이후 PR)

- 종목 단위 적중 판정과 guard 차단 의미(`guarded` / 범위를 벗어난 호출 위반)
- Codex App Server의 `arguments_summary` 표기 방식 인식
- 모든 `.env` / 실행 시 설정과 CI 관문(이 PR은 기존 분석 흐름, 스케줄 의미, CI 차단 규칙을 바꾸지 않습니다)
