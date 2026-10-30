# ResearchArtifact: 구조화된 리서치 결과물

`ResearchArtifact`는 분석 보고서를 구조화한 버전입니다. 이후 대시보드, 개별 종목 리서치 페이지, 모니터링 센터, 관심 종목, Copilot이 같은 리서치 결론을 다시 쓸 수 있도록 하기 위한 것입니다.

## 목표

첫 버전은 세 가지 문제를 해결합니다.

- 보고서 결론을 Markdown에만 의존하지 않고 `thesis`로 정리해 남깁니다.
- 모든 구조화 보고서에는 `invalidation_conditions`가 반드시 들어가며, 언제 판단을 뒤집거나 다시 평가해야 하는지를 분명히 합니다.
- 근거 항목마다 `freshness`와 `quality_level`을 붙여, 화면에서 데이터가 얼마나 최신이고 믿을 만한지 보여 줄 수 있게 합니다.

## 필드

최상위 구조:

- `schema_version`: 항상 `research-artifact-v1`입니다.
- `artifact_id`: 고정된 결과물 id입니다. `report:<source_report_id>`를 우선 사용합니다. 아직 저장되지 않았다면 `report:<stock_code>:<query_id>`를 써서, 일괄 분석에서 여러 종목이 같은 query id를 공유해 충돌하는 일을 막습니다. query id가 없으면 `report:<stock_code>`로 대체합니다.
- `source_report_id`: 과거 보고서의 기본 키입니다.
- `source_query_id`: 분석 작업의 query id입니다.
- `created_at`: 보고서 생성 시각입니다.
- `subject`: 분석 대상 종목입니다.
- `thesis`: 구조화된 투자 의견입니다.
- `evidence`: 근거 목록입니다.
- `invalidation_conditions`: 무효화 조건이며 최소 한 개가 필요합니다.
- `next_actions`: 다음에 할 일입니다.
- `data_quality`: 입력 데이터 품질 요약입니다.
- `metadata`: 민감도가 낮은 확장 필드입니다.

## Thesis

`thesis`에는 다음이 들어갑니다.

- `direction`: `bullish`(상승) / `bearish`(하락) / `neutral`(중립) / `unknown`(알 수 없음).
- `summary`: 핵심 의견입니다.
- `confidence`: 심리 점수를 환산한 신뢰도입니다.
- `score`: 원래의 심리 점수입니다.
- `action` / `action_label`: 구조화된 권장 행동입니다.
- `reasons`: 뒷받침하는 이유입니다.
- `risks`: 주요 위험 요인입니다.

## Evidence

`evidence`에는 다음이 들어갑니다.

- `source_type`: 예를 들어 `analysis_context`, `news`, `fundamental`, `market_structure`.
- `freshness`: `fresh` / `stale` / `unknown`.
- `quality_level`: `good` / `usable` / `limited` / `poor` / `unknown`.
- `source`, `as_of`, `url`, `metadata` 등 민감도가 낮은 확장 필드.

시각과 최신성의 경계:

- `as_of`는 명시적인 `provider_timestamp`에서만 가져오며, 원본의 시간대를 그대로 유지합니다. 보고서 생성 시각이나 수집 시각으로 시세 관측 시각을 대신하지 않습니다.
- `metadata.context_timestamp`는 context block의 원래 시간 의미를 그대로 두고, `metadata.fetched_at`에는 수집 시각을 따로 기록합니다. 둘 다 데이터가 최신이라는 증거는 아닙니다.
- 원본이 `stale`이라고 명시하면 `stale`을 그대로 둡니다. `available`, `fallback`, `partial`, `estimated`, `ok`만 있는 경우 freshness는 `unknown`이고, 품질 상태는 기존 로직대로 계산합니다. 공통 TTL은 없으며, 주식 거래일 규칙을 24시간 내내 열리는 시장에 적용하지도 않습니다.
- 시각 필드가 없는 예전 보고서도 계속 호환됩니다. 현재 어댑터는 읽는 시점의 시계로 과거 근거를 다시 판단하지 않으며, 근거 전체의 스냅샷을 고정해 두지도 않습니다.

첫 버전의 어댑터는 `analysis_context_pack_overview.blocks`, 뉴스 요약, 재무제표, 배당, 시장 구조에서 근거를 추출합니다.

## Invalidation

모든 `ResearchArtifact`에는 `invalidation_conditions`가 최소 한 개 있어야 합니다.

첫 버전의 기본 출처:

- `strategy.stop_loss`에서 가격 무효화 조건을 만듭니다.
- `strategy.take_profit`에서 익절 재검토 조건을 만듭니다.
- 데이터 품질 제한에서 `data_quality` 무효화 조건을 만듭니다.
- 뉴스 누락 안내에서 `evidence` 무효화 조건을 만듭니다.
- 명시적인 조건이 없으면 마지막 안전장치로 `manual:thesis_reassessment` 재검토 조건을 만듭니다.

## 호환 범위

`AnalysisReport`에 선택 필드가 추가되었습니다.

```text
structured_report?: ResearchArtifact | null
```

예전 보고서는 이 필드를 계속 반환하지 않아도 됩니다. Web 타입과 백엔드 schema 모두 선택 필드로 처리합니다.

현재 Stock Profile API는 과거 보고서 상세 정보에서 이 결과물을 그때그때 만들어 냅니다. 보고서를 생성할 때 전체 `structured_report`를 고정해 저장하는 일은 이후 작업 범위입니다.

## 구현 위치

백엔드:

- Schema: `api/v1/schemas/research_artifact.py`
- Helper: `src/services/research_artifact_service.py`
- 테스트: `tests/test_research_artifact_service.py`

Web:

- 타입: `apps/dsa-web/src/types/researchArtifact.ts`
- `AnalysisReport.structuredReport`: 선택적으로 사용하는 진입점

## 이후 연결 계획

1. 보고서 생성 과정에서 저장할 때 `structured_report`를 함께 기록합니다.
2. 개별 종목 리서치 페이지가 `thesis`, `evidence`, `invalidation_conditions`를 바로 읽습니다.
3. 모니터링 센터가 무효화 조건을 편집 가능한 규칙으로 바꿉니다.
4. 대시보드의 What Changed에서 두 `ResearchArtifact`의 thesis와 evidence 차이를 비교할 수 있습니다.
