# DecisionSignal 의사결정 신호

이 페이지는 #1390 P7을 마무리하며, DSA가 개별 종목 분석, Agent, 경고, 포트폴리오 위험에서 나온 AI 의견을 조회·피드백·사후 평가할 수 있는 `DecisionSignal` 자산으로 쌓는 방식을 설명합니다. 이는 리포트 위에 얹는 구조화된 색인이며, Markdown 리포트, `operation_advice`, 3단계 `decision_type`, 경고 규칙, 실제 매매 시스템을 대신하지 않습니다.

## 기능 범위

- `DecisionSignal`은 의견, 근거 요약, 위험, 관찰 조건, 수명 주기, 출처만 기록하며 주문을 넣거나 포지션을 바꾸지 않습니다.
- 기록 실패, 추출 실패, 경고-신호 연결 실패, 알림 발송 실패는 모두 주 분석, 경고 발동, 리포트 저장을 막지 않습니다.
- #1756은 `decision_profile`을 정식 필드로 만들고 server-side filter, 중복 제거, 기한 연장, active 무효화 의미를 바로잡았습니다. #1757은 그 정식 필드 계약 위에 사용자가 확인한 뒤 저장하는 reassess persist를 추가했습니다. 둘 다 환경 변수, config registry 항목, `.env.example` 내용을 새로 추가하지 않습니다.
- 현재 `DECISION_SIGNAL_*` 스위치는 없습니다. 신호 기능을 끄거나 롤백하려면 해당 코드를 revert합니다.

## 필드와 열거형

핵심 필드는 `api/v1/schemas/decision_signals.py`에서 정의하며, 주로 다음과 같습니다.

- 식별과 출처: `stock_code`, `stock_name`, `market`, `source_type`, `source_agent`, `source_report_id`, `trace_id`, `decision_profile`, `trigger_source`.
- 의견의 의미: `action`, `action_label`, `confidence`, `score`, `horizon`, `market_phase`, `plan_quality`, `status`.
- 계획과 설명: `entry_low`, `entry_high`, `stop_loss`, `target_price`, `invalidation`, `watch_conditions`, `reason`, `risk_summary`, `catalyst_summary`.
- 근거와 품질: `evidence`, `data_quality_summary`, `metadata`.
- 수명 주기: `expires_at`, `created_at`, `updated_at`.

열거형 값:

| 필드 | 값 |
| --- | --- |
| `market` | `cn`, `hk`, `us`, `jp`, `kr`, `tw` |
| `source_type` | `analysis`, `agent`, `alert`, `market_review`, `manual` |
| `market_phase` | `premarket`, `intraday`, `lunch_break`, `closing_auction`, `postmarket`, `non_trading`, `unknown` |
| `action` | `buy`, `add`, `hold`, `reduce`, `sell`, `watch`, `avoid`, `alert` |
| `horizon` | `intraday`, `1d`, `3d`, `5d`, `10d`, `swing`, `long` |
| `decision_profile` | `conservative`, `balanced`, `aggressive`. 데이터베이스의 `NULL`은 legacy / unknown을 뜻함 |
| `plan_quality` | `complete`, `partial`, `minimal`, `unknown` |
| `status` | `active`, `expired`, `invalidated`, `closed`, `archived` |

웹 화면은 이 wire value를 현재 UI 언어의 읽기 쉬운 이름으로 바꿔 보여 줘야 하며, API 응답은 원래 열거형 값을 그대로 유지합니다.

## Canonical 점수와 action 기준

개별 종목 분석, 기술 점수 fallback, 리포트 표시 fallback, `DecisionSignal` 추출은 모두 `decision-scale-v1` 기준을 함께 씁니다. `decision_type`은 `buy|hold|sell` 호환 통계용으로만 남아 있으며, 더 세밀한 실행 의미는 8단계 `action`을 기준으로 합니다.

- 사용자에게 보이는 필드는 두 종류입니다. `operation_advice`는 텍스트 표현(예: "持有观察", 보유하며 관찰)을 유지하고, `action`은 통일된 8단계 판단 기준(예: `hold/watch/reduce`)으로 위험 관리, 백테스트, 목록 표시에 쓰입니다. 새로 만들거나 최종 저장 전에 다시 계산한 개별 종목 리포트는 두 값이 일치하도록 하는 것이 원칙입니다. 과거 기록이나 호환 payload에서 의미가 어긋나면, 목록, 백테스트, DecisionSignal 같은 구조화 표시에서는 `action`을 우선하고 `operation_advice`는 설명 텍스트로만 남깁니다.

| score | signal key | `action` | legacy `decision_type` | 의미 |
| --- | --- | --- | --- | --- |
| 80-100 | `strong_buy` | `buy` | `buy` | 강력 매수. 성공 확률이 높은 기회로, 매수/추가 매수 계획을 실행할 수 있음 |
| 60-79 | `buy` | `buy` | `buy` | 다소 적극적인 기회. 확인할 항목이 조금 남아 있어도 됨 |
| 40-59 | `watch` | `watch` | `hold` | 신호가 엇갈리거나 확인이 부족함. 발동 조건을 기다림 |
| 20-39 | `reduce` | `reduce` | `sell` | 위험이 뚜렷하게 커짐. 노출을 먼저 줄임 |
| 0-19 | `sell` | `sell` | `sell` | 추세나 위험이 크게 나빠짐. 우선 정리 |

`score >= 60`인데 최종 `action`이 `hold/watch`이거나, `score < 40`인데 최종 `action`이 여전히 `hold/watch`라면 분명한 guardrail 설명이 있어야 합니다. 예를 들면 `dashboard.decision_stability.reason`, `dashboard.decision_score_calibration.guardrail_reason`, `metadata.guardrail_reason`입니다. 위험 관리로 등급을 낮추면 `raw_score`, `adjusted_score`, `raw_action`, `final_action`과 그 이유를 남깁니다. 분명한 이유가 없는 중립 행동은 DecisionSignal을 추출할 때 canonical score에 맞춰 `buy/reduce/sell`로 정렬됩니다.

## 수명 주기, 중복 제거, 상태

`src/services/decision_signal_service.py`가 신호 수명 주기의 주 진입점입니다.

- `horizon`과 `expires_at`을 명시해 넘기면 그 값을 우선합니다.
- `horizon`을 넘기지 않으면, `alert`이거나 장 시작 전/장중/점심 휴장/단일가 매매 단계일 때는 기본값이 `intraday`이고, 장 마감 후, 비거래 시간, 알 수 없는 단계, 단계 정보가 없을 때는 기본값이 `3d`입니다.
- `intraday`의 만료 시각은 민감도가 낮은 `metadata.market_phase_summary.minutes_to_close/minutes_to_open`을 먼저 읽고, 없으면 시장별 fallback TTL을 씁니다.
- `expired`, `invalidated`, `closed`, `archived`는 `PATCH /status`로 바로 `active`로 되돌릴 수 없습니다.
- 같은 출처의 중복 제거에는 `(source_report_id, source_type, market, stock_code, decision_profile, action, horizon, market_phase)`를 우선 씁니다. report는 없지만 `trace_id`가 있으면 trace 기준을 씁니다.
- `decision_profile`은 신호 식별에 포함됩니다. `NULL`은 `NULL`과만 일치하고, 비어 있지 않은 profile은 같은 profile과만 일치합니다. Exact dedup, relaxed dedup, horizon/phase fill, expired refresh, active invalidation, stale backfill invalidation 모두 이 same-profile 의미를 따릅니다.
- 반대 방향의 새 active 신호는 같은 profile의 예전 active 신호만 `invalidated`로 표시하고, 무효화 출처를 metadata에 기록합니다. 서로 다른 비-`NULL` profile은 action이 반대여도 함께 존재할 수 있습니다.
- Expired duplicate refresh는 `decision_profile`을 바꾸지 않으며, 같은 profile의 기록만 갱신할 수 있습니다.

## API

현재 공개 API는 `api/v1/endpoints/decision_signals.py`와 `docs/architecture/api_spec.json`에 설명되어 있습니다.

- `POST /api/v1/decision-signals`: 만들거나 같은 출처 키로 중복 제거하며, `{ item, created }`를 돌려줍니다.
- `GET /api/v1/decision-signals`: 페이지 단위 조회. 시장, 종목, 행동, 단계, `decision_profile`, 출처, 상태, 기간, 보유 종목 필터를 지원합니다. `decision_profile`을 생략하거나 비워 보내면 profile 조건 없이 모든 profile을 돌려줍니다. `decision_profile=unknown`은 `NULL` 행을 조회하고, 올바른 profile은 정확히 일치하는 것만 찾습니다.
- `GET /api/v1/decision-signals/{signal_id}`: 하나를 조회합니다.
- `PATCH /api/v1/decision-signals/{signal_id}/status`: 상태와 선택적 metadata를 갱신합니다.
- `GET /api/v1/decision-signals/latest/{stock_code}`: 종목의 최신 active 신호를 조회합니다.
- `POST /api/v1/decision-signals/outcomes/run`: 사후 평가를 명시적으로 실행합니다.
- `GET /api/v1/decision-signals/outcomes`, `GET /api/v1/decision-signals/outcomes/stats`, `GET /api/v1/decision-signals/{signal_id}/outcomes`: 사후 결과와 통계를 조회합니다.
- `GET/PUT /api/v1/decision-signals/{signal_id}/feedback`: useful / not useful 피드백을 조회하거나 기록합니다.
- `POST /api/v1/decision-signals/reassess`: 출처가 된 과거 리포트 스냅샷을 바탕으로 판단 성향별 신호를 다시 계산합니다. `persist=false`는 미리 보기만 하고, `persist=true`는 서버가 다시 계산해 guardrail을 통과한 결과를 저장합니다.

이 API들은 기존 `/api/v1/*` 관리자 인증을 그대로 따릅니다. `ADMIN_AUTH_ENABLED=true`이면 유효한 관리자 세션 Cookie가 필요합니다.

## 판단 성향별 과거 성과

#1758은 기존 `GET /api/v1/decision-signals/outcomes/stats` 응답에 `profile_calibration`을 추가했으며, endpoint, 데이터베이스 테이블, 설정 항목, 시세 요청은 새로 추가하지 않았습니다. 기존의 전체 통계 필드와 8가지 단일 차원 breakdown은 원래 기준을 유지합니다. 표본 하나는 여전히 `(signal_id, horizon, engine_version)` outcome 기록 하나이며, 같은 신호라도 복기 기간이 다르면 따로 셉니다. 따라서 독립된 신호 개수로 이해하면 안 됩니다.

`profile_calibration.minimum_completed_sample_size`는 `30`으로 고정되어 있으며, breakdowns는 다음을 포함합니다.

- `decision_profile`
- `decision_profile_action`
- `decision_profile_horizon`
- `decision_profile_market_phase`
- `decision_profile_data_quality_level`
- `profile_source`

각 bucket의 `dimensions`는 구조화된 필드이며, 이어 붙인 문자열을 쓰지 않습니다. Profile 보정은 다음 출처를 기준으로 해석합니다.

- `decision_profile`은 연결된 신호의 현재 정식 필드를 읽습니다. `NULL`이나 잘못된 값은 `unknown`으로 묶으며, `balanced`로 대체하지 않습니다.
- `profile_source`는 연결된 신호의 현재 metadata를 읽으며, `auto_default`, `backfill_defaulted`, `legacy_unknown`, `user_selected`만 받고 나머지는 `unknown`으로 묶습니다. 이는 outcome 시점의 스냅샷이 아니라 현재 기준의 귀속이므로, metadata가 정상적으로 바뀌면 통계상 분류가 달라질 수 있습니다.
- `action`, `horizon`, `market_phase`, `data_quality_level`은 outcome에 고정된 필드를 읽습니다. 새 outcome을 만들 때 data quality는 `data_quality_summary`에 명시된 level을 우선 쓰고, summary가 없거나 올바른 JSON에 명시된 level이 없을 때만 정규화한 `metadata.data_quality_level`을 씁니다. 이미 있는 outcome은 이 읽기 규칙 때문에 조용히 다시 쓰이지 않습니다.

각 bucket은 따로 `completed >= 30` 기준을 적용하며, 상위 bucket, 전체 표본, 다른 형제 bucket이 이를 대신 채워 줄 수 없습니다. 표본이 부족하면 counts는 그대로 돌려주지만 `hit_rate_pct`, `avg_stock_return_pct`, `miss_rate_pct`, `unable_rate_pct`, `max_adverse_excursion_pct`는 모두 `null`입니다. 웹에는 표본 수와 "样本不足，仅供观察。"(표본이 부족해 참고용으로만 관찰) 안내만 표시합니다. 표본이 충분하면 다음과 같습니다.

- 적중률은 `hit / (hit + miss)`, 미적중률은 `miss / (hit + miss)`이며, neutral은 두 분모에 들어가지 않습니다.
- 평가 불가율은 `unable / total`입니다.
- 종목 평균 구간 등락률은 기존 completed outcome의 `stock_return_pct` 평균을 그대로 쓰며, 전략이나 포트폴리오 수익을 뜻하지 않습니다.
- 최대 불리 변동은 outcome에 저장된 가격만 씁니다. `buy/add/hold/watch/alert`는 `(start_price - min_low) / start_price`, `sell/reduce/avoid`는 `(max_high - start_price) / start_price`로 계산하며, 결과는 0보다 작지 않습니다. 가격이 없거나 유한하지 않거나 시작 가격이 양수가 아니면 그 행은 계산할 수 없습니다. Bucket은 계산 가능한 행 중 최댓값을 돌려주고, 계산 가능한 행이 없으면 `null`이며, 지표를 채우려고 시세를 읽지 않습니다.

웹은 기존 "신호 성과 통계" 카드 안에 "보수 / 균형 / 공격" 세 가지 선택지를 두고, 기본 선택은 항상 균형입니다. 세부 보기는 "제안 행동별"과 "복기 기간별" 두 가지만 있습니다. 성향 순위를 매기거나 추천하지 않으며, 요청, 라우트, 내비게이션, 설정 항목도 늘리지 않습니다. 예전 백엔드에 `profile_calibration`이 없으면 원래 통계 카드를 그대로 보여 줍니다.

## Reassess preview와 persist

`reassess`는 `source_report_id`에 해당하는 저장된 과거 리포트 스냅샷만 씁니다. `persist=false`는 사용자 확인 전 미리 보기용이고, `persist=true`는 같은 `source_report_id + decision_profile`로 서버에서 다시 계산하며, 앞선 preview나 클라이언트가 캐시한 판단 필드를 신뢰하지 않습니다.

요청은 다음 형태만 지원합니다.

```json
{
  "source_report_id": 123,
  "decision_profile": "aggressive",
  "persist": false
}
```

계약 범위:

- `source_report_id`가 유일한 사실 출처이며, 재평가는 해당하는 저장된 과거 리포트 스냅샷만 읽습니다.
- Request에는 `source_report_id`, `decision_profile`, `persist`만 허용합니다. `signal_id`는 지원하지 않으며, 클라이언트가 `action`, `score`, `confidence`, `horizon`, `invalidation`, `stop_loss`, `target_price`, `metadata`, `scoring_breakdown`, `guardrail_result` 같은 권위 필드를 보내는 것도 받지 않습니다. 추가 필드가 있으면 조용히 무시하지 않고 HTTP 422를 돌려줍니다.
- 재평가는 실시간 시세를 몰래 가져오지 않으며, 현재 시장 데이터로 과거 스냅샷을 채우지도 않습니다.
- 출처 리포트 내용 검증은 preview와 persist에서 같습니다. `source_report_id`가 없거나 잘못되면 HTTP 422, 리포트가 없으면 HTTP 404 `source_report_not_found`, 개별 종목 리포트가 아니면 HTTP 400 `unsupported_report_type`, 저장된 스냅샷으로 판단 신호를 만들 수 없으면 HTTP 400 `unsupported_report_snapshot`을 돌려줍니다. Persist는 출처 리포트에 유효한 `created_at`도 있어야 하며, 없으면 HTTP 400 `unsupported_report_snapshot`을 돌려주고 저장하지 않습니다. preview는 이 저장 수명 주기 필드에 의존하지 않습니다.
- data quality는 `high`, `medium`, `low`, `poor`, `unknown`으로 정규화되며, guardrail은 정규화된 등급만 씁니다.
- Preview가 성공하면 `preview`, `item=null`, `created=false`를 돌려줍니다. 저장하지 않으며 목록, latest, 타임라인에도 들어가지 않습니다.
- Persist가 성공하면 `preview=null`, 백엔드가 권위를 갖는 `item`, `persist_status`를 돌려줍니다. `persist_status=created`는 새로 만듦, `existing`은 같은 필드 기반 identity의 기록이 이미 있고 바꾸지 않았음, `refreshed`는 기존 expired refresh / dimension-fill 의미에 따라 기록을 재사용하고 갱신했음을 뜻합니다. 호환 필드 `created`는 `created`일 때만 `true`입니다. `persist_status`는 이번 저장의 처리 결과만 설명하며, `item.status`가 반드시 active라는 뜻은 아닙니다. 새로 만든 과거 신호도 만료되었거나 더 새로운 반대 신호에 밀려 `expired/invalidated`로 돌아올 수 있습니다.
- Reassess persist와 lazy backfill은 같은 과거 수명 주기를 씁니다. `created_at`은 출처 리포트 시각에 맞추고, `expires_at`은 리포트 시각, horizon, market, 저장된 `market_phase_summary`로 계산합니다. 단계 요약은 `phase/session_date/minutes_to_open/minutes_to_close`만 남기며, 저장한 날이나 실시간 시세로 유효 기간을 다시 정하지 않습니다.
- 같은 profile에서 반대 신호의 무효화 순서도 과거 신호의 바뀌지 않는 `created_at`으로 판단하며, expired refresh의 `updated_at`은 과거 우선순위를 바꾸지 않습니다. 예전 리포트를 저장한다고 더 새로운 반대 신호가 밀려나서는 안 됩니다. 유효 기간 안이지만 더 새로운 반대 신호에 밀린 과거 item은 `invalidated`로 돌아오며, API는 무효화 처리를 마친 최종 데이터베이스 상태를 돌려줍니다.
- `created` item에는 `source_type=analysis`, 원래 `source_report_id`, `source_agent=decision_profile_reassess`, `trigger_source=web:decision_profile_reassess`, 정식 `decision_profile`을 기록합니다. metadata에는 `profile_source=user_selected`, `profile_policy_version`, `signal_generation_version`, `scoring_version`, `scoring_breakdown`, `data_quality_level`, 전체 `guardrail_result`를 저장합니다.
- `existing` item은 처음의 source 필드와 metadata를 그대로 유지합니다. 예를 들어 일반 분석에서 같은 identity의 `balanced/auto_default` 신호가 이미 자동 생성되었다면, 사용자가 balanced reassess를 다시 확인해도 그 기록을 돌려줄 뿐 `user_selected`로 덮어쓰지 않으며 새로 만들었다고 하지도 않습니다. 종료 상태의 existing은 다시 활성화되지 않습니다.
- `refreshed` item은 바뀌지 않는 원래 생성 출처(`source_type`, `source_report_id`, `source_agent`, `trigger_source`, `created_at` 등)를 유지하며, #1756 repository의 기존 두 가지 세부 의미를 따릅니다. expired refresh는 바뀔 수 있는 판단 필드, 유효 기간, 이번 reassess 감사 metadata를 갱신하고, active relaxed dimension-fill은 빠진 horizon/market phase만 채우며 원래 metadata를 유지합니다. 클라이언트는 반드시 백엔드가 돌려준 item을 기준으로 해야 하며, `refreshed`만 보고 metadata가 바뀌었다고 추정하면 안 됩니다.
- `guardrail_result`는 기계 감사용 데이터로, `raw_action`, `final_action`, `passed`, `violations`, `adjustments`, `adjusted`를 기록합니다. `warnings`는 사용자가 읽는 요약입니다. 테스트와 클라이언트 로직은 warning의 고정 `code`에 의존해야 하며, `message`는 첫 버전 표시용입니다.
- `MIN_ACTIONABLE_CONFIDENCE = 0.5`. 모든 `buy/add`는 horizon, invalidation 또는 stop loss, 올바른 가격 관계를 갖춰야 하며 data quality가 `poor/unknown`이면 안 됩니다. aggressive의 `buy/add`는 추가로 명확한 invalidation이 있어야 하고 `long` horizon을 받지 않습니다.
- 신뢰도/invalidation이 없거나 데이터 품질이 부족하면 감사 가능한 방식으로 `watch`로 낮추고 `passed=true, adjusted=true`를 기록합니다. 가격 관계가 서로 모순되면 과거 스냅샷의 의미를 바꾸지 않고는 유효한 계획을 저장할 수 없으므로 `passed=false`를 기록합니다.
- Preview에서만 나온 `passed=false`는 여전히 HTTP 200으로 보여 주며, UI는 `blocked_reason`을 눈에 띄게 표시해야 합니다. Persist 재계산 결과가 `passed=false`이면 HTTP 400 `guardrail_blocked`를 돌려주고 `blocked_reason`과 구조화된 `warnings`를 포함하며, 저장하지 않고 `created=true`도 돌려주지 않습니다.
- persist 재계산은 매번 먼저 `guardrail_result.passed=true`를 만족해야 저장 단계로 들어갑니다. `created/refreshed`의 `item.action`은 이번 `guardrail_result.final_action`과 같습니다. `existing`은 원래 기록과 원래 metadata를 돌려주며, 이번 guardrail 감사를 지어내지 않습니다.
- 기본 분석과 lazy backfill은 여전히 `balanced`만 자동 생성합니다. 사용자는 balanced, conservative, aggressive를 명시적으로 골라 확인 후 저장할 수 있으며, conservative/aggressive는 자동 생성되지 않습니다.
- aggressive는 모델 샘플링 온도(temperature)를 뜻하지 않으며, 세 가지 profile 신호를 자동으로 만들지도 않습니다.

## 웹 표시

웹 진입점은 `/decision-signals`입니다.

- 기본 조회는 `status=active`입니다.
- 페이지 상단에는 고급 목록 필터와 별개로 페이지 단위의 "현재 종목" 기본 경로가 있습니다. 사용자가 주 종목을 제출하거나, 자동 완성 후보를 고르거나, 후보 chip을 누르면 latest active와 타임라인이 같은 적용된 종목 맥락을 씁니다. 입력 초안만 고쳐서는 latest나 타임라인 조회가 일어나지 않습니다.
- 현재 종목 후보는 최근 분석한 종목을 먼저 보여 줍니다. 과거 후보가 없거나 불러오지 못하면 종목 인덱스에서 active이면서 popularity가 높은 인기 종목으로 대신합니다. 후보는 직접 누르는 입구일 뿐이며, 페이지를 열 때 자동으로 조회를 제출하지 않습니다. 과거 기록과 종목 인덱스를 모두 쓸 수 없으면 후보 없음 안내만 보여 줍니다.
- 현재 종목 맥락에는 적용된 코드, 이름, 추정할 수 있는 시장이 표시되며 지우기 버튼이 있습니다. 지우면 latest와 타임라인이 안내 상태로 돌아가며, 고급 목록 필터나 목록 출처 상세 서랍에는 영향을 주지 않습니다.
- 시장, 종목 코드, 행동, 시장 단계, 출처, 출처 리포트 ID, 상태로 고급 목록 필터를 쓸 수 있습니다. 이 필터는 현재 종목 맥락과 다르며, latest active 조회에도 섞이지 않습니다.
- 종목별 신호 타임라인은 기존 `GET /api/v1/decision-signals` 목록 API를 재사용하며, 타임라인 endpoint를 새로 만들지 않습니다. 타임라인은 비어 있지 않은 현재 종목이 적용된 뒤에만 조회합니다. 현재 종목이 없으면 안내 상태만 보여 주며, 시장 전체나 전역 타임라인을 가져오지 않습니다.
- 타임라인 기간은 `30d`, `90d`, `180d` 세 가지만 지원하며 기본값은 `90d`이고, 한 번에 최대 100건을 요청합니다. `total > items.length`이면 웹은 "仅展示最近 100 条信号，请缩小时间范围"(최근 100건만 표시하니 기간을 줄여 주세요)를 표시해, 불완전한 기록을 조용히 보여 주지 않게 합니다.
- 타임라인 필터에는 별도의 market, range, status 입력과 조회 버튼이 있습니다. 새 현재 종목을 고를 때 시장을 추정할 수 있으면 그때 한 번만 타임라인 market을 초기화합니다. 그 뒤로 사용자가 market을 직접 바꿀 수 있으며, 조회는 버튼을 누른 시점의 입력 값을 기준으로 합니다.
- 타임라인 status filter는 `all`과 `active`만 지원합니다. `all`은 `status`를 보내지 않고, `active`는 `status=active`를 보냅니다. P1은 종료 상태 필터를 제공하지 않으며, 프런트엔드에서 종료 상태를 걸러 내지도 않습니다.
- 타임라인은 profile filter를 지원하며, 목록 API의 server-side `decision_profile` 조회를 재사용합니다. `unknown`은 legacy `NULL` 행을 거르고 표시할 때만 씁니다. 일반 고급 목록에는 profile filter를 추가하지 않습니다.
- 신호 성과 통계는 전체 복기 완료 outcome 기준을 유지하며, 지금 보이는 신호 개수와 다르고 현재 종목이나 고급 목록 필터에 따라 바뀌지도 않습니다. 복기 완료 표본이 0이면 웹은 `0/-` 지표 묶음 대신 표본 없음 상태를 보여 줍니다.
- 웹 표시는 정식 `decision_profile` 필드를 먼저 읽고, 필드가 없을 때만 legacy metadata로 대신합니다. profile이 없거나 잘못된 과거 신호는 `unknown`으로 표시하며, `balanced`로 잘못 표시하지 않습니다.
- market filter는 API / 서비스 계층과 웹 프런트엔드 모두 `cn/hk/us/jp/kr/tw`를 지원합니다. `jp/kr/tw`의 프런트엔드 현지화 이름도 모두 갖췄습니다. `tw` 신호는 API로 정상 기록되고 `market=tw`로 조회되며, 웹 DecisionSignal 페이지의 시장 필터에서 대만 주식(tw)을 고를 수 있습니다. 경고(시장 신호등) 시장은 `cn/hk/us/jp/kr`를 지원합니다.
- 상세 서랍에는 행동, 상태, 점수, 신뢰도, 기간, 계획 품질, 시장 단계, 가격 계획, 위험, 관찰 조건, 근거, 데이터 품질, metadata가 표시됩니다.
- 상세 서랍이나 출처 리포트 ID가 있는 페이지 맥락에서 reassess preview를 시작할 수 있으며, 쓸 수 있는 출처 리포트 ID가 없으면 버튼이 비활성화됩니다. Preview 자체는 목록, latest, 타임라인에 들어가지 않으며, guardrail을 통과하면 사용자가 한 번 더 확인해 저장할 수 있습니다. 저장은 `persist=true`로 다시 요청하며, 성공하면 응답의 백엔드 `item`만 씁니다. `created`, `existing`, `refreshed`는 서로 다른 안내를 보여 줍니다. existing은 새로 만든 것으로 표시하지 않으며, 종료 상태의 existing은 active latest/타임라인에 미리 끼워 넣지 않습니다. created/refreshed만 돌아온 상태에 따라 갱신하고 관련 화면을 새로 고칩니다. 웹은 preview로 로컬 신호를 조합해 만들지 않습니다.
- 저장할 때 나온 guardrail 조정 warning은 계속 표시합니다. persist 재계산이 guardrail에 막히면 웹은 `blocked_reason`과 구조화된 warning을 보여 주고, 사용자가 이해할 수 있게 preview를 남겨 두며, 실패한 결과를 타임라인에 넣지 않습니다.
- 홈 화면 분석 양식에는 `decision_profile`이 없습니다. 기본 자동 생성 경로는 여전히 `balanced`만 씁니다.
- 웹은 신호를 `closed`, `invalidated`, `archived`로만 표시할 수 있으며, 종료 상태를 active로 되돌리는 기능은 없습니다.
- 과거 리포트 상세에는 리포트에 묶인 `source_type=analysis` 신호를 더 이상 함께 보여 주지 않으며, 리포트 상세를 연다고 `source_report_id` 신호 조회가 일어나지도 않습니다. 리포트 출처 신호를 보려면 `/decision-signals` 페이지에서 출처 리포트 ID로 정확히 거르거나, `/decision-signals?sourceReportId=<recordId>` deep link를 엽니다. 이 필터와 deep link는 모두 `source_type=analysis + source_report_id` 정확 조회를 써서, 예전 리포트의 best-effort 지연 백필 경로를 유지합니다.
- 보유 종목 페이지는 고유한 보유 종목마다 latest active 신호를 비동기로 조회합니다. 한 종목 조회가 실패하면 기능 저하 안내만 보여 주며, 포트폴리오 스냅샷이나 다른 보유 종목 신호를 막지 않습니다.

사용자에게 보이는 모든 열거형은 i18n 이름을 써야 합니다. 기술 ID, 종목 코드, API 필드 이름, env key, URL 예시는 영어로 둬도 됩니다.

## Decision profile identity

#1756 이후 `decision_profile`은 `decision_signals`의 정식 nullable 필드이며, metadata에는 호환 필드도 남아 있습니다.

- `decision_profile=balanced`
- `profile_source=auto_default`: 일반적인 새 분석 생성 경로.
- `profile_source=backfill_defaulted`: 과거 리포트 lazy backfill 경로.
- `profile_policy_version=decision-profile-v1`
- `signal_generation_version=legacy-report-extractor-v1`
- `decision_signal_metadata_version=decision-signal-metadata-v1`

- 새로 기록할 때는 최상위의 올바른 `decision_profile`이 우선합니다. 최상위에 명시적인 `null`, 빈 값, 잘못된 값이 있으면 바로 거부합니다. 최상위 값이 없을 때만 올바른 `metadata.decision_profile`로 대신하며, 둘 다 없거나 metadata의 profile이 잘못되었으면 기본값 `balanced`를 씁니다.
- 새로 기록할 때 `metadata.decision_profile`을 정식 필드 값과 맞춰 두 출처가 충돌하지 않게 합니다. metadata를 생략하거나 명시적으로 `null`이면 metadata 없음으로 처리하고, object는 얕은 복사하며, object가 아니면 거부합니다.
- PATCH에서 metadata를 생략하면 원래 값을 유지하고, 명시적인 `null`이면 SQL `NULL`로 비우며, object이면 통째로 바꿉니다. 정식 profile이 `NULL`이 아니면 metadata 안의 충돌하는 값을 덮어씁니다. 정식 profile이 legacy `NULL`이면 요청 object에서 profile key를 지우며, 정식 필드로 올리지 않습니다.
- 자동 무효화 기록도 정식 필드가 권위를 갖는 규칙을 따릅니다. 정식 profile이 `NULL`이 아니면 metadata profile을 맞추고, legacy `NULL`이면 무효화 정보만 덧붙이며 원래 legacy metadata를 유지하고 profile을 넣거나 지우지 않습니다.
- Legacy / unknown은 데이터베이스 `NULL`로만 나타냅니다. 일반 자동 생성과 lazy backfill은 `scoring_version`이나 `scoring_breakdown`을 기록하지 않습니다. 사용자가 명시적으로 시작한 reassess 경로만 profile policy에 따라 이 필드를 만들고 감사합니다. 이는 세 가지 profile을 자동 생성한다는 뜻이 아니며, #1758의 profile-aware outcome calibration도 포함하지 않습니다.
- Lazy backfill 의미: profile을 생략하면 예전의 `source_type=analysis + source_report_id` 지연 백필을 유지합니다. `decision_profile=balanced`는 balanced 백필을 만들 수 있으며, `decision_profile=unknown`, `conservative`, `aggressive`는 행을 자동으로 만들지 않습니다. 백필과 reassess persist는 출처 리포트 시각, 과거 TTL, superseded 판단을 함께 쓰며, 과거 수명 주기가 두 벌로 따로 있지 않습니다.

## 시장 구조 metadata

일반 개별 종목 분석과 Agent 개별 종목 분석에 `market_structure_context`가 있으면, `DecisionSignal`을 자동 추출할 때 다음과 같은 민감도 낮은 필드를 metadata에 덧붙입니다.

- `market_structure_version`
- `market_theme_version`
- `stock_market_position_version`
- `market_structure_status`
- `primary_theme`
- `theme_phase`
- `stock_role`
- `market_structure_risk_tags`

이 필드는 신호가 놓인 테마 배경을 설명하는 데만 쓰이며, `action`, `score`, `horizon`, 같은 출처 중복 제거 키, 수명 주기 계산에는 쓰이지 않습니다. 테마 대장주라는 증명도 아닙니다. `market_structure_risk_tags`나 빠진 근거가 구성 종목이나 leader stocks가 불완전하다는 것을 보여 주면, 클라이언트와 사후 분석은 기능이 낮아진 테마 근거로 다뤄야 합니다.

스냅샷 필드의 `provider` / `dataset`은 시장 구조 추출 과정의 메타데이터에서 오며, 실행 후 저장되는 근거입니다. LLM provider/model 라우팅, `base URL` 해석, `.env` 되쓰기, 설정 마이그레이션에는 관여하지 않습니다. 확인 범위는 `src/schemas/market_structure.py`를 보세요.

## 경고, 알림, 포트폴리오 위험

- 종목 단위의 실제 경고가 발동하면 같은 종목의 latest active 신호를 먼저 연결하고, 민감도 낮은 `decision_signal_summary`를 `alert_triggers.diagnostics`에 기록합니다.
- active 신호가 없으면 경고 worker는 최소한의 `source_type=alert/action=alert` 신호만 만듭니다.
- 경고 신호의 `trace_id=alert-rule-<hash>`는 같은 출처 재시도의 best-effort 중복 제거에만 쓰이며, active 신호 본체를 덮어쓰지 않습니다.
- 알림은 공개 요약 필드인 `action`, `horizon`, `reason`, `watch_conditions`, `risk_summary`, `source_report_id`만 인용합니다.
- 알림의 `reason`은 민감 정보를 가린 뒤 전체를 보여 줘서, 고정 글자 수 때문에 문장 중간에서 잘리지 않게 합니다. `watch_conditions`와 `risk_summary`는 여전히 짧은 요약 길이 제한을 둡니다.
- 알림에는 signal `metadata`, `evidence`, raw diagnostics, webhook URL, token, cookie를 내보내면 안 됩니다.
- `GET /api/v1/portfolio/risk`의 `decision_signal_risk`는 현재 보유 종목의 active `sell/reduce/alert` 신호만 세며, 조회가 실패하면 fail-open합니다.

경고와 알림의 자세한 내용은 `docs/alerts.md`와 `docs/notifications.md`를 보세요.

## 사후 평가와 피드백

P5는 `decision_signals` 주 테이블을 늘리지 않고 sidecar 테이블에 사용자 피드백과 사후 결과를 저장합니다.

- `decision_signal_feedback`는 신호마다 최신 `useful|not_useful` 피드백, 선택적 이유/메모, 출처를 저장합니다.
- `decision_signal_outcomes`는 `(signal_id, horizon, engine_version)` 기준으로 멱등하게 사후 평가 결과를 저장합니다.
- 현재 `engine_version=decision-signal-v1`입니다.
- 사후 평가는 일봉으로 검증할 수 있는 `1d/3d/5d/10d`만 지원합니다. `intraday/swing/long`, 방향이 없는 행동, 가격 누락, 이후 봉 부족은 `eval_status=unable`과 명확한 `unable_reason`으로 기록합니다.
- 평가할 때 action, market, market_phase, source_type, source_agent, plan_quality, data_quality_level, holding_state 같은 통계 차원을 고정하므로, 과거 통계가 나중의 live join에 의존하지 않습니다.

## 종목별 복기 요약(ReviewMemory)

#1903은 P5 사후 데이터 위에 읽기 전용, 저민감 종목별 복기 요약을 추가했습니다. "계산은 했지만 한 번도 쓰이지 않던" outcome/feedback을 Agent 메모리로 모아, 결과에서 다시 판단으로 돌아가는 피드백 고리를 만듭니다.

- 읽기 전용 API `GET /api/v1/decision-signals/stocks/{stock_code}/review`(선택적으로 `horizon=1d/3d/5d/10d`로 거름)는 `DecisionSignalReviewMemory` 계약을 돌려줍니다: `stock_code`, `scope`, `sample_size`, `completed`, `hit_rate_pct`, `avg_return_pct`, `common_miss_reasons`, `confidence_adjustment`, `notes`. 집계는 `decision_signal_outcome_service.py` / `decision_signal_outcome_repo.py`에서 하며, agent 계층에 들어가지 않습니다.
- 저민감 범위: 계약에는 집계 값과 feedback `reason_code` 태그만 있으며, raw evidence, prompt 텍스트, 진단 정보, 보유 종목, feedback 메모 원문은 드러내지 않습니다.
- 보수적 판정: completed 표본이 10개 미만이거나, unable 비율이 50%를 넘거나, 주된 데이터 품질이 `low/poor`이면 `confidence_adjustment`는 `observe`로 고정되고 `notes`에 이유가 표시되며, 신뢰도는 전혀 움직이지 않습니다. 표본이 충분하면 적중률에 따라 `upgrade`(60% 이상)/`downgrade`(40% 이하)/`neutral` 방향을 제안하지만 여전히 관찰용입니다.
- Agent 활용: `AGENT_MEMORY_ENABLED=true`이면 `AgentMemory.get_decision_signal_review()`가 이 요약을 읽고, `BaseAgent`가 별도의 `[Memory: decision-signal review]` section으로 prompt에 넣습니다(AnalysisHistory 텍스트와 섞지 않음). 여기에 "관찰용일 뿐, 매매 강도의 근거로 쓰지 않음"이라는 안내를 붙입니다. flag를 끄면 전체 흐름은 이전과 완전히 같습니다.
- DecisionSignal의 비매매 원칙은 바뀌지 않습니다. 과거 적중률이 사실상 비중이나 매매 강도 신호가 되어서는 안 됩니다.

## 민감 정보 가림과 저민감 범위

신호 기록과 상태 갱신에는 `src/utils/sanitize.py`의 `sanitize_decision_signal_text()`와 `sanitize_decision_signal_payload()`를 씁니다.

- 텍스트 필드, JSON 필드, 표시용 짧은 텍스트는 기록하기 전에 민감 정보를 가립니다.
- 민감한 key, Bearer, Authorization/Cookie header나 그 대입문, token처럼 보이는 문자열, webhook URL, URL userinfo, 민감한 query/fragment 매개변수가 붙은 URL을 다룹니다.
- 일반 근거 URL은 출처를 추적할 수 있도록 남겨 둡니다.
- `trace_id`는 같은 출처 중복 제거용 식별 필드입니다. 가려질 credential이 들어 있으면 API는 가림 처리로 망가진 식별 값을 저장하지 않고 요청을 거부합니다.
- 웹의 JSON 표시는 백엔드가 이미 가린 데이터만 보여 주며, raw diagnostics나 설정 값을 다시 조합하면 안 됩니다.

P7의 전체 인수 기준은 신호 풀, 알림 요약, 웹 표시에서 token, cookie, webhook URL, API key, 메일 비밀번호 같은 민감 정보가 새지 않는지 확인하는 것입니다.

## 마이그레이션과 롤백

#1756은 SQLite에 데이터를 지우지 않는 migration을 실행합니다.

마이그레이션 안내:

- 업그레이드 후 `.env`, `.env.example`, 웹 설정 항목을 새로 추가할 필요가 없습니다.
- 기존 SQLite는 열이 없을 때만 `ALTER TABLE ADD COLUMN decision_profile`을 실행하며, `decision_signals`를 drop/rebuild하거나 예전 index를 지우지 않습니다.
- Migration은 profile-aware indexes를 멱등하게 만들고, `metadata_json`을 행마다 방어적으로 해석합니다. 올바른 `metadata.decision_profile`만 정식 필드로 백필하며, invalid JSON, object가 아닌 값, 잘못된 profile은 `NULL`로 둡니다. 시작 로그에는 backfilled, invalid JSON, non-object, invalid profile, skipped existing profile 통계가 남으며, 이는 진단용일 뿐 시작을 막지 않습니다.
- 예전 과거 리포트를 한꺼번에 백필하지 않습니다. 신호 목록 API를 명시적으로 호출하거나 웹 AI 의견 페이지에서 출처 리포트 ID로 `source_type=analysis + source_report_id` 정확 조회를 했는데 결과가 없을 때만 best-effort 지연 백필이 일어납니다.
- 기존 `decision_signals`, feedback, outcome 데이터는 호환을 유지합니다.

롤백 안내:

- 현재 `DECISION_SIGNAL_*` 스위치는 없습니다. 신호 추출/기록을 끄는 롤백 방법은 관련 코드를 revert하는 것입니다.
- 롤백한 뒤에도 일반 리포트 저장, 경고 발동, 알림 발송, 포트폴리오 위험의 주 흐름은 기존 경로대로 동작합니다.
- 롤백해도 과거 `decision_signals`, `decision_signal_feedback`, `decision_signal_outcomes` 데이터는 자동으로 지워지지 않습니다. 정리가 필요하면 관리자가 데이터 정리 방침을 따로 정해야 합니다.
