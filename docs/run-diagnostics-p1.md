# 실행 진단과 데이터 신뢰성 1.0 (Phase 1)

이 문서는 #1391 Phase 1에서 실제로 반영하는 최소 런타임 범위를 정리합니다. 핵심은 `trace_id`를 통일하고, 1차 핵심 데이터 경로에 대해 provider 시도 내역을 구조화해 기록하는 것입니다.

## 이번 범위

- API / Web 비동기 작업을 만들 때 `TaskInfo`는 `task_id`를 기본 `trace_id`로 사용합니다.
- 작업 목록, 작업 상태, SSE 이벤트에 `trace_id` 필드가 추가됩니다. 기존 클라이언트는 이 필드를 무시해도 됩니다.
- 동기 분석은 해당 요청의 `query_id`를 기본 `trace_id`로 사용합니다.
- pipeline 실행 중에는 가벼운 진단 컨텍스트를 만들어 일봉 데이터 준비부터 개별 종목 분석까지 이어서 사용합니다.
- `data_provider/base.py`는 다음 경로에 대해 `ProviderRun` 형식의 이벤트를 기록합니다.
  - `daily_data`
  - `realtime_quote`
- 진단 기록은 메모리 컨텍스트에 쌓였다가 분석의 `context_snapshot.diagnostics`에 함께 저장됩니다. 이 필드가 없는 예전 이력 기록도 그대로 읽을 수 있습니다.

## `ProviderRun` 필드

첫 버전은 필드를 최소한으로 유지합니다.

- `trace_id`
- `data_type`
- `provider`
- `operation`
- `success`
- `latency_ms`
- `error_type`
- `error_message_sanitized`
- `fallback_to`
- `record_count`
- `created_at`

오류 요약에는 기본적인 마스킹이 적용되어 token, API key, Authorization, Cookie, 민감한 매개변수가 들어 있는 webhook URL 등이 출력되지 않습니다.

## 안정성 경계

- 진단 기록이 실패해도 warning만 남기며, 주 분석, 데이터 소스 fallback, 이력 저장에는 영향을 주지 않습니다.
- 이번에는 설정 항목을 새로 만들지 않고, 데이터 소스 우선순위와 fallback 전략도 바꾸지 않습니다.
- 이번에는 Web 표시 컴포넌트를 추가하지 않습니다. `trace_id`와 provider 실행 기록은 먼저 API/SSE/이력 스냅샷에 담아 두고, 이후 Phase 2/3에서 집계와 표시에 재사용합니다.

## 검증 방법

```bash
python -m pytest tests/test_run_diagnostics_p1.py tests/test_analysis_api_contract.py::AnalysisApiContractTestCase::test_get_analysis_status_normalizes_completed_queue_result_contract
python -m py_compile src/services/run_diagnostics.py src/services/task_queue.py src/services/analysis_service.py src/core/pipeline.py data_provider/base.py api/v1/schemas/analysis.py api/v1/endpoints/analysis.py
```
