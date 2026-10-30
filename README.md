# daily_stock_analysis 한국어판

매일 관심종목의 시세와 뉴스를 모아 AI가 분석하고, 그 결과를 디스코드·텔레그램 같은 메신저로 보내 주는 도구예요.

> 이 저장소는 [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis)를 한국 사용자에 맞게 고친 포크입니다.
> - 원작자: ZhuLinsen
> - 라이선스: 원본과 같은 MIT 라이선스 ([LICENSE](LICENSE) 파일은 원본 그대로)
> - 원본 중국어 README: [docs/README_CN.md](docs/README_CN.md)
>
> 이 도구가 내놓는 분석은 공부용 참고 자료예요. 투자 판단과 그 결과의 책임은 본인에게 있습니다.

## 한국어판에서 바뀐 점

- 한국 종목(`.KS`, `.KQ`)은 한국어 회사 이름과 한국어 검색어로 뉴스를 찾아요. 실제로 시험해 보니 삼성전자를 직접 다룬 기사가 0건에서 9건으로 늘었습니다.
- `REPORT_LANGUAGE=ko`로 두면 보고서 생성이 멈추던 오류(`KeyError: 'ko'`)를 고쳤어요.
- 보고서에 나오는 단위와 이름표를 한국어로 바꿨어요.
- 실행 기록(로그)과 설정 설명을 한국어로 옮겼어요.
- 기본값을 바꿨어요.
  - AI 모델: Gemini 무료 등급에서 쓸 수 있는 `gemini-3-flash-preview` (원본 기본값 `gemini-3.1-pro-preview`는 무료 등급에서 쓸 수 없어요)
  - 보고서 언어: 한국어(`ko`)
  - GitHub Actions 자동 실행: 한국 시간 평일 오전 8시

## 빠른 시작 (Windows)

### 1. 준비물

- **Python 3.12**를 설치하세요. 3.14나 3.15에서는 일부 패키지(`tiktoken`, `longbridge`) 설치가 실패해요.
- **Git**이 설치되어 있어야 해요.
- Gemini API 키 (아래 [키 받는 곳](#키-받는-곳) 참고)

### 2. 내려받고 설치하기

PowerShell을 열고 한 줄씩 실행하세요.

```powershell
# 한글이 섞인 파일 때문에 설치가 실패하지 않도록 먼저 실행 (새 창을 열 때마다 다시)
$env:PYTHONUTF8='1'

git clone https://github.com/dkdannyboy/daily_stock_analysis-ko.git
cd daily_stock_analysis-ko

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
```

- 컴퓨터에 파이썬이 여러 개 깔려 있으면 `python -m venv .venv` 대신 `py -3.12 -m venv .venv`를 쓰세요.
- `.venv\Scripts\activate`에서 "스크립트를 실행할 수 없습니다" 오류가 나면 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`를 한 번 실행한 뒤 다시 해 보세요.

### 3. 설정 파일 만들기

```powershell
copy .env.example .env
notepad .env
```

`.env` 파일에서 아래 항목을 채우고 저장하세요.

| 항목 | 넣을 값 | 꼭 필요? |
|---|---|---|
| `GEMINI_API_KEY` | Gemini API 키 | 필요 |
| `STOCK_LIST` | 관심종목, 쉼표로 구분 (예: `005930.KS,000660.KS`) | 필요 |
| `TAVILY_API_KEYS` | Tavily 키. 넣으면 뉴스 검색 결과가 훨씬 좋아져요 | 선택 |
| `DISCORD_WEBHOOK_URL` | 디스코드 웹후크 주소. 줄 맨 앞의 `#`을 지우고 넣으세요 | 선택 |

한국 종목은 종목번호 뒤에 시장을 붙여요. 코스피는 `.KS`, 코스닥은 `.KQ`입니다. 예를 들어 삼성전자는 `005930.KS`예요.

`.env`에는 진짜 키가 들어가니 다른 사람에게 보내거나 GitHub에 올리지 마세요.

### 4. 실행하기

```powershell
python main.py --stocks 005930.KS --no-market-review --force-run
```

- `--stocks 005930.KS`: 이번에는 삼성전자 한 종목만 분석해요 (`.env`의 `STOCK_LIST`보다 우선).
- `--no-market-review`: 시장 전체 리뷰는 건너뛰어요.
- `--force-run`: 주말이나 휴장일에도 거래일 확인을 건너뛰고 실행해요.

끝나면 디스코드를 설정한 경우 메시지가 오고, `reports` 폴더에 `report_날짜.md` 파일이 생겨요. 다른 옵션은 `python main.py --help`로 볼 수 있어요.

### Mac / Linux

`$env:PYTHONUTF8='1'`은 필요 없고, 나머지는 명령만 조금 달라요.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 키 받는 곳

### Gemini (필수)

1. [aistudio.google.com/apikey](https://aistudio.google.com/apikey)에 구글 계정으로 들어가요.
2. API 키를 만들고 복사해 `GEMINI_API_KEY`에 넣어요.

- **결제 수단은 등록하지 마세요.** 등록하지 않으면 무료 등급으로만 쓰여 요금이 나가지 않아요.
- 무료 등급으로 쓰면 보낸 내용이 구글 서비스 개선에 쓰일 수 있어요. 개인 정보는 넣지 마세요.

### Tavily (선택, 뉴스 검색)

1. [tavily.com](https://tavily.com)에서 **Start for free**를 누르고 가입해요.
2. 요금제 선택 화면에서 **Continue on Free**를 고르세요. 한 달에 1,000크레딧까지 무료예요.
3. 대시보드의 API 키를 복사해 `TAVILY_API_KEYS`에 넣어요.

### 디스코드 웹후크 (선택, 결과 받기)

1. 결과를 받을 디스코드 서버에서 **서버 설정 → 연동 → 웹후크**로 들어가요.
2. **새 웹후크**를 만들고 보낼 채널을 고른 뒤 **웹후크 URL 복사**를 눌러요.
3. 복사한 주소를 `DISCORD_WEBHOOK_URL`에 넣어요.

## GitHub Actions로 매일 아침 8시에 자동 실행하기

내 컴퓨터를 켜 두지 않아도 GitHub가 매일 대신 실행해 줘요.

1. 이 저장소 오른쪽 위의 **Fork**를 눌러 내 계정으로 복사해요.
2. 내 포크에서 **Settings → Secrets and variables → Actions → New repository secret**으로 아래 값을 하나씩 등록해요.
   - `GEMINI_API_KEY` (필수)
   - `STOCK_LIST` (필수, 예: `005930.KS,000660.KS`)
   - `TAVILY_API_KEYS` (선택)
   - `DISCORD_WEBHOOK_URL` (선택)
3. 내 포크의 **Actions** 탭으로 가서 워크플로 사용 버튼(I understand my workflows, go ahead and enable them)을 눌러 켜요.
4. 바로 확인하고 싶으면 Actions 탭에서 **매일 주식 분석 → Run workflow**를 눌러요. 주말에 시험할 때는 `강제 실행` 칸을 체크하세요.

알아 두면 좋은 점:

- 실행 시각은 한국 시간 월~금 오전 8시예요(`cron: '0 23 * * 0-4'`, UTC 기준 일~목 23시). GitHub 사정으로 몇 분에서 수십 분 늦게 시작될 수 있어요.
- 휴장일에는 분석을 건너뛰어요. 장이 열리기 전이라 전 거래일 데이터로 분석해요.
- 보고서 언어(`ko`)와 AI 모델(`gemini-3-flash-preview`)은 기본으로 설정되어 있어요. 바꾸고 싶으면 **Variables** 탭에 `REPORT_LANGUAGE`, `GEMINI_MODEL`을 등록하면 됩니다.
- 시장 전체 리뷰는 기본이 중국 시장(`cn`)이에요. 한국 시장으로 보려면 Variables에 `MARKET_REVIEW_REGION`을 `kr`로 등록하세요.
- 공개 저장소에 60일 동안 아무 변화가 없으면 GitHub가 예약 실행을 멈춰요. 그때는 Actions 탭에서 다시 켜면 됩니다.

## 더 알아보기

더 자세한 설정(다른 AI 모델, 다른 알림 채널, 웹 화면 등)은 원본 문서를 참고하세요. 대부분 중국어나 영어로 되어 있어요.

- [원본 중국어 README](docs/README_CN.md)
- [영어 README](docs/README_EN.md)
- [전체 설정 안내 (중국어)](docs/full-guide.md)
- 모든 설정 항목과 한국어 설명: [.env.example](.env.example)

## 라이선스

MIT 라이선스예요. 원작자 ZhuLinsen의 저작권 표시가 담긴 [LICENSE](LICENSE) 파일을 그대로 유지하고 있어요.
