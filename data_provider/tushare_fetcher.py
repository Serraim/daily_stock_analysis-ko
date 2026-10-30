# -*- coding: utf-8 -*-
"""
===================================
TushareFetcher - 예비 데이터 소스 1 (Priority 2)
===================================

데이터 출처: Tushare Pro API
특징: Token 필요, 요청 횟수 제한 있음
장점: 데이터 품질이 높고 API가 안정적

요청 속도 제어 전략:
1. '분당 호출 카운터' 구현
2. 무료 한도(분당 80회)를 넘으면 다음 1분까지 강제로 대기
3. tenacity로 점점 간격을 늘려 재시도
"""

import json as _json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any

import pandas as pd
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .base import BaseFetcher, DataFetchError, RateLimitError, STANDARD_COLUMNS,is_bse_code, is_st_stock, is_kc_cy_stock, normalize_stock_code, _is_hk_market
from .realtime_types import UnifiedRealtimeQuote, ChipDistribution
from src.config import get_config
import os
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


# ETF code prefixes by exchange
# Shanghai: 51xxxx, 52xxxx, 56xxxx, 58xxxx
# Shenzhen: 15xxxx, 16xxxx, 18xxxx
_ETF_SH_PREFIXES = ('51', '52', '56', '58')
_ETF_SZ_PREFIXES = ('15', '16', '18')
_ETF_ALL_PREFIXES = _ETF_SH_PREFIXES + _ETF_SZ_PREFIXES


def _is_etf_code(stock_code: str) -> bool:
    """
    Check if the code is an ETF fund code.

    ETF code ranges:
    - Shanghai ETF: 51xxxx, 52xxxx, 56xxxx, 58xxxx
    - Shenzhen ETF: 15xxxx, 16xxxx, 18xxxx
    """
    code = normalize_stock_code(stock_code)
    return code.startswith(_ETF_ALL_PREFIXES) and len(code) == 6


def _is_us_code(stock_code: str) -> bool:
    """
    미국 주식 코드인지 판단
    
    미국 주식 코드 규칙:
    - 대문자 1-5개, 예: 'AAPL', 'TSLA'
    - '.'이 들어갈 수 있음, 예: 'BRK.B'
    """
    code = stock_code.strip().upper()
    return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))


def _resolve_tushare_http_url() -> Optional[str]:
    """``TUSHARE_HTTP_URL`` 환경 변수를 읽고 기본 검사를 함.

    - 비었거나 / 공백뿐이거나 / 설정 안 됨 → ``None`` 반환, 호출하는 쪽은 공식 기본 주소를 그대로 씀.
    - 설정돼 있으면 앞뒤 공백을 지워 반환하고, ``http://`` 또는 ``https://``로 시작하는지 검사함.
      호스트 이름만(예: ``api.tushare.pro``) 잘못 넣으면 ``requests``가 이를
      상대 경로로 보고 요청이 실패하기 때문.
    """
    raw = os.getenv("TUSHARE_HTTP_URL")
    if not raw:
        return None
    url = raw.strip()
    if not url:
        return None
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(
            "TUSHARE_HTTP_URL은 http:// 또는 https://로 시작해야 합니다, "
            f"현재 값: {url!r}"
        )
    return url


class _TushareHttpClient:
    """Lightweight Tushare Pro client that does not require the tushare SDK."""

    def __init__(self, token: str, timeout: int = 30, api_url: str = "http://api.tushare.pro") -> None:
        self._token = token
        self._timeout = timeout
        self._api_url = api_url

    def query(self, api_name: str, fields: str = "", **kwargs) -> pd.DataFrame:
        req_params = {
            "api_name": api_name,
            "token": self._token,
            "params": kwargs,
            "fields": fields,
        }
        res = requests.post(self._api_url, json=req_params, timeout=self._timeout)
        if res.status_code != 200:
            raise Exception(f"Tushare API HTTP {res.status_code}")

        result = _json.loads(res.text)
        if result.get("code") != 0:
            raise Exception(result.get("msg") or f"Tushare API error code {result.get('code')}")

        data = result.get("data") or {}
        columns = data.get("fields") or []
        items = data.get("items") or []
        return pd.DataFrame(items, columns=columns)

    def __getattr__(self, api_name: str):
        if api_name.startswith("_"):
            raise AttributeError(api_name)

        def caller(**kwargs) -> pd.DataFrame:
            return self.query(api_name, **kwargs)

        return caller


class TushareFetcher(BaseFetcher):
    """
    Tushare Pro 데이터 소스 구현
    
    우선순위: 2
    데이터 출처: Tushare Pro API
    
    핵심 전략:
    - 분당 호출 카운터로 한도 초과 방지
    - 분당 80회를 넘으면 강제로 대기
    - 실패하면 점점 간격을 늘려 재시도
    
    한도 안내(Tushare 무료 사용자):
    - 분당 최대 80회 요청
    - 하루 최대 500회 요청
    """
    
    name = "TushareFetcher"
    priority = int(os.getenv("TUSHARE_PRIORITY", "2"))  # 기본 우선순위, __init__에서 설정에 따라 바뀜

    def __init__(self, rate_limit_per_minute: int = 80):
        """
        TushareFetcher 초기화

        Args:
            rate_limit_per_minute: 분당 최대 요청 수(기본 80, Tushare 무료 한도)
        """
        self.rate_limit_per_minute = rate_limit_per_minute
        self._call_count = 0  # 이번 1분 동안의 호출 횟수
        self._minute_start: Optional[float] = None  # 현재 카운트 구간 시작 시각
        self._api: Optional[object] = None  # Tushare API 인스턴스
        self.date_list: Optional[List[str]] = None  # 거래일 목록 캐시(역순, 최신 날짜가 먼저)
        self._date_list_end: Optional[str] = None  # 캐시 기준 마감일, 날짜가 바뀌면 새로 고칠 때 씀

        # API 초기화 시도
        self._init_api()

        # API 초기화 결과에 따라 우선순위 조정
        self.priority = self._determine_priority()
    
    def _init_api(self) -> None:
        """
        Tushare API 초기화

        Token이 설정되지 않으면 이 데이터 소스는 쓸 수 없음.
        여기서는 내장 HTTP client를 직접 써서 tushare SDK에 꼭 의존하지 않게 함.
        그래서 Docker / PyInstaller / 여러 가상 환경에서 패키지가 빠져 초기화가 실패하는 일을 줄임.
        """
        config = get_config()

        if not config.tushare_token:
            logger.warning("Tushare Token이 설정되지 않아 이 데이터 소스를 쓸 수 없음")
            return

        try:
            self._api = self._build_api_client(config.tushare_token)
            logger.info("Tushare API 초기화 성공")
        except Exception as e:
            logger.error(f"Tushare API 초기화 실패: {e}")
            self._api = None

    def _build_api_client(self, token: str) -> _TushareHttpClient:
        """
        Build a lightweight Tushare Pro client over direct HTTP requests.

        The project already normalizes all Pro calls through the same request
        contract, so we do not need the official tushare SDK during runtime.

        ``TUSHARE_HTTP_URL`` 환경 변수로 요청을 직접 만든 서버나 호환되는 외부
        엔드포인트로 보낼 수 있음. ``api.tushare.pro``에 바로 닿지 않을 때 미러/게이트웨이로 바꾸기 편함.
        비우거나 설정하지 않으면 공식 기본 주소를 그대로 쓰고, 동작은 이전 버전과 똑같음.
        """
        api_url = _resolve_tushare_http_url()
        if api_url:
            logger.info("Tushare 사용자 지정 접속 주소 사용: %s", api_url)
            client = _TushareHttpClient(token=token, api_url=api_url)
        else:
            client = _TushareHttpClient(token=token)
        logger.debug("Tushare API client configured for direct HTTP calls")
        return client

    def _determine_priority(self) -> int:
        """
        Token 설정과 API 초기화 상태로 우선순위 결정

        전략:
        - Token이 설정되고 API 초기화 성공: 우선순위 -1(가장 높음, efinance보다 우선)
        - 그 밖의 경우: 우선순위 2(기본)

        Returns:
            우선순위 숫자(0=가장 높음, 숫자가 클수록 낮음)
        """
        config = get_config()

        if config.tushare_token and self._api is not None:
            # Token이 설정되고 API 초기화 성공, 우선순위를 가장 높게 올림
            logger.info("✅ TUSHARE_TOKEN 확인, API 초기화 성공. Tushare 데이터 소스 우선순위를 가장 높게 올림 (Priority -1)")
            return -1

        # Token이 없거나 API 초기화 실패, 기본 우선순위 유지
        return 2

    def is_available(self) -> bool:
        """
        데이터 소스를 쓸 수 있는지 확인

        Returns:
            True면 사용 가능, False면 사용 불가
        """
        return self._api is not None

    def _check_rate_limit(self) -> None:
        """
        요청 속도 제한 확인 및 적용
        
        요청 속도 제어 전략:
        1. 새로운 1분이 시작됐는지 확인
        2. 그렇다면 카운터 초기화
        3. 이번 1분 호출 횟수가 한도를 넘으면 강제로 대기
        """
        current_time = time.time()
        
        # 카운터를 초기화해야 하는지 확인(새로운 1분)
        if self._minute_start is None:
            self._minute_start = current_time
            self._call_count = 0
        elif current_time - self._minute_start >= 60:
            # 1분이 지났으니 카운터 초기화
            self._minute_start = current_time
            self._call_count = 0
            logger.debug("요청 속도 카운터 초기화됨")
        
        # 한도를 넘었는지 확인
        if self._call_count >= self.rate_limit_per_minute:
            # 기다려야 할 시간 계산(다음 1분까지)
            elapsed = current_time - self._minute_start
            sleep_time = max(0, 60 - elapsed) + 1  # +1초 여유
            
            logger.warning(
                f"Tushare 요청 속도 한도 도달 ({self._call_count}/{self.rate_limit_per_minute}회/분), "
                f"{sleep_time:.1f}초 대기..."
            )
            
            time.sleep(sleep_time)
            
            # 카운터 초기화
            self._minute_start = time.time()
            self._call_count = 0
        
        # 호출 횟수 증가
        self._call_count += 1
        logger.debug(f"Tushare 이번 1분 호출 횟수: {self._call_count}/{self.rate_limit_per_minute}")

    def _call_api_with_rate_limit(self, method_name: str, **kwargs) -> pd.DataFrame:
        """Tushare API 호출을 모두 요청 속도 제한으로 감싸서 실행."""
        if self._api is None:
            raise DataFetchError("Tushare API 未初始化，请检查 Token 配置")

        self._check_rate_limit()
        method = getattr(self._api, method_name)
        return method(**kwargs)

    def _get_china_now(self) -> datetime:
        """상하이 시간대 현재 시각을 돌려줌. 날짜가 바뀔 때 새로 고치는 로직을 테스트하기 쉽게 함."""
        return datetime.now(ZoneInfo("Asia/Shanghai"))

    def _get_trade_dates(self, end_date: Optional[str] = None) -> List[str]:
        """날짜가 바뀌면 거래일 달력 캐시를 새로 고침. 서비스가 날짜를 넘겨도 옛 달력을 계속 쓰지 않게 함."""
        if self._api is None:
            return []

        china_now = self._get_china_now()
        requested_end_date = end_date or china_now.strftime("%Y%m%d")

        if self.date_list is not None and self._date_list_end == requested_end_date:
            return self.date_list

        start_date = (china_now - timedelta(days=20)).strftime("%Y%m%d")
        df_cal = self._call_api_with_rate_limit(
            "trade_cal",
            exchange="SSE",
            start_date=start_date,
            end_date=requested_end_date,
        )

        if df_cal is None or df_cal.empty or "cal_date" not in df_cal.columns:
            logger.warning("[Tushare] trade_cal 응답이 비어 있어 거래일 달력 캐시를 갱신할 수 없음")
            self.date_list = []
            self._date_list_end = requested_end_date
            return self.date_list

        trade_dates = sorted(
            df_cal[df_cal["is_open"] == 1]["cal_date"].astype(str).tolist(),
            reverse=True,
        )
        self.date_list = trade_dates
        self._date_list_end = requested_end_date
        return trade_dates

    @staticmethod
    def _pick_trade_date(trade_dates: List[str], use_today: bool) -> Optional[str]:
        """사용 가능한 거래일 목록으로 오늘 또는 직전 거래일을 고름."""
        if not trade_dates:
            return None
        if use_today or len(trade_dates) == 1:
            return trade_dates[0]
        return trade_dates[1]

    @staticmethod
    def _detect_exchange_hint(stock_code: str) -> Optional[str]:
        """Return SH/SZ/BJ when the raw user input carries an explicit exchange hint."""
        upper = (stock_code or "").strip().upper()
        if upper.startswith(("SH", "SS")) or upper.endswith((".SH", ".SS")):
            return "SH"
        if upper.startswith("SZ") or upper.endswith(".SZ"):
            return "SZ"
        if upper.startswith("BJ") or upper.endswith(".BJ"):
            return "BJ"
        return None

    @classmethod
    def _get_legacy_realtime_symbol(cls, stock_code: str) -> str:
        """Build the legacy tushare symbol while preserving explicit SH/SZ hints."""
        code = normalize_stock_code(stock_code)
        exchange_hint = cls._detect_exchange_hint(stock_code)

        if code == '000001' and exchange_hint == 'SH':
            return 'sh000001'
        if code == '399001':
            return 'sz399001'
        if code == '399006':
            return 'sz399006'
        if code == '000300':
            return 'sh000300'
        if is_bse_code(code):
            return f"bj{code}"
        return code
    
    def _convert_stock_code(self, stock_code: str) -> str:
        """
        A주 / ETF / 베이징거래소 등을 Tushare ts_code로 변환(홍콩 주식 로직은 없음).

        Tushare가 요구하는 형식 예:
        - 상하이 주식: 600519.SH
        - 선전 주식: 000001.SZ
        - 상하이 ETF: 510050.SH
        - 선전 ETF: 159919.SZ

        Args:
            stock_code: 원래 코드, 예: '600519', '000001', '563230'

        Returns:
            Tushare 형식 코드, 예: '600519.SH', '000001.SZ'
        """
        raw_code = stock_code.strip()
        
        # Already has suffix.
        if '.' in raw_code:
            upper = raw_code.upper()
            code = normalize_stock_code(raw_code)
            exchange_hint = self._detect_exchange_hint(raw_code)
            if exchange_hint in ("SH", "SZ", "BJ") and code.isdigit():
                return f"{code}.{exchange_hint}"

            ts_code = upper
            if ts_code.endswith('.SS'):
                return f"{ts_code[:-3]}.SH"
            return ts_code

        if _is_us_code(raw_code):
            raise DataFetchError(f"TushareFetcher 不支持美股 {raw_code}，请使用 AkshareFetcher 或 YfinanceFetcher")

        if _is_hk_market(raw_code):
            #raise DataFetchError(f"TushareFetcher는 홍콩 주식 {raw_code}을(를) 지원하지 않음, AkshareFetcher를 쓰세요")
            return normalize_stock_code(raw_code)

        code = normalize_stock_code(raw_code)
        exchange_hint = self._detect_exchange_hint(raw_code)

        if exchange_hint == "SH":
            return f"{code}.SH"
        if exchange_hint == "SZ":
            return f"{code}.SZ"
        if exchange_hint == "BJ":
            return f"{code}.BJ"

        # ETF: determine exchange by prefix
        if code.startswith(_ETF_SH_PREFIXES) and len(code) == 6:
            return f"{code}.SH"
        if code.startswith(_ETF_SZ_PREFIXES) and len(code) == 6:
            return f"{code}.SZ"
        
        # BSE (Beijing Stock Exchange): 8xxxxx, 4xxxxx, 920xxx
        if is_bse_code(code):
            return f"{code}.BJ"
        
        # Regular stocks
        # Shanghai: 600xxx, 601xxx, 603xxx, 605xxx, 688xxx (STAR Market)
        # Shenzhen: 000xxx, 001xxx, 002xxx, 003xxx, 300xxx, 301xxx (ChiNext)
        if code.startswith(('600', '601', '603', '605', '688')):
            return f"{code}.SH"
        elif code.startswith(('000', '001', '002', '003', '300', '301')):
            return f"{code}.SZ"
        else:
            logger.warning(f"종목 {code}의 시장을 알 수 없어 기본값 선전 시장 사용")
            return f"{code}.SZ"

    def _convert_hk_stock_code_for_tushare(self, stock_code: str) -> str:
        """
        사용자 입력을 Tushare Pro API가 쓰는 ts_code로 변환(홍콩 주식 nnnnn.HK 포함).

        - 홍콩 주식이 아니면: _convert_stock_code에 맡김(A주 / ETF / 베이징거래소 등).
        - 홍콩 주식: HK00700, 00700, 00700.HK 같은 형태를 숫자 5자리 + .HK로 통일.
        """
        raw_code = stock_code.strip()
        if _is_hk_market(raw_code):
            if "." in raw_code:
                ts_code = raw_code.upper()
                if ts_code.endswith(".SS"):
                    return f"{ts_code[:-3]}.SH"
                if ts_code.endswith(".HK"):
                    return ts_code
            digits = re.sub(r"\D", "", raw_code)
            if not digits:
                raise DataFetchError(f"홍콩 주식 코드 {raw_code}을(를) 인식할 수 없음")
            code = digits[-5:].rjust(5, "0")
            return f"{code}.HK"
        return self._convert_stock_code(stock_code)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Tushare에서 원본 데이터 가져오기
        
        코드 종류에 따라 다른 API 사용:
        - 일반 주식: daily()
        - ETF 펀드: fund_daily()
        
        흐름:
        1. API를 쓸 수 있는지 확인
        2. 미국 주식인지 확인(지원 안 함)
        3. 요청 속도 제한 확인
        4. 종목 코드 형식 변환
        5. 코드 종류에 맞는 API를 골라 호출
        """
        if self._api is None:
            raise DataFetchError("Tushare API 未初始化，请检查 Token 配置")
        
        # US stocks not supported
        if _is_us_code(stock_code):
            raise DataFetchError(f"TushareFetcher 不支持美股 {stock_code}，请使用 AkshareFetcher 或 YfinanceFetcher")
        
        # Rate-limit check
        self._check_rate_limit()
        
        is_hk = _is_hk_market(stock_code)
         # ETF / 홍콩 주식인지 판단해 API 선택
        is_etf = _is_etf_code(stock_code)
        if is_hk:
            ts_code = self._convert_hk_stock_code_for_tushare(stock_code)
            api_name = "hk_daily"
        else:
            ts_code = self._convert_stock_code(stock_code)
            api_name = "fund_daily" if is_etf else "daily"
        
        # Convert date format (Tushare requires YYYYMMDD)
        ts_start = start_date.replace('-', '')
        ts_end = end_date.replace('-', '')
        
       

        logger.debug(f"Tushare 호출 {api_name}({ts_code}, {ts_start}, {ts_end})")
        
        try:
            if is_hk:
                # 홍콩 주식은 hk_daily API 사용
                df = self._api.hk_daily(
                    ts_code=ts_code,
                    start_date=ts_start,
                    end_date=ts_end,
                )
            elif is_etf:
                # ETF uses fund_daily interface
                df = self._api.fund_daily(
                    ts_code=ts_code,
                    start_date=ts_start,
                    end_date=ts_end,
                )
            else:
                # Regular A-share stocks use daily interface
                df = self._api.daily(
                    ts_code=ts_code,
                    start_date=ts_start,
                    end_date=ts_end,
                )
            
            return df
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 한도 초과 감지
            if any(keyword in error_msg for keyword in ['quota', '配额', 'limit', '权限']):
                logger.warning(f"Tushare 한도 초과 가능성: {e}")
                raise RateLimitError(f"Tushare 한도 초과: {e}") from e
            
            raise DataFetchError(f"Tushare 데이터 받기 실패: {e}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        Tushare 데이터 표준화
        
        Tushare daily / fund_daily가 돌려주는 열 이름:
        ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
        
        표준 열 이름으로 매핑해야 함:
        date, open, high, low, close, volume, amount, pct_chg

        단위 환산은 A주(그리고 같은 단위를 쓰는 ETF 등의 API)에만 적용:
        - vol은 '수(100주)' 단위라 100을 곱해 '주'로 바꿈
        - amount는 '천 위안' 단위라 1000을 곱해 '위안'으로 바꿈

        홍콩 주식 hk_daily의 vol / amount는 바로 쓸 수 있는 단위라 위 환산을 하지 않음.
        """
        df = df.copy()
        is_hk = _is_hk_market(stock_code)

        # 열 이름 매핑
        column_mapping = {
            'trade_date': 'date',
            'vol': 'volume',
            # open, high, low, close, amount, pct_chg 열 이름은 같음
        }
        
        df = df.rename(columns=column_mapping)
        
        # 날짜 형식 변환(YYYYMMDD -> YYYY-MM-DD)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        
        # 거래량 / 거래대금: A주 계열 API만 단위 환산(홍콩 주식 hk_daily는 안 함)
        if 'volume' in df.columns and not is_hk:
            df['volume'] = df['volume'] * 100
        
        if 'amount' in df.columns and not is_hk:
            df['amount'] = df['amount'] * 1000
        
        # 종목 코드 열 추가
        df['code'] = stock_code
        
        # 필요한 열만 남김
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        """
        종목 이름 가져오기
        
        Tushare의 stock_basic API로 종목 기본 정보 가져오기
        
        Args:
            stock_code: 종목 코드
            
        Returns:
            종목 이름, 실패하면 None
        """
        if self._api is None:
            logger.warning("Tushare API가 초기화되지 않아 종목 이름을 받을 수 없음")
            return None

        # 캐시 확인
        if hasattr(self, '_stock_name_cache') and stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]
        
        # 캐시 초기화
        if not hasattr(self, '_stock_name_cache'):
            self._stock_name_cache = {}
        
        try:
            # 요청 속도 제한 확인
            self._check_rate_limit()
            

            # 시장/종류에 따라 기본 정보 API 선택
            if _is_hk_market(stock_code):
                ts_code = self._convert_hk_stock_code_for_tushare(stock_code)
                # 홍콩 주식: hk_basic 사용
                df = self._api.hk_basic(
                    ts_code=ts_code,
                    fields='ts_code,name'
                )
            elif _is_etf_code(stock_code):
                ts_code = self._convert_stock_code(stock_code)
                # ETF: fund_basic 사용
                df = self._api.fund_basic(
                    ts_code=ts_code,
                    fields='ts_code,name'
                )
            else:
                ts_code = self._convert_stock_code(stock_code)
                # A주 주식: stock_basic 사용
                df = self._api.stock_basic(
                    ts_code=ts_code,
                    fields='ts_code,name'
                )
            
            if df is not None and not df.empty:
                name = df.iloc[0]['name']
                self._stock_name_cache[stock_code] = name
                logger.debug(f"Tushare 종목 이름 받기 성공: {stock_code} -> {name}")
                return name
            
        except Exception as e:
            logger.warning(f"Tushare 종목 이름 받기 실패 {stock_code}: {e}")
        
        return None
    
    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """
        종목 목록 가져오기
        
        Tushare의 stock_basic API로 A주 목록 가져오기(홍콩 주식 제외).
        
        Returns:
            code, name, industry, area, market 열이 있는 DataFrame, 실패하면 None
        """
        if self._api is None:
            logger.warning("Tushare API가 초기화되지 않아 종목 목록을 받을 수 없음")
            return None
        
        try:
            self._check_rate_limit()

            df = self._api.stock_basic(
                exchange='',
                list_status='L',
                fields='ts_code,name,industry,area,market'
            )

            if df is None or df.empty:
                return None

            df = df.copy()
            df['code'] = df['ts_code'].astype(str).str.split('.').str[0]

            if not hasattr(self, '_stock_name_cache'):
                self._stock_name_cache = {}
            for _, row in df.iterrows():
                self._stock_name_cache[row['code']] = row['name']

            logger.info(f"Tushare 종목 목록 받기 성공: {len(df)}건")
            return df[['code', 'name', 'industry', 'area', 'market']]

        except Exception as e:
            logger.warning(f"Tushare 종목 목록 받기 실패: {e}")

        return None
    
    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        실시간 시세 가져오기

        전략:
        1. 먼저 Pro API 시도(2000포인트 필요): 데이터가 많고 안정적
        2. 실패하면 구버전 API로 대체: 조건이 낮지만 데이터가 적음

        Args:
            stock_code: 종목 코드

        Returns:
            UnifiedRealtimeQuote 객체, 실패하면 None
        """
        if self._api is None:
            return None

        # HK stocks not supported by Tushare
        if _is_hk_market(stock_code):
            logger.debug(f"TushareFetcher 홍콩 주식 실시간 시세 건너뜀 {stock_code}")
            return None

        normalized_code = normalize_stock_code(stock_code)

        from .realtime_types import (
            RealtimeSource,
            safe_float, safe_int
        )

        # 요청 속도 제한 확인
        self._check_rate_limit()

        # Pro API 시도
        try:
            ts_code = self._convert_stock_code(stock_code)
            # Pro 실시간 API 호출 시도(포인트 필요)
            df = self._api.quotation(ts_code=ts_code)

            if df is not None and not df.empty:
                row = df.iloc[0]
                logger.debug(f"Tushare Pro 실시간 시세 받기 성공: {stock_code}")

                return UnifiedRealtimeQuote(
                    code=normalized_code,
                    name=str(row.get('name', '')),
                    source=RealtimeSource.TUSHARE,
                    price=safe_float(row.get('price')),
                    change_pct=safe_float(row.get('pct_chg')),  # Pro API는 보통 등락률을 바로 줌
                    change_amount=safe_float(row.get('change')),
                    volume=safe_int(row.get('vol')),
                    amount=safe_float(row.get('amount')),
                    high=safe_float(row.get('high')),
                    low=safe_float(row.get('low')),
                    open_price=safe_float(row.get('open')),
                    pre_close=safe_float(row.get('pre_close')),
                    turnover_rate=safe_float(row.get('turnover_ratio')), # Pro API에는 회전율이 있을 수 있음
                    pe_ratio=safe_float(row.get('pe')),
                    pb_ratio=safe_float(row.get('pb')),
                    total_mv=safe_float(row.get('total_mv')),
                )
        except Exception as e:
            # 디버그 로그만 남기고 오류는 내지 않음, 대체 API를 계속 시도
            logger.debug(f"Tushare Pro 실시간 시세 사용 불가(포인트 부족일 수 있음): {e}")

        # 대체: 구버전 API 시도
        try:
            import tushare as ts

            symbol = self._get_legacy_realtime_symbol(stock_code)

            # 구버전 실시간 API 호출 (ts.get_realtime_quotes)
            df = ts.get_realtime_quotes(symbol)

            if df is None or df.empty:
                return None

            row = df.iloc[0]

            # 등락률 계산
            price = safe_float(row['price'])
            pre_close = safe_float(row['pre_close'])
            change_pct = 0.0
            change_amount = 0.0

            if price and pre_close and pre_close > 0:
                change_amount = price - pre_close
                change_pct = (change_amount / pre_close) * 100

            # 통합 객체 만들기
            return UnifiedRealtimeQuote(
                code=normalized_code,
                name=str(row['name']),
                source=RealtimeSource.TUSHARE,
                price=price,
                change_pct=round(change_pct, 2),
                change_amount=round(change_amount, 2),
                volume=safe_int(row['volume']) // 100,  # '수(100주)' 단위로 변환
                amount=safe_float(row['amount']),
                high=safe_float(row['high']),
                low=safe_float(row['low']),
                open_price=safe_float(row['open']),
                pre_close=pre_close,
            )

        except Exception as e:
            logger.warning(f"Tushare (구버전) 실시간 시세 받기 실패 {stock_code}: {e}")
            return None

    def get_main_indices(self, region: str = "cn") -> Optional[List[dict]]:
        """
        주요 지수 실시간 시세 가져오기(Tushare Pro), A주만 지원
        """
        if region != "cn":
            return None
        if self._api is None:
            return None

        from .realtime_types import safe_float

        # 지수 매핑: Tushare 코드 -> 이름
        indices_map = {
            '000001.SH': '上证指数',
            '399001.SZ': '深证成指',
            '399006.SZ': '创业板指',
            '000688.SH': '科创50',
            '000016.SH': '上证50',
            '000300.SH': '沪深300',
        }

        try:
            self._check_rate_limit()

            # Tushare index_daily는 과거 데이터를 줌. 실시간 데이터는 다른 API나 추정값이 필요
            # Tushare 무료 사용자는 지수 실시간 시세를 못 받을 수 있어서, 여기서는 예비 수단으로 씀
            # index_daily로 최근 거래일 데이터 가져오기

            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - pd.Timedelta(days=5)).strftime('%Y%m%d')

            results = []

            # 모든 지수 데이터를 한꺼번에 가져오기
            for ts_code, name in indices_map.items():
                try:
                    df = self._api.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                    if df is not None and not df.empty:
                        row = df.iloc[0] # 가장 최근 하루

                        current = safe_float(row['close'])
                        prev_close = safe_float(row['pre_close'])

                        results.append({
                            'code': ts_code.split('.')[0], # sh000001 형식과 맞추려면 변환이 필요하지만, 여기서는 숫자만 유지
                            'name': name,
                            'current': current,
                            'change': safe_float(row['change']),
                            'change_pct': safe_float(row['pct_chg']),
                            'open': safe_float(row['open']),
                            'high': safe_float(row['high']),
                            'low': safe_float(row['low']),
                            'prev_close': prev_close,
                            'volume': safe_float(row['vol']),
                            'amount': safe_float(row['amount']) * 1000, # 천 위안을 위안으로 변환
                            'amplitude': 0.0 # Tushare index_daily는 진폭을 직접 주지 않음
                        })
                except Exception as e:
                    logger.debug(f"Tushare 지수 {name} 받기 실패: {e}")
                    continue

            if results:
                return results
            else:
                logger.warning("[Tushare] 지수 시세 데이터를 받지 못함")

        except Exception as e:
            logger.error(f"[Tushare] 지수 시세 받기 실패: {e}")

        return None

    def get_market_stats(self) -> Optional[dict]:
        """
        시장 상승/하락 통계 가져오기(Tushare Pro)
        2000포인트면 이 API(ts.pro_api().rt_k)를 하루 두 번 호출 가능
        API 제한은 여기 참고: https://tushare.pro/document/1?doc_id=108
        """
        if self._api is None:
            return None

        try:
            logger.info("[Tushare] ts.pro_api() 시장 통계 받는 중...")
            
            # 현재 중국 시각을 구해 거래 시간인지 판단
            china_now = self._get_china_now()
            current_clock = china_now.strftime("%H:%M")
            current_date = china_now.strftime("%Y%m%d")

            trade_dates = self._get_trade_dates(current_date)
            if not trade_dates:
                return None

            if current_date in trade_dates:
                if current_clock < '09:30' or current_clock > '16:30':
                    use_realtime = False
                else:
                    use_realtime = True
            else:
                use_realtime = False

            # 장중에 실시간으로 쓰려면 실시간 데이터를 주는 다른 소스(akshare, efinance)를 사용
            if use_realtime:
                try:
                    df = self._call_api_with_rate_limit("rt_k", ts_code='3*.SZ,6*.SH,0*.SZ,92*.BJ')
                    if df is not None and not df.empty:
                        return self._calc_market_stats(df)
                    
                except Exception as e:
                    logger.error(f"[Tushare] ts.pro_api().rt_k 실시간 데이터 받기 실패: {e}")
                    return None
            else:

                if current_date not in trade_dates:
                    last_date = self._pick_trade_date(trade_dates, use_today=True)  # 가장 최근 날짜 사용
                else:
                    if current_clock < '09:30': 
                        last_date = self._pick_trade_date(trade_dates, use_today=False)  # 전날 데이터 사용
                    else:  # 즉 '> 16:30'                  
                        last_date = self._pick_trade_date(trade_dates, use_today=True)  # 당일 데이터 사용

                if last_date is None:
                    return None

                try:
                    df = self._call_api_with_rate_limit(
                        "daily",
                        ts_code='3*.SZ,6*.SH,0*.SZ,92*.BJ',
                        start_date=last_date,
                        end_date=last_date,
                    )
                    # API마다 열 이름 대소문자가 다를 수 있어서(예: rt_k는 소문자, daily는 대문자) 열 이름을 모두 소문자로 통일
                    df.columns = [col.lower() for col in df.columns]

                    # 종목 기본 정보 가져오기(코드와 이름 포함)
                    df_basic = self._call_api_with_rate_limit("stock_basic", fields='ts_code,name')
                    df = pd.merge(df, df_basic, on='ts_code', how='left')
                    # 다른 데이터 소스와 맞추려고 daily의 amount 열 값에 1000을 곱함
                    if 'amount' in df.columns:
                        df['amount'] = df['amount'] * 1000

                    if df is not None and not df.empty:
                        return self._calc_market_stats(df)
                except Exception as e:
                    logger.error(f"[Tushare] ts.pro_api().daily 데이터 받기 실패: {e}")
                    

            
        except Exception as e:
            logger.error(f"[Tushare] 시장 통계 받기 실패: {e}")

        return None
    
    def _calc_market_stats(
            self,
            df: pd.DataFrame,
            ) -> Optional[Dict[str, Any]]:
            """시세 DataFrame으로 상승/하락 통계 계산."""
            import numpy as np

            df = df.copy()
            
            # 1. 비교용 기본 데이터 추출: 현재가, 전일 종가
            # 여러 API의 서로 다른 열 이름 지원: sina/em efinance tushare xtdata
            code_col = next((c for c in ['代码', '股票代码', 'ts_code','stock_code'] if c in df.columns), None)
            name_col = next((c for c in ['名称', '股票名称','name','name'] if c in df.columns), None)
            close_col = next((c for c in ['最新价', '最新价', 'close','lastPrice'] if c in df.columns), None)
            pre_close_col = next((c for c in ['昨收', '昨日收盘', 'pre_close','lastClose'] if c in df.columns), None)
            amount_col = next((c for c in ['成交额', '成交额', 'amount','amount'] if c in df.columns), None) 
            
            limit_up_count = 0
            limit_down_count = 0
            up_count = 0
            down_count = 0
            flat_count = 0

            for code, name, current_price, pre_close, amount in zip(
                df[code_col], df[name_col], df[close_col], df[pre_close_col], df[amount_col]
            ):
                
                # 거래정지 종목 제외. efinance는 거래정지 종목 가격이 빠져 '-'로, em은 none으로 나올 때가 있음
                if pd.isna(current_price) or pd.isna(pre_close) or current_price in ['-'] or pre_close in ['-'] or amount == 0:
                    continue
                
                # em, efinance는 str이라 float로 바꿔야 함
                current_price = float(current_price)
                pre_close = float(pre_close)
                
                # 접두사를 뗀 숫자 코드 구하기
                pure_code = normalize_stock_code(str(code)) 

                # A. 종목마다 가격 제한폭 비율 결정(숫자 코드로 판단)
                if is_bse_code(pure_code): 
                    ratio = 0.30
                elif is_kc_cy_stock(pure_code): #pure_code.startswith(('688', '30')):
                    ratio = 0.20
                elif is_st_stock(name): #'ST' in str_name:
                    ratio = 0.05
                else:
                    ratio = 0.10

                # B. A주 규칙대로 상한가/하한가 계산: 전일 종가 * (1 ± 비율) -> 소수 둘째 자리 반올림
                limit_up_price = np.floor(pre_close * (1 + ratio) * 100 + 0.5) / 100.0
                limit_down_price = np.floor(pre_close * (1 - ratio) * 100 + 0.5) / 100.0

                limit_up_price_Tolerance = round(abs(pre_close * (1 + ratio) - limit_up_price), 10)
                limit_down_price_Tolerance = round(abs(pre_close * (1 - ratio) - limit_down_price), 10)

                # C. 정확히 비교
                if current_price > 0 :
                    is_limit_up = (current_price > 0) and (abs(current_price - limit_up_price) <= limit_up_price_Tolerance)
                    is_limit_down = (current_price > 0) and (abs(current_price - limit_down_price) <= limit_down_price_Tolerance)

                    if is_limit_up:
                        limit_up_count += 1
                    if is_limit_down:
                        limit_down_count += 1

                    if current_price > pre_close:
                        up_count += 1
                    elif current_price < pre_close:
                        down_count += 1
                    else:
                        flat_count += 1
                    
            # 개수 세기
            stats = {
                'up_count': up_count,
                'down_count': down_count,
                'flat_count': flat_count,
                'limit_up_count': limit_up_count,
                'limit_down_count': limit_down_count,
                'total_amount': 0.0,
            }
            
            # 거래대금 합계
            if amount_col and amount_col in df.columns:
                df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce')
                stats['total_amount'] = (df[amount_col].sum() / 1e8)
                
            return stats

    def get_trade_time(self,early_time='09:30',late_time='16:30') -> Optional[str]:
        '''
        지금 시각 기준으로 데이터를 받을 수 있는 시작 날짜 구하기

        Args:
                early_time: 기본 '09:30'
                late_time: 기본 '16:30'
                early_time-late_time 사이에는 직전 거래일 데이터를, 그 밖의 시간에는 당일 데이터를 씀
        Returns:
                start_date: 데이터를 받을 수 있는 시작 날짜
        '''
        china_now = self._get_china_now()
        china_date = china_now.strftime("%Y%m%d")
        china_clock = china_now.strftime("%H:%M")

        trade_dates = self._get_trade_dates(china_date)
        if not trade_dates:
            return None

        if china_date in trade_dates:
            if  early_time < china_clock < late_time: # 직전 거래일 데이터를 쓰는 시간대
                use_today = False
            else:
                use_today = True
        else:
            # 거래일이 아니면: today가 trade_dates에 없으니 trade_dates[0]이 가장 최근 거래일
            use_today = True

        start_date = self._pick_trade_date(trade_dates, use_today=use_today)
        if start_date is None:
            return None

        if not use_today:
            logger.info(f"[Tushare] 현재 시각 {china_clock}에는 당일 매물대 분포를 못 받을 수 있어, 직전 거래일 데이터를 시도 {start_date}")

        return start_date
    
    def get_sector_rankings(self, n: int = 5) -> Optional[Tuple[list, list]]:
        """
        업종 상승/하락 순위 가져오기(Tushare Pro)
        
        데이터 소스 우선순위:
        1. 퉁화순(THS) API (ts.pro_api().moneyflow_ind_ths)
        2. 동방재부(Eastmoney) API (ts.pro_api().moneyflow_ind_dc)
        주의: API마다 업종 분류와 섹터 정의가 달라서 두 결과가 다를 수 있음
        """
        def _get_rank_top_n(df: pd.DataFrame, change_col: str, industry_name: str, n: int) -> Tuple[list, list]:
            df[change_col] = pd.to_numeric(df[change_col], errors='coerce')
            df = df.dropna(subset=[change_col])

            # 상승률 상위 n개
            top = df.nlargest(n, change_col)
            top_sectors = [
                {'name': row[industry_name], 'change_pct': row[change_col]}
                for _, row in top.iterrows()
            ]

            bottom = df.nsmallest(n, change_col)
            bottom_sectors = [
                {'name': row[industry_name], 'change_pct': row[change_col]}
                for _, row in bottom.iterrows()
            ]
            return top_sectors, bottom_sectors

        # 15:30 이후에야 당일 데이터가 있음
        start_date = self.get_trade_time(early_time='00:00', late_time='15:30')
        if not start_date:
            return None

        # 퉁화순 API 우선
        logger.info("[Tushare] ts.pro_api().moneyflow_ind_ths 섹터 순위 받는 중(퉁화순)...")
        try:
            df = self._call_api_with_rate_limit("moneyflow_ind_ths", trade_date=start_date)
            if df is not None and not df.empty:
                change_col = 'pct_change'
                name = 'industry'
                if change_col in df.columns:
                    return _get_rank_top_n(df, change_col, name, n)
        except Exception as e:
            logger.warning(f"[Tushare] 퉁화순 업종 순위 받기 실패: {e} 동방재부 API 시도")

        # 퉁화순 API 실패, 동방재부 API로 대체 시도
        logger.info("[Tushare] ts.pro_api().moneyflow_ind_dc 섹터 순위 받는 중(동방재부)...")
        try:
            df = self._call_api_with_rate_limit("moneyflow_ind_dc", trade_date=start_date)
            if df is not None and not df.empty:
                df = df[df['content_type'] == '行业']  # 업종 섹터만 남김
                change_col = 'pct_change'
                name = 'name'
                if change_col in df.columns:
                    return _get_rank_top_n(df, change_col, name, n)
        except Exception as e:
            logger.warning(f"[Tushare] 동방재부 업종 순위 받기 실패: {e}")
            return None
        
        # 결과가 비었거나 API 호출이 실패하면 None 반환
        return None
    
    

    
    def get_chip_distribution(self, stock_code: str) -> Optional[ChipDistribution]:
        """
        매물대 분포 데이터 가져오기
        
        데이터 출처: ts.pro_api().cyq_chips()
        포함: 수익 비율, 평균 단가, 매물 집중도
        
        주의: ETF/지수는 매물대 분포 데이터가 없어 바로 None 반환. 홍콩 주식도 지원 안 해서 바로 None 반환.
        5000포인트 미만이면 하루 15회, 시간당 5회 호출 가능
        
        Args:
            stock_code: 종목 코드
            
        Returns:
            ChipDistribution 객체(최근 거래일 데이터), 실패하면 None

        """
        if _is_us_code(stock_code):
            logger.warning(f"[Tushare] TushareFetcher는 미국 주식 {stock_code}의 매물대 분포를 지원하지 않음")
            return None
        
        if _is_etf_code(stock_code):
            logger.warning(f"[Tushare] TushareFetcher는 ETF {stock_code}의 매물대 분포를 지원하지 않음")
            return None

        if _is_hk_market(stock_code):
            logger.warning(f"[Tushare] TushareFetcher는 홍콩 주식 {stock_code}의 매물대 분포를 지원하지 않음")
            return None
        
        try:
            # 19시 이후에야 당일 데이터가 있음
            start_date = self.get_trade_time(early_time='00:00', late_time='19:00') 
            if not start_date:
                return None

            ts_code = self._convert_stock_code(stock_code)

            df = self._call_api_with_rate_limit(
                "cyq_chips",
                ts_code=ts_code,
                start_date=start_date,
                end_date=start_date,
            )
            if df is not None and not df.empty:
                daily_df = self._call_api_with_rate_limit(
                    "daily",
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=start_date,
                )
                if daily_df is None or daily_df.empty:
                    return None
                current_price = daily_df.iloc[0]['close']
                metrics = self.compute_cyq_metrics(df, current_price)

                chip = ChipDistribution(
                    code=stock_code,
                    date=datetime.strptime(start_date, '%Y%m%d').strftime('%Y-%m-%d'),
                    profit_ratio=metrics['获利比例'],
                    avg_cost=metrics['平均成本'],
                    cost_90_low=metrics['90成本-低'],
                    cost_90_high=metrics['90成本-高'],
                    concentration_90=metrics['90集中度'],
                    cost_70_low=metrics['70成本-低'],
                    cost_70_high=metrics['70成本-高'],
                    concentration_70=metrics['70集中度'],
                )
                
                logger.info(f"[매물대 분포] {stock_code} 날짜={chip.date}: 수익 비율={chip.profit_ratio:.1%}, "
                        f"평균 단가={chip.avg_cost}, 90% 집중도={chip.concentration_90:.2%}, "
                        f"70% 집중도={chip.concentration_70:.2%}")
                return chip

        except Exception as e:
            logger.warning(f"[Tushare] 매물대 분포 받기 실패 {stock_code}: {e}")
            return None

    def compute_cyq_metrics(self, df: pd.DataFrame, current_price: float) -> dict:
        """
        Tushare 매물대 분포 상세표(cyq_chips)로 자주 쓰는 매물대 지표 계산  
        :param df: 'price'와 'percent' 열이 있는 DataFrame  
        :param current_price: 종목의 당일 현재가/종가(수익 비율 계산용)  
        :return: 매물대 지표를 담은 딕셔너리  
        """
        import numpy as np
        # 1. 가격 오름차순으로 정렬(Tushare 데이터는 보통 역순)
        df_sorted = df.sort_values(by='price', ascending=True).reset_index(drop=True)

        # 2. 원본 percent 합계의 부동소수점 오차를 막으려고 100%로 정규화
        total_percent = df_sorted['percent'].sum()

        df_sorted['norm_percent'] = df_sorted['percent'] / total_percent * 100

        # 3. 매물 누적 분포 계산
        df_sorted['cumsum'] = df_sorted['norm_percent'].cumsum()

        # --- 수익 비율 ---
        # 가격이 현재가 이하인 매물의 합
        winner_rate = df_sorted[df_sorted['price'] <= current_price]['norm_percent'].sum()

        # --- 평균 단가 ---
        # 가격의 가중 평균
        avg_cost = np.average(df_sorted['price'], weights=df_sorted['norm_percent'])

        # --- 도우미 함수: 지정한 누적 비율 지점의 가격 구하기 ---
        def get_percentile_price(target_pct):
            # 누적 합이 처음으로 목표 비율 이상이 되는 행 인덱스 찾기
            idx = df_sorted['cumsum'].searchsorted(target_pct)
            idx = min(idx, len(df_sorted) - 1) # 범위를 넘지 않게 함
            return df_sorted.loc[idx, 'price']

        # --- 90% 원가 구간과 집중도 ---
        # 앞뒤로 5%씩 제외
        cost_90_low = get_percentile_price(5)
        cost_90_high = get_percentile_price(95)
        if (cost_90_high + cost_90_low) != 0:
            concentration_90 = (cost_90_high - cost_90_low) / (cost_90_high + cost_90_low) * 100
        else:
            concentration_90 = 0.0
            
        # --- 70% 원가 구간과 집중도 ---
        # 앞뒤로 15%씩 제외
        cost_70_low = get_percentile_price(15)
        cost_70_high = get_percentile_price(85)
        if (cost_70_high + cost_70_low) != 0:
            concentration_70 = (cost_70_high - cost_70_low) / (cost_70_high + cost_70_low) * 100
        else:
            concentration_70 = 0.0

        # 정리된 결과 반환
        return {
            "获利比例": round(winner_rate/100, 4), # akshare와 맞추려고 /100, 소수 형식으로 반환
            "平均成本": round(avg_cost, 4),
            "90成本-低": round(cost_90_low, 4),
            "90成本-高": round(cost_90_high, 4),
            "90集中度": round(concentration_90/100, 4),
            "70成本-低": round(cost_70_low, 4),
            "70成本-高": round(cost_70_high, 4),
            "70集中度": round(concentration_70/100, 4)
        }



if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = TushareFetcher()
    
    try:
        # 과거 데이터 테스트
        df = fetcher.get_daily_data('600519')  # 마오타이
        print(f"받기 성공, 총 {len(df)}건")
        print(df.tail())
        
        # 종목 이름 테스트
        name = fetcher.get_stock_name('600519')
        print(f"종목 이름: {name}")
        
    except Exception as e:
        print(f"받기 실패: {e}")

    # 시장 통계 테스트
    print("\n" + "=" * 50)
    print("Testing get_market_stats (tushare)")
    print("=" * 50)
    try:
        stats = fetcher.get_market_stats()
        if stats:
            print(f"Market Stats successfully computed:")
            print(f"Up: {stats['up_count']} (Limit Up: {stats['limit_up_count']})")
            print(f"Down: {stats['down_count']} (Limit Down: {stats['limit_down_count']})")
            print(f"Flat: {stats['flat_count']}")
            print(f"Total Amount: {stats['total_amount']:.2f} 억 (Yi)")
        else:
            print("Failed to compute market stats.")
    except Exception as e:
        print(f"Failed to compute market stats: {e}")


    # 매물대 분포 데이터 테스트
    print("\n" + "=" * 50)
    print("매물대 분포 데이터 받기 테스트")
    print("=" * 50)
    try:
        chip = fetcher.get_chip_distribution('600519')  # 마오타이
    except Exception as e:
        print(f"[매물대 분포] 받기 실패: {e}")

    # 업종 순위 테스트
    print("\n" + "=" * 50)
    print("업종 순위 받기 테스트")
    print("=" * 50)
    try:
        rankings = fetcher.get_sector_rankings(n=5)
        if rankings:
            top, bottom = rankings
            print("상승률 Top 5:")
            for sector in top:
                print(f"{sector['name']}: {sector['change_pct']}%")
            print("\n하락률 Top 5:")
            for sector in bottom:
                print(f"{sector['name']}: {sector['change_pct']}%")
        else:
            print("업종 순위 데이터를 받지 못함")
    except Exception as e:
        print(f"[업종 순위] 받기 실패: {e}")
