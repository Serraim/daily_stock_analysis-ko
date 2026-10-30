# 알림 기능 기준 문서

이 문서는 알림 기능 P0-P7의 최종 상태를 기록합니다. 채널, 설정 key, GitHub Actions 매핑, 웹 설정 메타데이터, CLI 진단 기준, 웹 원클릭 테스트, 사용자 정의 Webhook Body 템플릿 의미, 알림 라우팅 정책, 소음 줄이기, 통합 리포트 실패 격리, ntfy / Gotify 정식 채널, WebPush / Apprise 검토, 그리고 로컬 / Docker / GitHub Actions / Desktop 상황별 설정 안내를 다룹니다. P0은 기준 정리와 읽기 전용 진단만 했고, P1은 웹에서 채널 하나씩 실제 테스트를 추가했습니다. P2는 기존 Body 템플릿을 제품 기능으로 다듬었고, P3은 report / alert / system_error 라우팅을, P4는 프로세스 내 소음 줄이기를 추가했습니다. P5는 테스트 진단과 통합 리포트의 채널별 실패 격리를 강화했고, P6-A는 ntfy, P6-C는 Gotify를 추가했으며, P6-D는 WebPush / Apprise를 검토만 했습니다. P7은 문서를 마무리하고 Actions env 대조표를 자동화했으며, 실행 시 의존성, 설정 진입점, URL별 템플릿, 프로세스 간 영구 저장, 실제 일일 요약, 재시도 루프는 추가하지 않습니다.

## 채널 기준

| 채널 | 유형 | Minimal key | Advanced key | 설명 |
| --- | --- | --- | --- | --- |
| DingTalk(딩톡) Webhook | 정적 설정 | `DINGTALK_WEBHOOK_URL` | `DINGTALK_SECRET` | 서명(加签) 보안 방식을 지원하며, Web UI 설정 페이지와 채널별 테스트에 연결되어 있습니다. |
| WeCom(기업용 위챗) | 정적 설정 | `WECHAT_WEBHOOK_URL` | `WECHAT_MSG_TYPE` | 설정하면 일괄 알림 발송에 참여합니다 |
| Feishu(페이슈) Webhook / App Bot | 정적 설정 | `FEISHU_WEBHOOK_URL` 또는 `FEISHU_APP_ID` + `FEISHU_APP_SECRET` + `FEISHU_CHAT_ID` | `FEISHU_WEBHOOK_SECRET`, `FEISHU_WEBHOOK_KEYWORD`, `FEISHU_RECEIVE_ID_TYPE`, `FEISHU_DOMAIN` | Webhook URL이 우선합니다. Webhook을 설정하지 않았다면 App Bot 세 값으로 지정한 그룹/사용자에게 직접 알림을 보낼 수 있습니다. `FEISHU_STREAM_ENABLED`는 이벤트 구독 / Stream Bot만 뜻하며, 직접 알림 설정 완료 판단에는 쓰이지 않습니다 |
| Telegram | 정적 설정 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `TELEGRAM_MESSAGE_THREAD_ID` | token과 chat id가 모두 있어야 합니다 |
| 메일 | 정적 설정 | `EMAIL_SENDER`, `EMAIL_PASSWORD` | `EMAIL_RECEIVERS`, `EMAIL_SENDER_NAME` | `EMAIL_RECEIVERS`를 비워 두면 자기 자신에게 보냅니다 |
| Pushover | 정적 설정 | `PUSHOVER_USER_KEY`, `PUSHOVER_API_TOKEN` | - | 두 key가 모두 있어야 합니다 |
| ntfy | 정적 설정 | `NTFY_URL` | `NTFY_TOKEN`, `WEBHOOK_VERIFY_SSL` | `NTFY_URL`에는 topic 경로가 있어야 합니다. 예: `https://ntfy.sh/my-topic` |
| Gotify | 정적 설정 | `GOTIFY_URL`, `GOTIFY_TOKEN` | `WEBHOOK_VERIFY_SSL` | `GOTIFY_URL`은 서버 base URL이며 `/message`를 포함하지 않습니다. token은 `X-Gotify-Key` Header로 보냅니다 |
| PushPlus | 정적 설정 | `PUSHPLUS_TOKEN` | `PUSHPLUS_TOPIC` | `PUSHPLUS_TOPIC`은 token이 있을 때만 적용됩니다 |
| Server酱3(ServerChan3) | 정적 설정 | `SERVERCHAN3_SENDKEY` | - | 휴대폰 앱 푸시 |
| 사용자 정의 Webhook | 정적 설정 | `CUSTOM_WEBHOOK_URLS` | `CUSTOM_WEBHOOK_BEARER_TOKEN`, `CUSTOM_WEBHOOK_BODY_TEMPLATE`, `WEBHOOK_VERIFY_SSL` | 여러 URL을 쉼표로 구분해 넣을 수 있습니다 |
| Discord | 정적 설정 | `DISCORD_WEBHOOK_URL` 또는 `DISCORD_BOT_TOKEN` + `DISCORD_MAIN_CHANNEL_ID` | `DISCORD_INTERACTIONS_PUBLIC_KEY` | Webhook과 Bot 모두 발송에 쓸 수 있습니다 |
| Slack | 정적 설정 | `SLACK_WEBHOOK_URL` 또는 `SLACK_BOT_TOKEN` + `SLACK_CHANNEL_ID` | - | 텍스트와 이미지를 같은 채널로 보낼 때는 Bot을 우선 씁니다 |
| AstrBot | 정적 설정 | `ASTRBOT_URL` | `ASTRBOT_TOKEN`, `WEBHOOK_VERIFY_SSL` | `ASTRBOT_TOKEN`은 선택 사항입니다 |
| `UNKNOWN` | 대체 열거값 | - | - | 알 수 없는 채널을 받기 위한 값이며, 정적 환경 변수로 켜지지 않습니다 |
| DingTalk 대화 | 실행 시 맥락 | - | - | 출처 메시지 맥락에서 가져오므로 `.env`만으로는 정적으로 판단할 수 없습니다 |
| Feishu 대화 | 실행 시 맥락 | - | - | 출처 메시지 맥락에서 가져오며, 대화형 명령 결과는 출처 대화로만 돌아갑니다 |
| Telegram 대화 | 실행 시 맥락 | - | - | 출처 메시지 맥락에서 가져오며, 대화형 명령 결과는 출처 대화로만 돌아갑니다 |

Discord로 긴 리포트를 보낼 때는 기존 분할 발송 경로를 재사용합니다. 실행 중 `content` 하나가 Discord의 2000자 제한을 넘지 않으며, Webhook과 Bot API 모두 조각을 하나씩 보내고 조각 사이에 잠시 기다립니다. 429를 받으면 Discord가 돌려준 `retry_after`나 `Retry-After`에 따라 제한된 횟수만큼 재시도해, 중간에 요청 제한에 걸려 리포트 앞부분만 받는 일을 막습니다.

## Minimal / Advanced 구분

- Minimal key: 알림 채널 하나를 켜는 데 충분한 최소 설정입니다.
- Advanced key: 인증, 보안, 형식, 스레드, 그룹, 인증서 검증, 표시 방식에만 영향을 주며, 혼자서는 채널을 켤 수 없습니다.
- P3의 `NOTIFICATION_*_CHANNELS`는 Advanced key입니다. 이미 켜진 채널을 좁힐 뿐, 혼자서 채널을 켜지 않습니다.
- P4의 `NOTIFICATION_DEDUP_TTL_SECONDS`, `NOTIFICATION_COOLDOWN_SECONDS`, `NOTIFICATION_QUIET_HOURS`, `NOTIFICATION_TIMEZONE`, `NOTIFICATION_MIN_SEVERITY`, `NOTIFICATION_DAILY_DIGEST_ENABLED`는 Advanced key입니다. 이미 켜진 정적 채널의 발송 방식에만 영향을 주며, 혼자서 채널을 켜지 않습니다.
- `REPORT_SHOW_LLM_MODEL`은 리포트 표시 스위치입니다. 기본값 `true`이면 알림 리포트 아래쪽에 이번 분석에 쓴 LLM 모델을 보여 주고, `false`이면 숨깁니다. 이 값은 리포트 렌더링에만 영향을 주며, 실행 시 provider/model/Base URL, LiteLLM 라우팅, 모델 저장, 마이그레이션, 정리 로직은 바꾸지 않습니다. 되돌리려면 `true`로 바꾸거나 변수를 지웁니다.
- `WEBHOOK_VERIFY_SSL`은 이 설정을 읽는 webhook 계열 HTTPS 알림 요청이 함께 쓰는 인증서 검증 스위치입니다.
- WebPush, Apprise, 더 세밀한 라우팅, 프로세스 간 소음 줄이기, 실제 일일 요약은 아직 실행 기능으로 구현하지 않았습니다. 나중에 관련 설정을 도입한다면 먼저 이 문서, `.env.example`, 웹 메타데이터, 회귀 테스트를 고쳐야 합니다.
- Bark는 custom webhook 기준을 유지하며, `BARK_*` 정식 설정을 추가하지 않습니다.
- Feishu App Bot 발송 경로는 `requirements.txt`에 이미 있는 `lark-oapi>=1.0.0`을 재사용하므로 새 의존성이 아닙니다. 표준 소스 설치, Docker, GitHub Actions daily workflow, 데스크톱 빌드 과정은 모두 `pip install -r requirements.txt`로 설치합니다. 공식 근거: [Feishu message create OpenAPI](https://open.feishu.cn/document/server-docs/im-v1/message/create), [lark-oapi PyPI](https://pypi.org/project/lark-oapi/), [SDK repo](https://github.com/larksuite/oapi-sdk-python). App Bot 파일 업로드는 같은 SDK의 `im.v1.file.create` API를 쓰며, 공식 문서는 [Feishu file create OpenAPI](https://open.feishu.cn/document/server-docs/im-v1/file/create)입니다.

## 리포트 렌더링과 분할

현재 기본 알림 리포트의 진입점, 내용 출처, 전체 레이아웃은 그대로입니다. 이번 단계에서는 알림 렌더링의 기술 방향만 정리했습니다. 채널별 기능 프로필, 발송 전 메시지 구조, 구조를 인식하는 분할 기능을 갖춰, 앞으로 채널을 늘릴 때 sender마다 비슷한 로직을 계속 쌓지 않게 합니다.

기본 발송 경로는 기존 sender 동작을 그대로 쓰며, 새 renderer를 연결하지 않았습니다. Feishu와 Telegram은 원래의 호환 변환을, WeCom과 Slack은 원래의 분할 로직을 계속 써서 실제로 보이는 리포트 레이아웃이 바뀌지 않게 했습니다. 새로 추가한 채널 기능 프로필, PreparedMessage, renderer preset, 구조 인식 분할은 앞으로의 확장 기반일 뿐입니다. WeCom, Feishu, Telegram, Slack 등 채널 전용 renderer를 쓰려면 명시적 설정, 실제 발송 검증, 회귀 테스트를 거쳐 단계적으로 연결해야 합니다.

호환성 제외 안내:
- 이번에는 `src/notification_sender/wechat_sender.py`, `src/notification_sender/slack_sender.py`, `src/notification_sender/telegram_sender.py`의 발송 경로를 바꾸지 않았습니다. `src/notification_sender/feishu_sender.py`에는 `send_feishu_file()` 파일 발송 경로를 추가했으며, Webhook 모드에서는 파일 내용을 텍스트로 보내는 방식으로 대신하고, App Bot 텍스트 발송 경로(`send_to_feishu` → `_send_via_app_bot`)는 그대로입니다.
- `model_used`는 리포트 렌더링 끝부분에만 표시되며, provider/model/base_url의 실행 시 선택, 저장, 정리, 마이그레이션에 관여하지 않습니다. 어떤 CI 스캔에서 "provider/API 호환 마이그레이션" 같은 키워드가 걸리면, 먼저 테스트 fixture의 `model_used` 예시와 리포트 스냅샷 fixture(`tests/fixtures/notification_reports/*.md`), 그리고 `src/notification.py`의 `report_show_llm_model` 표시 전용 스위치 로직으로 범위를 좁혀 확인하세요.
- `REPORT_SHOW_LLM_MODEL`과 `report_renderer_enabled`는 모두 표시/기능 저하 방침 스위치입니다. 끄면 리포트에 보이는 구조만 바뀌고, 설정 마이그레이션이나 실행 매개변수 되돌리기는 일어나지 않습니다. 되돌리려면 `true`로 돌리거나(또는 항목을 지우거나) 기본 설정으로 복원합니다.

관련 섹터 렌더링은 리포트 본문을 만드는 단계에서 처리합니다. 업종/테마 등락 순위 신호가 없으면 알림 리포트는 원래의 한 줄 형식을 씁니다. 예: `通信线缆及配套 / 通信设备 / 通信 / 江苏板块 / 科技风格`(통신 케이블 및 부품 / 통신 장비 / 통신 / 장쑤 섹터 / 기술주 스타일). 이때 "유형" 열은 따로 보여 주지 않습니다. `fundamental_context.boards.data` / `sector_rankings`나 `fundamental_context.concept_boards.data` / `concept_rankings`의 상승 주도/하락 주도 신호가 잡힐 때만 "섹터 / 유형 / 섹터 성과 / 섹터 등락률" 표로 보여 주며, "유형" 열은 "업종 섹터"인지 "테마 섹터"인지 표시합니다. 이 로직은 리포트 표시에만 영향을 주며 provider/model/Base URL, LiteLLM 라우팅, 모델 저장, 마이그레이션, 정리 로직을 바꾸지 않습니다.

## GitHub Actions 매핑

저장소에 들어 있는 `.github/workflows/00-daily-analysis.yml`은 정해진 변수 이름만 명시적으로 가져옵니다. P0/P3/P4/P6에서 Body 템플릿, 보안 항목, PushPlus topic, 라우팅, 소음 줄이기, ntfy, Gotify 등 알림 key를 기본 workflow에 넣었습니다. 아래 표는 `scripts/generate_notification_actions_env_table.py`가 workflow의 `env:`와 알림 진단 메타데이터에서 만들어 내며, 손으로 쓴 대조표가 실제 Actions 매핑과 계속 어긋나는 일을 막습니다.

<!-- notification-actions-env-table:start -->

| Key | Tier | Channel / feature | Actions source | Default |
| --- | --- | --- | --- | --- |
| `WECHAT_WEBHOOK_URL` | minimal | wechat | Secret | - |
| `WECHAT_MSG_TYPE` | advanced | wechat | Variable or Secret | `markdown` |
| `FEISHU_WEBHOOK_URL` | minimal | feishu | Secret | - |
| `FEISHU_WEBHOOK_SECRET` | advanced | feishu | Secret | - |
| `FEISHU_WEBHOOK_KEYWORD` | advanced | feishu | Variable or Secret | - |
| `DINGTALK_WEBHOOK_URL` | minimal | dingtalk | Secret | - |
| `DINGTALK_SECRET` | advanced | dingtalk | Secret | - |
| `TELEGRAM_BOT_TOKEN` | minimal | telegram | Secret | - |
| `TELEGRAM_CHAT_ID` | minimal | telegram | Secret | - |
| `TELEGRAM_MESSAGE_THREAD_ID` | advanced | telegram | Secret | - |
| `EMAIL_SENDER` | minimal | email | Variable or Secret | - |
| `EMAIL_PASSWORD` | minimal | email | Secret | - |
| `EMAIL_RECEIVERS` | advanced | email | Variable or Secret | - |
| `EMAIL_SENDER_NAME` | advanced | email | Variable or Secret | `daily_stock_analysis股票分析助手` |
| `PUSHOVER_USER_KEY` | minimal | pushover | Secret | - |
| `PUSHOVER_API_TOKEN` | minimal | pushover | Secret | - |
| `NTFY_URL` | minimal | ntfy | Secret | - |
| `NTFY_TOKEN` | advanced | ntfy | Secret | - |
| `GOTIFY_URL` | minimal | gotify | Secret | - |
| `GOTIFY_TOKEN` | minimal | gotify | Secret | - |
| `PUSHPLUS_TOKEN` | minimal | pushplus | Secret | - |
| `PUSHPLUS_TOPIC` | advanced | pushplus | Variable or Secret | - |
| `CUSTOM_WEBHOOK_URLS` | minimal | custom | Secret | - |
| `CUSTOM_WEBHOOK_BEARER_TOKEN` | advanced | custom | Secret | - |
| `CUSTOM_WEBHOOK_BODY_TEMPLATE` | advanced | custom | Variable or Secret | - |
| `WEBHOOK_VERIFY_SSL` | advanced | ntfy, gotify, custom, astrbot | Variable or Secret | `true` |
| `DISCORD_WEBHOOK_URL` | minimal | discord | Secret | - |
| `DISCORD_BOT_TOKEN` | minimal | discord | Secret | - |
| `DISCORD_MAIN_CHANNEL_ID` | minimal | discord | Secret | - |
| `FEISHU_APP_ID` | minimal | feishu | Secret | - |
| `FEISHU_APP_SECRET` | minimal | feishu | Secret | - |
| `FEISHU_CHAT_ID` | minimal | feishu | Variable or Secret | - |
| `FEISHU_RECEIVE_ID_TYPE` | advanced | feishu | Variable or Secret | - |
| `FEISHU_DOMAIN` | advanced | feishu | Variable or Secret | - |
| `FEISHU_SEND_AS_FILE` | advanced | feishu | Variable or Secret | - |
| `ASTRBOT_URL` | minimal | astrbot | Secret | - |
| `ASTRBOT_TOKEN` | advanced | astrbot | Secret | - |
| `SERVERCHAN3_SENDKEY` | minimal | serverchan3 | Secret | - |
| `SLACK_WEBHOOK_URL` | minimal | slack | Secret | - |
| `SLACK_BOT_TOKEN` | minimal | slack | Secret | - |
| `SLACK_CHANNEL_ID` | minimal | slack | Secret | - |
| `NOTIFICATION_REPORT_CHANNELS` | advanced | routing | Variable or Secret | - |
| `NOTIFICATION_ALERT_CHANNELS` | advanced | routing | Variable or Secret | - |
| `NOTIFICATION_SYSTEM_ERROR_CHANNELS` | advanced | routing | Variable or Secret | - |
| `NOTIFICATION_DEDUP_TTL_SECONDS` | advanced | noise | Variable or Secret | `0` |
| `NOTIFICATION_COOLDOWN_SECONDS` | advanced | noise | Variable or Secret | `0` |
| `NOTIFICATION_QUIET_HOURS` | advanced | noise | Variable or Secret | - |
| `NOTIFICATION_TIMEZONE` | advanced | noise | Variable or Secret | - |
| `NOTIFICATION_MIN_SEVERITY` | advanced | noise | Variable or Secret | - |
| `NOTIFICATION_DAILY_DIGEST_ENABLED` | advanced | noise | Variable or Secret | `false` |

<!-- notification-actions-env-table:end -->
(표의 `EMAIL_SENDER_NAME` 기본값 `daily_stock_analysis股票分析助手`는 "daily_stock_analysis 주식 분석 도우미"라는 뜻의 프로그램 기본 발신자 이름입니다.)

기본 workflow는 여전히 `MARKDOWN_TO_IMAGE_CHANNELS`와 `MERGE_EMAIL_NOTIFICATION`을 매핑하지 않습니다. 이 둘은 채널 자격 증명이 아니라 발송 형태나 묶음 동작을 정하는 스위치이므로, Actions에서 같은 이름의 Secret/Variable을 자동으로 읽기 시작하면 동작이 예상치 않게 바뀔 수 있습니다.

## 이미지 리포트 공유 템플릿

`MARKDOWN_TO_IMAGE_CHANNELS`를 설정하면 개별 종목 분석, 통합 리포트, 시장 복기는 기존 알림 라우팅을 그대로 따르면서, 이미지로 바꾸는 단계에서 너비 1080px의 브랜드 공유 템플릿을 씁니다. 개별 종목 하나는 "결론—가격대—기술적 분석—위험—보유" 순서의 판단 카드로, 시장은 "신호—지수—시장 폭—강세/약세 섹터—자금 관찰—주요 추적—전략—위험" 순서의 복기 카드로 만들며, 여러 종목 리포트는 통합 레이아웃을 유지합니다. 아래쪽에는 GitHub 저장소 주소, 선택 사항인 샤오훙수(小红书) 계정 영역, "仅供研究交流，不构成投资建议"(연구·교류용이며 투자 권유가 아님) 위험 안내가 표시됩니다.

- 샤오훙수 URL, 닉네임, QR 코드 경로는 `SHARE_IMAGE_XIAOHONGSHU_*` 설정으로 바꿀 수 있습니다. QR 코드 아래에는 닉네임만 보이고 숫자 ID는 보이지 않습니다. 모두 비워 두면 내장 QR 코드와 닉네임 `@霸天土小豆`를 보여 줍니다. QR 코드는 이미지로 바꿀 때 HTML에 넣으므로, 외부 이미지 서비스나 실행 중 네트워크에 의존하지 않습니다.
- 템플릿은 리포트에 이미 있는 0–100 점수, 8단계 행동, `battle_plan.sniper_points` 가격대만 보여 줍니다. 이상적/차선 매수가, 손절가, 목표가는 대비가 강한 전용 매매 카드로 표시하며, 점수나 매수·매도 비율을 따로 만들지 않습니다.
- 구조화 필드, 결측값 처리, 개별 종목/시장 매핑, 로컬 미리 보기 예시는 [공유 이미지 템플릿과 데이터 채우기](share-images.md)를 보세요.
- `wkhtmltoimage`, `markdown-to-file`, `playwright`는 같은 포스터 HTML을 씁니다. 기존 `MD2IMG_ENGINE`, `MARKDOWN_TO_IMAGE_MAX_CHARS`, 변환 실패 시 텍스트로 돌아가는 동작은 그대로입니다. Playwright 모드는 먼저 웹 의존성을 설치하고 `npx playwright install chromium`을 실행해야 합니다.
- 템플릿은 본문 길이에 맞춰 긴 이미지를 만들며, 정해진 화면 크기에 맞추려고 리포트를 잘라 내지 않습니다. 내용이 `MARKDOWN_TO_IMAGE_MAX_CHARS`를 넘으면 여전히 이미지 변환을 건너뜁니다.
- GitHub Actions는 기본적으로 `MARKDOWN_TO_IMAGE_CHANNELS`를 매핑하지 않습니다. fork한 workflow에서 쓰려면 환경 변수 매핑을 직접 추가하고 고른 변환 도구를 설치해야 합니다.

## CLI 진단

```bash
python main.py --check-notify
```

이 명령은 설정을 읽기만 하며, 알림을 보내거나 `.env`에 쓰지 않습니다. 설정 로드와 로그 초기화 직후에 실행되고 끝나면 바로 종료하며, Web, 스케줄, 시장 복기, 기본 분석 흐름으로 들어가지 않습니다.

- 종료 코드 `0`: error 수준 진단이 없습니다.
- 종료 코드 `1`: error가 있습니다. 예를 들어 설정된 정적 알림 채널이 0개이거나, 짝을 이뤄야 하는 key를 반만 설정한 경우입니다.

## 웹 원클릭 테스트

웹 설정 페이지의 "알림 채널" 분류에서 채널 하나씩 테스트할 수 있습니다. 테스트는 현재 페이지의 초안 값으로 임시 설정을 만들어 실제 테스트 알림 한 건을 보내지만, `.env`를 저장하거나 실행 중인 전역 설정을 바꾸지는 않습니다.

- 테스트 범위: 정적 알림 채널 14개. `UNKNOWN`과 실행 시 맥락 채널은 포함하지 않습니다.
- 일반 채널: 한 번의 발송 결과, 걸린 시간, 공통 오류 코드를 돌려줍니다.
- 사용자 정의 Webhook: URL 순서대로 attempts를 돌려주며, URL마다 성공/실패, HTTP 상태, 걸린 시간, 오류 코드를 보여 줍니다. 여러 URL 가운데 일부만 성공하면 최상위 message에 성공 수 / 전체 수를 표시합니다.
- 돌려주는 결과에서는 token, secret, password, Bearer, webhook 전체 query, token으로 보이는 경로를 가립니다.
- 설정이 없거나 발송에 실패하면 `success=false`를 돌려주며, 저장된 설정과 기본 분석 흐름에는 영향을 주지 않습니다.

## 사용자 정의 Webhook Body 템플릿

`CUSTOM_WEBHOOK_BODY_TEMPLATE`은 사용자 정의 Webhook의 전역 JSON body 템플릿입니다. 설정하면 URL 자동 인식보다 먼저 적용되므로 Bark, Slack, Discord, DingTalk 등의 자동 payload를 덮어씁니다. 설정하지 않으면 원래대로 URL 자동 인식을 씁니다. 렌더링 결과가 올바른 JSON object가 아니면 오류를 기록하고 기본 payload로 돌아가며, 주 알림 흐름은 멈추지 않습니다.

쓸 수 있는 자리 표시자:

- `$content_json`: JSON 이스케이프한 알림 본문. 기본으로 이것을 권장합니다.
- `$title_json`: JSON 이스케이프한 알림 제목. 기본으로 이것을 권장합니다.
- `$content` / `$title`: 이스케이프하지 않은 원래 문자열입니다. 본문에 큰따옴표, 백슬래시, 줄바꿈이 있으면 JSON이 깨져 fallback이 일어날 수 있습니다.

Docker Compose 배포에서 웹 설정 페이지가 이 템플릿을 `.env`에 저장할 때는, 앱 자리 표시자를 자동으로 `$$content_json`, `$$title_json`, `$$content`, `$$title`로 씁니다. Compose가 이를 호스트 환경 변수로 보고 빈 값으로 펼치지 않게 하기 위해서이며, 앱은 실행할 때 다시 `$` 하나짜리 자리 표시자로 되돌립니다. Docker가 쓰는 `.env`를 직접 편집할 때도 `$$content_json` 형식으로 저장하세요.

이 기능은 알림 본문 렌더링에만 영향을 주며, LLM `provider` / `model` / `base URL` / LiteLLM 라우팅의 저장, 마이그레이션, 정리 의미와는 관계없습니다. 구조화 스캔에서 provider/API 호환 의미가 걸린다면, 이번 webhook 수정 경로 자체가 아니라 이 문서의 리포트 모델 표시와 알림 설정 분리 설명으로 범위를 좁혀 확인하세요.

일반 webhook 예시:

```env
CUSTOM_WEBHOOK_BODY_TEMPLATE={"title":$title_json,"content":$content_json}
```

Bark를 custom webhook으로 쓸 때는 Bark endpoint를 `CUSTOM_WEBHOOK_URLS`에 바로 넣으면 되며, `BARK_*` 설정은 따로 필요 없습니다. 전역 템플릿을 설정하지 않으면 시스템이 `api.day.app` 기준으로 `title` / `body` / `group`을 자동으로 만듭니다. 전역 템플릿을 설정했다면 Bark body를 직접 써야 합니다.

```env
CUSTOM_WEBHOOK_URLS=https://api.day.app/YOUR_BARK_KEY
```

```env
CUSTOM_WEBHOOK_BODY_TEMPLATE={"title":$title_json,"body":$content_json,"group":"stock"}
```

AstrBot은 이미 정식 알림 채널이므로 `ASTRBOT_URL`과 선택 사항인 `ASTRBOT_TOKEN`을 우선 쓰세요. AstrBot 호환 endpoint를 `CUSTOM_WEBHOOK_URLS`에 넣어야 할 때만 custom webhook 템플릿을 씁니다. 예:

```env
CUSTOM_WEBHOOK_BODY_TEMPLATE={"content":$content_json}
```

ntfy는 이미 정식 알림 채널이므로 `NTFY_URL`과 선택 사항인 `NTFY_TOKEN`을 우선 쓰세요. `NTFY_URL`은 완전한 topic endpoint를 뜻합니다. 예: `https://ntfy.sh/my-topic` 또는 `https://self-hosted:port/my-topic`. 시스템은 마지막 경로 조각을 topic으로 해석하고 서버 루트로 JSON publish를 보냅니다.

```env
NTFY_URL=https://ntfy.sh/my-topic
NTFY_TOKEN=
```

Gotify는 이미 정식 알림 채널이므로 `GOTIFY_URL`과 `GOTIFY_TOKEN`을 우선 쓰세요. `GOTIFY_URL`은 Gotify 서버 base URL을 뜻하며, 리버스 프록시 경로 접두사는 넣을 수 있지만 `/message`는 넣지 않습니다. 시스템은 보낼 때 고정 `/message` API를 붙이고, application token을 `X-Gotify-Key` Header로 보냅니다. `NTFY_URL`은 완전한 topic endpoint이고 `GOTIFY_URL`은 서버 base URL인데, 이는 두 서비스의 API 설계 차이 때문에 일부러 그렇게 한 것입니다.

```env
GOTIFY_URL=https://gotify.example
GOTIFY_TOKEN=app-token
```

```env
# 리버스 프록시 경로 접두사 예시. 실제 요청은 https://example.com/gotify/message 로 갑니다
GOTIFY_URL=https://example.com/gotify
GOTIFY_TOKEN=app-token
```

NapCat / OneBot HTTP API는 실제 endpoint와 대상 유형에 맞춰 조정해야 합니다. 아래는 흔한 body 형태의 예일 뿐이며, `user_id`, `group_id`, URL 경로, 인증 방식은 사용하는 NapCat 설정을 따르세요.

```env
# 개인 대화: CUSTOM_WEBHOOK_URLS=http://127.0.0.1:3000/send_private_msg
CUSTOM_WEBHOOK_BODY_TEMPLATE={"user_id":123456,"message":$content_json}
```

```env
# 그룹 대화: CUSTOM_WEBHOOK_URLS=http://127.0.0.1:3000/send_group_msg
CUSTOM_WEBHOOK_BODY_TEMPLATE={"group_id":123456789,"message":$content_json}
```

## 알림 라우팅 정책

P3은 세 가지 알림 라우팅 설정을 추가했습니다.

| 라우팅 유형 | 설정 key | 현재 발생원 |
| --- | --- | --- |
| `report` | `NOTIFICATION_REPORT_CHANNELS` | 개별 종목 알림, 통합 일일 리포트, 시장 복기, 합친 알림, Feishu 문서 성공 링크 |
| `alert` | `NOTIFICATION_ALERT_CHANNELS` | EventMonitor 발동 알림 |
| `system_error` | `NOTIFICATION_SYSTEM_ERROR_CHANNELS` | 예약된 기능. 현재 자동 시스템 오류 발생원은 추가하지 않음 |

설정 값은 쉼표로 구분한 채널 열거값입니다: `wechat,dingtalk,feishu,telegram,email,pushover,ntfy,gotify,pushplus,serverchan3,custom,discord,slack,astrbot`.

- 비워 두거나 설정하지 않으면: 예전처럼 설정된 모든 정적 채널로 보냅니다.
- 값이 있으면: 라우팅 목록과 설정된 채널의 교집합에만 보냅니다. 교집합이 비어 있어도 전체 채널로 대신 보내지 않습니다.
- `send_to_context()`는 라우팅 제한을 받지 않으므로, 봇 대화 맥락은 여전히 작업을 시작한 쪽의 답장을 받습니다.
- 대화형 명령(DingTalk 대화, Feishu 대화, Telegram)에 출처 맥락이 있으면 `FEISHU_WEBHOOK_URL` 같은 정적 알림 채널은 건너뜁니다. `SCHEDULE`, CLI, API, 출처 맥락이 없는 작업은 여전히 report 라우팅대로 보냅니다.
- 라우팅 필터는 Markdown을 이미지로 바꾸기 전에 적용되며, `MARKDOWN_TO_IMAGE_CHANNELS`는 라우팅을 거친 채널에만 적용됩니다.
- `MERGE_EMAIL_NOTIFICATION`은 따로 설정할 필요가 없습니다. report 라우팅 뒤의 채널에 `email`이 남아 있으면 기존 메일 합치기 동작은 그대로입니다.
- `--check-notify`는 알 수 없는 채널 값을 error로, 올바르지만 켜지지 않은 라우팅 대상을 warning으로 보고합니다.

## 통합 리포트 실패 격리

P5는 통합 리포트 알림 경로의 실패 경계를 강화했습니다. `_send_notifications()`는 report 라우팅 필터를 거친 뒤 정적 알림 채널마다 따로 보냅니다. 어떤 채널에서 예외가 나면 로그를 남기고 그 채널만 실패로 보며, 다음 채널을 건너뛰거나 분석 주 흐름을 멈추지 않습니다.

- 메일은 수신자 그룹마다 따로 격리합니다. 한 수신자 그룹이 실패해도 다음 그룹은 계속 보냅니다.
- 정적 채널 중 하나라도 발송에 성공하면 P4 소음 줄이기 reservation이 정식 기록으로 남고, 모든 정적 채널이 실패하거나 예외를 내면 reservation을 풉니다.
- `send_to_context()`는 여전히 정적 채널 route와 소음 줄이기 기록과 별개이며, 작업을 시작한 Bot 대화 맥락에 답장하는 데 쓰입니다.

#1390 P6의 의사결정 신호 요약도 같은 실패 격리 경계를 따릅니다. 분석 리포트 알림과 경고 알림에는 민감도 낮은 `decision_signal_summary` 요약(행동, 기간, 이유, 관찰 조건, 위험, 출처 리포트)만 덧붙이며, signal `metadata`, `evidence`, raw diagnostics, webhook/token은 내보내지 않습니다. 경고 알림 발송이 실패하면 알림 시도나 dispatch fallback만 기록하며, 이미 기록된 trigger나 DecisionSignal은 롤백하지 않습니다.

DecisionSignal 알림 요약 필드, 민감 정보 범위, 마이그레이션과 롤백 안내는 [DecisionSignal 의사결정 신호](decision-signals.md)를 보세요.

## 알림 소음 줄이기

P4는 프로세스 안에서 동작하는 소음 줄이기를 추가했습니다. 정적 설정 채널에만 영향을 주며, `send_to_context()`가 봇이 시작한 대화로 보내는 답장에는 영향을 주지 않습니다. 기본적으로 모든 설정이 꺼져 있으며, 설정하지 않으면 예전과 같습니다.

| 설정 key | 기본값 | 설명 |
| --- | --- | --- |
| `NOTIFICATION_DEDUP_TTL_SECONDS` | `0` | 같은 고정 중복 제거 key는 TTL 안에서 한 번만 보냄. `0`이면 끔 |
| `NOTIFICATION_COOLDOWN_SECONDS` | `0` | 같은 쿨다운 key는 구간 안에서 빈도를 제한. `0`이면 끔 |
| `NOTIFICATION_QUIET_HOURS` | 비어 있음 | 방해 금지 시간대. 형식은 `HH:MM-HH:MM`이며 자정을 넘겨도 됨 |
| `NOTIFICATION_TIMEZONE` | 비어 있음 | 방해 금지 시간대의 시간대. 예: `Asia/Shanghai`(한국은 `Asia/Seoul`). 비워 두면 Python 실행 환경의 로컬 시간대(보통 프로세스의 `TZ`나 시스템 시간대로 정해짐)를 씀 |
| `NOTIFICATION_MIN_SEVERITY` | 비어 있음 | `info`, `warning`, `error`, `critical`. 비워 두면 거르지 않음 |
| `NOTIFICATION_DAILY_DIGEST_ENABLED` | `false` | 예약된 설정. 현재 일일 요약을 보내거나 요약 내용을 저장하지 않음 |

심각도 기본값:

- `report`: `info`
- `alert`: `warning`
- `system_error`: `error`
- 알 수 없거나 설정하지 않은 라우팅: `info`

구현 범위:

- 중복 제거 / 쿨다운 상태는 현재 Python 프로세스 안의 dict이며, `main.py` 단일 프로세스와 `--serve` 단일 worker에 맞습니다.
- `uvicorn --workers N`, 여러 컨테이너, 여러 서버 환경에서는 상태를 공유하지 않으므로, 소음 줄이기는 worker마다 대략적으로만 적용됩니다.
- pipeline의 개별 종목과 통합 리포트 경로는 고정 key를 써서, 리포트 안의 생성 시각이 달라져 중복 제거가 무력해지는 일을 막습니다. `dedup_key`를 명시하지 않은 다른 report 알림은 내용 hash로 중복을 제거합니다.
- `cooldown_key`를 명시하지 않은 호출은 라우팅과 심각도별 기본 쿨다운 슬롯을 함께 씁니다. 예를 들어 report / info의 일반 알림은 같은 슬롯을 씁니다.
- 같은 프로세스에서 같은 key로 동시에 보내면 먼저 수명이 짧은 in-flight 슬롯을 차지해 갑작스러운 중복 발송을 막습니다. 정적 채널이 모두 실패하면 이 슬롯을 풀고, 정식 중복 제거 / 쿨다운 상태에는 기록하지 않습니다.
- 소음 줄이기 판단에서 예외가 나면 fail-open합니다. 로그를 남기고 정적 채널 발송을 계속합니다.
- `NOTIFICATION_TIMEZONE`을 비워 두면 `datetime.now().astimezone()`이 해석한 실행 환경의 로컬 시간대를 씁니다. Actions / Docker 환경에서는 시간대 혼동을 막으려면 `NOTIFICATION_TIMEZONE`을 명시하는 것이 좋습니다.

## WebPush / Apprise 검토

P6-D는 설계 검토만 했으며, 의존성, `.env` 설정, 실행 시 알림 경로를 추가하지 않았습니다. 결론은 둘 다 이번에 채널 구현 PR에 바로 섞기에는 맞지 않는다는 것입니다.

WebPush를 나중에 구현하려면 먼저 구독 수명 주기와 보안 범위를 따로 설계해야 합니다.

- 웹 프런트엔드에서 Service Worker를 등록해야 합니다. Service Worker / `PushManager.subscribe()`는 secure context가 필요하므로 운영 환경에서는 보통 HTTPS가 필수이며, 로컬 개발에서는 localhost를 쓸 수 있습니다.
- VAPID 공개 키/개인 키가 필요합니다. 구독할 때 public key를 내려 주고, 서버가 보낼 때 private key를 갖고 있어야 하며, 키 교체 방침도 잘 지켜야 합니다.
- 브라우저 권한 상호 작용이 필요합니다. 구독은 사용자 동작으로 시작되어야 하며, 백그라운드에서 조용히 켤 수 없습니다.
- `PushSubscription`에는 endpoint와 암호화 key가 들어 있습니다. endpoint는 capability URL이므로 secret으로 다루고 가려서 보여 줘야 합니다.
- 구독을 영구 저장하고, 구독 만료와 기기 해제를 처리해야 합니다. 현재의 `.env` / 단일 프로세스 설정 모델에는 여러 사용자/기기 구독을 바로 넣기 어렵습니다.
- 구독을 제출, 삭제, 갱신하는 API에는 인증과 CSRF 방어가 있어야 하며, 프런트엔드에서 진입점을 숨기는 것만으로는 안 됩니다.

Apprise를 나중에 도입한다면 기본 의존성이 아니라 선택 의존성으로 먼저 검토해야 합니다.

- Apprise는 범용 알림 라이브러리로 지원 범위가 넓지만, 이미 있는 WeChat, Telegram, Discord, Slack, ntfy, Gotify, Pushover 등의 정식 채널과 겹칩니다.
- 의존성 크기, 설치 실패 경로, Docker 이미지 증가, GitHub Actions 의존성 캐시, 선택 extras 방침을 검토해야 합니다.
- secret을 넘길 때 완전한 Apprise URL을 그대로 드러내면 안 됩니다. 가림 처리, 웹 테스트 대상 마스킹, 오류 로그 필터를 통일해야 합니다.
- 발송 실패는 Apprise 채널 안에서 격리해야 하며, 기존 채널의 실패 격리 의미에 영향을 주면 안 됩니다.
- Apprise를 쓰기로 한다면, 먼저 별도의 experimental channel이나 CLI 전용 시험 구현을 추가한 뒤 웹 설정 페이지와 Actions env에 넣을지 정하는 것을 권장합니다.

## 로컬 설정

로컬 실행에서는 프로젝트 루트의 `.env`를 우선 씁니다. `.env.example`을 복사한 뒤 minimal key를 하나 이상 채우면 해당 정적 알림 채널이 켜집니다. advanced key는 인증, 보안, 형식, 라우팅, 소음 줄이기 동작만 바꾸며, 혼자서 채널을 켜지 않습니다.

```bash
python main.py --check-notify
```

`--check-notify`는 읽기 전용 진단입니다. 알림을 보내지 않고, `.env`에 쓰지 않으며, 분석 흐름에 들어가지 않습니다. WebUI를 설정한 뒤에는 시스템 설정 페이지에서 채널별 테스트로 실제 테스트 메시지를 보낼 수도 있습니다. 이 테스트는 페이지 초안으로 만든 임시 설정만 쓰며 `.env`를 저장하지 않습니다.

## Docker

Docker에서는 `--env-file .env` / Compose `env_file`로 알림 관련 환경 변수를 넣을 수 있습니다. 호스트의 `.env` 파일 하나를 bind mount해서 컨테이너 안의 `/app/.env`를 덮어쓰지 마세요. 그러면 웹 설정 페이지가 설정을 저장할 때 Docker mount point 제약 때문에 원자적 교체나 권한 문제가 생길 수 있습니다. 새 버전 웹 설정 페이지는 사용 중인 `.env`에 일부 키가 없으면 시작할 때 주입된 같은 이름의 환경 변수를 대신 보여 줍니다. WebUI에서 저장한 알림 설정을 컨테이너를 다시 만든 뒤에도 유지하려면, `ENV_FILE`을 `/app/data/runtime.env`처럼 쓰기 가능한 데이터 볼륨의 파일로 지정하고, 시작 환경에 있는 같은 이름의 예전 값도 함께 고치거나 지워서 재시작할 때 덮어쓰이지 않게 하세요.

방해 금지 시간대를 쓴다면 `NOTIFICATION_TIMEZONE`을 명시하는 것이 좋습니다. 컨테이너 기본 시간대가 예상과 다를 수 있기 때문입니다. 자체 서명 인증서를 쓰는 내부망 webhook에는 임시로 `WEBHOOK_VERIFY_SSL=false`를 쓸 수 있지만, 인터넷 구간에서는 인증서 검증을 끄지 마세요.

## GitHub Actions

기본 `00-daily-analysis.yml`은 표에 명시적으로 매핑된 Secret / Variable만 읽습니다. repository Secret이나 Variable을 새로 추가해도, 변수 이름이 이미 workflow의 `env:`에 있어야만 실행 프로세스에 들어갑니다. `STOCK_GROUP_N` / `EMAIL_GROUP_N`처럼 번호가 임의로 붙는 변수는 자동으로 들어가지 않습니다.

Secret은 token, password, webhook URL 같은 민감한 항목에, Variable은 `WECHAT_MSG_TYPE`, `EMAIL_SENDER_NAME`, 라우팅, 소음 줄이기 구간, 시간대 같은 민감하지 않은 동작 설정에 맞습니다. `MARKDOWN_TO_IMAGE_CHANNELS`와 `MERGE_EMAIL_NOTIFICATION`은 기본으로 매핑되지 않으므로, 자신의 fork에서 쓰려면 workflow를 직접 고치고 관련 테스트를 추가해야 합니다.

## Desktop

데스크톱 앱은 웹 설정 페이지의 알림 설정과 채널별 테스트를 그대로 씁니다. 알림 테스트는 실제 테스트 메시지를 보내지만 현재 페이지의 초안 값만 쓰며 자동으로 저장하지 않습니다. 계속 쓰려면 설정 저장을 눌러야 합니다.

데스크톱 앱은 설정 내보내기 / 가져오기로 `.env`를 복원할 수 있습니다. 어떤 알림 채널을 되돌리려면 그 채널의 minimal key를 비우고 저장하면 됩니다. advanced key가 남아 있어도 혼자서 채널을 켜지는 않지만, 나중에 문제를 찾을 때 헷갈리지 않도록 함께 지우는 것이 좋습니다.

## 롤백 방법

- 로컬 / Docker: 예전 `.env`를 복원하거나, 해당 채널의 minimal key를 지운 뒤 프로세스를 다시 시작합니다.
- GitHub Actions: 해당 Secret / Variable을 비우거나 지웁니다. 매핑되지 않은 key는 workflow 실행 프로세스에 들어가지 않습니다.
- Desktop: 설정 백업으로 예전 `.env`를 가져오거나, 설정 페이지에서 해당 채널 설정을 비우고 저장합니다.
- 버전 되돌리기: P6/P7에서 추가한 `NTFY_*`, `GOTIFY_*`, 라우팅, 소음 줄이기 key는 예전 버전에서 무시됩니다. 오해를 피하려면 `.env`나 Actions 설정에서도 함께 지우세요.
