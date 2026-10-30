# Zeabur 배포 가이드

이 가이드는 A주(중국 본토 증시 상장 주식) 관심 종목 AI 분석 시스템을 Zeabur에 배포하는 방법을 WebUI와 Discord 봇 기능까지 포함해 자세히 설명합니다.

## 목차

- [1. 배포 준비](#1-배포-준비)
- [2. Zeabur에 배포하기](#2-zeabur에-배포하기)
- [3. 시작 명령 설정](#3-시작-명령-설정)
- [4. Discord 봇 배포](#4-discord-봇-배포)
- [5. 환경 변수 설정](#5-환경-변수-설정)
- [6. 스토리지 마운트 설정](#6-스토리지-마운트-설정)
- [7. 헬스 체크](#7-헬스-체크)
- [8. 자주 묻는 질문](#8-자주-묻는-질문)

## 1. 배포 준비

### 1.1 필요한 것

- Zeabur 계정
- GitHub 계정(저장소 연결용)
- Discord 개발자 계정(봇을 배포하는 경우)
- 관련 API 키(예: Gemini API Key, 검색 서비스 API Key 등)

### 1.2 저장소 준비

저장소에 다음 파일이 들어 있는지 확인합니다.

- `.github/workflows/docker-publish.yml`(자동으로 생성되어 있음)
- `docker/Dockerfile`(이미 존재함)
- 프로젝트 전체 코드

## 2. Zeabur에 배포하기

### 2.1 GitHub 저장소 연결

1. Zeabur 콘솔에 로그인합니다.
2. 「새 프로젝트」를 클릭합니다.
3. 「GitHub에서 가져오기」를 선택합니다.
4. 저장소와 브랜치를 선택합니다(`main` 권장).
5. 「가져오기」를 클릭합니다.

### 2.2 빌드 규칙 설정

Zeabur는 `.github/workflows/docker-publish.yml` 파일을 자동으로 감지하고 GitHub Actions로 이미지를 빌드합니다.

자동으로 감지되지 않으면 직접 설정할 수 있습니다.

1. 프로젝트 페이지에서 「빌드 규칙」을 클릭합니다.
2. 「Dockerfile」을 선택합니다.
3. Dockerfile 경로에 `docker/Dockerfile`을 입력합니다.
4. 「저장」을 클릭합니다.

### 2.3 서비스 시작

1. 이미지 빌드가 끝날 때까지 기다립니다.
2. 「서비스 시작」을 클릭합니다.
3. 서비스가 시작되면 「접속(Networking)」 탭에서 접속 주소를 확인할 수 있습니다.

### 2.4 프런트엔드 빌드와 정적 리소스

FastAPI는 `static/` 디렉터리에 있는 프런트엔드 리소스를 자동으로 서비스합니다. 프런트엔드 빌드 결과물 위치는
`apps/dsa-web/vite.config.ts`에서 정하며, 기본값은 프로젝트 루트의 `static/`입니다.

Dockerfile은 멀티 스테이지 빌드를 사용하므로 이미지를 빌드할 때 프런트엔드도 자동으로 함께 빌드됩니다.
기본 정적 리소스를 바꾸고 싶다면 호스트에서 직접 빌드한 뒤 컨테이너 안의 `/app/static`에 마운트하면 됩니다.

### 2.5 리소스 설정 권장값

Zeabur 서비스는 메모리 `1G`부터 시작하는 것을 권장합니다. `512M`은 가벼운 Web/API, 단일 종목, 낮은 동시 실행 환경에만 적합하며, 이때는 `MAX_WORKERS=1`로 설정하는 것을 권장합니다.

- 최소 시도 가능: `512M`. 무거운 작업을 여러 개 동시에 실행하지 마십시오.
- 권장: `1G`. 단일 서비스로 일반적인 분석을 돌리기에 적합합니다.
- 고부하: `2G+`. Web/API와 예약 분석을 함께 실행하거나, 여러 종목, 시장 리뷰, 뉴스 확장, 이미지 리포트, 종목 선별을 함께 쓰는 경우에 적합합니다.

`512M`만 쓸 수 있다면 `server + analyzer`에 해당하는 다중 서비스 조합을 동시에 배포하지 말고, 꼭 필요하지 않은 시장 리뷰, 뉴스 확장, 이미지 리포트 기능은 꺼 두십시오.

## 3. 시작 명령 설정

### 3.1 지원하는 시작 모드

시스템은 여러 시작 모드를 지원하며, 필요에 따라 다른 시작 명령을 설정할 수 있습니다.

| 모드 | 시작 명령 | 설명 |
|------|----------|------|
| 예약 실행 모드(기본) | `python main.py --schedule` | 정해진 일정에 따라 주식 분석을 실행합니다 |
| FastAPI 모드 | `python main.py --serve` | FastAPI를 시작하고 분석도 실행합니다 |
| FastAPI 전용 모드 | `python main.py --serve-only` | FastAPI만 시작하고 분석은 실행하지 않습니다 |
| 시장 리뷰 전용 | `python main.py --market-review` | 시장 리뷰 분석만 실행합니다 |

### 3.2 시작 명령 설정 방법

1. Zeabur 콘솔에서 서비스 페이지로 들어갑니다.
2. 「설정」을 클릭합니다.
3. 「시작 명령」 항목을 찾습니다.
4. 필요한 시작 명령을 입력합니다. 예:
    - FastAPI 시작: `python main.py --serve`
    - FastAPI만 시작: `python main.py --serve-only --host 0.0.0.0 --port 8000`
    - 예약 실행 시작: `python main.py --schedule`
5. 「저장」을 클릭합니다.
6. 서비스를 재시작합니다.

## 4. Discord 봇 배포

### 4.1 준비 작업

1. Discord 애플리케이션과 봇 만들기
   - [Discord 개발자 포털](https://discord.com/developers/applications)에 접속합니다.
   - 「New Application」을 클릭해 새 애플리케이션을 만듭니다.
   - 「Bot」 탭에서 「Add Bot」을 클릭해 봇을 만듭니다.
   - 봇 Token을 복사합니다.

2. 봇 권한 설정
   - 「Bot」 탭에서 아래로 스크롤해 「Privileged Gateway Intents」로 이동합니다.
   - 「Server Members Intent」와 「Message Content Intent」를 켭니다.
   - 「OAuth2」→「URL Generator」에서 「bot」 범위를 선택합니다.
   - 필요한 권한을 선택합니다(예: 「Send Messages」, 「Read Messages/View Channels」 등).
   - 생성된 초대 링크를 복사해 봇을 내 서버에 추가합니다.

### 4.2 환경 변수 설정

Zeabur 콘솔의 「환경 변수」 설정에서 다음 변수를 추가합니다.

| 변수 이름 | 설명 | 예시 값 |
|--------|------|--------|
| `DISCORD_BOT_TOKEN` | Discord 봇 Token | `MTAxMjM0NTY3ODkwMTEyMzQ1Ng.GhIjKl.MnOpQrStUvWxYz1234567890` |
| `DISCORD_MAIN_CHANNEL_ID` | 메인 채널 ID | `123456789012345678` |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL(선택) | `https://discord.com/api/webhooks/...` |

### 4.3 봇 시작

봇 기능은 설정으로 켜지며, 별도의 시작 명령은 필요하지 않습니다. 설정 파일에 봇 관련 설정이 들어 있거나 환경 변수로 설정되어 있는지 확인하십시오.

## 5. 환경 변수 설정

### 5.1 기본 환경 변수

| 변수 이름 | 설명 | 기본값 |
|--------|------|--------|
| `PYTHONUNBUFFERED` | Python 출력 버퍼링 끄기 | `1` |
| `LOG_DIR` | 로그 디렉터리 | `/app/logs` |
| `DATABASE_PATH` | 데이터베이스 경로 | `/app/data/stock_analysis.db` |

### 5.2 API 서비스 설정

| 변수 이름 | 설명 | 기본값 |
|--------|------|--------|
| `API_HOST` | API 서비스 수신 주소 | `0.0.0.0` |
| `API_PORT` | API 서비스 포트 | `8000` |

> 예전 `WEBUI_HOST`/`WEBUI_PORT`/`WEBUI_ENABLED` 환경 변수도 계속 쓸 수 있으며, API 서비스 설정으로 자동 전달됩니다.

### 5.3 분석 관련 설정

| 변수 이름 | 설명 |
|--------|------|
| `ANSPIRE_API_KEYS` | Anspire Open API 키(LLM과 검색에 함께 사용, 권장) |
| `AIHUBMIX_KEY` | AIHubMix API 키(키 하나로 여러 모델 사용, 권장) |
| `GEMINI_API_KEY` | Gemini API 키 |
| `OPENAI_API_KEY` | OpenAI 호환 API 키 |
| `SERPAPI_API_KEYS` | SerpAPI 키(권장) |
| `TAVILY_API_KEYS` | Tavily API 키(쉼표로 구분) |
| `BOCHA_API_KEYS` | Bocha API 키(쉼표로 구분) |
| `BRAVE_API_KEYS` | Brave Search API 키(쉼표로 구분) |
| `MINIMAX_API_KEYS` | MiniMax API 키(쉼표로 구분) |
| `SEARXNG_BASE_URLS` | SearXNG 인스턴스 주소(쉼표로 구분, 할당량 제한 없는 예비 검색 수단이며 settings.yml에서 `format: json`을 켜야 함). 비워 두면 공개 인스턴스 탐색을 명시적으로 켠 경우에만 `searx.space`를 사용합니다 |
| `SEARXNG_PUBLIC_INSTANCES_ENABLED` | `SEARXNG_BASE_URLS`가 비어 있을 때 `searx.space`에서 공개 인스턴스를 자동으로 가져올지 여부(기본값 `false`) <!-- 계약 키(tests): 默认 `false` --> |

### 5.4 설정 방법

Zeabur 콘솔에서:

1. 서비스 페이지로 들어갑니다.
2. 「환경 변수」를 클릭합니다.
3. 「환경 변수 추가」를 클릭합니다.
4. 변수 이름과 값을 입력합니다.
5. 「저장」을 클릭합니다.
6. 서비스를 재시작합니다.

## 6. 스토리지 마운트 설정

### 6.1 마운트할 수 있는 디렉터리

| 디렉터리 | 설명 |
|------|------|
| `/app/data` | 데이터베이스와 데이터 파일 |
| `/app/logs` | 로그 파일 |
| `/app/reports` | 분석 리포트 |

### 6.2 마운트 설정 방법

1. Zeabur 콘솔에서 서비스 페이지로 들어갑니다.
2. 「스토리지」를 클릭합니다.
3. 「볼륨 추가」를 클릭합니다.
4. 「영구 스토리지」를 선택합니다.
5. 마운트 경로를 설정합니다.
   - 볼륨 경로: `/app/data`
   - 컨테이너 내부 경로: `/app/data`
6. 「저장」을 클릭합니다.
7. 마운트가 필요한 다른 디렉터리도 같은 방법으로 반복합니다.

### 6.3 주의 사항

- 마운트하면 데이터가 영구 저장되어 컨테이너를 재시작해도 사라지지 않습니다.
- 데이터베이스를 보존하려면 최소한 `/app/data` 디렉터리는 마운트하는 것을 권장합니다.

## 7. 헬스 체크

시스템에는 헬스 체크 기능이 내장되어 있으며, 기본적으로 다음을 확인합니다.

- WebUI 모드: `http://localhost:8000/health` 엔드포인트 확인
- FastAPI 모드: `http://localhost:8000/api/health` 엔드포인트 확인
- 서비스가 아닌 모드: 항상 정상 상태 반환

헬스 체크 설정은 다음과 같습니다.

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || curl -f http://localhost:8000/health \
    || python -c "import sys; sys.exit(0)"
```

## 8. 자주 묻는 질문

### 8.1 API 서비스에 접속할 수 없음

- 시작 명령에 `--serve` 또는 `--serve-only` 인자가 들어 있는지 확인합니다.
- 「접속(Networking)」 탭에 도메인이 설정되어 있는지 확인합니다.
- 방화벽 설정을 확인합니다.

### 8.2 봇이 응답하지 않음

- Discord 봇 Token이 올바른지 확인합니다.
- 봇이 서버에 추가되어 있는지 확인합니다.
- 봇 권한이 충분한지 확인합니다.
- 로그 파일에 오류 메시지가 있는지 확인합니다.

### 8.3 분석 작업이 실행되지 않음

- 예약 실행 설정이 올바른지 확인합니다.
- API 키가 유효한지 확인합니다.
- 로그 파일에 오류 메시지가 있는지 확인합니다.

### 8.4 데이터가 사라짐

- `/app/data` 디렉터리를 마운트했는지 확인합니다.
- 볼륨 설정이 올바른지 확인합니다.

## 9. 고급 설정

### 9.1 여러 인스턴스 배포

Zeabur에 인스턴스를 여러 개 배포해 기능별로 나눌 수 있습니다.

1. API 서비스용 인스턴스 1개(`python main.py --serve-only`)
2. 예약 실행용 인스턴스 1개(`python main.py --schedule`)
3. 봇용 인스턴스 1개(`python main.py --discord-bot`)

데이터베이스를 함께 쓰도록 모든 인스턴스가 같은 `/app/data` 볼륨을 공유하게 하십시오.

### 9.2 사용자 지정 도메인

Zeabur 콘솔의 「접속(Networking)」 탭에서 다음을 할 수 있습니다.

1. 자동으로 생성된 도메인 사용
2. 사용자 지정 도메인 연결
3. HTTPS 설정

## 10. 배포 업데이트

### 10.1 자동 업데이트

저장소에 새 코드를 푸시하면:

1. GitHub Actions가 새 이미지를 자동으로 빌드합니다.
2. Zeabur가 새 이미지를 감지합니다.
3. 「자동 배포」를 선택하거나 직접 배포를 실행할 수 있습니다.

### 10.2 수동 업데이트

1. Zeabur 콘솔에서 서비스 페이지로 들어갑니다.
2. 「배포 기록」을 클릭합니다.
3. 「재배포」를 선택합니다.
4. 또는 「이미지 업데이트」를 클릭합니다.

## 11. 모니터링과 로그

### 11.1 로그 보기

Zeabur 콘솔에서 서비스 페이지로 들어가 「로그」 탭을 클릭하면 실시간 로그와 이전 로그를 볼 수 있습니다.

### 11.2 모니터링 지표

Zeabur는 다음과 같은 기본 모니터링 지표를 제공합니다.

- CPU 사용률
- 메모리 사용률
- 네트워크 트래픽
- 디스크 사용률

자세한 지표는 「모니터링」 탭에서 확인할 수 있습니다.

## 12. 문제 해결

> 아래 명령 중 `printenv | grep`, `cat` 등은 컨테이너(Linux) 안에서 실행되므로 Windows에서도 그대로 쓸 수 있습니다.

### 12.1 자세한 로그 보기

```bash
# 컨테이너 접속
zeabur exec <서비스 이름> bash

# 로그 파일 보기
cat /app/logs/stock_analysis_20260125.log
```

### 12.2 설정 확인

```bash
# 컨테이너 접속
zeabur exec <서비스 이름> bash

# 환경 변수 확인
printenv | grep -i discord
printenv | grep -i webui
```

### 12.3 연결 테스트

```bash
# 네트워크 연결 테스트
zeabur exec <서비스 이름> curl -I https://api.discord.com

# API 연결 테스트
zeabur exec <서비스 이름> python -c "import requests; print(requests.get('https://api.discord.com').status_code)"
```

## 13. 권장 운영 방법

1. **영구 스토리지 사용**: 데이터베이스를 보존하려면 `/app/data` 디렉터리를 항상 마운트합니다.
2. **적절한 헬스 체크 설정**: 실제 상황에 맞게 헬스 체크 인자를 조정합니다.
3. **민감 정보는 환경 변수로 관리**: API 키를 코드에 직접 적어 넣지 마십시오.
4. **정기 데이터 백업**: `/app/data` 디렉터리 내용을 주기적으로 내려받아 백업합니다.
5. **알맞은 시작 모드 사용**: 필요에 맞는 시작 명령을 고릅니다.
6. **서비스 상태 모니터링**: 서비스 상태와 로그를 정기적으로 확인합니다.
7. **부하에 맞춘 메모리 설정**: 전체 분석은 `1G`부터 시작하는 것을 권장합니다. `512M` 저사양 환경에서는 `MAX_WORKERS=1`로 설정하고, 고부하 환경에서는 `2G+`를 사용합니다.

## 14. 문의

문제가 있으면 프로젝트 관리자에게 연락하거나 GitHub Issues에 질문을 남겨 주십시오.
