# 문서 센터

이 프로젝트 문서의 입구입니다. README는 프로젝트 개요와 빠른 시작을 다루고, 더 자세한 설정, 배포, 기능 설명, 문제 해결은 여기서 찾아가면 됩니다.

## 상황별로 고르기

| 하고 싶은 일 | 먼저 볼 문서 | 이어서 볼 문서 |
| --- | --- | --- |
| 이 프로젝트로 무엇을 할 수 있는지 빠르게 알아보기 | [README](../README.md) | [전체 설정 및 배포 가이드](full-guide.md) |
| 처음으로 프로젝트 실행해 보기 | [초보자용 클라이언트 설치와 설정](beginner-client-setup.md) | [전체 설정 및 배포 가이드](full-guide.md) |
| LLM 채널 설정하기 | [LLM 설정 가이드](LLM_CONFIG_GUIDE.md) | [LLM 서비스 제공자 설정 가이드](llm-providers.md)(xAI Grok 직접 연결 포함) |
| 알림 발송 설정하기 | [알림 기능 기준 문서](notifications.md) | [전체 설정 및 배포 가이드](full-guide.md) |
| 서버나 클라우드 플랫폼에 배포하기 | [배포 가이드](DEPLOY.md) | [클라우드 WebUI 배포](deploy-webui-cloud.md), [Zeabur 배포](docker/zeabur-deployment.md) |
| Bot / 메신저 연동하기 | [Bot 명령과 연동](bot-command.md) | [Bot 플랫폼 설정](bot/), [Grok Bot 연동](grok-bot-integration.md) |
| 실행 문제 해결하기 | [FAQ](FAQ.md) | [변경 이력](CHANGELOG.md) |
| 데이터 소스 실패나 기능 저하 대응하기 | [데이터 소스 안정성과 장애 대응 도해](data-source-stability.md) | [FAQ](FAQ.md) |
| 개발에 참여하거나 PR 보내기 | [기여 가이드](CONTRIBUTING.md) | [API 명세](architecture/api_spec.json) |

## 빠른 시작

| 문서 | 내용 |
| --- | --- |
| [README](../README.md) | 프로젝트 소개, 핵심 기능, 빠른 시작, 알림 예시 |
| [초보자용 클라이언트 설치와 설정](beginner-client-setup.md) | 코드를 모르는 사용자를 위한 클라이언트 다운로드, Anspire Open / AIHubMix 모델 설정, 뉴스 소스 설정, 자주 묻는 질문 |
| [전체 설정 및 배포 가이드](full-guide.md) | 환경 준비, 실행 방법, 설정 설명, 배포 경로, 자주 묻는 질문 |
| [FAQ](FAQ.md) | 설정, 모델, 알림, 배포, 실행에 관한 자주 묻는 질문 |
| [데이터 소스 안정성과 장애 대응 도해](data-source-stability.md) | Tushare, TickFlow, AkShare, Efinance, YFinance, Longbridge 등 연결된 소스의 쓰임새, fallback 경로, 권장 설정 |
| [데이터 센터](data-center-diagnostics.md) | 읽기 전용 Provider 기능, 데이터셋 품질, 정확한 시장 지원, 실행 시점 우선순위 |
| [변경 이력](CHANGELOG.md) | 버전 변화, 기능 조정, 마이그레이션 안내 |

## 설정

| 문서 | 내용 |
| --- | --- |
| [LLM 설정 가이드](LLM_CONFIG_GUIDE.md) | LLM 채널, 3단계 설정, 웹 설정 페이지, 자주 쓰는 모델 설정 |
| [LLM 서비스 제공자 설정 가이드](llm-providers.md) | Provider 프리셋, Actions 매핑, 오류 분류, 진단 방법 |
| [LiteLLM YAML 예시](examples/litellm_config.example.yaml) | LiteLLM 다중 채널 설정 예시 |
| [Grok Bot Skill 예시](examples/grok_bot/README.md) | Grok Bot에 붙여 넣는 최소 Skill. 기존 REST를 호출합니다 |
| [알림 기능 기준 문서](notifications.md) | WeCom(기업용 위챗), Feishu(페이슈), Telegram, Discord, Slack, 메일 등 알림 채널 설정 |
| [Tushare 종목 목록 가이드](TUSHARE_STOCK_LIST_GUIDE.md) | Tushare 종목 목록 관련 설정과 사용법 |

## 기능별 안내

| 문서 | 내용 |
| --- | --- |
| [관심 종목 변화 상태와 다음 할 일](watchlist-next-action.md) | 홈 화면 관심 종목 목록의 변화·상태·다음 할 일 세 가지 신호, 대응 규칙, 이후 확장 범위 |
| [Bot 명령과 연동](bot-command.md) | Bot 명령, Webhook, 플랫폼 연동, 콜백 설명 |
| [Bot 플랫폼 설정](bot/) | Feishu, DingTalk(딩톡), Discord 등 Bot 설정 스크린샷과 보충 설명 |
| [실시간 경고 센터](alerts.md) | EventMonitor 기준, 웹 규칙 관리, 알림 결과, 쿨다운 상태, Phase 범위 |
| [개별 종목 리서치 통합 API](stock-profile-api.md) | 단일 stock-profile 계약, 블록별 품질 상태, 코드 정규화, 이후 웹 범위 |
| [DecisionSignal 의사결정 신호](decision-signals.md) | AI 의견 풀의 필드 의미, API, 웹 표시, 경고/알림/포트폴리오 위험 연동, 사후 평가, 민감 정보 가림, 마이그레이션과 롤백 |
| [ETF 로테이션](etf-rotation.md) | `--etf-rotation` 규칙 기반 듀얼 모멘텀 로테이션: 규칙, 설정, 리포트 구성, 매개변수 안정성 해석, 데이터 경고 범위 |
| [ResearchArtifact 구조화 리서치 결과물](research-artifact.md) | structured_report 필드, Thesis / Evidence / Invalidation / Next Action / Data Quality 계약, 예전 리포트 호환 범위 |
| [포트폴리오 위험과 노출 대시보드](portfolio-risk-exposure-dashboard.md) | 보유 종목 페이지의 위험 표시, 시장 노출, 통화 노출, 가격 품질 통합 표시 |
| [종목 선별 설명 계약](screening-explanations.md) | Why Selected / Why Now에 대한 백엔드의 결정적 설명, 출처, 품질 상태, 결측값 범위 |
| [뉴스 / 정보 소스](intelligence-sources.md) | RSS/Atom 정식 뉴스 소스 설정, 테스트, 수집, 중복 제거, 저장, 조회, 보안 범위 |
| [분석 컨텍스트 패키지 계약, 실행 시 사용과 표시 범위](analysis-context-pack.md) | AnalysisContextPack 첫 버전 범위, 필드 품질 상태, P1/P2 내부 계약, P3 Prompt 요약 사용, P4 이력/API/웹의 저민감 정보 표시, P5 데이터 품질 점수, P6 마이그레이션·롤백과 소스 코드 기준점. 전체 가이드에서 #1386 단계 인식 분석, 마이그레이션, 롤백 안내를 보충합니다 |
| [이미지 인식 Prompt](image-extract-prompt.md) | 이미지에서 종목 정보를 인식하는 Prompt와 사용 범위 |
| [OpenClaw Skill 연동](openclaw-skill-integration.md) | OpenClaw / Skill 외부 연동 설명 |
| [Grok Bot 연동](grok-bot-integration.md) | 2026-08-11 Grok Bot(AI teammate)과 DSA REST / DecisionSignal / Skill의 연동 범위 |

## 배포와 패키징

| 문서 | 내용 |
| --- | --- |
| [배포 가이드](DEPLOY.md) | 서버 배포, Docker, systemd, Supervisor 등 배포 방법 |
| [클라우드 WebUI 배포](deploy-webui-cloud.md) | 클라우드 서버에서 WebUI에 접속하기 위한 배포 설명 |
| [Zeabur 배포](docker/zeabur-deployment.md) | Zeabur 플랫폼 배포 설명 |
| [데스크톱 앱 패키징 안내](desktop-package.md) | Electron 데스크톱 앱과 웹 빌드 결과물 패키징 설명 |

## 참고와 개발

| 문서 | 내용 |
| --- | --- |
| [API 명세](architecture/api_spec.json) | FastAPI OpenAPI 명세 결과물 |
| [기여 가이드](CONTRIBUTING.md) | Issue, PR, 테스트, 문서 동기화, 협업 규칙 |

## 다른 언어

| 문서 | 내용 |
| --- | --- |
| [영어 문서 색인](INDEX_EN.md) | English documentation index |
| [영어 README](README_EN.md) | English project overview and quick start |
| [번체 중국어 README](README_CHT.md) | 繁體中文項目概覽與快速開始 |
