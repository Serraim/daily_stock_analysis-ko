# -*- coding: utf-8 -*-
"""
===================================
EfinanceFetcher - 우선 데이터 소스 (Priority 0)
===================================

데이터 출처: 둥팡차이푸 크롤러 (efinance 라이브러리 사용)
특징: 무료, Token 불필요, 데이터가 풍부하고 API가 간단함
저장소: https://github.com/Micro-sheep/efinance

AkshareFetcher와 비슷하지만 efinance 라이브러리는:
1. API가 더 간단하고 쓰기 쉬움
2. 여러 종목을 한 번에 가져올 수 있음
3. 인터페이스 래핑이 더 안정적임

차단 방지 전략:
1. 요청 전마다 1.5~3.0초 무작위 대기
2. User-Agent 무작위 교체
3. tenacity로 지수 백오프 재시도
4. 서킷 브레이커: 연속 실패 시 자동으로 잠시 쉼
"""

import logging
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd
import requests  # 예외를 잡기 위해 requests를 가져옴
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

# Timeout (seconds) for efinance library calls that go through eastmoney APIs
# with no built-in timeout.  Prevents indefinite hangs when hosts are unreachable.
try:
    _EF_CALL_TIMEOUT = int(os.environ.get("EFINANCE_CALL_TIMEOUT", "30"))
except (ValueError, TypeError):
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "EFINANCE_CALL_TIMEOUT is not a valid integer, using default 30s"
    )
    _EF_CALL_TIMEOUT = 30

from src.patches.eastmoney_patch import eastmoney_patch
from src.config import get_config
from src.services.stock_list_parser import ParseStatus, parse_analysis_target
from .base import (
    BaseFetcher,
    DataFetchError,
    RateLimitError,
    STANDARD_COLUMNS,
    is_bse_code,
    is_st_stock,
    is_kc_cy_stock,
    normalize_stock_code,
    _is_hk_market,
    _is_etf_code as _is_a_share_etf_code,
)
from .realtime_types import (
    UnifiedRealtimeQuote, RealtimeSource,
    get_realtime_circuit_breaker,
    safe_float, safe_int  # 공통 타입 변환 함수 사용
)


# 하위 호환을 위해 예전 타입 별칭을 남겨 둠
@dataclass
class EfinanceRealtimeQuote:
    """
    실시간 시세 데이터 (efinance 제공) - 하위 호환용 별칭
    
    새 코드에서는 UnifiedRealtimeQuote를 쓰세요
    """
    code: str
    name: str = ""
    price: float = 0.0           # 현재가
    change_pct: float = 0.0      # 등락률(%)
    change_amount: float = 0.0   # 등락폭
    
    # 거래량·가격 지표
    volume: int = 0              # 거래량
    amount: float = 0.0          # 거래대금
    turnover_rate: float = 0.0   # 회전율(%)
    amplitude: float = 0.0       # 진폭(%)
    
    # 가격 범위
    high: float = 0.0            # 고가
    low: float = 0.0             # 저가
    open_price: float = 0.0      # 시가
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'code': self.code,
            'name': self.name,
            'price': self.price,
            'change_pct': self.change_pct,
            'change_amount': self.change_amount,
            'volume': self.volume,
            'amount': self.amount,
            'turnover_rate': self.turnover_rate,
            'amplitude': self.amplitude,
            'high': self.high,
            'low': self.low,
            'open': self.open_price,
        }


logger = logging.getLogger(__name__)

EASTMONEY_HISTORY_ENDPOINT = "push2his.eastmoney.com/api/qt/stock/kline/get"


# 무작위 교체용 User-Agent 목록
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]


# 실시간 시세 캐시 (중복 요청 방지)
# TTL은 10분(600초): 여러 종목을 분석할 때 같은 데이터를 다시 받지 않도록 함
_realtime_cache: Dict[str, Any] = {
    'data': None,
    'timestamp': 0,
    'ttl': 600  # 캐시 유효 시간 10분
}

# ETF 실시간 시세 캐시 (주식과 따로 보관)
_etf_realtime_cache: Dict[str, Any] = {
    'data': None,
    'timestamp': 0,
    'ttl': 600  # 캐시 유효 시간 10분
}

_ETF_SH_PREFIXES = ('51', '52', '56', '58')
_ETF_SZ_PREFIXES = ('15', '16', '18')


def _is_etf_code(stock_code: str) -> bool:
    """
    코드가 ETF인지 판별
    
    ETF 코드 규칙:
    - 상하이거래소 ETF: 51xxxx, 52xxxx, 56xxxx, 58xxxx
    - 선전거래소 ETF: 15xxxx, 16xxxx, 18xxxx
    
    Args:
        stock_code: 종목/펀드 코드
        
    Returns:
        ETF 코드면 True, 일반 주식 코드면 False
    """
    return _is_a_share_etf_code(stock_code)


def _build_eastmoney_etf_secid(stock_code: str) -> str:
    """Build Eastmoney secid for A-share ETF historical K-line queries."""
    code = normalize_stock_code(stock_code)
    if not _is_etf_code(code):
        raise DataFetchError(f"ETF 코드 {stock_code}를 알아볼 수 없습니다")
    if code.startswith(_ETF_SH_PREFIXES):
        return f"1.{code}"
    if code.startswith(_ETF_SZ_PREFIXES):
        return f"0.{code}"
    raise DataFetchError(f"ETF {stock_code}의 Eastmoney 시장 접두어를 정할 수 없습니다")


def _is_us_code(stock_code: str) -> bool:
    """
    코드가 미국 주식인지 판별
    
    미국 주식 코드 규칙:
    - 대문자 1~5자, 예: 'AAPL', 'TSLA'
    - '.'이 들어갈 수 있음, 예: 'BRK.B'
    """
    code = stock_code.strip().upper()
    return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))


def _ef_call_with_timeout(func, *args, timeout=None, **kwargs):
    """Run an efinance library call in a thread with a timeout.

    efinance internally uses requests/urllib3 with no timeout, so when
    eastmoney hosts are unreachable the call can hang for many minutes.
    This helper caps the *calling thread's* wait time.  Note: Python threads
    cannot be forcibly killed, so the worker thread may continue running in
    the background until the OS-level TCP timeout fires or the process exits.
    This is acceptable — the calling thread returns promptly on timeout.
    """
    if timeout is None:
        timeout = _EF_CALL_TIMEOUT
    # Do NOT use 'with ThreadPoolExecutor(...)' here: the context manager calls
    # shutdown(wait=True) on __exit__, which would re-block on the hung thread.
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(func, *args, **kwargs)
        return future.result(timeout=timeout)
    finally:
        # wait=False: calling thread returns immediately; worker cleans up later
        executor.shutdown(wait=False)


def _classify_eastmoney_error(exc: Exception) -> Tuple[str, str]:
    """
    Classify Eastmoney request failures into stable log categories.
    """
    message = str(exc).strip()
    lowered = message.lower()

    remote_disconnect_keywords = (
        'remotedisconnected',
        'remote end closed connection without response',
        'connection aborted',
        'connection broken',
        'protocolerror',
    )
    timeout_keywords = (
        'timeout',
        'timed out',
        'readtimeout',
        'connecttimeout',
    )
    rate_limit_keywords = (
        'banned',
        'blocked',
        '频率',
        'rate limit',
        'too many requests',
        '429',
        '限制',
        'forbidden',
        '403',
    )

    if any(keyword in lowered for keyword in remote_disconnect_keywords):
        return "remote_disconnect", message
    if isinstance(exc, (TimeoutError, requests.exceptions.Timeout)) or any(
        keyword in lowered for keyword in timeout_keywords
    ):
        return "timeout", message
    if any(keyword in lowered for keyword in rate_limit_keywords):
        return "rate_limit_or_anti_bot", message
    if isinstance(exc, requests.exceptions.RequestException):
        return "request_error", message
    return "unknown_request_error", message


class EfinanceFetcher(BaseFetcher):
    """
    Efinance 데이터 소스 구현
    
    우선순위: 0 (가장 높음, AkshareFetcher보다 먼저)
    데이터 출처: 둥팡차이푸 (efinance 라이브러리로 감쌈)
    저장소: https://github.com/Micro-sheep/efinance
    
    주요 API:
    - ef.stock.get_quote_history(): 과거 캔들(K선) 데이터 조회
    - ef.stock.get_base_info(): 종목 기본 정보 조회
    - ef.stock.get_realtime_quotes(): 실시간 시세 조회
    
    핵심 전략:
    - 요청 전마다 1.5~3.0초 무작위 대기
    - User-Agent 무작위 교체
    - 실패하면 지수 백오프로 재시도 (최대 3회)
    """
    
    name = "EfinanceFetcher"
    priority = int(os.getenv("EFINANCE_PRIORITY", "0"))  # 최우선, AkshareFetcher보다 앞
    
    def __init__(self, sleep_min: float = 1.5, sleep_max: float = 3.0):
        """
        EfinanceFetcher 초기화
        
        Args:
            sleep_min: 최소 대기 시간(초)
            sleep_max: 최대 대기 시간(초)
        """
        self.sleep_min = sleep_min
        self.sleep_max = sleep_max
        self._last_request_time: Optional[float] = None
        # 둥팡차이푸 패치가 켜져 있을 때만 패치를 적용
        if get_config().enable_eastmoney_patch:
            eastmoney_patch()

    @staticmethod
    def _build_history_failure_message(
        stock_code: str,
        beg_date: str,
        end_date: str,
        exc: Exception,
        elapsed: float,
        is_etf: bool = False,
    ) -> Tuple[str, str]:
        category, detail = _classify_eastmoney_error(exc)
        instrument_type = "ETF" if is_etf else "stock"
        message = (
            "Eastmoney 历史K线接口失败: "
            f"endpoint={EASTMONEY_HISTORY_ENDPOINT}, stock_code={stock_code}, "
            f"market_type={instrument_type}, range={beg_date}~{end_date}, "
            f"category={category}, error_type={type(exc).__name__}, elapsed={elapsed:.2f}s, detail={detail}"
        )
        return category, message

    def _set_random_user_agent(self) -> None:
        """
        무작위 User-Agent 설정
        
        requests Session의 headers를 바꾸는 방식
        크롤링 차단을 피하는 핵심 방법 중 하나
        """
        try:
            random_ua = random.choice(USER_AGENTS)
            logger.debug(f"User-Agent 설정: {random_ua[:50]}...")
        except Exception as e:
            logger.debug(f"User-Agent 설정 실패: {e}")
    
    def _enforce_rate_limit(self) -> None:
        """
        요청 속도 제한 적용
        
        방식:
        1. 직전 요청 후 지난 시간을 확인
        2. 간격이 모자라면 그만큼 더 대기
        3. 그다음 무작위 jitter 대기
        """
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            min_interval = self.sleep_min
            if elapsed < min_interval:
                additional_sleep = min_interval - elapsed
                logger.debug(f"추가 대기 {additional_sleep:.2f}초")
                time.sleep(additional_sleep)
        
        # 무작위 jitter 대기
        self.random_sleep(self.sleep_min, self.sleep_max)
        self._last_request_time = time.time()
    
    @retry(
        stop=stop_after_attempt(1),  # 속도 제한에 걸리지 않도록 1회로 줄임
        wait=wait_exponential(multiplier=1, min=4, max=60),  # 대기 시간 설정은 그대로 유지
        retry=retry_if_exception_type((
            ConnectionError,
            TimeoutError,
            requests.exceptions.RequestException,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        efinance에서 원본 데이터 가져오기
        
        코드 종류에 따라 API를 자동 선택:
        - 미국 주식: 지원 안 함. 예외를 던져 DataFetcherManager가 다른 데이터 소스로 넘어가게 함
        - 일반 주식: ef.stock.get_quote_history()
        - ETF: ef.stock.get_quote_history() 사용 (ETF는 거래소 상장 증권이라 주식 캔들 인터페이스를 씀)
        
        흐름:
        1. 코드 종류 판별 (미국 주식/주식/ETF)
        2. 무작위 User-Agent 설정
        3. 요청 속도 제한 (무작위 대기)
        4. 알맞은 efinance API 호출
        5. 받은 데이터 처리
        """
        # 미국 주식은 지원하지 않으므로 예외를 던져 DataFetcherManager가 AkshareFetcher/YfinanceFetcher로 넘어가게 함
        if _is_us_code(stock_code):
            raise DataFetchError(f"EfinanceFetcher는 미국 주식 {stock_code}를 지원하지 않습니다. AkshareFetcher나 YfinanceFetcher를 쓰세요")

        # efinance의 과거 캔들 인터페이스는 홍콩 주식 코드에서 엉뚱한 시장 데이터를 줄 수 있으므로,
        # 명시적으로 건너뛰고 AkShare/Tushare/YFinance/Longbridge 같은 홍콩 주식 경로에 맡김.
        if _is_hk_market(stock_code):
            raise DataFetchError(f"EfinanceFetcher 不支持港股日线 {stock_code}，请使用 AkshareFetcher 或其他港股数据源")
        
        # 코드 종류에 따라 조회 방법을 고름
        if _is_etf_code(stock_code):
            return self._fetch_etf_data(stock_code, start_date, end_date)
        else:
            return self._fetch_stock_data(stock_code, start_date, end_date)
    
    def _fetch_stock_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        일반 A주 과거 데이터 조회
        
        데이터 출처: ef.stock.get_quote_history()
        
        API 인자 설명:
        - stock_codes: 종목 코드
        - beg: 시작일, 형식 'YYYYMMDD'
        - end: 종료일, 형식 'YYYYMMDD'
        - klt: 주기, 101=일봉
        - fqt: 수정주가 방식, 1=전진 수정주가
        """
        import efinance as ef
        
        # 차단 방지 1: 무작위 User-Agent
        self._set_random_user_agent()
        
        # 차단 방지 2: 강제 대기
        self._enforce_rate_limit()
        
        # 날짜 형식 변환 (efinance는 YYYYMMDD 형식 사용)
        beg_date = start_date.replace('-', '')
        end_date_fmt = end_date.replace('-', '')
        
        logger.info(f"[API 호출] ef.stock.get_quote_history(stock_codes={stock_code}, "
                   f"beg={beg_date}, end={end_date_fmt}, klt=101, fqt=1)")
        
        api_start = time.time()
        try:
            # efinance로 A주 일봉 데이터 조회
            # klt=101 은 일봉
            # fqt=1 은 전진 수정주가
            df = _ef_call_with_timeout(
                ef.stock.get_quote_history,
                stock_codes=stock_code,
                beg=beg_date,
                end=end_date_fmt,
                klt=101,  # 일봉
                fqt=1,    # 전진 수정주가
                timeout=60,
            )
            
            api_elapsed = time.time() - api_start
            
            # 받은 데이터 요약을 기록
            if df is not None and not df.empty:
                logger.info(
                    "[API 응답] Eastmoney 과거 캔들 받기 성공: "
                    f"endpoint={EASTMONEY_HISTORY_ENDPOINT}, stock_code={stock_code}, "
                    f"range={beg_date}~{end_date_fmt}, rows={len(df)}, elapsed={api_elapsed:.2f}s"
                )
                logger.info(f"[API 응답] 컬럼: {list(df.columns)}")
                if '日期' in df.columns:
                    logger.info(f"[API 응답] 날짜 범위: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")
                logger.debug(f"[API 응답] 최근 3건:\n{df.tail(3).to_string()}")
            else:
                logger.warning(
                    "[API 응답] Eastmoney 과거 캔들이 비어 있음: "
                    f"endpoint={EASTMONEY_HISTORY_ENDPOINT}, stock_code={stock_code}, "
                    f"range={beg_date}~{end_date_fmt}, elapsed={api_elapsed:.2f}s"
                )
            
            return df
            
        except Exception as e:
            api_elapsed = time.time() - api_start
            category, failure_message = self._build_history_failure_message(
                stock_code=stock_code,
                beg_date=beg_date,
                end_date=end_date_fmt,
                exc=e,
                elapsed=api_elapsed,
            )

            if category == "rate_limit_or_anti_bot":
                logger.warning(failure_message)
                raise RateLimitError(f"efinance 요청이 제한된 것 같습니다: {failure_message}") from e

            logger.error(failure_message)
            raise DataFetchError(f"efinance 데이터 받기 실패: {failure_message}") from e
    
    def _fetch_etf_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        ETF 과거 데이터 조회

        Exchange-traded ETFs have OHLCV data just like regular stocks, so we use
        ef.stock.get_quote_history (the stock K-line API) which returns full
        open/high/low/close/volume data.

        Previously this method used ef.fund.get_quote_history which only returns
        NAV data (单位净值/累计净值) without volume or OHLC, causing:
        - Issue #541: 'got an unexpected keyword argument beg'
        - Issue #527: ETF volume/turnover always showing 0

        Args:
            stock_code: ETF code, e.g. '512400', '159883', '515120'
            start_date: Start date, format 'YYYY-MM-DD'
            end_date: End date, format 'YYYY-MM-DD'

        Returns:
            ETF historical OHLCV DataFrame
        """
        import efinance as ef

        # Anti-ban strategy 1: random User-Agent
        self._set_random_user_agent()

        # Anti-ban strategy 2: enforce rate limit
        self._enforce_rate_limit()

        # Format dates (efinance uses YYYYMMDD)
        beg_date = start_date.replace('-', '')
        end_date_fmt = end_date.replace('-', '')
        secid = _build_eastmoney_etf_secid(stock_code)

        logger.info(
            f"[API 호출] ef.stock.get_quote_history(stock_codes={secid}, "
            f"beg={beg_date}, end={end_date_fmt}, klt=101, fqt=1, "
            f"quote_id_mode=True, use_id_cache=False)  [ETF stock_code={stock_code}]"
        )

        api_start = time.time()
        try:
            # ETFs are exchange-traded securities; use the stock API to get full OHLCV data
            df = _ef_call_with_timeout(
                ef.stock.get_quote_history,
                stock_codes=secid,
                beg=beg_date,
                end=end_date_fmt,
                klt=101,  # daily
                fqt=1,    # forward-adjusted
                quote_id_mode=True,
                use_id_cache=False,
                timeout=60,
            )

            api_elapsed = time.time() - api_start

            if df is not None and not df.empty:
                logger.info(
                    "[API 응답] Eastmoney 과거 캔들 받기 성공 [ETF]: "
                    f"endpoint={EASTMONEY_HISTORY_ENDPOINT}, stock_code={stock_code}, secid={secid}, "
                    f"range={beg_date}~{end_date_fmt}, rows={len(df)}, elapsed={api_elapsed:.2f}s"
                )
                logger.info(f"[API 응답] 컬럼: {list(df.columns)}")
                if '日期' in df.columns:
                    logger.info(f"[API 응답] 날짜 범위: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")
                logger.debug(f"[API 응답] 최근 3건:\n{df.tail(3).to_string()}")
            else:
                logger.warning(
                    "[API 응답] Eastmoney 과거 캔들이 비어 있음 [ETF]: "
                    f"endpoint={EASTMONEY_HISTORY_ENDPOINT}, stock_code={stock_code}, secid={secid}, "
                    f"range={beg_date}~{end_date_fmt}, elapsed={api_elapsed:.2f}s"
                )

            return df

        except Exception as e:
            api_elapsed = time.time() - api_start
            category, failure_message = self._build_history_failure_message(
                stock_code=stock_code,
                beg_date=beg_date,
                end_date=end_date_fmt,
                exc=e,
                elapsed=api_elapsed,
                is_etf=True,
            )

            if category == "rate_limit_or_anti_bot":
                logger.warning(failure_message)
                raise RateLimitError(f"efinance 요청이 제한된 것 같습니다: {failure_message}") from e

            logger.error(failure_message)
            raise DataFetchError(f"efinance ETF 데이터 받기 실패: {failure_message}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        efinance 데이터 표준화
        
        efinance가 돌려주는 컬럼 이름 (중국어):
        股票名称, 股票代码, 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
        
        표준 컬럼 이름으로 바꿔야 함:
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # Column mapping (efinance Chinese column names -> standard English column names)
        column_mapping = {
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount',
            '涨跌幅': 'pct_chg',
            '股票代码': 'code',
            '股票名称': 'name',
        }
        
        # 컬럼 이름 변경
        df = df.rename(columns=column_mapping)
        
        # Fallback: if OHLC columns are missing (e.g. very old data path), fill from close
        if 'close' in df.columns and 'open' not in df.columns:
            df['open'] = df['close']
            df['high'] = df['close']
            df['low'] = df['close']
            
        # Fill volume and amount if missing
        if 'volume' not in df.columns:
            df['volume'] = 0
        if 'amount' not in df.columns:
            df['amount'] = 0

        
        # code 컬럼이 없으면 직접 추가
        if 'code' not in df.columns:
            df['code'] = stock_code
        
        # 필요한 컬럼만 남김
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df
    
    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        실시간 시세 조회
        
        데이터 출처: ef.stock.get_realtime_quotes()
        ETF 데이터 출처: ef.stock.get_realtime_quotes(['ETF'])
        등록된 지수: 둥팡차이푸 단일 종목 secid 인터페이스（get_index_realtime_quote）
        
        Args:
            stock_code: 종목 코드
            
        Returns:
            UnifiedRealtimeQuote 객체, 실패하면 None
        """
        # 등록된 지수는 둥팡차이푸 단일 종목 secid 인터페이스로 조회（Story 1.5）
        target = parse_analysis_target(stock_code)
        if target.asset_type == ParseStatus.INDEX:
            return self.get_index_realtime_quote(target.canonical_id)

        # ETF는 ETF 실시간 시세 인터페이스로 따로 요청해야 함
        if _is_etf_code(stock_code):
            return self._get_etf_realtime_quote(stock_code)

        import efinance as ef
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "efinance"
        
        # 서킷 브레이커 상태 확인
        if not circuit_breaker.is_available(source_key):
            logger.info(f"[서킷 브레이커] 데이터 소스 {source_key}가 차단 상태라 건너뜀")
            return None
        
        try:
            # 캐시 확인
            current_time = time.time()
            if (_realtime_cache['data'] is not None and 
                current_time - _realtime_cache['timestamp'] < _realtime_cache['ttl']):
                df = _realtime_cache['data']
                cache_age = int(current_time - _realtime_cache['timestamp'])
                logger.debug(f"[캐시 적중] 실시간 시세(efinance) - 캐시 나이 {cache_age}s/{_realtime_cache['ttl']}s")
            else:
                # 전체 새로고침 실행
                logger.info(f"[캐시 없음] 실시간 시세(efinance) 전체 새로고침")
                # 차단 방지
                self._set_random_user_agent()
                self._enforce_rate_limit()
                
                logger.info(f"[API 호출] ef.stock.get_realtime_quotes() 실시간 시세 조회 중...")
                import time as _time
                api_start = _time.time()
                
                # efinance 실시간 시세 API (with timeout to avoid indefinite hangs)
                df = _ef_call_with_timeout(ef.stock.get_realtime_quotes)
                
                api_elapsed = _time.time() - api_start
                logger.info(f"[API 응답] ef.stock.get_realtime_quotes 성공: {len(df)}개 종목, 소요 {api_elapsed:.2f}s")
                circuit_breaker.record_success(source_key)
                
                # 캐시 갱신
                _realtime_cache['data'] = df
                _realtime_cache['timestamp'] = current_time
                logger.info(f"[캐시 갱신] 실시간 시세(efinance) 캐시를 새로 고침，TTL={_realtime_cache['ttl']}s")
            
            # 요청한 종목 찾기
            # efinance가 돌려주는 컬럼 이름은 '股票代码' 또는 'code'일 수 있음
            code_col = '股票代码' if '股票代码' in df.columns else 'code'
            row = df[df[code_col] == stock_code]
            if row.empty:
                logger.info(f"[API 응답] 종목 {stock_code}의 실시간 시세를 찾지 못함")
                return None
            
            row = row.iloc[0]
            
            # realtime_types.py의 공통 변환 함수 사용
            # 컬럼 이름 확인 (중국어 또는 영어일 수 있음)
            name_col = '股票名称' if '股票名称' in df.columns else 'name'
            price_col = '最新价' if '最新价' in df.columns else 'price'
            pct_col = '涨跌幅' if '涨跌幅' in df.columns else 'pct_chg'
            chg_col = '涨跌额' if '涨跌额' in df.columns else 'change'
            vol_col = '成交量' if '成交量' in df.columns else 'volume'
            amt_col = '成交额' if '成交额' in df.columns else 'amount'
            turn_col = '换手率' if '换手率' in df.columns else 'turnover_rate'
            amp_col = '振幅' if '振幅' in df.columns else 'amplitude'
            high_col = '最高' if '最高' in df.columns else 'high'
            low_col = '最低' if '最低' in df.columns else 'low'
            open_col = '开盘' if '开盘' in df.columns else 'open'
            # efinance는 거래량 비율, PER, 시가총액 등도 돌려줌
            vol_ratio_col = '量比' if '量比' in df.columns else 'volume_ratio'
            pe_col = '市盈率' if '市盈率' in df.columns else 'pe_ratio'
            total_mv_col = '总市值' if '总市值' in df.columns else 'total_mv'
            circ_mv_col = '流通市值' if '流通市值' in df.columns else 'circ_mv'
            
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get(name_col, '')),
                source=RealtimeSource.EFINANCE,
                price=safe_float(row.get(price_col)),
                change_pct=safe_float(row.get(pct_col)),
                change_amount=safe_float(row.get(chg_col)),
                volume=safe_int(row.get(vol_col)),
                amount=safe_float(row.get(amt_col)),
                turnover_rate=safe_float(row.get(turn_col)),
                amplitude=safe_float(row.get(amp_col)),
                high=safe_float(row.get(high_col)),
                low=safe_float(row.get(low_col)),
                open_price=safe_float(row.get(open_col)),
                volume_ratio=safe_float(row.get(vol_ratio_col)),  # 거래량 비율
                pe_ratio=safe_float(row.get(pe_col)),  # PER
                total_mv=safe_float(row.get(total_mv_col)),  # 시가총액
                circ_mv=safe_float(row.get(circ_mv_col)),  # 유통 시가총액
            )
            
            logger.info(f"[실시간 시세-efinance] {stock_code} {quote.name}: 가격={quote.price}, 등락={quote.change_pct}%, "
                       f"거래량 비율={quote.volume_ratio}, 회전율={quote.turnover_rate}%")
            return quote
            
        except FuturesTimeoutError:
            logger.info(f"[시간 초과] ef.stock.get_realtime_quotes()가 {_EF_CALL_TIMEOUT}s를 넘어 {stock_code}를 건너뜀")
            circuit_breaker.record_failure(source_key, "timeout")
            return None
        except Exception as e:
            logger.info(f"[API 오류] {stock_code} 실시간 시세(efinance) 받기 실패: {e}")
            circuit_breaker.record_failure(source_key, str(e))
            return None

    def get_index_realtime_quote(
        self, stock_code: str
    ) -> Optional[UnifiedRealtimeQuote]:
        """Fetch a registered CN index quote via the Eastmoney single-stock secid API.

        Supports SH (``1.{code}``), SZ (``0.{code}``) and CSI (``2.{code}``)
        secid forms. This is the only realtime source for CSI indices and the
        fallback for SH/SZ indices when Tencent/Sina fail (Story 1.5).
        """
        target = parse_analysis_target(stock_code)
        if target.asset_type != ParseStatus.INDEX or target.matched_index is None:
            return None
        entry = target.matched_index
        exchange = entry.exchange.upper()
        if exchange == "SH":
            secid = f"1.{entry.bare_code}"
        elif exchange == "SZ":
            secid = f"0.{entry.bare_code}"
        elif exchange == "CSI":
            secid = f"2.{entry.bare_code}"
        else:
            return None

        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "efinance_index"
        if not circuit_breaker.is_available(source_key):
            logger.info(f"[서킷 브레이커] 데이터 소스 {source_key}가 차단 상태라 건너뜀")
            return None

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()
            response = requests.get(
                "https://push2.eastmoney.com/api/qt/stock/get",
                params={
                    "secid": secid,
                    "fltt": "2",
                    "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f168,f169,f170,f171",
                },
                timeout=10,
            )
            if response.status_code != 200:
                circuit_breaker.record_failure(source_key, f"HTTP {response.status_code}")
                return None
            payload = response.json()
            data = payload.get("data") or {}
            price = safe_float(data.get("f43"))
            if price is None or price <= 0:
                circuit_breaker.record_failure(source_key, "empty quote payload")
                return None
            circuit_breaker.record_success(source_key)
            quote = UnifiedRealtimeQuote(
                code=target.canonical_id,
                name=str(data.get("f58") or entry.display_name or ""),
                source=RealtimeSource.EFINANCE,
                price=price,
                change_pct=safe_float(data.get("f170")),
                change_amount=safe_float(data.get("f169")),
                volume=safe_int(data.get("f47")),
                amount=safe_float(data.get("f48")),
                amplitude=safe_float(data.get("f171")),
                high=safe_float(data.get("f44")),
                low=safe_float(data.get("f45")),
                open_price=safe_float(data.get("f46")),
                pre_close=safe_float(data.get("f60")),
                volume_ratio=safe_float(data.get("f168")),
            )
            logger.info(
                "[실시간 시세-둥팡차이푸 지수] %s %s: 가격=%s, 등락=%s%%, secid=%s",
                target.canonical_id,
                quote.name,
                quote.price,
                quote.change_pct,
                secid,
            )
            return quote
        except Exception as e:
            logger.info(f"[API 오류] {target.canonical_id} 지수 실시간 시세(둥팡차이푸) 받기 실패: {e}")
            circuit_breaker.record_failure(source_key, str(e))
            return None

    def _get_etf_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        ETF 실시간 시세 조회

        efinance 기본 실시간 인터페이스는 주식만 돌려주므로, ETF는 ['ETF']를 명시해야 함.
        """
        import efinance as ef
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "efinance_etf"

        if not circuit_breaker.is_available(source_key):
            logger.info(f"[서킷 브레이커] 데이터 소스 {source_key}가 차단 상태라 건너뜀")
            return None

        try:
            current_time = time.time()
            if (
                _etf_realtime_cache['data'] is not None and
                current_time - _etf_realtime_cache['timestamp'] < _etf_realtime_cache['ttl']
            ):
                df = _etf_realtime_cache['data']
                cache_age = int(current_time - _etf_realtime_cache['timestamp'])
                logger.debug(f"[캐시 적중] ETF 실시간 시세(efinance) - 캐시 나이 {cache_age}s/{_etf_realtime_cache['ttl']}s")
            else:
                self._set_random_user_agent()
                self._enforce_rate_limit()

                logger.info("[API 호출] ef.stock.get_realtime_quotes(['ETF']) ETF 실시간 시세 조회 중...")
                import time as _time
                api_start = _time.time()
                df = _ef_call_with_timeout(ef.stock.get_realtime_quotes, ['ETF'])
                api_elapsed = _time.time() - api_start

                if df is not None and not df.empty:
                    logger.info(f"[API 응답] ETF 실시간 시세 성공: {len(df)}건, 소요 {api_elapsed:.2f}s")
                    circuit_breaker.record_success(source_key)
                else:
                    logger.info(f"[API 응답] ETF 실시간 시세가 비어 있음, 소요 {api_elapsed:.2f}s")
                    df = pd.DataFrame()

                _etf_realtime_cache['data'] = df
                _etf_realtime_cache['timestamp'] = current_time

            if df is None or df.empty:
                logger.info(f"[실시간 시세] ETF 실시간 시세 데이터가 비어 있어(efinance) {stock_code}를 건너뜀")
                return None

            code_col = '股票代码' if '股票代码' in df.columns else 'code'
            code_series = df[code_col].astype(str).str.zfill(6)
            target_code = str(stock_code).strip().zfill(6)
            row = df[code_series == target_code]
            if row.empty:
                logger.info(f"[API 응답] ETF {stock_code}의 실시간 시세를 찾지 못함(efinance)")
                return None

            row = row.iloc[0]
            name_col = '股票名称' if '股票名称' in df.columns else 'name'
            price_col = '最新价' if '最新价' in df.columns else 'price'
            pct_col = '涨跌幅' if '涨跌幅' in df.columns else 'pct_chg'
            chg_col = '涨跌额' if '涨跌额' in df.columns else 'change'
            vol_col = '成交量' if '成交量' in df.columns else 'volume'
            amt_col = '成交额' if '成交额' in df.columns else 'amount'
            turn_col = '换手率' if '换手率' in df.columns else 'turnover_rate'
            amp_col = '振幅' if '振幅' in df.columns else 'amplitude'
            high_col = '最高' if '最高' in df.columns else 'high'
            low_col = '最低' if '最低' in df.columns else 'low'
            open_col = '开盘' if '开盘' in df.columns else 'open'

            quote = UnifiedRealtimeQuote(
                code=target_code,
                name=str(row.get(name_col, '')),
                source=RealtimeSource.EFINANCE,
                price=safe_float(row.get(price_col)),
                change_pct=safe_float(row.get(pct_col)),
                change_amount=safe_float(row.get(chg_col)),
                volume=safe_int(row.get(vol_col)),
                amount=safe_float(row.get(amt_col)),
                turnover_rate=safe_float(row.get(turn_col)),
                amplitude=safe_float(row.get(amp_col)),
                high=safe_float(row.get(high_col)),
                low=safe_float(row.get(low_col)),
                open_price=safe_float(row.get(open_col)),
            )

            logger.info(
                f"[ETF 실시간 시세-efinance] {target_code} {quote.name}: "
                f"가격={quote.price}, 등락={quote.change_pct}%, 회전율={quote.turnover_rate}%"
            )
            return quote
        except Exception as e:
            logger.info(f"[API 오류] ETF {stock_code} 실시간 시세(efinance) 받기 실패: {e}")
            circuit_breaker.record_failure(source_key, str(e))
            return None

    def get_main_indices(self, region: str = "cn") -> Optional[List[Dict[str, Any]]]:
        """
        주요 지수 실시간 시세 조회 (efinance), A주만 지원
        """
        if region != "cn":
            return None
        import efinance as ef

        indices_map = {
            '000001': ('上证指数', 'sh000001'),
            '399001': ('深证成指', 'sz399001'),
            '399006': ('创业板指', 'sz399006'),
            '000688': ('科创50', 'sh000688'),
            '000016': ('上证50', 'sh000016'),
            '000300': ('沪深300', 'sh000300'),
        }

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API 호출] ef.stock.get_realtime_quotes(['沪深系列指数']) 지수 시세 조회 중...")
            import time as _time
            api_start = _time.time()
            df = _ef_call_with_timeout(ef.stock.get_realtime_quotes, ['沪深系列指数'])
            api_elapsed = _time.time() - api_start

            if df is None or df.empty:
                logger.warning(f"[API 응답] 지수 시세가 비어 있음, 소요 {api_elapsed:.2f}s")
                return None

            logger.info(f"[API 응답] 지수 시세 성공: {len(df)}건, 소요 {api_elapsed:.2f}s")
            code_col = '股票代码' if '股票代码' in df.columns else 'code'
            code_series = df[code_col].astype(str).str.zfill(6)

            results: List[Dict[str, Any]] = []
            for code, (name, full_code) in indices_map.items():
                row = df[code_series == code]
                if row.empty:
                    continue
                item = row.iloc[0]

                price_col = '最新价' if '最新价' in df.columns else 'price'
                pct_col = '涨跌幅' if '涨跌幅' in df.columns else 'pct_chg'
                chg_col = '涨跌额' if '涨跌额' in df.columns else 'change'
                open_cols = [column for column in ('今开', '开盘', 'open') if column in df.columns]
                high_col = '最高' if '最高' in df.columns else 'high'
                low_col = '最低' if '最低' in df.columns else 'low'
                vol_col = '成交量' if '成交量' in df.columns else 'volume'
                amt_col = '成交额' if '成交额' in df.columns else 'amount'
                amp_col = '振幅' if '振幅' in df.columns else 'amplitude'

                current = safe_float(item.get(price_col, 0))
                change_amount = safe_float(item.get(chg_col, 0))
                open_price = 0.0
                for column in open_cols:
                    candidate = safe_float(item.get(column), default=None)
                    if candidate not in (None, 0.0):
                        open_price = candidate
                        break
                if open_price == 0.0 and open_cols:
                    open_price = safe_float(item.get(open_cols[0], 0), 0)

                results.append({
                    'code': full_code,
                    'name': name,
                    'current': current,
                    'change': change_amount,
                    'change_pct': safe_float(item.get(pct_col, 0)),
                    'open': open_price,
                    'high': safe_float(item.get(high_col, 0)),
                    'low': safe_float(item.get(low_col, 0)),
                    'prev_close': current - change_amount if current or change_amount else 0,
                    'volume': safe_float(item.get(vol_col, 0)),
                    'amount': safe_float(item.get(amt_col, 0)),
                    'amplitude': safe_float(item.get(amp_col, 0)),
                })

            if results:
                logger.info(f"[efinance] 지수 시세 {len(results)}건 받음")
            return results if results else None
        except Exception as e:
            logger.error(f"[efinance] 지수 시세 받기 실패: {e}")
            return None

    def get_market_stats(self) -> Optional[Dict[str, Any]]:
        """
        시장 상승·하락 통계 조회 (efinance)
        """
        import efinance as ef

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            current_time = time.time()
            if (
                _realtime_cache['data'] is not None and
                current_time - _realtime_cache['timestamp'] < _realtime_cache['ttl']
            ):
                df = _realtime_cache['data']
                logger.info(
                    "[MarketStats] component=market_stats provider=EfinanceFetcher "
                    "api=ef.stock.get_realtime_quotes action=cache_hit cache_age=%.0fs",
                    current_time - _realtime_cache['timestamp'],
                )
            else:
                started_at = time.monotonic()
                logger.info(
                    "[MarketStats] component=market_stats provider=EfinanceFetcher "
                    "api=ef.stock.get_realtime_quotes action=request_start"
                )
                df = _ef_call_with_timeout(ef.stock.get_realtime_quotes)
                elapsed = time.monotonic() - started_at
                logger.info(
                    "[MarketStats] component=market_stats provider=EfinanceFetcher "
                    "api=ef.stock.get_realtime_quotes action=request_complete elapsed=%.2fs",
                    elapsed,
                )
                _realtime_cache['data'] = df
                _realtime_cache['timestamp'] = current_time

            if df is None or df.empty:
                logger.warning(
                    "[MarketStats] component=market_stats provider=EfinanceFetcher "
                    "api=ef.stock.get_realtime_quotes action=parse status=empty"
                )
                return None

            return self._calc_market_stats(df)
        except Exception as e:
            logger.error(
                "[MarketStats] component=market_stats provider=EfinanceFetcher "
                "api=ef.stock.get_realtime_quotes action=failed error=%s",
                e,
            )
            return None
        
    def _calc_market_stats(
        self,
        df: pd.DataFrame,
        ) -> Optional[Dict[str, Any]]:
        """시세 DataFrame으로 상승·하락 통계를 계산합니다."""
        import numpy as np

        df = df.copy()
        
        # 1. 비교용 기본 데이터 추출: 현재가, 전일 종가
        # 여러 인터페이스의 컬럼 이름을 모두 지원: sina/em efinance tushare xtdata
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
            
            # 거래정지 종목 거르기: efinance는 거래정지 종목 가격이 '-'로 빠질 때가 있고, em은 none으로 표시됨
            if pd.isna(current_price) or pd.isna(pre_close) or current_price in ['-'] or pre_close in ['-'] or amount == 0:
                continue
            
            # em, efinance는 str이라 float로 변환 필요
            current_price = float(current_price)
            pre_close = float(pre_close)
            
            # 접두어를 뗀 숫자 코드만 얻기
            pure_code = normalize_stock_code(str(code)) 

            # A. 종목별 가격제한폭 비율 결정 (숫자 코드로 판단)
            if is_bse_code(pure_code): 
                ratio = 0.30
            elif is_kc_cy_stock(pure_code): #pure_code.startswith(('688', '30')):
                ratio = 0.20
            elif is_st_stock(name): #'ST' in str_name:
                ratio = 0.05
            else:
                ratio = 0.10

            # B. A주 규칙대로 상·하한가 계산: 전일 종가 * (1 ± 비율) -> 소수 둘째 자리 반올림
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
                
        # 개수 집계
        stats = {
            'up_count': up_count,
            'down_count': down_count,
            'flat_count': flat_count,
            'limit_up_count': limit_up_count,
            'limit_down_count': limit_down_count,
            'total_amount': 0.0,
        }
        
        # 거래대금 집계
        if amount_col and amount_col in df.columns:
            df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce')
            stats['total_amount'] = (df[amount_col].sum() / 1e8)
            
        return stats

    def get_sector_rankings(self, n: int = 5) -> Optional[Tuple[List[Dict], List[Dict]]]:
        """
        업종 등락 순위 조회 (efinance)
        """
        import efinance as ef

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API 호출] ef.stock.get_realtime_quotes(['行业板块']) 업종 시세 조회 중...")
            df = _ef_call_with_timeout(ef.stock.get_realtime_quotes, ['行业板块'])
            if df is None or df.empty:
                logger.warning("[efinance] 업종 시세 데이터가 비어 있음")
                return None

            change_col = '涨跌幅' if '涨跌幅' in df.columns else 'pct_chg'
            name_col = '股票名称' if '股票名称' in df.columns else 'name'
            if change_col not in df.columns or name_col not in df.columns:
                return None

            df[change_col] = pd.to_numeric(df[change_col], errors='coerce')
            df = df.dropna(subset=[change_col])
            top = df.nlargest(n, change_col)
            bottom = df.nsmallest(n, change_col)

            top_sectors = [
                {'name': str(row[name_col]), 'change_pct': float(row[change_col])}
                for _, row in top.iterrows()
            ]
            bottom_sectors = [
                {'name': str(row[name_col]), 'change_pct': float(row[change_col])}
                for _, row in bottom.iterrows()
            ]
            return top_sectors, bottom_sectors
        except Exception as e:
            logger.error(f"[efinance] 업종 순위 받기 실패: {e}")
            return None
    
    def get_base_info(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        종목 기본 정보 조회
        
        데이터 출처: ef.stock.get_base_info()
        포함: PER, PBR, 업종, 시가총액, 유통 시가총액, ROE, 순이익률 등
        
        Args:
            stock_code: 종목 코드
            
        Returns:
            기본 정보가 담긴 딕셔너리, 실패하면 None
        """
        import efinance as ef
        
        try:
            # 차단 방지
            self._set_random_user_agent()
            self._enforce_rate_limit()
            
            logger.info(f"[API 호출] ef.stock.get_base_info(stock_codes={stock_code}) 기본 정보 조회 중...")
            import time as _time
            api_start = _time.time()
            
            info = _ef_call_with_timeout(ef.stock.get_base_info, stock_code)
            
            api_elapsed = _time.time() - api_start
            logger.info(f"[API 응답] ef.stock.get_base_info 성공, 소요 {api_elapsed:.2f}s")
            
            if info is None:
                logger.warning(f"[API 응답] {stock_code} 기본 정보를 받지 못함")
                return None
            
            # 딕셔너리로 변환
            if isinstance(info, pd.Series):
                return info.to_dict()
            elif isinstance(info, pd.DataFrame):
                if not info.empty:
                    return info.iloc[0].to_dict()
            
            return None
            
        except Exception as e:
            logger.error(f"[API 오류] {stock_code} 기본 정보 받기 실패: {e}")
            return None
    
    def get_belong_board(self, stock_code: str) -> Optional[pd.DataFrame]:
        """
        종목이 속한 업종 조회
        
        데이터 출처: ef.stock.get_belong_board()
        
        Args:
            stock_code: 종목 코드
            
        Returns:
            소속 업종 DataFrame, 실패하면 None
        """
        import efinance as ef
        
        try:
            # 차단 방지
            self._set_random_user_agent()
            self._enforce_rate_limit()
            
            logger.info(f"[API 호출] ef.stock.get_belong_board(stock_code={stock_code}) 소속 업종 조회 중...")
            import time as _time
            api_start = _time.time()
            
            df = _ef_call_with_timeout(ef.stock.get_belong_board, stock_code)
            
            api_elapsed = _time.time() - api_start
            
            if df is not None and not df.empty:
                logger.info(f"[API 응답] ef.stock.get_belong_board 성공: 업종 {len(df)}개, 소요 {api_elapsed:.2f}s")
                return df
            else:
                logger.warning(f"[API 응답] {stock_code} 업종 정보를 받지 못함")
                return None
            
        except FuturesTimeoutError:
            logger.warning(f"[시간 초과] ef.stock.get_belong_board({stock_code})가 {_EF_CALL_TIMEOUT}s를 넘어 건너뜀")
            return None
        except Exception as e:
            logger.error(f"[API 오류] {stock_code} 소속 업종 받기 실패: {e}")
            return None
    
    def get_enhanced_data(self, stock_code: str, days: int = 60) -> Dict[str, Any]:
        """
        확장 데이터 조회 (과거 캔들 + 실시간 시세 + 기본 정보)
        
        Args:
            stock_code: 종목 코드
            days: 과거 데이터 일수
            
        Returns:
            모든 데이터가 담긴 딕셔너리
        """
        result = {
            'code': stock_code,
            'daily_data': None,
            'realtime_quote': None,
            'base_info': None,
            'belong_board': None,
        }
        
        # 일봉 데이터 조회
        try:
            df = self.get_daily_data(stock_code, days=days)
            result['daily_data'] = df
        except Exception as e:
            logger.error(f"{stock_code} 일봉 데이터 받기 실패: {e}")
        
        # 실시간 시세 조회
        result['realtime_quote'] = self.get_realtime_quote(stock_code)
        
        # 기본 정보 조회
        result['base_info'] = self.get_base_info(stock_code)
        
        # 소속 업종 조회
        result['belong_board'] = self.get_belong_board(stock_code)
        
        return result


if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = EfinanceFetcher()
    
    # 일반 주식 테스트
    print("=" * 50)
    print("일반 주식 데이터 받기 테스트 (efinance)")
    print("=" * 50)
    try:
        df = fetcher.get_daily_data('600519')  # 마오타이
        print(f"[주식] 받기 성공, 총 {len(df)}건")
        print(df.tail())
    except Exception as e:
        print(f"[주식] 받기 실패: {e}")
    
    # ETF 테스트
    print("\n" + "=" * 50)
    print("ETF 데이터 받기 테스트 (efinance)")
    print("=" * 50)
    try:
        df = fetcher.get_daily_data('512400')  # 비철금속 대표 ETF
        print(f"[ETF] 받기 성공, 총 {len(df)}건")
        print(df.tail())
    except Exception as e:
        print(f"[ETF] 받기 실패: {e}")
    
    # 실시간 시세 테스트
    print("\n" + "=" * 50)
    print("실시간 시세 받기 테스트 (efinance)")
    print("=" * 50)
    try:
        quote = fetcher.get_realtime_quote('600519')
        if quote:
            print(f"[실시간 시세] {quote.name}: 가격={quote.price}, 등락률={quote.change_pct}%")
        else:
            print("[실시간 시세] 데이터를 받지 못함")
    except Exception as e:
        print(f"[실시간 시세] 받기 실패: {e}")
    
    # 기본 정보 테스트
    print("\n" + "=" * 50)
    print("기본 정보 받기 테스트 (efinance)")
    print("=" * 50)
    try:
        info = fetcher.get_base_info('600519')
        if info:
            print(f"[기본 정보] PER={info.get('市盈率(动)', 'N/A')}, PBR={info.get('市净率', 'N/A')}")
        else:
            print("[기본 정보] 데이터를 받지 못함")
    except Exception as e:
        print(f"[기본 정보] 받기 실패: {e}")

    # 시장 통계 테스트 
    print("\n" + "=" * 50)
    print("Testing get_market_stats (efinance)")
    print("=" * 50)
    try:
        stats = fetcher.get_market_stats()
        if stats:
            print(f"Market Stats successfully computed:")
            print(f"Up: {stats['up_count']} (Limit Up: {stats['limit_up_count']})")
            print(f"Down: {stats['down_count']} (Limit Down: {stats['limit_down_count']})")
            print(f"Flat: {stats['flat_count']}")
            print(f"Total Amount: {stats['total_amount']:.2f} 억 위안 (Yi)")
        else:
            print("Failed to compute market stats.")
    except Exception as e:
        print(f"Failed to compute market stats: {e}")
