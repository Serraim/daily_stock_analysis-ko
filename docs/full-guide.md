# 📖 전체 설정 및 배포 가이드

이 문서는 A주 AI 분석 시스템의 전체 설정 설명을 담고 있으며, 고급 기능이나 특별한 배포 방식이 필요한 사용자를 위한 것입니다. (A주는 중국 본토 주식을 말하며, 이 포크에서는 한국 주식도 `.KS`/`.KQ` 접미사로 분석할 수 있습니다.)

> 💡 빠르게 시작하려면 [README.md](../README.md)를 보세요. 이 문서는 고급 설정용입니다.

<a id="-项目结构"></a>

## 📁 프로젝트 구조

```
daily_stock_analysis/
├── main.py              # 메인 프로그램 진입점
├── src/                 # 핵심 비즈니스 로직
│   ├── analyzer.py      # AI 분석기
│   ├── config.py        # 설정 관리
│   ├── notification.py  # 메시지 알림
│   └── ...
├── data_provider/       # 다중 데이터 소스 어댑터
├── bot/                 # 봇 상호 작용 모듈
├── api/                 # FastAPI 백엔드 서비스
├── apps/dsa-web/        # React 프런트엔드
├── docker/              # Docker 설정
├── docs/                # 프로젝트 문서
└── .github/workflows/   # GitHub Actions
```

## 📑 목차

- [프로젝트 구조](#-项目结构)
- [GitHub Actions 자세한 설정](#github-actions-详细配置)
- [전체 환경 변수 목록](#环境变量完整列表)
- [Docker 배포](#docker-部署)
- [로컬 실행 자세한 설정](#本地运行详细配置)
- [예약 실행 설정](#定时任务配置)
- [알림 채널 자세한 설정](#通知渠道详细配置)
- [데이터 소스 설정](#数据源配置)
- [고급 기능](#高级功能)
- [백테스트 기능](#回测功能)
- [로컬 WebUI 관리 화면](#本地-webui-管理界面)

---

<a id="github-actions-详细配置"></a>

## GitHub Actions 자세한 설정
<!-- 계약 키(tests): ### 通知 -->

### 1. 이 저장소 Fork하기

오른쪽 위의 `Fork` 버튼을 누릅니다.

### 2. Secrets 설정

Fork한 저장소 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`으로 들어갑니다.

<div align="center">
  <img src="assets/secret_config.png" alt="GitHub Secrets 설정 화면 예시" width="600">
</div>

#### AI 모델 설정(하나 이상 설정)

| Secret 이름 | 설명 | 필수 |
|------------|------|:----:|
| `MODELFLARE_KEY` | [Modelflare](https://modelflare.dev/sign-up?utm_source=github&utm_campaign=daily_stock_analysis) API Key. 기본 주소와 모델을 자동으로 채움 | 권장 |
| `AIHUBMIX_KEY` | [AIHubMix](https://inferera.com/?aff=CfMq) API Key. Key 하나로 모든 모델을 바꿔 가며 쓸 수 있으며, 이 프로젝트를 통하면 10% 할인 | 권장 |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/)에서 무료 Key 발급 | 선택 |
| `ANTHROPIC_API_KEY` | Anthropic Claude API Key | 선택 |
| `OPENAI_API_KEY` | OpenAI 호환 API Key(DeepSeek, 통이첸원(Qwen) 등 지원) | 선택 |
| `OPENAI_BASE_URL` | OpenAI 호환 API 주소(예: `https://api.deepseek.com`) | 선택 |
| `OPENAI_MODEL` | 모델 이름(예: `gemini-3.1-pro-preview`, `deepseek-v4-flash`, `gpt-5.5`) | 선택 |
| `ANSPIRE_API_KEYS` | Anspire 검색과 LLM이 함께 쓰는 Key의 legacy 호환 진입점. 모델 권한은 콘솔 기준 | 선택 |

> *참고: 위 모델 Key / 채널 가운데 하나 이상을 설정해야 합니다. Modelflare는 `MODELFLARE_KEY`만 넣으면 되며, 채널이 하나일 때 기본 모델은 `openai/gpt-6.1-sol`(`LITELLM_MODEL`로 바꿀 수 있음), 접속 주소는 기본으로 `https://modelflare.dev/v1`입니다. 전체 예시는 [LLM 설정 가이드](LLM_CONFIG_GUIDE.md#示例modelflare)를 보세요. 실제 모델은 계정 권한을 기준으로 합니다. 시작할 때 설정 검사에서 쓸 수 있는 AI 모델 Key나 모델 채널이 없으면 분명한 오류를 알려 줍니다.

#### 알림 채널 설정(여러 개를 동시에 설정하면 모두에게 발송)

> 알림 채널, minimal/advanced key 구분, Actions 매핑, `--check-notify` 진단, 웹 원클릭 테스트, 로컬 / Docker / GitHub Actions / Desktop 상황별 설명은 [알림 문서](notifications.md)를 보세요.

| Secret 이름 | 설명 | 필수 |
|------------|------|:----:|
| `WECHAT_WEBHOOK_URL` | WeCom(기업용 위챗) Webhook URL | 선택 |
| `FEISHU_WEBHOOK_URL` | Feishu(페이슈) Webhook URL | 선택 |
| `FEISHU_WEBHOOK_SECRET` | Feishu Webhook 서명 키("서명 검증"을 켰다면 필수) | 선택 |
| `FEISHU_WEBHOOK_KEYWORD` | Feishu Webhook 키워드("키워드"를 켰다면 필수) | 선택 |
| `DINGTALK_WEBHOOK_URL` | DingTalk(딩톡) 그룹 봇 Webhook URL | 선택 |
| `DINGTALK_SECRET` | DingTalk 그룹 봇 서명 키(SEC로 시작) | 선택 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token(@BotFather에서 발급) | 선택 |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 선택 |
| `TELEGRAM_MESSAGE_THREAD_ID` | Telegram Topic ID(하위 주제로 보낼 때 사용) | 선택 |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL([만드는 법](https://support.discord.com/hc/en-us/articles/228383668)) | 선택 |
| `DISCORD_BOT_TOKEN` | Discord Bot Token(Webhook과 둘 중 하나) | 선택 |
| `DISCORD_MAIN_CHANNEL_ID` | Discord Channel ID(Bot을 쓸 때 필요) | 선택 |
| `DISCORD_INTERACTIONS_PUBLIC_KEY` | Discord Public Key(들어오는 Interaction/Webhook 콜백 서명을 검증할 때만 필요) | 선택 |
| `SLACK_BOT_TOKEN` | Slack Bot Token(권장, 이미지 업로드 지원. 함께 설정하면 Webhook보다 우선) | 선택 |
| `SLACK_CHANNEL_ID` | Slack Channel ID(Bot을 쓸 때 필요) | 선택 |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL(텍스트만, 이미지 미지원) | 선택 |
| `EMAIL_SENDER` | 보내는 사람 메일 주소(예: `xxx@qq.com`) | 선택 |
| `EMAIL_PASSWORD` | 메일 인증 코드(로그인 비밀번호가 아님) | 선택 |
| `EMAIL_RECEIVERS` | 받는 사람 메일 주소(여러 개는 쉼표로 구분, 비워 두면 자신에게 발송) | 선택 |
| `EMAIL_SENDER_NAME` | 보내는 사람 표시 이름(기본값: daily_stock_analysis 주식 분석 도우미) | 선택 |
| `PUSHPLUS_TOKEN` | PushPlus Token([발급 주소](https://www.pushplus.plus), 중국 내 푸시 서비스) | 선택 |
| `SERVERCHAN3_SENDKEY` | Server酱³(ServerChan3) Sendkey([발급 주소](https://sc3.ft07.com/), 휴대폰 앱 푸시 서비스) | 선택 |
| `ASTRBOT_URL` | AstrBot Webhook URL | 선택 |
| `ASTRBOT_TOKEN` | AstrBot Bearer Token(선택) | 선택 |
| `NTFY_URL` | ntfy 전체 topic endpoint. 반드시 topic 경로 포함. 예: `https://ntfy.sh/my-topic` | 선택 |
| `NTFY_TOKEN` | ntfy Bearer Token(선택) | 선택 |
| `GOTIFY_URL` | Gotify 서버 base URL. `/message`는 넣지 않으며 시스템이 자동으로 붙임 | 선택 |
| `GOTIFY_TOKEN` | Gotify application token. `X-Gotify-Key` Header로 보냄 | 선택 |
| `CUSTOM_WEBHOOK_URLS` | 사용자 정의 Webhook(DingTalk 등 지원, 여러 개는 쉼표로 구분) | 선택 |
| `CUSTOM_WEBHOOK_BEARER_TOKEN` | 사용자 정의 Webhook의 Bearer Token(인증이 필요한 Webhook용) | 선택 |
| `CUSTOM_WEBHOOK_BODY_TEMPLATE` | 사용자 정의 Webhook JSON body 템플릿. AstrBot, NapCat, 자체 서비스 등 특수한 payload에 맞출 때 사용 | 선택 |
| `WEBHOOK_VERIFY_SSL` | 이 설정을 읽는 webhook 계열 HTTPS 알림 요청의 인증서 검증(기본 true). false로 두면 자체 서명 인증서를 쓸 수 있음. 경고: 끄면 심각한 보안 위험(MITM)이 있으므로 믿을 수 있는 내부망에서만 쓸 것 | 선택 |

> *참고: 채널을 하나 이상 설정해야 하며, 여러 개를 설정하면 모두에게 동시에 보냅니다. 시작할 때 설정 검사가 Telegram / 메일의 짝 필드 누락과, 흔한 Webhook URL이 `http://`나 `https://`로 시작하지 않는 문제를 알려 줍니다.
>
> 현재 기본 `00-daily-analysis.yml`은 정해진 Secret / Variable 이름만 명시적으로 매핑하며, `STOCK_GROUP_1`, `EMAIL_GROUP_1`처럼 번호가 임의로 붙는 변수나 `NEWS_INTEL_AUTO_FETCH_ENABLED` 같은 새 선택 스위치를 실행 환경에 자동으로 넣지 않습니다. 그래서 메일 그룹 기능과 로컬 뉴스 자동 새로 고침 기능은 지금 저장소에 들어 있는 기본 GitHub Actions workflow에는 적용되지 않으며, 로컬 `.env`, Docker, 또는 `env:` 매핑을 직접 늘린 실행 환경에서만 쓸 수 있습니다. Actions는 `CUSTOM_WEBHOOK_BODY_TEMPLATE`, `WEBHOOK_VERIFY_SSL`, `FEISHU_WEBHOOK_SECRET`, `FEISHU_WEBHOOK_KEYWORD`, `PUSHPLUS_TOPIC`, `NTFY_URL`, `NTFY_TOKEN`, `GOTIFY_URL`, `GOTIFY_TOKEN`, P3 알림 라우팅 키, P4 알림 소음 줄이기 키를 명시적으로 매핑했습니다. `MARKDOWN_TO_IMAGE_CHANNELS`와 `MERGE_EMAIL_NOTIFICATION`은 여전히 동작 스위치이므로 기본 workflow에서 자동으로 매핑하지 않습니다.

#### 알림 동작 설정

| Secret 이름 | 설명 | 필수 |
|------------|------|:----:|
| `SINGLE_STOCK_NOTIFY` | 종목별 알림 모드: `true`로 두면 종목 하나를 분석할 때마다 바로 보냄 | 선택 |
| `REPORT_TYPE` | 리포트 유형: `simple`(간단), `full`(전체), `brief`(3-5문장 요약). Docker 환경에서는 `full` 권장 | 선택 |
| `REPORT_LANGUAGE` | 리포트와 Agent Chat의 기본 출력 언어: `zh`(기본, 중국어) / `en`(영어) / `ko`(한국어). Prompt, 템플릿, 알림 fallback, 웹 리포트 페이지의 고정 문구, `context.report_language`를 명시하지 않은 종목 질문 답변에도 함께 적용됨. `ko`는 영어 구조 뼈대를 재사용하고 출력 언어 지시로 모델이 한국어로 답하게 하며, 알림은 리포트 언어에 맞춰 현지화된 이름표로 렌더링함. 저장소의 `00-daily-analysis.yml`이 이 변수를 명시적으로 매핑하므로 Actions Secrets/Variables에 설정하면 바로 적용됨 | 선택 |
| `REPORT_SUMMARY_ONLY` | 분석 결과 요약만: `true`이면 개별 종목 상세 없이 요약만 보냄. 종목이 많을 때 빠르게 훑어보기 좋음(기본 false, Issue #262) | 선택 |
| `REPORT_SHOW_LLM_MODEL` | 알림 리포트 아래쪽에 이번 분석에 쓴 LLM 모델 이름을 보여 줄지 여부. 기본 `true`, `false`로 두면 실행 모델 정보를 숨김. 이 변수는 표시만 바꾸며, provider/model/Base URL, LiteLLM 라우팅, 실행 모델 저장/마이그레이션/정리 의미에는 영향이 없음. | 선택 |
| `REPORT_TEMPLATES_DIR` | Jinja2 템플릿 디렉터리(프로젝트 루트 기준 상대 경로, 기본 `templates`) | 선택 |
| `REPORT_RENDERER_ENABLED` | Jinja2 템플릿 렌더링 사용(기본 `false`, 회귀가 없도록 보장) | 선택 |
| `REPORT_INTEGRITY_ENABLED` | 리포트 완전성 검사 사용. 필수 필드가 없으면 재시도하거나 자리 표시자로 채움(기본 `true`) | 선택 |
| `REPORT_INTEGRITY_RETRY` | 완전성 검사 재시도 횟수(기본 `1`, `0`이면 재시도 없이 자리 표시자만) | 선택 |
| `REPORT_HISTORY_COMPARE_N` | 과거 신호 비교 개수. `0`이면 끔(기본), `>0`이면 사용 | 선택 |
| `ANALYSIS_DELAY` | 개별 종목 분석과 시장 분석 사이의 지연(초). API 요청 제한을 피하기 위함. 예: `10` | 선택 |
| `SAVE_CONTEXT_SNAPSHOT` | 분석 이력의 `context_snapshot` 저장 여부. 기본 `true`. `false`로 두거나 `--no-context-snapshot`을 쓰면 전체 맥락 스냅샷을 저장하지 않음 | 선택 |
| `MERGE_EMAIL_NOTIFICATION` | 개별 종목과 시장 복기를 합쳐서 보냄(기본 false). 메일 수를 줄여 스팸 처리 위험을 낮춤. `SINGLE_STOCK_NOTIFY`와 함께 쓸 수 없음(종목별 모드에서는 합치기가 적용되지 않음) | 선택 |
| `MARKDOWN_TO_IMAGE_CHANNELS` | Markdown을 이미지로 바꿔 보낼 채널(쉼표로 구분): telegram,wechat,custom,email,slack. 종목별 알림에서 쓰려면 함께 설정하고 이미지 변환 도구를 설치해야 함 | 선택 |
| `NOTIFICATION_REPORT_CHANNELS` | report 라우팅 채널(종목별 알림, 통합 일일 리포트, 시장 복기, 합친 알림 등). 비워 두면 설정된 모든 채널 | 선택 |
| `NOTIFICATION_ALERT_CHANNELS` | alert 라우팅 채널(EventMonitor 경고). 비워 두면 설정된 모든 채널 | 선택 |
| `NOTIFICATION_SYSTEM_ERROR_CHANNELS` | system_error 예약 라우팅 채널. 현재 자동 시스템 오류 발생원은 추가하지 않으며, 비워 두면 설정된 모든 채널 | 선택 |
| `NOTIFICATION_DEDUP_TTL_SECONDS` | 알림 중복 제거 TTL(초). `0`이면 끔. 같은 고정 중복 제거 key는 TTL 안에서 한 번만 보냄 | 선택 |
| `NOTIFICATION_COOLDOWN_SECONDS` | 알림 쿨다운(초). `0`이면 끔. 같은 쿨다운 key는 구간 안에서 빈도를 제한 | 선택 |
| `NOTIFICATION_QUIET_HOURS` | 알림 방해 금지 시간대. 형식 `HH:MM-HH:MM`, 자정을 넘겨도 됨. 비워 두면 끔 | 선택 |
| `NOTIFICATION_TIMEZONE` | 방해 금지 시간대에 쓰는 IANA 시간대. 예: `Asia/Shanghai`(한국은 `Asia/Seoul`). 비워 두면 `TZ`나 시스템 로컬 시간대를 따름 | 선택 |
| `NOTIFICATION_MIN_SEVERITY` | 최소 알림 수준: `info`, `warning`, `error`, `critical`. 비워 두면 현재 동작 유지 | 선택 |
| `NOTIFICATION_DAILY_DIGEST_ENABLED` | 일일 요약 예약 스위치. 현재는 요약을 보내거나 요약 내용을 저장하지 않음 | 선택 |
| `MARKDOWN_TO_IMAGE_MAX_CHARS` | 이 길이를 넘으면 이미지로 바꾸지 않음. 지나치게 큰 이미지를 막기 위함(기본 15000) | 선택 |
| `MD2IMG_ENGINE` | 이미지 변환 엔진: `wkhtmltoimage`(기본), `markdown-to-file`, `playwright`(웹 의존성과 Chromium 설치 필요) | 선택 |
| `SHARE_IMAGE_XIAOHONGSHU_URL` | 공유 이미지의 샤오훙수(小红书) 홈 URL. 비워 두면 링크를 표시하지 않을 수 있음 | 선택 |
| `SHARE_IMAGE_XIAOHONGSHU_HANDLE` | 공유 이미지의 샤오훙수 닉네임. 샤오훙수 설정을 모두 비워 두면 내장 닉네임 `@霸天土小豆`를 표시 | 선택 |
| `SHARE_IMAGE_XIAOHONGSHU_QR_PATH` | 공유 이미지의 샤오훙수 QR 코드 파일 경로. 절대 경로나 프로젝트 루트 기준 상대 경로를 쓸 수 있으며, 샤오훙수 설정을 모두 비워 두면 저장소에 내장된 QR 코드를 씀 | 선택 |
| `PREFETCH_REALTIME_QUOTES` | `false`로 두면 실시간 시세 미리 가져오기를 끄고, efinance/akshare_em의 전체 시장 조회를 피함(기본 true) | 선택 |

> 호환성 안내: `REPORT_SHOW_LLM_MODEL`은 기본값 `true`의 원래 표시 의미를 유지하며, 끄면 아래쪽 모델 문구 출력에만 영향을 줍니다. 이 설정은 provider/model/Base URL, LiteLLM 라우팅, 모델 저장, 마이그레이션, 정리 의미를 바꾸지 않습니다. 되돌리려면 이 변수를 복원하거나 지우고 `true`로 둡니다.

> 안내: `REPORT_LANGUAGE`는 리포트 텍스트, 웹 리포트 페이지의 고정 문구, 언어를 명시하지 않은 Agent Chat 답변에 영향을 줍니다. WebUI 화면 언어(내비게이션, 로그인 페이지, 사이드바, 설정 페이지, 공통 컨트롤)는 별도의 상태를 쓰며 이 값과 연동되지 않습니다.
> WebUI 언어 상태는 브라우저 `localStorage`의 `dsa.uiLanguage`에 저장되며, 시작 시 다음 순서로 정해집니다.
> 1) 명시적 선택(`localStorage.dsa.uiLanguage`, `zh`/`en`만 지원)
> 2) 브라우저 언어 감지(`navigator.languages` / `navigator.language`, `zh-*` 또는 `en-*`)
> 3) 기본값 `zh`로 돌아감.

<a id="其他配置"></a>

#### 기타 설정

| Secret 이름 | 설명 | 필수 |
|------------|------|:----:|
| `STOCK_LIST` | 관심 종목 코드. 예: `600519,300750,002594,7203.T,005930.KS`(한국 주식은 `005930.KS`처럼 `.KS`/`.KQ`를 붙임). 영문 쉼표를 권장하며, 중국어 쉼표·모점(、)·세미콜론·공백·줄바꿈도 인식해 영문 쉼표로 정리함 | ✅ |
| `ANSPIRE_API_KEYS` | [Anspire AI Search](https://aisearch.anspire.cn/)는 중국어 콘텐츠에 특히 최적화됨. 같은 Key를 검색과 Anspire LLM 게이트웨이의 대체 예시로 쓸 수 있음(사용 가능 여부는 콘솔과 계정 권한 기준) | 권장 |
| `SERPAPI_API_KEYS` | [SerpAPI](https://serpapi.com/github-daily-stock-analysis) 검색 엔진 결과 보강. 실시간 금융 뉴스에 적합 | 권장 |
| `TAVILY_API_KEYS` | [Tavily](https://tavily.com/) 검색 API(뉴스 검색) | 선택 |
| `BOCHA_API_KEYS` | [Bocha(博查) 검색](https://open.bocha.cn/) Web Search API(중국어 검색 최적화, AI 요약 지원, 여러 key는 쉼표로 구분) | 선택 |
| `BRAVE_API_KEYS` | [Brave Search](https://brave.com/search/api/) API(개인정보 우선, 미국 주식 최적화, 여러 key는 쉼표로 구분) | 선택 |
| `MINIMAX_API_KEYS` | [MiniMax](https://platform.minimax.io/) Coding Plan Web Search(구조화된 검색 결과) | 선택 |
| `SEARXNG_BASE_URLS` | SearXNG 자체 호스팅 인스턴스(할당량 없는 대체 수단, settings.yml에서 format: json을 켜야 함). 비워 두면 공개 인스턴스 찾기를 명시적으로 켰을 때만 `searx.space`를 씀 | 선택 |
| `SEARXNG_PUBLIC_INSTANCES_ENABLED` | `SEARXNG_BASE_URLS`가 비어 있을 때 `searx.space`에서 공개 인스턴스를 자동으로 가져올지 여부(기본 `false`). 공개 인스턴스는 대부분 요청 제한이 있거나 JSON 출력을 켜지 않아서, 켜면 분석마다 30~60초가 더 걸리고 뉴스가 비어 있을 수 있음 | 선택 |
| `SEARXNG_TIMEOUT_SECONDS` | 자체 호스팅 SearXNG의 검색 1회 시간 초과(초, 기본 `10`, 최소 `1`). 인스턴스가 느리면(엔진을 많이 묶은 NAS 배포 등) 늘릴 수 있으며, 공개 인스턴스의 시간 초과에는 영향이 없음. GitHub Actions에서는 이 변수를 명시적으로 매핑해야 함 | 선택 |
| `TUSHARE_TOKEN` | [Tushare Pro](https://tushare.pro/weborder/#/login?reg=834638 ) Token | 선택 |
| `TUSHARE_HTTP_URL` | Tushare Pro HTTP 접속 주소. 비워 두거나(설정하지 않거나 공백) 하면 공식 endpoint `http://api.tushare.pro`를 씀. 회사 내부망 프록시, 국경 간 네트워크, 자체 미러를 거쳐야 할 때만 `http://`나 `https://`로 시작하는 전체 주소를 넣음 | 선택 |
| `TICKFLOW_API_KEY` | [TickFlow](https://tickflow.org) API Key. 선택이며, A주 일봉, 실시간 시세, 종목 목록/이름, 시장 복기 강화에 쓰임. 실패하거나 권한이 부족하면 자동으로 대체 소스로 돌아감. | 선택 |
| `MX_APIKEY` / `MX_PRIORITY` | Miaoxiang(妙想, 둥팡차이푸 MX_API) 보조 데이터 소스: 둥팡차이푸 공개 API가 실패하거나 요청 제한에 걸릴 때 매물대(보유 원가 분포)와 개별 종목 자금 흐름을 대신 가져옴. **명시적으로 켜야 하는 서드파티 기능**: 사용자가 직접 Key를 준비해야 하며(Miaoxiang Skills 페이지), 기간 한정 무료/회원 할당량 정책은 바뀔 수 있어 계속 무료라고 약속하지 않음. 설정하지 않으면 켜지지 않고 동작도 바뀌지 않음. `MX_PRIORITY` 기본값 `6`. GitHub Actions에서는 Secrets에 `MX_APIKEY`를 설정해야 함 | 선택 |
| `LONGBRIDGE_OAUTH_CLIENT_ID` | [Longbridge OpenAPI](https://open.longbridge.com/) OAuth client_id. 비워 두고 Legacy Access Token도 없으면 `LONGBRIDGE_APP_KEY`를 호환용으로 씀 | 선택 |
| `LONGBRIDGE_OAUTH_TOKEN_CACHE_B64` | OAuth token 캐시 파일의 base64 내용. GitHub Actions / Docker 같은 headless 환경에서 SDK token 캐시를 복원할 때 씀 | 선택 |
| `LONGBRIDGE_APP_KEY` | Longbridge Legacy App Key. `LONGBRIDGE_ACCESS_TOKEN`이 없으면 OAuth client_id의 호환 별칭으로도 쓸 수 있음 | 선택 |
| `LONGBRIDGE_APP_SECRET` | Longbridge App Secret | 선택 |
| `LONGBRIDGE_ACCESS_TOKEN` | Longbridge Legacy Access Token(OAuth access token이 아님) | 선택 |
| `LONGBRIDGE_STATIC_INFO_TTL_SECONDS` | Longbridge `static_info` 프로세스 내 캐시 시간(초, 기본 86400, 0=캐시 안 함) | 선택 |
| `LONGBRIDGE_CONNECTION_COOLDOWN_SECONDS` | Longbridge 연결 종료 계열 예외가 난 뒤의 대기 시간(초, 기본 15. 대기 중에는 Longbridge를 잠시 건너뛰어 잦은 재연결을 막음) | 선택 |
| `LONGBRIDGE_HTTP_URL` | HTTP API 주소(기본 `https://openapi.longbridge.com`) | 선택 |
| `LONGBRIDGE_QUOTE_WS_URL` | 시세 WebSocket 주소(기본 `wss://openapi-quote.longbridge.com/v2`) | 선택 |
| `LONGBRIDGE_TRADE_WS_URL` | 거래 WebSocket 주소(기본 `wss://openapi-trade.longbridge.com/v2`) | 선택 |
| `LONGBRIDGE_REGION` | 접속 지점 지정. SDK가 네트워크에 따라 자동으로 고르며 기본 `hk`. 잘못 판단하면 설정할 수 있음(예: `cn`, `hk`) | 선택 |
| `LONGBRIDGE_ENABLE_OVERNIGHT` | 야간 거래 시세 사용 여부 `true` / `false`, 기본 `false` | 선택 |
| `LONGBRIDGE_PUSH_CANDLESTICK_MODE` | 캔들 푸시 모드: `realtime` 또는 `confirmed`(기본 `realtime`) | 선택 |
| `LONGBRIDGE_PRINT_QUOTE_PACKAGES` | 연결할 때 시세 패키지를 출력할지 여부(설정하지 않으면 기본 `false`, `1`/`true`/`yes`로 켬) | 선택 |
| `ENABLE_CHIP_DISTRIBUTION` | 매물대(보유 원가 분포) 사용(Actions 기본 false. 매물대 데이터가 필요하면 Variables에서 true로 설정. API가 불안정할 수 있음) | 선택 |

Miaoxiang 매물대/자금 흐름은 같은 프로세스 안에서 네트워크 요청 진입 잠금을 함께 씁니다. 조회 메서드에 들어갈 때 아직 끝나지 않은 요청이 있으면 새 조회는 바로 건너뛰며, 이 잠금에서 줄을 서지 않습니다. 자금 흐름 보조 조회의 시간 초과 격리는 실제 백그라운드 요청이 끝날 때까지 유지되고, 다른 데이터 소스로는 여전히 돌아갈 수 있습니다. 이미 보낸 요청을 취소하지 않으며, 관리자가 원래 하던 매물대 호출 직렬화도 바꾸지 않습니다. 이 보조 소스는 기능 검사로 모든 일봉 요청에서 빠지며, 표를 고르고 해석할 때 사전/리스트 형식의 `nameMap`을 모두 지원합니다.

Miaoxiang 자금 흐름은 명확한 주력 순유입 금액 지표만 씁니다. 종가, 비율, 빠진 금액은 자금 흐름의 대체 값으로 쓰지 않습니다. 최신 거래일 금액이 없으면 알 수 없음으로 두고, 5/10일 구간에 빠진 금액이 있으면 합계를 내지 않으며, 더 이전 날짜로 채우지 않습니다.

> **GitHub Actions:** 저장소에 들어 있는 `00-daily-analysis.yml`은 `TUSHARE_TOKEN`, `TICKFLOW_API_KEY` / `TICKFLOW_*`, 위 표의 `LONGBRIDGE_*`를 작업 환경에 매핑했습니다. TickFlow API Key는 **Secrets**에 두는 것을 권장하며, 우선순위, 수정주가, 일괄 스위치는 **Variables**나 **Secrets**에 둘 수 있습니다. Longbridge OAuth 방식은 client_id 하나가 필요합니다(`LONGBRIDGE_OAUTH_CLIENT_ID` 우선. 비워 두고 Legacy Access Token도 없으면 `LONGBRIDGE_APP_KEY`를 호환용으로 씀). 그리고 로컬의 `~/.longbridge/openapi/tokens/<client_id>` 파일을 base64로 바꿔 Secret `LONGBRIDGE_OAUTH_TOKEN_CACHE_B64`에 저장합니다. Legacy 방식은 여전히 `LONGBRIDGE_APP_KEY`, `LONGBRIDGE_APP_SECRET`, `LONGBRIDGE_ACCESS_TOKEN`으로 설정할 수 있습니다. 선택 사항인 접속 지점 변수(예: `LONGBRIDGE_REGION`)는 **Variables**나 **Secrets**에 둘 수 있습니다.

> **일일 workflow의 TUSHARE_HTTP_URL 매핑:** `00-daily-analysis.yml`은 `TUSHARE_HTTP_URL`을 명시적으로 매핑했습니다(`vars.TUSHARE_HTTP_URL || secrets.TUSHARE_HTTP_URL` 우선순위를 쓰며, 저장소의 `TICKFLOW_PRIORITY` 같은 민감하지 않은 설정을 읽는 방식과 같음). 이 주소는 자격 증명이 아니라 "접속 주소" 설정이므로, 팀 검토와 버전 감사가 쉽도록 **Variables**에 두는 것을 권장합니다. 주의: 실제 우선순위는 `vars`가 비어 있지 않으면 이기는 방식이라서, **Secrets의 같은 이름 변수는 비어 있지 않은 Variables를 덮어쓸 수 없습니다**. vars가 비어 있을 때만 secrets를 씁니다. 보안을 설계할 때 이 실제 동작을 기준으로 하세요. GitHub는 Variables와 Secrets를 서로 독립된 쓰기 권한 모델로 설계했습니다. repository Variables에 쓰기 권한이 있는 사람이나 자동화는 Secrets를 읽거나 고치지 않고도, 비어 있지 않은 Variable 하나를 설정해 실행 시 endpoint를 바꿀 수 있습니다(`TUSHARE_TOKEN`과 요청 본문 전체를 공격자가 통제하는 주소로 보내는 것 포함). Secrets는 값의 기밀성만 보호하며, "endpoint 무결성"이나 "우선순위 덮어쓰기"를 자동으로 보장하지 않습니다. endpoint에 더 강한 접근 통제가 필요하면 GitHub Environment protection rules, CODEOWNERS, branch protection, 별도의 배포 승인 절차를 쓰세요. **"Secrets에만 두고 Variables는 비워 두기"를 변경 방지 장치로 여기지 마세요**. 설정하지 않거나 비워 두면 fetcher는 계속 공식 `http://api.tushare.pro` endpoint를 쓰며, 이 변수가 없다고 오류가 나지 않습니다.

> **Longbridge 실행 동작:** 자격 증명을 설정하지 않으면 선택 fetcher인 Longbridge를 만들지 않습니다. 실행 중 `client is closed`, `context closed`, `connection closed` 같은 연결 종료 계열 예외를 만나면 대기 상태에 들어가며(기본 15초, `LONGBRIDGE_CONNECTION_COOLDOWN_SECONDS`로 조정), 대기 중에는 미국/홍콩 주식의 실시간·일봉 요청이 Longbridge를 자동으로 건너뛰고 YFinance / AkShare 등의 대체 경로로 돌아갑니다.

> 보충 설명
- TUSHARE_TOKEN을 설정했지만 홍콩 주식 일봉 API 권한이 없으면, 홍콩 주식 데이터를 조회하지 못하거나 잘못 나올 수 있습니다. 예전 버전에서 홍콩 주식을 지원하지 않는다고 안내하던 것과 같은 결과입니다.

#### ✅ 최소 설정 예시

빨리 시작하고 싶다면 최소한 다음을 설정하면 됩니다.

1. **AI 모델**: [Modelflare Channels 예시](LLM_CONFIG_GUIDE.md#示例modelflare)대로 설정하거나, `AIHUBMIX_KEY`([AIHubmix](https://inferera.com/?aff=CfMq), Key 하나로 여러 모델), `GEMINI_API_KEY`, `OPENAI_API_KEY`를 씁니다
2. **알림 채널**: 하나 이상 설정합니다. 예: `WECHAT_WEBHOOK_URL` 또는 `EMAIL_SENDER` + `EMAIL_PASSWORD`
3. **종목 목록**: `STOCK_LIST`(필수)
4. **검색 API**: `ANSPIRE_API_KEYS` 또는 `SERPAPI_API_KEYS`(권장, 뉴스와 여론 검색에 사용)

> 💡 위 4가지만 설정하면 바로 쓸 수 있습니다!

### 3. Actions 켜기

1. Fork한 저장소로 들어갑니다
2. 위쪽의 `Actions` 탭을 누릅니다
3. 안내가 보이면 `I understand my workflows, go ahead and enable them`을 누릅니다

### 4. 직접 테스트

1. `Actions` 탭으로 들어갑니다
2. 왼쪽에서 `每日股票分析`(일일 주식 분석) workflow를 고릅니다
3. 오른쪽의 `Run workflow` 버튼을 누릅니다
4. 실행 모드를 고릅니다
5. 초록색 `Run workflow`를 눌러 확인합니다

### 5. 완료!

기본으로 평일마다 **18:00(베이징 시간, 한국 시간 19:00)**에 자동으로 실행됩니다.

---

<a id="环境变量完整列表"></a>

## 전체 환경 변수 목록

<a id="ai-模型配置"></a>

### AI 모델 설정

> 자세한 설명은 [LLM 설정 가이드](LLM_CONFIG_GUIDE.md)(3단계 설정, 채널 모드, Vision, Agent, 문제 해결)를, 자주 쓰는 서비스 제공자 프리셋, Actions 변수 대조, 오류 해결은 [LLM 서비스 제공자 설정 가이드](llm-providers.md)를 보세요.
> 호환성 안내(Issue #1306/#1391, 덧붙여 #1381 확인): 이 절과 관련된 변경은 기존 이력 기록 경로를 재사용해 시장 복기 결과를 보여 줄 뿐이며, API/API 매개변수, 웹의 단계별 결과 별도 표시, 일일 리포트 4단계 구조화 저장, 일일 리포트 상태 표를 추가하지 않고, `provider` / `model` / `base_url` 실행 라우팅과 기본 모델 동작도 바꾸지 않습니다. #1381도 백엔드 runtime 재사용일 뿐이며, 설정 마이그레이션/정리/되쓰기 분기를 추가하지 않습니다. Issue #1381의 API/웹/일일 리포트 구조화 인수 조건이 함께 반영되지 않았다면 이 PR을 완전한 마무리로 볼 수 없으며, 이후 PR에서 계속 제공해야 합니다. 되돌리는 방법은 배포 롤백입니다(현재 커밋을 바로 revert하거나, 기존 설정 되돌리기 경로를 따름). 호환성 검증은 기존 제약 검사(`requirements.txt`의 `litellm` 버전 제약)와 기존 설정 회귀 테스트 `tests/test_system_config_service.py`, `tests/test_system_config_api.py`, `tests/test_llm_channel_config.py`, `tests/test_market_review_runtime.py`를 주로 씁니다. 공식 참고 자료: [LiteLLM OpenAI-compatible](https://docs.litellm.ai/docs/providers/openai_compatible), [OpenAI Chat Completion API](https://platform.openai.com/docs/api-reference/chat).
> #1391 Phase 2의 구조화 검사 위험은 `src/agent/factory.py`의 `agent_max_steps` / `agent_orchestrator_timeout_s` 정수 안전 보정에서 나온 것으로, 설정 읽기 쪽의 타입 호환 강화이며 `litellm_model`, `agent_litellm_model`, `openai_base_url`, `LLM_*` 라우팅 상태를 고쳐 쓰지 않습니다. 회귀는 `tests/test_agent_pipeline.py::TestAgentConfig::test_build_agent_executor_does_not_mutate_llm_route_config`와 `tests/test_agent_pipeline.py::TestAgentConfig::test_build_agent_executor_multi_arch_does_not_mutate_llm_route_config`로 다시 확인할 수 있습니다. 설정 값이 잘못되면(숫자가 아닌 값 등) `src.agent.factory`가 warning을 남기고 기본값으로 돌아가므로, 문제를 찾기 쉽고 설정이 적용되었다고 잘못 판단하는 일을 막습니다.
> #1815 Phase 3의 호환 범위 안내: 이번에는 일본/한국과 Market Light의 서비스 범위만 정리했으며, LLM provider/model/base_url 마이그레이션 로직을 추가하지 않고 `.env` 주 라우팅 모델의 저장 의미도 바꾸지 않습니다. `MarketSymbol`, 경고 열거형, 스냅샷 `data_quality/limitations` 조정은 기존 `.env` 원자적 upsert 의미대로 저장 설정에 기록되며, 명시적으로 제출하지 않은 키는 지워지지 않습니다.
> 이 절은 모델/채널 설정 목록만 맞추며, 새로운 외부 provider / Base URL 호환 약속을 추가하지 않습니다. 호환 의미는 현재 저장소의 `requirements.txt` 의존성 제약과 관련 테스트를 기준으로 하며, 과거 되돌리기 경로는 위 두 문서의 "되돌리기/복원" 설명을 보세요.

| 변수 이름 | 설명 | 기본값 | 필수 |
|--------|------|--------|:----:|
| `GENERATION_BACKEND` | 일반 분석 생성 backend. `litellm` 또는 명시적으로 켜는 `codex_cli` / `claude_code_cli` / `opencode_cli`(experimental/limited) 지원 | `litellm` | 아니오 |
| `OPENCODE_CLI_MODEL` | `GENERATION_BACKEND=opencode_cli`일 때 OpenCode `--model`에 넘길 선택적 모델. 비워 두면 로컬 OpenCode 기본 모델을 쓰며, 인증과 모델 사용 가능 여부는 로컬 OpenCode 설정이 맡음 | 비어 있음 | 아니오 |
| `GENERATION_FALLBACK_BACKEND` | backend 단위 fallback. 설정하지 않으면 기본 `litellm`, 빈 값이면 끔, 자기 자신으로 fallback하면 no-op으로 해석 | `litellm` | 아니오 |
| `GENERATION_BACKEND_TIMEOUT_SECONDS` | generation backend 호출 1회의 시간 초과(초). 주로 로컬 CLI backend용. 범위 `1-3600` | `300` | 아니오 |
| `GENERATION_BACKEND_MAX_OUTPUT_BYTES` | 로컬 CLI backend 호출 1회에서 진단용 stdout/stderr와 최종 응답을 받는 총 상한. `--output-last-message`가 stdout에 다시 출력한 최종 응답은 중복으로 세지 않음. 범위 `1-33554432` | `1048576` | 아니오 |
| `GENERATION_BACKEND_MAX_CONCURRENCY` | generation backend 전체 동시 실행 상한. 범위 `1-16`. LiteLLM Router / `MAX_WORKERS` 동작은 바꾸지 않음 | `1` | 아니오 |
| `LOCAL_CLI_BACKEND_MAX_CONCURRENCY` | 로컬 CLI backend 동시 실행 상한. 범위 `1-4`. 실제 동시 실행 수는 이 값과 `GENERATION_BACKEND_MAX_CONCURRENCY` 중 작은 값 | `1` | 아니오 |
| `AGENT_BACKEND` | 종목 질문(问股) Chat 실행 방식: `auto`(권장, 기본 LiteLLM 유지) 또는 `litellm` | `auto` | 아니오 |
| `AGENT_GENERATION_BACKEND` | Agent Chat 생성 backend. 웹 설정 페이지는 `auto|litellm`만 보여 주며, local CLI backend를 직접 써 넣으면 tool-calling 미지원 진단을 돌려줌 | `auto` | 아니오 |
| `AGENT_SKILL_CONCURRENCY` | `specialist` 모드 전략 전문가 worker 동시 실행 상한, 범위 `1-4`. 전략은 최대 4개까지 고를 수 있고 기본으로 3개를 동시에 실행하며, 4번째는 다음 묶음으로 넘어가 전체 시간 초과 예산을 함께 씀 | `3` | 아니오 |
| `AGENT_DATA_TOOL_TIMEOUT_S` | Agent `data` 계열 도구의 기본 시간 초과(초). `market` 계열 도구(`get_market_indices` / `get_sector_rankings` 등 네트워크 데이터 호출)의 계열 기본값으로도 쓰임. `0`이면 끄고 전체 예산으로 돌아감. 실제 시간 초과는 먼저 정해진 것이 이기는(first-wins) 방식으로 해석함: 실행별로 명시한 `tool_call_timeout_seconds` > 도구별로 명시한 `timeout_seconds` > 계열 기본값 > 제한 없음. 남은 wall-clock 예산은 넘을 수 없는 바깥 상한으로만 쓰이며, `inf`/`nan`/음수는 「제한 없음」으로 낮춤. 시간 초과는 best-effort 소프트 중단임: Python 스레드는 강제로 멈출 수 없어 handler가 시간 초과 뒤에도 계속 실행될 수 있음. 시간 초과 결과는 `retriable: false`로 표시하고 `non_retriable_tool_results`에 기록해 재시도를 막으며, 아직 백그라운드에서 도는 handler에는 협조적 취소 신호를 걸어(`is_tool_cancellation_requested()`와 기존 `check_tool_execution()` 확인 지점이 모두 반응. handler가 한 번도 확인하지 않으면 동작은 그대로) 부작용을 최대한 줄임 | `0` | 아니오 |
| `AGENT_SEARCH_TOOL_TIMEOUT_S` | Agent `search` 계열 도구의 기본 시간 초과(초). `0`이면 끄고 전체 예산으로 돌아감 | `0` | 아니오 |
| `AGENT_ANALYSIS_TOOL_TIMEOUT_S` | Agent `analysis` 계열 도구의 기본 시간 초과(초). `0`이면 끄고 전체 예산으로 돌아감 | `0` | 아니오 |
| `AGENT_ACTION_TOOL_TIMEOUT_S` | Agent `action` 계열 도구의 기본 시간 초과(초). `0`이면 끄고 전체 예산으로 돌아감 | `0` | 아니오 |
| `LITELLM_MODEL` | 기본 모델. 형식은 `provider/model`(예: `gemini/gemini-3.1-pro-preview`), 우선 사용 권장 | - | 아니오 |
| `AGENT_LITELLM_MODEL` | 「기본 모델」 종목 질문의 기본 모델(선택). 비워 두면 기본 모델을 이어받고, provider 접두사가 없으면 `openai/<model>`로 해석. Codex는 이 값을 쓰지 않음 | - | 아니오 |
| `AGENT_CONTEXT_COMPRESSION_ENABLED` | 「기본 모델」 종목 질문에서 보이는 대화 기록의 LLM 압축 스위치. Codex는 최근 20개의 보이는 대화를 쓰며 이 설정은 유지함 | `false` | 아니오 |
| `AGENT_CONTEXT_COMPRESSION_PROFILE` | 종목 질문 맥락 압축 전략: `cost` / `balanced` / `long_context_raw_first` | `balanced` | 아니오 |
| `AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS` | 과거 token 추정치가 이 값을 넘으면 압축 시작. 비워 두면 profile preset을 따름 | - | 아니오 |
| `AGENT_CONTEXT_PROTECTED_TURNS` | 압축할 때 최근 N개의 사용자 차례와 그 뒤의 답변은 원문 유지. 비워 두면 profile preset을 따름 | - | 아니오 |
| `LITELLM_FALLBACK_MODELS` | 예비 모델, 쉼표로 구분 | - | 아니오 |
| `LLM_CHANNELS` | 채널 이름 목록(쉼표로 구분). `LLM_{NAME}_*`와 함께 씀. 자세한 내용은 [LLM 설정 가이드](LLM_CONFIG_GUIDE.md) | - | 아니오 |
| `MODELFLARE_KEY` | Modelflare를 Key 하나로 연결하며 기본 채널을 자동으로 켬. Actions는 Secrets에서만 읽음 | - | 쓸 때 |
| `LLM_MODELFLARE_API_KEY` | 고급 채널 Key. MODELFLARE_KEY보다 우선. 여러 Key는 `LLM_MODELFLARE_API_KEYS`를 씀 | - | 아니오 |
| `LLM_MODELFLARE_PROTOCOL` | Modelflare 채널 프로토콜. 기본 주소는 자동으로 `openai`로 인식 | `openai` | 아니오 |
| `LLM_MODELFLARE_API_SURFACE` | Modelflare 채널 API Surface. 빠른 시작 예시는 `chat_completions`를 씀 | `chat_completions` | 아니오 |
| `LLM_MODELFLARE_BASE_URL` | Modelflare 접속 주소. 명시적으로 설정하면 기본값보다 우선 | `https://modelflare.dev/v1` | 아니오 |
| `LLM_MODELFLARE_MODELS` | 고급 명시 채널 모델 목록. Modelflare 채널 하나만 쓸 때는 LITELLM_MODEL을 재사용할 수 있음 | 채널이 하나이면 자동 추론 | 아니오 |
| `LLM_HERMES_API_KEY` | Hermes 예약 로컬 HTTP generation의 단일 API Key. `.env`, 실행 시 설정, Secrets에서만 와야 함 | - | Hermes를 쓸 때 필수 |
| `LLM_HERMES_BASE_URL` | Hermes 로컬 loopback `/v1` 주소. 기본 `http://127.0.0.1:8642/v1`, 원격 주소는 지원하지 않음 | `http://127.0.0.1:8642/v1` | 아니오 |
| `LLM_HERMES_MODELS` | Hermes 원본 모델 목록. Phase 3 기본값은 `hermes-agent`이고 실행 시 route는 `openai/hermes-agent`. Vision / stream / tools / Agent tools는 지원하지 않음 | `hermes-agent` | 아니오 |
| `LITELLM_CONFIG` | 고급 모델 라우팅 YAML 설정 파일 경로(고급) | - | 아니오 |
| `LLM_PROMPT_CACHE_TELEMETRY_ENABLED` | Provider prompt cache usage / diagnostics 텔레메트리. provider의 implicit cache는 제어하지 않음 | `true` | 아니오 |
| `LLM_PROMPT_CACHE_HINTS_ENABLED` | 주 분석 경로에서 검증된 provider별 prompt cache hints를 직접 보낼지 여부. Agent 경로는 현재 diagnostics만 기록하고 hints를 보내지 않음. 기본은 끔 | `false` | 아니오 |
| `LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL` | Prompt cache 진단 수준: `off` / `basic` / `debug`. basic/debug는 debug 로그와 테스트용 관찰 객체에서만 민감 정보를 가린 진단을 제공하며, 공개 Usage API나 일반 설정 페이지 출력으로 쓰지 않음 | `off` | 아니오 |
| `LLM_USAGE_HMAC_SECRET` | LLM 사용량 텔레메트리 message HMAC 키. 비워 두면 데이터 디렉터리의 로컬 키 파일을 자동으로 씀 | - | 아니오 |
| `LLM_USAGE_HMAC_KEY_VERSION` | LLM 사용량 텔레메트리 HMAC 키 버전 태그. 키를 교체할 때 함께 바꿈 | `local-v1` | 아니오 |
| `ANSPIRE_API_KEYS` | [Anspire](https://open.anspire.cn/dsa?share_code=QFBC0FYC) API Key. Key 하나로 LLM 게이트웨이와 검색을 함께 켬 | - | 선택 |
| `AIHUBMIX_KEY` | [AIHubmix](https://inferera.com/?aff=CfMq) API Key. Key 하나로 모든 모델을 바꿔 가며 쓸 수 있고 Base URL을 따로 설정할 필요 없음 | - | 선택 |
| `GEMINI_API_KEY` | Google Gemini API Key | - | 선택 |
| `GEMINI_MODEL` | 기본 모델 이름(legacy, `LITELLM_MODEL`이 우선) | `gemini-3.1-pro-preview` | 아니오 |
| `GEMINI_MODEL_FALLBACK` | 예비 모델(legacy) | `gemini-3-flash-preview` | 아니오 |
| `OPENAI_API_KEY` | OpenAI 호환 API Key | - | 선택 |
| `OPENAI_BASE_URL` | OpenAI 호환 API 주소 | - | 선택 |
| `OLLAMA_API_BASE` | Ollama 로컬 서비스 주소(예: `http://localhost:11434`). 자세한 내용은 [LLM 설정 가이드](LLM_CONFIG_GUIDE.md) | - | 선택 |
| `OPENAI_MODEL` | OpenAI 모델 이름(legacy. AIHubmix 사용자는 `gemini-3.1-pro-preview`, `gpt-5.5` 등을 넣을 수 있음) | `gpt-5.5` | 선택 |
| `ANTHROPIC_API_KEY` | Anthropic Claude API Key | - | 선택 |
| `ANTHROPIC_MODEL` | Claude 모델 이름 | `claude-sonnet-4-6` | 선택 |
| `ANTHROPIC_TEMPERATURE` | Claude temperature 매개변수(0.0-1.0) | `0.7` | 선택 |
| `ANTHROPIC_MAX_TOKENS` | Claude 응답 최대 token 수 | `8192` | 선택 |

> GitHub Actions 안내: 저장소에 들어 있는 `00-daily-analysis.yml`은 `GENERATION_FALLBACK_BACKEND`가 설정되지 않았으면 명시적으로 `litellm`을 써서, 설정하지 않은 Secret/Variable이 빈 값으로 내보내져 backend fallback이 뜻하지 않게 꺼지는 일을 막습니다. Actions에서 backend fallback을 끄려면 fallback을 primary backend와 같은 값으로 두어 resolver가 self no-op으로 처리하게 하세요.

> 생성 backend 상태 안내: 웹 설정 페이지의 빠른 검사는 저장된 설정과 저장하지 않은 초안만 읽고, 로컬 CLI 실행 파일이 보이는지 확인하며, 실제 모델 요청은 보내지 않습니다. JSON 연기 테스트는 따로 명시적으로 실행하는 작업으로, 서버에 고정된 JSON 프롬프트와 schema로 실제 요청을 한 번 보냅니다. `health_status`와 `last_error_code/message`는 이번 상태 계산이나 연기 테스트 결과일 뿐, 과거부터 저장된 상태가 아닙니다.

> *참고: 쓸 수 있는 `LLM_CHANNELS` / `LITELLM_CONFIG`, 또는 legacy provider Key / `OLLAMA_API_BASE` 가운데 하나 이상을 설정해야 합니다. Modelflare는 Channels로 연결합니다. 기존 `ANSPIRE_API_KEYS`와 `AIHUBMIX_KEY`의 legacy 호환 진입점은 여전히 `OPENAI_BASE_URL`을 설정할 필요 없이 시스템이 자동으로 맞춥니다.

> 종목 질문 single-agent 경로는 백그라운드에서 DeepSeek V4 thinking + tool-call을 위해 최근 3개의 provider trace를 저장하고, `reasoning_content` / tool 결과를 원래 순서대로 다시 재생합니다. 이 기능은 설정 항목을 추가하지 않고 웹 이력 API에도 들어가지 않습니다. Claude extended thinking은 오프라인 연결 부분만 다루며, multi-agent trace 주입은 이후 개선으로 남겨 둡니다.

> Codex App Server 종목 질문 backend는 제거되었습니다. `AGENT_BACKEND`는 `auto`(권장, 기본 LiteLLM 유지)나 `litellm`만 지원합니다. 예전 `codex_app_server` 값은 불러오고, 표시하고, 내보낼 수는 있지만, 실행 요청은 준비와 제출 수락 전에 `backend_removed`를 돌려주며 모델, 계정, provider를 자동으로 바꾸지 않습니다. 「设置 → Agent 设置 → 问股生成方式」(설정 → Agent 설정 → 종목 질문 생성 방식)에서 올바른 값을 직접 골라 저장하세요. 예전 값이 남아 있어도 관계없는 설정 저장은 막지 않지만, 예전 값을 명시적으로 저장하거나 가져오면 거부하며 일부만 기록하지도 않습니다. 상태와 초안 미리 보기는 설정만 확인하며, Codex 명령이나 schema/version 확인을 실행하지 않고 모델도 호출하지 않습니다. 과거 대화, 종목 식별, Skill, 단일/다중 Agent, provider trace는 원래 계약을 유지합니다. 별도의 `GENERATION_BACKEND=codex_cli` 일반 리포트와 그 밖의 generation-only 기능은 이번 제거와 관계없으며, 여전히 각자의 CLI와 원래 의존성이 필요합니다.

### 알림 채널 설정

알림 설정 기준, 진단, 배포 상황별 설명은 [알림 문서](notifications.md)를 보세요.

| 변수 이름 | 설명 | 필수 |
|--------|------|:----:|
| `WECHAT_WEBHOOK_URL` | WeCom(기업용 위챗) 봇 Webhook URL | 선택 |
| `FEISHU_WEBHOOK_URL` | Feishu(페이슈) 봇 Webhook URL | 선택 |
| `FEISHU_WEBHOOK_SECRET` | Feishu 봇 서명 키(봇 보안 설정에서 "서명 검증"을 켰을 때만 입력) | 선택 |
| `FEISHU_WEBHOOK_KEYWORD` | Feishu 봇 키워드(봇 보안 설정에서 "키워드"를 켰을 때만 입력) | 선택 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | 선택 |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 선택 |
| `TELEGRAM_MESSAGE_THREAD_ID` | Telegram Topic ID | 선택 |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL | 선택 |
| `DISCORD_BOT_TOKEN` | Discord Bot Token(Webhook과 둘 중 하나) | 선택 |
| `DISCORD_MAIN_CHANNEL_ID` | Discord Channel ID(Bot을 쓸 때 필요) | 선택 |
| `DISCORD_INTERACTIONS_PUBLIC_KEY` | Discord Public Key(들어오는 Interaction/Webhook 콜백 서명을 검증할 때만 필요) | 선택 |
| `DISCORD_MAX_WORDS` | Discord 메시지 하나의 content 상한(기본 2000. 실행 중 Discord의 2000자 제한을 넘지 않으며, 긴 리포트는 자동으로 나눠 보내고 429 요청 제한에는 제한된 횟수만큼 재시도) | 선택 |
| `SLACK_BOT_TOKEN` | Slack Bot Token(권장, 이미지 업로드 지원. 함께 설정하면 Webhook보다 우선) | 선택 |
| `SLACK_CHANNEL_ID` | Slack Channel ID(Bot을 쓸 때 필요) | 선택 |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL(텍스트만, 이미지 미지원) | 선택 |
| `EMAIL_SENDER` | 보내는 사람 메일 주소 | 선택 |
| `EMAIL_PASSWORD` | 메일 인증 코드(로그인 비밀번호가 아님) | 선택 |
| `EMAIL_RECEIVERS` | 받는 사람 메일 주소(쉼표로 구분, 비워 두면 자신에게 발송) | 선택 |
| `EMAIL_SENDER_NAME` | 보내는 사람 표시 이름 | 선택 |
| `STOCK_GROUP_N` / `EMAIL_GROUP_N` | 메일 그룹 라우팅(Issue #268): `STOCK_GROUP_N`은 `STOCK_LIST`의 부분 집합이어야 하며, 메일 수신자에만 영향을 주고 분석 범위나 다른 알림 채널은 바꾸지 않음 | 선택 |
| `CUSTOM_WEBHOOK_URLS` | 사용자 정의 Webhook(쉼표로 구분) | 선택 |
| `CUSTOM_WEBHOOK_BEARER_TOKEN` | 사용자 정의 Webhook Bearer Token | 선택 |
| `WEBHOOK_VERIFY_SSL` | 이 설정을 읽는 webhook 계열 HTTPS 알림 요청의 인증서 검증(기본 true). false로 두면 자체 서명 인증서를 쓸 수 있음. 경고: 끄면 심각한 보안 위험이 있음 | 선택 |
| `PUSHOVER_USER_KEY` | Pushover 사용자 Key | 선택 |
| `PUSHOVER_API_TOKEN` | Pushover API Token | 선택 |
| `NTFY_URL` | ntfy 전체 topic endpoint. 반드시 topic 경로 포함. 예: `https://ntfy.sh/my-topic` | 선택 |
| `NTFY_TOKEN` | ntfy Bearer Token(선택) | 선택 |
| `GOTIFY_URL` | Gotify 서버 base URL. `/message`는 넣지 않음 | 선택 |
| `GOTIFY_TOKEN` | Gotify application token. `X-Gotify-Key` Header로 보냄 | 선택 |
| `PUSHPLUS_TOKEN` | PushPlus Token(중국 내 푸시 서비스) | 선택 |
| `SERVERCHAN3_SENDKEY` | Server酱³(ServerChan3) Sendkey | 선택 |
| `ASTRBOT_URL` | AstrBot Webhook URL | 선택 |
| `ASTRBOT_TOKEN` | AstrBot Bearer Token(선택) | 선택 |
| `NOTIFICATION_REPORT_CHANNELS` | report 라우팅 채널, 쉼표로 구분. 허용 값: wechat,feishu,telegram,email,pushover,ntfy,gotify,pushplus,serverchan3,custom,discord,slack,astrbot | 선택 |
| `NOTIFICATION_ALERT_CHANNELS` | alert 라우팅 채널, 쉼표로 구분. 비워 두면 모든 채널 유지 | 선택 |
| `NOTIFICATION_SYSTEM_ERROR_CHANNELS` | system_error 예약 라우팅 채널, 쉼표로 구분. 비워 두면 모든 채널 유지 | 선택 |
| `NOTIFICATION_DEDUP_TTL_SECONDS` | 알림 중복 제거 TTL(초). `0`이면 끔 | 선택 |
| `NOTIFICATION_COOLDOWN_SECONDS` | 알림 쿨다운(초). `0`이면 끔 | 선택 |
| `NOTIFICATION_QUIET_HOURS` | 방해 금지 시간대. 형식 `HH:MM-HH:MM`, 자정을 넘겨도 됨 | 선택 |
| `NOTIFICATION_TIMEZONE` | 방해 금지 시간대의 시간대. 예: `Asia/Shanghai`(한국은 `Asia/Seoul`). 비워 두면 `TZ`나 시스템 로컬 시간대를 따름 | 선택 |
| `NOTIFICATION_MIN_SEVERITY` | 최소 알림 수준: info, warning, error, critical. 비워 두면 현재 동작 유지 | 선택 |
| `NOTIFICATION_DAILY_DIGEST_ENABLED` | 일일 요약 예약 스위치. 현재는 요약을 보내지 않음 | 선택 |

> 안내: 기본 `00-daily-analysis.yml` GitHub Actions workflow는 정해진 변수 이름만 매핑하며, 번호가 임의로 붙는 `STOCK_GROUP_N` / `EMAIL_GROUP_N`을 자동으로 넣지 않습니다. 그래서 메일 그룹은 지금 로컬 `.env`, Docker, 또는 이런 환경 변수를 명시적으로 넣은 다른 실행 환경에서만 적용됩니다. 자신의 GitHub Actions에서 쓰려면 workflow의 job `env:`에 그룹마다 명시적으로 매핑해야 합니다.

#### Feishu(페이슈) 클라우드 문서 설정(선택, 메시지 잘림 문제 해결)

| 변수 이름 | 설명 | 필수 |
|--------|------|:----:|
| `FEISHU_APP_ID` | Feishu 앱 ID | 선택 |
| `FEISHU_APP_SECRET` | Feishu 앱 Secret | 선택 |
| `FEISHU_FOLDER_TOKEN` | Feishu 클라우드 드라이브 폴더 Token | 선택 |
| `FEISHU_SEND_AS_FILE` | Feishu App Bot이 리포트를 파일로 보냄(기본 `false`) | 선택 |

> Feishu 클라우드 문서 설정 순서:
> 1. [Feishu 개발자 콘솔](https://open.feishu.cn/app)에서 앱을 만듭니다
> 2. GitHub Secrets를 설정합니다
> 3. 그룹을 만들고 앱 봇을 추가합니다
> 4. 클라우드 드라이브 폴더에 그룹을 협업자(관리 권한)로 추가합니다
>
> 안내: `FEISHU_APP_ID` / `FEISHU_APP_SECRET`은 Feishu 앱, 클라우드 문서, Stream Bot 모드에 쓰이며, 그룹 Webhook 알림을 직접 켜지 않습니다. 그룹 알림만 간단히 받고 싶다면 `FEISHU_WEBHOOK_URL`을 먼저 설정하세요.
>
> 보충: `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_CHAT_ID`를 모두 설정하면 Feishu App Bot 직접 알림 채널을 켤 수 있어, Webhook 없이도 지정한 chat이나 사용자에게 직접 보낼 수 있습니다. `FEISHU_RECEIVE_ID_TYPE` 기본값은 `chat_id`이며, 개인 대화라면 `open_id`로 바꿉니다. 이 방식은 Feishu OpenAPI Bot 대화를 쓰며, 그룹 Webhook과는 서로 독립된 경로입니다.

<a id="搜索服务配置"></a>

### 검색 서비스 설정

| 변수 이름 | 설명 | 필수 |
|--------|------|:----:|
| `ANSPIRE_API_KEYS` | Anspire Open API Key(검색과 LLM 게이트웨이를 함께 쓰는 설정 예시. 사용 가능 여부는 계정 권한과 게이트웨이 노출 범위에 달려 있으며, A주 분석 효과를 크게 높일 수 있음) | 권장 |
| `SERPAPI_API_KEYS` | SerpAPI 검색 엔진 결과 보강. 실시간 금융 뉴스에 적합 | 권장 |
| `TAVILY_API_KEYS` | Tavily 검색 API Key | 선택 |
| `BOCHA_API_KEYS` | Bocha(博查) 검색 API Key(중국어 최적화) | 선택 |
| `BRAVE_API_KEYS` | Brave Search API Key(미국 주식 최적화) | 선택 |
| `MINIMAX_API_KEYS` | MiniMax Coding Plan Web Search(구조화된 검색 결과) | 선택 |
| `SOCIAL_SENTIMENT_API_KEY` | Stock Sentiment API Key(Reddit / X / Polymarket, 선택) | 선택 |
| `SOCIAL_SENTIMENT_API_URL` | Stock Sentiment API 주소(기본 `https://api.adanos.org`) | 선택 |
| `SEARXNG_BASE_URLS` | SearXNG 자체 호스팅 인스턴스(할당량 없는 대체 수단, settings.yml에서 format: json을 켜야 함). 비워 두면 공개 인스턴스 찾기를 명시적으로 켰을 때만 `searx.space`를 씀 | 선택 |
| `SEARXNG_PUBLIC_INSTANCES_ENABLED` | `SEARXNG_BASE_URLS`가 비어 있을 때 `searx.space`에서 공개 인스턴스를 자동으로 가져올지 여부(기본 `false`). 공개 인스턴스는 대부분 요청 제한이 있거나 JSON 출력을 켜지 않아서, 켜면 분석마다 30~60초가 더 걸리고 뉴스가 비어 있을 수 있음 | 선택 |
| `SEARXNG_TIMEOUT_SECONDS` | 자체 호스팅 SearXNG의 검색 1회 시간 초과(초, 기본 `10`, 최소 `1`). 인스턴스가 느리면(엔진을 많이 묶은 NAS 배포 등) 늘릴 수 있으며, 공개 인스턴스의 시간 초과에는 영향이 없음. GitHub Actions에서는 이 변수를 명시적으로 매핑해야 함 | 선택 |
| `NEWS_STRATEGY_PROFILE` | 뉴스 전략 기간 단계: `ultra_short`(1일)/`short`(3일)/`medium`(7일)/`long`(30일). 실제 기간은 `NEWS_MAX_AGE_DAYS`와 비교해 더 작은 값 | 기본 `short` |
| `NEWS_MAX_AGE_DAYS` | 뉴스 최대 유효 기간(일). 검색할 때 결과를 최근 것으로 제한 | 기본 `3` |
| `BIAS_THRESHOLD` | 이격도 임곗값(%). 넘으면 추격 매수하지 말라고 안내. 강한 추세 종목은 자동으로 1.5배까지 완화 | 기본 `5.0` |

> 동작 안내: 검색 서비스와 소셜 여론 서비스는 선택적인 보강 경로입니다. 어느 서비스든 초기화에 실패하면 시스템은 warning을 남기고 그 서비스를 건너뛰도록 기능을 낮추며, 해당 단계에만 영향을 주고 기술적 분석 주 경로와 주 작업 흐름은 막지 않습니다.

### 뉴스 검색의 설명 가능한 정렬(Issue #1356)

`search_stock_news`는 후보 뉴스마다 「설명 가능한 관련도」를 계산해 3가지 태그로 남깁니다.

- `direct_company_news`: 대상 코드나 회사 이름과 일치(공식/거래소 출처 가중치 포함)
- `sector_related_news`: 업종 섹터 의미와 일치
- `macro_market_news`: 대상과 일치하지 않는 거시/시장 맥락 뉴스

정렬은 먼저 분류 우선순위(direct > sector > macro)로, 다음은 언어 선호(중국어 우선)로, 마지막으로 점수로 합니다. 그래서 같은 기간 안에 대상 종목과 분명히 일치하는 뉴스가 있으면 그것을 먼저 보여 줍니다.

정렬 뒤에는 도메인과 관계없는 진입 필터를 한 번 더 거칩니다. 분명한 다운로드/설치 파일/앱 평점 페이지, 성인/성매매 스팸 페이지는 빼고, 같은 묶음에 이미 대상 종목 직접 뉴스나 점수가 있는 업종/시장 후보가 있으면 `score=0`인 배경 채우기 항목은 `news_context`, Agent 도구 출력, 과거 정보 캐시에 넣지 않습니다. 이 규칙에는 특정 사이트 차단 목록을 넣지 않아, 도메인을 하나하나 나열해 관리하지 않게 했습니다.

디버깅 방법:

- 돌려주는 항목마다 `relevance_score` / `relevance_category` / `relevance_reasons` 메타데이터가 남으며, 최종 `to_text()`와 정보 맥락에 해당 「关联度」(관련도) 설명이 붙습니다.
- 검색 경로 로그에 `[新闻相关度]`(뉴스 관련도) 통계가 나오므로, 그 묶음이 왜 direct/sector/macro로 나뉘었는지 되짚어 보기 쉽습니다.

호환과 되돌리기 안내: 이 변경은 모델, provider, Base URL, LiteLLM route, 설정 정리나 되쓰기 로직을 추가하거나 바꾸지 않습니다. 문제가 생기면 이번 커밋을 롤백해야만 예전 정렬 동작으로 돌아갈 수 있으며, 과거 설정 마이그레이션과는 관계없습니다.

### Futu 보유 종목 가져오기 설정

| 변수 이름 | 설명 | 기본값 | 필수 |
|--------|------|--------|:----:|
| `FUTU_OPEND_HOST` | OpenD 주소. 고정된 `futu-api==10.8.6808`은 IPv4 주소나 IPv4로 해석되는 호스트 이름만 지원함. 다른 컴퓨터에 연결할 때는 믿을 수 있는 네트워크나 로컬 포트 포워딩만 써야 함. | `127.0.0.1` | 선택 |
| `FUTU_OPEND_PORT` | OpenD 포트, 올바른 범위는 `1-65535`. | `11111` | 선택 |
| `FUTU_SECURITY_FIRM` | Futu `SecurityFirm` 열거형 이름. `NONE`은 SDK 공식 자동 인식을 한 번 쓴다는 뜻이며, 증권사를 명시할 수도 있음. | `NONE` | 선택 |
| `FUTU_ACC_ID` | 조건에 맞는 REAL 계좌 ID 하나를 지정. 비워 두면 상태가 `ACTIVE`인 `NORMAL`(일반)과 `MASTER`(주) 증권 계좌를 모두 합침. 계좌 ID는 민감한 설정으로 다루고 저장소에 커밋하지 말 것. | 비어 있음 | 선택 |

`MASTER`는 Futu의 주 계좌 역할을 뜻할 뿐, 계좌가 읽기 전용이라는 뜻은 아닙니다. 이 연동의 읽기 전용 범위는 계좌, 보유 종목, 증권 정보 조회 API만 호출하고, 거래 잠금 해제, 주문, 주문 수정, 주문 취소 API는 호출하지 않는다는 데서 나옵니다.

<a id="数据源配置"></a>

### 데이터 소스 설정

| 변수 이름 | 설명 | 기본값 | 필수 |
|--------|------|--------|:----:|
| `TUSHARE_TOKEN` | Tushare Pro Token | - | 선택 |
| `TUSHARE_HTTP_URL` | Tushare Pro HTTP 접속 주소. 비워 두면 공식 endpoint `http://api.tushare.pro`를 씀. 회사 내부망 프록시, 국경 간 네트워크, 자체 미러를 거쳐야 할 때만 `http://`나 `https://`로 시작하는 전체 주소를 넣음 | `http://api.tushare.pro` | 선택 |
| `TICKFLOW_API_KEY` | TickFlow API Key. 선택이며, A주 일봉, 실시간 시세, 종목 목록/이름, 시장 복기 강화에 쓰임. 실패하거나 권한이 부족하면 자동으로 대체 소스로 돌아감. | - | 선택 |
| `TICKFLOW_PRIORITY` | TickFlow 일반 A주 일봉 데이터 소스 우선순위. 숫자가 작을수록 먼저 시도하며 기본 `2`. API Key가 없으면 쓰지 않음. 등록 지수는 별도의 고정 순서를 쓰며 이 변수를 읽지 않음. 실시간 시세에는 영향 없음. | `2` | 선택 |
| `TENCENT_PRIORITY` | Tencent 직접 연결 일반 A주 일봉 데이터 소스 우선순위. 숫자가 작을수록 먼저 시도하며 기본 `5`로, 공통 경로의 마지막 대체 소스. 등록 지수는 별도의 고정 순서를 쓰며 이 변수를 읽지 않음. 실시간 시세에는 영향 없음. | `5` | 선택 |
| `TICKFLOW_KLINE_ADJUST` | TickFlow 일봉 수정주가 방식: `none`, `forward`, `backward`, `forward_additive`, `backward_additive`. | `none` | 선택 |
| `TICKFLOW_BATCH_DAILY_ENABLED` | TickFlow 일봉 일괄 미리 가져오기 사용 여부. 권한이 부족하면 실패 상태를 잠시 캐시하고 일반 대체 경로로 계속 진행함. | `true` | 선택 |
| `TICKFLOW_BATCH_SIZE` | TickFlow 일봉과 실시간 시세 일괄 요청 1회의 최대 종목 수. | `100` | 선택 |
| `FUTU_HK_REALTIME_SOURCE_PRIORITY` | 홍콩 주식 실시간 시세의 별도 우선순위. `futu`, `longbridge`, `akshare`, `yfinance` 중에서 쉼표로 구분해 고름. 실패하면 자동으로 다음으로 넘어감. | `futu,longbridge,akshare,yfinance` | 선택 |
| `LONGBRIDGE_OAUTH_CLIENT_ID` | Longbridge OAuth client_id. 비워 두고 Legacy Access Token도 없으면 `LONGBRIDGE_APP_KEY`를 호환용으로 씀 | - | 선택 |
| `LONGBRIDGE_OAUTH_TOKEN_CACHE_B64` | OAuth token 캐시 파일의 base64 내용. GitHub Actions / Docker 같은 headless 환경용 | - | 선택 |
| `LONGBRIDGE_APP_KEY` | Longbridge Legacy App Key. `LONGBRIDGE_ACCESS_TOKEN`이 없으면 OAuth client_id의 호환 별칭으로도 쓸 수 있음 | - | 선택 |
| `LONGBRIDGE_APP_SECRET` | Longbridge App Secret | - | 선택 |
| `LONGBRIDGE_ACCESS_TOKEN` | Longbridge Legacy Access Token(OAuth access token이 아님) | - | 선택 |
| `LONGBRIDGE_*`(선택) | 공식 [환경 변수](https://open.longbridge.com/zh-CN/docs/getting-started#环境变量) 참고. 그 밖에 `LONGBRIDGE_STATIC_INFO_TTL_SECONDS`와 `LONGBRIDGE_CONNECTION_COOLDOWN_SECONDS`가 있음 | - | 선택 |
| `ENABLE_REALTIME_QUOTE` | 실시간 시세 사용(끄면 과거 종가로 분석) | `true` | 선택 |
| `ENABLE_REALTIME_TECHNICAL_INDICATORS` | 장중 실시간 기술적 분석: 켜면 실시간 가격으로 MA5/MA10/MA20과 정배열을 계산(Issue #234), 끄면 전일 종가를 씀 | `true` | 선택 |
| `ENABLE_CHIP_DISTRIBUTION` | 매물대(보유 원가 분포) 분석 사용(이 API는 불안정하므로 클라우드 배포에서는 끄는 것을 권장). GitHub Actions 사용자는 Repository Variables에서 `ENABLE_CHIP_DISTRIBUTION=true`로 설정해야 켜지며, workflow 기본값은 꺼짐. | `true` | 선택 |
| `ENABLE_EASTMONEY_PATCH` | 둥팡차이푸 API 패치: 둥팡차이푸 API가 자주 실패하면(RemoteDisconnected, 연결 끊김 등) `true`로 두는 것을 권장. NID 토큰과 무작위 User-Agent를 넣어 요청 제한에 걸릴 확률을 낮춤 | `false` | 선택 |
| `REALTIME_SOURCE_PRIORITY` | 실시간 시세 소스 우선순위, 쉼표로 구분. 예: `tencent,akshare_sina,efinance,akshare_em`. TickFlow 실시간 시세를 쓰려면 `tickflow`를 명시적으로 넣어야 함. | `.env.example` 참고 | 선택 |
| `ENABLE_FUNDAMENTAL_PIPELINE` | 기본적 분석 집계 전체 스위치. 끄면 `not_supported` 블록만 돌려주며, 원래 분석 경로는 바꾸지 않음 | `true` | 선택 |
| `FUNDAMENTAL_STAGE_TIMEOUT_SECONDS` | 기본적 분석 단계 전체 지연 예산(초) | `8.0` | 선택 |
| `FUNDAMENTAL_FETCH_TIMEOUT_SECONDS` | 기능별 소스 호출 1회의 시간 초과(초). 시장 구조 업종/테마 순위도 이 예산을 함께 씀 | `8.0` | 선택 |
| `FUNDAMENTAL_RETRY_MAX` | 기본적 분석 기능 재시도 횟수(첫 시도 포함) | `1` | 선택 |
| `FUNDAMENTAL_CACHE_TTL_SECONDS` | 기본적 분석 집계 캐시 TTL(초). 짧은 캐시로 반복 조회 부담을 줄임 | `120` | 선택 |
| `FUNDAMENTAL_CACHE_MAX_ENTRIES` | 기본적 분석 캐시 최대 항목 수(TTL 안에서 시간 순으로 정리) | `256` | 선택 |

> 동작 안내:
> - A주: `valuation/growth/earnings/institution/capital_flow/dragon_tiger/boards` 집계 기능별로 돌려줍니다.
> - ETF: 얻을 수 있는 항목을 돌려주고, 없는 기능은 `not_supported`로 표시하며, 전체적으로 원래 흐름에 영향을 주지 않습니다.
> - 미국/홍콩 주식: yfinance 어댑터로 `valuation/growth/earnings/belong_boards`(출처 `info.sector`/`industry`)를 돌려줍니다. `institution/capital_flow/dragon_tiger/boards`는 아직 해당 데이터 소스가 없어 `not_supported`로 표시하며, yfinance를 쓸 수 없거나 필드가 없으면 전체를 `not_supported`로 낮추고 여전히 fail-open합니다.
> - 일본/한국 주식: 현재 Yfinance 기본 경로로만 일봉과 실시간 시세를 가져옵니다. `institution`, `capital_flow`, `dragon_tiger`, `boards`처럼 A주 전용 소스나 해외 완전판에 의존하는 기능은 `not_supported`로 낮춥니다(자세한 내용은 [시장 지원 범위](market-support.md)).
> - 대만 주식: 미국/홍콩 주식의 해외 기본 경로 외에, `institution` 블록에 3대 법인의 원본 순매수/순매도를 추가로 보여 줍니다(TWSE T86 / TPEx, 기본으로 켜져 있고 fail-open하며, 데이터를 못 받으면 `not_supported` 유지). `capital_flow`, `dragon_tiger`, `boards`는 여전히 `not_supported`입니다.
> - 어떤 예외든 fail-open으로 처리하며, 오류만 기록하고 기술적 분석/뉴스/매물대 주 경로에는 영향을 주지 않습니다.
> - `TICKFLOW_API_KEY`를 설정하면 TickFlow가 선택적인 A주 일봉 데이터 소스와 시장 복기 보강 소스로 만들어집니다. `TICKFLOW_PRIORITY`는 일반 A주 일봉/공통 데이터 소스 대체 순서에만 영향을 줍니다. 실시간 시세 우선순위는 `REALTIME_SOURCE_PRIORITY`가 따로 정하며, `tickflow`를 명시적으로 넣었을 때만 TickFlow 실시간 시세를 씁니다. `REALTIME_SOURCE_PRIORITY`에서 `tickflow`보다 앞에 있는 데이터 소스가 먼저 시도됩니다.
> - 현재 `IndexRegistry`에 등록된 모든 상하이·선전 지수(`sh`/`sz`/`csi` 접두사. 구체적인 목록은 [지수 관심 종목 설정](#指数自选股配置)의 등록표 설명과 `scripts/stock_index_seeds/index_registry.csv`를 기준으로 함)는 시장을 명시해 입력하면(`000016.SH` 같은 거래소 접미사 형식도 받음) 공통 priority 정렬에 참여하지 않고, Tencent → AkShare → TickFlow → YFinance 순서로 고정해 기능을 낮춥니다. 설정하지 않았거나 쓸 수 없는 소스는 건너뜁니다. 접미사 없는 `000016` 같은 코드는 여전히 종목으로 처리하며 지수 경로를 쓰지 않습니다. 이 고정 경로는 `EFINANCE_PRIORITY`, `AKSHARE_PRIORITY`, `TUSHARE_PRIORITY`, `TICKFLOW_PRIORITY`, `PYTDX_PRIORITY`, `BAOSTOCK_PRIORITY`, `YFINANCE_PRIORITY`, `TENCENT_PRIORITY`를 읽지 않으며, 일반 종목과 실시간 시세의 기존 순서에도 영향을 주지 않습니다.
> - 등록 지수 이름은 로컬 등록표를 우선 씁니다. 등록된 이름이 잘못되었을 때만 Tencent → AkShare → TickFlow 순서로 조회하며, 이름 조회 경로에는 YFinance를 쓰지 않습니다. 지수 일봉 네 소스가 모두 실패하면 빈 결과를 돌려주고 종합 경고를 기록합니다. 일반 종목은 여전히 기존의 `DataFetchError` 최종 실패 계약을 유지합니다.
> - TickFlow 일봉 기본값은 `TICKFLOW_KLINE_ADJUST=none`입니다. 일봉 `volume`은 손(手, 100주) 단위를 주 단위로 통일해 바꾸고, `amount`는 위안 단위를 유지합니다.
> - TickFlow 일봉 구간 요청은 `start_time` / `end_time` / `count`를 명시적으로 넘깁니다. 공식 quickstart는 시간 범위 조회도 여전히 `count` 제한을 받는다고 분명히 밝힙니다. 결과가 비어 있지 않은데 행 수가 `count`를 꽉 채웠고 첫 거래일이 요청 시작 거래일보다 늦으면, 시스템은 잘렸을 가능성이 있다고 보고 캐시에 쓰지 않으며 manager가 다음 소스로 계속 넘어가게 합니다.
> - 일괄 분석할 때 `prefetch_daily_klines()`가 종목별 `get_daily_data()`보다 먼저 프로세스 내 캐시를 데워 두며, 외부 호출 경로는 바꾸지 않습니다.
> - TickFlow 기능은 요금제 권한에 따라 단계가 나뉩니다. 권한이 제한된 요금제도 주요 지수 조회는 쓸 수 있고, `CN_Equity_A` 종목 풀 조회를 지원하는 요금제에서만 TickFlow 시장 통계를 켭니다.
> - TickFlow는 선완(申万) 1단계 업종 종목 풀과 전체 A주 시세로 업종 등락 순위를 만들 수 있으며, 시장 구조 업종 주도 테마 fallback에 우선 참여합니다. 테마 순위는 여전히 기존 AkShare / Tushare / Efinance 경로가 제공합니다.
> - TickFlow 공식 quickstart는 `quotes.get(universes=["CN_Equity_A"])` 사용법을 소개하지만, API Key마다 해당 권한이 있다는 보장은 없습니다. 일괄 일봉, 호가 깊이, 재무 같은 기능도 권한에 따라 fail-open합니다.
> - TickFlow가 실제로 돌려주는 `change_pct` / `amplitude`는 비율 값입니다. 시스템은 연결 계층에서 이를 백분율 값으로 통일해 바꿔, 기존 데이터 소스 필드와 의미를 맞춥니다.
> - A주 시장 복기 리포트는 장 마감 후 작업대 형식을 씁니다. 장세 신호, 지수 상세, 섹터 Top 표, 최근 3일 시장 단서, 내일 매매 계획, 위험 안내를 항상 포함합니다. 장세 신호는 `66/100（偏暖，可进攻）`(66/100, 다소 따뜻함, 공격 가능) 같은 순수 텍스트 점수로 표현해, 색 블록 진행 막대가 터미널마다 다르게 보이는 일을 막습니다. 최근 3일 시장 단서는 제목, 출처, 링크만 나열하고 검색 요약 조각은 더 이상 보여 주지 않습니다. 일부 데이터 소스가 없으면 쓸 수 있는 블록은 남기고 해당 위치를 기능 저하 상태로 표시합니다.
> - 필드 계약:
>   - `fundamental_context.belong_boards` = 개별 종목 관련 섹터 목록. A주는 AkShare 섹터 명단에서, 미국/홍콩 주식은 yfinance `info.sector` / `info.industry`에서 기록하며, 데이터가 없으면 `[]`입니다.
>   - `fundamental_context.boards.data` = `sector_rankings`(섹터 등락 순위, 구조 `{top, bottom}`. HK/US는 현재 제공하지 않음).
>   - `fundamental_context.concept_boards.data` = `concept_rankings`(테마 등락 순위, 구조 `{top, bottom}`. 현재 A주만 제공하며, 쓸 수 없으면 fail-open으로 비어 있거나 없음).
>   - `fundamental_context.earnings.data.financial_report` = 재무 보고 요약(보고 기간, 매출, 지배주주 순이익, 영업현금흐름, ROE, 그리고 출처가 `info.financialCurrency`인 `currency`. HK ADR은 흔히 CNY).
>   - `fundamental_context.earnings.data.dividend` = 배당 지표(현금 배당 세전 기준만, `events`, `ttm_cash_dividend_per_share`, `ttm_dividend_yield_pct`, `currency` 포함). `currency`는 `info.currency`에서 따로 읽으므로 `financial_report.currency`와 다를 수 있습니다(HK ADR은 재무 보고 CNY, 배당 HKD). TTM 수익률은 기본으로 `ttm_cash / latest_price * 100`(같은 통화)로 바로 다시 계산하며, TTM cash나 latest price가 없을 때만 yfinance `trailingAnnualDividendYield`나 `dividendYield`로 대신합니다.
>   - `get_stock_info.belong_boards` = 개별 종목 소속 섹터 목록.
>   - `get_stock_info.boards`는 호환 별칭이며 값은 `belong_boards`와 같습니다(메이저 버전에서만 제거를 검토).
>   - `get_stock_info.sector_rankings`는 `fundamental_context.boards.data`와 같습니다.
>   - `AnalysisReport.details.belong_boards` = 구조화된 리포트 상세의 관련 섹터 목록.
>   - `AnalysisReport.details.sector_rankings` = 구조화된 리포트 상세의 섹터 등락 순위(프런트엔드 섹터 연동 표시에 사용).
>   - `AnalysisReport.details.concept_rankings` = 구조화된 리포트 상세의 테마 등락 순위(프런트엔드 관련 섹터 신호 매칭과, 알림 표에서 유형별로 업종/테마를 구분하는 데 사용).
> - 섹터 등락 순위의 데이터 소스 순서는 전체 priority와 같습니다.
> - 시간 초과 제어는 `best-effort` 소프트 시간 초과입니다. 단계는 예산에 따라 빠르게 기능을 낮춰 계속 진행하지만, 하위 서드파티 호출을 강제로 중단한다고 보장하지는 않습니다.
> - `FUNDAMENTAL_STAGE_TIMEOUT_SECONDS=8.0`은 새로 추가된 기본적 분석 단계의 목표 예산이지 엄격한 SLA가 아닙니다. Windows, Docker, 또는 무료 데이터 소스가 요청 제한에 걸린 환경에서는 `12-15s`까지 늘려도 됩니다.
> - 엄격한 SLA가 필요하다면 이후 버전에서 하위 프로세스 격리 실행으로 바꾸고, 시간 초과 뒤 강제로 종료해야 합니다.

### 기타 설정

| 변수 이름 | 설명 | 기본값 |
|--------|------|--------|
| `STOCK_LIST` | 관심 종목 코드(쉼표로 구분) | - |
| `ADMIN_AUTH_ENABLED` | 웹 로그인: `true`로 두면 비밀번호 보호를 켬. 처음 접속할 때 웹에서 초기 비밀번호를 정하며, 「系统设置 > 修改密码」(시스템 설정 > 비밀번호 변경)에서 바꿀 수 있음. 비밀번호를 잊으면 `python -m src.auth reset_password` 실행. 웹의 `.env` 백업 가져오기/내보내기는 이 스위치를 켠 뒤에만 쓸 수 있음(데스크톱 앱은 이 제한이 없음). | `false` |
| `TRUST_X_FORWARDED_FOR` | 신뢰할 수 있는 리버스 프록시가 한 단계뿐인 배포에서는 `true`로 두고, `X-Forwarded-For`의 가장 오른쪽 값을 실제 클라이언트 IP로 씀(로그인 요청 제한 등에 사용). 인터넷에 직접 노출된다면 위조를 막기 위해 `false` 유지. 여러 단계 프록시/CDN 환경에서는 요청 제한 key가 가장자리 프록시 IP가 될 수 있으므로 따로 검토가 필요함 | `false` |
| `MAX_WORKERS` | 동시 스레드 수 | `3` |
| `GUARD_ENABLED` | 선택적인 [fastapi-guard](https://github.com/Guard-Core/fastapi-guard) 보안 미들웨어 사용: IP별 요청 제한, IP 허용/차단 목록, 경로/쿼리 매개변수/요청 헤더 패턴 차단(`ssrf`를 뺀 모든 검사 분류. 브라우저는 페이지 주소를 `Referer`로 보내는데 guard-core 4.4.0은 그 안의 localhost와 사설망 주소를 ssrf로 판단하기 때문), 스캐너 자동 차단. 로그인 실패 요청 제한을 대신하지 않고 함께 동작함. 상태는 프로세스 메모리에 있어 Redis가 필요 없음. 바꾼 뒤에는 다시 시작해야 함. CORS는 여전히 원래 CORS 미들웨어가 처리함(guard 바깥쪽에 있어 429/403에도 CORS 헤더가 붙음). `fastapi-guard` 의존성이 필요함(`requirements.txt`에 있으며, 설치하지 않은 채 켜면 오류가 남) | `false` |
| `GUARD_RATE_LIMIT` / `GUARD_RATE_LIMIT_WINDOW` | IP마다 구간(초) 안에서 허용하는 최대 요청 수. 정적 리소스와 상태 확인도 똑같이 셈. 캐시가 비어 있을 때 WebUI 페이지 하나를 여는 데 약 14~34개 요청이 듦 | `300` / `60` |
| `GUARD_WHITELIST` / `GUARD_BLACKLIST` | IP 허용/차단 목록(쉼표로 구분, CIDR 지원). 허용 목록이 비어 있지 않으면 목록 밖의 IP는 모두 403. 목록 안의 IP는 요청 제한을 받지 않음 | 비어 있음 |
| `GUARD_TRUSTED_PROXIES` | `TRUST_X_FORWARDED_FOR=true`일 때만 적용: 신뢰할 수 있는 리버스 프록시 주소. 기본은 로컬 loopback뿐. 이 주소에서 온 연결만 `X-Forwarded-For`의 가장 오른쪽 값을 믿고, 다른 출처가 위조한 이 헤더는 무시함(로그인 요청 제한의 `get_client_ip()`도 가장 오른쪽 값을 쓰지만 프록시 출처는 검사하지 않음). `TRUST_X_FORWARDED_FOR`가 `false`이면 항상 TCP 상대 주소를 씀. guard를 켜면 내장 시작 진입점(`main.py`, `server.py`, `webui.py`)이 Uvicorn도 같은 프록시만 믿게 하고, `TRUST_X_FORWARDED_FOR=false`이면 Uvicorn의 프록시 헤더 처리를 끔. 그래서 리버스 프록시 뒤에 배포한다면 `TRUST_X_FORWARDED_FOR=true`로 설정하세요. guard를 켜고 `TRUST_X_FORWARDED_FOR=false`이면 Uvicorn의 프록시 헤더 처리가 꺼져, HTTPS 리버스 프록시 뒤에서 로그인 cookie에 `Secure` 플래그가 붙지 않음(`_cookie_params()`가 `request.url.scheme`을 읽기 때문). 그러므로 HTTPS 프록시 뒤에서는 `TRUST_X_FORWARDED_FOR=true`로 설정하세요. `uvicorn` 명령으로 직접 시작한다면 `FORWARDED_ALLOW_IPS`를 이 값과 맞추거나 `--no-proxy-headers`를 붙이세요. Docker에서 프록시가 loopback에 있지 않다면 프록시 주소를 넣어야 하며, 그렇지 않으면 모든 사용자가 같은 요청 제한 key를 함께 쓰게 됨 | `127.0.0.1,::1` |
| `GUARD_SCAN_BODY` | 요청 본문도 함께 검사할지 여부(기본은 경로, 쿼리 매개변수, 요청 헤더만 검사) | `false` |
| `GUARD_PASSIVE_MODE` | 로그만 남기고 차단하지 않음. 먼저 지켜볼 때 편함 | `false` |
| `MARKET_REVIEW_ENABLED` | 시장 복기 사용 | `true` |
| `DAILY_MARKET_CONTEXT_ENABLED` | 그날의 시장 환경 요약을 개별 종목 분석 Prompt에 넣고, 위험이 높거나 시장이 식는 환경에서는 공격적인 매수 의견을 누그러뜨림. 기본으로 켜져 있으며, `false`로 둬도 시장 복기는 실행할 수 있음 | `true` |
| `MARKET_REVIEW_REGION` | 시장 복기 지역: cn(A주), hk(홍콩 주식), us(미국 주식), jp(일본 주식), kr(한국 주식), both(5개 시장). us/jp/kr는 한 지역만 보는 사용자에게 알맞음. 쉼표로 묶어 `cn,kr`처럼 쓸 수도 있음 | `cn` |
| `MARKET_REVIEW_COLOR_SCHEME` | 시장 복기 지수 등락 색상: `green_up`=초록 상승·빨강 하락(기본), `red_up`=빨강 상승·초록 하락(한국식 표시는 `red_up`) | `green_up` |
| `TRADING_DAY_CHECK_ENABLED` | 거래일 확인: 기본 `true`, 비거래일에는 실행을 건너뜀. `false`로 두거나 `--force-run`을 쓰면 강제로 실행(Issue #373) | `true` |
| `SCHEDULE_ENABLED` | 예약 실행 사용 | `false` |
| `SCHEDULE_TIME` | 예약 실행 시각 | `18:00` |
| `SCHEDULE_TIMES` | 여러 예약 실행 시각, 쉼표로 구분. 비어 있으면 `SCHEDULE_TIME`을 씀 | 비어 있음 |
| `DSA_RUNTIME_SCHEDULER_TIMEOUT_SECONDS` | Web/API runtime scheduler의 분석 1회 엄격 시간 초과(초, 최소 60초). 시간을 넘기면 별도 분석 프로세스를 종료하며, 다음 작업을 막지 않음 | `2700` |
| `DSA_TIMEOUT_PARTIAL_NOTIFY` | **기본으로 켜짐(동작 변경)**: 엄격 시간 초과가 난 뒤 이미 저장된 개별 종목에 대해 「부분 완료」 알림을 보냄. 예전에는 시간 초과 시 알림을 보내지 않았음. `false`이면 구조화된 `last_error`는 기록하지만 알림은 보내지 않음 | `true` |
| `LOG_DIR` | 로그 디렉터리 | `./logs` |
| `SAVE_CONTEXT_SNAPSHOT` | 분석 이력의 `context_snapshot` 저장. `false`이면 새 이력에 enhanced_context, market_phase_summary, AnalysisContextPack overview, 진단 스냅샷을 저장하지 않지만, 이번 실행의 Prompt 저민감 요약은 끄지 않음 | `true` |

---

<a id="docker-部署"></a>

## Docker 배포

Dockerfile은 다단계 빌드를 쓰며, 프런트엔드는 이미지를 빌드할 때 자동으로 패키징되어 `static/`에 들어갑니다.
정적 리소스를 바꾸려면 로컬 `static/`을 컨테이너 안의 `/app/static`에 마운트하면 됩니다.
실행 중인 `server` 컨테이너는 기본으로 `/app/static`의 미리 빌드된 결과물을 그대로 쓰며, 컨테이너 안에 `apps/dsa-web` 소스 디렉터리를 두거나 실행 중에 `npm`을 설치할 필요가 없습니다. WebUI가 열리지 않으면 먼저 `/app/static/index.html`이 있는지 확인하세요.

현재 공식 이미지 배포 주소:

- GHCR: `ghcr.io/zhulinsen/daily_stock_analysis:<tag>`
- Docker Hub: `<DOCKERHUB_USERNAME>/daily_stock_analysis:<tag>`(배포자의 `DOCKERHUB_USERNAME` secret에 따라 정해지며, 공식 배포는 `zhulinsen/daily_stock_analysis`)

### 빠른 시작

```bash
# 1. 저장소 복제
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git
cd daily_stock_analysis

# 2. 환경 변수 설정
cp .env.example .env
vim .env  # API Key와 설정 입력

# 3. 컨테이너 시작
docker-compose -f ./docker/docker-compose.yml up -d server     # 웹 서비스 모드(권장, API와 WebUI 제공)
docker-compose -f ./docker/docker-compose.yml up -d analyzer   # 예약 실행 모드
docker-compose -f ./docker/docker-compose.yml up -d            # 두 모드를 함께 시작

# 4. WebUI 접속
# http://localhost:8000

# 5. 로그 보기
docker-compose -f ./docker/docker-compose.yml logs -f server
```

(Windows에서는 `vim` 대신 메모장 같은 편집기로 `.env`를 열어 고치면 됩니다.)

기본 Compose는 서비스마다 `limits.memory: 1G`, `reservations.memory: 512M`을 설정합니다. `512M`은 가벼운 Web/API, 종목 하나, 낮은 동시성 환경에만 권장하며 이때 `MAX_WORKERS=1`로 둡니다. 일반적인 전체 분석에는 `1G`를, `server + analyzer`를 함께 시작하거나 종목이 많거나 시장 복기, 뉴스 확장, 이미지 리포트, 종목 선별을 쓴다면 `2G+`를 권장합니다. `512M`만 쓸 수 있다면 두 서비스를 함께 시작하지 말고 무거운 기능을 줄이세요.

### 공식 이미지를 바로 받아 실행하기

대상 컴퓨터에 소스를 두지 않으려면 공식 이미지를 바로 받아 쓸 수 있습니다.

```bash
# Web/API 모드
docker pull zhulinsen/daily_stock_analysis:latest
docker run -d \
  --name dsa-server \
  --env-file .env \
  -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/reports:/app/reports" \
  zhulinsen/daily_stock_analysis:latest \
  python main.py --serve-only --host 0.0.0.0 --port 8000

# 예약 실행 모드
docker run -d \
  --name dsa-analyzer \
  --env-file .env \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/reports:/app/reports" \
  zhulinsen/daily_stock_analysis:latest
```

버전을 고정하거나 롤백하기 쉽게 하려면 `latest`를 구체적인 버전 tag(예: `v3.13.0`)로 바꾸세요.

### 실행 모드 안내

| 명령 | 설명 | 포트 |
|------|------|------|
| `docker-compose -f ./docker/docker-compose.yml up -d server` | 웹 서비스 모드, API와 WebUI 제공 | 8000 |
| `docker-compose -f ./docker/docker-compose.yml up -d analyzer` | 예약 실행 모드, 매일 자동 실행 | - |
| `docker-compose -f ./docker/docker-compose.yml up -d` | 두 모드를 함께 시작 | 8000 |

### Docker Compose 설정

`docker-compose.yml`은 YAML 앵커로 설정을 재사용합니다.

```yaml
version: '3.8'

x-common: &common
  build:
    context: ..
    dockerfile: docker/Dockerfile
  restart: unless-stopped
  env_file:
    - ../.env
  environment:
    - TZ=Asia/Shanghai
  volumes:
    - ../data:/app/data
    - ../logs:/app/logs
    - ../reports:/app/reports
    - ../strategies:/app/strategies:ro
  deploy:
    resources:
      limits:
        memory: 1G
      reservations:
        memory: 512M

services:
  # 예약 실행 모드
  analyzer:
    <<: *common
    container_name: stock-analyzer

  # FastAPI 모드
  server:
    <<: *common
    container_name: stock-server
    command: ["python", "main.py", "--serve-only", "--host", "0.0.0.0", "--port", "${API_PORT:-8000}"]
    ports:
      - "${API_PORT:-8000}:${API_PORT:-8000}"
```

### `.env`와 데이터 디렉터리 매핑 안내

`docker run`을 쓰든 Compose를 쓰든, 시작 시 환경 변수 주입과 실행 중 파일 쓰기를 구분해야 합니다.

- 환경 변수 주입: `--env-file .env` 또는 Compose의 `env_file`
  역할: `.env`의 키와 값을 컨테이너 시작 시 환경 변수로 Python 프로세스에 넘깁니다.
- 실행 중 설정 쓰기: 호스트의 `.env` 파일 하나를 bind mount해서 컨테이너 안의 `.env` 경로를 덮어쓰지 마세요. Docker는 단일 파일 마운트 대상을 mount point로 다루므로, 설정을 저장할 때 `os.replace()` 원자적 갱신이 `Device or resource busy`로 실패할 수 있고, 대체 쓰기도 권한 제한을 받을 수 있습니다.

기본 Compose와 `docker run` 예시는 `env_file` / `--env-file`로 시작 설정만 넣으며, 더 이상 호스트의 `.env` 파일 하나를 컨테이너에 마운트하지 않습니다. WebUI 설정 페이지는 현재 사용 중인 `.env` 파일에 일부 키가 없으면 시작 시 주입된 같은 이름의 환경 변수를 대신 보여 줘서, Docker 사용자가 설정을 전혀 읽지 않았다고 오해하지 않게 합니다. 하지만 "`.env` 내보내기"는 여전히 현재 사용 중인 설정 파일의 내용만 내보냅니다.

WebUI에서 저장한 실행 설정은 기본으로 컨테이너 안의 설정 파일에 쓰이며, 호스트의 `.env`에 다시 쓰는 것과 다릅니다. 컨테이너를 지우거나 다시 만들면 시작할 때 넣은 `.env`가 기준이 됩니다. 실행 설정을 계속 유지하려면 쓰기 대상을 쓰기 가능한 데이터 볼륨에 두세요(예: `ENV_FILE=/app/data/runtime.env`로 `data` 볼륨 안의 파일을 가리킴). `.env` 단일 파일 bind mount는 쓰지 마세요. 주의: 시작할 때의 `env_file`, `--env-file`, `docker run -e`, Compose `environment:`에 같은 이름의 예전 값이 남아 있으면, 컨테이너를 다시 시작할 때 이 프로세스 환경 변수가 실행 파일에 저장된 값을 덮어쓸 수 있습니다. WebUI에서 저장한 값을 쓰려면 시작 환경의 같은 이름 덮어쓰기를 함께 고치거나 지우세요.

다음 디렉터리를 함께 매핑하는 것을 권장합니다.

- `./data:/app/data`: 데이터베이스, 캐시, 실행 데이터
- `./logs:/app/logs`: 로그 출력
- `./reports:/app/reports`: 생성된 분석 리포트
- `./strategies:/app/strategies:ro`: 사용자 정의 전략 YAML(읽기 전용 마운트)

공식 Docker 이미지는 시작할 때 `/app/data`, `/app/logs`, `/app/reports` 마운트 디렉터리를 자동으로 만들고 권한을 고친 뒤, 컨테이너 안의 root가 아닌 사용자 `dsa`(UID/GID `1000:1000`)로 권한을 낮춰 앱을 실행합니다. 일반 Docker / Compose 배포에서는 호스트 디렉터리에 `chown`이나 `chmod`를 직접 할 필요가 없습니다.

`--user`나 Compose `user:`로 다른 실행 사용자를 지정했거나, 읽기 전용 마운트, rootless Docker, NFS처럼 `chown`이 제한되는 저장소를 쓴다면 자동 수정이 적용되지 않을 수 있습니다. 이때는 실제 실행 사용자가 `data`, `logs`, `reports`에 쓸 권한이 있는지 확인하거나, 쓰기 가능한 볼륨을 쓰세요.

내장 정적 리소스를 바꿔야 한다면 다음을 추가로 마운트할 수 있습니다.

- `./static:/app/static:ro`

### 자주 쓰는 명령

```bash
# 실행 상태 보기
docker-compose -f ./docker/docker-compose.yml ps

# 로그 보기
docker-compose -f ./docker/docker-compose.yml logs -f server

# 서비스 멈추기
docker-compose -f ./docker/docker-compose.yml down

# 이미지 다시 빌드(코드 업데이트 후)
docker-compose -f ./docker/docker-compose.yml build --no-cache
docker-compose -f ./docker/docker-compose.yml up -d server
```

### 이미지 직접 빌드

```bash
docker build -f docker/Dockerfile -t stock-analysis .
docker run -d \
  --name dsa-server-local \
  --env-file .env \
  -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/reports:/app/reports" \
  stock-analysis \
  python main.py --serve-only --host 0.0.0.0 --port 8000
```

---

<a id="本地运行详细配置"></a>

## 로컬 실행 자세한 설정

### 의존성 설치

```bash
# Python 3.10+ 권장
pip install -r requirements.txt

# 또는 conda 사용
conda create -n stock python=3.10
conda activate stock
pip install -r requirements.txt
```

Windows PowerShell이 여전히 시스템 기본 코드 페이지를 쓰고 있다면, 처음 의존성을 설치하거나 환경 검사를 실행하기 전에 UTF-8을 먼저 켜는 것을 권장합니다. 서드파티 도구나 터미널 출력이 중국어(한글 포함) 문자에서 실패하는 일을 막기 위해서입니다.

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
python -m pip install -r requirements.txt
python scripts/check_env.py --config
```

**스마트 가져오기 의존성**: `pypinyin`(이름→코드 병음 매칭)과 `openpyxl`(Excel .xlsx 해석)은 `requirements.txt`에 들어 있어, 위의 `pip install -r requirements.txt`를 실행하면 자동으로 설치됩니다. 스마트 가져오기(이미지/CSV/Excel/클립보드) 기능을 쓴다면 의존성이 제대로 설치되었는지 확인하세요. 없으면 `ModuleNotFoundError`가 날 수 있습니다.

### 명령줄 인수

```bash
python main.py                        # 전체 분석(개별 종목 + 시장 복기)
python main.py --market-review        # 시장 복기만
python main.py --no-market-review     # 개별 종목 분석만
python main.py --etf-rotation         # ETF 로테이션 신호 + 규칙 백테스트(LLM 호출 안 함, docs/etf-rotation.md 참고)
python main.py --stocks 600519,300750 # 종목 지정
python main.py --portfolio futu       # Futu 실제 LONG 보통주 보유 종목 사용(--stocks/STOCK_LIST 덮어씀)
python main.py --dry-run              # 데이터만 가져오고 AI 분석은 안 함
python main.py --no-notify            # 알림 보내지 않음
python main.py --schedule             # 예약 실행 모드
python main.py --force-run            # 비거래일에도 강제로 실행(Issue #373)
python main.py --debug                # 디버그 모드(자세한 로그)
python main.py --workers 5            # 동시 실행 수 지정
```

한국 주식은 `python main.py --stocks 005930.KS,035420.KS`처럼 `.KS`/`.KQ` 접미사를 붙여 지정합니다.

### 지수 일회성 분석(Phase 1)

`--stocks` 일회성 진입점은 등록된 SH, SZ, CSI 지수의 전체 분석을 지원합니다. 지수 대상은 `sh`/`sz` 접두사(예: `sh000016`)나 `.CSI` 별칭(예: `000300.CSI`, `930955.CSI`)으로 명시합니다. 접미사 없는 6자리 코드(예: `000016`)는 항상 종목으로 처리합니다.

```bash
# 상하이 50, CSI 300(후선 300), 고배당 저변동 100 세 지수를 한 번에 분석
python main.py --stocks sh000016,000300.CSI,930955.CSI
# 지수와 일반 종목을 한 번에 분석(000016은 종목으로 실행)
python main.py --stocks sh000016,000016
# 지수 데이터만 가져오고 AI 분석은 안 함
python main.py --stocks sh000016 --dry-run
```

지수 대상은 Pipeline 안에서 `market=cn`으로 시장 단계, 일봉 대상 날짜, 이어서 실행할 날짜, 과거 기간, `DecisionSignal`을 똑같이 처리합니다. 매물대, 기본적 분석, 섹터 소속, 자금 흐름, 룽후방, 회사 이벤트 같은 개별 종목 전용 모듈은 한꺼번에 건너뜁니다. 등록되지 않은 `.CSI` 입력(예: `930956.CSI`)은 시세 데이터 provider에 요청하기 전에 분명히 거부합니다. CLI `--stocks`와 Actions 일일 workflow는 등록되지 않은 대상이 하나라도 있으면 이번 실행 전체를 거부하며(같은 묶음의 어떤 대상도 실행하지 않음), Web/API는 비동기 일괄 요청에서 그 대상만 `rejected`로 보내고 동기/단일 종목 요청에는 4xx를 돌려줍니다. 검색과 리포트에는 등록표의 중국어 지수 이름을 쓰며, 기계용 코드는 붙이지 않습니다.

지수는 A주와 거래일 의미를 공유합니다. 거래일 확인을 켜면 등록 지수(`sh`/`sz` 접두사나 `.CSI` 별칭)는 `market=cn`으로 A주 휴장 필터에 참여하므로, A주 휴장일에는 지수도 건너뜁니다. 여전히 시장을 알 수 없는 지수가 아닌 code는 기존 fail-open 동작을 유지합니다. `--force-run`으로 비거래일에도 강제로 실행할 수 있습니다.

지수 실시간 시세는 별도의 고정 경로를 씁니다: Tencent → Sina → 둥팡차이푸 단일 종목 API → TickFlow. SH/SZ 지수는 `sh000016`/`sz399001` 같은 명시적 기호로 요청하고, CSI 지수는 둥팡차이푸 단일 종목 API만 제공합니다(`2.{code}` secid). 명시한 지수 신원은 끝까지 유지되며, 같은 코드의 종목 시세로 바뀌지 않습니다.

### 지수 Web/API 진입점(Phase 2 PR1)

웹 자동 완성과 검색에서 등록 지수를 쓸 수 있습니다. 등록된 중국어 이름(예: `上证50`)이나 명시적 코드(`sh000016`, `930955.CSI`)로 검색하면 해당 지수 항목이 나오고 분석을 제출할 수 있습니다. 인기 후보는 여전히 종목만 보여 주며(`assetType=stock`) 지수는 포함하지 않습니다.

API `/analyze`는 명시적 지수 입력에 대해 구조화된 `AnalysisTarget`을 만듭니다. `sh000016`은 `asset_type=INDEX`, `canonical_id=sh000016`으로 큐에 들어가고, `930955.CSI`/`csi930955`는 `csi930955`로 모입니다. 지수와 같은 코드의 개별 종목(예: `sh000016`과 `000016`)은 따로 중복 제거되고 따로 스케줄되며 서로 합쳐지지 않습니다. 등록되지 않은 CSI 입력(예: `930956.CSI`)은 비동기 단일 종목이나 동기 모드에서 분명한 4xx를 돌려주고, 비동기 일괄 요청에서는 그 대상만 응답의 `rejected` 목록에 들어가며 같은 묶음의 다른 대상은 정상적으로 큐에 들어갑니다. 중국어 이름 입력(예: `贵州茅台`)은 여전히 기존 종목 이름 해석을 거치며, 지수 판별에는 들어가지 않습니다.

Bot `/analyze`는 등록 지수의 명시적 코드(`sh000016`), CSI 별칭(`930955.CSI`), 등록된 중국어 이름(`上证50`)을 지원합니다. 지수는 registry canonical과 구조화된 `AnalysisTarget`으로 CLI/API와 같은 Pipeline에 들어갑니다. 등록되지 않은 CSI, 알 수 없는 이름, 모호한 등록 이름은 분명히 오류를 내고 작업을 제출하지 않습니다. 일반 A/HK/US 코드와 종목 이름은 계속 legacy code 경로를 씁니다.

### 지수 GitHub Actions 진입점(Phase 2 PR3)

GitHub Actions 일일 workflow(`.github/workflows/00-daily-analysis.yml`)는 `STOCK_LIST` 설정에 있는 명시적 지수 token을 개별 종목과 한 묶음으로 분석합니다. `GITHUB_ACTIONS=true` 환경에서 `python main.py`를 인수 없이 실행하면(`full`과 `stocks-only` 모드. `market-only`는 종목 목록을 거치지 않으므로 이 분류에 참여하지 않음), `STOCK_LIST`는 `--stocks`와 같은 판별 규칙에 따라 구조화된 target으로 분류됩니다. 명시적 지수 token(예: `sh000016`, `930955.CSI`)은 지수 경로로, 종목 token은 기존 경로로 가며, 두 번째 Pipeline이나 기능 행렬을 따로 만들지 않습니다. 등록되지 않은 `.CSI` 대상이 있으면 이번 실행 전체를 거부합니다. 로컬에서 인수 없이 실행하는 기본 경로(`.env`/Docker의 `STOCK_LIST`)와 `--schedule`/`config.schedule_enabled` 예약 모드는 이 분류에 참여하지 않습니다. 로컬 `--stocks`는 분류에 참여하지만, 로컬 무인수 기본 경로와 예약 모드는 `--stocks`로 targets를 만들지 않으며, `STOCK_LIST`의 다른 실행 환경 의미는 그대로입니다.

> **Phase 2 범위**: `--schedule`, Bot `/ask`, Bot `/batch`는 아직 지수 입력을 열지 않았습니다. Web/API, Bot `/analyze`, 일회성 `--stocks`, GitHub Actions 일일 workflow는 지수를 지원합니다.

<a id="指数自选股配置"></a>

### 지수 관심 종목 설정

`STOCK_LIST`에는 두 가지 진입점에서 아래 규칙에 따라 지수 대상을 섞어 넣을 수 있습니다. 일회성 `--stocks`와 GitHub Actions 일일 workflow(`GITHUB_ACTIONS=true`로 인수 없이 실행하는 full/stocks-only 모드)입니다. 로컬 `.env`나 Docker에서 인수 없이 실행하는 기본 경로는 지수 분류에 참여하지 않으며, `STOCK_LIST`는 기존 종목 의미를 유지합니다. 로컬 `.env`/Docker에서 지수를 분석하려면 `--stocks`를 명시하거나(일회성 실행) GitHub Actions 진입점을 쓰세요. 분류 판단은 종목 해석보다 먼저 합니다. 등록 지수의 명시적 형태와 일치하면 `market=cn`의 지수 Pipeline으로 실행하고, 일치하지 않으면 종목 경로로 계속 갑니다(`.CSI` 접두사는 예외, 아래 거부 규칙 참고). 판단은 **정규화하기 전에** 하므로, 반드시 명시적 코드 형태로 쓰고 접미사 없는 코드의 "자동 인식"에 기대지 마세요.

**쓸 수 있는 등록 지수 코드 형태:**

| 지수 계열 | canonical(등록 신원) | display / 같은 뜻의 명시적 표기 | 예시 |
|----------|----------------------|------------------------|------|
| 상하이(상하이/CSI 계열 중 SH 상장) | `sh` + 6자리 | `{code}.SH`(계열을 넘는 별칭도 있음. 예: `sz399300` → `sh000300`) | `sh000016`, `000016.SH`(상하이 50) |
| 선전(선전/궈정 계열) | `sz` + 6자리 | `{code}.SZ` | `sz399006`, `399006.SZ`(창업판 지수); `sz399365`, `399365.SZ`(궈정 식량) |
| CSI(중정 코드 구간) | `csi` + 6자리 | `{code}.CSI` | `csi930606`, `930606.CSI`(CSI 철강); `csi930955`, `930955.CSI`(고배당 저변동 100) |
| 미국 지수 | CN 등록표에 넣지 않음 | 접미사 없는 코드 그대로 | `NDX`(나스닥 100), `SPX`, `DJI` |

> 전체 목록은 `scripts/stock_index_seeds/index_registry.csv`를 기준으로 하며, 빌드 결과물 `apps/dsa-web/public/stocks.index.json`은 이 파일로 만듭니다(`python scripts/generate_index_from_csv.py --index-only`). SH/SZ 계열의 같은 뜻 접미사는 canonical과 같습니다. `csi` 계열의 canonical은 `csi930606`이고 같은 뜻의 명시적 표기는 `930606.CSI`입니다(둘 다 같은 지수로 모임).

**규칙과 올바른/잘못된 예시:**

- **등록된 코드의 명시적 형태로 써야 합니다**(접두사나 거래소 접미사). 등록되지 않은 코드 구간을 쓰면 전체 묶음이 거부되거나 종목으로 처리됩니다. 대소문자는 구분하지 않습니다. `930955.csi`, `CSI930955`, `930955.CSI`는 같습니다. 같은 지수의 canonical과 명시적 별칭/display도 같습니다(`csi930606`과 `930606.CSI`, `sz399365`와 `399365.SZ`). 거래소 접미사를 잘못 쓰면(예: `399365.SH`) 바로 unsupported 오류가 나며(그 접미사는 그 코드를 받지 않음), 접미사 없는 6자리 코드만 종목 경로로 돌아갑니다.
- **등록되지 않은 `.CSI` 대상은 전체 묶음 거부(`--stocks`와 GitHub Actions 진입점에만 해당)**: 등록되지 않은 `.CSI`(예: `930956.CSI`, `930606.CSI` 밖의 CSI 구간)가 들어 있는 `--stocks`나 GitHub Actions 일일 workflow의 `STOCK_LIST`는 이번 실행 전체를 거부하며, 어떤 대상도 실행하지 않습니다. 로컬 `.env`/Docker 무인수 기본 경로는 지수 분류에 참여하지 않으므로 이런 전체 거부가 없습니다. Web/API 비동기 일괄 요청은 그 대상만 거부하고, 동기/단일 종목 요청에는 4xx를 돌려줍니다(아래 Web/API 지수 진입점 절의 rejected 목록 의미 참고). 거래소 접미사를 잘못 쓰면(예: `399365.SH`) 마찬가지로 바로 unsupported 오류가 납니다.
- **접미사 없는 코드는 지수로 자동으로 올라가지 않습니다**: 접미사 없는 `399365` / `930606` / `000016` 같은 6자리 코드는 모두 종목 경로로 처리하며("접미사 없는 코드는 기본으로 종목" 계약 유지), 모호하다는 안내만 남깁니다. 주의: SZ 계열 지수(예: `sz399365`)는 종목 canonical과 지수 canonical이 모두 `sz{code}` 접두사 형태라서, 같은 코드의 종목과 지수가 같은 저장 키 공간을 씁니다. 관심 종목에 섞어 넣을 때는 아래 canonical 분리 절의 합쳐지는 동작을 확인하세요.
- **NDX 같은 미국 지수는 접미사 없이 쓰는 것이 맞습니다**: 이들은 `us_index_mapping`의 전용 미국 지수 라우팅을 쓰므로, CN 접두사/접미사(예: `NDX.US`, `usNDX`)를 붙이지 **마세요**. 붙이면 오히려 종목 경로로 갈 수 있습니다.
- **ETF(예: 159934 금 ETF, XOP)는 지수 등록표에 들어가지 않습니다**: ETF는 종목 경로를 쓰며, 같은 숫자로 시작하는 지수와 관계없습니다. 접미사 없는 코드를 그대로 쓰면 되며, 지수 접두사는 필요 없고 지원하지도 않습니다.

**설정 예시(`STOCK_LIST`, 쉼표로 구분):**

```text
600519,sh000016,930606.CSI,sz399365,159934,NDX
```

위 예시는 개별 종목(600519 구이저우마오타이), 상하이 지수(sh000016), CSI 지수(930606.CSI), SZ 지수(sz399365), A주 ETF(159934, 종목 경로), 미국 지수(NDX, 미국 지수 라우팅)를 섞어 놓은 것입니다. 묶음에 등록되지 않은 `.CSI`가 있으면 전체가 실행되지 않으므로, **지수마다 등록표를 먼저 확인한 뒤 설정하는 것을 권장합니다**.

### 지수와 개별 종목 Dashboard canonical 분리(PR #2312)

등록 지수는 소문자 canonical(`sh000016`/`sz399001`/`csi930955`)로 이력 저장소에 기록됩니다. 이력 필터, 코드별 삭제, 개수 세기, 종목 바(stock-bar) 집계는 모두 parser 판별을 써서, 지수 기록과 같은 코드의 접미사 없는 종목(예: `000016`)을 엄격히 분리하고 서로 합치지 않습니다. 예외: SZ 계열 지수(예: `sz399365`)는 접미사 없는 종목의 canonical과 지수 canonical이 모두 `sz{code}` 접두사 형태라서(접미사 없는 `399365`를 종목으로 해석하면 canonical이 바로 `sz399365`) 둘이 자연스럽게 같은 키를 씁니다. 이 계열의 같은 코드 종목과 지수 기록은 위 분리 범위에 들지 않으며, 관심 종목에 섞으면 같은 키로 합쳐집니다.

- **이력 후보**: 지수 조회(`sh000016`, `SH000016`, `000016.SH`, `sz399001`, `csi930955`, `930955.CSI` 같은 명시적 형태)는 소문자 canonical, 대문자 legacy canonical, 명시적 별칭의 기존 기록과 일치하지만, 접미사 없는 같은 코드의 종목 기록과는 **일치하지 않습니다**. 접미사 없는 코드 조회(`000016`/`930955`)도 지수 기록과 일치하지 않습니다. 종목 별칭, 홍콩 주식, 해외 시장의 기존 같은 뜻 매칭은 그대로입니다.
- **삭제와 개수 세기**: `DELETE /api/v1/history/by-code/{code}`와 이력 총수는 지수 canonical에 대해 모든 명시적 형태를 하나로 모읍니다. 기록이 없어도 `deleted=0`을 돌려주며, 기존 동작을 깨는 404를 도입하지 않습니다.
- **종목 바**: 같은 지수의 `sh000016`/`SH000016`/`000016.SH` 예전 기록은 `/history/stocks`에서 한 줄로 합쳐 모든 명시적 형태를 세며, 접미사 없는 `000016` 종목 줄과는 나란히 존재하고 합쳐지지 않습니다. stock-bar 판별은 저장된 `record.code`에서 오며, display code로 거꾸로 추정하지 않습니다.
- **API `stock_code`는 canonical로 출력**: 이력 목록, 이력 상세, stock-bar는 등록 지수(예전 대문자/명시적 별칭으로 저장된 기록, 예: `SZ399300`, `000300.CSI` 포함)에 대해 항상 parser canonical(`sh000300`/`csi930955`)을 출력하므로, 프런트엔드가 별칭으로 canonical을 추측할 필요가 없습니다.
- **작업 / SSE / API 메타데이터**: 작업 목록과 SSE 이벤트는 제출된 `analysis_target`에 대해 선택적 `asset_type`(`stock`/`index`)을 드러내며, 다시 추측하지 않습니다. 이력 목록 항목과 stock-bar 항목에도 선택적 `asset_type`을 덧붙입니다. 이 필드를 모르는 예전 클라이언트는 그냥 무시하면 되며, 선택 필드를 덧붙이는 것이라 기존 계약을 깨지 않습니다.
- **웹 Dashboard 식별 키**: 작업/리포트/이력의 `assetType`을 우선하며, 백엔드가 parser canonical을 보장한 코드는 **대소문자만 맞춥니다**(`SH000016`→`sh000016`). 접두사/접미사 정규식으로 canonical을 다시 추측하는 것은 **금지**합니다(그렇게 하면 `000300.CSI`를 `csi000300`으로, `sz399300`을 별도 canonical로 잘못 판단해, 등록표가 유일한 판별 기준이라는 원칙을 어깁니다). watchlist 원본 문자열에 유형이 없을 때만, 불러온 `stocks.index.json`에서 `assetType=index`인 행의 canonical/display/명시적 별칭과 **정확히 일치**하는지 봅니다(먼저 normalize한 뒤 매칭하지 않으며, 접두사 정규식으로 추측하지 않음. 불러오는 동안에는 일괄 분석을 막고, 불러오기에 실패하거나 요청이 10초를 넘으면 기존 종목 의미로 fail-open). 행 선택, active task, 완료 후 자동 선택은 모두 자산 유형별로 나눠서, 지수 행과 같은 코드의 종목 행 상태가 서로 독립적이며, 완료 후에는 올바른 canonical 지수 리포트를 자동으로 선택합니다.

### Futu 실제 보유 종목을 분석 목록으로 쓰기

표준 소스 설치(`pip install -r requirements.txt`), 공식 Docker 이미지, Windows/macOS Desktop backend에는 고정된 `futu-api==10.8.6808`이 기본으로 들어 있습니다. 직접 줄인 사용자 정의 Python 환경을 쓸 때만 [Futu OpenAPI SDK 설치 안내](https://openapi.futunn.com/futu-api-doc/en/intro/intro.html)에 따라 따로 설치하면 됩니다. Futu OpenD를 실행하고 로그인한 뒤 다음을 실행합니다.

```bash
# 직접 줄인 사용자 정의 환경에서만 다음 줄을 실행
pip install "futu-api==10.8.6808"
# 표준 설치라면 바로 실행
python main.py --portfolio futu
```

`--portfolio futu`는 상태가 분명히 `ACTIVE`인 `REAL` 실제 증권 계좌만 읽으며, 분석을 시작할 때마다 `refresh_cache=True`로 보유 종목을 새로 고칩니다. 상태가 없거나 `N/A`, 알 수 없음, `DISABLED`인 계좌는 모두 거부합니다. `FUTU_ACC_ID`를 설정하지 않으면 쓸 수 있는 `NORMAL`(일반)과 `MASTER`(주) 증권 계좌를 모두 합치고 코드로 중복을 없앱니다. 설정하면 지정한 양의 정수 계좌 ID만 읽습니다. [Futu `get_acc_list` 계좌 역할 정의](https://openapi.futunn.com/futu-api-doc/trade/get-acc-list.html)에 따르면 `MASTER`는 주 계좌를 뜻할 뿐 읽기 전용 속성이 아니며, 말레이시아 `IPO` 계좌는 이 기능의 보유 종목 출처가 아니라서 건너뜁니다. 이 연동의 읽기 전용 범위는 조회 API만 호출한다는 데서 나옵니다.

보유 방향이 분명히 `LONG`이고, Futu 정적 유형이 `STOCK`이며, 수량이 0이 아닌 보통주 보유 종목만 분석에 들어갑니다. `SHORT`, 방향을 알 수 없는 것, 옵션, ETF, 워런트, 선물 같은 보유 종목은 뺍니다. Futu 보유 종목 코드 변환은 상하이·선전 A주, 홍콩 주식, 미국 주식만 지원합니다. 상하이·선전 B주, 일본 주식, 그 밖의 Futu 시장 보유 종목은 로그에 코드를 남기고 건너뛰며, 이는 직접 입력한 종목 목록의 기존 시장 지원 범위를 바꾸지 않습니다. 쓸 수 있는 계좌 ID가 잘못되었거나, `LONG` 보유 수량이 잘못되었거나, 0이 아닌 `LONG` 보유 코드가 잘못되었거나, 정적 유형이 없거나 알 수 없거나, 확인된 보통주 코드를 현재 분석 형식으로 바꿀 수 없으면 보유 종목 가져오기 전체를 분명히 실패시키며, 조용히 잘린 일부 결과를 돌려주지 않습니다.

OpenD 기본 주소는 `127.0.0.1:11111`이며, `FUTU_OPEND_HOST` / `FUTU_OPEND_PORT`로 바꿀 수 있습니다. 고정된 `futu-api==10.8.6808`의 네트워크 계층은 IPv4 socket을 쓰므로, `FUTU_OPEND_HOST`에는 IPv4 주소나 IPv4로 해석되는 호스트 이름을 넣어야 하며, `::1` 같은 IPv6 주소는 지원하지 않습니다. Docker 컨테이너 안에서 `127.0.0.1`은 컨테이너 자신을 가리킵니다. OpenD가 호스트에서 실행 중이라면 macOS / Windows에서는 `FUTU_OPEND_HOST=host.docker.internal`로 설정하고, Linux에서는 먼저 컨테이너에 `host.docker.internal:host-gateway` 매핑을 추가한 뒤 이 호스트 이름을 씁니다. 다른 컴퓨터에 연결하면 실제 계좌와 보유 종목 정보가 전송됩니다. [Futu 공식 문서는 실거래 연결에 프로토콜 암호화를 설정하라고 권합니다](https://openapi.futunn.com/futu-api-doc/en/ftapi/protocol.html). 이 기능은 프로세스 단위 SDK 암호화 설정을 바꾸지 않으므로, OpenD와 이 프로그램을 같은 컴퓨터에서 실행하거나, 믿을 수 있는 네트워크 / 로컬 포트 포워딩을 쓰는 것을 권장합니다. `FUTU_SECURITY_FIRM`을 설정하지 않으면 Futu SDK 공식 `SecurityFirm.NONE` 자동 인식만 한 번 쓰며, 여러 증권사를 하나씩 시도하거나 일부 확인이 실패한 뒤 결과를 몰래 이어 붙이지 않습니다. 증권사를 고정하려면 이 변수를 명시하세요.

`--stocks`를 함께 넘기면 Futu 보유 종목이 우선합니다. 예약 모드는 매번 실행하기 전에 실제 보유 종목을 다시 읽으며, 시작 시의 스냅샷을 재사용하지 않습니다. 조건에 맞는 Futu 보유 종목이 없으면 이번에는 개별 종목 분석을 건너뛰고 `STOCK_LIST`로 돌아가지 않습니다. 켜져 있는 시장 복기는 원래 설정대로 실행하고, 시장 복기도 요청하지 않았다면 종목 인덱스를 새로 고치거나 분석 파이프라인을 만들지 않습니다. 켜져 있는 자동 백테스트는 여전히 독립된 단계로 실행합니다. 단발성 CLI는 SDK, OpenD, 계좌 찾기, 보유 종목 읽기, 증권 분류 같은 보유 종목 해석 단계에서 실패했을 때만 0이 아닌 종료 코드를 돌려줍니다. 보유 종목 해석이 성공한 뒤의 거래일 달력, 분석 파이프라인, 리포트 예외는 원래 분석 흐름의 기록과 허용 방식을 따릅니다. 이미 실행 중인 서비스와 예약 스케줄은 보유 종목 가져오기 오류를 기록하고 계속 실행합니다. 이 기능은 계좌와 보유 종목만 읽으며, 주문, 주문 수정, 주문 취소, 거래 잠금 해제는 하지 않습니다. 기존 분석 로그에는 이번 실행의 종목 코드가 남지만 계좌 ID, 보유 수량, 원가, 자금은 남지 않습니다. 실행 로그를 공유하기 전에 필요하면 민감 정보를 가리세요.

---

<a id="定时任务配置"></a>

## 예약 실행 설정
<!-- 계약 키(tests): 不改变 Prompt / 最终报告阶段仍以 `report.meta.market_phase_summary.phase` 为准 / `AnalysisContextBuilder` 只映射这些上游 artifact / 不公开完整 pack / 文档、配置与迁移说明（Issue #1386 P7） / 不关闭当次 `AnalysisContextPack` 构建 / 同步分析响应也会读取本次已落库的 `analysis_history.context_snapshot` 提取 overview / 当前没有运行时 pack 总开关 / 回测查询支持 `analysis_phase=premarket|intraday|postmarket|unknown` / Bot / CLI / schedule / 默认 GitHub Actions / 生成开盘计划和观察条件 / 旧调用不传 `analysis_phase` 时保持兼容 / 盘中 / 午间 / 临近收盘 / 非零的其他状态计数 / 只消费公开 `market_phase_summary` 和低敏 `analysis_context_pack_overview` / daily_bars` block 仍表示 storage 中完整日线窗口 / 做实时状态判断、风险和机会提醒 / `details.context_snapshot` 会剥离顶层 `market_phase_summary` / 运行时 pack 总开关 / 不公开完整 pack、Prompt summary、新闻正文或持仓敏感明细 / AnalysisContextPack 文档、迁移与回滚（Issue #1389 P6） / 折叠头部展示可用数、缺失数、非零的其他状态计数和触发来源 / 既有 `news_context`、Agent pre-fetched JSON 和 `enhanced_context` 原始数据通道保持 P3 前行为 / 最终报告页展示最终阶段标签 / 需要发布回滚或代码回滚 / `SAVE_CONTEXT_SNAPSHOT` 是既有环境变量 / source` 保留实际成功的数据源 token / 盘中决策护栏与质量校验（Issue #1386 P5） / Web 端报告页在“策略点位”和“资讯”之后展示默认折叠的数据块摘要 / 不持久化整份 `analysis_history.context_snapshot` / 盘前 / 盘中 / 盘后分析 / AnalysisContextPack 数据质量评分与 Prompt 数据限制（Issue #1389 P5） / 不会通过该区块看到完整 `news.content` / 质量分/等级 / 盘中数据包与实时质量控制（Issue #1386 P3） / ### 告警 / `fetch_failed` 状态 / Web 主分析 / 重新分析 / 持仓手动分析 / 低敏 `analysis_context_pack_summary` / `details.context_snapshot` 会剥离顶层 `analysis_context_pack_overview` / 不覆盖 pending/processing TaskPanel / 默认折叠 / 当前没有阶段覆盖 selector / 折叠头部新增质量分/等级 / 进行中任务面板展示请求阶段 / 在这个新增的 pack 摘要区块中 / `SAVE_CONTEXT_SNAPSHOT=false` 时新记录不保证返回该字段 -->

### GitHub Actions 예약

`.github/workflows/00-daily-analysis.yml`을 편집합니다.

```yaml
schedule:
  # UTC 시간, 베이징 시간 = UTC + 8 (한국 시간 = UTC + 9)
  - cron: '0 10 * * 1-5'   # 월요일~금요일 18:00(베이징 시간)
```

자주 쓰는 시간 대조표:

| 베이징 시간 | UTC cron 식 |
|---------|----------------|
| 09:30 | `'30 1 * * 1-5'` |
| 12:00 | `'0 4 * * 1-5'` |
| 15:00 | `'0 7 * * 1-5'` |
| 18:00 | `'0 10 * * 1-5'` |
| 21:00 | `'0 13 * * 1-5'` |

(한국 시간으로 맞추려면 한국 시간에서 9시간을 빼서 UTC로 바꾸면 됩니다. 예: 한국 시간 16:00 → `'0 7 * * 1-5'`.)

#### GitHub Actions 비거래일 직접 실행(Issue #461 / #466)

`00-daily-analysis.yml`은 두 가지 제어 방식을 지원합니다.

- `TRADING_DAY_CHECK_ENABLED`: 저장소 단위 설정(`Settings → Secrets and variables → Actions`), 기본 `true`
- `workflow_dispatch.force_run`: 직접 실행할 때의 일회성 스위치, 기본 `false`

우선순위는 이렇게 이해하면 됩니다.

| 설정 조합 | 비거래일 동작 |
|---------|-------------|
| `TRADING_DAY_CHECK_ENABLED=true` + `force_run=false` | 실행 건너뜀(기본 동작) |
| `TRADING_DAY_CHECK_ENABLED=true` + `force_run=true` | 이번에는 강제 실행 |
| `TRADING_DAY_CHECK_ENABLED=false` + `force_run=false` | 항상 실행(예약과 직접 실행 모두 거래일을 확인하지 않음) |
| `TRADING_DAY_CHECK_ENABLED=false` + `force_run=true` | 항상 실행 |

직접 실행 순서:

1. `Actions → 每日股票分析 → Run workflow`를 엽니다(`每日股票分析`는 "일일 주식 분석" workflow 이름입니다)
2. `mode`(`full` / `market-only` / `stocks-only`)를 고릅니다
3. 오늘이 비거래일인데도 실행하고 싶다면 `force_run`을 `true`로 둡니다
4. `Run workflow`를 누릅니다

### 로컬 예약 실행

내장된 예약 실행 스케줄러는 매일 지정한 시각(기본 18:00)에 분석을 실행할 수 있습니다.

#### 명령줄 방식

```bash
# 예약 모드 시작(시작할 때 바로 한 번 실행하고, 이후 매일 18:00에 실행)
python main.py --schedule

# 예약 모드 시작(시작할 때는 실행하지 않고 다음 예약 시각만 기다림)
python main.py --schedule --no-run-immediately
```

> 안내: 예약 모드는 실행할 때마다 현재 저장된 `STOCK_LIST`를 다시 읽습니다. `--stocks`를 함께 넘겨도 이후 예약 실행의 종목 목록이 고정되지 않으므로, 특정 종목만 잠깐 돌리려면 예약이 아닌 단발성 실행 명령을 쓰세요.
>
> `python main.py --schedule`이나 같은 순수 CLI 스케줄 모드로 시작한 뒤 WebUI에서 새 `SCHEDULE_TIME` / `SCHEDULE_TIMES`를 저장하면, 다음 스케줄 확인 때 daily jobs를 자동으로 다시 묶으므로 프로세스를 다시 시작할 필요가 없습니다. 예전 실행 시각은 남지 않습니다. `python main.py --serve --schedule`은 Web/API runtime scheduler가 예약 실행을 맡으며, WebUI/API/Desktop처럼 오래 실행되는 프로세스에서 `SCHEDULE_ENABLED`, `SCHEDULE_TIME`, `SCHEDULE_TIMES`를 저장하면 현재 설정에 따라 runtime scheduler를 켜고 끄거나 다시 만듭니다. `python main.py --serve-only`나 Desktop을 다시 시작하면 켜져 있던 daily jobs가 자동으로 복구되지만, 서비스 시작 자체가 바로 분석을 실행하지는 않습니다.
>
> Web/API runtime scheduler의 즉시 실행 진입점은 실행 중인 분석 작업이 없을 때만 요청을 받습니다. 이미 분석이 진행 중이면 대기열에 넣은 척하지 않고 바쁨 상태를 돌려줍니다.

#### 환경 변수 방식

환경 변수로 예약 동작을 설정할 수도 있습니다(Docker나 .env에 알맞음).

| 변수 이름 | 설명 | 기본값 | 예시 |
|--------|------|:-------:|:-----:|
| `SCHEDULE_ENABLED` | 예약 실행 사용 여부 | `false` | `true` |
| `SCHEDULE_TIME` | 매일 실행 시각(HH:MM) | `18:00` | `09:30` |
| `SCHEDULE_TIMES` | 여러 매일 실행 시각, 쉼표로 구분. 비어 있으면 `SCHEDULE_TIME`을 씀 | 비어 있음 | `09:20,12:30,15:10,18:00` |
| `DSA_RUNTIME_SCHEDULER_TIMEOUT_SECONDS` | Web/API runtime scheduler의 분석 1회 엄격 시간 초과(초, 최소 60초) | `2700` | `3600` |
| `DSA_TIMEOUT_PARTIAL_NOTIFY` | **기본으로 켜짐(동작 변경)**: 엄격 시간 초과 뒤 이미 저장된 개별 종목의 부분 완료 알림을 보낼지 여부. 예전에는 시간 초과 시 알림을 보내지 않았음 | `true` | `false` |
| `SCHEDULE_RUN_IMMEDIATELY` | 예약 모드 시작 시 바로 한 번 실행할지 여부. 명시하지 않으면 `RUN_IMMEDIATELY`의 실행 시 덮어쓰기 의미를 따름 | `true` | `false` |
| `SCHEDULE_STARTUP_DEDUP` | 예약 모드 시작 즉시 실행의 같은 날 중복 방지: 그날 이미 성공했고 지금 분석해야 할 목록을 모두 다룬 전체 분석 기록이 있으면(날짜 + scope=full + 범위 부분 집합 판정. 표시는 `DATABASE_PATH`가 있는 디렉터리에 있으며 기본 `data/analysis_run_state.json`) 이번 시작 시 보충 실행을 건너뜀. 매일 예약 실행과 직접/API/GitHub Actions 실행은 중복 방지를 하지 않음. 표시가 없거나, 손상되었거나, schema를 알 수 없거나, 범위가 부족하면 모두 실행을 허용(fail-open)하며, v1 예전 표시도 업그레이드를 위해 한 번 허용함. 종목 목록 지문은 관찰용일 뿐 판정에 쓰지 않음. 시장 복기 완료 여부도 기록만 하고 판정에 쓰지 않음 | `true` | `false` |
| `RUN_IMMEDIATELY` | 예약 모드가 아닐 때 시작 시 바로 한 번 실행할지 여부. `SCHEDULE_RUN_IMMEDIATELY`를 명시하지 않았을 때의 legacy 대체 값도 됨 | `true` | `false` |
| `TRADING_DAY_CHECK_ENABLED` | 거래일 확인: 비거래일에는 실행을 건너뜀. `false`로 두면 강제 실행 | `true` | `false` |

> 시간 초과 부분 완료 문제 해결: 알림 채널 이상은 warning(`Partial timeout notification failed`)만 남기고 발송을 건너뛰며, **예외를 던지지 않고 `status().running`을 차지하지도 않습니다**(notify는 분석 잠금이 풀린 뒤의 백그라운드 스레드에서 실행). DB 조회 / `src.storage` 가져오기 실패도 fail-open합니다. API에는 여전히 baseline `timed out after Ns`로 남거나, `completed=0`으로 보강될 수 있습니다(「정말로 저장된 것이 없음」과 구분할 수 없음). 운영할 때는 `Failed to collect completed analyses after timeout`, `Timeout partial delivery failed open`, `Partial timeout notification failed`로 검색하세요. 병합 후 처음 배포할 때는 알림 양을 지켜봐서, 기본으로 켜진 설정이 불편을 주지 않게 하세요. `DSA_TIMEOUT_PARTIAL_NOTIFY=false`로 발송을 끌 수 있습니다.

예를 들어 Docker에서는 이렇게 설정합니다.

```bash
# 시작할 때 바로 분석하지 않도록 설정
docker run -e SCHEDULE_ENABLED=true -e SCHEDULE_RUN_IMMEDIATELY=false ...
```

> 호환 안내: 실행할 때 `RUN_IMMEDIATELY`를 명시했지만 `SCHEDULE_RUN_IMMEDIATELY`를 따로 넘기지 않았다면, 내장 스케줄 모드는 앞의 값을 계속 이어받아 `.env`에 저장된 `SCHEDULE_RUN_IMMEDIATELY` 예전 값에 거꾸로 덮이지 않게 합니다.

> 호환 안내(Issue #1815): `MARKET_REVIEW_REGION=cn|hk|us|jp|kr|both`는 시장 복기 입력 범위만 넓힙니다. 일본/한국은 복기 맥락에서만 쓰이며, Market Light 경고를 열지 않습니다.
> - `src/config.py`, `src/core/config_registry.py`, `src/services/system_config_service.py`의 변경은 설정 의미 확장일 뿐이며, `provider`/`model`/`base_url`의 실행 라우팅을 바꾸지 않고 provider/model/base URL 마이그레이션이나 정리 로직도 실행하지 않습니다.
> - 이번에 실제로 다루는 설정 항목: `MARKET_REVIEW_REGION`, `MARKET_REVIEW_COLOR_SCHEME`. `LITELLM_MODEL`, `AGENT_LITELLM_MODEL`, `LITELLM_FALLBACK_MODELS`, `VISION_MODEL`, `OPENAI_BASE_URL` 등의 예전 값은 원자적 upsert 의미를 유지하며, 다른 필드를 갱신할 때 몰래 지워지거나 덮이지 않습니다.
> - 확인할 수 있는 근거 요약: 공식 provider / Base URL / 모델 이름 출처는 [LLM 설정 가이드](LLM_CONFIG_GUIDE.md#常用官方文档来源用于核对预设-provider--base-url--模型命名)를 따르고, 현재 실행 의존성 범위는 `requirements.txt`의 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`을 따릅니다. 이번에는 설정 마이그레이션 스크립트나 정리 분기를 추가하지 않으며, 저장/가져오기는 여전히 이번에 제출한 키만 씁니다. `tests/test_system_config_service.py::SystemConfigServiceTestCase::test_update_market_review_region_does_not_trigger_runtime_model_cleanup`는 `MARKET_REVIEW_REGION`만 저장할 때 `LITELLM_CONFIG`, `LLM_CHANNELS`, `LLM_OPENAI_*`, `LITELLM_MODEL`, `AGENT_LITELLM_MODEL`, `LITELLM_FALLBACK_MODELS`, `VISION_MODEL`, `OPENAI_*` 같은 예전 설정을 지우거나 고쳐 쓰지 않는지 확인합니다.
> - 예전 값 되돌리기 방법: 백업한 `MARKET_REVIEW_REGION`과 설정 파일을 복원하면 예전 범위로 돌아가며, 제출하지 않은 모델/라우팅 키는 원래 값을 유지합니다. 필요하면 PR을 `revert`하고 `.env` 백업으로 되돌립니다.
> - 롤백 경로: 커밋 전의 `.env` / 설정 백업에 있는 `MARKET_REVIEW_REGION`과 관련 실행 변수를 복원하거나, 이 PR을 바로 revert합니다.

#### 거래일 판단(Issue #373)

기본으로 관심 종목의 시장(A주 / 홍콩 주식 / 미국 주식 / 일본 주식 / 한국 주식)과 `MARKET_REVIEW_REGION`에 따라 거래일인지 판단합니다.
- `exchange-calendars`로 A주 / 홍콩 주식 / 미국 주식 / 일본 주식 / 한국 주식 각각의 거래일 달력(공휴일 포함)을 구분합니다
- 여러 시장 종목을 섞어 보유하면, 종목마다 자기 시장이 열린 날에만 분석하고, 휴장인 종목은 그날 건너뜁니다
- 관련된 모든 시장이 비거래일이면 전체 실행을 건너뜁니다(pipeline을 시작하지 않고 알림도 보내지 않음)
- 이어서 실행하기와 `--dry-run`의 "데이터가 이미 있음" 판단은 같은 "최신 재사용 가능 거래일" 해석 로직을 함께 쓰며, 더 이상 서버의 달력 날짜를 그대로 쓰지 않습니다
- `最新可复用交易日`(최신 재사용 가능 거래일)은 종목이 속한 시장의 현지 시간대로 해석합니다. A주는 `Asia/Shanghai`, 홍콩 주식은 `Asia/Hong_Kong`, 미국 주식은 `America/New_York`, 일본 주식은 `Asia/Tokyo`, 한국 주식은 `Asia/Seoul`을 씁니다
- 비거래일(주말 / 공휴일)에 실행하면 가장 최근 거래일로 돌아가 로컬 데이터를 확인합니다. 그 거래일 데이터가 이미 있으면 중복 수집을 건너뛰고, 없으면 계속 채웁니다
- 거래일 장중이나 마감 전에 실행하면 바로 전에 끝난 거래일을 재사용 대상으로 삼습니다. 거래일 마감 후에 실행하면 그날 데이터가 이미 있을 때 바로 건너뛰고, 없으면 계속 수집합니다
- 무시하는 방법: `TRADING_DAY_CHECK_ENABLED=false` 또는 명령줄 `--force-run`

#### 시장 단계 기준(Issue #1386 P0)

P0은 내부 시장 단계 추정 기준만 새로 추가하며, 기존 일일 장 마감 리포트, 거래일 건너뛰기, 이어서 실행하기, API, 웹, Bot, Agent, GitHub Actions 기본 동작은 바꾸지 않습니다. 단계 추정은 이후 P1+의 맥락 계약을 준비하는 데 쓰입니다. `exchange-calendars`가 설치되지 않았거나 달력에 이상이 있으면 단계는 `unknown`이 되지만, 기존 거래일 판단과 최신 재사용 가능 거래일 로직은 원래의 fail-open 동작을 유지합니다.

단계 열거값은 정규 거래 시간(regular session) 의미를 기준으로 합니다.

| 단계 | 의미 |
| --- | --- |
| `premarket` | 정규 거래 시간 개장 전. 장전 시간외 시세를 이미 받았다는 뜻은 아님 |
| `intraday` | 정규 거래 시간 중이며, 점심 휴장이나 마감 직전 구간이 아님 |
| `lunch_break` | 시장 달력이 제공하는 점심 휴장 구간. 점심 휴장이 없는 시장은 이 단계에 들어가지 않음 |
| `closing_auction` | 마감 직전 추정 구간: A주 3분, 홍콩 주식 10분, 미국 주식 5분, 대만 주식 5분(13:25–13:30). 거래소 단일가 매매 제도 전체를 뜻하지는 않음 |
| `postmarket` | 정규 거래 시간 마감 후. 장후 시간외 시세를 이미 받았다는 뜻은 아님 |
| `non_trading` | 해당 시장의 현지 날짜가 거래일이 아님 |
| `unknown` | 알 수 없는 시장, 달력을 쓸 수 없음, 달력 이상으로 단계를 믿을 만하게 추정할 수 없음 |

현재 진입점 상황:

- 일반 개별 종목 분석, Agent 분석, 웹 직접 분석, Bot `/analyze` / `/ask`, schedule, GitHub Actions는 여전히 기존 분석 경로와 장 마감 후 복기 기준을 쓰며, P0 단계 기준 때문에 Prompt나 출력 구조가 자동으로 바뀌지 않습니다.
- 시장 복기는 여전히 `MARKET_REVIEW_REGION`과 거래일 필터에 따라 실행되며, 시장 단계 태그를 쓰지 않습니다.
- 여러 시장 관심 종목을 섞었다면 symbol마다 자기 시장으로 단계를 따로 추정해야 합니다. 통합 리포트에서 "여러 시장의 단계가 서로 다름"을 보여 주는 것은 P1+로 남겨 둡니다.

알려진 문제 기준:

- 장중에 실행하면 아직 마감하지 않은 장중 시세를 하루 전체를 복기하듯 쓸 수 있습니다.
- 출력이 "지금 장중 다음에 볼 것"보다 "오늘 흐름 복기 / 내일 주목할 점" 쪽으로 기울 수 있습니다.
- 실시간 시세 타임스탬프, 데이터 소스, 캐시, stale 상태가 아직 단계 맥락에 통일되어 들어가지 않았습니다.
- 점심 휴장, 마감 직전, 비거래일 강제 실행 같은 상황이 아직 Prompt와 리포트 구조에 명시적으로 표현되지 않습니다.

P0이 하지 않는 것: pipeline / Agent / API / 웹 / Bot에 연결하지 않고, 리포트 schema를 바꾸지 않으며, 경고 technical indicator의 partial bar 판단을 바꾸지 않고, 설정 항목도 추가하지 않습니다.

#### 실행 중 시장 단계 맥락(Issue #1386 P1a)

P1a는 일반 개별 종목 분석 pipeline, legacy Agent context, multi-agent `ctx.meta`에서 내부 `market_phase_context`를 만들어 넘깁니다. 이 맥락에는 시장, 단계, 시장 현지 날짜, 최신 재사용 가능 일봉 날짜, 거래일/개장/partial bar 세 가지 상태 표시, 개장·마감까지 남은 분의 best-effort 추정, 그리고 `unknown_market`, `calendar_unavailable`, `calendar_error` 같은 기능 저하 warning code가 들어 있습니다.

P1a 자체는 Prompt 문구, API/웹/Bot 매개변수, 리포트 구조, history/task status의 고정 metadata, quote freshness/data quality 의미를 바꾸지 않습니다. 일반 분석 history snapshot과 Agent history snapshot에서는 이 실행 중 필드를 빼고 저장합니다. 저장할 수 있는 metadata와 작업 상태 표시 계약은 이후 P1b에서 정합니다.

#### 시장 단계 저민감 Metadata(Issue #1386 P1b)

P1b는 P1a의 runtime `market_phase_context`를 안정적이고 민감도 낮은 공개용 `market_phase_summary`로 바꿔 `analysis_history.context_snapshot` 최상위에 기록합니다. 이력 상세, 동기 분석 응답, completed `/api/v1/analysis/status/{task_id}`는 모두 `report.meta.market_phase_summary`로 같은 시장 단계 메타 정보를 돌려줍니다. completed 작업 상태에는 `TaskStatus` 최상위 필드를 새로 넣지 않고, `status.result.report.meta.market_phase_summary`로만 간접적으로 드러냅니다.

`market_phase_summary`에는 시장, 단계, 시장 현지 시각, session date, effective daily-bar date, 거래일/개장/partial-bar 표시, 개장·마감까지 남은 분, 실행 출처, 분석 의도, warning code만 들어 있습니다. 전체 `market_phase_context`는 드러내지 않으며, quote freshness, fallback, stale, data_quality scoring 필드도 넣지 않습니다. `report.details.analysis_context_pack_overview`는 여전히 #1389 입력 데이터 블록의 품질 요약을 뜻합니다. API가 돌려주는 `details.context_snapshot`은 최상위 `market_phase_summary`와 `analysis_context_pack_overview`를 빼서, raw snapshot이 이 안정 공개 필드를 중복으로 보여 주지 않게 합니다. `SAVE_CONTEXT_SNAPSHOT=false`이면 `analysis_history.context_snapshot` 전체를 저장하지 않으며, summary가 없는 예전 이력 기록은 이 필드가 비어 있지만 리포트는 정상적으로 돌려줍니다.

P1b는 Prompt를 바꾸지 않고, `analysis_phase` 요청 매개변수를 추가하지 않으며, 웹 단계 태그나 페이지 표시도 하지 않습니다. pending/processing TaskPanel, SSE 진행 중 이벤트, Bot, 알림, `market_review`, P3 장중 데이터 품질 필드도 다루지 않습니다.

#### 시장 단계 Prompt 주입(Issue #1386 P2-min)

P2-min부터는 `market_phase_context`를 얻은 분석 경로에서 실행 중 시장 단계를 LLM이 읽을 수 있는 Prompt 블록으로 렌더링합니다. 일반 분석, single Agent, multi-agent는 Prompt에서 현재 단계, 시장 현지 시각, 최신 재사용 가능 완성 일봉 날짜, 최소한의 단계 제약을 보게 됩니다. 장 시작 전에는 "오늘 흐름이 이미 나타났다"고 쓰면 안 되고, 장중 / 점심 휴장 / 마감 직전에는 마지막 일봉이 아직 완성되지 않았을 수 있다고 밝혀야 하며, 장 마감 후에는 하루 전체 복기 의미를 유지하고, 비거래일이나 알 수 없는 단계에서는 보수적으로 표현합니다.

P2-min도 API/웹/Bot 매개변수를 추가하지 않고, history/task status/report metadata에 쓰지 않으며, 리포트 JSON schema를 바꾸지 않고, 완전한 quote freshness, fallback, stale, data_quality 계약도 도입하지 않습니다. Bot/API가 Agent에 바로 연결되어 P1a pipeline으로 `market_phase_context`를 만들지 않았다면 여전히 예전 동작을 유지합니다. 진입점 전달과 화면 표시는 이후 P4+로 남겨 둡니다.

#### 장중 데이터 묶음과 실시간 품질 관리(Issue #1386 P3)

P3는 일반 분석 주 경로가 쓰는 실시간 시세 품질 메타데이터를 보완하지만, 여전히 `analysis_phase` 매개변수를 추가하지 않고, API/웹/Bot 단계 진입점을 바꾸지 않으며, 리포트 JSON schema도 바꾸지 않습니다. #1389 P5 데이터 품질 점수나 모델 신뢰도 제한도 하지 않습니다. 실시간 quote에는 `fetched_at`, `provider_timestamp`, `is_stale`, `stale_seconds`, `fallback_from`이 붙습니다. `fetched_at`은 시스템이 가져온 시각이고, `provider_timestamp`는 provider가 실제로 시세 시각을 제공할 때만 채웁니다. provider 시각이 없으면 fresh라고 지어내지 않으며, `stale_seconds`와 `is_stale`은 비워 둡니다.

소스 전체 fallback의 의미는 고정되어 있습니다. `source`는 실제로 성공한 데이터 소스 token을 유지하고, `fallback_from`은 이번에 실패한 가장 높은 우선순위의 소스 token을 기록합니다. 첫 소스가 성공하고 뒤쪽 소스에서 필드만 보충했다면 `fallback_from`을 쓰지 않습니다. `AnalysisContextBuilder`는 이런 상위 artifact만 대응시키며, 데이터를 다시 가져오거나 품질 점수를 매기지 않습니다. quote block 상태는 `STALE > FALLBACK > AVAILABLE` 순서로 합칩니다. 장중 실시간 가격으로 `today`를 덮으면 `is_partial_bar`, `is_estimated`, `estimated_fields`, `realtime_source`, quote 메타데이터를 표시합니다. `daily_bars` block은 여전히 storage의 완성 일봉 구간을 뜻하며, partial/estimated는 technical block에만 들어갑니다. freshness scoring, 장중 cache TTL 단계 구분, Agent 도구 단위 재사용, API/웹 표시는 이후 단계로 남겨 둡니다.

#### 분석 단계 진입점과 작업 대기열 전달(Issue #1386 P4a)

P4a는 `analysis_phase=auto|premarket|intraday|postmarket` 요청 매개변수를 새로 추가했으며 기본값은 `auto`입니다. API 호출자가 이번 분석 단계를 명시적으로 덮어쓰는 데 씁니다. 이 매개변수는 지금 `POST /api/v1/analysis/analyze`, 비동기 작업 대기열, `AnalysisService`, 일반 분석 pipeline, 시장 단계 맥락에 연결되어 있습니다. 웹 프런트엔드 타입과 API mapper도 이 필드를 받지만 페이지 selector는 추가하지 않으며, Bot, schedule, GitHub Actions, DB migration도 이번 단계 범위가 아닙니다.

`analysis_phase`는 요청 덮어쓰기 값이며, 최종 리포트 단계는 여전히 `report.meta.market_phase_summary.phase`를 기준으로 합니다. 비동기 accepted response, 메모리 작업 status, 작업 목록, SSE payload는 요청한 단계를 그대로 보여 줍니다. 이력 DB fallback에는 새 저장 필드를 추가하지 않으므로, 예전 기록은 비어 있을 수 있습니다. 같은 종목에 다른 phase를 요청해도 같은 종목 작업으로 보고 중복을 제거해, 동시에 중복 분석하지 않게 합니다.

내부 단계 맥락 생성은 예전 매개변수 `analysis_intent`와도 호환됩니다. `analysis_phase`가 `auto`로 남아 있을 때만, `auto`가 아닌 `analysis_intent`를 이번 요청 단계로 정규화합니다. 외부 호출자는 `analysis_phase`를 우선 써야 합니다.

`auto`는 기존 거래일 달력 추정을 그대로 씁니다. `auto`가 아니면 phase만 덮어쓰고 `is_trading_day`, `is_market_open_now`, `is_partial_bar`, `minutes_to_open`, `minutes_to_close`를 다시 계산합니다. 덮어써도 실제 `market_local_time`이나 `effective_daily_bar_date`는 바뀌지 않습니다. 현재 날짜가 거래일이 아니거나 달력이 해당 session을 지원하지 않으면 분 필드는 비어 있을 수 있습니다.

#### 웹 단계 태그 표시(Issue #1386 P4b)

P4b는 웹에서 단계를 볼 수 있게 보완했지만, 단계 덮어쓰기 selector는 추가하지 않았습니다. 진행 중인 작업 패널은 P4a가 돌려준 요청 단계 `analysis_phase`만 보여 주며, `auto`는 "자동 단계"(自动阶段)로 분명히 표시해 최종 추정 단계처럼 보이지 않게 합니다. 최종 리포트 페이지는 `report.meta.market_phase_summary.phase`로 실제 시장 단계 태그를 보여 주고, `is_partial_bar=true`이면 "일봉 미완성"(日线未完成)이라고 안내합니다.

데이터 품질 요약은 계속 `report.details.analysis_context_pack_overview.data_quality`와 기존 `AnalysisContextSummary`를 재사용합니다. 웹은 같은 리포트 상세 페이지에 단계 태그를 보여 주고 저민감 데이터 품질 요약을 계속 재사용하며, 전체 `AnalysisContextPack`, Prompt summary, raw payload, 이미 빼낸 snapshot 내부 필드는 드러내지 않습니다. 이력 목록, Bot, schedule, GitHub Actions, Desktop, 알림 요약, 고급 단계 덮어쓰기 진입점은 여전히 이후 작업입니다.

#### AnalysisContextPack Prompt 요약(Issue #1389 P3)

P3는 일반 분석과 Agent 초기 맥락에 `AnalysisContextPack` 저민감 요약을 연결합니다. Pipeline은 이미 받은 시세, 일봉, 추세, 매물대, 기본적 분석, 뉴스, 시장 단계 artifacts로 pack을 만든 뒤 `analysis_context_pack_summary`를 Prompt에 넣습니다. 새로 추가된 이 pack 요약 블록에서 LLM은 subject, 버전, 데이터 블록별 상태/출처/warning/missing reason, 뉴스 결과 수만 보며, 이 블록으로 전체 `news.content`, `trend_result`, 매물대나 기본적 분석의 원본 payload를 보지 않습니다. 기존 `news_context`, Agent pre-fetched JSON, `enhanced_context` 원본 데이터 통로는 P3 이전 동작을 유지하며, 이 요약이 그것을 대신하거나 민감 정보를 가리지는 않습니다.

P3는 당시 API/웹/Bot 매개변수를 추가하지 않고, history/task status/report metadata에 쓰지 않으며, 리포트 JSON schema를 바꾸지 않고, 전체 pack을 이력, 알림, 웹에 드러내지도 않았습니다. Agent 도구 단위의 pack 데이터 재사용과 P5 데이터 품질 점수는 이후 단계로 남겨 두었습니다.

#### Multi-Agent 판단 차이 요약 입력(Issue #1904 P1 plumbing)

Multi-agent는 `DecisionAgent`에 들어가기 전에 내부 저민감 `agent_disagreement_summary`를 만듭니다. 앞선 Agent 의견의 방향 차이, 위험 override 근거, 위험 override가 현재 `AGENT_RISK_OVERRIDE` 설정으로 켜져 있는지, 핵심이 아닌 단계의 기능 저하 정보를 알리는 데 씁니다. 이 요약에는 agent name, signal, confidence, conflict type, decision path hint, 저민감 risk control 상태, degraded stage marker만 들어 있고, reasoning, raw_data, 원본 오류 텍스트, token, 비공개 payload는 들어 있지 않습니다.

이 기능은 지금 `DecisionAgent`의 내부 Prompt 입력 통로일 뿐입니다. 요약은 실행 중 `ctx.meta`에 기록되며, Agent pre-fetched data에 들어가지 않고, 공개 API, Web/Desktop 표시, history/task status/report metadata, dashboard schema, 최종 설명 필드를 새로 만들지 않습니다. `risk_level=high`는 위험 근거로만 쓰이며 혼자서 override를 일으키지 않습니다. summary와 최종 `_apply_risk_override()`는 같은 override 판단을 재사용하며 `AGENT_RISK_OVERRIDE=false`를 따릅니다. 핵심이 아닌 기능 저하 단계는 orchestrator의 `intel`, `risk`, specialist/skill agent 기능 저하 계약을 그대로 따라, 한쪽 방향 의견을 multi-agent 합의처럼 잘못 설명하지 않게 합니다. #1904의 사용자에게 보이는 최종 설명 출력은 여전히 이후 단계에 속합니다.

`AgentResult.runtime_facts`는 내부 선택 필드로, 이번 Orchestrator 실행에서 모은 기본 Agent 의견, degradation event, Pipeline termination, 실제 risk application을 저장합니다. degradation event는 `DURING_STAGE`로 단계 자체의 실패를, `BEFORE_STAGE`로 Pipeline deadline이나 budget guard 때문에 단계가 시작되지 않았음을 구분합니다. 단계가 끝난 뒤에 deadline check가 걸리면 그 단계를 timeout degradation으로 기록하지 않습니다. `pipeline_termination.last_completed_stage`는 `AgentRunStats.stage_results`에서 마지막으로 실제 `COMPLETED`된 결과에서 가져오며, 비어 있을 수도 있습니다.

구조화된 Orchestrator dashboard는 input preparation, 단 한 번의 risk application, post-risk finalization 순서로 처리합니다. post-risk finalization은 top-level decision/operation advice, core signal/position advice, battle-plan position strategy, DecisionAgent signal/canonical payload를 갱신합니다. 이번 단계에서는 dashboard의 다른 자유 텍스트에 있는 방향성 표현은 다루지 않습니다. runtime facts와 post-risk Agent dashboard도 Pipeline의 최종 판단을 뜻하지 않으며, 공개 explanation 필드를 만들지 않습니다.

Multi-Agent 결과가 `StockAnalysisPipeline`에 들어간 뒤에는 구조와 자금 흐름, 시장 단계, daily-market context 처리를 이어서 마칩니다. 시스템은 공개 행동을 바꿀 수 있는 단계마다 DecisionSignal builder와 같은 해석 진입점으로 8단계 action을 새로 고치고, 실행 순서대로 실제 `from_action` / `to_action` 변화를 기록합니다. 조정 과정의 시작점, 모든 중간 행동, 최종 행동을 공용 규칙으로 하나로 해석할 수 있을 때만, 시스템은 `AgentResult.runtime_facts`를 바탕으로 선택 필드 `dashboard.agent_disagreement_explanation`을 결정적으로 만듭니다. 이 필드는 `pipeline_start_action`을 조정 과정의 시작점으로, `final_action`을 유일한 권위 있는 최종 결론으로 씁니다. `final_action`은 리포트 `action`, 이력 기록 action, `DecisionSignal.action`과 같습니다. 3단계 `decision_type`은 더 이상 explanation의 최종 결론으로 쓰지 않으며, `risk_control.post_risk_signal`은 Agent 위험 관리 단계의 통계 배경 사실로만 남습니다.

모델이 돌려준 최상위나 중첩된 같은 이름의 explanation은 공용 Agent dashboard 해석 경계에서 지우며, 최종 필드는 Pipeline만 만듭니다. 잘못된 Agent signal은 기존 전략 의견 유효성 규칙에 따라 runtime facts와 공개 차이 통계에서 빠지며, 조용히 `hold`로 바뀌지 않습니다. 자유 텍스트를 8단계 action 하나로 해석할 수 없으면 공용 resolver는 fail-closed로 동작합니다. 리포트와 이력 기록은 `action=None`을 유지하고, explanation을 만들지 않으며, DecisionSignal도 만들지 않습니다. Pipeline은 `decision_type`으로 값을 몰래 채우지 않습니다. canonical action이 있을 때 이 필드는 dashboard와 함께 저장되며, DecisionSignal을 추출하기 전에 완성됩니다. 예전 리포트, single Agent/비 Agent 경로, `runtime_facts`가 없는 호환 호출에는 이 필드가 없어도 됩니다. 이번 단계에서는 Web/Desktop 전용 표시, 전체 trace, P2-P4의 가중치와 감사 기능을 추가하지 않습니다.

#### AnalysisContextPack 저민감 정보 표시(Issue #1389 P4)

P4는 `report.details.analysis_context_pack_overview`를 새로 추가했습니다. 이력 상세와 completed `/api/v1/analysis/status/{task_id}`는 저장된 `context_snapshot`에서 같은 저민감 overview를 돌려줍니다. 동기 분석 응답도 이번에 저장된 `analysis_history.context_snapshot`을 읽어 overview를 꺼내므로, `SAVE_CONTEXT_SNAPSHOT=false`이면 새 기록에서 이 필드를 돌려준다고 보장하지 않습니다. 웹 리포트 페이지는 "전략 가격대"(策略点位)와 "뉴스"(资讯) 다음에 기본으로 접힌 데이터 블록 요약을 보여 줍니다. 접힌 머리글에는 사용 가능 수, 누락 수, 0이 아닌 다른 상태 개수, 실행 출처를 보여 주고, 펼치면 데이터 블록별 상태, 출처, warning, missing reason, 상태 개수, 뉴스 결과 수를 보여 줍니다. API가 돌려주는 `details.context_snapshot`은 최상위 `analysis_context_pack_overview`를 빼서, 투명성 패널이 raw snapshot을 중복으로 보여 주지 않게 합니다.

이 overview에는 전체 pack, `analysis_context_pack_summary` Prompt 문자열, `items.value`, 뉴스 본문, `trend_result`, 매물대나 기본적 분석의 원본 payload가 들어 있지 않습니다. `SAVE_CONTEXT_SNAPSHOT=false`이면 `analysis_history.context_snapshot` 전체를 저장하지 않으므로 새 이력 기록에서 overview를 읽지 않습니다. overview가 없는 예전 이력 기록은 이 필드가 비어 있지만 리포트는 정상적으로 돌려줍니다. 이번 단계는 pending/processing TaskPanel, SSE 진행 중 이벤트, 알림 요약, Bot/Desktop 전용 표시, `market_review` overview, 데이터 품질 점수를 다루지 않습니다.

#### AnalysisContextPack 데이터 품질 점수와 Prompt 데이터 제한(Issue #1389 P5)

P5는 `PACK_VERSION = "1.0"`을 바꾸지 않고, 데이터 소스를 추가하지 않으며, 리포트 JSON schema를 바꾸지 않는다는 전제 아래, `AnalysisContextPack`에 가벼운 데이터 품질 점수와 모델이 읽을 수 있는 데이터 제한 블록을 더합니다. `ContextFieldStatus`에 `fetch_failed`를 새로 추가했으며, 이는 필드나 데이터 블록을 이번에 가져오는 데 분명히 실패했다는 뜻만 나타냅니다. 첫 버전은 `fundamental_context.status == "failed"`만 `fetch_failed`로 대응시키며, 빈 뉴스, 검색 미설정, 실시간 quote 없음, 매물대 누락은 여전히 기존 `missing` / `not_supported`로 처리합니다.

`DataQuality`에는 이제 `overall_score`, `level`, `block_scores`, `limitations`가 있으며, 예전 `warnings` / `metadata`도 유지합니다. 점수는 `quote`, `daily_bars`, `technical`, `news`, `fundamentals`, `chip` 여섯 블록을 항상 다루며, 보조 블록이 없다고 다시 정규화하지 않습니다. 핵심 블록의 기능이 낮아지면 Prompt의 "데이터 제한"(数据限制) 블록에서 모델에게 높은 신뢰도의 결론을 내지 말라고 요구합니다. 보조 블록이 없으면 해당 분석 단락만 제한하며, 이를 호재나 악재로 해석하면 안 됩니다. 이 Prompt 블록은 `format_analysis_context_pack_prompt_section()`이 한 곳에서 만들며, 일반 분석, single Agent, multi-agent가 같은 저민감 summary를 쓰고 raw payload, 뉴스 본문, 추세 원본 값, secret, token, webhook을 드러내지 않습니다.

이력 상세, 동기 분석 응답, completed 작업 상태는 계속 `report.details.analysis_context_pack_overview`로만 저민감 필드를 드러냅니다. P5는 이 overview 아래에 `data_quality`만 새로 추가하며, score, level, block_scores, limitations를 담고 `warnings`는 다시 공개하지 않습니다. 웹 리포트 페이지는 여전히 데이터 블록 요약을 기본으로 접어서 보여 주며, 접힌 머리글에 품질 점수/등급을 새로 보여 주고, 펼치면 제한 설명과 `fetch_failed` 상태를 보여 줍니다. `details.context_snapshot`은 계속 최상위 `analysis_context_pack_overview`를 뺍니다.

#### AnalysisContextPack 문서, 마이그레이션과 롤백(Issue #1389 P6)

P6는 문서와 설정 가시성만 마무리하며, pack runtime을 추가하지 않고, pack enable/disable feature flag를 만들지 않으며, `PACK_VERSION = "1.0"`을 바꾸지 않고, API 매개변수를 추가하지 않으며, 리포트 JSON schema를 바꾸지 않고, 데이터베이스 마이그레이션도 하지 않습니다. 전체 계약, 필드 상태, 저민감 요약 표시 범위, 민감 정보 가림 범위, 마이그레이션과 롤백 안내는 [AnalysisContextPack 문서](analysis-context-pack.md)를 보세요.

`SAVE_CONTEXT_SNAPSHOT`은 이미 있던 환경 변수이며, P6는 이를 `.env.example`, 설정 레지스트리, 웹 설정 도움말에 맞춰 넣었을 뿐입니다. 기본값은 `true`입니다. `false`로 두거나 CLI에서 `--no-context-snapshot`을 쓰면 새 이력 기록은 `analysis_history.context_snapshot` 전체를 더 이상 저장하지 않으며, 여기에는 `enhanced_context`, `market_phase_summary`, `analysis_context_pack_overview`, 진단 스냅샷, raw snapshot 필드가 포함됩니다. 이 설정은 이번 실행의 `AnalysisContextPack` 생성을 끄지 않고, Prompt의 저민감 `analysis_context_pack_summary`를 빼지 않으며, 분석 결과 JSON schema나 API 요청 매개변수도 바꾸지 않습니다.

지금은 실행 중 pack 전체 스위치가 없습니다. P3-P5의 pack Prompt 요약, overview, 데이터 품질 연결을 끄려면 배포 롤백이나 코드 롤백으로만 할 수 있습니다. `analysis_context_pack_overview` / `data_quality`가 없는 예전 이력 기록은 계속 빈 필드를 돌려주며, 리포트 읽기는 호환을 유지합니다.

#### 시장 구조 맥락(Issue #1909)

개별 종목 분석에 저민감 `market_structure_context`가 새로 추가되었으며, `AnalysisReport.details.market_structure`로 이력 상세, 동기 분석 응답, completed 작업 상태에 드러납니다. 이 필드는 두 계층 구조입니다. `market_theme_context`는 시장/테마 계층으로 A주 업종/테마 순위, 활발한 테마, 상승 주도 업종/테마, 테마 폭, 데이터 품질을 담고, `stock_market_position`은 개별 종목 위치 계층으로 종목이 속한 섹터, 주요 관련 테마, 테마 단계, 종목 위치, 위험 태그, 누락된 근거를 담습니다.

첫 버전의 시장 구조는 자체 서비스가 `DataFetcherManager.get_sector_rankings()`, `get_concept_rankings()`, `fundamental_context.belong_boards`를 바탕으로 만들며, 종목 선별 엔진을 호출하지 않습니다. 종목 선별에서 AlphaSift를 참고해 구현한 화제 상세, 확산 경로, 구성 종목, leader stocks는 이후 선택적 데이터 소스로 쓸 수 있지만, 지금 일반 개별 종목 분석에서 몰래 호출하지는 않습니다. 구성 종목이나 leader 근거가 없으면 `stock_role`은 기본으로 `follower/edge/unknown`을 유지하고, `missing_fields`에 `hotspot_constituents`, `leader_stocks`를 표시해, 단순 관련주를 테마 대장주로 잘못 쓰지 않게 합니다.

호환 범위: `market_structure_context`의 provider / model 스냅샷 필드(`model_used`, `market_structure_context.*.source.provider` 등)는 이력 추적과 화면 표시에만 쓰이며, LLM provider 라우팅, `base URL`, `provider/model` 실행 설정 입력이 되지 않습니다. `.env` 설정 정리, 되쓰기, 마이그레이션, 몰래 바꾸기를 일으키지 않습니다.

일반 LLM, single Agent, multi-agent prompt에는 시장 구조 저민감 요약이 들어갑니다. DecisionSignal 자동 추출은 `primary_theme`, `theme_phase`, `stock_role`, 버전 번호, 위험 태그를 metadata에 쓰며, 주 필드, 중복 제거 키, 수명 주기 규칙은 바꾸지 않습니다. 웹 리포트 페이지는 개요 다음에 "시장 위치"(市场位置) 카드를 보여 주며, 시장 테마 계층과 개별 종목 위치 계층을 나눠 보여 줍니다. 이 필드가 없는 예전 이력 기록에는 표시하지 않습니다. A주가 아닌 시장은 첫 버전에서 `not_supported`를 돌려주며, 기존 리포트에는 영향이 없습니다.

#### 장중 판단 안전장치와 품질 검사(Issue #1386 P5)

P5는 개별 종목 분석 리포트의 `dashboard.phase_decision`에 단계별 판단 필드를 덧붙입니다: `phase_context`, `action_window`, `immediate_action`, `watch_conditions`, `next_check_time`, `confidence_reason`, `data_limitations`. 이 필드는 리포트 JSON의 하위 호환 확장으로만 과거 `raw_result`에 들어가며, `analysis_phase` API 매개변수를 추가하지 않고, 웹 단계 진입점을 바꾸지 않으며, 설정 항목을 추가하지 않고, 매일 장 마감 복기 기본 동작에도 영향을 주지 않습니다.

일반 분석과 Agent 분석은 이력을 저장하기 전에 이번 실행의 `market_phase_summary`와 `analysis_context_pack_overview.data_quality`를 재사용해 가벼운 안전장치를 적용합니다. 핵심 quote / daily_bars / technical 데이터가 stale, fallback, missing, fetch_failed, partial, estimated이면 높은 신뢰도의 결론을 허용하지 않습니다. 장 시작 전, 비거래일, 알 수 없는 단계에서는 높은 신뢰도의 장중 매매 의견을 내면 안 됩니다. 장중, 점심 휴장, 마감 직전에는 주 결론에 장 마감 후 복기 말투가 있는지 확인하고, 분명한 "오늘 장 마감 후 복기에 따르면", "내일 주목할 점" 같은 표현을 단계에 맞는 관찰/대기 표현으로 바꿉니다. 안전장치는 저민감 `phase_context`와 데이터 제한만 보충하며, 관찰 조건이나 다음 확인 시각을 지어내지 않습니다. 알림 요약, 경고, 보유 종목, 백테스트 연동은 이후 P6로 남겨 둡니다.

#### 신호 귀속 분석(Issue #1742)

Issue #1742는 개별 종목 분석 리포트의 `dashboard.signal_attribution`에 신호 귀속 분석 필드를 새로 추가했습니다: `technical_indicators`, `news_sentiment`, `fundamentals`, `market_conditions`(네 가지 기여도. 유효한 0이 아닌 기여도는 합이 100이 되도록 정규화하며, 모두 0이면 유효한 신호가 없다는 뜻), `strongest_bullish_signal`, `strongest_bearish_signal`. 이 필드는 추천 이유가 어떻게 구성되는지 설명해, 사용자가 AI 판단의 귀속 가중치를 이해하도록 돕습니다.

신호 귀속 분석은 모든 리포트 렌더링 경로에 함께 표시됩니다.
- `generate_dashboard_report()`(기본 알림 리포트)
- `generate_single_stock_report()`(종목별 알림 리포트)
- `templates/report_markdown.j2`(Jinja2 템플릿)
- `HistoryService._generate_single_stock_markdown()`(웹 이력 서랍)

정규화 함수는 `_parse_response()`와 `parse_dashboard_json()`에서 명시적으로 호출하며, 다음을 보장합니다.
- 문자열 백분율을 int로 바꿈(예: `"35%"` → `35`)
- 음수는 0으로 바꿈
- 합이 100이 아니면 합이 100이 되도록 정규화
- 값을 [0, 100] 범위로 자름

`signal_attribution`은 선택적인 표시 필드입니다(필수 아님). 없어도 완전성 검사가 실패하지 않으며, `missing` 목록에 들어가거나 보완 prompt를 일으키지도 않습니다. 있으면 정규화해서 지원하는 리포트 경로에 보여 줍니다.

#### 경고, 보유 종목, 이력 연동(Issue #1386 P6)

P6는 기존 `market_phase_summary`와 `analysis_context_pack_overview`를 경고, 보유 종목, 이력, 백테스트, 알림 경로에 재사용하며, phase/pack 프로토콜을 새로 만들거나 데이터베이스 마이그레이션을 하지 않습니다. 경고 발동 기록은 여전히 기존 `diagnostics` 텍스트 필드를 씁니다. diagnostics를 JSON으로 만들 수 있으면 worker가 `status=triggered` 기록에 `analysis_visibility.market_phase_summary`, `analysis_visibility.analysis_context_pack_overview`, `analysis_visibility.source`를 합쳐서 씁니다. 예전 순수 텍스트 diagnostics는 원문을 그대로 두며, Alert API의 파생 필드는 비어 있고 `analysis_visibility_source=legacy_text`입니다.

경고 phase 요약은 발동 시점의 맥락에서 옵니다. symbol 대상은 종목 시장으로 추정하고, `target_scope=market`은 `cn|hk|us|jp|kr` 시장 지역을 그대로 쓰며, 계좌 단위로 하나로 정할 수 없으면 `unknown`이 되어도 됩니다. pack overview는 평가기에 이미 붙어 있던 overview나 최근 30일 이력 snapshot의 저민감 overview에서만 오며, 없으면 `null`을 돌려주고, pack을 지어내거나 가벼운 LLM 분석을 자동으로 실행하지 않습니다. 공개 source 값은 `alert_trigger_market_context`, `analysis_history_snapshot`, `evaluator_snapshot`, `legacy_text`, `null` 중 하나입니다.

보유 종목 페이지에 종목별 직접 분석 진입점이 새로 생겼으며, `POST /api/v1/portfolio/positions/{symbol}/analysis`에 해당합니다. 요청 필드는 `account_id`, `analysis_phase=auto|premarket|intraday|postmarket`, `force`입니다. 현재 보유 종목 스냅샷에서 수량이 0이 아닌 종목만 제출할 수 있으며, 보유하지 않았으면 404를, 여러 계좌가 같은 종목을 보유했는데 `account_id`를 넘기지 않았으면 `400 ambiguous_position_account`를 돌려줍니다. 이 진입점은 비동기 작업의 accepted / duplicate 의미를 그대로 따르며, `force`는 분석 새로 고침에만 영향을 주고 in-flight duplicate를 우회하지 않습니다. 백엔드는 저민감 `portfolio_context`만 내부 pipeline과 context pack의 선택적 `portfolio` block에 넘깁니다. 이 block은 기존 여섯 블록 데이터 품질 총점에 들어가지 않으며, 작업 목록이나 SSE payload에도 나오지 않습니다.

이력 목록, 종목별 이력, StockBar, 상세는 `context_snapshot`에서 `market_phase_summary`를 꺼냅니다. 예전 기록, snapshot 누락, 해석 실패이면 `null`을 돌려줍니다. 백테스트 결과 항목에는 `market_phase`와 `market_phase_summary`가 추가되었고, 결과 목록과 performance/summary 조회는 `analysis_phase=premarket|intraday|postmarket|unknown`을 지원합니다. 통계는 `intraday`, `lunch_break`, `closing_auction`을 intraday로, `non_trading`, 누락, 잘못된 값을 unknown으로 묶습니다. phase로 거르는 백테스트 조회는 repository 계층에서 SQL 조건으로 결과와 snapshot을 한꺼번에 읽고, 먼저 bucket으로 나눈 뒤 페이지를 나누며, summary diagnostics에 `phase_breakdown`과 `raw_phase_counts`를 돌려줍니다.

알림 요약은 통일된 공개 형식 helper를 재사용하며, 단계 태그, trigger source, partial-bar warning, 데이터 품질 등급, 앞쪽 limitations 두 개만 출력합니다. raw context pack, Prompt, 뉴스 본문, 보유 종목의 민감한 세부 내용은 출력하지 않습니다. 웹 경고 이력, 보유 종목, 이력 목록, StockBar, 백테스트 페이지에는 단계 badge, 품질 요약, phase filter, breakdown이 함께 표시됩니다.

#### 문서, 설정, 마이그레이션 안내(Issue #1386 P7)

P7은 장 시작 전 / 장중 / 장 마감 후 분석에 대한 사용자 안내만 정리하며, 실행 기능, 설정 항목, API 매개변수, 데이터베이스 마이그레이션, 웹 단계 덮어쓰기 selector, Bot phase 매개변수, GitHub Actions 장중 workflow는 추가하지 않습니다. 기본 일일 장 마감 분석, 기본 GitHub Actions, 기존 schedule 동작은 그대로입니다.

권장 사용 방법:

| 상황 | 권장 용도 | 설명 |
| --- | --- | --- |
| 장 시작 전 | 개장 계획과 관찰 조건 만들기 | 아직 일어나지 않은 오늘 흐름을 사실처럼 쓰면 안 됩니다. 직전 완성 거래일, 밤사이 정보, 개장 시 발동 조건을 중심으로 봅니다. |
| 장중 / 점심 휴장 / 마감 직전 | 실시간 상태 판단, 위험과 기회 알림 | 현재가, 실시간 시세의 신선도, partial bar, 데이터 제한, 다음 관찰 조건을 봅니다. 장 마감 후 전체 복기를 대신하지 않습니다. |
| 장 마감 후 | 전체 복기와 다음 날 계획 | 하루 전체 의미를 쓰며, 기본 일일 분석과 가장 가까운 상황입니다. |

진입점과 표시:

| 진입점 | 단계 동작 |
| --- | --- |
| `POST /api/v1/analysis/analyze` | `analysis_phase=auto|premarket|intraday|postmarket`를 지원합니다. 넘기지 않으면 기본값은 `auto`입니다. |
| 웹 주 분석 / 다시 분석 / 보유 종목 직접 분석 | 현재 단계 덮어쓰기 selector가 없으며, 프런트엔드는 기본으로 `auto`를 넘깁니다. 진행 중 작업 패널은 요청 단계를, 최종 리포트 페이지는 최종 단계 태그를 보여 줍니다. |
| Bot / CLI / schedule / 기본 GitHub Actions | `analysis_phase`를 넘기지 않고 계속 `auto` 추정을 씁니다. 기본 장 마감 분석 동작은 그대로입니다. |
| 이력 / 백테스트 / 알림 / 경고 | 공개 `market_phase_summary`와 저민감 `analysis_context_pack_overview`만 씁니다. 전체 pack, Prompt summary, 뉴스 본문, 보유 종목의 민감한 세부 내용은 공개하지 않습니다. |

`analysis_phase`는 요청 덮어쓰기 값이며, 최종 리포트 단계는 여전히 `report.meta.market_phase_summary.phase`를 기준으로 합니다. 예전 호출이 `analysis_phase`를 넘기지 않아도 호환됩니다. `market_phase_summary`나 `analysis_context_pack_overview`가 없는 예전 이력은 빈 필드를 돌려주며 리포트 읽기에 영향이 없습니다. 백테스트 조회는 `analysis_phase=premarket|intraday|postmarket|unknown` 필터를 지원하며, P6 규칙에 따라 점심 휴장과 마감 직전을 intraday로 묶습니다.

`SAVE_CONTEXT_SNAPSHOT=false`나 CLI `--no-context-snapshot`은 새 이력이 `context_snapshot` 전체를 저장하지 않게만 하므로, 새 이력은 phase summary / pack overview / diagnostics snapshot 같은 저장 요약을 더 이상 공개하지 않습니다. 이번 실행의 `AnalysisContextPack` 생성을 끄지 않고, Prompt의 저민감 `analysis_context_pack_summary`를 빼지 않으며, 리포트 JSON schema도 바꾸지 않습니다. 호출자가 예전 장 마감 후 기준에 더 가까운 출력으로 잠시 돌아가고 싶다면 `analysis_phase=postmarket`을 고정해서 넘기면 됩니다. P0-P6 단계/pack runtime 연결을 완전히 빼려면 배포 롤백이나 코드 롤백이 필요합니다.

#### Crontab 사용

상주 프로세스를 쓰고 싶지 않다면 시스템의 Cron을 써도 됩니다(Linux/macOS 기준이며, Windows에서는 작업 스케줄러를 쓰면 됩니다).

```bash
crontab -e
# 추가: 0 18 * * 1-5 cd /path/to/project && python main.py
```

---

<a id="通知渠道详细配置"></a>

## 알림 채널 자세한 설정

알림 채널 표, minimal/advanced key 구분, `--check-notify` 진단 기준, 상황별 설정 안내는 [알림 문서](notifications.md)를 보세요.

### WeCom(기업용 위챗)

1. WeCom 그룹 대화에 "그룹 봇"(群机器人)을 추가합니다
2. Webhook URL을 복사합니다
3. `WECHAT_WEBHOOK_URL`을 설정합니다

<a id="飞书"></a>

### Feishu(페이슈)

> ⚠️ **꼭 구분하세요**: `FEISHU_WEBHOOK_SECRET`(Webhook 서명 키)과 `FEISHU_APP_SECRET`(Feishu 앱 Secret)은 완전히 다른 설정이며 서로 바꿔 쓸 수 없습니다.

**최소 동작 설정(보안 제한 없음):**

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your_hook_token
```

**전체 순서:**

1. **Feishu 그룹 대화에서 사용자 정의 봇 만들기**:
   - 대상 그룹 대화 열기 → 오른쪽 위 「群设置」(그룹 설정) →「群机器人」(그룹 봇) →「添加机器人」(봇 추가) →「自定义机器人」(사용자 정의 봇)
   - 봇 이름을 넣고 생성된 **Webhook URL**을 복사합니다(형식: `https://open.feishu.cn/open-apis/bot/v2/hook/...`)
2. `FEISHU_WEBHOOK_URL`을 설정합니다(앞 단계에서 복사한 URL).
3. 봇의 **보안 설정**을 보고, 켜 둔 보안 항목에 따라 추가 설정이 필요한지 정합니다.
   - **추가 보안 설정 없음**: `FEISHU_WEBHOOK_URL`만 넣으면 됩니다.
   - **「签名校验」(서명 검증)을 켰다면**: Feishu에 보이는 secret을 `FEISHU_WEBHOOK_SECRET`에 넣습니다. 양쪽을 모두 켜거나 모두 비워야 하며, 그렇지 않으면 Feishu가 서명 검증 실패를 돌려줍니다.
   - **「关键词」(키워드)를 켰다면**: 같은 키워드를 `FEISHU_WEBHOOK_KEYWORD`에 넣습니다. 시스템이 메시지마다 앞에 자동으로 붙이므로 리포트 템플릿을 직접 고칠 필요가 없습니다.
   - **IP 허용 목록을 켰다면**: 현재 실행 환경의 외부 IP가 허용 목록에 있는지 확인합니다(로컬/Docker/GitHub Actions의 외부 IP는 모두 다릅니다).
4. `FEISHU_APP_ID` / `FEISHU_APP_SECRET`은 Feishu 앱 / Stream Bot / 클라우드 문서 모드 전용이며, 그룹 Webhook 알림을 일으키지 않습니다. 이것만으로 `FEISHU_WEBHOOK_URL`을 대신하지 마세요.
5. `FEISHU_APP_ID` / `FEISHU_APP_SECRET`을 설정했고 `FEISHU_CHAT_ID`도 설정하면, 그룹 Webhook 없이 Feishu App Bot으로 지정한 그룹 대화나 사용자에게 바로 알림을 보낼 수 있습니다. `FEISHU_RECEIVE_ID_TYPE` 기본값은 `chat_id`이며, 개인 대화라면 `open_id`로 바꿉니다. 이 방식은 Feishu OpenAPI Bot 대화를 쓰며, 그룹 Webhook과는 서로 독립된 경로입니다.
6. App Bot 발송 경로는 `requirements.txt`에 이미 있는 `lark-oapi>=1.0.0`을 재사용합니다. 표준 소스 설치, Docker, GitHub Actions daily workflow, 데스크톱 빌드 과정은 모두 `pip install -r requirements.txt`로 설치하므로 새 라이브러리를 따로 설치할 필요가 없습니다. 참고: [Feishu message create OpenAPI](https://open.feishu.cn/document/server-docs/im-v1/message/create), [lark-oapi PyPI](https://pypi.org/project/lark-oapi/), [SDK repo](https://github.com/larksuite/oapi-sdk-python).

**흔한 실패 원인:**
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET`만 넣고, `FEISHU_WEBHOOK_URL`도, App Bot 직접 알림에 필요한 `FEISHU_CHAT_ID`도 설정하지 않음
- Feishu 봇에 「签名校验」(서명 검증)을 켰는데 `FEISHU_WEBHOOK_SECRET`을 설정하지 않음(또는 `FEISHU_APP_SECRET`을 잘못 넣음)
- Feishu 봇에 「关键词」(키워드)를 켰는데 로컬에 `FEISHU_WEBHOOK_KEYWORD`를 함께 설정하지 않음
- 봇이 대상 그룹에 추가되지 않았거나, 그룹 관리자가 봇의 발언을 제한함
- Feishu 쪽에 IP 허용 목록을 추가로 설정했는데 현재 실행 환경의 IP가 목록에 없음
- 메시지가 너무 김: Feishu 메시지 하나에는 길이 제한이 있으며, 시스템이 자동으로 나눠 보냅니다. 한 문서에서 전체 내용을 보려면 Feishu 클라우드 문서 기능(`FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_FOLDER_TOKEN`)을 설정하세요

그림이 포함된 더 자세한 문제 해결은 [docs/bot/feishu-bot-config.md](bot/feishu-bot-config.md)를 보세요.
### Telegram

1. @BotFather와 대화해 Bot을 만듭니다
2. Bot Token을 받습니다
3. Chat ID를 받습니다(@userinfobot으로 확인 가능)
4. `TELEGRAM_BOT_TOKEN`과 `TELEGRAM_CHAT_ID`를 설정합니다
5. (선택) Topic으로 보내려면 `TELEGRAM_MESSAGE_THREAD_ID`를 설정합니다(Topic 링크 끝에서 확인)

<a id="邮件"></a>

### 메일

1. 메일 계정의 SMTP 서비스를 켭니다
2. 인증 코드(앱 비밀번호, 로그인 비밀번호가 아님)를 받습니다
3. `EMAIL_SENDER`, `EMAIL_PASSWORD`, `EMAIL_RECEIVERS`를 설정합니다

지원하는 메일:
- QQ 메일: smtp.qq.com:465
- 163 메일: smtp.163.com:465
- Gmail: smtp.gmail.com:587

**종목 그룹별로 다른 메일 주소에 보내기**(Issue #268, 선택):
`STOCK_GROUP_N`과 `EMAIL_GROUP_N`을 설정하면 종목 그룹마다 리포트를 다른 메일 주소로 보낼 수 있어, 여러 사람이 분석을 함께 쓸 때 서로 섞이지 않습니다. 이번에 실제로 분석할 종목은 여전히 `STOCK_LIST`가 정하며, `STOCK_GROUP_N`은 `STOCK_LIST`의 부분 집합으로 써야 합니다. 이 설정은 메일 수신자에만 영향을 주며, Telegram, WeCom, Webhook 같은 다른 채널이 받는 전체 리포트는 바꾸지 않습니다. 시장 복기는 설정된 모든 메일 주소로 보냅니다.

> GitHub Actions 제한: 2026-03-29 기준으로 저장소에 들어 있는 `00-daily-analysis.yml`은 번호가 임의로 붙는 `STOCK_GROUP_N` / `EMAIL_GROUP_N`을 자동으로 넣지 않습니다. 그래서 저장소 Secrets / Variables에 이 변수만 추가하고 workflow에 명시적 매핑을 하지 않으면 실행 프로세스에 들어가지 않아, "그룹 설정이 적용되지 않는" 것처럼 보입니다.

```bash
STOCK_LIST=600519,300750,002594,AAPL
STOCK_GROUP_1=600519,300750
EMAIL_GROUP_1=user1@example.com
STOCK_GROUP_2=002594,AAPL
EMAIL_GROUP_2=user2@example.com
```

<a id="自定义-webhook"></a>

### 사용자 정의 Webhook

POST JSON을 받는 Webhook이라면 무엇이든 지원합니다. 예를 들면 다음과 같습니다.
- DingTalk(딩톡) 봇
- Discord Webhook
- Slack Webhook
- Bark(iOS 푸시)
- 자체 서비스

`CUSTOM_WEBHOOK_URLS`를 설정하며, 여러 개는 쉼표로 구분합니다.

AstrBot, NapCat, 자체 서비스의 특수한 body에 맞추려면 `CUSTOM_WEBHOOK_BODY_TEMPLATE`을 설정할 수 있습니다. 이것은 전역 템플릿이라 Bark, Slack, Discord 등의 URL 자동 인식 payload보다 먼저 적용됩니다. 렌더링 결과가 JSON object가 아니면 시스템이 기본 payload로 돌아갑니다. 줄바꿈과 따옴표가 JSON을 깨뜨리지 않도록 `$content_json` / `$title_json`을 쓰는 것을 권장합니다.

```env
CUSTOM_WEBHOOK_BODY_TEMPLATE={"msg_type":"text","content":$content_json}
```

쓸 수 있는 자리 표시자: `$content_json`, `$content`, `$title_json`, `$title`. 이 가운데 `$content` / `$title`은 JSON 이스케이프를 하지 않은 그대로의 문자열이라, 본문에 큰따옴표나 줄바꿈이 있으면 fallback이 일어날 수 있습니다.

Docker Compose 배포에서 웹 설정 페이지로 저장하면 이 앱 자리 표시자를 `$$content_json` / `$$title_json` 같은 형식으로 써서, Compose가 다시 배포할 때 빈 값으로 펼치지 않게 합니다. 앱은 실행할 때 다시 `$` 하나로 되돌립니다. Docker가 쓰는 `.env`를 직접 편집할 때도 `$$content_json` 같은 형식을 쓰세요.

Bark에 전역 템플릿을 쓰면 Bark body를 직접 써야 합니다.

```env
CUSTOM_WEBHOOK_BODY_TEMPLATE={"title":$title_json,"body":$content_json,"group":"stock"}
```

NapCat / OneBot 예시는 실제 endpoint, `user_id`, `group_id`에 맞춰 조정해야 합니다.

```env
CUSTOM_WEBHOOK_BODY_TEMPLATE={"user_id":123456,"message":$content_json}
```

### ntfy / Gotify

ntfy와 Gotify는 모두 정식 알림 채널이며, 텍스트 / JSON만 보내고 Markdown 이미지 변환에는 참여하지 않습니다.

ntfy는 전체 topic endpoint를 쓰며, 마지막 경로 조각이 topic이 됩니다.

```env
NTFY_URL=https://ntfy.sh/my-topic
NTFY_TOKEN=
```

Gotify는 서버 base URL을 쓰며, 시스템이 고정된 `/message` API를 자동으로 붙이고 application token을 `X-Gotify-Key` Header로 보냅니다. `GOTIFY_URL`에는 리버스 프록시 경로 접두사는 넣어도 되지만 `/message`는 넣지 마세요.

```env
GOTIFY_URL=https://gotify.example
GOTIFY_TOKEN=app-token
```

```env
# 실제 요청은 https://example.com/gotify/message 로 갑니다
GOTIFY_URL=https://example.com/gotify
GOTIFY_TOKEN=app-token
```

`NTFY_URL`과 `GOTIFY_URL`의 의미가 다른 것은 두 서비스의 API 설계 차이 때문에 일부러 그렇게 한 것입니다. ntfy는 사용자의 topic으로 endpoint를 이루고, Gotify의 `/message`는 고정된 서비스 API입니다.

### Discord

Discord는 두 가지 방식으로 알림을 보낼 수 있습니다.

긴 리포트는 Discord content 하나의 2000자 상한에 맞춰 자동으로 나눠 보냅니다. 어떤 조각이 429 요청 제한에 걸리면, 발송기는 Discord가 돌려준 `retry_after`나 `Retry-After`에 따라 제한된 횟수만큼 재시도하고 다음 조각을 계속 보냅니다. `DISCORD_MAX_WORDS`로 조각 길이를 줄일 수 있지만, 실행 중 2000을 넘도록 허용하지는 않습니다.

**방법 1: Webhook(권장, 간단)**

1. Discord 채널 설정에서 Webhook을 만듭니다
2. Webhook URL을 복사합니다
3. 환경 변수를 설정합니다.

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/yyy
```

**방법 2: Bot API(권한이 더 필요함)**

1. [Discord Developer Portal](https://discord.com/developers/applications)에서 애플리케이션을 만듭니다
2. Bot을 만들고 Token을 받습니다
3. Bot을 서버에 초대합니다
4. 채널 ID를 받습니다(개발자 모드에서 채널을 마우스 오른쪽 버튼으로 눌러 복사)
5. 환경 변수를 설정합니다.

```bash
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_MAIN_CHANNEL_ID=your_channel_id
```

Discord로 메시지를 보내는 것뿐 아니라 Discord Slash Command / Interaction 콜백도 받으려면, Discord Developer Portal의 `General Information -> Public Key`에서 공개 키를 복사해 설정해야 합니다.

```bash
DISCORD_INTERACTIONS_PUBLIC_KEY=your_public_key
```

이 공개 키를 설정하지 않으면 시스템은 Discord에서 들어오는 webhook 요청을 모두 거부합니다.

### Slack

Slack은 두 가지 방식으로 알림을 보낼 수 있습니다. 둘 다 설정하면 텍스트와 이미지를 같은 채널로 보내도록 Bot API를 우선 씁니다.

**방법 1: Bot API(권장, 이미지 업로드 지원)**

1. Slack App 만들기: https://api.slack.com/apps → Create New App
2. Bot Token Scopes 추가: `chat:write`, `files:write`
3. 워크스페이스에 설치하고 Bot Token(xoxb-...)을 받습니다
4. 채널 ID 받기: 채널 상세 → 아래쪽에서 채널 ID 복사
5. 환경 변수를 설정합니다.

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C01234567
```

**방법 2: Incoming Webhook(설정 간단, 텍스트만)**

1. Slack App 관리 페이지에서 Incoming Webhook을 만듭니다
2. Webhook URL을 복사합니다
3. 환경 변수를 설정합니다.

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../xxx
```

### Pushover(iOS/Android 푸시)

[Pushover](https://pushover.net/)는 iOS와 Android를 지원하는 여러 플랫폼용 푸시 서비스입니다.

1. Pushover 계정을 만들고 앱을 내려받습니다
2. [Pushover Dashboard](https://pushover.net/)에서 User Key를 받습니다
3. Application을 만들어 API Token을 받습니다
4. 환경 변수를 설정합니다.

```bash
PUSHOVER_USER_KEY=your_user_key
PUSHOVER_API_TOKEN=your_api_token
```

특징:
- iOS/Android 두 플랫폼 지원
- 알림 우선순위와 소리 설정 지원
- 무료 한도가 개인 사용에 충분함(월 10,000건)
- 메시지를 7일 동안 보관

### Markdown 이미지 변환(선택)

`MARKDOWN_TO_IMAGE_CHANNELS`를 설정하면 Markdown을 지원하지 않는 채널(telegram, wechat, custom, email, slack)에 리포트를 이미지로 보낼 수 있습니다.

**의존성 설치**:

1. **imgkit**: `requirements.txt`에 들어 있어 `pip install -r requirements.txt`를 실행하면 자동으로 설치됩니다
2. **wkhtmltopdf**(기본 엔진): 시스템 수준 의존성이라 직접 설치해야 합니다.
   - **macOS**: `brew install wkhtmltopdf`
   - **Debian/Ubuntu**: `apt install wkhtmltopdf fonts-noto-cjk`(프로젝트가 지원하는 중국어와 한국어 리포트를 제대로 렌더링하기 위함)
3. **markdown-to-file**(선택, emoji 지원이 더 좋음): `npm i -g markdown-to-file`을 실행하고 `MD2IMG_ENGINE=markdown-to-file`로 설정합니다
4. **Playwright**(선택, 웹 서비스에 알맞음): `apps/dsa-web`에서 `npm ci`와 `npx playwright install chromium`을 실행하고 `MD2IMG_ENGINE=playwright`로 설정합니다

설치하지 않았거나 설치에 실패하면 자동으로 Markdown 텍스트로 보냅니다.

**종목별 알림 + 이미지 발송**(Issue #455):

종목별 알림 모드(`SINGLE_STOCK_NOTIFY=true`)에서 Telegram 같은 채널로 이미지를 보내려면 `MARKDOWN_TO_IMAGE_CHANNELS=telegram`도 함께 설정하고 이미지 변환 도구(wkhtmltopdf 또는 markdown-to-file)를 설치해야 합니다. 개별 종목 일일 리포트 요약도 이미지 변환을 지원하며, 따로 설정할 것은 없습니다.

**문제 해결**: 로그에 「Markdown 转图片失败，将回退为文本发送」(Markdown 이미지 변환 실패, 텍스트로 대신 보냄)이 나오면, `MARKDOWN_TO_IMAGE_CHANNELS` 설정과 이미지 변환 도구가 제대로 설치되었는지 확인하세요(`which wkhtmltoimage` 또는 `which m2f`).

---

## 데이터 소스 설정

시스템은 기본으로 AkShare(무료)를 쓰며, 다른 데이터 소스도 지원합니다. (A주용 소스가 대부분이며, 한국 주식은 YFinance로 조회합니다.)

### AkShare(기본)
- 무료, 설정 필요 없음
- 데이터 출처: 둥팡차이푸(East Money) 수집

### Tushare Pro
- 가입해서 Token을 받아야 함
- 더 안정적이고 데이터가 더 많음
- `TUSHARE_TOKEN` 설정

### Baostock
- 무료, 설정 필요 없음
- 예비 데이터 소스로 쓰임

### YFinance
- 무료, 설정 필요 없음
- 미국/홍콩 주식 데이터 지원
- 미국 주식의 과거 데이터와 실시간 시세는 모두 YFinance를 써서, akshare 미국 주식 수정주가 이상으로 기술 지표가 틀리는 일을 막음

### Longbridge
- 미국/홍콩 주식 데이터의 대체 소스로, YFinance에 없는 거래량 비율, 회전율, PE 같은 필드를 보충함
- 새로 연결한다면 Longbridge 공식 OAuth 2.0을 권장함: client_id는 `LONGBRIDGE_OAUTH_CLIENT_ID`를 우선 쓰고, 비워 두고 Legacy Access Token도 없으면 `LONGBRIDGE_APP_KEY`를 호환용으로 씀. 먼저 상호 작용이 가능한 환경에서 `python scripts/generate_longbridge_oauth_token.py --client-id <client_id>`를 실행해 SDK token 캐시를 만듦
- GitHub Actions / Docker 같은 headless 환경에서는 분석 작업 중에 브라우저 인증을 기다릴 수 없음. 로컬의 `~/.longbridge/openapi/tokens/<client_id>` 파일을 base64로 바꿔 `LONGBRIDGE_OAUTH_TOKEN_CACHE_B64`에 설정하면 됨
- OAuth 실행은 SDK가 제공하는 `OAuthBuilder` / `Config.from_oauth`에 의존함. 지금 Linux/Docker 환경에 예전 SDK만 설치할 수 있다면 로그에 분명히 알려 주고 Longbridge를 자동으로 건너뛰며, YFinance / AkShare 대체 경로에는 영향이 없음
- Legacy API Key도 계속 호환됨: `LONGBRIDGE_APP_KEY`, `LONGBRIDGE_APP_SECRET`, `LONGBRIDGE_ACCESS_TOKEN`을 설정. 여기서 Access Token은 예전 API Key 자격 증명이며 OAuth access token이 아님
- 선택으로 `LONGBRIDGE_CONNECTION_COOLDOWN_SECONDS`를 설정해 연결 종료 계열 예외 뒤의 대기 시간(초)을 정할 수 있음(기본 15)
- 접속 지점은 `LONGBRIDGE_HTTP_URL`, `LONGBRIDGE_QUOTE_WS_URL`, `LONGBRIDGE_TRADE_WS_URL`, `LONGBRIDGE_REGION`으로 설정할 수 있음
- 그 밖의 선택 매개변수는 공식 [환경 변수 설명](https://open.longbridge.com/zh-CN/docs/getting-started#环境变量) 참고
- YFinance(미국 주식)나 AkShare(홍콩 주식)가 불완전한 데이터를 돌려줄 때만 자동으로 동작하며, A주 경로에는 영향이 없음
- 자격 증명을 설정하지 않으면 이 선택 데이터 소스를 만들지 않음. 실행 중 연결 종료 계열 예외가 나면 대기 시간 동안 Longbridge를 잠시 건너뛰어, 요청마다 재연결하는 일을 막음

### 둥팡차이푸 API가 자주 실패할 때

로그에 `RemoteDisconnected`, `push2his.eastmoney.com` 연결 끊김 같은 내용이 나오면 대부분 둥팡차이푸의 요청 제한 때문입니다. 다음을 권장합니다.

1. `.env`에 `ENABLE_EASTMONEY_PATCH=true`를 설정합니다
2. `MAX_WORKERS=1`로 동시 실행 수를 낮춥니다
3. Tushare를 설정했다면 Tushare 데이터 소스를 우선 씁니다

---

<a id="高级功能"></a>

## 고급 기능

### 홍콩 주식 지원

`hk` 접두사로 홍콩 주식 코드를 지정합니다.

```bash
STOCK_LIST=600519,hk00700,hk01810
```

홍콩 주식 일봉은 efinance, pytdx, baostock처럼 홍콩 주식 일봉을 지원하지 않는 데이터 소스를 건너뛰어, 홍콩 주식 코드가 다른 시장으로 잘못 연결되지 않게 합니다. 기본으로 AkShare/Tushare/YFinance/Longbridge 같은 홍콩 주식 경로가 대신 이어받습니다.

### ETF와 지수 분석

지수 추종형 ETF와 미국 지수(예: VOO, QQQ, SPY, 510050, SPX, DJI, IXIC)는 **지수 흐름, 추적 오차, 시장 유동성**만 분석하며, 펀드 운용사/발행사의 회사 단위 위험(소송, 평판, 경영진 변화 등)은 넣지 않습니다. 위험 경고와 실적 기대는 모두 지수 구성 종목 전체의 흐름을 바탕으로 해, 펀드 회사 뉴스를 대상 자체의 악재로 잘못 판단하지 않게 합니다. 자세한 내용은 Issue #274를 보세요.

### 여러 모델 바꿔 쓰기

모델을 여러 개 설정하면 시스템이 자동으로 바꿔 씁니다.

```bash
# Gemini(주력)
GEMINI_API_KEY=xxx
GEMINI_MODEL=gemini-3.1-pro-preview

# OpenAI 호환(예비)
OPENAI_API_KEY=xxx
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash
# deepseek-chat / deepseek-reasoner도 여전히 쓸 수 있지만, 공식적으로 2026/07/24 이후 지원 중단 예정입니다
```

### 고급 모델 라우팅(내부적으로 LiteLLM 사용)

자세한 내용은 [LLM 설정 가이드](LLM_CONFIG_GUIDE.md)를 보세요. 기본으로 쓸 때는 기본 모델, 예비 모델, 모델 채널만 이해하면 됩니다. 이 절까지 왔다면 하부의 [LiteLLM](https://github.com/BerriAI/litellm) 라우팅 기능을 직접 쓰려는 것이며, Proxy 서비스를 따로 실행할 필요는 없습니다.

**두 단계 구조**: 같은 모델의 여러 Key 교대 사용(Router)과 다른 모델로의 대체(Fallback)는 단계가 나뉘어 서로 간섭하지 않습니다.

**여러 Key + 다른 모델 대체 설정 예시**:

```env
# 기본 모델: Gemini Key 3개를 교대로 쓰며, 하나라도 429가 나면 Router가 자동으로 다음 Key로 전환
GEMINI_API_KEYS=key1,key2,key3
LITELLM_MODEL=gemini/gemini-3.1-pro-preview

# 다른 모델 대체: 기본 모델의 모든 Key가 실패하면 Claude → GPT 순서로 시도
# 해당 API Key 설정 필요: ANTHROPIC_API_KEY, OPENAI_API_KEY
LITELLM_FALLBACK_MODELS=anthropic/claude-sonnet-4-6,openai/gpt-5.4-mini
```

**예상 동작**: 첫 요청은 `key1`을 씁니다. 429가 나면 Router가 다음에는 `key2`를 씁니다. Key 3개를 모두 쓸 수 없으면 Claude로, 그것도 실패하면 GPT로 바꿉니다.

> ⚠️ `LITELLM_MODEL`에는 반드시 provider 접두사(예: `gemini/`, `anthropic/`, `openai/`)가 있어야 합니다.
> 그렇지 않으면 시스템이 어떤 API Key 묶음을 써야 할지 알 수 없습니다. 예전 형식의 `GEMINI_MODEL`(접두사 없음)은 `LITELLM_MODEL`을 설정하지 않았을 때 자동 추론에만 쓰입니다.

**의존성 안내**: `requirements.txt`에는 `openai>=1.0.0`이 남아 있습니다. LiteLLM이 내부적으로 OpenAI SDK를 통일 인터페이스로 쓰기 때문이며, 명시적으로 남겨 두어 버전 호환을 보장합니다. 사용자가 따로 설정할 필요는 없습니다.

**비전 모델(이미지에서 종목 코드 추출)**: 자세한 내용은 [LLM 설정 가이드 - Vision](LLM_CONFIG_GUIDE.md#扩展功能看图模型-vision-配置)을 보세요.

이미지에서 종목 코드를 추출하는 기능(예: `/api/v1/stocks/extract-from-image`)은 통일된 비전 모델 연결을 씁니다. 하부는 LiteLLM Vision과 OpenAI `image_url` 형식을 쓰며, Gemini, Claude, OpenAI, DeepSeek 같은 Vision 지원 모델을 지원합니다. `items`(code, name, confidence)와 호환용 `codes` 배열을 돌려줍니다.

> 호환성 안내: `/api/v1/stocks/extract-from-image` 응답에는 기존 `codes`에 더해 `items` 필드가 새로 생겼습니다. 하위 클라이언트가 엄격한 JSON Schema를 쓰고 모르는 필드를 받지 않는다면 schema를 함께 고치세요.

**스마트 가져오기**: 이미지 외에 CSV/Excel 파일과 클립보드 붙여넣기(`/api/v1/stocks/parse-import`)도 지원하며, 코드/이름 열을 자동으로 해석합니다. 이름→코드 해석은 로컬 매핑, 병음 매칭, AkShare 온라인 fallback을 지원합니다. `pypinyin`(병음 매칭)과 `openpyxl`(Excel 해석)이 필요하며, 둘 다 `requirements.txt`에 들어 있습니다.

- **AkShare 이름 해석 캐시**: 이름→코드 해석에 AkShare 온라인 fallback을 쓰면 결과를 1시간(TTL) 캐시해 잦은 요청을 막습니다. 처음 호출하거나 캐시가 만료되면 자동으로 새로 고칩니다.
- **CSV/Excel 열 이름**: `code`, `股票代码`, `代码`, `name`, `股票名称`, `名称` 등을 지원합니다(대소문자 무관). 머리글이 없으면 첫째 열을 코드, 둘째 열을 이름으로 봅니다.
- **텍스트 인코딩**: CSV와 클립보드 텍스트는 UTF-8(BOM 포함)과 GBK를 지원합니다.
- **흔한 해석 실패**: 파일이 너무 크거나(>2MB), 인코딩이 UTF-8/GBK가 아니거나, Excel 시트가 비어 있거나 손상되었거나, CSV 구분자/열 수가 맞지 않으면 API가 구체적인 오류를 돌려줍니다.

- **모델 우선순위**: `VISION_MODEL` > `LITELLM_MODEL` > 이미 있는 API Key로 추론(`OPENAI_VISION_MODEL`은 더 이상 쓰지 않으니 `VISION_MODEL`로 바꾸세요)
- **Provider 대체**: 기본 모델이 실패하면 `VISION_PROVIDER_PRIORITY`(기본 `gemini,anthropic,openai`)에 따라 다음으로 쓸 수 있는 provider로 자동 전환합니다
- **기본 모델이 Vision을 지원하지 않을 때**: 기본 모델이 DeepSeek처럼 Vision을 지원하지 않는 모델이라면, 이미지 추출용으로 `VISION_MODEL=openai/gpt-5.5`나 `gemini/gemini-3.1-pro-preview`를 명시할 수 있습니다
- **설정 검사**: `VISION_MODEL`을 설정했는데 해당 provider의 API Key가 없으면 시작할 때 warning을 출력하며, 이미지 추출 기능은 쓸 수 없습니다

### 디버그 모드

```bash
python main.py --debug
```

로그 파일 위치:
- 일반 로그: `logs/stock_analysis_YYYYMMDD.log`
- 디버그 로그: `logs/stock_analysis_debug_YYYYMMDD.log`

디버그 로그는 기본으로 프로젝트 자체의 DEBUG 정보를 남기지만, LiteLLM 내부 로그는 `WARNING`으로 낮춰서 스트리밍 생성 중에 token마다 서드파티 디버그 로그가 대량으로 쌓이지 않게 합니다. LiteLLM 내부를 자세히 봐야 한다면 `.env`에서 잠시 `LITELLM_LOG_LEVEL=DEBUG`로 설정하세요.

### SQLite 쓰기 안정화 설정

기본 파일형 SQLite는 연결할 때 `WAL`을 켜고 `busy_timeout`을 설정합니다. `save_daily_data()`도 `(code, date)` 기준의 일괄 원자적 upsert로 바뀌어, 일괄 갱신과 동시 쓰기에서 잠금 경쟁을 줄입니다.

조정하려면 `.env`에서 설정할 수 있습니다.

| 변수 | 기본값 | 설명 |
|------|-------|------|
| `SQLITE_WAL_ENABLED` | `true` | 파일형 SQLite에서 `journal_mode=WAL`을 쓸지 여부 |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | SQLite 잠금 대기 시간 초과(밀리초) |
| `SQLITE_WRITE_RETRY_MAX` | `3` | `database is locked` / `database table is locked`를 만났을 때 최대 재시도 횟수 |
| `SQLITE_WRITE_RETRY_BASE_DELAY` | `0.1` | 쓰기 재시도 기본 대기 시간(초, 지수적으로 늘어남) |

---

## 분석 판단의 실행 가능성
<!-- 계약 키(tests): metadata 省略或显式 `null` 均按无 metadata 处理 / 显式 `null` 时清空为 SQL `NULL` / 顶层显式 `null`、空值或非法值会被拒绝 / 正式字段为 legacy `NULL` 时会移除请求 object 中的 profile key -->

개별 종목 리포트의 매매 의견은 지지선, 저항선, 거래량/매물대, 주력 자금 흐름, 위험 이벤트를 함께 보고 보정해, 하루 등락이나 점수가 기준선을 넘었다는 이유만으로 "매수/매도" 사이를 크게 오가지 않게 합니다. 가격이 지지선과 저항선 사이에 있고 자금 흐름이 분명하지 않으면 리포트는 "보유, 박스권 관망, 흔들기 관찰" 같은 중립적이고 실행 가능한 의견을 먼저 냅니다. 지지선 근처에서 확인되었거나, 저항선을 유효하게 돌파했고 거래량·가격·자금이 받쳐 줄 때만 매수를, 핵심 지지선을 깨거나 주력 자금이 계속 빠져나갈 때만 매도/비중 축소를 냅니다.
이 조정은 실행 가능한 판단의 실행 중 저장과 프롬프트 제약 경로에 영향을 주지만, LLM 모델, LiteLLM 라우팅, Provider/Key와 그 호환 범위는 바꾸지 않으며, 설정 저장/정리 의미에도 영향을 주지 않습니다.
호환성 확인 결론: 설정과 모델 쪽 의미 외에, 이 판단 안정성 경로는 `src/analyzer.py`, `src/core/pipeline.py`, `src/core/backtest_engine.py`, `src/report_language.py`, `src/agent` 판단 경로의 실행 동작을 다룹니다. 리포트 판단 유형 매핑과 백테스트 진입점 연동을 다시 확인하는 것을 권장합니다.
확인 경로: 관련 로직은 위 실행 경로와 해당 테스트(`tests/test_backtest_engine.py`, `tests/test_analyzer_news_prompt.py`, `tests/test_decision_stability.py`, `tests/test_agent_pipeline.py` 등)에서 동작합니다. `src/config.py`, `src/report.py`, 저장/영속화 경로에 설정 필드나 정리 로직을 새로 추가하지 않았습니다.

### 제안 행동 분류(Taxonomy)(#1390 P0)

개별 종목 리포트는 `operation_advice` 자유 텍스트를 유지하면서, 선택 필드 `action` / `action_label`을 새로 추가합니다. 웹 이력 목록, 같은 종목 이력, StockBar, 백테스트 결과 행의 구조화 표시를 돕는 용도입니다. `decision_type`은 여전히 예전의 `buy|hold|sell` 3단계 통계 기준을 유지하며, `action`이 비어 있어도 기존 `decision_type` 추론 과정을 고쳐 쓰지 않습니다.

| `action` | 흔한 출처 텍스트(프로그램이 인식하는 문자열) | `decision_type` 연결 |
| --- | --- | --- |
| `buy` | `strong_buy`, `强烈买入`, `买入`, `布局`, `建仓` | `buy` |
| `add` | `add`, `加仓`, `增持`, `accumulate` | `buy` |
| `hold` | `hold`, `持有`, `持有观察`, `洗盘观察` | `hold` |
| `watch` | `watch`, `观望`, `等待`, `wait` | `hold` |
| `reduce` | `reduce`, `减仓`, `trim` | `sell` |
| `sell` | `sell`, `卖出`, `清仓`, `strong_sell`, `强烈卖出` | `sell` |
| `avoid` | `avoid`, `回避`, `规避`, `不建议买入`, `避免买入`, `do not buy` | `hold` |
| `alert` | `alert`, `风险预警`, `警惕`, `触发告警`, `risk alert` | `hold` |

(중국어 표현의 뜻: 买入=매수, 强烈买入=강력 매수, 布局/建仓=포지션 구축, 加仓/增持=추가 매수, 持有=보유, 持有观察=보유하며 관찰, 洗盘观察=흔들기 관찰, 观望=관망, 等待=대기, 减仓=비중 축소, 卖出=매도, 清仓=전량 매도, 强烈卖出=강력 매도, 回避/规避=회피, 不建议买入/避免买入=매수 비권장, 风险预警=위험 경고, 警惕=경계, 触发告警=경고 발동.)

위 표의 `decision_type` 연결은 8단계 action과 예전 3단계 통계 기준의 호환 관계만 설명합니다. #1390 P0은 `action`을 기존 `decision_type`에 자동으로 거꾸로 쓰지 않습니다. 상위에서 명시한 `action`과 `decision_type`이 함께 있는데 의미가 다르면, 3단계 통계, 백테스트, 예전 리포트 기준은 여전히 `decision_type` / 원래 추론 과정을 따르며, `action/action_label`은 구조화 표시를 돕는 역할만 합니다.

알 수 없거나 모호한 의견은 `watch`나 `hold`로 채우지 않고, 빈 `action/action_label`을 돌려줍니다. 웹 이력 카드, StockBar, 같은 종목 이력 서랍, 백테스트 결과 행은 예전 기록에 `action/action_label`이 없으면 `operation_advice`로 표시용 fallback을 합니다. 이 fallback은 프런트엔드 태그에만 영향을 주며, 안정적인 API action이나 이후 신호 자산과 같지 않습니다. 웹 표시 계층은 `action`과 `action_label`을 함께 받으면 현재 화면 언어에 맞춰 `action`으로 태그를 우선 만듭니다. API의 `action_label`은 여전히 리포트 언어로 만들어, 웹이 아닌 클라이언트나 `action`이 없는 호환 표시에 쓰입니다. 시장 복기와 그 밖의 개별 종목이 아닌 리포트는 매매 `action`을 만들지 않고 `operation_advice` 텍스트만 남깁니다. `dashboard.phase_decision.immediate_action`은 시장 단계 안전장치 리포트 필드이며, #1390 P0의 8단계 action 파생에 참여하지 않습니다. 최종 시장 단계는 여전히 `report.meta.market_phase_summary.phase`에서 옵니다.

#1390 P0은 이후 신호 자산 필드를 기존 summary, 이력 목록, StockBar, 백테스트 응답에 펼쳐 넣지 않습니다. #1390 P1부터는 별도의 `DecisionSignal` 리소스가 `horizon`, `plan_quality`, `status` 같은 더 세밀한 계획 필드를 받으며, 기존 리포트 주 계약은 바꾸지 않고, 이력을 백필하지 않으며, 설정 항목도 추가하지 않습니다.

### 의사결정 신호 자산(#1390 P1/P2/P3/P4/P5)

`DecisionSignal`은 별도의 백엔드 리소스로, AI 의견을 조회·중복 제거·상태 갱신이 가능한 신호 자산으로 쌓는 데 씁니다. `operation_advice`를 대신하지 않고 `decision_type=buy|hold|sell`을 늘리지도 않습니다. #1390 P2부터 일반 개별 종목 분석과 Agent 개별 종목 분석은 분석 이력을 저장한 뒤, 최종 `AnalysisResult`에서 best-effort로 `source_type=analysis` 신호 하나를 추출합니다. API나 service를 명시적으로 호출하는 방법도 그대로 남아 있습니다.

자동 추출은 이미 만들어진 리포트의 구조화 필드만 쓰며, Markdown을 다시 해석하지 않고, 예전 이력을 백필하지 않으며, 설정 항목을 추가하거나 리포트 주 계약을 바꾸지 않습니다. 추출 실패, 제안 행동이 알 수 없거나 모호함, 개별 종목이 아닌 리포트, 시장을 알 수 없음이면 기록을 건너뛰며 분석 리포트 저장에는 영향이 없습니다. `source_report_id`는 방금 저장한 `AnalysisHistory.id`를 씁니다. `trace_id`는 실행 진단 trace를 우선 쓰고, 없으면 pipeline trace나 `query_id`로 대신합니다. `stock_name`은 `AnalysisResult.name`에서, `trigger_source`는 실행 진입점에서 오며, 없으면 `system`입니다.

P2 자동 추출의 시장 단계는 저장 스냅샷의 `market_phase_summary.phase`를 먼저, 그다음 `AnalysisResult.market_phase_summary.phase`를 읽습니다. 데이터 품질은 저장 스냅샷의 `analysis_context_pack_overview.data_quality`를 먼저, 그다음 `AnalysisResult.analysis_context_pack_overview.data_quality`를 읽습니다. 가격 계획은 이력 저장 때의 목표가 해석 규칙을 재사용해 `dashboard.battle_plan.sniper_points.ideal_buy/secondary_buy/stop_loss/take_profit`을 `entry_low/entry_high/stop_loss/target_price`로 대응시킵니다. `ideal_buy`만 있으면 `entry_low`에, `secondary_buy`만 있으면 `entry_high`에 쓰고, 둘 다 있으면 유효한 가격을 정렬해 `entry_low <= entry_high`가 되게 합니다. 손절가나 목표가가 없으면 service가 자동 계산하는 `plan_quality`만 낮아지며, 필드를 지어내지 않습니다. `watch_conditions`는 `dashboard.phase_decision.watch_conditions`를 먼저 읽고, 없을 때만 `dashboard.battle_plan.action_checklist`를 읽습니다. `catalyst_summary`는 `dashboard.intelligence.positive_catalysts`가 있고 목록일 때만 씁니다. `confidence`는 리포트의 신뢰 등급을 보수적으로 대응시킵니다: `高/high=0.8`, `中/medium/mid=0.6`, `低/low=0.4`(高/中/低 = 높음/중간/낮음). 원래 신뢰 등급은 `metadata`에 남습니다.

P3부터 수명 주기는 `DecisionSignalService`가 한 곳에서 채웁니다. 명시적으로 넘긴 `horizon` / `expires_at`이 항상 우선합니다. `horizon`을 넘기지 않으면 `alert`이거나 `premarket/intraday/lunch_break/closing_auction`일 때 기본값은 `intraday`, `postmarket/non_trading/unknown`이거나 단계 맥락이 없을 때 기본값은 `3d`입니다. `expires_at`을 넘기지 않으면 `intraday`는 `metadata.market_phase_summary.minutes_to_close/minutes_to_open`을 먼저 읽고, 맥락이 없으면 결정적인 TTL fallback(A주 4시간, 홍콩 주식 5.5시간, 미국 주식 6.5시간, 알 수 없음 4시간)을 씁니다. `1d/3d/5d/10d`는 달력 날짜 기준이고, `swing/long`은 자동으로 만료되지 않습니다. fallback TTL은 거래일 달력 맥락이 없을 때의 기능 저하 방침일 뿐, 실제 거래소 마감 시각과 같지 않습니다. 자동 추출은 `market_phase_summary.phase/session_date/minutes_to_open/minutes_to_close`만 저민감 힌트로 `metadata.market_phase_summary`에 쓰며, 최종 `horizon/expires_at`은 여전히 service가 계산합니다.

핵심 필드에는 `stock_code`, `stock_name`, `market`, `source_type`, `source_agent`, `source_report_id`, `trace_id`, `decision_profile`, `market_phase`, `trigger_source`, `action`, `action_label`, `confidence`, `score`, `horizon`, `entry_low`, `entry_high`, `stop_loss`, `target_price`, `invalidation`, `watch_conditions`, `reason`, `risk_summary`, `catalyst_summary`, `evidence`, `data_quality_summary`, `plan_quality`, `status`, `expires_at`, `created_at`, `updated_at`, `metadata`가 있습니다. `action`은 8단계 제안 행동을 재사용합니다. `decision_profile`은 `conservative|balanced|aggressive`를 지원하며, 데이터베이스의 `NULL`은 legacy/unknown만 뜻합니다. `market_phase`는 시장 단계 열거형을 재사용합니다. `source_type`은 `analysis|agent|alert|market_review|manual`, `status`는 `active|expired|invalidated|closed|archived`, `horizon`은 `intraday|1d|3d|5d|10d|swing|long`을 지원합니다.

`confidence`는 `0.0-1.0`, `score`는 `0-100`이며, 과거 리포트의 `sentiment_score`와 분리되어 있습니다. 가격 계획 필드 `entry_low`, `entry_high`, `stop_loss`, `target_price`는 유한한 양수여야 하며, `entry_low`와 `entry_high`를 함께 넘기면 `entry_low <= entry_high`여야 합니다. `plan_quality`는 `complete|partial|minimal|unknown`을 지원합니다. 호출자가 올바른 값을 명시하면 그대로 저장하고, 넘기지 않으면 service가 계산합니다. 진입 구간(`entry_low`나 `entry_high` 중 하나라도 값이 있음)을 1항목, `stop_loss`, `target_price`, `invalidation`, `watch_conditions`를 각각 1항목으로 셉니다. 2항목을 채우면 `partial`, 4항목 이상이면 `complete`, action/reason만 있으면 `minimal`입니다.

새 API:

- `POST /api/v1/decision-signals`: 만들거나 같은 출처 키로 중복 제거하며, `{ item, created }`를 HTTP 200으로 돌려줍니다. 새로 기록할 때 `decision_profile`을 생략하면 기본값 `balanced`이고, 올바른 `conservative|balanced|aggressive`를 넘길 수도 있습니다. 최상위에 명시적인 `null`, 빈 값, 잘못된 값이 있으면 거부합니다. 최상위 값이 없을 때만 올바른 `metadata.decision_profile`로 대신하며, 쓰기 전에 `metadata.decision_profile`을 정식 필드 값과 맞춥니다. metadata를 생략하거나 명시적으로 `null`이면 metadata 없음으로 처리하고, object는 얕은 복사하며, object가 아니면 거부합니다. 정확한 중복 제거 키는 `(source_report_id, source_type, market, stock_code, decision_profile, action, horizon, market_phase)`입니다. report는 없지만 `trace_id`가 있으면 `(trace_id, source_type, market, stock_code, decision_profile, action, horizon, market_phase)`를 쓰며, 둘 다 없으면 중복을 제거하지 않습니다. 정확 일치, relaxed fallback, horizon/phase fill, expired refresh, active invalidation, stale backfill invalidation 모두 same-profile 의미를 따릅니다. `NULL`은 `NULL`과만, 비어 있지 않은 profile은 같은 profile과만 일치하며, expired duplicate refresh는 `decision_profile`을 바꾸지 않습니다. 정확 일치에 실패하면 같은 출처 + `source_type/market/stock_code/decision_profile/action`으로 좁은 relaxed fallback을 하며, 예전 기록에 비어 있는 `horizon/market_phase`만 채웁니다. `horizon`은 새 값을 service가 기본으로 만들었을 때만 채울 수 있습니다. 기간을 명시해 다르거나, 이미 다른 단계가 있거나, profile이 다르면 여러 개를 그대로 둡니다. 같은 출처의 expired 같은 profile 기록과 일치하고 새 요청이 active이면서 미래의 `expires_at`을 가지고 있으면, 그 기록을 그 자리에서 갱신하고 `created=false`를 돌려주며, 이번 연장은 새로운 active 활성화 이벤트로 처리합니다. active로 새로 만들었거나 expired를 연장한 bullish 신호(`buy/add`)는 같은 profile의 이전 active defensive 신호(`reduce/sell/avoid`)를 `invalidated`로 표시하며, 반대도 마찬가지입니다. 서로 다른 비어 있지 않은 profile은 행동이 반대여도 함께 존재할 수 있습니다. active duplicate retry도 같은 profile 무효화 보정을 다시 실행해, 지난번에 생성은 성공했지만 무효화 기록이 실패한 partial create를 복구합니다. 일반적인 예전 duplicate/replay는 새로운 활성화 이벤트로 보지 않습니다. `hold/watch/alert`는 자동 무효화를 일으키지 않습니다. 갱신이든 중복 일치든 밖으로는 `created=false`를 돌려주며, 이 기능은 동시성 고유성을 보장하지 않습니다.
- `GET /api/v1/decision-signals`: 페이지 단위 조회. `market`, `stock_code`, `action`, `market_phase`, `decision_profile`, `source_type`, `source_report_id`, `trace_id`, `trigger_source`, `status`, 기간, `holding_only`, `account_id`를 지원합니다. `decision_profile`을 생략하거나 비워 보내면 profile 조건 없이 모든 profile을 돌려줍니다. `decision_profile=unknown`은 legacy `NULL` 행을 조회하고, 올바른 profile은 정확히 일치하는 것만 찾습니다.
- `GET /api/v1/decision-signals/{signal_id}`: 하나를 조회하며, 없으면 404를 돌려줍니다.
- `PATCH /api/v1/decision-signals/{signal_id}/status`: 올바른 상태와 선택적 `metadata`를 갱신합니다. metadata를 생략하면 원래 값을 유지하고, 명시적인 `null`이면 SQL `NULL`로 비우며, object이면 통째로 바꿉니다. 정식 `decision_profile`이 `NULL`이 아니면 metadata 안의 충돌하는 profile을 덮어씁니다. 정식 필드가 legacy `NULL`이면 요청 object에서 profile key를 지우며, 정식 필드로 올리지 않습니다. `expired/invalidated/closed/archived` 같은 종료 상태는 PATCH로 바로 `active`로 되돌릴 수 없으며, expired 연장은 여전히 active + 미래 `expires_at`으로 다시 `POST`해야만 할 수 있습니다.
- `GET /api/v1/decision-signals/latest/{stock_code}`: 종목별 최신 active 신호를 조회하며, 기본값은 `limit=1`입니다.

읽기 진입점은 지연 만료를 합니다. 목록, 상세, latest 조회 전에 `expires_at`이 지난 active 신호를 expired로 표시합니다. 만들 때 이미 만료된 active 신호는 바로 expired로 저장합니다. 같은 출처의 expired 신호는 active + 미래 `expires_at`으로 다시 `POST`해야만 연장할 수 있으며, `PATCH /status`는 `expires_at`을 받지 않습니다. `expired|invalidated|closed|archived`는 PATCH로 바로 살아나지 않고, `closed|invalidated|archived`는 create 경로로도 살아나지 않습니다. 반대 신호로 자동 무효화될 때는 예전 신호의 `metadata`에 `invalidated_by_signal_id`, `invalidated_reason`, `invalidated_at`, `previous_status`를 합쳐서 씁니다. 정식 profile이 `NULL`이 아니면 metadata profile을 맞추고, 정식 profile이 legacy `NULL`이면 원래 metadata profile을 유지하고 정식 필드로 올리지 않습니다. 예전 metadata JSON이 손상되었거나 object가 아니면 무효화 metadata로 바꾸고 해당 replacement marker를 기록하며, 새 신호 생성은 막지 않습니다. 시간 필드는 UTC로 정규화해 시간대 없는 `datetime`으로 저장하고 비교합니다. 시간대가 있는 입력은 먼저 UTC로 바꾼 뒤 `tzinfo`를 지우고, 시간대 없는 입력은 UTC로 봅니다. API 응답은 계속 시간대 접미사 없는 ISO 문자열을 돌려줍니다. 종목 코드는 저장과 조회 모두 `market`에 따라 결정적으로 정규화합니다. A주 `600519`, `SH600519`, `600519.SH` 같은 흔한 변형은 같은 코드로, 홍콩 주식 `00700`, `HK00700`, `00700.HK`는 `HK00700`으로 일치시키며, 미국 주식 ticker는 대문자로 통일합니다. `holding_only=true`는 active 계좌의 `portfolio_positions` 가운데 `quantity > 0`인 캐시 보유 종목만 읽고, 보유 종목의 `(market, stock_code)`로 신호를 맞추며, 선택적으로 active `account_id`를 지정할 수 있습니다. 이 조회는 포트폴리오 snapshot replay를 호출하지 않으며, 캐시가 없으면 빈 결과를 돌려주므로 먼저 portfolio snapshot API로 캐시를 새로 고쳐야 합니다.

`source_report_id`는 비어 있어도 되고, 이력 기록이 있는지 강제로 확인하지 않습니다. 이력 기록을 지울 때는 `source_type=analysis`이면서 `source_report_id`가 실제로 지운 ID와 일치하는 이력 연결 신호만 명시적으로 정리하며, `manual/agent/alert/market_review` 같은 약한 참조 신호는 ID가 겹친다는 이유만으로 지우지 않습니다. 목록 API는 `source_report_id`와 `trace_id`로 typed filter를 지원합니다. `task_id`, `alert_trigger_id` 같은 이후 연결 필드는 먼저 `metadata`에 넣으며, P1은 별도 열이나 typed filter를 추가하지 않고, 이후 연동 단계에서 별도 계약으로 올립니다. JSON 필드, 긴 텍스트 필드, 표시용 짧은 텍스트 필드(`stock_name/source_agent/trigger_source/action_label`)는 기록하기 전에 신호 전용 민감 정보 가림을 거칩니다. 민감한 key, Bearer, Authorization/Cookie header나 그 대입문, token처럼 보이는 문자열, 그 밖의 민감한 대입, webhook URL, URL userinfo, 민감한 query/fragment 매개변수가 붙은 URL을 다룹니다. 일반 근거 URL은 출처를 추적할 수 있도록 남기며, 긴 텍스트에는 진단 텍스트의 300자 자르기를 적용하지 않습니다. `trace_id`는 같은 출처 중복 제거용 식별 필드이므로, 가려질 민감한 credential이 들어 있으면 API는 손실된 가림 값을 저장하지 않고 요청을 거부합니다.

이 API들은 기존 `/api/v1/*` 관리자 인증을 그대로 따릅니다. `ADMIN_AUTH_ENABLED=true`이면 유효한 관리자 세션 Cookie가 있어야 하며, 이 기능은 별도의 인증 방식을 추가하지 않습니다.

#1390 P4는 웹에 기존 `DecisionSignal` API를 연결했습니다. #1756 이후 사이드바의 "AI 의견"(AI 建议) 진입점 `/decision-signals`는 여전히 구조화된 의사결정 신호를 한곳에서 조회하는 곳이며, 기본으로 `status=active` 신호를 보여 주고 시장, 종목 코드, 행동, 시장 단계, 출처, 출처 리포트 ID, 상태로 거를 수 있습니다. 타임라인 영역에는 profile filter가 새로 생겼으며, 목록 API의 server-side `decision_profile` 조회를 재사용합니다. `unknown`은 legacy `NULL` 행을 거르고 표시할 때만 쓰며, 일반 고급 목록에는 profile filter를 추가하지 않습니다. 페이지에는 종목 코드로 최신 active 신호를 조회하는 진입점도 있습니다. 카드, 상세, 타임라인 표시는 정식 `decision_profile` 필드를 먼저 읽고, 필드가 없을 때만 legacy metadata로 대신합니다. 명시적인 `null`, 과거 누락, 잘못된 profile은 unknown으로 표시합니다. 신호 상세에는 행동, 성향, 신뢰도/점수, horizon, plan_quality, market_phase, 가격 계획, 위험, 관찰 조건, 출처 리포트, 데이터 품질이 표시됩니다. 웹은 신호를 `closed`, `invalidated`, `archived`로만 표시할 수 있으며, 종료 상태를 active로 되돌리는 기능은 없습니다.

#1390 P5는 신호 단위 피드백, 사후 평가, 통계 sidecar를 새로 추가했으며, `decision_signals` 주 테이블을 늘리지 않고, `analysis_history_id`에 묶인 `BacktestResult`도 재사용하지 않습니다. `decision_signal_feedback`는 `signal_id`별로 최신 `useful|not_useful` 피드백, 선택적 이유/메모, 출처를 저장합니다. `decision_signal_outcomes`는 `(signal_id, horizon, engine_version)` 기준으로 멱등하게 사후 결과를 저장하며, 현재 `engine_version=decision-signal-v1`입니다. Outcome은 평가할 때 `action/market/market_phase/source_type/source_agent/plan_quality/data_quality_level/holding_state` 같은 통계 차원을 고정하므로, 과거 통계가 나중의 live join으로 바뀌지 않습니다. 과거 리포트를 지울 때는 먼저 `source_type=analysis`이면서 지운 이력 ID에 묶인 신호를 찾고, 해당 feedback/outcome 하위 테이블을 정리합니다.

P5 사후 평가는 일봉으로 검증할 수 있는 `1d/3d/5d/10d`만 지원합니다. 기간의 의미는 anchor 뒤의 1/3/5/10개 `StockDaily` 거래 봉이며, `DecisionSignalService._horizon_days()`의 달력 날짜 만료 의미를 재사용하지 않습니다. `anchor_date`는 `metadata.market_phase_summary.session_date`를 먼저 읽고, 없으면 `created_at.date()`를 씁니다. anchor 당일에는 반드시 `StockDaily.close`가 있어야 하며, 전 거래일로 물러나지 않습니다. 행동 대응은 `buy/add -> up`, `hold -> not_down`, `reduce/sell/avoid -> not_up`입니다. `watch/alert`, `intraday/swing/long`, anchor 가격 없음, 이후 봉 부족 등은 `eval_status=unable`과 명확한 `unable_reason`으로 기록합니다. anchor 가격 없음, 잘못된 anchor 가격, 이후 봉 부족, 기간 종가 없음/잘못됨은 복구 가능한 unable이라, 이후 기본 재실행 때 데이터가 채워지면 다시 평가합니다. 방향이 없는 행동, 지원하지 않는 horizon, anchor date 없음은 종료 unable이라, 기본으로 멱등하게 건너뜁니다. 자동 추출은 실행 중에 `portfolio_context.quantity`도 받을 수 있지만, 저민감 `holding_state=holding|empty|unknown`만 metadata에 써서 사후 스냅샷에 쓰며, 수량, 계좌, 원가는 저장하지 않습니다.

P5는 웹 `/decision-signals` 페이지의 필터 영역 아래에 현재 outcome engine의 전체 통계 카드를 보여 줍니다. 상세 서랍은 필요할 때 그 신호의 outcomes를 읽고, useful/not useful 피드백을 제출할 수 있습니다. 이 페이지는 새 내비게이션 페이지를 만들지 않고, BacktestPage에 들어가지 않으며, 백그라운드 예약 작업도 추가하지 않습니다. 사후 계산은 `POST /api/v1/decision-signals/outcomes/run`으로 명시적으로 실행합니다. 일괄 실행은 기본으로 outcome이 없는 신호를 먼저 처리하고, 그다음 복구 가능한 unable을 다시 시도하므로, 이미 완료되었거나 종료 unable인 최신 신호가 계속 `limit`을 차지하지 않습니다.

#1758은 같은 `GET /api/v1/decision-signals/outcomes/stats` 응답에 `profile_calibration`을 덧붙여, decision profile, profile + action, profile + horizon, profile + market phase, profile + 고정된 data quality, profile source별로 구조화된 묶음을 돌려줍니다. 묶음마다 따로 `completed >= 30`을 요구하며, 부족하면 counts만 남기고 다섯 가지 설명 지표는 모두 `null`을 돌려줍니다. 웹은 표본 수와 "样本不足，仅供观察。"(표본이 부족해 참고용으로만 관찰)만 보여 주며, 성향 순위를 매기거나 추천하지 않습니다. 적중/미적중률의 분모는 `hit + miss`이고, 평가 불가율의 분모는 total입니다. 최대 불리 변동은 outcome에 저장된 `start_price/min_low/max_high`로만 계산하며 시세를 읽지 않습니다. `decision_profile`과 metadata 기반 `profile_source`는 조회 시점에 연결된 신호의 현재 귀속이며, action, horizon, market phase, data quality는 계속 outcome에 고정된 값을 씁니다. 새 outcome의 data quality는 summary에 명시된 level이 없을 때만 정규화된 metadata level로 대신하며, 기존 outcome은 조용히 다시 쓰이지 않습니다. 웹은 원래 통계 요청과 Card를 재사용하며, 보수/균형/공격과 행동별/기간별 두 가지 보기만 제공합니다. 예전 백엔드에 새 필드가 없어도 원래 통계는 그대로 쓸 수 있습니다. 전체 기준은 [DecisionSignal 의사결정 신호](decision-signals.md)를 보세요.

보유 종목 페이지는 AI 의견을 막지 않는 보강 정보로 비동기 로드합니다. 포트폴리오 스냅샷과 위험 모듈은 원래 로직대로 먼저 그리고, 이어서 현재 스냅샷의 고유한 보유 종목마다 `GET /api/v1/decision-signals/latest/{stock_code}?market=<market>&limit=1`로 latest active 신호를 조회합니다. 더 이상 `holding_only=true` 공통 목록을 페이지 단위로 훑지 않으며, 고정된 페이지 수로 잘리는 일도 없습니다. 보유 종목 하나의 latest 조회가 실패하면, 페이지는 이미 불러온 다른 신호를 그대로 두고 눈에 보이는 기능 저하 안내를 보여 줍니다. 일치하는 신호가 없으면 보유 종목 행에 빈 자리 표시를 보여 줍니다. 매칭 로직은 웹의 종목 코드 같은 뜻 규칙을 재사용하며, A주 `600519/SH600519/600519.SH`, 홍콩 주식 `00700/HK00700/00700.HK`, 미국 주식의 대소문자 ticker를 다룹니다.

#1390 P6는 `DecisionSignal`을 경고, 알림, 포트폴리오 위험에 재사용하며, 테이블, 마이그레이션, 설정을 추가하지 않습니다. 실제 종목 단위 경고가 발동하면 같은 종목의 latest active 신호를 먼저 연결하고, 저민감 `decision_signal_summary`를 `alert_triggers.diagnostics`에 씁니다. active 신호가 없으면 worker는 최소한의 `source_type=alert`, `action=alert` 신호만 만듭니다. `trace_id=alert-rule-<hash>`는 같은 출처 재시도의 best-effort 멱등 중복 제거에만 쓰이며, active 신호 본체를 덮어쓰지 않고, 단계가 달라 중복이 생기지 않도록 `market_phase`도 쓰지 않습니다. 경고 알림과 분석 알림은 요약 가운데 `action/horizon/reason/watch_conditions/risk_summary/source_report_id` 같은 공개 필드만 인용하며, 알림이 실패해도 trigger나 신호 기록에는 영향이 없습니다. `GET /api/v1/portfolio/risk`에는 `decision_signal_risk` 집계 블록이 추가되며, 현재 보유 종목의 active `sell/reduce/alert` 신호만 세고 `avoid/buy/add/hold/watch`는 분명히 뺍니다. 신호 조회가 실패하면 위험 API는 fail-open하며, 웹 위험 영역은 기능 저하 상태를 보여 줍니다.

#1390 P7의 마무리 문서는 [DecisionSignal 의사결정 신호](decision-signals.md)를 보세요. #1756은 `DECISION_SIGNAL_*` 설정이나 실행 스위치를 추가하지 않지만, `decision_signals`에 nullable `decision_profile` 필드, API 요청/응답 필드, profile-aware index를 추가합니다. 기존 SQLite는 열이 없을 때만 `ALTER TABLE ADD COLUMN`을 실행하며, 테이블을 drop/rebuild하거나 예전 index를 지우지 않습니다. 마이그레이션은 profile-aware index를 멱등하게 만들고, `metadata_json`을 행마다 방어적으로 해석해 올바른 `metadata.decision_profile`만 백필하며, invalid JSON, object가 아닌 값, 잘못된 profile은 `NULL`로 둡니다. 지금의 롤백 방법은 해당 코드를 revert하는 것입니다. 롤백하면 신호 추출과 기록은 멈추지만, 기존 리포트 저장, 경고 발동, 알림 발송, 포트폴리오 위험의 주 흐름은 신호 풀에 의존하지 않고 계속 동작합니다. 과거 signal, feedback, outcome 데이터는 자동으로 정리되지 않습니다.

일반 개별 종목 과거 리포트 상세에는 더 이상 그 리포트에서 추출한 `source_type=analysis` 신호를 함께 보여 주지 않으며, 리포트 상세를 연다고 `source_report_id=<recordId>` 신호 조회를 하지도 않습니다. 구조화된 AI 의견을 보려면 `/decision-signals` 페이지에서 출처 리포트 ID로 거르거나, `/decision-signals?sourceReportId=<recordId>` deep link를 열거나, 종목으로 조회하세요. 출처 리포트 ID를 넣거나 이 URL 매개변수를 쓰면, 웹은 `source_type=analysis + source_report_id=<recordId>` 정확 조회를 하며, 기본 `status=active` 같은 다른 목록 필터를 겹치지 않아 예전 리포트의 best-effort 지연 백필 의미를 유지합니다.

<a id="回测功能"></a>

## 백테스트 기능

백테스트 모듈은 과거 AI 분석 기록을 자동으로 사후 검증해, 분석 의견이 얼마나 맞았는지 평가합니다.

### 동작 원리

1. 대기 기간(기본 14일)이 지난 `AnalysisHistory` 기록을 고릅니다
2. 분석일 이후의 일봉 데이터(이후 캔들)를 가져옵니다
3. 매매 의견으로 기대 방향을 추론하고 실제 흐름과 비교합니다
4. 익절/손절 도달 여부를 평가하고 실행 수익을 모의 계산합니다
5. 전체와 종목별 두 기준으로 성과 지표를 모읍니다

### 매매 의견 대응표

| 매매 의견(프로그램이 인식하는 문자열) | 포지션 추론 | 기대 방향 | 성공 조건 |
|---------|---------|---------|---------|
| 买入/加仓/strong buy(매수/추가 매수) | long | up | 상승률 ≥ 중립 구간 |
| 卖出/减仓/strong sell(매도/비중 축소) | cash | down | 하락률 ≥ 중립 구간 |
| 持有/持有观察/震荡观望/洗盘观察/hold/hold and watch/range-bound watch/shakeout watch(보유/보유 관찰/박스권 관망/흔들기 관찰) | long | not_down | 뚜렷하게 하락하지 않음 |
| 观望/等待/wait(관망/대기) | cash | flat | 가격이 중립 구간 안에 있음 |

### 설정

`.env`에서 다음 변수를 설정합니다(모두 기본값이 있으며 선택 사항).

| 변수 | 기본값 | 설명 |
|------|-------|------|
| `BACKTEST_ENABLED` | `true` | 매일 분석 후 백테스트를 자동으로 실행할지 여부 |
| `BACKTEST_EVAL_WINDOW_DAYS` | `10` | 평가 기간(거래일 수) |
| `BACKTEST_MIN_AGE_DAYS` | `14` | N일 이전의 기록만 백테스트해, 데이터가 불완전한 일을 피함 |
| `BACKTEST_ENGINE_VERSION` | `v1` | 엔진 버전. 로직을 바꿀 때 결과를 구분하는 데 씀 |
| `BACKTEST_NEUTRAL_BAND_PCT` | `2.0` | 중립 구간 임곗값(%). ±2% 안이면 횡보로 봄 |

### 자동 실행

백테스트는 매일 분석 흐름이 끝난 뒤 자동으로 실행됩니다(막지 않으며, 실패해도 알림 발송에는 영향 없음). API로 직접 실행할 수도 있습니다.

### 평가 지표

| 지표 | 설명 |
|------|------|
| `direction_accuracy_pct` | 방향 예측 정확도(기대 방향과 실제가 일치) |
| `win_rate_pct` | 승률(승 / (승+패), 중립 제외) |
| `avg_stock_return_pct` | 평균 종목 수익률 |
| `avg_simulated_return_pct` | 평균 모의 실행 수익률(익절·손절 청산 포함) |
| `stop_loss_trigger_rate` | 손절 발동률(손절을 설정한 기록만 집계) |
| `take_profit_trigger_rate` | 익절 발동률(익절을 설정한 기록만 집계) |

---

<a id="本地-webui-管理界面"></a>

## 로컬 WebUI 관리 화면
<!-- 계약 키(tests): Web 报告页在策略点位和资讯之后默认折叠展示数据块状态 -->

WebUI는 FastAPI API 서비스와 같은 서비스 프로세스를 씁니다. 시작한 뒤 브라우저에서 설정 관리, 직접 분석, 작업 진행 확인, 과거 리포트, 백테스트, 보유 종목 관리, 스마트 가져오기 등을 할 수 있습니다. 인증, 클라우드 서버 접속, API 호출 세부 사항은 아래 설명을 보세요.

### FastAPI API 서비스

FastAPI는 RESTful API 서비스를 제공하며, 설정 관리와 분석 실행을 지원합니다.

### 시작 방법

| 명령 | 설명 |
|------|------|
| `python main.py --serve` | API 서비스 시작 + 전체 분석 한 번 실행 |
| `python main.py --serve-only` | API 서비스만 시작. 분석을 직접 실행할 수 있고 설정에서 켜 둔 예약 실행도 복구하지만, 시작할 때 바로 분석하지는 않음 |

### 기능

- 📝 **설정 관리** - 관심 종목 목록 보기/수정
- 🗂️ **홈 화면 세 가지 보기** - 홈 화면에는 「历史 / 自选 / 今日」(이력 / 관심 종목 / 오늘) 작업 영역이 있으며 기본으로 이력 보기에 들어갑니다. 모바일 서랍 안의 세 목록은 각자의 안쪽 영역이 세로 터치 스크롤을 받아, 바깥 카드가 제스처를 잘라 내지 않으며, 데스크톱에서는 카드 경계 자르기를 유지합니다. 관심 종목 행은 마우스나 키보드로 확인된 최신 분석 상세를 열 수 있고, 안내는 항상 현재의 찾는 중, 찾기 실패, 상세 없음 확인 상태를 따릅니다. stock-bar 요청과 작업 완료 후 데이터 새로 고침은 시작할 때 확인 대기 상태로 들어가며, 다시 확인하거나 상태를 알 수 없는 동안에는 예전 stock-bar나 fallback 리포트를 열지 않습니다. 관심 종목 페이지를 새로 고치면 목록과 상세 상태를 함께 다시 시도하며, 종목별 상세 보충 조회는 고정된 동시 실행 상한을 쓰고, 새로 고치거나 페이지 상태가 바뀌면 쓸모없어진 묶음을 취소합니다. 전체 또는 "오늘 아직 분석하지 않은" 종목만 일괄 제출할 수 있습니다
- 📌 **작업 패널 접기** - 홈 화면 작업 패널을 접고 펼 수 있습니다. 접으면 pending/processing 요약만 남기고 사이드바 공간을 관심 종목 목록에 더 내줍니다. 접힌 상태는 현재 페이지 세션 동안 유지됩니다
- 🧭 **화면 언어 전환** - 로그인 상태와 로그아웃 상태 모두 화면 언어(`zh` / `en`)를 빠르게 바꿀 수 있습니다. `REPORT_LANGUAGE`와 별개이며, 정적 UI 문구와 내비게이션 뼈대에 쓰입니다
- 🚀 **빠른 분석** - API로 개별 종목 분석을 실행합니다. 홈 화면에는 "시장 복기" 버튼과 일회성 시장 선택기도 있어, Docker/server 모드에서 서버 기본값이나 잠시 고른 하나/여러 시장으로 백그라운드 복기를 실행할 수 있습니다
- 🎯 **전략 선택** - 홈 화면에서 분석 전략 skill을 명시적으로 고를 수 있습니다. `skills`를 넘기지 않으면 시스템 기본 전략으로 실행해, 예전 동작과 호환을 유지하기 쉽습니다
- 🧪 **오늘 상태/작업 새로 고침 중복 방지** - 홈 화면 「今日」(오늘)과 「自选」(관심 종목)은 시간대를 고려한 이력 구간으로 판단해 페이지 단위 이력 조회를 보냅니다. 작업이 끝난 뒤에는 가장 최근의 stock bar 새로 고침이 성공해야만 실패 상태를 지워, 예전 요청이 순서가 뒤바뀌어 새 상태를 덮어쓰고 중복 제출이 생기는 일을 막습니다
- 🧭 **첫 설정 안내** - 홈 화면은 읽기 전용 설정 상태를 읽어, LLM 주 채널이나 관심 종목 같은 기본 항목이 없으면 무엇이 빠졌는지 알려 주고 시스템 설정으로 안내합니다
- 📊 **실시간 진행 상황** - 분석 작업 상태가 실시간으로 바뀌며 여러 작업을 동시에 진행할 수 있습니다. 일반 분석 과정은 LLM 단계에 들어가면 LiteLLM 스트리밍 생성을 먼저 시도하고, 작업 SSE로 더 세밀한 `message/progress`를 돌려보냅니다
- 🧪 **종목 선별 작업 복구 가능** - 종목 선별 구현은 AlphaSift를 참고했습니다. 페이지에서 백그라운드 작업을 제출한 뒤 스냅샷, 후보 맥락, LLM 재정렬, 최종 보강 같은 단계를 폴링하며, 다른 페이지로 갔다 돌아와도 현재 작업 진행 상황이나 최종 결과를 복구합니다. 화제 순위 새로 고침은 종목 선별과 동시에 할 수 있고, 상세는 테마를 고른 뒤 필요할 때 불러옵니다. 구성 종목은 둥팡차이푸와 퉁화순(同花顺)을 함께 시도하며, DSA 검색 서비스를 재사용해 최근 소식을 보충할 수도 있습니다. 5분 안에 다시 선별하면 기본으로 최근 성공 스냅샷을 재사용합니다. 실행할 때마다 점수 차이가 제한된 비슷한 점수 후보 안에서 다른 조합을 만들 수 있지만, 분명히 앞선 후보는 계속 보호되며, 엄격한 필터, 위험 제약, 점수는 영향을 받지 않습니다
- 🗂️ **시장 복기 작업 확인** - 홈 화면에서 시장 복기를 실행하면 `task_id`를 돌려주고 `GET /api/v1/analysis/status/{task_id}`를 폴링해, 진행 중/완료/실패 상황을 눈으로 확인할 수 있게 하며, 실패하면 오류 내용을 그대로 보여 줍니다
- 🗂️ **시장 복기 이력 별도 진입점** - 시장 복기 이력은 전용 진입점으로 일반 개별 종목 이력과 분리됩니다. `stock_code=MARKET` + `report_type=market_review`로 시장 복기 기록을 바로 조회하고 다시 보는 것을 권장합니다
- 🧾 **시장 복기 이력 재사용** - 시장 복기 작업은 분석 이력에 저장되며 `report_type`은 `market_review`입니다. 이력 목록/상세에서 해당 Markdown이나 상세 페이지를 바로 열 수 있으며, 분석을 다시 계산하지 않습니다
- 🧭 **시장 위치 카드** - A주 일반 분석 리포트는 시장 테마 계층과 개별 종목 위치 계층을 보여 주며, 시장 주도 테마, 주요 관련 테마, 테마 단계, 종목 위치, 누락된 근거를 구분합니다
- 🧩 **입력 데이터 블록 확인** - 일반 분석 리포트는 이력 상세, 동기 응답, completed 작업 상태에서 저민감 `AnalysisContextPack` overview를 돌려주며, 웹 리포트 페이지는 전략 가격대와 뉴스 다음에 데이터 블록 상태, 출처, 누락 원인, 기능 저하 요약을 기본으로 접어서 보여 줍니다
- 💬 **종목 질문의 주 대상** - 서버가 명확한 코드나 인덱스에서 유일한 이름을 받으면 대상을 저장합니다. 일반 추가 질문, 새로 고침, 다시 열기, 대화 전환은 서버에서 복구합니다. 종목을 분명히 바꿀 때만 주 대상을 갱신하고, 비교는 이번 범위만 넓히며, 처음 비교할 때 아무 종목이나 하나를 고르지 않습니다. 리포트 이동은 안내일 뿐이며 확인된 상태를 스스로 만들지 않습니다. 모델이 실패하거나 멈춰도 이미 받은 대상은 취소되지 않습니다.
- 🧠 **대화별 Skill 선택** - 종목 질문 대화는 현재 Skill 선택을 저장합니다. 새로 고치거나 대화를 바꾸면 각자의 선택을 복구하며, 새 대화는 계속 서버 기본 Skill을 씁니다
- 📈 **백테스트 검증** - 과거 분석의 정확도를 평가하고 방향 승률과 모의 수익을 조회합니다
- 🔗 **API 문서** - `/docs`에 접속하면 Swagger UI를 볼 수 있습니다

### 이번 변경과 관련된 제품 동작

- 웹 언어 상태는 두 단계 구조입니다. `dsa.uiLanguage`(브라우저에 저장)와 `REPORT_LANGUAGE`(리포트와 종목 질문의 기본 출력)는 분리되어 있습니다.
  - `dsa.uiLanguage`는 WebUI 문구와 내비게이션 언어(`zh` / `en`)만 정하며, 우선순위는 로컬 저장 값 -> 브라우저 언어 -> 기본 `zh`입니다.
  - `REPORT_LANGUAGE`는 리포트 텍스트, 종목 약칭 현지화, 리포트 페이지 고정 문구, `context.report_language`를 주지 않은 Agent Chat 답변(`zh` / `en` / `ko`)을 정합니다. 한국어 리포트를 받으려면 `REPORT_LANGUAGE=ko`로 설정하세요.
- 페이지 언어 전환은 사용자 경험 개선이며, 회귀 검증 증거 기록 범위에 들지 않습니다. 스크린샷과 명령은 PR 절차에 따라 PR 설명에서 따로 관리하세요.
- 이번 변경은 요청 단위의 리포트 언어 덮어쓰기 매개변수만 추가하며, `provider`/`model`/`base_url`의 설정 마이그레이션과 정리 로직은 바꾸지 않습니다.

### API 목록

| API | 메서드 | 설명 |
|------|------|------|
| `/api/v1/analysis/analyze` | POST | 종목 분석 실행 |
| `/api/v1/analysis/market-review` | POST | 백그라운드에서 시장 복기 실행. 요청 본문에 `{"send_notification": true, "region": "cn,us"}`를 넣을 수 있음. `region`은 이번 요청만 덮어쓰며, `main.py --market-review`, `bot`과 같은 `GeminiAnalyzer/SearchService/NotificationService` 조립 방식을 재사용함 |
| `/api/v1/analysis/tasks` | GET | 작업 목록 조회 |
| `/api/v1/analysis/tasks/stream` | GET (SSE) | 작업 실시간 상태 스트림 구독. `task_progress`는 선택적으로 `flow_event` 증분 실행 흐름 이벤트를 포함 |
| `/api/v1/analysis/tasks/{task_id}/flow` | GET | active task의 실행 흐름 스냅샷 조회 |
| `/api/v1/analysis/status/{task_id}` | GET | 작업 상태 조회 |
| `/api/v1/screening/screen/tasks` | POST | 백그라운드 종목 선별 작업 제출(먼저 `SCREENING_ENABLED`를 켜야 함) |
| `/api/v1/screening/screen/tasks/{task_id}` | GET | 종목 선별 작업 상태와 완료 결과 조회 |
| `/api/v1/history` | GET | 분석 이력 조회 |
| `/api/v1/history/{record_id}/share-image` | GET | 브라우저용 과거 리포트 PNG 공유 이미지 생성. 쓸 수 있는 `MD2IMG_ENGINE`이 필요함 |
| `/api/v1/history/{record_id}/share-image-html` | GET | Electron 데스크톱 앱의 내장 Chromium이 캡처할 제한된 공유 이미지 HTML 생성 |
| `/api/v1/history/{record_id}/diagnostics` | GET | 과거 리포트의 실행 진단 요약과 민감 정보를 가린 복사용 텍스트 조회 |
| `/api/v1/history/{record_id}/flow` | GET | 과거 리포트의 실행 흐름 스냅샷 조회. 일반 개별 종목과 `MARKET/market_review` 시장 복기가 같은 계약을 씀 |
| `/api/v1/decision-signals` | POST | 의사결정 신호를 명시적으로 만들거나 같은 출처 키로 중복 제거하며, `{ item, created }`를 돌려줌 |
| `/api/v1/decision-signals` | GET | 의사결정 신호 페이지 조회. 종목, 시장, 행동, 단계, 성향, 출처, 상태, 기간, cache-only 보유 종목 필터 지원 |
| `/api/v1/decision-signals/outcomes/run` | POST | 신호 사후 평가를 명시적으로 실행. 기본으로 completed/종료 unable은 건너뛰고 복구 가능한 unable은 다시 계산하며, `force=true`이면 다시 계산해 덮어씀 |
| `/api/v1/decision-signals/outcomes` | GET | 신호 사후 결과 페이지 조회 |
| `/api/v1/decision-signals/outcomes/stats` | GET | 현재 사후 평가 엔진의 통계 조회. 기본으로 archived 신호는 뺌 |
| `/api/v1/decision-signals/{signal_id}/outcomes` | GET | 신호 하나의 현재 사후 평가 엔진 결과 조회 |
| `/api/v1/decision-signals/{signal_id}/feedback` | GET | 신호 하나의 사용자 피드백 조회. 피드백이 없으면 `feedback_value=null` |
| `/api/v1/decision-signals/{signal_id}/feedback` | PUT | 신호 하나의 `useful|not_useful` 피드백 기록 또는 갱신 |
| `/api/v1/decision-signals/{signal_id}` | GET | 의사결정 신호 하나 조회. 읽기 전에 지연 만료를 실행 |
| `/api/v1/decision-signals/{signal_id}/status` | PATCH | 의사결정 신호 상태와 선택적 metadata 갱신 |
| `/api/v1/decision-signals/latest/{stock_code}` | GET | 지정한 종목의 최신 active 의사결정 신호 조회 |
| `/api/v1/usage/summary?period=today|month|all` | GET | 호출 유형과 모델별로 LLM 호출 수와 Token 사용량 요약 |
| `/api/v1/usage/dashboard?period=today|month|all&limit=50` | GET | Token 사용량 대시보드 데이터: 총량, Prompt/Completion 구분, 모델별 사용량, 호출 유형 분포, 최근 호출 상세. 웹에서는 왼쪽 내비게이션의 "用量"(사용량) 메뉴 |
| `/api/v1/backtest/run` | POST | 백테스트 실행 |
| `/api/v1/backtest/results` | GET | 백테스트 결과 조회(페이지 단위) |
| `/api/v1/backtest/performance` | GET | 전체 백테스트 성과 조회 |
| `/api/v1/backtest/performance/{code}` | GET | 종목별 백테스트 성과 조회 |
| `/api/v1/stocks/extract-from-image` | POST | 이미지에서 종목 코드 추출(multipart, 시간 초과 60초) |
| `/api/v1/stocks/parse-import` | POST | CSV/Excel/클립보드 해석(multipart file 또는 JSON `{"text":"..."}`, 파일 2MB 이하, 텍스트 100KB 이하) |
| `/api/health` | GET | 상태 확인 |
| `/docs` | GET | API Swagger 문서 |

> 안내: `POST /api/v1/analysis/analyze`는 `async_mode=false`일 때 종목 하나만 지원합니다. 여러 종목 `stock_codes`는 `async_mode=true`를 써야 합니다. 비동기 `202` 응답은 종목 하나이면 `task_id`를, 여러 종목이면 `accepted` / `duplicates` 요약 구조를 돌려줍니다.
> 안내: `POST /api/v1/analysis/analyze`는 `skills`로 전략 skill ID 목록을 넘길 수 있으며, 넘기지 않으면 서버 기본 전략으로 실행합니다. 예전 호출과의 호환을 위해 `strategies` 필드도 호환 별칭으로 남아 있습니다.
> 안내: `POST /api/v1/analysis/analyze`는 `analysis_phase=auto|premarket|intraday|postmarket`를 지원하며 기본값은 `auto`입니다. `auto`가 아니면 이번 분석 단계와 파생 단계 표시만 덮어쓰고, 실제 거래일 달력 시각은 바꾸지 않습니다. accepted response, 메모리 task status, 작업 목록, SSE는 요청 단계를 그대로 보여 주며, 최종 리포트 단계는 `report.meta.market_phase_summary.phase`를 기준으로 합니다.
> 안내: `POST /api/v1/analysis/analyze`는 `report_language=zh|en|ko`를 지원하며 `reportLanguage`도 별칭으로 받습니다. 넘기지 않으면 전역 `REPORT_LANGUAGE`(또는 환경의 `Config.report_language`)로 돌아갑니다. 이 필드는 이번 분석의 리포트 텍스트, `report.meta.report_language`, 저장된 표시에만 영향을 주며 실행 설정으로 저장되지 않습니다.
> 안내: 웹 홈 화면의 전략 드롭다운은 전략을 명시적으로 고르는 선택 진입점입니다. 사용자가 직접 고르지 않으면 `skills`를 보내지 않아 예전 클라이언트 동작과 같고, 전략을 고르면 이 API로 넘어가 작업 상태와 이력 스냅샷에 남습니다.
> 안내: `POST /api/v1/analysis/market-review`는 백엔드와 CLI/Bot이 함께 쓰는 설정 경로(`GeminiAnalyzer(config=...)`와 같은 검색/프롬프트 구성 진입점)를 씁니다. Provider 호환 라우팅은 `litellm_model`, `llm_model_list`를 먼저 인식해 쓰고, 설정하지 않았다면 legacy `GEMINI_*`, `OPENAI_*`, `ANTHROPIC_*`, `DEEPSEEK_*` 키로 돌아갑니다. provider, Base URL, LiteLLM 라우팅 의미를 추가하거나 바꾸지 않습니다.
> 안내: `POST /api/v1/analysis/market-review`는 `report_language=zh|en|ko`(별칭 `reportLanguage` 지원)도 받습니다. 넘기지 않으면 마찬가지로 전역 `REPORT_LANGUAGE`로 돌아갑니다. 이 매개변수는 이번 복기 리포트 텍스트와 구조화 반환 필드의 언어 관련 내용에만 영향을 줍니다. Bot, schedule, CLI, 버튼으로 실행하는 `main.py --market-review`는 여전히 전역 설정을 따르며, 요청 단위 덮어쓰기 기능은 추가하지 않았습니다.
> 안내: `POST /api/v1/analysis/market-review`에는 길이 1–64의 문자열 필드 `region`을 선택적으로 넘길 수 있으며, `cn`, `hk`, `us`, `jp`, `kr`, `both` 또는 쉼표로 구분한 올바르고 비어 있지 않은 부분 집합(예: `cn,us`)을 지원합니다. 요청 계층은 대소문자, 공백, 중복, 시장 순서를 정리합니다. 빈 문자열, 빈 token, 알 수 없는 token, `both`와 다른 시장을 섞은 값은 전체를 4xx로 돌려주며, 일부만 실행하거나 대체 값으로 돌아가지 않습니다. 필드를 생략하면 계속 전역 `MARKET_REVIEW_REGION`을 읽습니다.
> 안내: 홈 화면의 시장 선택기는 이번 웹 실행만 덮어쓰며, 설정 읽기/저장 API를 호출하지 않고 LocalStorage에도 쓰지 않습니다. "服务器默认"(서버 기본값)을 고르면 요청에서 `region`을 생략하며, UI는 웹 Settings의 saved/display 값으로 실행 시 실제 시장을 추측하지 않습니다. 백엔드는 작업 제출 경계에서 유일한 canonical 실제 실행 값을 정하며, accepted 응답, pending/processing/completed 상태, 작업 목록, `task_created`/`task_started`/`task_progress`/`task_completed` SSE, 완료 상태의 구조화 payload, History 목록 항목의 `region`과 `context_snapshot.market_review_region`이 모두 이 값을 재사용합니다. 장기 설정인 `MARKET_REVIEW_REGION`은 예전의 너그러운 필터/대체 의미를 유지하며, CLI, Bot, schedule, 기본 `cn` 의미는 그대로입니다.
> 안내: `POST /api/v1/analysis/market-review`는 웹 / 데스크톱 앱에서 사람이 직접 실행하는 진입점이라, 누르면 바로 시장 복기 작업을 제출하며 `TRADING_DAY_CHECK_ENABLED=true`나 그날 관련 시장의 휴장 때문에 건너뛰지 않습니다. 예약 실행, GitHub Actions 직접 실행, CLI 기본 진입점은 여전히 거래일 확인을 따르며, `--force-run`이나 workflow `force_run`으로 무시할 수 있습니다.
> 감사 근거: 우선순위와 대체 의미는 `src/config.py`의 `Config._load_from_env()`를 기준으로 합니다(`LITELLM_CONFIG` > `LLM_CHANNELS` > legacy). 함께 보는 회귀 테스트는 `tests/test_llm_channel_config.py`(설정 출처 해석)와 `tests/test_market_review_runtime.py`(공유 조립 경로)입니다. 이 API는 현재 단일 프로세스/단일 서버 수준의 중복 방지만 제공하므로, 여러 인스턴스로 배포한다면 외부 작업 대기열이나 분산 잠금으로 전역 멱등성을 보완해야 합니다.
> 안내: `POST /api/v1/analysis/market-review`를 실행하면 리포트가 `report_type=market_review`로 이력 DB에 기록됩니다. `/api/v1/history`나 `/api/v1/history/{record_id}`로 과거 Markdown을 바로 조회할 수 있어, 분석을 다시 계산할 필요가 없습니다.
> 안내: 이력 목록에 `report_type` 조회 매개변수가 생겼습니다. `stock_code=MARKET&report_type=market_review`로 시장 복기 이력만 따로 읽을 수 있으며, 일반 개별 종목 이력 로직과 완전히 분리됩니다.
> 안내: `POST /api/v1/analysis/market-review`의 작업 상태와 이력 저장에는 모두 `market_review_payload`가 들어갑니다. 그중 `region`은 이번에 실제로 실행한 canonical 시장 문자열이며, 그 밖에 `market_scope`, `color_scheme`, `sections`, `sectors`, `concepts`, `news`, `market_light`, `indices` 같은 구조화 필드가 있습니다. 여러 시장 결과는 지역별로 `markets`에 저장됩니다. 웹의 Markdown 렌더링, 이력 상세, 공유 이미지는 이 구조화 필드를 재사용하며, 구조화 필드가 비었거나 일부만 있으면 필드별로 원래 Markdown으로 돌아갑니다.
> 안내: 실행 흐름 스냅샷 API는 `lanes/nodes/edges/events/summary` 통일 계약을 돌려줍니다. active task에 diagnostics가 없으면 skeleton flow를 돌려주고, 작업 SSE가 실제 `flow_event`를 받았다면 스냅샷에 최근 증분 이벤트가 들어갑니다. completed history는 `context_snapshot.diagnostics`와 `analysis_context_pack_overview`로 전체 구조를 우선 만듭니다. `cancel_requested/cancelled`는 올바른 상태이며 failed로 바뀌지 않습니다.
> 안내: `market_review_payload`의 `breadth`는 시장 폭 데이터를 실제로 쓸 수 있을 때만 내려옵니다. 미국/홍콩 주식이거나 API를 잠시 쓸 수 없으면 이 필드를 내려보내지 않습니다. 프런트엔드 표시 계층은 "필드 없음"을 0이 아니라 "데이터 없음"으로 처리해야 합니다.
> 안내: 이 endpoint가 `task_id`를 돌려주면 WebUI는 `GET /api/v1/analysis/status/{task_id}`를 폴링해 상태를 보여 줍니다. 상태가 `completed`이면 완료 안내(리포트가 만들어졌고 설정대로 알림을 보냄)를 보여 주고, `failed`이면 프런트엔드 오류 영역에 `error` 원인을 보여 줍니다.
> 안내: `GET /api/v1/history/{record_id}/diagnostics`는 이력 기록의 기본 키 ID나 `query_id`를 받으며, `normal/degraded/failed/unknown` 요약, 핵심 경로 구성 요소, 민감 정보를 가린 복사용 `copy_text`를 돌려줍니다. 진단 스냅샷이 없는 예전 리포트는 `unknown`을 돌려주며 리포트 읽기에는 영향이 없습니다.
> 안내: `GET /api/v1/history`의 목록 요약은 `stock_code`로 같은 종목의 이력을 페이지 단위로 조회할 수 있으며, 추세 판단, 분석 요약, 모델 이름, 분석 당시 가격/등락률 같은 선택 필드를 돌려줍니다. 스냅샷 필드가 없는 예전 기록은 빈 값을 돌려줍니다. `created_at`과 `/api/v1/history/stocks`의 `last_analysis_time`은 서버 시간대 오프셋이 붙은 ISO 8601 타임스탬프를 쓰며, 날짜 필터는 여전히 서버 현지 날짜 기준으로 해석합니다. 웹 리포트 페이지의 "과거 추세" 서랍은 이 API로 같은 종목의 이력을 불러옵니다.
> 안내: `GET /api/v1/usage/dashboard`는 `llm_usage` 감사 테이블을 재사용하며, 설정 항목이나 데이터베이스 마이그레이션을 추가하지 않습니다. API는 이미 저장된 호출 수, Prompt/Completion/Total Token 집계, 모델별 사용량, 최근 호출 기록만 돌려주며, 모델 맥락 창이나 provider 메타데이터를 추정하지 않습니다.
> 안내(Issue #1520): 목록의 모델 이름 표시 필드는 이력 스냅샷의 `model_used`에서만 오며, 이력 추적 표시에만 쓰입니다. 실행 시 모델 라우팅(`litellm_model`, `llm_model_list`), Provider, Base URL, 설정 마이그레이션/정리 의미에는 영향이 없습니다. 되돌리려면 이번 커밋을 되돌리면 되며, 운영 중인 이력 조회/서랍/API 경로의 호환성은 그대로입니다.
> 안내: 이력 상세, 동기 분석 응답, completed 작업 상태는 `report.details.analysis_context_pack_overview`로 저민감 입력 데이터 블록 overview를 돌려줍니다. 그중 동기 분석 응답은 이번에 저장된 `analysis_history.context_snapshot`에 의존하므로, `SAVE_CONTEXT_SNAPSHOT=false`이면 새 기록에서 overview를 돌려준다고 보장하지 않습니다. `details.context_snapshot`은 이 최상위 필드를 빼며, 전체 `AnalysisContextPack`이나 Prompt summary를 돌려주지 않습니다.
> 종목 질문 상태: `POST /api/v1/agent/chat`, `/chat/stream`은 서버의 대화 스냅샷으로 주 대상을 정하며, `context.stock_code`를 사실로 받아들이지 않습니다. 리포트 hint는 완전한 canonical / 종목 또는 지수 유형이 일치할 때만 재사용합니다. detail, accepted, non-stream 응답은 `active_stock_context`(code/name/canonical/type), `session_state_version`, `session_generation`을 제공합니다. 메시지, 명시한 Skill, 종목은 같은 수락 트랜잭션에서 커밋되며, 실행은 이 스냅샷을 쓰고 종목을 되쓰지 않습니다. 종목을 분명히 바꾸면 예전 대상에 딸린 데이터를 지웁니다. 비교는 이번에 명시한 scope만 넓힙니다. 금융 약어 / 거래소 조각을 종목 매개변수로 잘못 쓴 경우는 실제 scope guard가 여전히 거부하며, 도구 이름은 여전히 정확히 일치해야 합니다. 대상이 없는 일반 전략 질문은 빈 종목 scope를 쓰고, 모호하거나 확인할 수 없는 종목 전환에는 일반적인 확인 질문을 돌려줍니다. `context.report_language`는 여전히 전역 `REPORT_LANGUAGE`보다 우선합니다. 알고 있는 generation을 요청과 함께 보낼 수 있으며, 충돌하면 SSE는 `session_state_conflict`를, non-stream은 409를 돌려줍니다. 새로 고친 뒤 직접 다시 시도하세요. 자동으로 다시 보내지 않습니다. 예전 API에 새 필드가 모두 없으면 웹은 확인되지 않음으로 표시하며 텍스트로 추측하지 않습니다. 일부 필드만 없으면 프로토콜 오류입니다. 예전 이력과 데이터를 지우지 않는 업그레이드 / 롤백은 [LLM 설정 가이드](LLM_CONFIG_GUIDE.md#问股会话状态与升级)를 보세요.

> Skill 대화 상태: 최상위 `skills`가 요청 선택의 유일한 출처입니다. 생략하거나 `null`이면 저장된 선택을 그대로 쓰고, 선택이 없으면 실행 설정의 기본값을 씁니다. 명시적인 `[]`는 비운 것으로 저장하고 내장 기본값을 쓰며, 설정의 비어 있지 않은 Skill을 켜지 않습니다. 비어 있지 않은 목록은 기존 catalog 기준으로 정리하고 중복을 없애며, 섞인 항목은 유효한 것만 남기고, 모두 잘못되었으면 예전 값을 이어받고 빈 상태를 쓰지 않습니다. `context.skills/strategies`는 제거되었습니다. 수락 트랜잭션은 메시지, 명시한 Skill, 종목을 함께 쓰며, 성공해야만 accepted를 보냅니다. detail의 `session_state.selected_skill_ids`는 여전히 선택 없음 `null`, 비움 `[]`, 저장된 목록을 따로 돌려줍니다. 웹은 저장된 값과 제출 대기 초안을 구분합니다. 손대지 않은 추가 질문은 선택을 생략하며, 충돌이 나도 초안을 저장된 값처럼 보이게 하지 않습니다. 대화를 지우면 상태도 함께 지워집니다.
> 안내: `POST /api/v1/backtest/run`에 `analysis_date_from` / `analysis_date_to`(`YYYY-MM-DD`) 요청 매개변수가 생겨, 과거 분석 날짜로 후보를 거를 수 있습니다. `analysis_date_from > analysis_date_to`이면 API는 400 `invalid_params`를 돌려줍니다.
> 안내: 백테스트가 성공했지만 새로 저장된 결과가 없으면 `BacktestRunResponse.message`에 읽을 수 있는 진단 설명을, `diagnostics`에 문제 해결 맥락(예: `empty_reason`, `analysis_date_from`, `analysis_date_to`, `eval_window_days`, `min_age_days`, `limit`)을 돌려줍니다.
> 안내: `GET /api/v1/backtest/results`, `GET /api/v1/backtest/performance`, `GET /api/v1/backtest/performance/{code}`도 `analysis_date_from`, `analysis_date_to`를 지원하며, 넘기지 않으면 예전 동작을 유지합니다.

> 호환성 감사 근거:
> - 공식 출처: LiteLLM OpenAI-compatible provider 문서 <https://docs.litellm.ai/docs/providers/openai_compatible>, OpenAI Chat API 문서 <https://platform.openai.com/docs/api-reference/chat/create>, DeepSeek API 문서 <https://api-docs.deepseek.com/>.
> - 의존성 버전: 프로젝트 제약은 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`(`requirements.txt` 참고)이며, 위 호환 의미 회귀 테스트는 이 버전 범위에서 실행합니다.
> - 다시 확인할 수 있는 테스트:
>   - `tests/test_llm_channel_config.py`(설정 출처 우선순위와 provider/base url 매핑)
>   - `tests/test_market_review_runtime.py`(`build_market_review_runtime` 조립 경로 재사용)
>   - `tests/test_analysis_api_contract.py`(`/api/v1/analysis/market-review` 계약과 작업 상태 경로)
> - 롤백/되돌리기: 새 경로에 문제가 있으면 먼저 과거의 `LITELLM_MODEL`, `LITELLM_FALLBACK_MODELS`와 legacy `GEMINI_*` / `OPENAI_*` / `ANTHROPIC_*` / `DEEPSEEK_*`를 복원하거나, 데스크톱 앱 백업 또는 관리자 인증을 켠 웹의 `POST /api/v1/system/config/import`로 되돌린 뒤 다시 시작합니다. 실행 수준에서는 `LITELLM_CONFIG` / `LLM_CHANNELS`를 잠시 비워 legacy로 돌아가게 할 수 있습니다.

> 진행 스트림 안내: `GET /api/v1/analysis/tasks/stream`에는 `task_created / task_started / task_completed / task_failed` 외에 `task_progress` 이벤트가 새로 생겼습니다. 일반 분석 과정은 "시세 준비 / 뉴스 검색 / 맥락 정리 / LLM 생성 / 리포트 저장" 같은 단계에서 `progress`와 `message`를 계속 갱신합니다. LiteLLM 스트리밍 응답은 서버에서 전체 텍스트로만 모으며, 최종 JSON 해석에 성공해야 과거 리포트를 저장합니다. 첫 chunk 전에 스트리밍을 쓸 수 없으면 자동으로 원래의 비스트리밍 호출로 돌아갑니다. 일부 chunk가 나온 뒤 실패하면 먼저 같은 모델로 비스트리밍 재시도를 하고, 그것도 실패하면 기존의 기본 모델->예비 모델 순서로 계속 시도합니다.  
> 작업 진행 콜백에 예외가 나도 주 경로는 멈추지 않으며, 시스템은 경고를 warning 수준으로 올리고 서버 로그에 전체 예외를 남겨 SSE 전송 끊김을 찾기 쉽게 합니다.
>  
> 안내: 이 기능은 실행 시 SSE와 대체 경로의 세부 사항이므로 전체 가이드(`full-guide*.md`)에 먼저 기록하며, `README.md`에서는 자세한 동작 분기를 펼치지 않습니다.

**호출 예시**:
```bash
# 상태 확인
curl http://127.0.0.1:8000/api/health

# 분석 실행(A주)
curl -X POST http://127.0.0.1:8000/api/v1/analysis/analyze \
  -H 'Content-Type: application/json' \
  -d '{"stock_code": "600519"}'

# 전략 함께 넘기기(선택)
curl -X POST http://127.0.0.1:8000/api/v1/analysis/analyze \
  -H 'Content-Type: application/json' \
  -d '{"stock_code": "600519", "skills": ["bull_trend", "growth_quality"]}'

# 작업 상태 조회
curl http://127.0.0.1:8000/api/v1/analysis/status/<task_id>

# 오늘 LLM 사용량 조회
curl "http://127.0.0.1:8000/api/v1/usage/summary?period=today"

# 오늘 LLM 사용량 대시보드 조회
curl "http://127.0.0.1:8000/api/v1/usage/dashboard?period=today&limit=50"

# 백테스트 실행(전체 종목)
curl -X POST http://127.0.0.1:8000/api/v1/backtest/run \
  -H 'Content-Type: application/json' \
  -d '{"force": false}'

# 백테스트 실행(종목 지정)
curl -X POST http://127.0.0.1:8000/api/v1/backtest/run \
  -H 'Content-Type: application/json' \
  -d '{"code": "600519", "force": false}'

# 백테스트 실행(분석 날짜 구간)
curl -X POST http://127.0.0.1:8000/api/v1/backtest/run \
  -H 'Content-Type: application/json' \
  -d '{"analysis_date_from": "2026-05-01", "analysis_date_to": "2026-05-31", "limit": 100}'

# 백테스트 실행(종목 지정 + 날짜 구간 + 강제 재실행)
curl -X POST http://127.0.0.1:8000/api/v1/backtest/run \
  -H 'Content-Type: application/json' \
  -d '{"code": "600519", "force": true, "analysis_date_from": "2026-05-01", "analysis_date_to": "2026-05-31"}'

# 전체 백테스트 성과 조회
curl http://127.0.0.1:8000/api/v1/backtest/performance

# 종목별 백테스트 성과 조회
curl http://127.0.0.1:8000/api/v1/backtest/performance/600519

# 백테스트 결과 페이지 조회
curl "http://127.0.0.1:8000/api/v1/backtest/results?page=1&limit=20"
```

(Windows PowerShell에서는 `curl` 대신 `curl.exe`를 쓰고, 작은따옴표로 감싼 JSON은 따옴표 처리 방식이 달라 그대로 동작하지 않을 수 있습니다. 브라우저에서 `/docs`(Swagger UI)를 열어 실행하는 편이 쉽습니다.)

### 사용자 정의 설정

기본 포트를 바꾸거나 같은 네트워크(LAN)에서 접속을 허용하려면:

```bash
python main.py --serve-only --host 0.0.0.0 --port 8888
```

### 지원하는 종목 코드 형식

| 유형 | 형식 | 예시 |
|------|------|------|
| A주 | 6자리 숫자 | `600519`, `000001`, `300750` |
| 베이징증권거래소 | 8/4/92로 시작하는 6자리, `BJ` 접두사나 `.BJ` 접미사 지원 | `920748`, `BJ920493`, `920493.BJ` |
| 홍콩 주식 | hk + 5자리 숫자 | `hk00700`, `hk09988` |
| 미국 주식 | 영문자 1-5개(선택적으로 .X 접미사) | `AAPL`, `TSLA`, `BRK.B` |
| 일본 주식 | Yahoo 접미사 `.T` | `7203.T`, `6758.T` |
| 한국 주식 | Yahoo 접미사 `.KS`(코스피) / `.KQ`(코스닥) | `005930.KS`, `035720.KQ` |
| 미국 지수 | SPX/DJI/IXIC 등 | `SPX`, `DJI`, `NASDAQ`, `VIX` |

### 주의 사항

- 브라우저 접속: `http://127.0.0.1:8000`(또는 설정한 포트)
- 클라우드 서버에 배포한 뒤 브라우저에 어떤 주소를 넣어야 할지 모르겠다면 [클라우드 서버 웹 화면 접속 가이드](deploy-webui-cloud.md)를 보세요
- 분석이 끝나면 설정한 채널로 자동으로 알림을 보냅니다
- 이 기능은 GitHub Actions 환경에서는 자동으로 꺼집니다
- [openclaw Skill 연동 가이드](openclaw-skill-integration.md)도 참고하세요

---

## 자주 묻는 질문

### Q: 알림 메시지가 잘려요
A: WeCom(기업용 위챗)/Feishu(페이슈)에는 메시지 길이 제한이 있어 시스템이 자동으로 나눠 보냅니다. 전체 내용이 필요하면 Feishu 클라우드 문서 기능을 설정하세요.

### Q: 데이터를 가져오지 못해요
A: AkShare는 웹 수집 방식을 써서 잠시 요청 제한에 걸릴 수 있습니다. 시스템에 재시도 장치가 있으니 보통 몇 분 기다렸다가 다시 하면 됩니다.

### Q: 관심 종목은 어떻게 추가하나요?
A: `STOCK_LIST` 환경 변수를 고치세요. 여러 코드는 영문 쉼표로 구분하는 것을 권장합니다. 시스템은 중국어 쉼표, 모점(、), 세미콜론, 공백, 줄바꿈도 인식하며, 웹 설정 페이지에서 저장하거나 관심 종목을 추가·삭제하면 영문 쉼표로 정리합니다.

관심 종목을 추가·삭제하거나 `STOCK_LIST`만 저장하면 종목 목록만 실행 중에 바로 바뀌고, 다른 실행 설정과 컨테이너 환경 덮어쓰기는 그대로 유지됩니다. 일부 설정만 저장할 때는 관계없는 기존 LLM 채널이나 모델 선택 오류 때문에 막히지 않습니다. 모델, 채널, 라우팅 파일, 관련 자격 증명을 바꿀 때는 여전히 모델 의존 관계 전체를 확인합니다. 이번 저장이 Agent 경로를 켜는 경우도 마찬가지로 확인합니다. `AGENT_BACKEND` / `AGENT_GENERATION_BACKEND`를 LiteLLM(`auto` 포함)으로 바꾸거나, `AGENT_MODE=true`로 설정하거나, `all`이 아닌 `AGENT_SKILLS`를 설정하는 경우입니다. 뒤의 두 가지는 일반 분석의 Agent 분기를 쓰며 자체 `LLMToolAdapter`를 갖고 있어 `AGENT_BACKEND`에 따라 정해지지 않습니다. `AGENT_MODE`를 끄기만 하거나, `AGENT_SKILLS`를 `all`이나 빈 값으로 두거나, 관계없는 저장을 할 때는 LLM 설정의 영향을 받지 않습니다. 이미 있는 종료된 `codex_app_server` 설정은 남겨 둬도 관계없는 저장을 막지 않지만, 이 종료된 값을 명시적으로 저장하거나 가져오면 여전히 거부됩니다. 이미 있는 모델 오류는 따로 고쳐야 하며, 관심 종목 저장이 성공했다고 모델 설정이 올바르다는 뜻은 아닙니다.

### Q: GitHub Actions가 실행되지 않아요
A: Actions를 켰는지, cron 식이 맞는지 확인하세요(UTC 시간 기준이라는 점에 주의).

---

더 궁금한 점은 [Issue를 제출](https://github.com/ZhuLinsen/daily_stock_analysis/issues)해 주세요.

## Agent 도구 데이터 캐시와 저장

- `get_daily_history`는 먼저 로컬 `stock_daily` 일봉 캐시를 재사용해 봅니다. 캐시가 최신이고 홈 화면 기본값인 30건 이상을 다루면 외부 데이터 소스에 다시 요청하지 않습니다.
- Agent가 요청한 일수가 로컬 캐시 기록 수보다 많으면, 도구는 실제로 쓸 수 있는 기록을 돌려주고 `partial_cache=true`, `requested_days`, `actual_records`로 일부만 캐시에서 찾았다는 것을 알립니다.
- 캐시가 없거나 만료되었으면 도구는 원래 로직대로 데이터 소스에서 일봉 데이터를 가져오며, 성공하면 best-effort로 `stock_daily`에 다시 씁니다. 저장에 실패해도 Agent 답변은 막지 않습니다.
- `search_stock_news`와 `search_comprehensive_intel`은 성공적으로 돌아오면 best-effort로 `news_intel`에 쓰며, 기존 URL / fallback key 중복 제거 로직을 재사용합니다.
- `get_realtime_quote`는 `stock_daily`를 실시간 시세 캐시로 쓰지 않으며, 장중 실시간 시세를 일봉 테이블에 쓰지도 않습니다. 실시간 시세 캐시가 필요하다면 실시간 시세 저장소를 따로 설계해야 합니다.

## Agent 이벤트 경고 모니터링

`AGENT_EVENT_MONITOR_ENABLED=true`로 두면 schedule 모드는 `AGENT_EVENT_MONITOR_INTERVAL_MINUTES`마다 경고 worker를 실행합니다. worker는 매번 Alert API로 만들고 켜 둔 저장 규칙을 읽으며, `AGENT_EVENT_ALERT_RULES_JSON`의 legacy 규칙도 계속 호환합니다. 발동하면 여전히 기존 알림 채널로 보냅니다. Alert API / 웹 저장 규칙은 실시간 가격, 등락률, 거래량, 일봉 기술 지표, `watchlist`, `portfolio_holdings`, `portfolio_account`, 그리고 `market` 시장 신호등 대상을 지원합니다. legacy JSON은 여전히 기본 규칙 세 가지만 지원합니다.

> 호환과 마이그레이션 안내: 이 절은 현재 이벤트 경고 규칙(`price_change_percent` 포함)의 실행 동작을 기록하며, 모델 이름, provider, Base URL, LiteLLM, `OPENAI_*`, `DEEPSEEK_*`, `GEMINI_*` 같은 외부 모델/API 설정 의미는 바꾸지 않았습니다. legacy JSON은 자동으로 옮기거나 지우거나 고쳐 쓰지 않습니다. 되돌리려면 `AGENT_EVENT_MONITOR_ENABLED`를 지우거나 끄면 백그라운드 경고 worker가 멈춥니다.

| `alert_type` | 방향 필드 | 임곗값 필드 | 설명 |
| --- | --- | --- | --- |
| `price_cross` | `above` / `below` | `price` | 현재가가 지정 가격을 위로 또는 아래로 돌파 |
| `price_change_percent` | `up` / `down` | `change_pct` | 등락률이 지정 비율에 도달 |
| `volume_spike` | - | `multiplier` | 최신 거래량이 최근 20일 평균의 지정 배수를 넘음 |
| `ma_price_cross` | `above` / `below` | `window` | 일봉 close가 MA(window)를 위로 또는 아래로 교차(경계 발동) |
| `rsi_threshold` | `above` / `below` | `period`, `threshold` | RSI가 임곗값을 위로 또는 아래로 교차(경계 발동) |
| `macd_cross` | `bullish_cross` / `bearish_cross` | `fast_period`, `slow_period`, `signal_period` | DIF/DEA 골든크로스 또는 데드크로스(경계 발동) |
| `kdj_cross` | `bullish_cross` / `bearish_cross` | `period`, `k_period`, `d_period` | K/D 골든크로스 또는 데드크로스(경계 발동) |
| `cci_threshold` | `above` / `below` | `period`, `threshold` | CCI가 임곗값을 위로 또는 아래로 교차(경계 발동) |
| `portfolio_stop_loss` | `mode=near|breach` | - | 계좌 단위 손절에 가까워지거나 발동 |
| `portfolio_concentration` | - | - | 계좌 단위 symbol 집중도 |
| `portfolio_drawdown` | - | - | 계좌 단위 최대 낙폭 경고 |
| `portfolio_price_stale` | - | - | 보유 종목 가격이 stale이거나 missing |
| `market_light_status` | - | `statuses` | 현재 시장 신호등 상태가 `red/yellow` 목록과 일치 |
| `market_light_score_drop` | - | `min_drop` | 전 거래일 대비 Market Light score 하락 폭이 임곗값에 도달 |

예시:

```env
AGENT_EVENT_MONITOR_ENABLED=true
AGENT_EVENT_MONITOR_INTERVAL_MINUTES=5
AGENT_EVENT_ALERT_RULES_JSON=[{"stock_code":"600519","alert_type":"price_cross","direction":"above","price":1800},{"stock_code":"300750","alert_type":"price_change_percent","direction":"down","change_pct":3.0},{"stock_code":"000858","alert_type":"volume_spike","multiplier":2.5}]
```

worker는 `triggered`, `skipped`, `degraded`, `failed`를 평가 이력으로 `alert_triggers`에 기록하며, 정상적으로 발동하지 않은 경우는 기록하지 않습니다. DB 저장 규칙의 `triggered` 이력은 `rule_id + target + data_source + data_timestamp`로 같은 데이터 지점에 대해 best-effort 중복 제거를 하며, 중복 일치는 가장 먼저 생긴 발동 기록을 재사용합니다. `data_timestamp`가 없으면 중복 제거를 하지 않습니다. 실제로 발동하면 알림 채널마다의 attempt를 `alert_notifications`에 기록하고, Alert API로 만든 저장 규칙에는 `alert_cooldowns` 업무 쿨다운 상태를 씁니다. 저장된 쿨다운을 읽지 못하면 worker는 DB 이상 동안 중복 발송을 막기 위해 프로세스 내 fingerprint를 임시로 씁니다. legacy `AGENT_EVENT_ALERT_RULES_JSON` 규칙은 계속 프로세스 내 fingerprint로 억제하며 저장 쿨다운을 쓰지 않습니다. 알림 기반 시설의 `notification_noise.py` 소음 줄이기는 여전히 따로 동작합니다. 웹 규칙 목록은 백엔드가 돌려준 `cooldown_active`로 쿨다운 상태를 판단해, 브라우저 현지 시간대 해석이 표시에 영향을 주지 않게 합니다.

기술 지표 규칙은 일봉 close의 경계 발동만 쓰며, partial bar 처리는 서버 현지 시간대 + 16:00이라는 추정 기준이고, 시장 달력으로 정확히 판단하지 않습니다. `watchlist`는 매번 `STOCK_LIST`를 새로 읽은 뒤 펼치고, `portfolio_holdings`는 보유 종목 스냅샷에서 0이 아닌 보유 종목을 symbol로 중복 제거해 펼치며, `portfolio_account`는 보유 종목 위험 서비스를 재사용해 계좌 단위로 평가합니다. `market` 규칙의 target은 `cn|hk|us|jp|kr`만 지원하며, 구조화된 `MarketLightSnapshot`을 씁니다. `trade_date`는 이번 market overview에서 오고, `data_quality=unavailable`이면 발동을 건너뛰며, 비거래일은 거래일 관문에서 건너뜁니다. `market_light_score_drop`은 서로 다른 거래일의 score만 비교합니다. WebUI의 "告警"(경고) 페이지에서는 저장 규칙을 관리하고, 일회성 dry-run 테스트를 실행하며, 발동 이력, 알림 시도 결과, 읽기 전용 쿨다운 상태를 볼 수 있습니다. 일괄 규칙의 목록 쿨다운 상태는 부모 규칙의 요약이며, 하위 대상의 쿨다운은 발동 이력을 기준으로 합니다. 자세한 범위는 [실시간 경고 센터](alerts.md)를 보세요.

## 보유 종목 관리 안내

### `/portfolio` 페이지에서 할 수 있는 일

- 전체 보유 종목을 보거나 계좌 하나의 관점으로 바꿔 봅니다.
- `fifo` / `avg` 두 가지 원가 계산 방식을 바꿔 가며 스냅샷 KPI, 위험 요약, Top Positions 집중도 차트를 봅니다.
- 웹 페이지에서 바로 계좌를 추가하거나 잘못 만든 계좌를 지우고, 거래, 현금 내역, 기업 행위 같은 이벤트를 입력합니다.
- CSV로 보유 기록을 가져올 수 있으며, 먼저 `dry_run`으로 미리 본 뒤 실제로 쓸지 정합니다.
- 이벤트 목록에서 계좌, 날짜, 방향, 코드 등으로 거르고, 계좌 하나의 이벤트를 지워 바로잡을 수 있습니다.

### 관련 API

| API | 메서드 | 설명 |
|------|------|------|
| `/api/v1/portfolio/snapshot` | GET | 보유 종목 스냅샷 조회 |
| `/api/v1/portfolio/risk` | GET | 위험 요약 조회 |
| `/api/v1/portfolio/trades` | GET | 거래 기록 페이지 조회 |
| `/api/v1/portfolio/cash-ledger` | GET | 현금 내역 페이지 조회 |
| `/api/v1/portfolio/corporate-actions` | GET | 기업 행위 페이지 조회 |
| `/api/v1/portfolio/imports/csv/brokers` | GET | 내장 CSV 증권사 해석기 조회 |
| `/api/v1/portfolio/fx/refresh` | POST | 환율 캐시 직접 새로 고침 |
| `/api/v1/portfolio/accounts/{account_id}` | DELETE | 보유 계좌 삭제/보관 |
| `/api/v1/portfolio/trades/{trade_id}` | DELETE | 거래 기록 삭제 |
| `/api/v1/portfolio/cash-ledger/{entry_id}` | DELETE | 현금 내역 삭제 |
| `/api/v1/portfolio/corporate-actions/{action_id}` | DELETE | 기업 행위 삭제 |

> 조회 API는 모두 `account_id`, `date_from`, `date_to`, `page`, `page_size` 같은 공통 필터 매개변수를 지원하며, 이벤트 목록은 통일된 `items`, `total`, `page`, `page_size` 구조를 돌려줍니다.

### 사용 동작 안내

- CSV 가져오기에는 `huatai`, `citic`, `cmb` 해석기가 내장되어 있습니다(중국 증권사용). 증권사 목록 API가 실패하면 웹은 자동으로 이 내장 선택지로 돌아갑니다.
- 가져오기는 먼저 CSV를 표준화된 기록으로 해석한 뒤, 보유 장부에 한 건씩 제출합니다. 바쁜 행은 `failed_count`에 세며, 한 행의 충돌 때문에 전체 요청이 실패하지 않습니다.
- 계좌 삭제는 소프트 삭제입니다. 기본 계좌 목록, 스냅샷, 위험, 입력 진입점, 이벤트 목록에는 더 이상 그 계좌가 보이지 않지만, 거래, 현금 내역, 기업 행위는 실제로 지우지 않습니다. 내역 한 건을 바로잡으려면 계좌를 보관하기 전에 이벤트 목록의 삭제 수정 기능을 쓰세요.
- 거래 중복 제거는 계좌 안에서 고유한 `trade_uid`를 우선 쓰며, 없으면 날짜, 코드, 방향, 수량, 가격, 수수료, 세금, 통화로 만든 결정적 해시로 대신합니다.
- 매도는 먼저 가능한 수량을 확인하며, 초과 매도이면 `409 portfolio_oversell`을 돌려줍니다. 동시 쓰기 충돌이 나면 `409 portfolio_busy`를 돌려줄 수 있습니다.
- 보유 종목 스냅샷의 `positions[]`는 `price_source`, `price_date`, `price_stale`, `price_available` 같은 가격 메타 정보를 돌려줍니다. 당일 스냅샷은 기본으로 실시간 시세를 먼저 시도하고, 실시간 가격을 쓸 수 없거나 양수가 아니면 `as_of` 당일이나 그 이전의 가장 가까운 과거 종가로 돌아갑니다. `include_realtime=false`를 넘기면 실시간 시세를 건너뛰고 바로 로컬 과거 종가 대체 경로를 씁니다. 웹 보유 종목 페이지는 이 모드로 보유 목록을 먼저 그려, 외부 실시간 시세 소스가 느려져도 첫 화면이 막히지 않게 합니다. 과거 `as_of` 스냅샷은 실시간 가격을 가져오지 않으며, 원가를 현재가처럼 조용히 쓰지도 않습니다. 가격이 없는 보유 종목은 `price_available=false`로 표시하고 시가총액과 미실현 손익 합계에서 뺍니다.
- 환율 새로 고침은 먼저 온라인 소스를 시도합니다. 온라인에서 가져오지 못하면 가장 최근 캐시로 돌아가고 `is_stale=true`로 표시해, 스냅샷과 위험 페이지 전체를 못 쓰게 되는 일을 막습니다.
- `PORTFOLIO_FX_UPDATE_ENABLED=false`이면 직접 새로 고침 API가 "온라인 새로 고침이 꺼져 있음"을 분명히 돌려주며, 페이지가 "지금 새로 고칠 환율 쌍이 없음"으로 잘못 안내하지 않습니다.
- 위험 요약에는 집중도, 낙폭, 손절 근접도 같은 정보가 있습니다. `sector_concentration`은 먼저 섹터별로 분류해 보고, 실패하면 `UNCLASSIFIED`로 낮추며, 위험 결과 반환은 막지 않습니다.

### Agent가 보유 종목 읽기

- Agent는 `get_portfolio_snapshot`으로 계좌 기준의 간결한 보유 종목 요약을 받을 수 있으며, 기본으로 간단한 위험 블록이 들어 있어 Token 사용량을 줄이기에 좋습니다.
- 선택 매개변수로 `account_id`, `cost_method`, `as_of`, `include_positions`, `include_risk`가 있습니다.
- 위험 블록 생성이 실패해도 스냅샷은 그대로 돌려줍니다. 현재 환경에서 보유 종목 모듈을 켜지 않았다면 도구는 구조화된 `not_supported`를 돌려줍니다.
