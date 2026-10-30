# 실행 진단과 데이터 신뢰성 1.0(Phase 2)

이 문서는 #1391 Phase 2에서 백엔드에 반영한 범위를 기록합니다. Phase 1의 `trace_id`와 provider 실행 기록을 바탕으로 사용자가 읽을 수 있는 실행 진단 요약을 만들고, 민감 정보를 가린 문제 해결용 텍스트를 복사할 수 있게 합니다.

## 이번 범위

- `RunDiagnosticSummary` 집계 로직을 추가해 전체 상태를 출력합니다.
  - `normal` / 정상
  - `degraded` / 일부 기능 저하
  - `failed` / 실패
  - `unknown` / 알 수 없음
- 요약은 다음 핵심 단계를 다룹니다.
  - 실시간 시세
  - 일봉 데이터
  - 뉴스 검색
  - LLM
  - 알림
  - 이력 저장
- `AnalysisService`의 동기/비동기 작업 결과에 선택 필드 `diagnostic_summary`를 추가합니다.
- 과거 리포트 진단 API를 추가합니다.

```http
GET /api/v1/history/{record_id}/diagnostics
```

`record_id`에는 이력 기록의 기본 키 ID나 `query_id`를 쓸 수 있으며, 진단 요약과 `copy_text`를 돌려줍니다.

## 문제 해결 정보 복사

`copy_text`는 issue 작성이나 문제 해결용 일반 텍스트이며 다음을 포함합니다.

- `trace_id`
- `query_id`
- `stock_code`
- `trigger_source`
- 전체 `data_status`
- 실시간 시세, 일봉, 뉴스, LLM, 알림, 이력 저장의 간단한 상태
- 가장 중요한 원인

생성하기 전에 실행 진단의 민감 정보 가림 규칙을 그대로 적용해 token, API key, Authorization, Cookie, webhook URL, 메일 비밀번호, 프록시 자격 증명 같은 민감 정보가 나오지 않게 합니다.

## 호환성 범위

- 이번에는 설정 항목을 추가하지 않으며, 데이터 소스 우선순위와 fallback 전략도 바꾸지 않습니다.
- 이번에는 LLM/provider/Base URL/설정 마이그레이션의 의미를 바꾸지 않으며, 이력 스냅샷의 진단 필드와 조회 API만 추가합니다.
- API는 선택 필드와 새 읽기 전용 API만 추가하므로, 예전 클라이언트는 무시하면 됩니다.
- 예전 리포트에 `context_snapshot.diagnostics`가 없으면 오류 없이 `unknown`을 돌려줍니다.
- 알림 진단은 현재 작업 맥락에서 기록합니다. 과거 리포트를 저장할 때 알림 결과가 아직 없었다면 요약에 알림 결과가 알 수 없음으로 표시됩니다.
- 진단 요약 생성이 실패해도 리포트 읽기나 분석의 주 흐름에 영향을 주면 안 됩니다.

### 구조화 검사 경고에 대한 설명

- 자동 검사에서 잡힌 "모델/provider/base URL 호환성 위험"의 출처는 다음과 같습니다. `src/agent/factory.py`에 `agent_max_steps`와 `agent_orchestrator_timeout_s`에 대한 **숫자 안전 보정**(`_coerce_config_int`)이 추가되어, 스캔이 이를 설정에 민감한 경로로 잘못 판단했을 수 있습니다. 이 결과는 테스트와 라우팅 보호 때문에 걸린 것이며, 실행 시점의 설정이나 호환성 의미가 바뀐 것은 아닙니다.
- 숫자 설정에 잘못된 값이 있으면 시스템은 `src.agent.factory` 로그에 `warning`을 남기고(예: `[AgentFactory] Invalid value for agent_max_steps...`) 기본값으로 돌아갑니다. 이 로그는 "설정이 적용되지 않는" 문제를 찾는 데 쓰이며, 모델/provider/base URL 호환성과는 별개입니다.
- 이번 변경에서 몰래 마이그레이션하거나 지우거나 고쳐 쓰는 일이 없음을 확인했습니다.
  - `src/core/pipeline.py`와 `src/services/analysis_service.py`는 진단 기록만 추가하며, `Config`의 `litellm_model`, `agent_litellm_model`, `openai_base_url`, 채널 `LLM_*` 필드를 바꾸지 않습니다.
  - `src/agent/factory.py`의 `_coerce_config_int`는 실행 매개변수를 만들 때 `max_steps`와 `timeout_seconds`만 계산하며, `config` 객체에 다시 쓰지 않습니다. `litellm_model`, `agent_litellm_model`, `openai_base_url`의 원래 값은 생성 과정에서 그대로 전달됩니다.
  - 이번 변경은 `Config`의 실행 중 정리, 영구 저장, 마이그레이션 흐름을 건드리지 않으므로, 다시 쓰기 때문에 실행 중 설정이 바뀔 위험이 없습니다.
- 회귀 검증: `tests/test_agent_pipeline.py::TestAgentConfig::test_build_agent_executor_does_not_mutate_llm_route_config`와 `tests/test_agent_pipeline.py::TestAgentConfig::test_build_agent_executor_multi_arch_does_not_mutate_llm_route_config`가 `build_agent_executor` 실행 뒤에도 위 필드가 원래 값을 유지하는지 확인합니다.
- 되돌리는 방법: 예전 동작으로 돌아가려면 이번 관련 커밋을 제거하거나, `context_snapshot`/`RunDiagnosticSummary`의 역직렬화 과정에서 `diag_*` 필드를 빼면 됩니다. 주 흐름과 모델/provider 설정은 따로 마이그레이션하거나 고칠 필요가 없습니다.

## 검증 방법

```bash
python -m pytest tests/test_run_diagnostics_p2.py tests/test_run_diagnostics_p1.py
python -m py_compile src/services/run_diagnostics.py src/services/history_service.py api/v1/endpoints/history.py api/v1/schemas/history.py
```
