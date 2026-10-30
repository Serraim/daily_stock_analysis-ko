# 뉴스 / 정보 소스 MVP

Issue #1707의 첫 버전은 "허용된 뉴스 소스 수집, 로컬 저장, 조회 가능한 근거"에 집중합니다. RSS/Atom을 필요할 때마다 하는 검색 기능과 섞지 않으며, 별도의 여론 페이지도 기본으로 추가하지 않습니다.

## 지원 범위

- RSS / Atom HTTP(S) 뉴스 소스를 설정할 수 있습니다.
- NewsNow HTTP JSON 소스를 지원합니다. 기본으로 차이롄서(财联社, 중국 금융 뉴스) 인기 뉴스, 쉐추(雪球, 중국 투자자 커뮤니티) 인기 종목, 화얼제젠원(华尔街见闻) 속보, 진스(金十) 데이터, 거룽후이(格隆汇) 이벤트 등 주요 중국 금융 소스가 들어 있습니다.
- 내장 RSS/Atom/NewsNow 템플릿을 조회하고, 템플릿에서 테스트와 켜기/끄기가 가능한 뉴스 소스를 만들 수 있습니다. 내장 기본 소스 전체를 한 번에 만들 수도 있습니다.
- 뉴스 소스 설정, 사용 여부, 적용 범위(scope), 마지막 수집 상태를 저장합니다.
- 수집한 항목은 `intelligence_items`에 저장하며 제목, 요약, URL, 출처, 게시 시각, 수집 시각, 시장, 적용 범위를 함께 기록합니다.
- URL로 중복을 제거합니다. URL이 없는 항목은 `no-url:intel:<hash>`를 대체 키로 씁니다.
- `symbol` / `market` / `sector` 적용 범위와 `cn` / `hk` / `us` / `jp` / `kr` / `tw` / `global` 시장 표시를 지원합니다.
- 일괄 수집은 fail-open 방식입니다. 소스 하나가 실패해도 다른 소스나 메인 분석 흐름을 막지 않습니다.
- 보관 기간(retention) 정리를 지원해 뉴스 저장소가 끝없이 커지지 않도록 합니다.

## 보안 경계

사용자 지정 URL은 기본 검사를 거칩니다.

- 절대 경로의 `http` / `https` URL만 허용합니다.
- URL에 username/password를 넣을 수 없습니다.
- `localhost`, `.local`, 루프백 주소, 사설망 주소, 링크 로컬 주소, 예약 주소, 공유 주소 대역, 멀티캐스트 주소는 금지합니다.
- 주소 확인과 수집 단계에서는 환경 변수 프록시(`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` 등)를 명시적으로 끕니다. 프록시를 거쳐 검사를 우회하지 못하게 하기 위해서입니다.
- 실제 연결 단계에서 대상 호스트의 DNS 결과를 다시 검사합니다. 검사 뒤에 제한된 주소로 바뀌는 경우를 막기 위해서입니다.
- 리다이렉트된 최종 URL도 다시 검사합니다.
- 오류 메시지에서는 흔히 쓰이는 `token` / `key` / `secret` 쿼리 파라미터를 가립니다.

명시적으로 하지 않는 것: 크롤링 차단 우회, 로그인 흉내, 쿠키 수집, 허가받지 않은 포털의 직접 수집.

## 설정 항목

```env
NEWS_INTEL_RETENTION_DAYS=30
NEWS_INTEL_FETCH_TIMEOUT_SEC=8
NEWS_INTEL_MAX_ITEMS_PER_SOURCE=50
NEWS_INTEL_AUTO_FETCH_ENABLED=false
NEWSNOW_BASE_URL=https://newsnow.busiyi.world
```

`NEWSNOW_BASE_URL`은 `GET {NEWSNOW_BASE_URL}/api/s?id=<source_id>` 주소를 만드는 데 쓰입니다.

`NEWS_INTEL_AUTO_FETCH_ENABLED`는 기본적으로 꺼져 있습니다. `true`로 설정하면 개별 종목 분석, Agent 분석, 시장 리뷰가 로컬 뉴스 저장소를 읽기 전에 fail-open 자동 갱신을 한 번 실행합니다. 내장 뉴스 소스가 없으면 기본 소스를 만들어 켜고, 이미 있지만 꺼져 있는 내장 기본 소스는 다시 켠 다음, 켜져 있는 모든 소스를 수집해 `intelligence_items`에 기록합니다. 종목마다 외부 사이트에 반복 요청하지 않도록 실행 중인 프로세스 안에서 60분 대기 시간을 둡니다. 대기 시간 동안에는 로컬 DB 데이터를 다시 씁니다.

**외부 의존성 호환성 안내:**

- **공식 프로젝트와 배포 가이드**: https://github.com/qqhann/newsnow
- **현재 기본값** `https://newsnow.busiyi.world`는 공개 예시 인스턴스이며 **공식 배포가 아닙니다**. 다음 위험이 있습니다.
  - 관리, 요청 제한, 서비스 중단 때문에 사용할 수 없게 될 수 있습니다.
  - 안정성, 신뢰성, 데이터 정확성을 보장하지 않으며 시연과 테스트용입니다.
  - 모든 사용자가 같은 공개 인스턴스를 가리키므로 요청 제한에 걸릴 수 있습니다.
- **실제 운영 환경에서는** NewsNow 인스턴스를 직접 띄우거나, 관리 가능한 것이 확인된 사설/기업 배포를 연결할 것을 강하게 권장합니다. 그래야 안정성과 데이터 신뢰성을 확보할 수 있습니다.

**API 계약 호환성 확인(배포 전 필수):**

- 기본 접속 가능 여부와 응답 형식을 확인합니다.
  ```bash
  curl -sS "${NEWSNOW_BASE_URL}/api/s?id=cls-hot" | python -c "import sys, json; data=json.load(sys.stdin); assert isinstance(data, dict) and isinstance(data.get('items'), list); print('OK')"
  ```
  (Windows PowerShell에서는 `${NEWSNOW_BASE_URL}` 대신 실제 주소를 직접 넣어 실행하세요.)
- 필드 호환성의 자세한 내용은 자동화 테스트 `test_newsnow_source_fetches_json_items`를 참고하세요. `status`, `id`, `items[].title`, `items[].url`/`mobileUrl`, `items[].pubDate`/`items[].extra.date` 등의 필드를 다룹니다.
- **배포 인스턴스는 자동화된 출시 보장 범위에 들어가지 않습니다.** 공개 예시 인스턴스에 의존한다면, 배포 전에 실제 운영 환경에서 위 확인을 꼭 실행하세요.

## API

모든 엔드포인트는 `/api/v1/intelligence` 아래에 있습니다.

- `POST /sources`: 뉴스 소스를 만듭니다.
- `GET /sources`: 뉴스 소스를 조회합니다.
- `GET /sources/templates?market=hk`: 내장 뉴스 소스 템플릿을 조회합니다.
- `POST /sources/templates/{template_id}`: 내장 템플릿으로 뉴스 소스를 만듭니다. 이름, 사용 여부, 적용 범위, 설명을 덮어쓸 수 있습니다.
- `POST /sources/defaults`: 내장 기본 소스 전체를 한 번에 만듭니다. 여러 번 호출해도 결과가 같으며(멱등), 같은 이름의 소스가 이미 있으면 `created=false`를 반환하고 중복으로 넣지 않습니다. `enabled`를 넘기지 않으면 `false`로 만들어집니다. 기본으로 켜고 싶다면 `{ "enabled": true }`를 넘기세요.
- `POST /sources/test`: payload를 테스트하며 DB에 저장하지 않습니다.
- `POST /sources/{source_id}/fetch?dry_run=false`: 소스 하나를 수집합니다.
- `POST /sources/fetch-enabled`: 켜져 있는 모든 소스를 fail-open 방식으로 수집합니다.
- `GET /items?scope_type=market&market=cn&days=7`: 뉴스 항목을 조회합니다.

로컬 `.env`, Docker, 또는 환경 변수를 명시적으로 넘겨주는 다른 실행 환경에서 "소스 생성 -> 수집 -> 저장 -> 분석에 활용"을 자동으로 처리하려면 다음을 설정하세요.

```env
NEWS_INTEL_AUTO_FETCH_ENABLED=true
```

이 스위치를 켠다는 것은 실행 중에 설정된 외부 RSS/Atom/NewsNow HTTP 소스에 접속하는 것에 사용자가 명시적으로 동의한다는 뜻입니다. 기본값이 꺼짐인 이유는 확인되지 않은 외부 요청, 공개 NewsNow 예시 인스턴스의 부담, 분석 프롬프트 입력 변화를 피하기 위해서입니다.

> 참고: 이 스위치는 실제로 실행되는 프로세스의 환경 변수에서 보일 때만 적용됩니다. 저장소에 기본으로 들어 있는 `00-daily-analysis.yml`은 `env`를 허용 목록(allowlist) 방식으로 연결합니다. 목록에 명시하지 않은 변수는 저장소의 Variables/Secrets에 같은 이름으로 설정해도 실행 환경에 들어가지 않으므로, 기본 workflow에서는 이 스위치가 자동으로 적용되지 않습니다. 저장소에 포함된 일일 분석 작업에서 이 기능을 켜려면 workflow에 이 변수를 넘기는 줄을 직접 추가하거나, 로컬/Docker에서 환경 변수를 직접 설정해 실행하세요.

## NewsNow 기본 소스

NewsNow는 RSS가 아니라 인기 뉴스를 모아 주는 플랫폼입니다. DSA는 HTTP API로 JSON 응답을 직접 읽으며 MCP가 필요 없습니다.

```text
GET {NEWSNOW_BASE_URL}/api/s?id=cls-hot
```

이 PR에서는 "소스 설정 -> 수집 -> 저장 -> 분석에서 읽기" 흐름이 끝까지 동작하도록 다음 금융 관련 기본 소스를 먼저 연결했습니다.

- `cls-hot`: 차이롄서 인기 뉴스. 주로 A주(중국 본토 증시)와 테마 이슈입니다.
- `xueqiu-hotstock`: 쉐추 인기 종목. 주로 개별 종목에 대한 관심도입니다.
- `wallstreetcn-quick`: 화얼제젠원 속보. 주로 거시경제, 원자재, 시장 이벤트입니다.
- `jin10`: 진스 데이터. 주로 세계 거시경제와 해외 시장 이벤트입니다.
- `gelonghui`: 거룽후이 이벤트. 주로 홍콩 주식과 해외 상장 중국 기업 관련 맥락입니다.

중국 내 다른 플랫폼이 더 필요하면 `POST /sources`로 NewsNow 소스를 직접 추가할 수 있습니다. `source_type=newsnow`로 두고 `url`에 `https://<your-newsnow>/api/s?id=<source_id>`를 넣으세요. RSS를 선호한다면 RSSHub 같은 허용된 RSS 소스를 `source_type=rss`로 연결해도 됩니다.

## 이후 연결 방향

첫 버전을 바탕으로 분석 흐름은 로컬 뉴스 저장소를 가능한 범위에서(best-effort) 읽습니다.

- 개별 종목의 기존 방식 분석은 `symbol=<종목 코드>` 뉴스를 먼저 읽고, 같은 시장의 `market` 단위 뉴스로 보충합니다. 내용은 기존 `news_context`에 덧붙여지며 AnalysisContextPack 요약 및 과거 기록의 `news_content`와 함께 저장됩니다.
- Agent 분석도 `news_context`로 로컬 뉴스 근거를 넣어 줍니다. Agent가 이미 저장된 뉴스를 보려고 다시 검색할 필요가 없도록 하기 위해서입니다.
- 시장 리뷰는 같은 시장의 `market` 단위 뉴스를 시장 뉴스 목록에 합칩니다. 프롬프트, 구조화 payload, 보고서 news 필드 모두에서 출처 링크를 볼 수 있습니다.
- `NEWS_INTEL_AUTO_FETCH_ENABLED=true`이면 위 진입점들이 먼저 로컬 뉴스 저장소를 fail-open 방식으로 자동 갱신합니다. 갱신에 실패해도 분석은 멈추지 않습니다.
- 이번 기능은 로컬 뉴스를 활용하는 경로만 추가합니다. 모델 이름, provider/base URL, 기본 모델 정책, 대체(fallback) 정책, `save_context_snapshot` 전 정리 로직, 실행 중 설정의 의미는 바꾸지 않습니다. 기존 배포 설정과 호환되며, 되돌리려면 로컬 뉴스 연결 진입점을 걷어 내거나 로컬 뉴스 소스 설정/데이터를 삭제하면 됩니다.

이후 PR에서 NewsNow HTTP provider, 보고서 evidence 표시, Web 설정/보고서 보기 화면을 더 다듬을 수 있습니다.

## 호환성과 되돌리기(Issue #1707)

- 이 기능은 외부 LLM provider의 동작 방식을 바꾸지 않으며, provider/model/base URL/기본 모델 정책/실행 중 라우팅이나 설정 이전 분기를 새로 만들지 않습니다.
- 구조화 검사가 경고한 모델/API 호환성 위험은 이번 변경에 해당하지 않습니다. `news_context` 주입 경로는 기존 LLM 분석 입력 구성 과정(`src/core/pipeline.py`, `src/market_analyzer.py`, `src/analyzer.py`)만 다시 쓰며, `.env` 쓰기, 저장 전 정리, 비우기/되채우기 로직을 새로 추가하지 않습니다.
- 되돌리는 방법: 이 PR을 `revert`합니다. 설정만 낮추고 싶다면 로컬 뉴스 소스 설정(`sources` 테이블과 기존 `intelligence_items` 데이터 포함)을 끄고 지우기만 하면 됩니다. 기존 모델, provider, 다른 과거 분석 흐름에는 영향이 없습니다.

## PR 설명에 다시 쓸 수 있는 내용(Issue #1707)

- Refs: `#1707`
- 호환성 결론: 이번 변경은 로컬 뉴스 활용 경로만 추가합니다. 모델 이름/provider/base URL/기본 모델 정책/대체 정책/저장 전 정리 로직/실행 중 설정 이전은 바꾸지 않습니다. `news_context`와 `market_review_payload` 확장은 가능한 범위에서 덧붙이는 방식이라 기존 계약과 호환 범위에 영향을 주지 않습니다.
- 되돌리기 계획: 가장 작은 되돌리기 방법은 `revert this PR`입니다. 연결만 낮추려면 실행 중에 로컬 뉴스 소스(`sources`, `intelligence_items`)를 끄고 정리하면 됩니다.
