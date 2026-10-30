# Tushare 종목 목록 수집 도구 사용 안내

## 기능 개요

Tushare Pro에서 A주(중국 본토 주식), 홍콩 주식, 미국 주식 목록 정보를 받아 로컬에 CSV 파일로 저장합니다.

Tushare는 중국 시장 데이터 서비스이며, 한국 주식 목록은 제공하지 않습니다.

## 빠른 시작

### 1. Token 설정

프로젝트 루트 디렉터리의 `.env` 파일에 Tushare Token을 추가합니다.

```bash
TUSHARE_TOKEN=你的tushare_token
```

(`你的tushare_token`은 "본인의 tushare_token" 자리이므로 실제 Token으로 바꿔 넣습니다.)

> Token 받기: [Tushare Pro](https://tushare.pro/weborder/#/login)에 가입한 뒤 받을 수 있습니다

### 2. 스크립트 실행

```bash
python3 scripts/fetch_tushare_stock_list.py
```

A주 종목 이름의 상태 표시를 바로잡으려면 `--a-rk`를 붙이세요. 스크립트는 `stock_basic`을 기본 출처로 유지하면서, `rt_k`로 `XD`, `XR`, `DR`, `N`, `C` 접두사가 붙은 이름을 채워 넣고 결과를 `data/stock_list_a.csv`에 덮어씁니다.

```bash
python3 scripts/fetch_tushare_stock_list.py --a-rk
```

### 3. 결과 확인

데이터는 `data/` 디렉터리에 저장됩니다.

```
data/
├── stock_list_a.csv       # A주 목록(--a-rk를 쓰면 보정된 이름)
├── stock_list_hk.csv      # 홍콩 주식 목록
├── stock_list_us.csv      # 미국 주식 목록
└── README_stock_list.md   # 데이터 설명 문서
```

## 기능 특징

✅ **자동 페이지 나누기**: 미국 주식 데이터는 페이지를 나눠 자동으로 읽습니다(페이지당 5000건)
✅ **요청 속도 조절**: 요청 사이마다 5~10초를 무작위로 쉽니다
✅ **오류 처리**: 한 시장이 실패해도 다른 시장에는 영향을 주지 않습니다
✅ **진행 상황 표시**: 읽기 진행 상황을 실시간으로 보여 줍니다
✅ **자동 문서화**: 자세한 데이터 설명 문서를 만듭니다

## 시장별 안내

Tushare는 계정의 포인트(积分)에 따라 쓸 수 있는 API가 달라집니다.

| 시장 | API | 필요 포인트 | 데이터 양 |
|------|------|----------|--------|
| A주 | stock_basic | 2000포인트 | 약 5000종목 |
| 홍콩 주식 | hk_basic | 2000포인트 | 약 2000종목 |
| 미국 주식 | us_basic | 체험 120 / 정식 5000 | 약 10000종목 |

## 출력 파일 형식

### A주(stock_list_a.csv)

`--a-rk`로 실행하면 이 파일에 보정된 A주 종목 이름이 기록됩니다.

```csv
ts_code,symbol,name,area,industry,market,exchange,list_date,...
000001.SZ,000001,平安银行,深圳,银行,主板,SZSE,19910403,...
600519.SH,600519,贵州茅台,贵州,白酒,主板,SSE,20010827,...
```

### 홍콩 주식(stock_list_hk.csv)

```csv
ts_code,name,fullname,market,list_date,trade_unit,curr_type,...
00700.HK,腾讯控股,腾讯控股有限公司,主板,20040616,100,HKD,...
00005.HK,汇丰控股,汇丰控股有限公司,主板,19750401,100,HKD,...
```

### 미국 주식(stock_list_us.csv)

```csv
ts_code,name,enname,classify,list_date,...
AAPL,苹果,Apple Inc.,EQT,19801212,...
TSLA,特斯拉,Tesla Inc.,EQT,20100629,...
BABA,阿里巴巴,Alibaba Group,ADR,20140919,...
```

CSV 안의 중국어 값(종목명, 지역, 업종, `主板`(메인보드) 등)은 Tushare가 돌려주는 원본 데이터입니다.

## 사용 예시

### Python으로 데이터 읽기

```python
import pandas as pd

# A주 읽기
a_stocks = pd.read_csv('data/stock_list_a.csv')
print(f"A股数量: {len(a_stocks)}")

# 메인보드 종목만 고르기
main_board = a_stocks[a_stocks['market'] == '主板']
print(f"主板数量: {len(main_board)}")

# 특정 종목 찾기
stock = a_stocks[a_stocks['ts_code'] == '600519.SH']
print(stock[['name', 'industry', 'list_date']])
```

### 종목 자동 완성 인덱스 새로 고침

한 번에 새로 고치는 스크립트를 쓰는 것을 권장합니다. 이 스크립트는 A주를 가져올 때 기본으로 `--a-rk`를 쓰고, 이어서 자동 완성 인덱스를 만들어 동기화합니다.

```bash
pip install -r requirements.txt
python3 scripts/refresh_stock_index.py
```

자동 완성 인덱스를 만들 때는 `pypinyin`으로 중국어 종목 이름의 전체 병음과 병음 첫 글자 필드를 기록합니다. 이 의존성이 없으면 스크립트는 바로 실패합니다. 병음 검색을 지원하지 못하는 불완전한 인덱스가 만들어지지 않게 하기 위해서입니다.

CSV만 따로 업데이트하려면 먼저 데이터를 가져옵니다.

```bash
python3 scripts/fetch_tushare_stock_list.py --a-rk
```

이미 새 CSV가 있고 인덱스만 다시 만들려면:

```bash
python3 scripts/generate_index_from_csv.py --test  # 먼저 테스트
python3 scripts/generate_index_from_csv.py         # 확인한 뒤 생성
```

### 로컬 클라이언트의 최신 인덱스 자동 받기

새 버전 클라이언트는 기본적으로 프로젝트 GitHub `main` 브랜치에서 최신 `apps/dsa-web/public/stocks.index.json`을 읽어 로컬 `data/cache/stocks.index.json`에 캐시합니다. 프런트엔드는 여전히 로컬 `/stocks.index.json`에 접근하므로 GitHub에 직접 교차 출처 요청을 보낼 필요가 없습니다.

원격 인덱스 주소, 확인 주기, 네트워크 타임아웃은 시스템에 내장된 값이며 사용자가 설정할 수 없습니다. 사용자는 켤지 말지만 정하면 됩니다.

```bash
STOCK_INDEX_REMOTE_UPDATE_ENABLED=true
```

기본으로 켜져 있으며, 시스템은 최대 48시간에 한 번 업데이트를 확인합니다. 실행 환경에서 GitHub raw에 접속할 수 없거나, 요청이 타임아웃되거나, 돌아온 내용이 올바른 종목 인덱스가 아니면 기존 캐시를 그대로 씁니다. 원격 캐시가 없으면 앱에 함께 들어 있는 내장 인덱스를 계속 씁니다. 원격 업데이트가 실패해도 WebUI 시작, 종목 자동 완성, 분석 흐름은 막히지 않습니다. 시스템에 내장된 기준만큼 연속으로 실패하면, 현재 프로세스에서는 다음 48시간 주기까지 재시도를 멈춥니다.

## 주의 사항

1. **포인트 조건**: 계정 포인트가 충분한지 확인하세요(A주/홍콩 주식 2000, 미국 주식 체험 120)
2. **요청 제한**: API의 분당 요청 횟수 제한에 주의하세요
3. **데이터 업데이트**: 관리자는 사흘에 한 번 새로 고쳐 저장소에 커밋하는 것을 권장합니다. 로컬 클라이언트는 기본적으로 최대 48시간에 한 번 GitHub `main`의 인덱스 업데이트를 확인합니다. 이후 GitHub Actions workflow로 새로 고침과 PR 제출을 자동화할 수 있습니다
4. **네트워크 연결**: 안정적인 네트워크 연결이 필요합니다

## 자주 묻는 질문

### Q: "未找到 TUSHARE_TOKEN"(TUSHARE_TOKEN을 찾을 수 없음)이라고 나와요
**A**: `.env` 파일에 `TUSHARE_TOKEN=你的token`(본인 Token)을 설정하세요

### Q: "账号积分不足"(계정 포인트 부족)이라고 나와요
**A**:
- A주/홍콩 주식은 2000포인트가 필요합니다
- 미국 주식은 120포인트로 체험, 5000포인트로 정식 권한을 받습니다
- 포인트를 얻는 방법은 https://tushare.pro 에서 확인하세요

### Q: 읽기에 실패하면 어떻게 하나요?
**A**:
1. 네트워크 연결을 확인합니다
2. Token이 맞는지 확인합니다
3. 계정 포인트가 충분한지 확인합니다
4. 현재 스크립트는 자동으로 재시도하지 않습니다. 요청이 한 번 실패하면 오류를 출력하고 끝나므로, 원인을 확인한 뒤 다시 실행하세요

### Q: 데이터는 얼마나 자주 업데이트하나요?
**A**: 관리자가 쓰는 로컬 CSV와 저장소 인덱스는 사흘에 한 번 업데이트해 저장소에 커밋하는 것을 권장합니다. 특별 관리 종목 지정 해제나 이름 변경처럼 영향이 큰 일이 생기면 그때그때 새로 고칠 수 있습니다. 앞으로 GitHub Actions workflow로 새로 고침과 PR 제출을 자동화할 수 있습니다. 일반 로컬 클라이언트는 기본적으로 최대 48시간에 한 번 GitHub `main`에서 최신 인덱스를 확인합니다.

### Q: GitHub raw에 접속할 수 없으면 쓸 수 없나요?
**A**: 아닙니다. 원격 인덱스 업데이트는 best-effort 방식입니다. 실패하면 기존 원격 캐시나 앱에 함께 들어 있는 내장 인덱스를 계속 씁니다. 인덱스를 전혀 쓸 수 없으면 웹 자동 완성은 기존 fallback으로 넘어가며, 종목 코드는 여전히 직접 입력할 수 있습니다.

## 관련 링크

- [Tushare 공식 사이트](https://tushare.pro)
- [Tushare 문서](https://tushare.pro/document/2)
- [포인트 얻는 방법](https://tushare.pro/document/1)
- [API 데이터 디버깅](https://tushare.pro/document/2)
