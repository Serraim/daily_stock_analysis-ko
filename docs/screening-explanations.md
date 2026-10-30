# 종목 선별 설명 계약

종목 선별 후보는 `why_selected`, `why_now`, `explanation_quality`를 함께 반환합니다. 설명은 백엔드가 후보 정규화와 DSA 데이터 보충을 마친 뒤 만들며, Web은 text, source, quality를 항목별로 보여 줍니다. 그룹 전체 품질은 요약일 뿐 각 항목의 출처를 대신하지 않습니다. Web은 더 이상 `change_pct`, `amount`, LLM 필드를 보고 스스로 추측하지 않습니다.

## 필드

각 explanation item에는 다음이 들어갑니다.

- `code`: 고정된 이유 코드. 예: `selection_reason`, `top_factors`, `news`, `quote_change_pct`, `awaiting_evidence`.
- `text`: 사용자에게 보이는 설명.
- `source`: `screening`, `realtime_quote`, 뉴스 출처, 이벤트 출처 또는 `llm`.
- `quality`: `observed`(관측됨), `inferred`(추론됨), `unknown`(알 수 없음).
- `value`: 선택 사항인 숫자 값. 실제 값 `0`은 그대로 유지해야 합니다.

`explanation_quality.why_selected/why_now`는 `ok`, `partial`, `unknown` 중 하나로 요약됩니다.

## Why Selected

확정적인 로컬 설명은 screening reason과, 현재 전략이 실제로 점수 계산에 쓴 팩터를 먼저 씁니다. 가중치가 0이거나 설정되지 않은 팩터는 기본 `selection_reason`에도 들어가지 않고 "핵심 팩터"로도 적히지 않으며, 두 곳 모두 "팩터 점수 × 전략 가중치"의 실제 기여도 순으로 보여 줍니다. `risk_summary` / `risk_level`은 항상 별도의 위험 표시에 남으며, reason이 없다고 해서 `selection_reason`으로 올라가지 않습니다. 업종 태그도 혼자서 선정 근거 행세를 하지 않습니다. reason과 검증 가능한 가중 팩터가 모두 없으면 "현재 종목 선별 후보 결과에 들어갔다"는 사실만 확인합니다. LLM 순위 조정, 포트폴리오 제약, 후처리로 바뀌었을 수 있는 최종 순위를 "확정적 선별 순위"로 잘못 적지 않습니다. `post_analysis_summaries`에서 온 DSA/외부 analyzer 요약은 `post_analyzer:<name>` 출처를 유지하고 inferred로 표시하며, 로컬 observed인 척하지 않습니다. 후보에 명시적인 `reason` / `ranking_reason`이 이미 있어도 사후 분석 요약은 `post_analysis_summary`로 함께 반환됩니다. 중복 제거 기준은 `(text, source, quality)`입니다. 출처와 품질이 같은 동일 문구는 한 번만 남기고, 출처나 품질이 다르면 문구가 같아도 각각 남깁니다. 명시적 reason이 사후 분석 요약의 다른 이름일 뿐이라면 screening/observed 출처를 새로 만들지 않습니다. 순수하게 로컬에서 확정적으로 계산한 `scorecard` 요약은 observed를 유지하지만, scorecard가 `llm_confidence`, `llm_catalysts`, `llm_risks` 중 하나라도 썼다면 설명 품질은 inferred입니다. LLM 순위의 `reason`과 `thesis`는 둘 다 정당한 독립 설명 진입점이며, thesis만 반환되어도 llm/inferred로 남깁니다. 두 내용이 다르면 둘 다 남기고, 같으면 위 기준으로 중복을 제거합니다. raw 래핑 객체를 정규화할 때는 응답 필드를 먼저 합친 뒤 scorecard가 바깥쪽 LLM 입력을 썼는지 판단합니다. LLM이 설정되지 않았거나, 시간 초과되었거나, 잘못된 구조를 반환해도 후보는 최소한 선정 결과 설명을 반환합니다. LLM은 로컬 설명의 전제 조건이 아닙니다.

사후 분석기가 요약을 생략하거나 `null` 또는 빈 요약을 반환한 경우, `post_analysis_status`가 `completed`이고 `post_analysis_score_deltas`가 유한한 0이 아닌 숫자이면 Why Selected는 `post_analysis_score_delta` 항목을 반환합니다. 이 항목은 분석기가 완료되었다는 것, 점수 조정 값, 요약이 제공되지 않았다는 것을 설명합니다. `value`에는 부호가 있는 점수 차이를 남기고, 출처는 여전히 `post_analyzer:<name>`이며, 품질은 해당 분석기 요약의 규칙을 그대로 따릅니다. 이 항목은 점수에 준 영향만 설명하며, 왜 점수를 조정했는지는 추측하지 않습니다. 요약이 있으면 요약 항목을 쓰고 점수 조정 설명을 중복해 붙이지 않습니다. 실패, 건너뜀, 점수 차이 0, 유효한 점수 차이가 없는 경우에는 이런 항목을 만들지 않습니다. 정규화, 서비스 응답, 과거 기록 저장은 상태, 점수 차이, 생성된 설명을 그대로 유지하며 원래 점수와 순위 재조정 동작을 바꾸지 않습니다.

## Why Now

시점 설명에는 출처가 있는 근거만 씁니다: DSA 뉴스, 이벤트, 그리고 `dsa_context.quote`에 분명히 있는 실시간 시세 필드입니다. 뉴스와 이벤트는 모두 해석 가능한 `published_date`가 있어야 하고, 게시 시각이 최근 30일 안이어야 합니다. 해석에는 SearchService가 이미 지원하는 ISO, RFC 2822, 중국어 날짜, Unix timestamp, 상대 날짜 형식을 다시 씁니다. 날짜가 없거나 기간이 지난 뉴스/이벤트는 observed로 표시하지 않으며, 다시 검색하지 않고 이미 보충된 후보 컨텍스트를 재사용하는 경로도 마찬가지입니다. 후보 최상위의 `change_pct=0`이나 `amount=0`만으로는 데이터가 실제로 있다는 증거가 되지 않습니다. 예전 데이터 소스가 0으로 값 없음을 표시했을 수 있기 때문입니다. quote 출처 정보가 없으면 `awaiting_evidence`를 반환하며 "현재 등락률 0%"로 적지 않습니다.

`dsa_context.quote.change_pct`가 분명히 있고 값이 `0`이면 정상적인 보합 데이터이므로 `value=0`과 `quality=observed`를 반환합니다. LLM catalyst는 `inferred` 보충 설명으로 쓸 수 있지만 관측된 사실인 척할 수는 없습니다.
quote에 `is_stale`/`price_stale` 표시가 있거나 품질이 partial/unavailable/stale/missing/fetch_failed이면, 그 안의 숫자는 Why Now observed에 들어가지 않습니다. 다른 최신 근거가 없으면 `awaiting_evidence`를 반환합니다.

## 현재 단계의 범위

이번 단계에서는 API explanation과 Web 표시만 완료했습니다. Issue #2282의 전략 metadata 확장, 결과 행 action, run history diff, export/backtest 등은 이후 범위입니다.

## 되돌리기

explanation 생성, Web 필드/카드, 관련 테스트를 없애면 되돌릴 수 있습니다. 기존 후보 필드와 screening 정렬 흐름은 호환을 유지합니다.

## 브라우저 확인

`cd apps/dsa-web && npx playwright test --config playwright.fixture.config.ts`는 고정된 API fixture로 실제 페이지를 그리며, 백엔드 서비스나 키가 필요 없습니다. CI의 `web-gate`는 Chromium을 설치해 확인을 실행하고, 스크린샷을 `web-ui-evidence-<head SHA>` artifact로 올립니다(30일 보관). 스크린샷은 저장소에 커밋하지 않습니다. 이 확인은 페이지 동작과 표시를 검증할 뿐, 실시간 provider/LLM이 쓸 수 있는 상태라는 뜻은 아닙니다.

## 예전 기록 호환

예전에 저장된 실행 기록을 열거나 자동 복원할 때, 후보에 `why_selected`는 없지만 `reason`, `llm_thesis`, 사후 분석 요약이 남아 있으면 Web은 설명 카드에 서로 다른 "과거 요약(출처 기록 없음)"을 모두 남깁니다. 출처는 `legacy_result`, 품질은 `unknown`입니다. 현재 전략 가중치로 예전 팩터를 다시 설명하지 않고, 예전 시세나 최상위 자리 채움 값 0을 현재 observed 근거로 다루지 않습니다. 이미 explanation 배열이 있으면 그것을 먼저 씁니다. 호환 표시는 데이터베이스에 다시 쓰지 않고 과거 기록도 바꾸지 않습니다.

## 확인 항목 표

- 받아들이는 ranker 응답: reason만, thesis만, reason+thesis, 같은 문구의 reason/thesis, risk만.
- 정규화: 일반 Pick, raw 래핑 필드, 여러 번 정규화한 뒤에도 출처 정보가 일관됨.
- 사후 분석: 명시적 reason과 각 analyzer가 함께 존재함. 실제 scorecard, DSA, external_http가 점수를 조정해 순위를 바꾼 뒤에도 순위 이유와 완료된 analyzer 요약이 각각 남음. external_http가 요약 없이 점수를 올리거나 내려 순위를 바꾸면 일반 출처 설명이 남고, 서비스 응답과 과거 기록이 일치함. 같은 문구라도 출처가 다르면 inferred가 사라지지 않음. 로컬 scorecard와 LLM 입력을 쓴 scorecard를 따로 분류함.
- 전송/저장: 동기 screen, 비동기 task, history의 프론트엔드 매핑이 항목을 유지함. screen 저장과 history_detail 읽기가 항목별로 일치함.
- 화면: 출처가 섞이면 항목마다 표시함. 전체 partial이 개별 observed/inferred를 덮지 않음. 예전 기록의 출처는 unknown. 실제 0과 값 없음을 구분함.

### 사전 보충 근거 새로고침

순위 결정 후 보충과 Why Now는 같은 사용 가능 판단을 씁니다. 뉴스와 이벤트는 출처와 비어 있지 않은 제목/요약이 있어야 하고, 게시 시각이 30일 범위 안이어야 합니다. 두 종류의 캐시가 모두 쓸 수 있을 때만 보충을 건너뜁니다. 기간이 지났거나, 날짜가 없거나, 출처/본문이 없는 종류는 따로 새로 가져오고, 다른 종류의 유효한 캐시와 기존 시세/기본적 분석 데이터는 계속 다시 씁니다. 새로 가져오기에 실패하면 성능 저하 경고를 남기며, 예전 뉴스를 observed로 올리지 않습니다. 후보 수 상한과 기존 검색 제한 시간은 그대로입니다.

제목과 요약은 각각 앞뒤 공백을 없앤 뒤 값을 씁니다. 제목이 없거나 공백뿐이면 유효한 요약을 씁니다. 캐시 판단과 Why Now 표시가 같은 본문 값을 쓰므로, 공백 제목이 요약을 가려 불필요한 새로 가져오기가 일어나는 일을 막습니다.

회귀 테스트는 실제 `screen()` 진입점, 검색 응답 정규화, `history_detail()` 읽기를 다룹니다. 최상위나 컨텍스트에 있는 기간 지난/날짜 없는 뉴스와 이벤트는 해당 종류만 새로 가져오게 하고, 새 근거는 observed로 응답과 과거 기록에 기록됩니다. 두 종류의 캐시가 모두 유효하면 보충을 건너뛰고 기존 경고를 유지합니다.

### 이유 없는 모델 순위

성공적으로 받아들인 LLM 순위 결과가 reason/thesis를 생략해도(risk만, code만 있는 정상 응답 포함), llm/inferred로 "모델이 순위 결정에 참여함(선정 이유 미제공)"을 표시하며 전체 Why Selected는 partial입니다. 실제 0점도 모델 입력으로 칩니다. 위험 문구는 위험 영역에만 남고, 실패해서 팩터만으로 대신 계산한 결과에는 모델 참여 항목을 붙이지 않습니다.

회귀 테스트는 후보 두 개의 실제 순위 재조정으로 점수 생략, 0점, risk만 있는 응답을 다룹니다. 순위가 바뀐 뒤에도 각 후보의 로컬 가중 팩터는 observed, 모델 참여 항목은 inferred를 유지하며, 여러 번 정규화해도 전체 품질은 partial입니다.

### 브라우저 테스트 진입점 분리

`npm run test:smoke`는 기본 `playwright.config.ts`를 쓰며 `e2e/fixtures/`를 명시적으로 제외합니다. `DSA_WEB_SMOKE_PASSWORD`가 설정되지 않으면 로그인이 필요한 smoke 테스트는 계속 건너뛰며 백엔드/Web 서비스를 띄우지 않습니다. 종목 선별의 API mock fixture 5개는 `npx playwright test --config playwright.fixture.config.ts`로만 실행되며, 이 설정은 Web 서비스를 따로 띄우고 비밀번호나 백엔드가 필요 없습니다. CI는 비밀번호 없는 기본 진입점과 전용 fixture 진입점을 모두 실행해, 전용 설정만 통과해서 기본 진입점의 회귀가 가려지는 일을 막습니다.
