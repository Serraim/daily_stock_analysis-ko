# 클라우드 서버 웹 화면 접속 가이드

프로젝트를 클라우드 서버에 배포했는데 브라우저에 어떤 주소를 넣어야 웹 관리 화면이 열리는지 모르겠다면, 이 문서를 보시면 됩니다.

> 사실 두 단계면 됩니다. 서비스가 외부 접속을 받도록 하고, 브라우저에 주소를 입력하는 것입니다.

---

## 목차

- [방법 1: 직접 배포(pip + python)](#方式一直接部署pip--python)
- [방법 2: Docker Compose](#方式二docker-compose)
- [브라우저에서 화면 여는 법](#如何在浏览器里打开界面)
- [Docker 재빌드가 적용되었는지 확인하는 법](#如何确认-docker-重建已生效)
- [접속이 안 되나요? 먼저 이것부터 확인하세요](#访问不了先检查这几项)
- [선택: Nginx 리버스 프록시(도메인 연결 / 80 포트)](#可选nginx-反向代理绑定域名--80-端口)
- [보안 권장 사항](#安全建议)

---

<a id="方式一直接部署pip--python"></a>

## 방법 1: 직접 배포(pip + python)

### 1단계: .env의 수신 주소 바꾸기

편집기로 `.env`(프로젝트 루트, 즉 `main.py`가 있는 디렉터리)를 열고 다음 줄을 찾습니다.

```env
WEBUI_HOST=127.0.0.1
```

`127.0.0.1`을 `0.0.0.0`으로 바꿉니다.

```env
WEBUI_HOST=0.0.0.0
```

> `127.0.0.1`은 이 컴퓨터에서만 접속할 수 있다는 뜻이고, `0.0.0.0`은 어디서든 접속을 받는다는 뜻입니다. 클라우드 서버에서는 `.env`의 `WEBUI_HOST`를 `0.0.0.0`으로 바꾸거나 시작 명령에 `--host 0.0.0.0`을 명시해야 외부에서 화면을 열 수 있습니다.

### 2단계: 서비스 시작

프로젝트 루트에서 실행합니다.

```bash
# 웹 화면만 시작(분석은 자동으로 실행하지 않음)
python main.py --webui-only

# 또는: 웹 화면 시작(시작할 때 분석을 한 번 실행. 매일 예약 분석이 필요하면 --schedule을 붙이거나 SCHEDULE_ENABLED=true로 설정)
python main.py --webui
```

시작에 성공하면 터미널에 다음과 비슷한 내용이 나옵니다(`FastAPI 服务已启动`은 "FastAPI 서비스가 시작됨"이라는 뜻입니다).

```
FastAPI 服务已启动: http://0.0.0.0:8000
```

터미널을 닫은 뒤에도 서비스가 계속 돌게 하려면 `nohup`을 쓸 수 있습니다.

```bash
nohup python main.py --webui-only > /dev/null 2>&1 &
```

> 로그 파일은 프로그램이 자동으로 `logs/` 디렉터리에 씁니다. `tail -f logs/stock_analysis_*.log`로 볼 수 있습니다.

### 포트 바꾸기(선택)

기본 포트는 8000입니다. 다른 포트를 쓰려면 `.env`에 설정합니다.

```env
WEBUI_PORT=8888
```

그런 다음 서비스를 다시 시작합니다.

---

<a id="方式二docker-compose"></a>

## 방법 2: Docker Compose

### 1단계: .env 설정이 있는지 확인

프로젝트의 `docker/docker-compose.yml`은 컨테이너 안에서 이미 `WEBUI_HOST=0.0.0.0`을 자동으로 설정합니다. `.env`에서 수신 주소를 따로 바꿀 필요 없이 Docker가 처리합니다.

Docker Compose의 `env_file: ../.env`는 `.env`를 **시작 시 환경 변수**로 컨테이너에 넣을 뿐, 컨테이너 안에 `/app/.env`를 만들지 않으며, WebUI가 설정을 저장할 때 호스트의 `.env`에 다시 쓰지도 않습니다. 새 버전 WebUI는 사용 중인 `.env` 파일에 일부 키가 없으면 시작 시 주입된 같은 이름의 환경 변수를 대신 보여 주므로, Docker 시작 때 주입한 설정이 페이지에 보입니다. 하지만 "`.env` 내보내기"는 여전히 현재 사용 중인 설정 파일의 내용만 내보냅니다.

WebUI에서 저장한 설정을 컨테이너를 지우거나 다시 만들거나 업그레이드한 뒤에도 유지하려면, 사용할 설정 파일을 마운트된 데이터 볼륨에 두세요. 예를 들어 Compose의 `environment`에 다음을 추가합니다.

```yaml
- ENV_FILE=/app/data/runtime.env
```

`../data:/app/data` 마운트도 그대로 둡니다. 주의: 시작할 때의 `../.env`, `docker run -e`, Compose `environment:`에 같은 이름의 예전 값이 남아 있으면, 컨테이너를 다시 시작한 뒤 이 시작 환경 변수가 실행 파일에 저장된 값을 덮어쓸 수 있습니다. WebUI에서 저장한 값을 쓰려면 시작 환경의 같은 이름 설정을 함께 고치거나 지우세요.

### 2단계: 서비스 시작

프로젝트 루트에서 실행합니다.

```bash
# 예약 분석 + 웹 화면을 함께 시작(권장)
docker-compose -f ./docker/docker-compose.yml up -d

# 또는 웹 화면 서비스만 시작
docker-compose -f ./docker/docker-compose.yml up -d server
```

시작한 뒤 상태를 확인합니다.

```bash
docker-compose -f ./docker/docker-compose.yml ps
```

`server` 서비스 상태가 `running`이면 웹 화면이 실행 중이라는 뜻입니다.

### 포트 바꾸기(선택)

기본 포트는 8000입니다. 다른 포트를 쓰려면 `.env`에 설정합니다.

```env
API_PORT=8888
```

그런 다음 컨테이너를 다시 시작합니다.

```bash
docker-compose -f ./docker/docker-compose.yml down
docker-compose -f ./docker/docker-compose.yml up -d
```

---

<a id="如何在浏览器里打开界面"></a>

## 브라우저에서 화면 여는 법

서비스가 시작되면 브라우저 주소창에 다음을 입력합니다.

```
http://서버의_공인_IP:8000
```

예를 들어 서버 IP가 `1.2.3.4`라면 다음을 입력합니다.

```
http://1.2.3.4:8000
```

도메인이 이 서버를 가리키도록 설정되어 있다면 도메인으로 바로 접속해도 됩니다.

```
http://your-domain.com:8000
```

> **공인 IP는 어디서 확인하나요?** 클라우드 서버 콘솔(Alibaba Cloud/Tencent Cloud/AWS 등)에 로그인하면 인스턴스 목록에서 「공인 IP」나 「탄력적 IP」를 볼 수 있습니다.

---

<a id="如何确认-docker-重建已生效"></a>

## Docker 재빌드가 적용되었는지 확인하는 법

먼저 두 가지를 구분하세요.

1. **Docker 이미지 배포 버전**: 배포할 때 쓴 이미지 tag를 봅니다. 예: `ghcr.io/zhulinsen/daily_stock_analysis:v3.12.0`. 저장소의 Docker 배포는 `.github/workflows/docker-publish.yml`이 `v*.*.*` Git tag에 따라 실행하므로, Docker 버전은 이미지 tag / GitHub Releases를 기준으로 합니다.
2. **현재 페이지가 불러온 프런트엔드 빌드**: WebUI "시스템 설정" 페이지의 버전 정보 카드를 보고, 브라우저가 받은 정적 리소스가 새것인지 확인합니다.

즉 **"시스템 설정"의 버전 정보는 프런트엔드 재빌드 성공 여부를 판단하는 데 알맞으며, Docker 이미지 배포 버전과 같지 않습니다**.

WebUI는 이제 "시스템 설정" 페이지에 읽기 전용 "버전 정보" 카드를 보여 주며, 다음을 포함합니다.

- `WebUI 版本`(WebUI 버전)
- `代码版本`(코드 버전)
- `构建时间`(빌드 시각)

정식 Docker / Desktop 배포는 release tag를 `WebUI 版本`으로 넣고, 해당 commit을
`代码版本`으로 보여 줍니다. Git clone으로 직접 빌드하면 WebUI는 `git describe`와 현재
commit을 씁니다. 빌드 환경에 배포 정보도 Git 메타데이터도 없으면 버전은 분명하게
`development`로 표시되며, 빌드 시각을 배포 버전처럼 보여 주지 않습니다.

`docker-compose -f ./docker/docker-compose.yml up -d --build`를 다시 실행했거나 프런트엔드 `npm run build`만 다시 실행했다면, 브라우저를 새로 고친 뒤 "시스템 설정"에 들어가 "코드 버전"과 "빌드 시각"이 바뀌었는지 확인하세요. 두 값을 함께 보면 브라우저가 지금 불러온 정적 리소스가 어떤 코드와 빌드에서 왔는지 확인할 수 있습니다.

"지금 배포한 것이 정확히 어느 정식 버전인지" 확인하려면 다음 방법을 우선 쓰세요.

```yaml
# 방법 1: docker-compose / 배포 스크립트의 image tag 보기
image: ghcr.io/zhulinsen/daily_stock_analysis:v3.12.0
```

```bash
# 방법 2: 실행했던 pull 명령 다시 보기
docker pull ghcr.io/zhulinsen/daily_stock_analysis:v3.12.0
```

계속 `latest`를 써 왔다면 명시적인 버전 tag로 바꾸는 것을 권장합니다. 그렇지 않으면 컨테이너 안 페이지 정보만으로는 같은 버전으로 다시 업데이트했는지 판단하기 어렵습니다.

로컬 프런트엔드 패키징 과정을 확인할 때는 다음 명령을 최소 검증으로 실행하는 것을 권장합니다.

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run build
```

`build`가 성공하면 `static` 아래에 만들어진 `index.html`/JS/CSS 리소스에 이번 버전,
commit, 빌드 시각이 들어가고 `build-info.json`도 만들어집니다. 시작할 때 이 파일의 소스 요약을 비교하므로,
`rsync -a`가 예전 타임스탬프를 유지하더라도 소스와 정적 결과물이 다르다는 것을 알아채고 다시 빌드합니다.
새로 고친 뒤 "버전 정보" 카드에서 바뀐 값을 볼 수 있어야 합니다.

---

<a id="访问不了先检查这几项"></a>

## 접속이 안 되나요? 먼저 이것부터 확인하세요

### 1. 보안 그룹 / 방화벽에서 포트를 열지 않음

가장 흔한 원인입니다. 클라우드 서버는 기본으로 22(SSH) 포트만 열려 있으므로, 8000(또는 바꾼 포트)을 직접 열어야 합니다.

**방법**(Alibaba Cloud 예시):
1. Alibaba Cloud 콘솔에 로그인 → 클라우드 서버 ECS → 해당 인스턴스 찾기
2. 「보안 그룹」→「규칙 설정」→「보안 그룹 규칙 추가」 클릭
3. 방향은 「인바운드」, 포트 범위는 `8000/8000`, 허용 대상은 `0.0.0.0/0`으로 넣고 「확인」 클릭

Tencent Cloud, AWS 등 다른 클라우드도 비슷합니다. 「보안 그룹」이나 「방화벽 규칙」을 찾아 TCP 8000 포트를 허용하는 인바운드 규칙을 하나 추가하면 됩니다.

### 2. 서버 운영 체제의 방화벽이 막고 있음

시스템에서 `ufw`나 `firewalld`를 쓰고 있다면 여기서도 포트를 열어야 합니다.

```bash
# Ubuntu / Debian(ufw)
sudo ufw allow 8000

# CentOS / RHEL(firewalld)
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### 3. 직접 배포에서 .env의 WEBUI_HOST를 바꾸지 않음

두 번째로 흔한 원인입니다. `.env`의 기본값은 `WEBUI_HOST=127.0.0.1`이라서 서비스가 이 컴퓨터에서만 접속을 받고, 외부에서는 아예 연결할 수 없습니다.

고치는 법: `.env`를 열어 `WEBUI_HOST=127.0.0.1`을 `WEBUI_HOST=0.0.0.0`으로 바꾸고 서비스를 다시 시작합니다. 시작 명령에 `--host 0.0.0.0`을 명시해도 됩니다.

> Docker 방식은 이 설정을 바꿀 필요가 없으니 건너뛰어도 됩니다.

### 4. 포트 번호가 맞지 않음

접속 주소의 포트가 `.env` / 시작 명령에서 설정한 포트와 같은지 확인하세요.

- 직접 배포: 기본 8000, `WEBUI_PORT=xxxx`로 바꿀 수 있음
- Docker: 기본 8000, `API_PORT=xxxx`로 바꿀 수 있음

### 5. 페이지는 열리는데 UI 요소가 비정상적으로 크거나 레이아웃이 깨짐

**증상**: 브라우저로 8000 포트에 접속되고 내용도 보이지만, 글자, 버튼, 카드가 비정상적으로 크고 정상적인 레이아웃과 색상이 없습니다.

**근본 원인**: `static/index.html`은 있지만 CSS/JS 리소스가 없습니다(`static/assets/`가 비어 있거나 없음). 브라우저가 HTML 뼈대만 불러오고 스타일과 스크립트를 받지 못해 꾸밈없는 HTML로 표시된 것입니다.

먼저 브라우저 개발자 도구(F12 → Network 탭)에서 `/assets/index-*.js`, `/assets/index-*.css`에 **404** 오류가 있는지 확인하세요. 있다면 다음처럼 고칩니다.

**Docker 사용자**:

```bash
docker-compose -f ./docker/docker-compose.yml down
docker-compose -f ./docker/docker-compose.yml build --no-cache
docker-compose -f ./docker/docker-compose.yml up -d
```

다시 빌드한 뒤 `Ctrl+Shift+R`로 브라우저 캐시를 무시하고 새로 고친 다음 페이지에 접속합니다.

**직접 배포 사용자**: 먼저 Node.js 18 이상(20 이상 권장)을 설치한 뒤 프런트엔드를 직접 빌드합니다.

```bash
cd apps/dsa-web
npm ci
npm run build
cd ../..
python main.py --webui-only
```

---

<a id="可选nginx-反向代理绑定域名--80-端口"></a>

## 선택: Nginx 리버스 프록시(도메인 연결 / 80 포트)

도메인이 있거나 주소에 `:8000`을 붙이고 싶지 않다면, Nginx를 리버스 프록시로 써서 80/443 포트로 들어온 트래픽을 백엔드 서비스로 넘길 수 있습니다.

### Nginx 설치

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y nginx

# CentOS
sudo yum install -y nginx
```

### 설정 파일 예시

`/etc/nginx/conf.d/stock-analyzer.conf` 파일을 새로 만들고 다음 내용을 넣습니다(`your-domain.com`은 자신의 도메인이나 IP로 바꾸세요).

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 지원(Agent 대화 페이지에 필요)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 설정을 적용하고 Nginx 다시 불러오기

```bash
sudo nginx -t            # 설정에 문법 오류가 없는지 확인
sudo systemctl reload nginx
```

설정이 끝나면 포트 번호 없이 `http://your-domain.com`으로 바로 접속할 수 있습니다.

> **Nginx를 쓴 뒤 주의할 점**:
> - 웹 로그인 인증(`ADMIN_AUTH_ENABLED=true`)을 켰다면 `.env`에서 `TRUST_X_FORWARDED_FOR=true`도 함께 켜는 것을 권장합니다. 그렇지 않으면 시스템이 실제 IP를 제대로 알아내지 못할 수 있습니다. 이 옵션은 **신뢰할 수 있는 리버스 프록시가 한 단계뿐인**(Nginx → App) 배포에 맞습니다. 여러 단계의 프록시나 CDN(CDN → Nginx → App)을 쓴다면 로그인 요청 제한의 key가 실제 클라이언트 IP가 아니라 가장자리 프록시 IP가 될 수 있으므로, 실제 구성에 맞춰 검토해야 합니다.
> - HTTPS가 필요하면 [Certbot](https://certbot.eff.org/)으로 무료 Let's Encrypt 인증서를 자동으로 받을 수 있습니다.

---

<a id="安全建议"></a>

## 보안 권장 사항

웹 화면을 인터넷에 공개하기 전에 로그인 비밀번호 보호를 꼭 켜는 것을 권장합니다.

`.env`에 다음을 설정합니다.

```env
ADMIN_AUTH_ENABLED=true
```

서비스를 다시 시작한 뒤 처음 웹 페이지에 접속하면 초기 비밀번호를 정하라고 나옵니다. 설정이 끝나면 설정 페이지를 열 때마다 비밀번호를 입력해야 하므로, API Key 같은 민감한 설정을 다른 사람이 보지 못하게 막을 수 있습니다.

> 비밀번호를 잊었다면 서버에서 다음을 실행하세요: `python -m src.auth reset_password`

---

다른 문제가 있나요? [Issue를 제출](https://github.com/ZhuLinsen/daily_stock_analysis/issues)해 주세요.
