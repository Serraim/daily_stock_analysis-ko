# 🚀 배포 가이드

이 문서는 A주(중국 본토 증시 상장 주식) 관심 종목 AI 분석 시스템을 서버에 배포하는 방법을 설명합니다.

## 📋 배포 방식 비교

| 방식 | 장점 | 단점 | 추천 상황 |
|------|------|------|----------|
| **Docker Compose** ⭐ | 한 번에 배포, 환경 격리, 이전과 업그레이드가 쉬움 | Docker 설치 필요 | **추천**: 대부분의 경우 |
| **직접 배포** | 단순하고 추가 의존성 없음 | 환경 의존성이 있고 이전이 번거로움 | 임시 테스트 |
| **Systemd 서비스** | 시스템 수준 관리, 부팅 시 자동 시작 | 설정이 번거로움 | 장기간 안정적으로 운영 |
| **Supervisor** | 프로세스 관리, 자동 재시작 | 별도 설치 필요 | 여러 프로세스 관리 |

**결론: Docker Compose를 권장합니다. 다른 서버로 옮기기도 가장 빠르고 편합니다!**

---

## 🐳 방식 1: Docker Compose 배포(권장)

> 아래 설치 명령은 Linux 서버 기준입니다. Windows PC에서는 Docker Desktop을 설치해 Docker를 사용할 수 있습니다.

### 1. Docker 설치

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# CentOS
sudo yum install -y docker docker-compose
sudo systemctl start docker
sudo systemctl enable docker
```

### 2. 설정 파일 준비

```bash
# 코드 클론(또는 코드를 서버에 업로드)
git clone <your-repo-url> /opt/stock-analyzer
cd /opt/stock-analyzer

# 설정 파일을 복사한 뒤 편집
cp .env.example .env
vim .env  # 실제 API Key 등 설정값 입력
```

### 3. 한 번에 시작

```bash
# 빌드 후 시작(예약 분석과 Web 화면 서비스를 함께 실행)
docker-compose -f ./docker/docker-compose.yml up -d

# 로그 보기
docker-compose -f ./docker/docker-compose.yml logs -f

# 실행 상태 보기
docker-compose -f ./docker/docker-compose.yml ps
```

시작에 성공하면 브라우저에 `http://서버공인IP:8000`을 입력해 Web 관리 화면을 열 수 있습니다. 열리지 않으면 먼저 클라우드 서버 콘솔의 「보안 그룹」에서 8000 포트를 허용했는지 확인하십시오.

> 접속 방법을 모르겠다면 → [클라우드 서버 Web 화면 접속 가이드](deploy-webui-cloud.md)

### 3.1 리소스 권장 사항

기본 `docker/docker-compose.yml`은 서비스마다 `limits.memory: 1G`, `reservations.memory: 512M`을 설정하며, 이것이 전체 분석에 권장하는 출발점입니다.

- 최소 시도 가능: `512M`. 가벼운 Web/API, 단일 종목, 낮은 동시 실행 환경에만 적합하며, `MAX_WORKERS=1`로 설정하는 것을 권장합니다.
- 권장: `1G`. `server` 또는 `analyzer` 하나만 실행하는 일반적인 분석에 적합합니다.
- 고부하: `2G+`. `server + analyzer`를 함께 시작하거나, 여러 종목, 기본값 `MAX_WORKERS=3`, 시장 리뷰, 뉴스 확장, 이미지 리포트, 종목 선별을 쓰는 경우에 적합합니다.

`512M`만 쓸 수 있다면 `server`와 `analyzer`를 동시에 시작하지 말고, 꼭 필요하지 않은 시장 리뷰, 뉴스 확장, 이미지 리포트 기능은 꺼 두십시오.

### 3.2 예약 알림 중복 방지

자동 예약 실행의 진입점은 하나만 두는 것을 권장합니다. 독립된 `analyzer`를 쓰거나, `SCHEDULE_ENABLED=true`를 켠 `server`를 쓰십시오. NAS에 남아 있는 `--schedule` 컨테이너나 중복 배포가 없는지 확인하십시오. 두 인스턴스가 서로 다른 데이터베이스를 쓰면 중복을 걸러낼 수 없습니다.

CLI와 Web/API의 일일 예약 실행은 `DATABASE_PATH`가 가리키는 같은 SQLite 파일 안에서 이번 예정 시각을 원자적으로 선점(claim)합니다. 예정 시각, 관심 종목/보유 종목 출처, 분석/알림 옵션, 리포트 기준이 모두 같으면 자동 실행은 한 번만 이뤄지며, 두 번째 프로세스가 첫 번째 프로세스가 끝난 뒤에 실행되더라도 마찬가지입니다. 예정 시각, 관심 종목, 분석/알림 옵션이 다르면 각각 따로 실행됩니다. 예정 시각은 스케줄러가 도는 프로세스의 시간대를 기준으로 UTC로 환산되므로, 한 배포 안에서는 `TZ`를 같게 유지하십시오. 공식 Compose의 두 서비스는 기본적으로 `data/`를 공유하므로 선점 기록도 함께 씁니다.

이 기능은 "자동 실행은 많아야 한 번"을 보장할 뿐, 실패 시 자동 재시도나 알림 전달을 보장하지는 않습니다. 선점한 뒤 프로세스가 종료되거나, 시간이 초과되거나, 분석이 실패하더라도(알림 일부가 이미 나갔을 수 있음) 다른 타이머가 전체 작업을 다시 실행하지 않습니다. 결과를 확인한 뒤 Web의 "지금 실행"으로 직접 다시 돌릴 수 있습니다. 선점은 실제 실행 시점에 이뤄지고 관심 종목 스냅샷을 고정하므로, 설정 저장과 비동기 시작 사이의 경쟁 상태를 막습니다. Web 작업이 다른 작업 때문에 시작되지 못했다면 선점하지 않습니다. 시작 시 즉시 실행, 수동 CLI/API 분석, "지금 실행"은 이 중복 방지 대상이 아니며 이 기능 때문에 막히지도 않습니다. 기록은 약 7일간 자동 보관됩니다. 데이터베이스에 쓸 수 없거나 잠금 대기 시간이 초과되면 오류를 기록하고 이번 회차를 건너뛰며, Web 예약 상태 화면에 선점 오류가 표시됩니다.

이 기능은 공유 SQLite 파일의 안정적인 파일 잠금에 의존하므로, 같은 호스트의 프로세스와 같은 로컬 bind mount를 쓰는 컨테이너에만 적용됩니다. 데이터베이스가 서로 다르거나 NFS 또는 여러 호스트에 걸친 배포에서의 분산 중복 방지는 보장하지 않습니다. 새로운 설정을 추가하거나 기존 분석 데이터를 수정할 필요는 없습니다.

### 4. 자주 쓰는 관리 명령

```bash
# 서비스 중지
docker-compose -f ./docker/docker-compose.yml down

# 서비스 재시작
docker-compose -f ./docker/docker-compose.yml restart

# 코드 업데이트 후 다시 배포
git pull
docker-compose -f ./docker/docker-compose.yml build --no-cache
docker-compose -f ./docker/docker-compose.yml up -d

# 컨테이너에 들어가 디버깅
docker-compose -f ./docker/docker-compose.yml exec -u dsa stock-analyzer bash

# 분석을 수동으로 한 번 실행
docker-compose -f ./docker/docker-compose.yml exec -u dsa stock-analyzer python main.py --no-notify
```

### 5. 데이터 영구 보관

데이터는 호스트 디렉터리에 자동으로 저장됩니다.
- `./data/` - 데이터베이스 파일
- `./logs/` - 로그 파일
- `./reports/` - 분석 리포트

### 6. 권한 안내

Docker 이미지의 시작 진입점은 `./data`, `./logs`, `./reports`에 해당하는 마운트 디렉터리를 자동으로 만들고 권한을 바로잡은 뒤, root가 아닌 사용자(`dsa`, UID 1000)로 권한을 낮춰 애플리케이션을 실행합니다. 일반적인 배포에서는 `chown` / `chmod`를 직접 실행할 필요가 없습니다.

`--user` / Compose `user:`를 직접 지정했거나, 읽기 전용 마운트, rootless Docker, NFS처럼 컨테이너가 소유자를 바꿀 수 없는 환경을 쓴다면, 실제 실행 사용자가 이 디렉터리들에 쓰기 권한을 갖고 있는지 확인하십시오.

---

## 🖥️ 방식 2: 직접 배포

> 아래 명령은 Linux(Ubuntu/Debian) 서버 기준입니다. Windows에서는 가상환경 활성화 등 일부 명령이 다릅니다.

### 1. Python 환경 설치

```bash
# Python 3.10+ 설치
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3-pip

# 가상환경 만들기
python3.10 -m venv /opt/stock-analyzer/venv
source /opt/stock-analyzer/venv/bin/activate
```

### 2. 의존성 설치

```bash
cd /opt/stock-analyzer
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

> `-i https://pypi.tuna.tsinghua.edu.cn/simple`은 중국 내 PyPI 미러 주소입니다. 중국 밖에서는 이 옵션을 빼고 `pip install -r requirements.txt`만 실행해도 됩니다.

### 3. 환경 변수 설정

```bash
cp .env.example .env
vim .env  # 설정값 입력
```

### 4. 실행

```bash
# 한 번만 실행
python main.py

# 예약 실행 모드(포그라운드 실행)
python main.py --schedule

# 백그라운드 실행(nohup 사용)
nohup python main.py --schedule > /dev/null 2>&1 &

# Web 관리 화면 시작(클라우드 서버라면 먼저 .env에서 WEBUI_HOST=0.0.0.0 설정)
python main.py --webui-only

# Web 화면 시작(시작할 때 분석을 한 번 실행합니다. 매일 예약 실행하려면 --schedule을 붙이거나 SCHEDULE_ENABLED=true로 설정)
python main.py --webui
```

> 접속 방법을 모르겠다면 → [클라우드 서버 Web 화면 접속 가이드](deploy-webui-cloud.md)

---

## 🔧 방식 3: Systemd 서비스

> Systemd는 Linux 전용입니다.

systemd 서비스 파일을 만들어 부팅 시 자동 시작과 자동 재시작을 설정합니다.

### 1. 서비스 파일 만들기

```bash
sudo vim /etc/systemd/system/stock-analyzer.service
```

내용:
```ini
[Unit]
Description=A주 관심 종목 AI 분석 시스템
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/stock-analyzer
Environment="PATH=/opt/stock-analyzer/venv/bin"
ExecStart=/opt/stock-analyzer/venv/bin/python main.py --schedule
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

### 2. 서비스 시작

```bash
# 설정 다시 불러오기
sudo systemctl daemon-reload

# 서비스 시작
sudo systemctl start stock-analyzer

# 부팅 시 자동 시작
sudo systemctl enable stock-analyzer

# 상태 보기
sudo systemctl status stock-analyzer

# 로그 보기
journalctl -u stock-analyzer -f
```

---

## ⚙️ 설정 안내

### 필수 설정 항목

| 설정 항목 | 설명 | 얻는 방법 |
|--------|------|----------|
| `ANSPIRE_API_KEYS` / `AIHUBMIX_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | AI 모델을 최소 하나는 설정해야 합니다. Anspire 또는 AIHubMix를 우선 권장합니다 | 각 서비스 제공자 콘솔 |
| `STOCK_LIST` | 관심 종목 목록 | 쉼표로 구분한 종목 코드입니다. 등록된 지수의 명시적 형식(예: `sh000016`, `930606.CSI`, `sz399365`)은 일회성 `--stocks` 실행이나 GitHub Actions 진입점에서 지원합니다(로컬 `.env`/Docker에서 인자 없이 기본 실행하면 주식으로 처리하므로, 지수는 `--stocks`로 지정해야 합니다). 규칙은 [지수 관심 종목 설정](full-guide.md#指数自选股配置)을 참고하십시오 |
| 알림 채널 | 최소 하나 설정합니다. 예: WeCom(위챗 워크), Feishu(페이슈), Telegram, 이메일 | 각 알림 플랫폼 |

### 선택 설정 항목

| 설정 항목 | 기본값 | 설명 |
|--------|--------|------|
| `SCHEDULE_ENABLED` | `false` | 예약 실행 사용 여부 |
| `SCHEDULE_TIME` | `18:00` | 매일 실행 시각 |
| `MARKET_REVIEW_ENABLED` | `true` | 시장 리뷰 사용 여부 |
| `ANSPIRE_API_KEYS` | - | Anspire LLM 및 뉴스 검색(권장) |
| `AIHUBMIX_KEY` | - | AIHubMix, 키 하나로 여러 모델 사용(권장) |
| `SERPAPI_API_KEYS` | - | SerpAPI 실시간 금융 뉴스 검색(권장) |
| `TAVILY_API_KEYS` | - | Tavily 뉴스 검색(선택) |
| `MINIMAX_API_KEYS` | - | MiniMax 검색(선택) |

---

## 🌐 프록시 설정

서버가 중국 본토에 있으면 Gemini API에 접속하려면 프록시가 필요합니다.

### Docker 방식

`docker-compose.yml`을 편집합니다.
```yaml
environment:
  - http_proxy=http://your-proxy:port
  - https_proxy=http://your-proxy:port
```

### 직접 배포 방식

`main.py` 맨 위를 편집합니다.
```python
os.environ["http_proxy"] = "http://your-proxy:port"
os.environ["https_proxy"] = "http://your-proxy:port"
```

---

## 📊 모니터링과 유지 관리

> 아래 `tail`, `ps`, `ls`, `find` 명령은 Linux/macOS용입니다.

### 로그 보기

```bash
# Docker 방식
docker-compose -f ./docker/docker-compose.yml logs -f --tail=100

# 직접 배포
tail -f /opt/stock-analyzer/logs/stock_analysis_*.log
```

### 상태 점검

```bash
# 프로세스 확인
ps aux | grep main.py

# 최근 리포트 확인
ls -la /opt/stock-analyzer/reports/
```

### 정기 유지 관리

```bash
# 오래된 로그 정리(7일 보관)
find /opt/stock-analyzer/logs -mtime +7 -delete

# 오래된 리포트 정리(30일 보관)
find /opt/stock-analyzer/reports -mtime +30 -delete
```

---

## ❓ 자주 묻는 질문

### 1. Docker 빌드 실패

```bash
# 캐시를 지우고 다시 빌드
docker-compose -f ./docker/docker-compose.yml build --no-cache
```

### 2. API 접속 시간 초과

프록시 설정을 확인하고, 서버에서 Gemini API에 접속할 수 있는지 확인하십시오.

### 3. 데이터베이스 잠김

```bash
# 서비스를 중지한 뒤 lock 파일 삭제
rm /opt/stock-analyzer/data/*.lock
```

### 4. 메모리 부족

기본 Compose는 이미 `1G`를 권장합니다. 그래도 OOM(메모리 부족)이 발생하거나 플랫폼이 컨테이너를 강제로 종료한다면 `docker-compose.yml`의 메모리 한도를 높이십시오. `server + analyzer`, 여러 종목, 시장 리뷰, 이미지 리포트, 종목 선별을 함께 돌린다면 `2G+`를 권장합니다.
```yaml
deploy:
  resources:
    limits:
      memory: 1G
    reservations:
      memory: 512M
```

저사양 환경에서 `512M`만 쓸 수 있다면 `MAX_WORKERS=1`로 설정하고, `server`와 `analyzer` 중 하나만 시작하며, 꼭 필요하지 않은 시장 리뷰, 뉴스 확장, 이미지 리포트 작업을 줄이는 것을 권장합니다.

### 5. WebUI를 열었더니 UI 요소가 비정상적으로 크게 보이거나 레이아웃이 깨짐

**증상**: 8000 포트에는 접속되지만 페이지의 글자, 버튼, 카드가 비정상적으로 크게 보이고 정상적인 레이아웃이 나오지 않습니다.

**원인**: `static/index.html`은 있지만 CSS/JS 리소스 파일이 없어서(`static/assets/`가 비어 있거나 없음) 브라우저가 스타일과 스크립트를 불러오지 못하고 HTML만 그대로 표시합니다.

**해결 방법**:

- **Docker 배포**: 다음 명령으로 이미지를 다시 빌드합니다(프런트엔드가 이미지에 제대로 포함되도록 함).
  ```bash
  docker-compose -f ./docker/docker-compose.yml down
  docker-compose -f ./docker/docker-compose.yml build --no-cache
  docker-compose -f ./docker/docker-compose.yml up -d
  ```
  빌드가 끝나면 브라우저 캐시를 새로 고친 뒤(`Ctrl+Shift+R`) 다시 접속합니다.

- **직접 배포(pip + python)**: 먼저 프런트엔드를 빌드한 다음 서비스를 시작합니다.
  ```bash
  # Node.js 18+ 설치(20+ 권장, 아직 설치하지 않았다면)
  # 프런트엔드 빌드
  cd apps/dsa-web
  npm ci
  npm run build
  cd ../..
  # 서비스 시작
  python main.py --webui-only
  ```

**확인**: 브라우저 개발자 도구(F12 → Network)에서 `/assets/index-*.js`와 `/assets/index-*.css`에 404 오류가 있는지 확인합니다. 있다면 리소스가 빠진 것이므로 위 단계대로 다시 빌드하면 됩니다.

---

## 🔄 빠른 서버 이전

서버 한 대에서 다른 서버로 옮기는 방법입니다.

```bash
# 기존 서버: 압축
cd /opt/stock-analyzer
tar -czvf stock-analyzer-backup.tar.gz .env data/ logs/ reports/

# 새 서버: 배포
mkdir -p /opt/stock-analyzer
cd /opt/stock-analyzer
git clone <your-repo-url> .
tar -xzvf stock-analyzer-backup.tar.gz
docker-compose -f ./docker/docker-compose.yml up -d
```

---

## ☁️ 방식 4: GitHub Actions 배포(서버 불필요)

**가장 간단한 방식입니다!** 서버 없이 GitHub의 무료 컴퓨팅 자원을 사용합니다.

### 장점
- ✅ **완전 무료**(매월 2000분)
- ✅ **서버 불필요**
- ✅ **자동 예약 실행**
- ✅ **유지 관리 비용 없음**

### 제한
- ⚠️ 상태가 남지 않음(실행할 때마다 새 환경)
- ⚠️ 예약 실행이 몇 분 늦어질 수 있음
- ⚠️ HTTP API를 제공할 수 없음

### 배포 단계

#### 1. GitHub 저장소 만들기

```bash
# git 초기화(아직 하지 않았다면)
cd /path/to/daily_stock_analysis
git init
git add .
git commit -m "Initial commit"

# GitHub 저장소를 만들고 푸시
# GitHub 웹페이지에서 새 저장소를 만든 뒤:
git remote add origin https://github.com/<내-사용자명>/daily_stock_analysis.git
git branch -M main
git push -u origin main
```

#### 2. Secrets 설정(중요!)

저장소 페이지 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

다음 Secrets를 추가합니다.

| Secret 이름 | 설명 | 필수 여부 |
|------------|------|------|
| `ANSPIRE_API_KEYS` | Anspire Open API Key(키 하나로 LLM과 검색 사용) | 권장 |
| `AIHUBMIX_KEY` | AIHubMix API Key(키 하나로 여러 모델 사용) | 권장 |
| `ANTHROPIC_API_KEY` | Anthropic API Key | 선택 |
| `GEMINI_API_KEY` | Gemini AI API Key | 선택 |
| `OPENAI_API_KEY` | OpenAI 호환 API Key | 선택 |
| `WECHAT_WEBHOOK_URL` | WeCom(위챗 워크) 봇 Webhook | 선택* |
| `FEISHU_WEBHOOK_URL` | Feishu(페이슈) 봇 Webhook | 선택* |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | 선택* |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 선택* |
| `TELEGRAM_MESSAGE_THREAD_ID` | Telegram Topic ID | 선택* |
| `EMAIL_SENDER` | 보내는 사람 이메일 | 선택* |
| `EMAIL_PASSWORD` | 이메일 인증 코드(앱 비밀번호) | 선택* |
| `SERVERCHAN3_SENDKEY` | Server酱³(ServerChan, 중국 알림 서비스) Sendkey | 선택* |
| `CUSTOM_WEBHOOK_URLS` | 사용자 지정 Webhook(여러 개는 쉼표로 구분) | 선택* |
| `STOCK_LIST` | 관심 종목 목록. 예: `600519,300750` | ✅ |
| `SERPAPI_API_KEYS` | SerpAPI Key | 권장 |
| `TAVILY_API_KEYS` | Tavily 검색 API Key | 선택 |
| `BOCHA_API_KEYS` | Bocha(博查) 검색 API Key | 선택 |
| `BRAVE_API_KEYS` | Brave Search API Key | 선택 |
| `MINIMAX_API_KEYS` | MiniMax Coding Plan Web Search | 선택 |
| `SEARXNG_BASE_URLS` | 직접 운영하는 SearXNG 인스턴스(할당량 제한 없는 예비 검색 수단이며 settings.yml에서 `format: json`을 켜야 함). 비워 두면 공개 인스턴스 탐색을 명시적으로 켠 경우에만 `searx.space`를 사용합니다 | 선택 |
| `SEARXNG_PUBLIC_INSTANCES_ENABLED` | `SEARXNG_BASE_URLS`가 비어 있을 때 `searx.space`에서 공개 인스턴스를 자동으로 가져올지 여부(기본값 `false`) <!-- 계약 키(tests): 默认 `false` --> | 선택 |
| `TUSHARE_TOKEN` | Tushare Token | 선택 |
| `GEMINI_MODEL` | 모델 이름(기본값 gemini-2.0-flash) | 선택 |

> *참고: 알림 채널은 최소 하나 설정해야 하며, 여러 채널로 동시에 알림을 보낼 수 있습니다.

#### 3. Workflow 파일 확인

`.github/workflows/00-daily-analysis.yml` 파일이 있고 커밋되어 있는지 확인합니다.

```bash
git add .github/workflows/00-daily-analysis.yml
git commit -m "Add GitHub Actions workflow"
git push
```

#### 4. 수동 테스트 실행

1. 저장소 페이지 → **Actions** 탭을 엽니다.
2. **"每日股票分析"** workflow를 선택합니다(화면에 중국어 이름 그대로 표시되며, "일일 주식 분석"이라는 뜻입니다).
3. **"Run workflow"** 버튼을 클릭합니다.
4. 실행 모드를 선택합니다.
   - `full` - 전체 분석(종목 + 시장)
   - `market-only` - 시장 리뷰만
   - `stocks-only` - 종목 분석만
5. 초록색 **"Run workflow"** 버튼을 클릭합니다.

#### 5. 실행 로그 보기

- Actions 페이지에서 실행 기록을 볼 수 있습니다.
- 개별 실행 기록을 클릭하면 자세한 로그를 볼 수 있습니다.
- 분석 리포트는 Artifact로 30일간 보관됩니다.

### 예약 실행 안내

기본 설정: **월요일부터 금요일까지, 베이징 시간 18:00**(한국 시간 19:00)에 자동 실행

시각 변경: `.github/workflows/00-daily-analysis.yml`의 cron 표현식을 편집합니다.

```yaml
schedule:
  - cron: '0 10 * * 1-5'  # UTC 시간, +8 = 베이징 시간
```

자주 쓰는 cron 예시:
| 표현식 | 설명 |
|--------|------|
| `'0 10 * * 1-5'` | 월~금 18:00(베이징 시간) |
| `'30 7 * * 1-5'` | 월~금 15:30(베이징 시간) |
| `'0 10 * * *'` | 매일 18:00(베이징 시간) |
| `'0 2 * * 1-5'` | 월~금 10:00(베이징 시간) |

> 베이징 시간은 UTC+8, 한국 시간은 UTC+9이므로 한국 시간이 베이징 시간보다 1시간 빠릅니다.

### 관심 종목 변경

방법 1: 저장소 Secret `STOCK_LIST`를 수정합니다.

방법 2: 코드를 직접 수정한 뒤 푸시합니다.
```bash
# .env.example을 수정하거나 코드에서 기본값 설정
git commit -am "Update stock list"
git push
```

### 자주 묻는 질문

**Q: 예약 실행이 왜 실행되지 않나요?**
A: GitHub Actions 예약 실행은 5~15분 늦어질 수 있고, 저장소에 활동이 있을 때만 실행됩니다. 오랫동안 commit이 없으면 workflow가 비활성화될 수 있습니다.

**Q: 이전 리포트는 어떻게 보나요?**
A: Actions → 실행 기록 선택 → Artifacts → `analysis-reports-xxx` 다운로드

**Q: 무료 사용량으로 충분한가요?**
A: 한 번 실행에 약 2~5분이 걸리므로 한 달 영업일 22일 기준 44~110분이며, 2000분 한도보다 훨씬 적습니다.

---

## 🌐 클라우드 서버에 배포했는데 브라우저로 어떻게 접속하나요?

자세한 내용 → [클라우드 서버 Web 화면 접속 가이드](deploy-webui-cloud.md)

다루는 내용: 직접 배포와 Docker 두 방식의 시작 및 접속 방법, 보안 그룹/방화벽 설정, 자주 발생하는 문제 해결, Nginx 리버스 프록시(선택).

---

**배포가 순조롭기를 바랍니다! 🎉**
