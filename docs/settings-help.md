# 설정 페이지 도움말 관리 안내

설정 페이지 도움말은 설정 항목의 핵심 설명을 WebUI 안에 넣어, 사용자가 설정 페이지와 문서 사이를 계속 오가지 않아도 되게 합니다. 페이지에는 짧은 설명만 남기고, 자세한 설명은 설정 항목 제목 옆의 help 아이콘을 눌러 엽니다.

이 문서는 도움말 시스템의 관리 규칙만 설명하며, 전체 설정 문서를 대신하지 않습니다. 설정의 의미, 기본값, 실행 시점 우선순위, 문제 해결 세부 사항은 여전히 `.env.example`, `docs/full-guide.md`, 관련 주제별 문서를 기준으로 합니다.

## 데이터 구조

백엔드 설정 레지스트리는 `src/core/config_registry.py`에서 필드에 도움말 메타데이터를 붙입니다.

- `help_key`: 프런트엔드 다국어 도움말 문구의 고정 key입니다.
- `examples`: 그대로 보여 줄 수 있는 설정 예시입니다. 민감한 필드는 `sk-xxxx`, `your_token` 같은 자리 표시자만 써야 합니다.
- `docs`: 관련 문서 링크입니다. 저장소에 이미 있는 주제별 문서나 전체 가이드를 우선 가리킵니다.
- `warning_codes`: 프런트엔드나 이후 검증 확장에서 쓸 고정 안내 code입니다.

긴 프런트엔드 문구는 `apps/dsa-web/src/locales/settingsHelp.ts`에서 관리합니다.

- 기본으로 중국어 문구를 보여 줍니다.
- 영어 문구도 같은 구조를 유지해 나중에 언어 전환을 넓히기 쉽게 합니다.
- 문구는 용도, 값 설명, 영향 범위, 주의 사항, 관련 문서를 설명해야 하며, 주제별 문서 전체를 복사하면 안 됩니다.

## WebUI 언어 안내(설정 항목 아님)

이 프로젝트에는 별도의 WebUI 화면 언어 기능(`zh` / `en`)이 있으며, 정적 페이지 문구, 내비게이션, 공통 컨트롤 문구에 쓰입니다. 이 상태는 `REPORT_LANGUAGE`와 분리되어 있으며 리포트 언어의 의미를 바꾸지 않습니다.

- 상태 키: `dsa.uiLanguage`(`localStorage`, 브라우저에 저장).
- 초기화 우선순위: `localStorage`의 유효한 값이 먼저이고, 다음으로 브라우저 언어(`zh-*` / `en-*`)를 인식하며, 마지막으로 `zh`로 돌아갑니다.
- 이 언어 스위치는 `.env` 설정 필드가 아니며, `system/config`의 설정 가능 필드 목록에도 나타나지 않습니다.
- 화면 언어를 바꾸면 접근성을 위해 `document.documentElement.lang`(`zh-CN` 또는 `en`)도 함께 바뀝니다.

## 적용 범위

PR1은 기반 구조와 첫 번째 대표 설정 항목을 다룹니다.

- `STOCK_LIST`
- `LITELLM_MODEL`
- `LLM_CHANNELS`
- `FEISHU_WEBHOOK_URL`
- `WEBUI_HOST`

PR2는 자주 쓰고 잘못 입력하기 쉬운 설정 항목을 이어서 다룹니다.

- AI 모델 실행: Agent 기본 모델, fallback 모델, 고급 YAML 라우팅, temperature, provider API Key, OpenAI-compatible Base URL.
- LLM Channels 편집기 내부 필드: 채널 이름, 프로토콜, Base URL, API Key, 모델 목록, 실행 시점 기능 감지, 기본 모델, Agent 기본 모델, fallback, Vision, temperature.
- 데이터 소스와 검색: Tushare, 종목 인덱스 원격 업데이트 스위치, 실시간 시세 우선순위, 실시간 기술 지표, 검색 API Key, SearXNG, 매물대(보유 원가 분포), 뉴스 기간.
- 알림: Webhook, Telegram, 메일, Discord/Slack 같은 채팅 플랫폼, 리포트 출력, Webhook SSL 검증.
- WebUI / auth / schedule / proxy: Host, Port, 로그인 보호, 신뢰할 수 있는 리버스 프록시, 예약 실행, 거래일 확인, 네트워크 프록시.

PR3 registered-field slice / 단계별 보완: 웹 설정 페이지에 실제로 표시되고 설정할 수 있는 필드의 Help를 채우는 데 집중합니다. 일반 설정 카드에 지금 보이는 필드와, 조건에 따라 보이는 AI legacy 필드가 포함됩니다.

- Agent 설정(22개 필드): 종목 질문(问股) 생성 방식, Agent 모드, 최대 추론 단계, 전략 목록, 전략 디렉터리, 자연어 라우팅, 아키텍처, 오케스트레이터 모드, 타임아웃, 위험 거부권, Deep Research 예산/타임아웃, 메모리, 전략 자동 가중치, 전략 라우팅, 종목 질문 화면의 대화 맥락 압축, 이벤트 모니터링 스위치/간격, 경고 규칙 JSON. 일반 사용자에게는 새 `AGENT_BACKEND` 선택기만 보이며, 예전 `AGENT_GENERATION_BACKEND`는 설정 호환용으로만 남아 있습니다.
- 백테스트 설정(5개 필드): 백테스트 스위치, 평가 기간, 최소 기록 경과 기간, 엔진 버전, 중립 수익 구간.
- 리포트 설정(9개 필드): 요약만 발송, 모델 이름 표시, 템플릿 디렉터리, 렌더링 엔진, 완전성 검사/재시도, 과거 신호 비교, 종목별 발송, 메일 합치기.
- 알림 라우팅 설정(9개 필드): 리포트/경고/시스템 오류 채널 라우팅, 중복 제거/쿨다운, 방해 금지 시간대/시간대, 최소 등급, 일일 요약(예약).
- 시스템 실행(7개 필드): 로그 수준, 디버그 모드, 최대 동시 실행 수, 분석 간격, 시장 분석 스위치/시장/색상 구성.
- AI legacy와 Anspire 설정: provider 전용 다중 Key, 모델 이름, temperature, Vision 모델, max tokens, Anspire LLM 게이트웨이 필드.
- 데이터 소스와 검색: TickFlow, SerpAPI, Brave, Bocha, MiniMax, SearXNG 공개 인스턴스, BIAS(이격도) 임곗값, Pytdx 서버 필드.
- 알림 고급 필드: Feishu(페이슈) 고급 보안/앱 필드, Telegram topic, Discord/Slack 고급 필드, Pushover, ntfy, Gotify, PushPlus, ServerChan3, AstrBot, 사용자 정의 Webhook 고급 템플릿/인증 필드.

Issue #1512를 마무리한 뒤로 웹 설정 페이지는 백엔드 설정 레지스트리에 정식으로 등록된 필드만 보여 줍니다. 등록되지 않은 `.env` key는 더 이상 일반 편집 항목으로 보이지 않으며, raw key나 `Auto-inferred field metadata.`, help 버튼 없는 설정 항목이 화면에 섞이지 않게 합니다. 이런 key는 여전히 `.env` 파일이나 가져오기/내보내기 기능으로 유지하고 관리할 수 있습니다.

예외: `LLM_CHANNELS`가 선언한 동적 채널 세부 키(예: `LLM_DEEPSEEK_API_KEY`, `LLM_MY_PROXY_MODELS`)는 설정 API 응답에 남아 "AI 모델 연결" 편집기가 읽고 저장할 수 있게 합니다. 이 키들은 일반 설정 카드로 보이지 않으며, `WEB_SETTINGS_HIDDEN_FROM_UI`의 운영용 숨김 의미도 쓰지 않습니다.

아직 웹 설정 페이지에 넣지 않은, 자주 쓰지 않거나 운영용인 `.env` 변수로는 `DATABASE_PATH`, `SQLITE_*`, `USE_PROXY`, `PROXY_HOST`, `PROXY_PORT` 등이 있습니다. 나중에 웹에서 이 필드들을 편집해야 한다면 자동 추정에 기대지 말고 먼저 `src/core/config_registry.py`에 정식으로 등록하고 help 메타데이터를 채워야 합니다.

### 적용 범위의 경계

- `settingsHelp.ts`의 `settings.llm_channel.*` 계열은 LLM 채널 편집기 내부 필드 설명으로, 프런트엔드 렌더링에만 쓰이며 `.env`의 개별 설정 항목과 대응하지 않습니다. 편집기를 쓰기 쉽게 하려고 PR2에서 의도적으로 넣은 "내장 확장" 설계입니다.
- 나머지 help 문구는 모두 `src/core/config_registry.py`의 어떤 필드의 `help_key`를 통해 백엔드 등록 메타데이터와 연결되어야 합니다. 그래야 문서 출처, `warning_codes`와 함께 일관되게 관리할 수 있습니다.

## 기준 자료 우선순위

도움말 문구를 추가하거나 고칠 때는 다음 순서로 확인합니다.

1. `.env.example`: 설정 키 이름, 기본값, 예시 형식, 민감 정보 자리 표시자.
2. `docs/full-guide.md`: 주요 설정 설명, 실행 진입점, 배포 맥락.
3. `docs/LLM_CONFIG_GUIDE.md`, `docs/llm-providers.md`: LLM 우선순위, Channels, provider/model, 호환 범위, 문제 해결 설명.
4. 주제별 문서: 예를 들어 `docs/bot/feishu-bot-config.md`, `docs/deploy-webui-cloud.md`, `docs/desktop-package.md`.
5. 코드 구현과 테스트: 문서와 코드가 다르면 실제로 실행되는 구현을 먼저 기준으로 삼고 문서를 함께 고칩니다.

## 관리 원칙

- 도움말 문구는 설정 저장, 검증, 실행 시점 우선순위, `.env` 되쓰기, 환경 변수 덮어쓰기의 의미를 바꿀 수 없습니다.
- 실제 키, 계정, token, Webhook 전체 값, 로컬 절대 경로를 보여 주지 않습니다.
- LLM 관련 예시에 특정 provider 접두사, 모델 이름, Base URL을 쓴다면 현재 저장소 문서나 공식 출처로 거슬러 확인할 수 있어야 합니다. 그렇지 않으면 자리 표시자를 쓰거나 기준 자료로 링크합니다.
- 서드파티 모델/API의 사용 가능 여부, LiteLLM 호환 기간, provider fallback 규칙은 설정 도움말에서 따로 약속하지 않습니다. 바꿔야 한다면 주제별 문서와 PR 호환성 설명을 함께 고쳐야 합니다.
- 중국어와 영어 문구는 같은 의미 범위를 유지해야 합니다. 한 언어만 고쳤다면 전달 설명에 이유를 적어야 합니다.
- 첫 화면의 짧은 설명은 간결하게 두고 자세한 설명은 help dialog에 넣어, hover 툴팁과 늘 보이는 짧은 설명이 겹치지 않게 합니다.

## 재시작이 필요한 경우

설정 페이지에서 저장하면 보통 `.env`에만 쓰고, 실행 중 다시 불러올 수 있는 설정을 새로 고칩니다. 도움말 문구와 `warning_codes`는 다음 경우를 분명히 구분해야 합니다.

- `WEBUI_HOST`, `WEBUI_PORT`: 수신 주소와 포트는 프로세스가 시작될 때만 연결되므로, 저장한 뒤 현재 프로세스, Docker 컨테이너, 서비스 관리자를 다시 시작해야 적용됩니다.
- `RUN_IMMEDIATELY`: schedule 모드가 아닐 때 시작 시 한 번 실행할지 정하는 설정입니다. 저장해도 이미 실행 중인 WebUI/API 프로세스가 바로 분석을 시작하지는 않습니다.
- 웹 설정 페이지는 `SCHEDULE_TIME` / `SCHEDULE_TIMES` / `SCHEDULE_RUN_IMMEDIATELY` 같은 내부 키를 직접 보여 주지 않습니다. 사용자는 "예약 실행" 카드에서 사용 여부, 여러 실행 시각, 지금 한 번 실행을 관리합니다.
- `SCHEDULE_ENABLED`: WebUI/API/Desktop처럼 오래 실행되는 프로세스(`python main.py --serve --schedule` 포함)는 저장 후 새 값에 따라 runtime scheduler를 시작하거나 멈춥니다. `--serve-only`나 Desktop 프로세스를 다시 시작할 때도 켜져 있던 daily jobs를 복구하지만, 그 때문에 바로 분석을 실행하지는 않습니다. 순수 CLI schedule 모드(`python main.py --schedule`)는 여전히 시작할 때의 인수와 설정대로 동작합니다.
- `SCHEDULE_TIME`, `SCHEDULE_TIMES`: 재시작이 필요하지 않습니다. `SCHEDULE_TIMES`가 비어 있으면 `SCHEDULE_TIME`을 씁니다. 실행 중인 scheduler는 새 시각으로 daily jobs를 다시 만듭니다.
- `SCHEDULE_RUN_IMMEDIATELY`: schedule 모드의 시작 동작입니다. 저장해도 현재 프로세스가 바로 한 번 분석하지는 않습니다. 수동 실행은 runtime scheduler의 run-now API를 쓰세요.
- `SCHEDULE_STARTUP_DEDUP`: 순수 CLI schedule 모드(`python main.py --schedule`)에서 시작 즉시 실행할 때 같은 날 중복을 막는 스위치이며, 웹 설정 페이지에는 직접 나오지 않습니다. 자세한 내용은 `docs/full-guide.md`의 설정 표를 보세요.
- runtime scheduler의 run-now API는 실행 중인 분석 작업이 없을 때만 요청을 받습니다. 이미 분석이 진행 중이면 바쁨 상태를 돌려주고, 웹 설정 페이지는 잠시 후 다시 시도하라고 안내합니다.
