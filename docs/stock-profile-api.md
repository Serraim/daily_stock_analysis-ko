# 개별 종목 리서치 통합 API

이 문서는 Issue #2279의 백엔드 계약 단계를 설명합니다. 목표는 이후 만들 `/stocks/:code` 작업 화면이 하나의 엔드포인트로 데이터를 받게 하는 것입니다. 브라우저가 시세, 과거 데이터, 리포트, 뉴스, 보유 종목, 모니터링 API를 동시에 호출해 직접 조립하지 않도록 합니다.

## 엔드포인트

`GET /api/v1/stocks/{stock_code}/profile?history_days=60`

엔드포인트는 먼저 입력값을 canonical code(표준 코드)로 통일합니다. 실시간 시세, 과거 데이터, 리포트 조회에는 canonical code를 사용합니다. 예전 진입점이 별칭으로 저장했을 수 있는 intelligence(뉴스·정보)와 monitor(모니터링) 기록은 읽을 때 저장소에 이미 있는 동등 코드 집합으로 펼친 뒤 ID 기준으로 중복을 제거합니다.

- A주(중국 본토 증시 상장 주식): `SH600519`, `600519.SH` 등은 `600519`로 통일됩니다. 입력에 `SH` / `SZ` / `BJ`(상하이·선전·베이징 거래소)가 명시돼 있으면 이후 리포트, 뉴스, 모니터링의 별칭 확장에서도 이 시장 정보를 계속 유지합니다. 종목 인덱스에 같은 형태의 일본·한국 코드가 있어도 숫자만 보고 다른 시장으로 다시 추정하지 않습니다. 명시한 거래소와 코드 규칙이 충돌하면(예: `600519.SZ`) 400을 반환하며, 거래소를 떼어 내고 다른 종목을 조회하지 않습니다.
- 일본 주식: `7203.T`는 Yahoo canonical suffix(접미사)를 유지하고 `market=jp`를 반환합니다.
- 한국 주식: `005930.KS`, `035720.KQ`는 Yahoo canonical suffix를 유지하고 `market=kr`를 반환합니다. 종목 인덱스가 유일하게 식별한 예전 숫자 코드도 해석된 한국 시장 정보를 그대로 사용합니다. 캐시된 보유 종목 중 예전 6자리 숫자 코드의 한국 주식은 market이 `kr`로 명확할 때 해석된 정보와 프로필 suffix의 숫자 부분을 비교하며, market 정보가 없는 A주 규칙으로 다시 해석하지 않습니다.
- 대만 주식: profile 엔드포인트는 4~6자리 `.TW` / `.TWO` Yahoo suffix(6자리 ETF 포함)를 받으며 `market=tw`를 반환합니다. 시장을 지정한 뉴스 조회는 예전 숫자 코드 scope와도 호환되지만, `global` 조회에서는 이 모호한 별칭을 계속 제외합니다. 캐시된 보유 종목에 `market=tw`가 명시돼 있으면 예전 숫자 코드를 같은 시장의 숫자 부분 기준으로 프로필과 대조합니다.
- 홍콩 주식: `00700`, `00700.HK`, `HK00700`은 `HK00700`으로 통일됩니다. 캐시된 보유 종목에 `market=hk`가 명시돼 있으면 `700` 같은 예전 짧은 형식도 앞자리에 0을 채운 뒤 비교에 참여합니다.
- 미국 주식 ticker는 접미사 없는 대문자 형식으로 통일합니다. 예를 들어 `aapl`, `AAPL.US`는 모두 `AAPL`이 됩니다. 저장된 데이터를 읽을 때는 여전히 순수 ticker와 `.US` 등 동등 별칭을 함께 조회합니다.

응답에는 `quote`, `history`, `research`, `intelligence`, `portfolio`, `monitors` 여섯 개의 독립 블록과 최상위 `evidence_quality` 요약이 들어 있습니다. 각 블록의 `status`는 다음 값만 허용합니다.

| 상태 | 의미 |
| --- | --- |
| `fresh` | 이번 요청에서 사용할 수 있는 데이터를 받았습니다. 모든 외부 출처의 시간대나 갱신 주기가 같다는 뜻은 아닙니다 |
| `partial` | 핵심 정보는 쓸 수 있지만 분명한 제한이 있습니다. 예를 들어 리포트 목록만 있고 상세가 없거나, 보유 종목 관계가 캐시에서만 왔을 때입니다 |
| `unavailable` | 이번에는 사용할 수 있는 데이터가 없습니다. 원인은 안정적인 `limitations` code로 반환하며, 원본 예외나 키는 노출하지 않습니다 |

선택 블록 하나가 실패해도 다른 블록은 사라지지 않습니다. 예를 들어 quote가 실패해도 과거 리포트, 구조화된 ResearchArtifact, symbol intelligence, 모니터링 규칙은 반환될 수 있습니다. 최신 리포트 상세 조회가 실패하면 `research.recent_reports`는 그대로 남고, `structured_report`는 `null`이 되며 `latest_report_detail_unavailable`로 표시됩니다.

## 데이터 출처와 범위

- quote/history: `StockService`를 재사용하며 새 데이터 수집기를 추가하지 않습니다.
- research: `HistoryService`와 #2291의 `ResearchArtifact` builder를 재사용합니다. 리포트 조회는 프로필 진입점에서 이미 해석한 market hint를 `HistoryService`의 후보 생성 단계로 넘깁니다. 힌트 없이 해석해도 현재 시장에 속한다고 확인되는 숫자 별칭만 남깁니다. 예를 들어 `600519`는 A주 예전 기록과 계속 호환되고, `005930`은 한국 주식으로 유일하게 등록된 예전 리포트와 호환됩니다. 반면 한국 주식과 같은 형태이면서 A주임을 명시한 `SZ000660`은 숫자만 있는 `000660`을 조회하지 않습니다. 일본·한국·대만 조회는 거래소 접미사와, 같은 시장으로 이미 확인된 다른 예전 숫자 코드는 유지하지만, 다른 시장의 과거 기록과 맞을 수 있는 별칭은 펼치지 않습니다. 시장을 한정한 뒤 후보가 비면 바로 빈 페이지를 반환하며, 필터 없는 조회로 후퇴하지 않습니다. artifact는 과거 상세의 컨텍스트, raw result, 별도 펀더멘털 스냅샷 fallback도 함께 재사용해 재무제표, 배당, 시장 구조 관련 근거와 그 source count를 유지합니다.
- service import 경계: `api.v1`의 router는 지연 export 방식으로 바꿨습니다. 따라서 `StockProfileService -> ResearchArtifact schema` 경로가 거꾸로 모든 API endpoint를 불러오지 않습니다. CLI, 독립 스크립트, 단위 테스트는 `api.app`을 먼저 import하지 않아도 profile service를 직접 import할 수 있습니다.
- intelligence: `IntelligenceService`의 symbol scope 조회를 재사용합니다. canonical 코드, 거래소 접두사·접미사, 홍콩 주식 접두사·접미사, 대소문자 혼용, 일본·한국·대만 시장으로 한정한 예전 숫자 별칭과 호환됩니다. 힌트 없이 현재 시장으로 되돌려 해석할 수 없는 모호한 숫자 코드는 `global` 조회에 넣지 않습니다. 조회 별칭은 casefold identity 기준으로 중복을 제거하고, repository의 symbol 전용 대소문자 무시 필터로 과거 대소문자 차이를 처리해 count/select가 중복되지 않게 합니다. 별칭 또는 시장 조회 중 하나라도 실패하면 블록은 partial limitation을 유지합니다. 나머지 조회가 성공했지만 결과가 비어 있어도 "뉴스가 없음이 확인됨"으로 잘못 보고하지 않습니다.
- portfolio: `PortfolioRepository.list_cached_position_identities()`만 읽고, 캐시된 각 보유 종목의 market 정보로 예전 숫자 코드를 해석합니다. market과 프로필 정보가 일치할 때만 보유 중으로 봅니다. 개별 종목 페이지를 연다는 이유로 실시간 평가나 snapshot 쓰기를 일으키지 않으므로, 상태는 항상 `partial`이며 `cached_positions_only`를 포함합니다.
- monitors: `AlertService.list_rules()`를 재사용합니다. 대소문자를 무시한 symbol 필터로 페이지별 결과를 모으고, canonical code와 동등한 과거 별칭에 걸린 `single_symbol` 규칙의 중복을 제거합니다. 현재 경보 대상에는 별도 market 필드가 없으므로, 일본·한국·대만 프로필은 A주·홍콩 주식과 같은 형태일 수 있는 숫자 별칭을 조회하지 않습니다. 다른 시장의 규칙이 잘못 연결되는 것을 막기 위해서입니다.

이 단계에서는 Web 라우트나 페이지를 추가하지 않고, Home/Watchlist/Screening/Portfolio/Report 진입점도 연결하지 않으며, 캘린더 이벤트도 포함하지 않습니다. 이후 Web PR은 반드시 이 엔드포인트를 사용하고 블록별 상태를 각각 표시해야 합니다. 여러 요청을 모아 페이지를 조립하는 방식으로 되돌아가면 안 됩니다. 캘린더 이벤트는 #2307 계약이 병합된 뒤 별도 블록으로 확장합니다.

## 롤백

이 PR을 revert하면 profile schema, service, endpoint, 테스트, 문서가 모두 제거됩니다. 데이터베이스 마이그레이션, 설정 변경, 데이터 정리 단계는 없습니다.
