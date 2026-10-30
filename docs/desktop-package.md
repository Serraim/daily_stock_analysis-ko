# 데스크톱 앱 패키징 안내 (Electron + React UI)

이 프로젝트는 데스크톱 앱으로 패키징할 수 있습니다. 데스크톱 껍데기로는 Electron을, 화면으로는 `apps/dsa-web`의 React UI를 사용합니다.

> 웹 UI는 현재 중국어와 영어만 지원합니다. 이 문서에서 화면 메뉴를 가리킬 때는 한국어 이름 뒤 괄호에 실제 화면에 표시되는 중국어/영어 이름을 함께 적었습니다.

## 구조 설명

- React UI(Vite로 빌드)는 로컬 FastAPI 서버가 제공합니다.
- Electron이 시작되면 백엔드 서버를 자동으로 띄우고, `/api/health`가 준비된 뒤 UI를 불러옵니다.
- Windows 포터블/설치 모드에서는 사용자 설정 파일 `.env`와 데이터베이스가 exe와 같은 폴더에 놓입니다. macOS 패키지 버전은 실행 중 설정을 Electron 사용자 데이터 폴더에 저장합니다.
- 데스크톱 앱은 이 컴퓨터의 `8000-8100` 범위에서 비어 있는 포트를 자동으로 고르고, 실제로 고른 포트를 내장 백엔드에 함께 넘깁니다. 창이 연결할 주소를 정할 때 `.env`의 `WEBUI_PORT`에 의존하지 않으므로, 사용자가 포트를 바꾼 뒤 Electron이 예전 포트를 계속 기다리다 시작 시간이 초과되는 문제를 막습니다.
- 데스크톱 백엔드는 기본적으로 `requirements.txt`를 따라 `futu-api==10.8.6808`을 설치하고 고정(freeze)합니다. Windows/macOS 빌드 스크립트는 소스 환경과 PyInstaller 결과물에서 각각 `import futu`를 실행해, 배포 패키지에 SDK가 설치만 되고 실제로는 포함되지 않는 일을 막습니다.
- 매물대(筹码分布, 가격대별 보유 물량 분포) 기능이 쓰는 `py_mini_racer`는 빌드 환경에 실제로 설치된 버전 기준으로 Python 모듈, 네이티브 라이브러리, 실행 데이터를 통째로 수집합니다. 버전이 다른 DLL, ICU, snapshot 파일을 손으로 끼워 맞추지 않습니다. Windows/macOS는 `mini-racer>=0.13.2`를 명시적으로 요구합니다. 구버전의 freeze 로더가 번들 루트 폴더에서 네이티브 라이브러리를 찾아, 패키지 폴더 기준으로 수집한 배치와 어긋나는 문제를 피하기 위해서입니다. Linux는 AkShare의 기존 의존성을 그대로 따릅니다. Windows/macOS 빌드 스크립트는 소스 환경과 freeze된 백엔드에서 `MiniRacer().eval('1 + 1')`을 실행하며, 네이티브 라이브러리가 없거나 버전이 맞지 않으면 패키징을 중단합니다. `import py_mini_racer`가 성공했다는 것만으로는 검수 통과로 보지 않습니다. 또한 이 오프라인 검사가 통과했다고 해서 온라인 동방재부(东财, 중국 금융 정보 사이트) 데이터 API가 반드시 동작한다는 뜻은 아닙니다.
- 보고서의 "공유" 버튼은 Electron에 내장된 숨겨진 Chromium 창으로 로컬 백엔드가 만든 제한된 HTML을 렌더링해 PNG로 저장합니다. 따라서 데스크톱 설치 패키지에 `wkhtmltoimage`, `markdown-to-file`, Playwright 브라우저를 따로 넣을 필요가 없습니다.

## 로컬 개발

한 번에 실행(개발 모드):

```bash
powershell -ExecutionPolicy Bypass -File scripts\run-desktop.ps1
```

또는 직접 실행합니다.

1) React UI 빌드(결과물은 `static/`에 생성)

```bash
cd apps/dsa-web
npm install
npm run build
```

2) Electron 앱 실행(백엔드는 자동으로 시작됨)

```bash
cd apps/dsa-desktop
npm install
npm run dev
```

처음 실행하면 `.env.example`을 복사해 `.env`를 자동으로 만듭니다.

## 패키징 (Windows)

### 사전 준비

- Node.js 18+
- Python 3.10+
- Windows 개발자 모드 켜기(electron-builder가 심볼릭 링크를 만들어야 하기 때문)
  - 설정 -> 개인 정보 및 보안 -> 개발자용 -> 개발자 모드

### 한 번에 패키징

```bash
powershell -ExecutionPolicy Bypass -File scripts\build-all.ps1
```

이 스크립트는 다음을 차례로 실행합니다.
1. React UI 빌드
2. Python 의존성 설치
3. PyInstaller로 백엔드 패키징
4. electron-builder로 데스크톱 앱 패키징

현재 Windows 설치 파일은 NSIS 마법사 방식의 설치 과정을 사용합니다. 현재 사용자 계정에만 설치할 수 있고 관리자 권한 상승은 꺼져 있으며, 설치할 때 대상 폴더를 직접 고를 수 있습니다(예: C 드라이브가 아닌 곳). 설치 프로그램은 NSIS `.onVerifyInstDir` 콜백으로 `Program Files`, `Windows` 같은 시스템 보호 폴더를 고르지 못하게 막습니다. 이런 경로를 고르면 "다음" 버튼이 자동으로 비활성화됩니다. 설치가 끝난 뒤에도 데스크톱 앱은 기존 방식대로 설치 폴더 옆에 `.env`, `data/stock_analysis.db`(`data/stock_analysis.db-wal` / `data/stock_analysis.db-shm` 포함), `logs/desktop.log`를 만들거나 읽습니다. 기본값인 사용자별(per-user) 설치 폴더를 권장합니다. 설치하고 싶지 않다면 지금처럼 `win-unpacked` 무설치 패키지를 배포해도 됩니다.

## GitHub CI로 자동 패키징 및 Release 게시

저장소는 GitHub Actions로 데스크톱 앱을 자동 빌드해 GitHub Releases에 올릴 수 있습니다.

- 워크플로: `.github/workflows/desktop-release.yml`
- 실행 방법:
  - 시맨틱 버전 tag(예: `v3.2.12`)를 push하면 자동 실행
  - Actions 페이지에서 수동으로 실행하면서 `release_tag` 지정
- 결과물:
  - Windows 설치 파일: Release 첨부 파일과 로컬 `apps/dsa-desktop/dist/` 모두 `daily-stock-analysis-windows-installer-<tag>.exe`라는 이름으로 통일
  - Windows 자동 업데이트 메타데이터: Release 첨부 파일에 `latest.yml`과 `*.blockmap`이 추가로 남습니다. 설치판 데스크톱 앱이 백그라운드에서 업데이트를 내려받고 검증하는 데 쓰므로, 일반 사용자는 이 메타데이터를 직접 받을 필요가 없습니다. 내려받기가 끝난 뒤 사용자가 "재시작 후 설치"를 확인하면, 데스크톱 앱은 먼저 내장 백엔드를 멈추고 실행 중 파일을 백업한 다음 설치 프로그램을 자동(silent) 모드로 실행합니다.
  - Windows 무설치 패키지: `daily-stock-analysis-windows-noinstall-<tag>.zip`
  - macOS Intel: `daily-stock-analysis-macos-x64-<tag>.dmg`
  - macOS Apple Silicon: `daily-stock-analysis-macos-arm64-<tag>.dmg`

<a id="macos-提示应用已损坏无法打开"></a>
### macOS에서 "앱이 손상되어 열 수 없습니다"가 뜰 때

현재 macOS DMG는 아직 Apple Developer 인증서로 서명하거나 공증(notarization)하지 않았습니다. 빌드 설정은 명시적으로 서명되지 않은(unsigned) 앱을 만들고, PyInstaller 결과물을 처음 실행하기 전에 불완전한 서명을 지우며, electron-builder `afterPack` hook으로 DMG를 만들기 직전에 완성된 `.app`을 다시 한번 정리합니다. CI는 Electron 원본 `.app`과 DMG를 마운트한 뒤의 `.app`도 검사해, `code has no resources but signature indicates they must be present` 같은 손상된 서명이 들어간 결과물이 다시 배포되지 않도록 막습니다. 이 처리는 v3.27.0의 불완전한 서명 결함을 줄여 줄 뿐, **앱이 Apple의 신뢰를 얻게 해 주지는 않습니다**. 브라우저로 내려받은 뒤에도 macOS Gatekeeper가 "개발자를 확인할 수 없습니다"라고 표시하거나, 실행을 막거나, 사용자의 직접 확인을 요구할 수 있습니다.

다음 순서로 확인합니다.

1. 반드시 프로젝트의 [GitHub Releases](https://github.com/ZhuLinsen/daily_stock_analysis/releases)에서만 첨부 파일을 내려받고, 설치 파일의 아키텍처가 Mac과 맞는지 확인합니다. Apple 칩(M1/M2/M3/M4 등)은 `daily-stock-analysis-macos-arm64-<tag>.dmg`, Intel 칩은 `daily-stock-analysis-macos-x64-<tag>.dmg`를 사용합니다. 제3자가 다시 올렸거나 출처가 불분명한 설치 파일에 대해서는 Gatekeeper를 우회하지 마십시오.
2. DMG를 열어 `Daily Stock Analysis`를 "응용 프로그램" 폴더로 끌어다 놓은 뒤 한 번 실행해 봅니다. 차단되면 "시스템 설정 -> 개인정보 보호 및 보안"으로 가서 보안 알림에 표시된 앱 이름을 확인한 다음 "그래도 열기"를 누르고, 시스템 안내에 따라 한 번 더 확인합니다. 이전 macOS에서는 "시스템 환경설정 -> 보안 및 개인 정보 보호 -> 일반"이 같은 위치입니다.
3. 설치 파일이 위의 공식 Release에서 받은 것이 확실하고, "그래도 열기"로도 실행되지 않을 때에만 "터미널"을 열어 이 앱의 다운로드 격리(quarantine) 속성을 지운 뒤 다시 실행합니다.

```bash
xattr -dr com.apple.quarantine "/Applications/Daily Stock Analysis.app"
open "/Applications/Daily Stock Analysis.app"
```

앱이 `/Applications`에 없다면 명령의 경로를 실제 `.app` 경로로 바꾸십시오. "응용 프로그램" 폴더 전체에 `xattr`를 실행하지 말고, 출처가 불분명한 앱에도 이 명령을 쓰지 마십시오. macOS 버전에 따라서는 그래도 서명되지 않은 앱을 거부할 수 있으며, quarantine 속성을 지운다고 해서 실행이 보장되지는 않습니다. 이 경고를 근본적으로 없애려면 배포 과정에 Apple Developer 서명과 공증(notarization)을 넣어야 하며, 이는 위의 임시 허용 절차와는 별개의 일입니다.

관리자(메인테이너)는 다음 명령으로 "예상된 unsigned 거부"와 "배포하면 안 되는 불완전한 서명"을 구분할 수 있습니다.

```bash
codesign -d "/Applications/Daily Stock Analysis.app"
spctl --assess --type execute --verbose=4 "/Applications/Daily Stock Analysis.app"
```

현재 unsigned 결과물이라면 `codesign -d` 출력에 `code object is not signed at all`이 포함되고 `spctl`은 거부하는 것이 정상입니다. `code has no resources but signature indicates they must be present` 또는 다른 서명 손상 메시지가 나오면 배포를 중단해야 합니다.

권장 배포 절차:

1. 코드를 `main`에 병합
2. 자동 tag 워크플로가 버전을 만듦(또는 직접 tag 생성)
3. `desktop-release` 워크플로가 자동으로 빌드해 두 플랫폼의 설치 파일을 해당 GitHub Release에 첨부

## 배포 전 재현 가능한 검증(데스크톱 업데이트 경로)

데스크톱 자동 업데이트 경로는 Windows NSIS 설치 결과물과 `latest.yml`, `*.blockmap` 메타데이터에 의존합니다. 현재 데스크톱 CI는 `desktop-release` 패키징 결과물이 실제로 배포 가능한지까지는 확인하지 않으므로, 제출 전에 다음 로컬 검증을 추가로 해 두기를 권장합니다.

참고: 이 체크리스트는 Windows NSIS 설치판과 `electron-updater` 배포 메타데이터에 초점을 둡니다. 현재 Linux 환경에서는 Windows 설치 파일과 updater 메타데이터(`latest.yml` / `*.blockmap`)를 바로 만들 수 없으므로, 이 경로는 Windows 배포 실행 환경(runner)이나 Windows PC에서 다시 확인해야 합니다.

Windows가 아닌 환경에서 위 검증을 마칠 수 없다면, PR 검수 설명에 Windows 배포 경로를 다시 확인할 담당자, 확인 일정, `desktop-release` 결과물 점검 결과(release/tag와 `daily-stock-analysis-windows-installer-<tag>.exe`, `latest.yml`, `*.blockmap`의 버전 일치 여부와 내려받기 가능 여부)를 분명히 적어 주십시오.

1. 먼저 Web 정적 결과물을 빌드합니다(데스크톱 앱의 메인 창과 설정 페이지 진입이 여기에 의존합니다).

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run build
```

2. 데스크톱 앱 폴더로 돌아가 의존성을 설치하고, preload 단위 테스트를 실행한 뒤 Electron 패키징을 실행합니다.

```bash
cd ../dsa-desktop
npm ci
npm test
npm run build
```

Windows 배포 확인 환경에서는 다음도 추가로 실행할 수 있습니다.

```powershell
./scripts/verify-desktop-updater-artifacts.ps1 -ReleaseTag v$(node -p "require('./apps/dsa-desktop/package.json').version")
```

> 지금 실행하는 환경이 Windows NSIS 설치 프로그램을 만들 수 없다면, 전달 설명에 플랫폼 제약을 분명히 적고 지정된 Windows 배포 경로 확인 담당자에게 이 검증을 마무리해 달라고 요청하십시오.

3. 업데이트 메타데이터가 생성되었는지 확인합니다.

```bash
ls -1 dist | sort
ls -1 dist/*.yml dist/*.blockmap 2>/dev/null || true
```

4. 버전과 배포 첨부 파일이 맞는지 강제로 대조합니다(Windows 환경이나 NSIS 결과물을 만들 수 있는 실행 환경에서 확인).

```bash
RELEASE_TAG="v$(node -p \"require('./package.json').version\")"
REPO="ZhuLinsen/daily_stock_analysis"

for f in dist/*latest.yml dist/*.blockmap dist/daily-stock-analysis-windows-installer-*.exe; do
  [ -f \"$f\" ] && echo \"[FOUND] $f\"
done

if [ -f dist/latest.yml ]; then
  echo \"---- latest.yml 버전 부분 ----\"
  grep -E \"^version:|^files:|^sha512:\" dist/latest.yml
fi

echo \"---- Release 목록(직접 대조) ----\"
echo \"Release Tag: $RELEASE_TAG\"
echo \"Release 주소: https://github.com/$REPO/releases/tag/$RELEASE_TAG\"
echo \"첨부 파일에 다음이 있는지 확인:\"
echo \"- daily-stock-analysis-windows-installer-*.exe\"
echo \"- latest.yml\"
echo \"- *.blockmap\"
echo \"그리고 latest.yml의 version이 tag의 시맨틱 버전과 같고, path/url이 설치 파일 첨부 이름과 같은지 확인\"
```

5a. PR 설명에 남기기를 권장하는 "다시 확인할 수 있는 출력"(Windows):

```bash
echo "release-tag=${RELEASE_TAG}"
echo "latest.yml version:"
grep -E "^version:" dist/latest.yml
echo "latest.yml files:"
sed -n '1,80p' dist/latest.yml
echo "packaging artifacts:"
ls -1 dist/*.yml dist/*.blockmap dist/*installer*.exe 2>/dev/null | sort
```

Windows 배포 경로 확인 체크리스트(PR 이후 배포 팀/메인테이너가 실행):

- release/tag와 `daily-stock-analysis-windows-installer-<tag>.exe`의 버전 번호가 같은지
- `latest.yml`, `daily-stock-analysis-windows-installer-<tag>.exe`, `*.blockmap`이 같은 tag에 함께 올라와 있고 내려받을 수 있는지
- `latest.yml`의 `version`이 Release tag와 의미상 같은지(`v` 접두어를 뗀 뒤 비교), 그리고 `path` / `files.url`이 설치 파일 첨부 이름과 같은지
- 위 파일이 빠졌거나 `release-tag`가 맞지 않으면 배포 차단으로 표시하고 `desktop-release` 패키징 과정을 보완

5. Windows/NSIS 결과물과 배포 첨부 파일이 일치하는지는 Windows 환경에서 직접 확인하고(배포 과정을 수동으로 실행해도 됩니다), 업그레이드 후 실행 중 파일이 그대로 남아 있는지 대조합니다.

   1. 설치 전후로 각각 설치 폴더의 `.env`, `data/stock_analysis.db`, `data/stock_analysis.db-wal`, `data/stock_analysis.db-shm`, `logs/desktop.log`의 SHA256을 기록합니다.
   2. 데스크톱 앱을 다음에 실행한 뒤에도 위 파일이 그대로 있고 설치 전 기록과 같은지 확인합니다.
   3. 다르다면 앱을 종료한 뒤 사용자 데이터 폴더의 `.dsa-desktop-update-backup`이 깨끗이 정리되었는지 확인하고, 최신 로그와 함께 원인을 따라가 봅니다.

Windows에서는 PowerShell로 실행하기를 권장합니다.

```bash
Get-FileHash .env,data\\stock_analysis.db,data\\stock_analysis.db-wal,data\\stock_analysis.db-shm,logs\\desktop.log -Algorithm SHA256
```

참고: Windows NSIS 설치판은 "재시작 후 설치" 전에 내장 백엔드를 멈추고, 설치 폴더 옆의 위 실행 중 파일을 백업한 뒤, 업데이트 설치 프로그램을 자동(silent) 모드로 실행합니다. 설치 마법사가 아직 실행 중인 데스크톱 앱 프로세스를 먼저 덮어쓰는 일을 피하고, 업데이트 도중 파일이 사라질 위험을 줄이기 위한 것입니다. 복원에 실패하면 데스크톱 앱은 업데이트 설치 오류를 표시하고, 되돌릴 수 있도록 수동 다운로드 경로를 남겨 둡니다. 이 수정은 Windows 업데이트 설치 경로와 내장 백엔드 프로세스 수명 관리만 바꾸었으며, 설정 저장 방식, 모델 실행 정리 정책, 설정 이전 동작에는 영향을 주지 않습니다.

### 단계별 패키징

1) React UI 빌드

```bash
cd apps/dsa-web
npm install
npm run build
```

2) 기존 스크립트로 Python 백엔드 패키징(스크립트가 DSA 종목 선별 엔진, Futu SDK, AkShare 데이터 파일을 수집합니다)

- Windows:

```bash
powershell -ExecutionPolicy Bypass -File scripts\build-backend.ps1
```

- macOS:

```bash
bash scripts/build-backend-macos.sh
```

macOS 백엔드 패키징은 `src/services/screening/strategies` YAML 리소스 폴더를 명시적으로 포함합니다. PyInstaller 인자 배열 회귀 테스트는 실제 Bash로 숨은 import(hidden import)와 독립 `main.py` 진입점을 검증합니다.

이 스크립트는 의존성을 설치한 뒤 `--collect-all src.services.screening`, `--collect-all futu`, `--collect-data akshare`를 실행합니다. 빌드가 끝나면 freeze된 실행 파일로 `src.services.screening.pipeline`, `futu`, `orjson`을 모두 import할 수 있는지 검사하고, 종목 선별 전략 수를 대조하며, AkShare의 `file_fold/calendar.json`이 freeze 결과물에 들어갔는지 확인합니다. 이렇게 해서 배포 패키지가 종목 선별, 테마 핫이슈, Futu 보유 종목 가져오기, 일봉 보강 경로에서 모듈이나 package data가 없어 기능이 축소되는 일을 막습니다. 종목 선별 구현은 AlphaSift를 참고했습니다. PR 메인 CI는 `requirements.txt`, Futu broker, Desktop 패키징 진입점 또는 관련 workflow가 바뀌면 `desktop-futu-package-windows`와 `desktop-futu-package-macos` 차단 검사를 각각 실행합니다.

3) Electron 데스크톱 앱 패키징

```bash
cd apps/dsa-desktop
npm install
npm run build
```

패키징 결과물은 `apps/dsa-desktop/dist/`에 있습니다. Windows 설치 프로그램은 `daily-stock-analysis-windows-installer-<tag>.exe`로 생성되며, 설치 마법사에서 설치 폴더를 고를 수 있습니다.

## 폴더 구조

Windows 설치판에서는 설치 프로그램이 현재 사용자 계정에만 설치되고 관리자 권한 상승은 꺼져 있으며, 사용자가 설치 마법사에서 설치 폴더를 고를 수 있습니다. 설치 프로그램은 `Program Files`, `Windows` 같은 시스템 보호 폴더를 고르지 못하게 막습니다(고르면 "다음" 버튼이 자동으로 비활성화됨). 설치가 끝나면 앱은 설치 폴더 옆에 `.env`, `data/stock_analysis.db`(`data/stock_analysis.db-wal` / `data/stock_analysis.db-shm` 포함), `logs/desktop.log`를 만들거나 읽습니다. 기본 사용자별(per-user) 설치 위치를 그대로 두거나, 사용자가 쓰기 권한을 가진 다른 폴더를 고르십시오.

`win-unpacked` 무설치 모드의 폴더 구조는 다음과 같습니다.

```
win-unpacked/
  Daily Stock Analysis.exe    <- 더블클릭해 실행
  .env                        <- 사용자 설정 파일(처음 실행 시 자동 생성)
  data/
    stock_analysis.db         <- 데이터베이스 본 파일
    stock_analysis.db-wal     <- WAL 로그 파일(업데이트 백업/복원 대상)
    stock_analysis.db-shm     <- WAL 공유 메타 파일(업데이트 백업/복원 대상)
  logs/
    desktop.log               <- 실행 로그
  resources/
    .env.example              <- 설정 템플릿
    backend/
      stock_analysis.exe      <- 백엔드 서버
```

## 설정 파일 안내

- Windows 데스크톱 앱의 `.env`는 exe와 같은 폴더에 있습니다.
- macOS 패키지 버전의 `.env`, `data/`, `logs/`는 Electron 사용자 데이터 폴더에 있어서 `.app`을 교체해도 사라지지 않습니다.
- 처음 실행할 때 `.env.example`을 복사해 자동으로 만듭니다.
- 구버전에서 업그레이드할 때 예전 `.app` 패키지 안의 `.env`, `data/stock_analysis.db`, 로그 파일에 아직 접근할 수 있으면, 새 버전은 대상 파일이 없을 때에 한해 사용자 데이터 폴더로 자동 이전합니다. 이미 있는 대상 파일은 덮어쓰지 않습니다.
- 사용자는 `.env`를 편집해 다음 항목을 설정해야 합니다.
  - `GEMINI_API_KEY` 또는 `OPENAI_API_KEY`: AI 분석에 꼭 필요
  - `STOCK_LIST`: 관심 종목 목록(쉼표로 구분)
  - 기타 선택 설정은 `.env.example` 참고

### `.env` 설정 백업 / 복원

- WebUI와 데스크톱 앱 모두 **시스템 설정 -> 설정 백업**(`系统设置 -> 配置备份` / `System settings -> Configuration backup`)에서 **.env 내보내기**(`导出 .env` / `Export .env`)와 **.env 가져오기**(`导入 .env` / `Import .env`) 버튼을 볼 수 있습니다.
- 데스크톱이 아닌 WebUI에서는 먼저 관리자 인증을 켜고 로그인해야 합니다. 인증을 켜지 않으면 버튼이 비활성화되고 API는 `403`을 돌려줍니다.
- **.env 내보내기**는 현재 **저장된** `.env` 백업 파일만 내보냅니다. 화면에서 아직 **설정 저장**(`保存配置` / `Save configuration`)을 누르지 않은 로컬 임시 변경은 내보내지 않습니다.
- **.env 가져오기**는 백업 파일의 키와 값을 읽어 현재 설정에 합치고, 가져온 즉시 설정을 다시 불러옵니다.
- 가져오기는 파일 전체 교체가 아니라 "키 단위 덮어쓰기"입니다. 백업 파일에 있는 키는 현재 값을 덮어쓰고, 없는 키는 그대로 둡니다.
- 현재 화면에 저장하지 않은 임시 변경이 있으면, 가져오기 전에 먼저 확인을 요청해 로컬 임시 변경과 저장된 설정이 뒤섞이지 않게 합니다.
- Web에서 기본값 `ADMIN_AUTH_ENABLED=false`일 때는 설정 페이지의 버튼이 비활성 상태로 표시되고 관리자 인증을 먼저 켜라는 안내가 나옵니다. 데스크톱 앱은 이 설정과 상관없이 설정 백업/복원 기능을 바로 쓸 수 있습니다.

> 권장: 구버전에서 업그레이드하는 macOS 사용자는 업그레이드 전에 **.env 내보내기**를 한 번 해 두면 안전합니다. 예전 `.app`이 이미 통째로 교체되었다면 패키지 안의 예전 파일은 되살릴 수 없으며, 백업을 가져오는 방법밖에 없습니다.

### 설정 페이지의 버전 정보

- **시스템 설정 -> 버전 정보**(`系统设置 -> 版本信息` / `System settings -> Version info`)의 "데스크톱 버전"(`桌面端版本` / `Desktop version`)은 Electron 메인 프로세스의 `app.getVersion()`이 제공하며, preload bridge를 통해 프런트엔드에 전달됩니다.
- 개발 모드 `npm run dev`와 패키지 모드 `npm run build` / 설치 파일 모두 같은 버전 주입 경로를 사용하며, `preload.js`에 따로 하드코딩한 버전 번호를 더는 관리하지 않습니다.
- `README.md`에는 설치와 실행 안내만 남겨 둡니다. 이런 데스크톱 실행 세부 사항은 이 문서에서 관리해 입문 문서가 지나치게 길어지지 않게 합니다.

### 같은 네트워크(LAN)에서 Windows 데스크톱 앱의 WebUI 접속하기

- 데스크톱 앱은 기본적으로 `WEBUI_HOST=127.0.0.1`로 이 컴퓨터에서만 접속할 수 있게 합니다. 설치 후 의도치 않게 백엔드 서버가 외부에 노출되는 것을 막기 위해서입니다.
- 같은 네트워크의 다른 기기에서 접속하려면 데스크톱 앱의 `.env` 또는 **시스템 설정**(`系统设置` / `System settings`)의 WebUI 수신 주소 항목(`WEBUI_HOST`)에서 `WEBUI_HOST=0.0.0.0`으로 설정하고 저장한 뒤 데스크톱 앱을 다시 시작합니다.
- 데스크톱 앱은 `8000-8100` 중 비어 있는 포트를 자동으로 골라 백엔드에 넘깁니다. 대부분은 여전히 `8000`이며, 포트가 사용 중이면 `logs/desktop.log`에서 `Using port ...`와 `Backend launch command=...`를 확인할 수 있습니다.
- Windows 방화벽이나 서버 보안 그룹에서도 실제 수신 포트를 허용해야 합니다. 외부에 공개하기 전에는 `ADMIN_AUTH_ENABLED`도 함께 켜는 것을 권장합니다.
- 백엔드가 `0.0.0.0`에 바인딩되어 있어도 데스크톱 창 자체는 이 컴퓨터에서 접근 가능한 주소로 상태 확인과 페이지 로딩을 합니다.

### 데스크톱 앱 업데이트 알림

- 앱은 메인 화면을 다 불러온 뒤 백그라운드에서 GitHub Releases의 최신 정식 버전을 확인하고, 현재 `app.getVersion()`과 시맨틱 버전으로 비교합니다.
- Windows NSIS 설치판은 내장된 GitHub 업데이트 소스로 새 버전을 자동으로 내려받습니다. 내려받기가 끝나면 알림을 한 번 띄우고, 사용자가 확인하면 조용히 재시작해 설치합니다.
- 자동 업데이트의 무인 설치는 현재 설치 폴더를 그대로 사용합니다. 사용자가 설치할 때 기본값이 아닌 폴더나 공백이 들어간 폴더를 골랐다면, 이후 자동 업데이트도 같은 폴더를 덮어씁니다.
- 데스크톱 앱에서는 화면 전체 오른쪽 위에 업데이트 버튼이 표시되어, 상태 확인, 수동 확인, Release 페이지 열기, 업데이트를 내려받은 뒤 "재시작 후 설치"를 할 수 있습니다. 일반 브라우저의 WebUI에는 이 버튼이 나타나지 않습니다.
- **시스템 설정 -> 버전 정보**의 "데스크톱 업데이트"(`桌面端更新` / `Desktop update`) 영역은 여전히 자세한 입구이자 대체 수단으로 쓸 수 있습니다. 오른쪽 위 버튼과 설정 페이지는 같은 업데이트 상태를 공유하며, 확인·내려받기·설치 중에는 양쪽 모두 비활성화되어 수동 확인을 중복으로 시작하지 않습니다.
- 메인 프로세스의 수동 확인 경로에도 진행 중(in-flight) 중복 방지가 있어 GitHub Releases에 동시에 요청을 보내지 않습니다.
- Windows 무설치 패키지, 개발 모드, macOS DMG는 계속 "알림 + 다운로드 페이지로 이동" 방식을 유지하며, 네트워크 오류 때문에 데스크톱 앱 시작이 막히지는 않습니다.
- 버전 확인 실패, GitHub API 시간 초과, 업데이트 메타데이터 누락, 다운로드·설치 오류는 `logs/desktop.log`에 기록되며, 설정 페이지나 오른쪽 위 버튼으로 수동 확인할 때 오류 상태가 표시됩니다.

## 자주 묻는 질문

### 실행 후 계속 "Preparing backend..."만 표시될 때

1. `logs/desktop.log`에서 오류 메시지를 확인합니다.
2. `.env` 파일이 있고 설정이 올바른지 확인합니다.
3. 8000-8100 포트가 모두 사용 중이 아닌지 확인합니다. 데스크톱 앱이 이 중 비어 있는 포트를 자동으로 고르므로 `.env`에서 `WEBUI_PORT`를 직접 바꿀 필요는 없습니다.
4. 로그에서 Electron이 기다리는 포트와 백엔드가 실제로 수신하는 포트가 다르게 나오면, 데스크톱 포트 동기화 수정이 들어간 버전으로 먼저 업그레이드하십시오.

### 백엔드 시작 시 ModuleNotFoundError가 날 때

PyInstaller로 패키징할 때 모듈이 빠진 것입니다. Windows와 macOS 백엔드 빌드 스크립트 양쪽에 `--hidden-import`를 함께 추가하고, freeze 결과물에서 실행 시 import 검사를 해야 합니다. 현재 스크립트는 LiteLLM 실행 경로에 필요한 `orjson`을 명시적으로 설치·freeze·검사합니다. 로그에 `No module named 'orjson'`이 있으면 수정된 버전으로 업그레이드해 다시 빌드하십시오. 이미 배포된 폴더에 의존성을 손으로 설치하는 것만으로는 해결되지 않습니다.

로그에 `akshare/file_fold/calendar.json`이 없다고 나오면, 백엔드 freeze 결과물이 AkShare package data를 빠짐없이 수집하지 못한 것입니다. 저장소의 현재 `scripts/build-backend.ps1` 또는 `scripts/build-backend-macos.sh`로 다시 빌드하십시오. 스크립트는 데스크톱 패키지를 만들기 전에 이 파일을 검사하고, 없으면 바로 빌드를 중단합니다.

### UI가 빈 화면으로 뜰 때

`static/index.html`이 있는지 확인하고, 없으면 React UI를 다시 빌드합니다.

### macOS 업그레이드 후 설정 이전

구버전은 실행 중 `.env`, 데이터베이스, 로그를 `.app` 패키지 안에 썼습니다. 새 버전은 Electron 사용자 데이터 폴더를 쓰도록 바뀌었고, 예전 `.app` 패키지 안의 파일에 아직 접근할 수 있으면 한 번만 이전합니다. 이전 규칙은 "대상이 없을 때만 복사"이므로, 사용자가 새 버전에서 이미 저장한 설정을 덮어쓰지 않습니다.

예전 `.app`이 이미 통째로 교체되었다면 패키지 안의 예전 `.env`는 새 버전이 자동으로 되살릴 수 없습니다. 이럴 때는 업그레이드 전에 내보낸 `.env`를 **시스템 설정 -> 설정 백업**(`系统设置 -> 配置备份`)에서 직접 가져오십시오. 한 번 이전하거나 다시 설정하고 나면, 이후 버전은 계속 사용자 데이터 폴더를 쓰므로 `.app`을 교체해도 설정이 사라지지 않습니다.

## 사용자에게 배포하기

Windows 배포 방법은 두 가지입니다.

1. 설치 파일: `apps/dsa-desktop/dist/`의 `daily-stock-analysis-windows-installer-<tag>.exe`를 배포합니다. 사용자는 설치할 때 대상 폴더를 직접 고를 수 있습니다.
2. 무설치 패키지: `apps/dsa-desktop/dist/win-unpacked/` 폴더 전체를 압축해 사용자에게 보냅니다.

`win-unpacked` 무설치 패키지를 쓰는 사용자는 다음만 하면 됩니다.

1. 폴더 압축 풀기
2. `.env`를 편집해 API Key와 종목 목록 설정
3. `Daily Stock Analysis.exe`를 더블클릭해 실행
