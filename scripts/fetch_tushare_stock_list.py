#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tushare 종목 목록 받기 스크립트

Tushare Pro에서 중국 A주, 홍콩, 미국 주식 목록을 받아 CSV 파일로 저장합니다

사용법:
    python3 scripts/fetch_tushare_stock_list.py
    python3 scripts/fetch_tushare_stock_list.py --a-rk

필요 환경:
    - .env에 TUSHARE_TOKEN 설정 필요
    - tushare 설치 필요: pip install tushare
    - 계정 포인트 조건:
        * A주/홍콩 주식: 2000포인트
        * 미국 주식: 120포인트 체험, 5000포인트 정식 권한

출력 파일:
    - data/stock_list_a.csv      A주 목록 (--a-rk 사용 시 수정된 이름으로 덮어씀)
    - data/stock_list_hk.csv     홍콩 주식 목록
    - data/stock_list_us.csv     미국 주식 목록
    - data/README_stock_list.md  데이터 설명 문서
"""

import argparse
import os
import sys
import time
import random
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

import pandas as pd
from dotenv import load_dotenv

# 프로젝트 루트 폴더를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import tushare as ts
except ImportError:
    print("[오류] tushare 라이브러리가 설치되어 있지 않습니다")
    print("다음을 실행하세요: pip install tushare")
    sys.exit(1)


# 설정
load_dotenv()

TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN')
OUTPUT_DIR = Path(__file__).parent.parent / "data"
PAGE_SIZE = 5000  # 미국 주식 한 페이지당 읽을 개수 (API 최대 6000, 여유 있게 5000)
SLEEP_MIN = 5     # 최소 대기 시간(초)
SLEEP_MAX = 10    # 최대 대기 시간(초)
A_RK_BATCH_SIZE = 200
A_RK_FIELDS = "ts_code,name,close,pre_close,trade_time"
A_RK_NAME_PREFIX_RE = re.compile(r"^(XD|XR|DR|N|C)")


def get_tushare_api() -> Optional[ts.pro_api]:
    """
    Tushare API 객체 가져오기

    Returns:
        Tushare API 객체, 실패하면 None
    """
    if not TUSHARE_TOKEN:
        print("[오류] TUSHARE_TOKEN을 찾을 수 없습니다")
        print(".env 파일에 설정하세요: TUSHARE_TOKEN=내_토큰")
        return None

    try:
        api = ts.pro_api(TUSHARE_TOKEN)
        # 연결 테스트
        api.trade_cal(exchange='SSE', start_date='20240101', end_date='20240101')
        print("✓ Tushare API 연결 성공")
        return api
    except Exception as e:
        print(f"[오류] Tushare API 연결 실패: {e}")
        print("다음을 확인하세요:")
        print("  1. TUSHARE_TOKEN이 맞는지")
        print("  2. 계정 포인트가 충분한지 (A주/홍콩 주식은 2000포인트 필요)")
        return None


def random_sleep(min_seconds: int = SLEEP_MIN, max_seconds: int = SLEEP_MAX):
    """
    요청이 너무 잦지 않도록 무작위로 잠시 쉼

    Args:
        min_seconds: 최소 대기 시간
        max_seconds: 최대 대기 시간
    """
    sleep_time = random.uniform(min_seconds, max_seconds)
    print(f"  ⏱  {sleep_time:.1f}초 쉬는 중...")
    time.sleep(sleep_time)


def fetch_a_stock_list(api: ts.pro_api) -> Optional[pd.DataFrame]:
    """
    A주 목록 받기

    API: stock_basic
    한도: 한 번에 최대 6000행 (A주 전체 시장 포함)

    Args:
        api: Tushare API 객체

    Returns:
        A주 데이터 DataFrame, 실패하면 None
    """
    print("\n[1/3] A주 목록 받는 중...")

    try:
        # 정상 상장된 종목 전체 받기
        df = api.stock_basic(
            exchange='',        # 빈 값: 모든 거래소
            list_status='L',    # L: 상장, D: 상장폐지, P: 상장정지
            fields='ts_code,symbol,name,area,industry,fullname,enname,cnspell,market,exchange,curr_type,list_status,list_date,delist_date,is_hs,act_name,act_ent_type'
        )

        if df is not None and len(df) > 0:
            print(f"✓ A주 목록 받기 성공, 총 {len(df)}개 종목")
            print("  - 거래소별 분포:")
            for exchange, count in df['exchange'].value_counts().items():
                print(f"    {exchange}: {count}개")
            return df
        else:
            print("[오류] A주 데이터가 비어 있습니다")
            return None

    except Exception as e:
        print(f"[오류] A주 목록 받기 실패: {e}")
        return None


def should_fix_a_stock_name(name: str) -> bool:
    """
    A주 종목 이름이 고쳐야 하는 상태 표시 이름인지 판단합니다.

    주로 신규 상장, 권리락·배당락 등의 접두어를 다룹니다:
    XD / XR / DR / N / C
    """
    if name is None:
        return False

    text = str(name).strip()
    if not text or text.lower() in {"nan", "none"}:
        return False

    return bool(A_RK_NAME_PREFIX_RE.match(text))


def chunk_list(items: List[str], chunk_size: int) -> List[List[str]]:
    """리스트를 정해진 크기로 나눕니다."""
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def fetch_rt_k_names(api: ts.pro_api, ts_codes: List[str]) -> Dict[str, str]:
    """
    rt_k가 돌려주는 종목 이름을 묶어서 받습니다.

    공식 문서 참고:
    https://tushare.pro/wctapi/documents/372.md

    rt_k는 A주 실시간 일봉 API로, 종목 코드나 코드 와일드카드로
    실시간 일봉 시세를 받을 수 있습니다. 이 스크립트는 이름을 채우는 보조 출처로만 써서
    stock_basic이 돌려준 일시적 거래 상태 접두어가 붙은 이름을 고칩니다.
    """
    if not ts_codes:
        return {}

    name_map: Dict[str, str] = {}
    batches = chunk_list(ts_codes, A_RK_BATCH_SIZE)

    print(f"\n[rt_k] 고칠 종목 수: {len(ts_codes)}, {len(batches)}번에 나눠 받는 중...")

    for index, batch in enumerate(batches, start=1):
        ts_code_param = ",".join(batch)
        print(f"  [rt_k] {index}/{len(batches)}번째 묶음: {len(batch)}개 종목")

        try:
            df = api.rt_k(ts_code=ts_code_param, fields=A_RK_FIELDS)
        except Exception as e:
            print(f"  [경고] rt_k {index}번째 묶음 받기 실패: {e}")
            continue

        if df is None or len(df) == 0:
            print(f"  [경고] rt_k {index}번째 묶음에 돌아온 데이터가 없습니다")
            continue

        for _, row in df.iterrows():
            code_value = row.get("ts_code", "")
            name_value = row.get("name", "")

            if pd.isna(code_value) or pd.isna(name_value):
                continue

            code = str(code_value).strip()
            name = str(name_value).strip()
            if code and name and code.lower() not in {"nan", "none"} and name.lower() not in {"nan", "none"}:
                name_map[code] = name

        if index < len(batches):
            random_sleep(1, 2)

    print(f"[rt_k] 이름 매핑 {len(name_map)}개 받기 성공")
    return name_map


def fix_a_stock_names_with_rt_k(api: ts.pro_api, df: pd.DataFrame) -> pd.DataFrame:
    """
    rt_k로 A주 종목 이름을 고칩니다.

    이름에 XD / XR / DR / N / C 접두어가 붙은 종목만 고칩니다.
    """
    if df is None or len(df) == 0:
        return df

    if "name" not in df.columns or "ts_code" not in df.columns:
        print("[경고] A주 데이터에 ts_code/name 열이 없어 rt_k 이름 수정을 건너뜁니다")
        return df

    fix_mask = df["name"].astype(str).map(should_fix_a_stock_name)
    fix_df = df.loc[fix_mask, ["ts_code", "name"]].copy()

    if fix_df.empty:
        print("[rt_k] 고칠 A주 종목 이름이 없습니다")
        return df

    ts_codes = fix_df["ts_code"].astype(str).tolist()
    print(f"[rt_k] 고칠 A주 종목 {len(ts_codes)}개 발견:")
    print("  " + ", ".join(ts_codes[:20]) + (" ..." if len(ts_codes) > 20 else ""))

    name_map = fetch_rt_k_names(api, ts_codes)
    if not name_map:
        print("[경고] rt_k에서 쓸 수 있는 이름이 오지 않아 원래 A주 이름을 그대로 둡니다")
        return df

    fixed_df = df.copy()
    fixed_count = 0
    for code, new_name in name_map.items():
        if not new_name:
            continue
        match_index = fixed_df.index[fixed_df["ts_code"].astype(str) == code]
        if len(match_index) == 0:
            continue

        old_name = str(fixed_df.loc[match_index[0], "name"])
        if old_name != new_name:
            fixed_df.loc[match_index[0], "name"] = new_name
            fixed_count += 1
            print(f"  ✓ {code}: {old_name} -> {new_name}")

    print(f"[rt_k] A주 이름 수정 완료, 총 {fixed_count}개 종목 수정")
    return fixed_df


def fetch_hk_stock_list(api: ts.pro_api) -> Optional[pd.DataFrame]:
    """
    홍콩 주식 목록 받기

    API: hk_basic
    한도: 한 번에 거래 중인 홍콩 주식 전체를 받을 수 있음

    Args:
        api: Tushare API 객체

    Returns:
        홍콩 주식 데이터 DataFrame, 실패하면 None
    """
    print("\n[2/3] 홍콩 주식 목록 받는 중...")

    try:
        # 정상 상장된 홍콩 주식 전체 받기
        df = api.hk_basic(
            list_status='L'    # L: 상장, D: 상장폐지
        )

        if df is not None and len(df) > 0:
            print(f"✓ 홍콩 주식 목록 받기 성공, 총 {len(df)}개 종목")
            return df
        else:
            print("[오류] 홍콩 주식 데이터가 비어 있습니다")
            return None

    except Exception as e:
        print(f"[오류] 홍콩 주식 목록 받기 실패: {e}")
        return None


def fetch_us_stock_list(api: ts.pro_api) -> Optional[pd.DataFrame]:
    """
    미국 주식 목록 받기 (페이지 나눠 읽기)

    API: us_basic
    한도: 한 번에 최대 6000개라 페이지를 나눠 받아야 함

    Args:
        api: Tushare API 객체

    Returns:
        미국 주식 데이터 DataFrame, 실패하면 None
    """
    print("\n[3/3] 미국 주식 목록 받는 중 (페이지 나눠 읽기)...")

    all_data = []
    offset = 0
    page = 1

    try:
        while True:
            print(f"  {page}페이지 (offset={offset})...")

            df = api.us_basic(
                offset=offset,
                limit=PAGE_SIZE
            )

            if df is None or len(df) == 0:
                print(f"  ✓ {page}페이지에 데이터가 없어 읽기 완료")
                break

            all_data.append(df)
            print(f"  ✓ {page}페이지에서 {len(df)}개 종목 받음")

            # 받은 데이터가 페이지 크기보다 적으면 마지막 페이지라는 뜻
            if len(df) < PAGE_SIZE:
                break

            offset += PAGE_SIZE
            page += 1

            # 무작위로 쉬기 (마지막 페이지는 쉬지 않음)
            random_sleep()

        if all_data:
            result_df = pd.concat(all_data, ignore_index=True)
            print(f"✓ 미국 주식 목록 받기 성공, 총 {len(result_df)}개 종목 ({page}페이지)")

            # 분류별 집계
            if 'classify' in result_df.columns:
                print("  - 분류별 분포:")
                for classify, count in result_df['classify'].value_counts().items():
                    print(f"    {classify}: {count}개")

            return result_df
        else:
            print("[오류] 미국 주식 데이터가 비어 있습니다")
            return None

    except Exception as e:
        print(f"[오류] 미국 주식 목록 받기 실패: {e}")
        return None


def save_to_csv(df: pd.DataFrame, filename: str, market_name: str) -> bool:
    """
    데이터를 CSV 파일로 저장

    Args:
        df: 데이터 DataFrame
        filename: 파일 이름
        market_name: 시장 이름 (로그용)

    Returns:
        저장 성공 여부
    """
    if df is None or len(df) == 0:
        print(f"[건너뜀] {market_name} 데이터가 비어 있어 파일을 저장하지 않습니다")
        return False

    try:
        output_path = OUTPUT_DIR / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        df.to_csv(output_path, index=False, encoding='utf-8-sig')

        file_size = output_path.stat().st_size / 1024  # KB
        print(f"✓ {market_name} 데이터 저장 완료: {output_path} ({file_size:.2f} KB)")
        return True

    except Exception as e:
        print(f"[오류] {market_name} 데이터 저장 실패: {e}")
        return False


def generate_data_documentation(
    a_df: Optional[pd.DataFrame],
    hk_df: Optional[pd.DataFrame],
    us_df: Optional[pd.DataFrame],
    a_filename: str = "stock_list_a.csv",
    a_title: str = "A股列表"
):
    """
    데이터 설명 문서 만들기

    Args:
        a_df: A주 데이터
        hk_df: 홍콩 주식 데이터
        us_df: 미국 주식 데이터
    """
    doc_path = OUTPUT_DIR / "README_stock_list.md"

    content = f"""# Tushare 종목 목록 데이터 설명

> 데이터 출처: [Tushare Pro](https://tushare.pro)
> 생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 파일 설명

| 파일 | 설명 | 항목 수 |
|------|------|--------|
| `{a_filename}` | {a_title} | {len(a_df) if a_df is not None else 0} |
| `stock_list_hk.csv` | 홍콩 주식 목록 | {len(hk_df) if hk_df is not None else 0} |
| `stock_list_us.csv` | 미국 주식 목록 | {len(us_df) if us_df is not None else 0} |

---

## A주 데이터 ({a_filename})

### 데이터 API
- **API 이름**: `stock_basic`
- **데이터 권한**: 2000포인트부터, 분당 50회 요청
- **데이터 한도**: 한 번에 최대 6000행 (A주 전체 시장 포함)

### 필드 설명

| 필드 이름 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| ts_code | str | TS 코드 | 000001.SZ |
| symbol | str | 종목 코드 | 000001 |
| name | str | 종목 이름 | 平安银行 |
| area | str | 지역 | 深圳 |
| industry | str | 업종 | 银行 |
| fullname | str | 종목 정식 이름 | 平安银行股份有限公司 |
| enname | str | 영문 정식 이름 | Ping An Bank Co., Ltd. |
| cnspell | str | 병음 약자 | PAYH |
| market | str | 시장 구분 | 主板/创业板/科创板/CDR |
| exchange | str | 거래소 코드 | SSE 상하이/SZSE 선전/BSE 베이징 |
| curr_type | str | 거래 통화 | CNY |
| list_status | str | 상장 상태 | L 상장/D 상장폐지/P 상장정지 |
| list_date | str | 상장일 | 19910403 |
| delist_date | str | 상장폐지일 | - |
| is_hs | str | 후강퉁·선강퉁 대상 여부 | N 아님/H 후구퉁/S 선구퉁 |
| act_name | str | 실제 지배자 이름 | - |
| act_ent_type | str | 실제 지배자 기업 성격 | - |

### 데이터 예시
```csv
ts_code,symbol,name,area,industry,fullname,enname,cnspell,market,exchange,curr_type,list_status,list_date,delist_date,is_hs,act_name,act_ent_type
000001.SZ,000001,平安银行,深圳,银行,平安银行股份有限公司,Ping An Bank Co., Ltd.,PAYH,主板,SZSE,CNY,L,19910403,,S,,
000002.SZ,000002,万科A,深圳,全国地产,万科企业股份有限公司,China Vanke Co., Ltd.,ZKA,主板,SZSE,CNY,L,19910129,,S,,
```

---

## 홍콩 주식 데이터 (stock_list_hk.csv)

### 데이터 API
- **API 이름**: `hk_basic`
- **데이터 권한**: 최소 2000포인트가 있어야 호출 가능
- **데이터 한도**: 한 번에 거래 중인 홍콩 주식 목록 전체를 받을 수 있음

### 필드 설명

| 필드 이름 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| ts_code | str | TS 코드 | 00001.HK |
| name | str | 종목 약칭 | 长和 |
| fullname | str | 회사 정식 이름 | 长江和记实业有限公司 |
| enname | str | 영문 이름 | CK Hutchison Holdings Ltd. |
| cn_spell | str | 병음 | ZH |
| market | str | 시장 구분 | 主板/创业板 |
| list_status | str | 상장 상태 | L 상장/D 상장폐지/P 상장정지 |
| list_date | str | 상장일 | 19720731 |
| delist_date | str | 상장폐지일 | - |
| trade_unit | float | 거래 단위 | 1000 |
| isin | str | ISIN 코드 | KYG217651051 |
| curr_type | str | 통화 코드 | HKD |

### 데이터 예시
```csv
ts_code,name,fullname,enname,cn_spell,market,list_status,list_date,delist_date,trade_unit,isin,curr_type
00001.HK,长和,长江和记实业有限公司,CK Hutchison Holdings Ltd.,ZH,主板,L,19720731,,1000,KYG217651051,HKD
00002.HK,中电控股,中华电力有限公司,CLP Holdings Ltd.,ZDKG,主板,L,19860125,,1000,HK0002007356,HKD
```

---

## 미국 주식 데이터 (stock_list_us.csv)

### 데이터 API
- **API 이름**: `us_basic`
- **데이터 권한**: 120포인트로 체험, 5000포인트부터 정식 권한
- **데이터 한도**: 한 번에 최대 6000개, 페이지 나눠 받기 가능

### 필드 설명

| 필드 이름 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| ts_code | str | 미국 주식 코드 | AAPL |
| name | str | 중국어 이름 | 苹果 |
| enname | str | 영문 이름 | Apple Inc. |
| classify | str | 분류 | ADR/GDR/EQT |
| list_date | str | 상장일 | 19801212 |
| delist_date | str | 상장폐지일 | - |

### 분류 설명
- **ADR**: 미국 예탁증서（American Depositary Receipt）
- **GDR**: 글로벌 예탁증서（Global Depositary Receipt）
- **EQT**: 보통주（Equity）

### 데이터 예시
```csv
ts_code,name,enname,classify,list_date,delist_date
AAPL,苹果,Apple Inc.,EQT,19801212,
TSLA,特斯拉,Tesla Inc.,EQT,20100629,
BABA,阿里巴巴,Alibaba Group Holding Ltd.,ADR,20140919,
```

---

## 사용법

### 데이터 읽기

```python
import pandas as pd

# A주 데이터 읽기
a_stocks = pd.read_csv('data/{a_filename}')

# 홍콩 주식 데이터 읽기
hk_stocks = pd.read_csv('data/stock_list_hk.csv')

# 미국 주식 데이터 읽기
us_stocks = pd.read_csv('data/stock_list_us.csv')
```

### 코드 형식 설명

**A주 코드 형식**:
- 상하이: `600000.SH`(메인보드), `688xxx.SH`(과창판), `900xxx.SH`(B주)
- 선전: `000001.SZ`(메인보드), `300xxx.SZ`(창업판), `200xxx.SZ`(B주)
- 베이징거래소: `8xxxxx.BJ`、`4xxxxx.BJ`、`920xxx.BJ`

**홍콩 주식 코드 형식**:
- 형식: `xxxxx.HK` (숫자 5자리 + .HK)
- 예시: `00700.HK` (텐센트)

**미국 주식 코드 형식**:
- 형식: 영문 코드 (접미어 없음)
- 예시: `AAPL`(애플), `TSLA`(테슬라)

---

## 주의할 점

1. **데이터 갱신**: 정기적으로 갱신하세요 (예: 한 달에 한 번)
2. **포인트 조건**:
   - A주/홍콩 주식: 2000포인트 필요
   - 미국 주식: 120포인트 체험, 5000포인트 정식 권한
3. **요청 제한**: API의 분당 요청 횟수 제한에 주의하세요
4. **데이터 범위**: 기본 정보만 들어 있습니다. 더 필요한 데이터는 Tushare 공식 문서를 참고하세요

---

## 관련 링크

- [Tushare 공식 사이트](https://tushare.pro)
- [Tushare 문서](https://tushare.pro/document/2)
- [포인트 얻는 방법](https://tushare.pro/document/1)
- [API 데이터 테스트](https://tushare.pro/document/2)
"""

    try:
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ 데이터 설명 문서 생성 완료: {doc_path}")
    except Exception as e:
        print(f"[오류] 설명 문서 생성 실패: {e}")


def build_arg_parser() -> argparse.ArgumentParser:
    """명령줄 인자를 만듭니다."""
    parser = argparse.ArgumentParser(description="Tushare 종목 목록 받기 도구")
    parser.add_argument(
        "--a-rk",
        action="store_true",
        help="rt_k로 A주 이름 중 XD/XR/DR/N/C 접두어가 붙은 것을 고쳐 stock_list_a.csv에 덮어씁니다",
    )
    return parser


def main(argv: Optional[List[str]] = None):
    """메인 함수"""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    print("=" * 60)
    print("Tushare 종목 목록 받기 도구")
    print("=" * 60)
    print(f"[정보] A주 이름 수정 모드: {'켜짐' if args.a_rk else '꺼짐'}")

    # 1. API 객체 가져오기
    api = get_tushare_api()
    if not api:
        return 1

    # 2. A주 데이터 받기
    a_df = fetch_a_stock_list(api)
    if a_df is not None:
        a_filename = 'stock_list_a.csv'
        a_title = 'A股列表'
        a_market_name = 'A股'

        if args.a_rk:
            a_df = fix_a_stock_names_with_rt_k(api, a_df)
            a_title = 'A股列表（修正后）'

        save_to_csv(a_df, a_filename, a_market_name)

    # 3. 홍콩 주식 데이터 받기
    random_sleep()  # 잠시 쉰 뒤 홍콩 주식 받기
    hk_df = fetch_hk_stock_list(api)
    if hk_df is not None:
        save_to_csv(hk_df, 'stock_list_hk.csv', '홍콩 주식')

    # 4. 미국 주식 데이터 받기 (페이지 나눔)
    random_sleep()  # 잠시 쉰 뒤 미국 주식 받기
    us_df = fetch_us_stock_list(api)
    if us_df is not None:
        save_to_csv(us_df, 'stock_list_us.csv', '미국 주식')

    # 5. 데이터 설명 문서 만들기
    print("\n데이터 설명 문서 만드는 중...")
    a_filename = 'stock_list_a.csv'
    a_title = 'A股列表（修正后）' if args.a_rk else 'A股列表'
    generate_data_documentation(a_df, hk_df, us_df, a_filename=a_filename, a_title=a_title)

    # 6. 요약
    print("\n" + "=" * 60)
    print("작업 완료!")
    print("=" * 60)

    total_count = 0
    if a_df is not None:
        total_count += len(a_df)
        print(f"  ✓ A주: {len(a_df)}개")
    if hk_df is not None:
        total_count += len(hk_df)
        print(f"  ✓ 홍콩 주식: {len(hk_df)}개")
    if us_df is not None:
        total_count += len(us_df)
        print(f"  ✓ 미국 주식: {len(us_df)}개")

    print(f"\n합계: {total_count}개 종목")
    print(f"저장 폴더: {OUTPUT_DIR}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n[중단] 사용자가 취소했습니다")
        sys.exit(1)
    except Exception as e:
        print(f"\n[오류] 예상하지 못한 예외: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
