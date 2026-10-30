# 데이터 센터

웹 데이터 센터는 `/data`에 있으며, 데이터 소스의 기능, 데이터셋 품질, 실행 시점의 우선순위를 읽기 전용으로 보여 줍니다. 이 페이지는 `GET /api/v1/data/overview`만 사용하며, 시스템 설정의 원본 값을 읽지 않고 screening, provider, 설정 점검 요청을 따로 조합하지도 않습니다.

## 페이지 내용

- Provider 기능: 카드에 실행 상태와 `dataset_markets`가 알려 주는 데이터셋/시장별 정확한 지원 관계를 보여 줍니다. 설정된 Provider 수는 페이지 상단에 합계로만 표시하고, 카드마다 enabled/configured 표시를 따로 두지 않습니다.
- 데이터셋 품질: `ok`, `degraded`, `partial`, `unconfigured`, `unavailable`, `unknown`, `stale` 상태와 함께 현재 출처, 마지막 성공 시각, 민감 정보를 가린 진단 정보를 보여 줍니다.
- 라우팅 우선순위: 실행 상황별 provider 순서와 그 설정의 출처를 보여 줍니다.
- Overview warnings: API가 주의가 필요하다고 판단했지만 다른 영역 표시를 막을 정도는 아닌 경고 코드입니다.

## 상태 표시 원칙

- 페이지는 "알려진 provider 이름"이라는 이유만으로 콜드 스타트 상태를 `ok`로 추정하지 않습니다. 백엔드가 `unknown`을 돌려주면 그대로 표시합니다.
- 페이지는 Provider의 `markets`와 `datasets`를 곱해 모든 조합을 지원한다고 계산하지 않습니다. 정확한 지원 범위는 `dataset_markets`를 기준으로 합니다.
- 여러 시장을 다루는 데이터셋이 시장마다 다른 provider를 쓰면 최상위 `source`가 비어 있는 것이 정상입니다. 이때 페이지는 `coverage.markets`를 읽어 시장별 실제 출처를 보여 주며, `--`로 표시하지 않습니다.
- Overview 요청이 실패하면 페이지 전체에 다시 시도할 수 있는 오류를 표시합니다. 요청은 성공했지만 provider와 dataset이 모두 비어 있으면 empty 상태를 표시합니다.
- 개별 provider나 dataset의 `partial`, `unknown`, `stale`, `unavailable` 상태는 해당 항목에만 영향을 주며, 나머지 항목은 계속 표시됩니다.

## 보안 원칙

이 페이지는 `/api/v1/system/config`를 호출하지 않으며 API Key, Token, Cookie, 원본 환경 변수를 보여 주지 않습니다. 설정을 바꿔야 할 때는 Settings로 이동만 하고, 민감 정보 가림과 권한 처리는 기존 설정 화면이 맡습니다.

## 검증과 롤백

프런트엔드 테스트는 `DataCapabilityOverviewResponse`와 같은 형태의 payload를 사용해 success, cold-start unknown, warning, empty, error, retry를 다룹니다. 페이지를 롤백할 때는 `/data` 라우트, 내비게이션, API/type, 페이지, 문서를 제거하면 되며, 백엔드 capability 계약에는 영향이 없습니다.

## 브라우저 인수 테스트

`cd apps/dsa-web && npx playwright test --config playwright.fixture.config.ts`는 고정된 API fixture로 실제 페이지를 렌더링하며, 백엔드 서비스나 키가 필요 없습니다. CI의 `web-gate`는 Chromium을 설치해 인수 테스트를 실행하고, 스크린샷을 `web-ui-evidence-<head SHA>` artifact로 업로드합니다(30일 보관). 스크린샷은 저장소에 커밋하지 않습니다. 이 테스트는 페이지의 동작과 표시를 확인할 뿐, 실제 provider/LLM이 지금 사용 가능한지를 뜻하지는 않습니다.

데스크톱 내비게이션은 창 높이가 낮을 때 링크 목록만 스크롤되고, 테마·언어·로그아웃 버튼은 보이는 영역에 남습니다. 테마 메뉴는 스크롤로 잘리는 영역에 들어가지 않습니다. 브라우저 인수 테스트에는 1280×720 화면에서 인증과 종목 선별이 모두 켜져 있을 때 설정/로그아웃에 접근할 수 있는지, 테마 메뉴, 로그아웃 취소가 포함됩니다.
