# 시장 지원 범위

## 일본/한국 개별 종목 suffix-only MVP(Issue #1718, Refs #1718)

현재 단계에서는 일본, 한국 주식의 Yahoo Finance 접미사 코드를 직접 입력해 기존의 개별 종목 분석, 이력 저장, 기본 리포트 표시 흐름에 넣을 수 있습니다. 웹 자동 완성에는 자주 쓰는 일본/한국 종목의 기본(seed) 인덱스가 들어 있어, 접미사 코드, 중국어·영어 이름, 흔히 쓰는 별칭으로 검색할 수 있습니다.

지원 형식:

- 일본: `7203.T`, `6758.T`
- 한국 KOSPI(코스피): `005930.KS`
- 한국 KOSDAQ(코스닥): `035720.KQ`

제약과 범위:

- 접미사 없이 코드만 입력하면 먼저 로컬/원격 종목 풀을 검색합니다. `005930`, `000660` 같은 코드가 `005930.KS`, `000660.KS` 같은 일본/한국 항목과 일치하면 일치한 시장으로 분석을 제출합니다. 종목 풀에서 찾지 못하면 기존 6자리 숫자 코드 규칙에 따라 A주(중국 본토 주식)로 처리하며, 이는 추적 가능한 시장 간 모호성으로 남겨 둡니다. 한국 주식은 `.KS`/`.KQ`까지 붙여 입력하는 것이 가장 확실합니다.
- 일본/한국 접미사 인식은 공용 시장 코드 도구로 모았습니다. 데이터 소스 라우팅, Prompt의 시장 인식, 거래일 달력, 종목 인덱스의 접미사 없는 코드 해석이 같은 규칙을 함께 써서, 이후 시장을 늘릴 때 규칙이 어긋나는 일을 줄입니다.
- 일본/한국 주식의 일봉과 기본 실시간/준실시간 시세는 `YfinanceFetcher`만 쓰며, AkShare, Tushare, Efinance, Pytdx, Baostock 같은 A주 전용 데이터 소스는 시도하지 않습니다. yfinance 시세에는 가능한 한 `market`, `currency`, `data_quality`, `missing_fields` 같은 품질 메타데이터가 붙습니다.
- 기본적 분석은 기존 해외(offshore) yfinance 경량 경로를 재사용합니다. A주 전용 자금 흐름, 룽후방(거래 상위 공시), 섹터 같은 기능은 `not_supported`로 기능을 낮추며, 해외 기본적 분석 맥락에도 provider, as_of, data_quality, 누락된 블록이 표시됩니다.
- 리포트 Prompt에 일본/한국 시장의 맥락을 추가해, A주의 상한가/하한가 제도, 북향 자금, 룽후방, 신용 거래 같은 개념을 그대로 적용하지 않게 했습니다.
- 거래일 달력에 `jp: XTKS / Asia/Tokyo`와 `kr: XKRX / Asia/Seoul`을 등록했습니다. 일본 주식은 정규 시간대 기준으로 장 시작 전, 장중, 점심 휴장, 15:25-15:30 종가 단일가 매매, 장 마감 후, 비거래일을 구분합니다. 한국 주식은 장 시작 전, 장중, 15:20-15:30 종가 단일가 매매, 장 마감 후, 비거래일을 구분합니다. 로컬 `exchange-calendars` 버전에 해당 달력이 없으면 기존 fail-open/fail-closed 동작은 그대로입니다.

호환성과 롤백 안내(구조화 검사에서 걸린 항목 관련):

- `#1815`는 이번에 `yfinance` 시세/기본적 분석 맥락에 선택 필드 메타데이터(`market`, `currency`, `data_quality`, `missing_fields`, `provider` 등)만 추가했습니다. LLM provider/model/base URL, 설정 Schema, 실행 시 환경 변수, 데이터베이스 필드, 기존 캐시 직렬화, 메시지 프로토콜 버전은 바꾸지 않았습니다.
- 이 PR과 관련된 설정 의미 측면에서 provider, model, base URL을 새로 추가하거나 바꾸지 않았고, 설정 정리/마이그레이션 분기도 추가하지 않았습니다. 저장된 설정은 그대로 유지되며, 되돌리려면 해당 커밋을 revert하면 됩니다.
- 외부 API 범위는 기존 `yfinance` 조회 경로(`Ticker`/`history`/`fast_info` 포함)와 기존 대체 로직으로 한정됩니다. API 게이트웨이/host를 새로 추가하거나 옮기지 않았으며, 영향을 받는 공개 매개변수는 `YFINANCE_PRIORITY` 하나뿐입니다. 일본/한국 주요 지수와 Yahoo symbol의 대응은 다음과 같습니다(직접 확인 가능).
  - 닛케이 225: `^N225`(<https://finance.yahoo.com/quote/%5EN225/>)
  - TOPIX(도쿄증권거래소 주가지수): `^TOPX`(<https://finance.yahoo.com/quote/%5ETOPX/>)
  - KOSPI: `^KS11`(<https://finance.yahoo.com/quote/%5EKS11/>)
  - KOSDAQ: `^KQ11`(<https://finance.yahoo.com/quote/%5EKQ11/>)
  - 의존성 버전: `requirements.txt`의 `yfinance>=0.2.0`. 회귀 테스트 경로는 `tests/test_yfinance_jp_kr_indices.py`와 `tests/test_yfinance_hk_indices.py`를 보세요.
- 호환성과 대체: `MARKET_REVIEW_REGION`은 올바른 쉼표 구분 부분 집합(예: `cn,us`)을 유지하고 `both`의 전체 동작도 그대로 둡니다. 잘못된 값이나 빈 값은 `cn`으로 돌아가며, 저장된 설정을 지우거나 옮기지 않습니다.
- 실행 범위: 일본/한국 지수는 market_review의 fail-open 규칙에 따라 하나씩 가져옵니다. 하나가 실패해도 다른 지수나 다른 시장을 막지 않습니다. 두 시장 모두 쓸 수 있는 주요 지수 시세가 없으면 로컬에서 보이는 `None/비어 있음`을 돌려주며, 주 흐름은 나머지 시장으로 계속 출력하거나 기능을 낮춰 진행합니다.
- 호환성 검증 근거: 시세/기본적 분석 맥락은 `data_provider/base.py`와 `realtime_types.py`에서 기존 `getattr`/선택 필드 규칙대로 하위로 전달되며, 새 필드를 반드시 읽거나 쓰도록 강제하지 않습니다. 설정 마이그레이션 스크립트는 없으며, provider/model/base URL fallback 경로가 바뀐 것은 확인되지 않았습니다.
- 롤백 방법: 새 메타데이터 필드가 어느 쪽에서 호환 문제를 일으키면, 먼저 그 필드를 무시하고 기존 시장 판정과 시세 표시 흐름대로 실행할 수 있습니다. 필요하면 이번 커밋을 롤백하거나 `jp/kr` `MarketSymbol`과 라우팅 확장을 제거해 예전 동작으로 돌아갑니다.

약속하지 않는 것:

- 실시간 시세는 약속하지 않습니다. Yahoo Finance 데이터는 지연되거나 필드가 빠질 수 있습니다.
- 완전한 기본적 분석, 업종/섹터, 시장 폭, 상승·하락 종목 수는 약속하지 않습니다. 일본/한국 시장 복기 v1은 주요 지수, 뉴스 단서, 템플릿/LLM 복기만 제공하며 일본/한국 시장 폭이나 섹터 순위는 제공하지 않습니다.
- 일본/한국 전체 상장 종목 목록은 약속하지 않습니다. 웹 자동 완성은 현재 저장소 안의 기본 인덱스에 든 자주 쓰는 종목(시장마다 상위 약 30종목으로 늘림)만 다루며, 찾지 못하면 접미사 코드를 직접 입력하면 됩니다.
- Portfolio의 JPY/KRW 환율, 원가, 시가총액 계산은 완전하게 맞추지 않습니다. 관련 필드는 프런트엔드·백엔드 검증에서 거부되지 않도록 시장 유형만 허용했습니다.

롤백 방법: `jp/kr` 시장 인식, 거래일 달력 등록, YFinance 라우팅 확장, 웹/API 타입 허용, `scripts/stock_index_seeds/`의 일본/한국 기본 인덱스를 제거하고, 이 문서의 기능 설명을 지웁니다.

## 일본/한국 시장 복기 v1(Issue #1815 Phase 2)

시장 복기 설정 `MARKET_REVIEW_REGION`에 `jp`와 `kr`를 추가하고, `both`의 다중 시장 순서 `cn,hk,us,jp,kr`에도 넣었습니다.

지원 범위:

- `jp`: Yahoo Finance에서 닛케이 225 `^N225`와 TOPIX `^TOPX`를 가져와 일본 시장 복기를 출력합니다. 확인할 수 있는 페이지:
  - `^N225`: <https://finance.yahoo.com/quote/%5EN225/>
  - `^TOPX`: <https://finance.yahoo.com/quote/%5ETOPX/>
- `kr`: Yahoo Finance에서 KOSPI `^KS11`과 KOSDAQ `^KQ11`을 가져와 한국 시장 복기를 출력합니다. 확인할 수 있는 페이지:
  - `^KS11`: <https://finance.yahoo.com/quote/%5EKS11/>
  - `^KQ11`: <https://finance.yahoo.com/quote/%5EKQ11/>
- 웹 설정 페이지에서는 `MARKET_REVIEW_REGION` 입력란에 쉼표로 구분한 부분 집합(예: `cn,jp`, `cn,us,jp,kr`)을 입력합니다. 거래일 확인은 `XTKS / Asia/Tokyo`와 `XKRX / Asia/Seoul`을 기준으로 `both` 가운데 그날 장이 열리는 시장만 남깁니다.
- 복기 전략, 뉴스 검색어, Prompt의 시장 맥락, 중국어·영어 알림 제목은 모두 일본/한국 전용 profile로 따로 처리합니다.

설명(호환성과 인수 기준):

- 실제 데이터 사용 가능 여부는 Yahoo Finance 지수 페이지와 API 계약에 달려 있습니다. 현재 구현은 `data_provider/yfinance_fetcher.py`의 지수 라우팅과 기능 저하 동작만 다루며, 실시간 시세 연결의 안정성은 약속하지 않습니다.
- 이 항목과 관련된 로컬 자동 검증은 기본적으로 오프라인 회귀 테스트를 씁니다. `tests/test_yfinance_jp_kr_indices.py`, `tests/test_yfinance_hk_indices.py`(공통 매핑/대체), `tests/test_trading_calendar.py`(거래일 필터)입니다. 실시간 사용 가능 여부를 추가로 확인하려면 네트워크가 되는 환경에서 위 Yahoo Finance 페이지에 직접 접속해 한 번 점검하면 됩니다.

- 외부 호환 범위(현재 구현의 기본 가정):
  - 데이터 소스: `yfinance`(최소 버전은 `requirements.txt`의 `yfinance>=0.2.0`)
  - 지속 조건: `^N225`, `^TOPX`, `^KS11`, `^KQ11`은 Yahoo Finance에서 조회 가능한 quote 페이지가 있어야 합니다. 조회할 수 없으면 해당 지수를 쓸 수 없는 것으로 보고, `market_review`의 fail-open 방식으로 기존 시장 출력으로 물러나며 주 흐름은 멈추지 않습니다.
- 호환성 검증(직접 확인 가능):
  - <https://finance.yahoo.com/quote/%5EN225/>
  - <https://finance.yahoo.com/quote/%5ETOPX/>
  - <https://finance.yahoo.com/quote/%5EKS11/>
  - <https://finance.yahoo.com/quote/%5EKQ11/>
  - 다시 실행해 볼 수 있는 온라인 확인 명령(선택):
```bash
python - <<'PY'
from yfinance import Ticker
for symbol in ("^N225", "^TOPX", "^KS11", "^KQ11"):
    data = Ticker(symbol).history(period="5d")
    print(symbol, "rows", len(data))
PY
```

범위:

- 일본/한국 시장 복기 v1은 상승·하락 종목 수, 상한가/하한가, 업종/섹터 순위, 자금 흐름 통계를 제공하지 않습니다. 구조화 payload의 `breadth`는 시장 폭 데이터가 있을 때만 나타납니다.
- 일본/한국 지수 하나를 가져오지 못하면 기존 yfinance fail-open 로직에 따라 건너뛰며, 다른 지수나 다른 시장에는 영향을 주지 않습니다.
- `exchange-calendars`에 해당 거래소 달력이 없으면 기존 거래일 fail-open/fail-closed 동작을 그대로 따릅니다.

롤백 방법: `MARKET_REVIEW_REGION`의 허용 값, 웹 설정 열거형, MarketProfile/MarketStrategy, `_MARKET_REVIEW_MARKETS`, 이 문서에서 `jp` / `kr`를 제거합니다.

## 대만 개별 종목 지원(suffix-only, Issue #1772 / #1777)

현재 단계에서는 대만 주식의 Yahoo Finance 접미사 코드를 직접 입력해 기존의 개별 종목 분석, 이력 저장, 리포트 렌더링, DecisionSignal, Portfolio, Intelligence 흐름에 넣을 수 있습니다. TWSE 상장 종목은 `.TW`, TPEx 장외(柜买) 종목은 `.TWO` 접미사를 쓰며, 둘 다 같은 `tw` 시장 태그로 묶습니다.

최근 대만 주식 흐름은 초기 MVP에서 정식 개별 종목 분석 시장으로 정리되었습니다. 시장 인식, 데이터 라우팅, 거래일 달력/장 단계, YFinance 일봉과 기본 시세, 주요 지수, 서비스 계층/API/웹 시장 열거형, TWD 통화 표시, 3대 법인(三大法人) 리포트 블록과 LLM prompt 활용이 모두 연결되었습니다. 남아 있는 한계는 대만 종목 풀 기본 인덱스/자동 완성, 시장 복기 `MARKET_REVIEW_REGION=tw`, Market Light 시장 신호등 경고, 대만 시장 폭/섹터 순위가 아직 들어가지 않았다는 점입니다.

지원 형식:

- 상장(TWSE): `2330.TW`, `0050.TW`
- 장외(TPEx / 柜买): `6488.TWO`, `5483.TWO`
- 코드 본체는 4-6자리 숫자입니다(보통주 4자리, ETF/기타는 6자리까지, 예: `00878.TW`, `006208.TW`). 일본 주식 `.T`의 4-5자리보다 범위가 넓습니다.

제약과 범위:

- **엄격한 suffix-only**: 접미사 없는 `2330`, `00878` 같은 코드는 대만 주식으로 처리하지 않습니다(`detect_market` / `get_market_for_stock`는 `.TW`/`.TWO` 접미사가 명시된 경우에만 `tw`를 돌려줍니다). 현재 대만 종목 인덱스/기본 인덱스 해석이 내장되어 있지 않으므로, 웹 자동 완성은 대만 종목 전체를 약속하지 않습니다. 찾지 못하면 전체 접미사 코드를 직접 입력하세요.
- 대만 주식의 일봉과 기본 실시간/준실시간 시세는 `YfinanceFetcher`만 쓰며, AkShare, Tushare, Efinance, Pytdx, Baostock 같은 A주 전용 데이터 소스는 시도하지 않습니다.
- 기본적 분석은 기존 해외 yfinance 경량 경로를 재사용합니다. `institution` 블록은 대만 3대 법인 자료를 추가로 받아 리포트에 렌더링하며, A주 전용 자금 흐름, 룽후방, 섹터 같은 기능은 `not_supported`로 기능을 낮춥니다.
- 리포트 Prompt에 대만 시장의 맥락(신대만달러, 3대 법인, TWSE/TPEx ±10% 상한가/하한가)을 추가하고, 3대 법인 순매수/순매도를 LLM 분석 맥락에 넣어 A주의 북향 자금, 룽후방 같은 개념을 그대로 적용하지 않게 했습니다.
- 거래일 달력에 `tw: XTAI / Asia/Taipei`를 등록했습니다. TWSE는 09:00–13:30 연속 거래이며 점심 휴장이 없습니다. 종가 단일가 매매 13:25–13:30은 5분짜리 추정 구간으로 모델링했습니다(`_CLOSING_AUCTION_WINDOW_MINUTES["tw"]=5`, `market_phase`가 `closing_auction`을 돌려줄 수 있음). 일본/한국도 정규 거래 시간대 기준으로 종가 단일가 매매 구간(일본 15:25-15:30, 한국 15:20-15:30)을 갖췄습니다. 로컬 `exchange-calendars` 버전에 해당 달력이 없으면 기존 fail-open/fail-closed 동작은 그대로입니다.
- 주요 지수로 가권지수 `^TWII`와 장외(柜买) 지수 `^TWOII`를 제공합니다.
- 3대 법인 순매수/순매도(institutional flows) 자료 계층: `TwInstitutionalFetcher`(`data_provider/tw_institutional_fetcher.py`)는 상장(TWSE T86, legacy `rwd` 엔드포인트) / 장외(TPEx OpenAPI)의 일별 외국인·투자신탁·자기매매·3대 법인 합계 순매수/순매도를 제공합니다(단위: **주식 수**. 날짜+시장별로 하루치 전체 시장을 캐시한 뒤 개별 종목을 걸러 내며, TPEx 민국 연도를 서기 연도로 바꾸는 부분은 단위 테스트로 확인합니다). API 실패/요청 제한/빈 응답/필드 누락은 모두 **fail-open**으로 데이터 없음을 돌려주며 분석을 멈추지 않습니다. `.TW`/`.TWO`에만 적용되며 기존 시장 흐름은 바꾸지 않습니다. 자료 출처는 정부 공개 데이터이며 「政府資料開放授權條款第 1 版」(정부 데이터 개방 허가 조항 제1판, OGDL v1, 상업적 이용과 재배포 허용, 출처 표시 필요)를 따릅니다.
- 3대 법인 fetcher는 동시 요청 때 캐시가 한꺼번에 뚫리지 않게 막는 장치와 TWSE/TPEx별 차단기(circuit breaker)를 갖추고 있습니다. TPEx OpenAPI는 최신 거래일 자료만 제공하므로, 제공되는 날짜와 다른 날짜를 명시하면 fail-open으로 데이터 없음을 돌려줍니다. 날짜가 틀린 자료가 조용히 리포트에 들어가지 않게 하기 위해서입니다.
- 대만 주식의 재무 금액에는 TWD -> 「新台币」(신대만달러) 표시를 써서, A주 맥락의 기본 단위 「元」(위안)으로 잘못 표시되지 않게 합니다.

약속하지 않는 것:

- 실시간 시세는 약속하지 않습니다. Yahoo Finance 데이터는 지연되거나 필드가 빠질 수 있습니다.
- 완전한 기본적 분석, 업종/섹터, 시장 폭, 상승·하락 종목 수, 대만 시장 복기는 약속하지 않습니다. `MARKET_REVIEW_REGION`은 여전히 `cn/hk/us/jp/kr/both` 또는 이 시장들의 쉼표 구분 부분 집합만 받습니다.
- 대만 종목 인덱스/기본 인덱스와 웹 자동 완성은 아직 완전히 연결되지 않았습니다. 경고의 MarketRegion과 백엔드 Market Light 경고는 여전히 `cn/hk/us`이며 `tw`는 없습니다.
- Portfolio의 TWD 환율, 원가, 시가총액 계산은 완전하게 맞추지 않습니다. 대만 주식 Portfolio는 현재 부분 평가(partial valuation) 시장입니다.

롤백 방법: `tw` 시장 인식, 거래일 달력 등록, YFinance 라우팅 확장, 3대 법인 자료 계층/리포트 활용, TWD 표시, 서비스 계층/API 시장 열거형, 프런트엔드 시장 타입 허용을 제거하고, 이 문서의 기능 설명을 지웁니다.

## 일본/한국 Portfolio와 Market Light 범위(Issue #1815 Phase 3)

Portfolio는 일본/한국 계좌, 거래, 보유 종목 스냅샷을 기존 흐름에 받아들이지만, 계좌/보유 종목 스냅샷에 `data_quality=partial`을 표시하고 `limitations`로 `realtime_quote_best_effort`, `fx_and_cost_basis_partial`, `sector_and_risk_metrics_limited`를 명시합니다. JPY/KRW 환율, 원가, 시가총액, 업종 집중도, 포트폴리오 위험 지표가 완전하다고 약속하지 않습니다.

- 일본/한국 계좌, 거래, 현금 내역, 기업 행위(corporate action) API는 계속 만들고 조회할 수 있습니다. 현재 JPY/KRW 환율 소스, 세금·수수료 모델, 거래 단위/최소 호가 단위 검증, 업종 매핑은 추가하지 않습니다.
- Market Light 스냅샷과 Market Light 경고는 여전히 `cn` / `hk` / `us`만 지원합니다.
- 웹 경고의 시장 드롭다운에는 `jp` / `kr`가 나오지 않으며, 백엔드 `normalize_market_region()`은 `jp` / `kr`에 대해 지원하지 않는다는 오류를 명시적으로 돌려줍니다.
- 웹 설정 페이지의 `MARKET_REVIEW_REGION`은 고정 열거형 드롭다운에서 자유 입력 텍스트 상자로 바뀌었으며, `cn,us,jp`, `cn,hk,us` 같은 쉼표 구분 부분 집합을 저장할 때 씁니다. 이 UI 변화는 시장 복기 설정에만 영향을 주며, Market Light 경고의 시장 열거형에는 영향이 없습니다.
- 기존 `MARKET_REVIEW_REGION` 값 `cn`, `hk`, `us`는 그대로 쓸 수 있습니다. 일본/한국이 추가되기 전의 `both`처럼 3개 시장만 복기하고 싶다면 `cn,hk,us`로 바꾸세요. 5개 시장을 모두 복기하고 싶을 때만 `both`를 계속 쓰거나 `cn,hk,us,jp,kr`를 명시합니다.
- 이번 범위 정리는 LLM Provider / Model / Base URL의 저장 의미를 바꾸지 않으며, 기본 모델 설정이나 실행 중 설정 정리·되쓰기도 하지 않습니다. 설정 업데이트는 여전히 **원자적 upsert**(`ConfigManager.apply_updates`)이며, 저장/가져오기는 제출한 키만 쓰고, 제출하지 않은 `LITELLM_MODEL`, `LITELLM_FALLBACK_MODELS`, `AGENT_LITELLM_MODEL`, `VISION_MODEL`, `OPENAI_BASE_URL` 등의 기존 값은 지우지 않고 남겨 둡니다.
- 바로 확인할 수 있는 설정 호환 근거: 이번에 외부 provider/model/Base URL을 새로 추가하거나 바꾸지 않았으며, 여전히 LiteLLM OpenAI-compatible 라우팅(<https://docs.litellm.ai/docs/providers/openai_compatible>), OpenAI Chat Completions 요청 형식(<https://platform.openai.com/docs/api-reference/chat/create>), 그리고 [LLM 서비스 제공자 설정 가이드](llm-providers.md#官方来源与兼容性)에 모아 둔 각 provider 공식 출처 링크를 따릅니다. 현재 실행 시 의존성 범위는 `requirements.txt`의 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`을 기준으로 합니다. 예전 설정에 대한 마이그레이션 스크립트나 정리 분기는 없으며, 저장/가져오기는 여전히 `ConfigManager.apply_updates`로 이번에 제출한 키만 씁니다. 되돌리려면 변경 전 `.env`/설정 백업의 `MARKET_REVIEW_REGION`을 복원하거나 이 PR을 바로 revert하면 됩니다. 제출하지 않은 `LITELLM_CONFIG`, `LLM_CHANNELS`, `LLM_OPENAI_*`, `LITELLM_MODEL`, `AGENT_LITELLM_MODEL`, `LITELLM_FALLBACK_MODELS`, `VISION_MODEL`, `OPENAI_*` 등의 기존 실행 설정은 옮길 필요가 없습니다. 회귀 근거는 `tests/test_system_config_service.py::SystemConfigServiceTestCase::test_update_market_review_region_does_not_trigger_runtime_model_cleanup`와 `tests/test_config_env_compat.py::test_market_review_region_updates_do_not_change_llm_provider_model_contract`입니다.
- 웹 UI 확인 기준: Market Light 경고의 대상 범위를 "시장 전체"로 바꾸면 시장 지역 드롭다운에는 A주, 홍콩 주식, 미국 주식만 나오고 일본/한국 주식은 나오지 않습니다. 설정 페이지의 `MARKET_REVIEW_REGION`은 쉼표 구분 값을 입력할 수 있는 텍스트 상자로 렌더링됩니다. 현재 저장소에는 일회성 스크린샷 증거를 보관하지 않으며, 대신 `apps/dsa-web/src/components/alerts/__tests__/AlertRuleForm.test.tsx`, `apps/dsa-web/src/components/settings/__tests__/SettingsField.test.tsx`, `apps/dsa-web/tests/system_config_i18n.test.ts`의 검증으로 확인합니다.

롤백 방법: Portfolio snapshot의 `data_quality` / `limitations` 확장을 제거하고, 경고 프런트엔드/백엔드의 시장 열거형 범위 설명을 예전대로 되돌립니다. 전체를 롤백하려면 `jp/kr` 시장 인식, 거래일 달력 등록, YFinance 라우팅 확장, 웹/API 타입 허용, `scripts/stock_index_seeds/`의 일본/한국 기본 인덱스를 제거하고, 이 문서의 기능 설명을 지웁니다.
