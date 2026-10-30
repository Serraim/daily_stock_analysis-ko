# 실행 진단과 데이터 신뢰성 1.0(Phase 3)

이 문서는 #1391 Phase 3에서 제공한 범위를 기록합니다. 새 설정을 추가하지 않고 실행 진단을 화면에서 볼 수 있게 보완했으며, 과거 문제 해결 정보를 백엔드 컨텍스트 스냅샷에 채워 넣어 직접 배포한 환경에서 이상을 빠르게 찾을 수 있게 했습니다.

## 이번 범위

- 과거 보고서 상세 화면에 기본으로 접혀 있는 "실행 진단 / 데이터 신뢰성" 영역을 추가했습니다. #1523 이후 Web 표시 제목은 "실행 진단 / 실행 상태"로 바뀌었고, 이 단계의 제목은 그대로입니다.
- 작업 패널은 진행 중인 작업의 trace 정보를 기본으로 접어서 보여 줍니다. 백엔드 로그, SSE, 과거 보고서 진단과 이어서 보기 쉽게 하기 위해서입니다.
- 과거 보고서는 읽기 전용 엔드포인트로 진단 요약을 가져옵니다.

```http
GET /api/v1/history/{record_id}/diagnostics
```

- 동기 분석 응답에 이미 `diagnostic_summary`가 있으면 프론트엔드는 과거 기록 엔드포인트를 따로 부르지 않고 바로 보여 줍니다.
- 진단 패널에서 백엔드가 만든, 민감 정보를 가린 `copy_text`를 복사할 수 있습니다. issue 작성이나 배포 문제 해결에 씁니다.
- 분석 흐름은 과거 기록을 저장한 뒤 작업/Provider/LLM/알림 진단을 `context_snapshot.diagnostics`에 채워 넣고, 과거 진단 엔드포인트가 이를 사용자가 읽기 쉬운 요약으로 모읍니다.
- 홈 화면의 실행 흐름 패널은 같은 RunFlowSnapshot 계약으로 진행 중인 작업(active task), 완료된 보고서, 시장 리뷰를 보여 줍니다. 진행 중인 작업은 작업 SSE의 선택적 증분 이벤트로 이벤트 흐름을 실시간으로 덧붙이고, 완료되거나 연결이 끊기면 스냅샷을 다시 가져와(refetch) 최종 결과를 맞춥니다.

## 실행 흐름 실시간 증분

실행 흐름 증분을 위해 별도의 SSE 엔드포인트를 새로 만들지 않고, 다음을 그대로 다시 씁니다.

```http
GET /api/v1/analysis/tasks/stream
```

호환 계약:

- 이벤트 종류는 여전히 `task_progress`입니다.
- 기존 task payload 필드는 바뀌지 않습니다.
- 이번 진행 상황 업데이트가 실행 진단에서 온 경우 `flow_event` 필드를 선택적으로 덧붙입니다. 예전 클라이언트는 이 필드를 무시하면 됩니다.
- `flow_event`는 `RunFlowSnapshot.events[]`와 같은, 민감 정보를 가린 이벤트 구조를 씁니다: `id`, `timestamp`, `severity`, `type`, `node_id`, `title`, `message`, `metadata`.
- 진행 중인 작업에는 `provider_run_started` / `llm_run_started` 실시간 이벤트가 덧붙을 수 있습니다. 이 이벤트는 실행 중인 running 카드 표시에만 쓰이며, 완료 후에는 같은 `node_id`의 `provider_run` / `llm_run` 결과 이벤트가 상태를 덮어씁니다. 과거 진단은 여전히 최종 결과를 기준으로 합니다.
- 백엔드 TaskQueue는 진행 중인 작업마다 최근 N개의 실행 흐름 이벤트만 보관해 메모리가 끝없이 늘어나지 않게 합니다. 전체 기록은 여전히 `context_snapshot.diagnostics`와 과거 RunFlowSnapshot을 기준으로 합니다.

예시(`message`, `title` 값은 프로그램이 만드는 중국어 문구 예시입니다. "LLM이 분석 결과를 생성하는 중", "LLM 성공"이라는 뜻입니다):

```json
{
  "task_id": "3f87...",
  "trace_id": "3f87...",
  "stock_code": "600519",
  "status": "processing",
  "progress": 64,
  "message": "LLM 正在生成分析结果",
  "flow_event": {
    "id": "flow_0002",
    "timestamp": "2026-06-08T22:30:24",
    "severity": "success",
    "type": "llm_run",
    "node_id": "llm_analysis_1",
    "title": "LLM 成功",
    "message": "LLM deepseek-chat 成功"
  }
}
```

실행 진단 기록 함수는 provider, LLM, 과거 기록 저장, 알림 기록이 메모리 진단에 성공적으로 쓰인 뒤 fail-open 방식으로 event sink를 실행합니다. sink가 실패하면 warning만 기록하며, 분석·저장·알림의 성공/실패 판정은 바꾸지 않습니다.

뉴스 정보 검색도 같은 provider 진단 방식에 포함됩니다. `SearchService.search_stock_news()`는 `data_type=news_search`로 Tavily, SearXNG, Bocha, Brave 등 검색 provider의 시도, 필터링 후 결과 수, 캐시 적중, 실패 이유를 기록합니다. 여러 검색 provider를 연달아 시도하면 Web 실행 흐름 기본 화면은 이를 "뉴스·여론" 노드 하나로 묶습니다. 카드에는 provider 순서와 상태를, 노드 상세에는 성공/실패 횟수와 fallback / retry 횟수를 보여 줍니다. 문제를 찾아야 할 때는 이 묶음 노드를 펼쳐 provider 시도를 하나씩 볼 수 있습니다.

실행 흐름 구성도의 데이터 출처 레인(lane)은 노드 시작 시각 순으로 먼저 정렬합니다. provider / LLM 노드에 완료 시각과 소요 시간만 있으면 `ended_at - duration_ms`로 `started_at`을 추정하고 카드에 시작 시각을 보여 줍니다. 쓸 수 있는 시각이 없는 노드는 원래 표시 순서를 대신 씁니다. 기본 화면은 "진입점 -> 데이터 출처 -> ContextPack -> LLM -> 저장/알림" 흐름 구조를 보여 주며, 문제 해결에 필요한 자세한 내용은 이벤트 흐름, 노드 상세, 묶음 노드를 펼친 화면에 남겨 둡니다.

Web 실행 흐름 기본 화면은 프론트엔드 내부 표시 모델을 쓰며, 백엔드 `RunFlowSnapshot` 계약은 바꾸지 않습니다.

- provider 시도는 `metadata.data_type`에 따라 데이터 출처 노드로 묶습니다. 예: 실시간 시세, 일봉 데이터, 뉴스·여론.
- `context_block_*` 노드는 기본적으로 `ContextPack` 상세 안으로 접어 넣어, 데이터 출처 레인에서 provider 시도와 뒤섞이지 않게 합니다.
- 묶음 노드를 누르면 상세 영역에서 시도 표를 볼 수 있습니다. "시도 펼치기"를 누르면 해당 묶음의 하위 provider 노드가 구성도에 다시 나타납니다.
- 이벤트 흐름은 여전히 모든 이벤트를 보여 줍니다. 이벤트와 연결된 노드는 지금 보이는 노드에 대응됩니다. 접혀 있으면 묶음 노드를, 펼치면 해당 시도를 가리킵니다.
- 구성도의 연결선은 여러 연결점을 씁니다. 가로 방향 주 흐름은 왼쪽·오른쪽 포트를, 같은 레인의 위아래 관계는 아래쪽에서 위쪽으로 연결하며, fallback / retry는 계속 글자 라벨과 점선으로 표시합니다.

## 실행 흐름 API

```http
GET /api/v1/analysis/tasks/{task_id}/flow
GET /api/v1/history/{record_id}/flow
```

- 두 엔드포인트는 같은 `RunFlowSnapshot` 계약을 반환합니다.
- 진행 중인 작업에 diagnostics가 없으면 skeleton flow를 반환하며, provider / LLM 이벤트를 지어내지 않습니다.
- 진행 중인 작업에 최근 `flow_event`가 있으면 스냅샷은 이 실제 이벤트를 반환하고, 이벤트의 노드 메타데이터로 임시 노드를 보충할 수 있습니다.
- 완료된 과거 기록은 `context_snapshot.diagnostics`와 `analysis_context_pack_overview`에서 전체 구성도를 우선 만듭니다.
- 시장 리뷰 과거 기록은 `code=MARKET`, `report_type=market_review`를 쓰며, 똑같이 `/history/{record_id}/flow`와 Web 실행 흐름 패널을 거칩니다. 별도의 UI 분기는 없습니다.
- `cancel_requested`와 `cancelled`는 정상적인 실행 흐름 상태입니다. 사용자의 취소를 `failed`로 바꾸면 안 됩니다.

## 실행 흐름 화면

실행 흐름 화면은 실행 진단 요약 위에 얹은 시각적 문제 해결 진입점입니다. 분석 한 번이 실행부터 데이터 수집, ContextPack 조립, LLM 생성, 저장/알림까지 대략 어떻게 흘러가는지 이어서 보여 줍니다. 진단 요약의 `copy_text`를 대신하지는 않으며, 같은 민감 정보 제거 진단 근거를 노드, 연결선, 이벤트, 요약 지표로 정리해 Web 홈 화면에서 이상이나 성능 저하 지점을 빨리 찾게 해 줍니다.

백엔드는 읽기 전용 스냅샷 엔드포인트 두 개를 제공합니다.

```http
GET /api/v1/analysis/tasks/{task_id}/flow
GET /api/v1/history/{record_id}/flow
```

- `tasks/{task_id}/flow`는 진행 중인 작업용입니다. 작업이 아직 메모리 큐에 있으면 현재 작업 스냅샷을 먼저 반환하고, 작업이 끝났으면 같은 `task_id/query_id`로 과거 진단을 읽어 봅니다. 진단이 없으면 skeleton flow를 반환하며 provider, LLM, 알림 이벤트를 지어내지 않습니다.
- `history/{record_id}/flow`는 과거 보고서용이며, 과거 기록 기본 키 ID나 해석 가능한 `query_id`를 받습니다. 일반 개별 종목 분석과 `MARKET/market_review` 시장 리뷰는 같은 `RunFlowSnapshot` 계약을 씁니다.
- 같은 화면에서 개별 종목 분석을 실행하면, 개별 종목 흐름이 필요에 따라 그날의 시장 컨텍스트를 새로 만들거나 다시 쓸 수 있습니다. 이것은 개별 종목 분석의 독립 단계가 아니라 프롬프트 배경 정보 생성입니다. 백그라운드에서는 별도의 `market_context_*` query_id와 `scope=daily_market_context`로 이 시장 컨텍스트를 저장해, 개별 종목 보고서와 query_id가 겹치지 않게 합니다.
- 예전에 섞여서 기록된 진단과 호환하기 위해, 실행 흐름은 과거 기록을 읽을 때 보고서 종류에 따라 위험이 낮은 필터링을 합니다. `MARKET/market_review` 기록에서는 개별 종목 시세, 일봉, 기술 지표, 기본적 분석, 매물대 provider 노드를 숨깁니다. 개별 종목 기록에서는 첫 개별 종목 시세 이전의 시장 뉴스 검색과, 첫 개별 종목 LLM 이전의 시장 저장/알림 노드를 숨깁니다.
- 알림을 건너뛰었거나 설정하지 않았으면 `attempts=0`을 허용하며, 실행 흐름은 이를 skipped로 보여 줍니다. 더 이상 Pydantic 검증 실패로 `/flow`가 500을 반환하지 않습니다.
- 스냅샷 최상위에는 `summary`, `lanes`, `nodes`, `edges`, `events`, `generated_at`이 있습니다. 노드 상태는 `pending/running/success/failed/degraded/fallback/timeout/cancel_requested/cancelled/skipped/unknown`을 쓰며, 사용자 취소 계열 상태는 `failed`로 바뀌지 않습니다.
- 예전 기록이거나 `context_snapshot.diagnostics`가 없거나 근거가 부족하면 백엔드는 `unknown` 또는 skeleton 노드를 반환합니다. Web은 비어 있음/알 수 없음 상태로 보여 주며, 보고서 상세 읽기에는 영향이 없습니다.

Web 진입점:

- 홈 화면의 진행 중인 작업 카드에 실행 흐름 진입점이 있으며, 서랍을 열면 `task_id`로 작업 스냅샷을 가져옵니다.
- 과거 보고서 요약과 실행 진단 영역에 실행 흐름 진입점이 있으며, 서랍을 열면 과거 기록 ID로 과거 스냅샷을 가져옵니다.
- 패널은 요약, 기본 구성도, 이벤트 흐름, 노드 상세를 보여 줍니다. 복잡한 구성도 묶음, 실시간 증분 이벤트, 배치 다듬기는 이후 단계에서 계속 정리합니다.

민감 정보 제거와 호환 경계:

- 실행 흐름은 기존 작업 정보, 과거 결과, `context_snapshot.diagnostics`에 있는 민감도가 낮은 진단 필드만 읽습니다. 설정 항목을 추가하지 않고, 데이터베이스 구조를 바꾸지 않으며, 예전 기록을 이전하지 않습니다.
- `model`, `provider`, `fallback_model`은 실제로 진단된 호출 정보를 보여 주는 데만 쓰입니다. 모델 선택, 요청 라우팅, Base URL 해석, 설정 저장에는 관여하지 않습니다.
- `metadata`, 오류 메시지, 로컬 경로는 백엔드에서 잘라 내고 민감 정보를 가립니다. API key, token, cookie, webhook, prompt/raw response, 프록시 헤더, 로컬 절대 경로가 드러나지 않게 하기 위해서입니다.
- 되돌릴 때는 Web 진입점과 조회 경로를 없애면 됩니다. 백엔드에 추가된 읽기 전용 스냅샷 엔드포인트는 기존 분석, 과거 기록, 알림, 진단 요약 엔드포인트의 성공/실패 의미를 바꾸지 않습니다.

## 상태 문구

전체 상태:

- `normal`: 정상
- `degraded`: 일부 기능 저하
- `failed`: 실패
- `unknown`: 알 수 없음

구성 요소 상태:

- `ok`: 정상
- `degraded`: 최근 실패 후 대체 경로로 동작 중
- `failed`: 실패
- `unknown`: 알 수 없음
- `not_configured`: 설정되지 않음
- `skipped`: 건너뜀

## 화면 동작 경계

- 진단 영역은 기본으로 접혀 있어 보고서 본문을 가리지 않습니다.
- 첫 화면에는 전체 상태, 가장 중요한 원인, 꼭 필요한 trace 정보만 보여 줍니다.
- 구성 요소 상태와 고급 JSON 필드는 펼친 영역 안에 두고, 고급 필드는 한 번 더 접어 정보가 지나치게 많아지지 않게 합니다.
- 예전 보고서이거나 엔드포인트가 실패했거나 근거가 부족하면 `unknown`을 보여 주며, 보고서 읽기에는 영향이 없습니다.

## 호환성 경계

- 이번 범위에서는 `.env` 설정 항목을 추가하지 않고, 데이터베이스 구조를 바꾸지 않으며, 데이터 이전도 하지 않습니다.
- Web은 Phase 1/2에서 덧붙인 선택 필드와 읽기 전용 진단 엔드포인트만 씁니다. 백엔드는 `src/core/pipeline.py`, `src/services/run_diagnostics.py`, `src/storage.py`, `src/services/history_service.py`의 진단 저장과 갱신 로직을 보완했고, `api/v1/endpoints/history.py`로 읽기 엔드포인트를 제공합니다.
- 백엔드 변경 범위에는 작업 구성, 과거 기록 저장 후 추가 기록, 과거 진단 조회, 알림 결과 진단 기록이 포함됩니다. 이 흐름들은 `context_snapshot.diagnostics` 진단 스냅샷과 요약을 덧붙이기만 하며, 분석 주 흐름, 알림 전송 성공/실패 의미, 과거 보고서 본문 필드는 바꾸지 않습니다.
- 복사용 텍스트는 백엔드가 만들고 민감 정보를 가립니다. 프론트엔드는 보여 주고 복사하는 일만 합니다.
- Desktop은 Web 빌드 결과물을 그대로 쓰며, Electron 메인 프로세스나 패키징 스크립트를 따로 바꾸지 않았습니다.
- 실행 중 설정/모델/provider/base_url의 호환 의미는 바뀌지 않습니다. 진단 저장 흐름 외에는 provider 우선순위, LiteLLM 라우팅, 실행 중 정리, 설정 대체 로직을 바꾸지 않습니다.
- 예전 기록과 예전 설정의 호환 규칙도 그대로입니다. 과거 진단 조회에 추가된 선택 필드는 기존 과거 기록 조회 응답 해석에 영향을 주지 않습니다. 되돌리려면 이번 화면 표시와 관련 프론트엔드 조회 경로를 없애거나, 기존 가이드대로 모델과 설정을 복구하면 됩니다.
- 되돌리기 전략: 프론트엔드 표시와 조회 진입점을 먼저 되돌립니다. 추가된 흐름을 완전히 떼어 내야 한다면 이번 PR을 되돌립니다(되돌린 뒤에도 과거 기록의 원래 응답은 유지되며, 추가된 진단 엔드포인트는 Web에 더 이상 표시되지 않습니다).

### 구조화 검사 결과 정리

이번 리뷰의 구조화 검사에서 외부 모델/API 호환성과 실행 중 설정 이전 위험이 감지되었습니다. 다시 확인한 결론은 다음과 같습니다.

- 모델 이름/provider/Base URL: 이번 범위에서는 모델 이름, provider, Base URL, channel, fallback 기본값을 추가하거나 바꾸거나 순서를 바꾸지 않습니다. `LITELLM_MODEL`, `AGENT_LITELLM_MODEL`, `VISION_MODEL`, `LITELLM_FALLBACK_MODELS`, `OPENAI_*`, `GEMINI_*`, `ANTHROPIC_*`, `DEEPSEEK_*`의 해석 우선순위도 바꾸지 않습니다.
- SDK/의존성 기본값: 이번 범위에서는 `requirements.txt`, `package.json` 의존성 조건, LiteLLM/OpenAI 호환 호출의 기본 파라미터를 바꾸지 않습니다. 외부 출처는 여전히 `docs/llm-providers.md`와 `docs/LLM_CONFIG_GUIDE*.md`에 기록된 공식 문서와 현재 고정된 의존성 설명을 기준으로 합니다.
- 저장 전 정리/설정 이전: 이번 범위에서는 `.env`, Web 설정 화면의 channel, 데스크톱 앱의 사용자 데이터 폴더, Docker 실행 설정 파일, 예전 설정에 대한 이전·정리·삭제·되쓰기 정책을 바꾸지 않습니다.
- 실제 실행 중 변경은 기존 분석 trace, provider/LLM/알림 결과, 민감 정보를 가린 오류 요약을 `context_snapshot.diagnostics`에 기록하고, 과거 기록 읽기 전용 엔드포인트와 Web의 기본 접힘 패널로 보여 주는 것뿐입니다. 진단 기록이 실패해도 fail-open으로 처리하며 분석이나 알림의 성공/실패 판정은 바꾸지 않습니다.
- 따라서 이번 건은 구조화 검사의 오탐/문서 정리에 해당합니다. 새 공식 출처, 예전 설정 이전 절차, provider 대체 경로를 따로 진행할 필요는 없습니다. 되돌려야 한다면 이 절의 되돌리기 전략대로 진단 표시/조회 진입점을 없애면 되며, 모델과 실행 설정 복구 방법은 바뀌지 않습니다.

## 호환성 회귀 테스트와 검증(PR 병합 전 핵심 근거)

- 백엔드 회귀 테스트 범위:
  - `tests/test_pipeline_market_phase_context.py`
  - `tests/test_realtime_types.py`
  - `tests/test_scheduler_background.py`
  - `tests/test_analysis_api_contract.py`(일부: 진단 컨텍스트 입출력/상태 조회 계약)
  - `tests/test_analysis_history.py`(일부: 과거 기록 API와 저장 흐름)
- 범위 대응: API 계약은 `tests/test_analysis_api_contract.py`와 `tests/test_analysis_history.py`가 맡습니다. 작업 구성, 과거 기록 저장, `context_snapshot.diagnostics`는 `tests/test_pipeline_market_phase_context.py`가 맡습니다. 알림 경로는 `./scripts/ci_gate.sh`에 있는 기존 알림 회귀 테스트와 import 검사가 받쳐 줍니다.
- 회귀 테스트 명령(PR 병합 전 모두 통과하는지 최소한 확인):

```bash
./scripts/ci_gate.sh
python -m pytest tests/test_realtime_types.py tests/test_scheduler_background.py tests/test_pipeline_market_phase_context.py tests/test_analysis_api_contract.py tests/test_analysis_history.py
cd apps/dsa-web && npm run lint && npm run build
```

## 검증 권장 사항

```bash
cd apps/dsa-web
npm run lint
npm run build
```

추가로 실행할 수 있는 테스트(실패해도 막지 않음):

```bash
cd apps/dsa-web
npm test -- --run src/components/report/__tests__/ReportDiagnostics.test.tsx src/components/tasks/__tests__/TaskPanel.test.tsx src/hooks/__tests__/useTaskStream.test.tsx
```

추가로 할 수 있는 확정적 스크립트 검사:

```bash
python -m py_compile api/v1/endpoints/analysis.py api/v1/endpoints/history.py api/v1/schemas/analysis.py api/v1/schemas/history.py src/core/pipeline.py src/services/run_diagnostics.py src/storage.py
```

## 되돌리기

가장 간단한 방법은 Phase 3 PR을 revert하는 것입니다. 이번 범위는 선택 필드와 읽기 엔드포인트를 보강한 것이므로, 되돌린 뒤에도 백엔드 과거 스냅샷과 이미 저장된 데이터는 남아 있고, Web에서는 진단 패널과 trace 진단 진입점이 더 이상 보이지 않습니다.
