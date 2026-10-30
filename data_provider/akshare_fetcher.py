# -*- coding: utf-8 -*-
"""
===================================
AkshareFetcher - 메인 데이터 소스 (Priority 1)
===================================

데이터 출처:
1. 둥팡차이푸 크롤러(akshare 라이브러리 사용) - 기본 데이터 소스
2. 시나 파이낸스 API - 예비 데이터 소스
3. 텐센트 파이낸스 API - 예비 데이터 소스

특징: 무료, Token 필요 없음, 데이터가 풍부함
위험: 크롤링 방식이라 사이트에서 차단하기 쉬움

차단 방지 전략:
1. 요청할 때마다 2-5초 무작위로 쉬기
2. User-Agent를 무작위로 바꾸기
3. tenacity로 점점 간격을 늘리며 재시도
4. 서킷 브레이커: 연속으로 실패하면 잠시 자동으로 쉼

추가 데이터:
- 실시간 시세: 거래량 비율, 회전율, PER, PBR, 시가총액, 유통 시가총액
- 매물대 분포: 수익 비율, 평균 단가, 매물 집중도
"""

import logging
import multiprocessing
import os
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from src.patches.eastmoney_patch import eastmoney_patch
from src.config import get_config
from src.services.stock_list_parser import ParseStatus, parse_analysis_target
from .base import BaseFetcher, DataFetchError, RateLimitError, STANDARD_COLUMNS, is_bse_code, is_st_stock, is_kc_cy_stock, normalize_stock_code
from .realtime_types import (
    UnifiedRealtimeQuote, ChipDistribution, RealtimeSource,
    get_realtime_circuit_breaker, get_chip_circuit_breaker,
    safe_float, safe_int  # 공통 타입 변환 함수 사용
)
from .us_index_mapping import is_us_index_code, is_us_stock_code


# 예전 코드와 호환되도록 RealtimeQuote 별칭을 남겨 둠
RealtimeQuote = UnifiedRealtimeQuote


logger = logging.getLogger(__name__)

SINA_REALTIME_ENDPOINT = "hq.sinajs.cn/list"
TENCENT_REALTIME_ENDPOINT = "qt.gtimg.cn/q"
_AKSHARE_HISTORY_CALL_TIMEOUT = 30.0
_AKSHARE_MARKET_STATS_CALL_TIMEOUT = 30.0
_AKSHARE_TIMEOUT_PROCESS_JOIN_GRACE = 1.0
_AKSHARE_TIMEOUT_PROCESS_START_METHOD = "spawn"


# 무작위로 바꿔 쓸 User-Agent 목록
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]


# 실시간 시세 캐시(같은 요청 반복 방지)
# TTL은 20분(1200초):
# - 일괄 분석: 보통 30종목을 5분 안에 끝내므로 20분이면 충분
# - 실시간성: 주식 분석에는 초 단위 데이터가 필요 없어 20분 지연은 괜찮음
# - 차단 방지: API 호출 횟수를 줄임
_realtime_cache: Dict[str, Any] = {
    'data': None,
    'timestamp': 0,
    'ttl': 1200  # 캐시 유효 시간 20분
}

# ETF 실시간 시세 캐시
_etf_realtime_cache: Dict[str, Any] = {
    'data': None,
    'timestamp': 0,
    'ttl': 1200  # 캐시 유효 시간 20분
}

# 홍콩 주식 실시간 시세 캐시. stock_hk_spot_em()은 시장 전체 데이터를 주므로 한 번 부를 때 부담이 큼.
_hk_realtime_cache: Dict[str, Any] = {
    'data': None,
    'timestamp': 0,
    'ttl': 1200,  # 캐시 유효 시간 20분
    'failure_ttl': 30,
    'last_result': None,
}
_hk_realtime_cache_lock = threading.Lock()


def _is_etf_code(stock_code: str) -> bool:
    """
    코드가 ETF인지 판단
    
    ETF 코드 규칙:
    - 상하이거래소 ETF: 51xxxx, 52xxxx, 56xxxx, 58xxxx
    - 선전거래소 ETF: 15xxxx, 16xxxx, 18xxxx
    
    Args:
        stock_code: 주식/펀드 코드
        
    Returns:
        ETF 코드면 True, 일반 주식 코드면 False
    """
    etf_prefixes = ('51', '52', '56', '58', '15', '16', '18')
    code = stock_code.strip().split('.')[0]
    return code.startswith(etf_prefixes) and len(code) == 6


def _is_hk_code(stock_code: str) -> bool:
    """
    코드가 홍콩 주식인지 판단

    홍콩 주식 코드 규칙:
    - 4-5자리 숫자 코드, 예: '00700' (텐센트), '0001' (CK허치슨), '0941' (차이나모바일)
    - 일부 홍콩 주식 코드는 접두어가 붙음, 예: 'hk00700', 'hk1810'

    ``data_provider.base._is_hk_market`` 및
    ``YfinanceFetcher._convert_stock_code`` / ``LongbridgeFetcher._is_hk_code``
    와 접두어 없는 홍콩 코드 자릿수(4-5자리)를 똑같이 맞춰서 ``DataFetcherManager``
    라우팅은 HK로 판단했는데 ``AkshareFetcher`` 안에서 거절되어 호출 흐름이 끊기는 일을 막음.

    Args:
        stock_code: 주식 코드

    Returns:
        홍콩 주식 코드면 True, 아니면 False
    """
    # 'hk' 접두어가 있으면 떼고 숫자로만 되어 있는지 확인
    code = stock_code.strip().lower()
    if code.endswith('.hk'):
        numeric_part = code[:-3]
        return numeric_part.isdigit() and 1 <= len(numeric_part) <= 5
    if code.startswith('hk'):
        # hk 접두어가 있으면 무조건 홍콩 주식, 떼고 나면 숫자 1-5자리여야 함
        numeric_part = code[2:]
        return numeric_part.isdigit() and 1 <= len(numeric_part) <= 5
    # 접두어가 없으면 숫자 4-5자리일 때만 홍콩 주식으로 봄(A주 / BSE는 모두 6자리라 겹치지 않음)
    return code.isdigit() and 4 <= len(code) <= 5


def _normalize_tencent_volume(fields: List[str]) -> Optional[int]:
    """
    텐센트 실시간 시세의 거래량을 '주' 단위로 맞춤.

    텐센트 응답의 6번 필드는 공개 설명과 실제 값이 완전히 같지 않음.
    회전율, 가격, 유통 시가총액으로 먼저 교차 검증해서 원래 값과 예전 '로트→주' 변환 값 중
    더 가까운 쪽을 고름. 교차 검증이 안 되면 예전 '로트→주' 변환을 그대로 써서
    예전 형식의 텐센트 응답이 실제 거래량의 1/100로 나오는 일을 막음.
    """
    if len(fields) <= 6 or not fields[6]:
        return None

    raw_volume = safe_int(fields[6])
    if raw_volume is None:
        return None

    price = safe_float(fields[3]) if len(fields) > 3 else None
    turnover_rate = safe_float(fields[38]) if len(fields) > 38 else None
    circ_mv_yi = safe_float(fields[44]) if len(fields) > 44 and fields[44] else None
    circ_mv = circ_mv_yi * 100000000 if circ_mv_yi is not None else None

    if price and price > 0 and turnover_rate and turnover_rate > 0 and circ_mv and circ_mv > 0:
        expected_volume = (circ_mv / price) * (turnover_rate / 100)
        if expected_volume > 0:
            raw_delta = abs(raw_volume - expected_volume)
            hand_to_share_volume = raw_volume * 100
            hand_delta = abs(hand_to_share_volume - expected_volume)
            return raw_volume if raw_delta <= hand_delta else hand_to_share_volume

    return raw_volume * 100


def _parse_tencent_amount(fields: List[str]) -> Optional[float]:
    """
    텐센트 실시간 시세의 거래대금을 읽음. 단위는 위안.

    실제 응답을 보면 35번 필드에 더 정확한 '가격/거래량/거래대금'
    세 값이 들어 있음. 37번 필드는 예전 '만 위안' 단위의 대체용 필드.
    """
    if len(fields) > 35 and fields[35]:
        parts = fields[35].split("/")
        if len(parts) >= 3:
            precise_amount = safe_float(parts[2])
            if precise_amount is not None:
                return precise_amount

    amount_wan = safe_float(fields[37]) if len(fields) > 37 and fields[37] else None
    return amount_wan * 10000 if amount_wan is not None else None


def is_hk_stock_code(stock_code: str) -> bool:
    """
    Public API: determine if a stock code is a Hong Kong stock.

    Delegates to _is_hk_code for internal compatibility.

    Args:
        stock_code: Stock code (e.g. '00700', 'hk00700')

    Returns:
        True if HK stock, False otherwise
    """
    return _is_hk_code(stock_code)


def _is_us_code(stock_code: str) -> bool:
    """
    코드가 미국 주식인지 판단(미국 지수는 제외).

    us_index_mapping 모듈의 is_us_stock_code()에 맡김.

    Args:
        stock_code: 주식 코드

    Returns:
        미국 주식 코드면 True, 아니면 False

    Examples:
        >>> _is_us_code('AAPL')
        True
        >>> _is_us_code('TSLA')
        True
        >>> _is_us_code('SPX')
        False
        >>> _is_us_code('600519')
        False
    """
    return is_us_stock_code(stock_code)


def _to_sina_tx_symbol(stock_code: str) -> str:
    """Convert 6-digit A-share code to sh/sz/bj prefixed symbol for Sina/Tencent APIs.

    Explicit sh/sz/bj prefixes are preserved (``sh000016`` -> ``sh000016``) so
    registered index codes keep their index identity instead of degrading into
    the colliding stock symbol (Story 1.5).
    """
    raw = (stock_code or "").strip()
    lower = raw.lower()
    for prefix in ("sh", "sz", "bj"):
        if lower.startswith(prefix) and len(raw) > len(prefix):
            candidate = raw[len(prefix):]
            if candidate.isdigit() and len(candidate) == 6:
                return f"{prefix}{candidate}"
    base = (raw.split(".")[0] if "." in raw else raw).strip()
    if is_bse_code(base):
        return f"bj{base}"
    # Shanghai: 60xxxx, 5xxxx (ETF), 90xxxx (B-shares)
    if base.startswith(("6", "5", "90")):
        return f"sh{base}"
    return f"sz{base}"


def _classify_realtime_http_error(exc: Exception) -> Tuple[str, str]:
    """
    Classify Sina/Tencent realtime quote failures into stable categories.
    """
    detail = str(exc).strip() or type(exc).__name__
    lowered = detail.lower()

    remote_disconnect_keywords = (
        "remotedisconnected",
        "remote end closed connection without response",
        "connection aborted",
        "connection broken",
        "protocolerror",
        "chunkedencodingerror",
    )
    timeout_keywords = (
        "timeout",
        "timed out",
        "readtimeout",
        "connecttimeout",
    )
    rate_limit_keywords = (
        "banned",
        "blocked",
        "频率",
        "rate limit",
        "too many requests",
        "429",
        "限制",
        "forbidden",
        "403",
    )

    if any(keyword in lowered for keyword in remote_disconnect_keywords):
        return "remote_disconnect", detail
    if isinstance(exc, (TimeoutError, requests.exceptions.Timeout)) or any(
        keyword in lowered for keyword in timeout_keywords
    ):
        return "timeout", detail
    if any(keyword in lowered for keyword in rate_limit_keywords):
        return "rate_limit_or_anti_bot", detail
    if isinstance(exc, requests.exceptions.RequestException):
        return "request_error", detail
    return "unknown_request_error", detail


def _build_realtime_failure_message(
    source_name: str,
    endpoint: str,
    stock_code: str,
    symbol: str,
    category: str,
    detail: str,
    elapsed: float,
    error_type: str,
) -> str:
    return (
        f"{source_name} 实时行情接口失败: endpoint={endpoint}, stock_code={stock_code}, "
        f"symbol={symbol}, category={category}, error_type={error_type}, "
        f"elapsed={elapsed:.2f}s, detail={detail}"
    )


def _akshare_call_with_timeout(
    func,
    *args,
    timeout: Optional[float] = None,
    call_name: str = "akshare",
    **kwargs,
):
    """Run an akshare call with a bounded wait time."""
    wait_seconds = _AKSHARE_HISTORY_CALL_TIMEOUT if timeout is None else float(timeout)

    multiprocessing.freeze_support()
    ctx = multiprocessing.get_context(_AKSHARE_TIMEOUT_PROCESS_START_METHOD)
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    process = ctx.Process(
        target=_akshare_timeout_worker,
        args=(child_conn, func, args, kwargs),
        name=f"akshare-{call_name}",
        daemon=True,
    )

    process.start()
    child_conn.close()

    try:
        if not parent_conn.poll(wait_seconds):
            _terminate_akshare_process(process)
            raise TimeoutError(f"{call_name} 호출이 {wait_seconds:g}s를 넘어서 기다리기를 멈춤")

        try:
            ok, value = parent_conn.recv()
        except EOFError as exc:
            raise RuntimeError(f"{call_name} 호출 프로세스가 결과를 돌려주지 않음") from exc
    finally:
        parent_conn.close()
        process.join(_AKSHARE_TIMEOUT_PROCESS_JOIN_GRACE)
        _terminate_akshare_process(process)

    if ok:
        return value
    raise value


def _akshare_timeout_worker(conn, func, args, kwargs) -> None:
    try:
        conn.send((True, func(*args, **kwargs)))
    except BaseException as exc:
        try:
            conn.send((False, exc))
        except BaseException:
            try:
                conn.send((False, RuntimeError(f"{type(exc).__name__}: {exc}")))
            except BaseException:
                pass
    finally:
        conn.close()


def _terminate_akshare_process(process) -> None:
    if process.is_alive():
        process.terminate()
        process.join(_AKSHARE_TIMEOUT_PROCESS_JOIN_GRACE)
    if process.is_alive():
        process.kill()
        process.join(_AKSHARE_TIMEOUT_PROCESS_JOIN_GRACE)


class AkshareFetcher(BaseFetcher):
    """
    Akshare 데이터 소스 구현
    
    우선순위: 1(가장 높음)
    데이터 출처: 둥팡차이푸 웹 크롤러
    
    핵심 전략:
    - 요청할 때마다 2.0-5.0초 무작위로 쉬기
    - User-Agent 무작위로 바꾸기
    - 실패하면 간격을 늘려 가며 재시도(최대 3번)
    """
    
    name = "AkshareFetcher"
    priority = int(os.getenv("AKSHARE_PRIORITY", "1"))
    
    def __init__(self, sleep_min: float = 2.0, sleep_max: float = 5.0):
        """
        AkshareFetcher 초기화
        
        Args:
            sleep_min: 최소 대기 시간(초)
            sleep_max: 최대 대기 시간(초)
        """
        self.sleep_min = sleep_min
        self.sleep_max = sleep_max
        self._last_request_time: Optional[float] = None
        self._history_call_timeout = _AKSHARE_HISTORY_CALL_TIMEOUT
        self._market_stats_call_timeout = _AKSHARE_MARKET_STATS_CALL_TIMEOUT
        # 둥팡차이푸 패치 옵션이 켜져 있을 때만 패치 적용
        if get_config().enable_eastmoney_patch:
            eastmoney_patch()
    
    def _set_random_user_agent(self) -> None:
        """
        무작위 User-Agent 설정
        
        requests Session의 headers를 바꿔서 처리
        크롤링 차단을 피하는 핵심 방법 중 하나
        """
        try:
            import akshare as ak
            # akshare는 내부에서 requests를 쓰므로 환경 변수나 직접 설정으로 영향을 줌
            # 실제로 akshare가 session을 직접 노출하지 않을 수 있어서 fake_useragent로 보완
            random_ua = random.choice(USER_AGENTS)
            logger.debug(f"User-Agent 설정: {random_ua[:50]}...")
        except Exception as e:
            logger.debug(f"User-Agent 설정 실패: {e}")
    
    def _enforce_rate_limit(self) -> None:
        """
        요청 속도 제한 적용
        
        전략:
        1. 지난 요청 이후 얼마나 지났는지 확인
        2. 간격이 짧으면 부족한 만큼 더 쉬기
        3. 그다음 무작위(jitter) 대기
        """
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            min_interval = self.sleep_min
            if elapsed < min_interval:
                additional_sleep = min_interval - elapsed
                logger.debug(f"추가로 {additional_sleep:.2f}초 대기")
                time.sleep(additional_sleep)
        
        # 무작위(jitter) 대기
        self.random_sleep(self.sleep_min, self.sleep_max)
        self._last_request_time = time.time()
    
    @retry(
        stop=stop_after_attempt(3),  # 최대 3번 재시도
        wait=wait_exponential(multiplier=1, min=2, max=30),  # 지수 백오프: 2, 4, 8... 최대 30초
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Akshare에서 원본 데이터 받기
        
        코드 종류에 따라 API를 자동으로 고름:
        - 등록된 A주 지수: ak.stock_zh_index_daily_em()
        - 미국 주식: 지원 안 함, 예외를 던져 YfinanceFetcher가 처리(Issue #311)
        - 홍콩 주식: ak.stock_hk_hist()
        - ETF: ak.fund_etf_hist_em()
        - 일반 A주: ak.stock_zh_a_hist()
        
        흐름:
        1. 코드 종류 판단(미국/홍콩/ETF/A주)
        2. 무작위 User-Agent 설정
        3. 요청 속도 제한(무작위 대기)
        4. 맞는 akshare API 호출
        5. 받은 데이터 정리
        """
        target = parse_analysis_target(stock_code)
        if target.asset_type == ParseStatus.INDEX:
            return self._fetch_index_data(target.canonical_id, start_date, end_date)

        # 코드 종류에 따라 다른 방법으로 받기
        if _is_us_code(stock_code):
            # 미국 주식: akshare의 stock_us_daily는 수정주가 계산에 알려진 문제가 있음(Issue #311 참고)
            # YfinanceFetcher에 맡겨 수정주가를 일관되게 유지
            raise DataFetchError(
                f"AkshareFetcher는 미국 주식 {stock_code}을(를) 지원하지 않아요. 올바른 수정주가는 YfinanceFetcher로 받으세요"
            )
        elif _is_hk_code(stock_code):
            return self._fetch_hk_data(stock_code, start_date, end_date)
        elif _is_etf_code(stock_code):
            return self._fetch_etf_data(stock_code, start_date, end_date)
        else:
            return self._fetch_stock_data(stock_code, start_date, end_date)

    def _fetch_index_data(
        self, stock_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Fetch a registry-recognized A-share index from Eastmoney."""
        import akshare as ak

        self._set_random_user_agent()
        self._enforce_rate_limit()
        logger.info(
            "[API 호출] ak.stock_zh_index_daily_em(symbol=%s, start_date=%s, end_date=%s)",
            stock_code,
            start_date.replace("-", ""),
            end_date.replace("-", ""),
        )
        try:
            df = _akshare_call_with_timeout(
                ak.stock_zh_index_daily_em,
                timeout=self._history_call_timeout,
                call_name="ak.stock_zh_index_daily_em",
                symbol=stock_code,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
            )
        except (ConnectionError, TimeoutError):
            raise
        except RateLimitError:
            raise
        except Exception as exc:
            error_msg = str(exc).lower()
            if any(
                keyword in error_msg
                for keyword in ("banned", "blocked", "频率", "rate", "限制")
            ):
                raise RateLimitError(f"Akshare 지수 API가 요청 제한에 걸렸을 수 있음: {exc}") from exc
            raise DataFetchError(f"Akshare 지수 데이터 받기 실패: {exc}") from exc

        if df is None:
            return pd.DataFrame()
        if not isinstance(df, pd.DataFrame):
            raise DataFetchError(
                f"Akshare 지수 API가 잘못된 타입을 돌려줌: {type(df).__name__}"
            )
        if df.empty:
            return df.copy()

        required_columns = {"date", "open", "high", "low", "close", "volume"}
        missing_columns = sorted(required_columns - set(df.columns))
        if missing_columns:
            raise DataFetchError(
                "Akshare 지수 데이터에 꼭 필요한 열이 없음: " + ", ".join(missing_columns)
            )

        result = df.copy()
        parsed_dates = pd.to_datetime(result["date"], errors="coerce", format="mixed")
        if parsed_dates.isna().any():
            invalid_dates = result.loc[parsed_dates.isna(), "date"].astype(str).tolist()
            raise DataFetchError(
                "Akshare 지수 데이터에 해석할 수 없는 date가 있음: "
                + ", ".join(invalid_dates[:3])
            )
        result["_index_sort_date"] = parsed_dates
        result = (
            result.sort_values("_index_sort_date", kind="stable")
            .drop(columns="_index_sort_date")
            .reset_index(drop=True)
        )
        if "pct_chg" not in result.columns:
            close = pd.to_numeric(result["close"], errors="coerce")
            pct_chg = close.pct_change(fill_method=None) * 100
            pct_chg = pct_chg.replace(
                [float("inf"), float("-inf")], float("nan")
            )
            if not pct_chg.empty and pd.isna(pct_chg.iloc[0]):
                pct_chg.iloc[0] = 0.0
            result["pct_chg"] = pct_chg
        if "amount" not in result.columns:
            result["amount"] = pd.NA
        return result
    
    def _fetch_stock_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        일반 A주 과거 데이터 받기

        전략:
        1. 먼저 둥팡차이푸 API (ak.stock_zh_a_hist) 시도
        2. 실패하면 시나 파이낸스 API (ak.stock_zh_a_daily) 시도
        3. 마지막으로 텐센트 파이낸스 API (ak.stock_zh_a_hist_tx) 시도
        """
        # 시도할 목록
        methods = [
            (self._fetch_stock_data_em, "둥팡차이푸"),
            (self._fetch_stock_data_sina, "시나 파이낸스"),
            (self._fetch_stock_data_tx, "텐센트 파이낸스"),
        ]

        last_error = None

        for fetch_method, source_name in methods:
            try:
                logger.info(f"[데이터 소스] {source_name}(으)로 {stock_code} 받기 시도...")
                df = fetch_method(stock_code, start_date, end_date)

                if df is not None and not df.empty:
                    logger.info(f"[데이터 소스] {source_name} 받기 성공")
                    return df
            except Exception as e:
                last_error = e
                logger.warning(f"[데이터 소스] {source_name} 받기 실패: {e}")
                # 다음 소스로 계속 시도

        # 모두 실패
        raise DataFetchError(f"Akshare 모든 경로에서 받기 실패: {last_error}")

    def _fetch_stock_data_em(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        일반 A주 과거 데이터 받기 (둥팡차이푸)
        데이터 출처: ak.stock_zh_a_hist()
        """
        import akshare as ak

        # 차단 방지 1: 무작위 User-Agent
        self._set_random_user_agent()

        # 차단 방지 2: 강제로 쉬기
        self._enforce_rate_limit()

        logger.info(f"[API 호출] ak.stock_zh_a_hist(symbol={stock_code}, ...)")

        try:
            import time as _time
            api_start = _time.time()

            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )

            api_elapsed = _time.time() - api_start

            if df is not None and not df.empty:
                logger.info(f"[API 응답] ak.stock_zh_a_hist 성공: {len(df)}행, 걸린 시간 {api_elapsed:.2f}s")
                return df
            else:
                logger.warning(f"[API 응답] ak.stock_zh_a_hist 빈 데이터")
                return pd.DataFrame()

        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '频率', 'rate', '限制']):
                raise RateLimitError(f"Akshare(EM) 요청 제한에 걸렸을 수 있음: {e}") from e
            raise e

    def _fetch_stock_data_sina(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        일반 A주 과거 데이터 받기 (시나 파이낸스)
        데이터 출처: ak.stock_zh_a_daily()
        """
        import akshare as ak

        # 코드 형식 변환: sh600000, sz000001, bj920748
        symbol = _to_sina_tx_symbol(stock_code)

        self._enforce_rate_limit()

        try:
            df = _akshare_call_with_timeout(
                ak.stock_zh_a_daily,
                symbol=symbol,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq",
                timeout=self._history_call_timeout,
                call_name="ak.stock_zh_a_daily",
            )

            # 시나 데이터 열 이름 맞추기
            # 시나 응답: date, open, high, low, close, volume, amount, outstanding_share, turnover
            if df is not None and not df.empty:
                # 날짜 열이 있는지 확인
                if 'date' in df.columns:
                    df = df.rename(columns={'date': '日期'})

                # _normalize_data가 기대하는 이름으로 나머지 열도 바꿈
                # _normalize_data가 기대하는 열: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额
                rename_map = {
                    'open': '开盘', 'high': '最高', 'low': '最低',
                    'close': '收盘', 'volume': '成交量', 'amount': '成交额'
                }
                df = df.rename(columns=rename_map)

                # 등락률 계산(시나 API는 안 줄 수도 있음)
                if '收盘' in df.columns:
                    df['涨跌幅'] = df['收盘'].pct_change() * 100
                    df['涨跌幅'] = df['涨跌幅'].fillna(0)

                return df
            return pd.DataFrame()

        except Exception as e:
            raise e

    def _fetch_stock_data_tx(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        일반 A주 과거 데이터 받기 (텐센트 파이낸스)
        데이터 출처: ak.stock_zh_a_hist_tx()
        """
        import akshare as ak

        # 코드 형식 변환: sh600000, sz000001, bj920748
        symbol = _to_sina_tx_symbol(stock_code)

        self._enforce_rate_limit()

        try:
            df = _akshare_call_with_timeout(
                ak.stock_zh_a_hist_tx,
                symbol=symbol,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq",
                timeout=self._history_call_timeout,
                call_name="ak.stock_zh_a_hist_tx",
            )

            # 텐센트 데이터 열 이름 맞추기
            # 텐센트 응답: date, open, close, high, low, volume, amount
            if df is not None and not df.empty:
                rename_map = {
                    'date': '日期', 'open': '开盘', 'high': '最高',
                    'low': '最低', 'close': '收盘', 'volume': '成交量',
                    'amount': '成交额'
                }
                df = df.rename(columns=rename_map)

                # 텐센트 데이터에는 보통 '涨跌幅'(등락률)이 있음, 없으면 계산
                if 'pct_chg' in df.columns:
                    df = df.rename(columns={'pct_chg': '涨跌幅'})
                elif '收盘' in df.columns:
                    df['涨跌幅'] = df['收盘'].pct_change() * 100
                    df['涨跌幅'] = df['涨跌幅'].fillna(0)

                return df
            return pd.DataFrame()

        except Exception as e:
            raise e
    
    def _fetch_etf_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        ETF 과거 데이터 받기
        
        데이터 출처: ak.fund_etf_hist_em()
        
        Args:
            stock_code: ETF 코드, 예: '512400', '159883'
            start_date: 시작 날짜, 형식 'YYYY-MM-DD'
            end_date: 종료 날짜, 형식 'YYYY-MM-DD'
            
        Returns:
            ETF 과거 데이터 DataFrame
        """
        import akshare as ak
        
        # 차단 방지 1: 무작위 User-Agent
        self._set_random_user_agent()
        
        # 차단 방지 2: 강제로 쉬기
        self._enforce_rate_limit()
        
        logger.info(f"[API 호출] ak.fund_etf_hist_em(symbol={stock_code}, period=daily, "
                   f"start_date={start_date.replace('-', '')}, end_date={end_date.replace('-', '')}, adjust=qfq)")
        
        try:
            import time as _time
            api_start = _time.time()
            
            # akshare로 ETF 일봉 데이터 받기
            df = ak.fund_etf_hist_em(
                symbol=stock_code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"  # 수정주가(과거 가격 조정)
            )
            
            api_elapsed = _time.time() - api_start
            
            # 받은 데이터 요약 기록
            if df is not None and not df.empty:
                logger.info(f"[API 응답] ak.fund_etf_hist_em 성공: {len(df)}행, 걸린 시간 {api_elapsed:.2f}s")
                logger.info(f"[API 응답] 열 이름: {list(df.columns)}")
                logger.info(f"[API 응답] 날짜 범위: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")
                logger.debug(f"[API 응답] 최근 3건:\n{df.tail(3).to_string()}")
            else:
                logger.warning(f"[API 응답] ak.fund_etf_hist_em 빈 데이터, 걸린 시간 {api_elapsed:.2f}s")
            
            return df
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 크롤링 차단 여부 확인
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '频率', 'rate', '限制']):
                logger.warning(f"차단됐을 가능성이 있음: {e}")
                raise RateLimitError(f"Akshare 요청 제한에 걸렸을 수 있음: {e}") from e
            
            raise DataFetchError(f"Akshare ETF 데이터 받기 실패: {e}") from e
    
    def _fetch_us_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        미국 주식 과거 데이터 받기
        
        데이터 출처: ak.stock_us_daily()(시나 파이낸스 API)
        
        Args:
            stock_code: 미국 주식 코드, 예: 'AMD', 'AAPL', 'TSLA'
            start_date: 시작 날짜, 형식 'YYYY-MM-DD'
            end_date: 종료 날짜, 형식 'YYYY-MM-DD'
            
        Returns:
            미국 주식 과거 데이터 DataFrame
        """
        import akshare as ak
        
        # 차단 방지 1: 무작위 User-Agent
        self._set_random_user_agent()
        
        # 차단 방지 2: 강제로 쉬기
        self._enforce_rate_limit()
        
        # 미국 주식 코드는 대문자로 그대로 사용
        symbol = stock_code.strip().upper()
        
        logger.info(f"[API 호출] ak.stock_us_daily(symbol={symbol}, adjust=qfq)")
        
        try:
            import time as _time
            api_start = _time.time()
            
            # akshare로 미국 주식 일봉 데이터 받기
            # stock_us_daily는 전체 기간 데이터를 주므로 뒤에서 날짜로 걸러야 함
            df = ak.stock_us_daily(
                symbol=symbol,
                adjust="qfq"  # 수정주가(과거 가격 조정)
            )
            
            api_elapsed = _time.time() - api_start
            
            # 받은 데이터 요약 기록
            if df is not None and not df.empty:
                logger.info(f"[API 응답] ak.stock_us_daily 성공: {len(df)}행, 걸린 시간 {api_elapsed:.2f}s")
                logger.info(f"[API 응답] 열 이름: {list(df.columns)}")
                
                # 날짜로 거르기
                df['date'] = pd.to_datetime(df['date'])
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
                df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
                
                if not df.empty:
                    logger.info(f"[API 응답] 거른 뒤 날짜 범위: {df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {df['date'].iloc[-1].strftime('%Y-%m-%d')}")
                    logger.debug(f"[API 응답] 최근 3건:\n{df.tail(3).to_string()}")
                else:
                    logger.warning(f"[API 응답] 거르고 나니 데이터가 없음, {start_date} ~ {end_date} 기간에 데이터 없음")
                
                # _normalize_data에 맞게 열 이름을 중국어 형식으로 바꿈
                # stock_us_daily 응답: date, open, high, low, close, volume
                rename_map = {
                    'date': '日期',
                    'open': '开盘',
                    'high': '最高',
                    'low': '最低',
                    'close': '收盘',
                    'volume': '成交量',
                }
                df = df.rename(columns=rename_map)
                
                # 등락률 계산(미국 주식 API는 따로 주지 않음)
                if '收盘' in df.columns:
                    df['涨跌幅'] = df['收盘'].pct_change() * 100
                    df['涨跌幅'] = df['涨跌幅'].fillna(0)
                
                # 거래대금 추정(미국 주식 API는 주지 않음)
                if '成交量' in df.columns and '收盘' in df.columns:
                    df['成交额'] = df['成交量'] * df['收盘']
                else:
                    df['成交额'] = 0
                
                return df
            else:
                logger.warning(f"[API 응답] ak.stock_us_daily 빈 데이터, 걸린 시간 {api_elapsed:.2f}s")
                return pd.DataFrame()
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 크롤링 차단 여부 확인
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '频率', 'rate', '限制']):
                logger.warning(f"차단됐을 가능성이 있음: {e}")
                raise RateLimitError(f"Akshare 요청 제한에 걸렸을 수 있음: {e}") from e
            
            raise DataFetchError(f"Akshare 미국 주식 데이터 받기 실패: {e}") from e

    def _fetch_hk_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        홍콩 주식 과거 데이터 받기
        
        데이터 출처: ak.stock_hk_hist()
        
        Args:
            stock_code: 홍콩 주식 코드, 예: '00700', '01810'
            start_date: 시작 날짜, 형식 'YYYY-MM-DD'
            end_date: 종료 날짜, 형식 'YYYY-MM-DD'
            
        Returns:
            홍콩 주식 과거 데이터 DataFrame
        """
        import akshare as ak
        
        # 차단 방지 1: 무작위 User-Agent
        self._set_random_user_agent()
        
        # 차단 방지 2: 강제로 쉬기
        self._enforce_rate_limit()
        
        # 코드 형식 맞추기(숫자 5자리)
        code = stock_code.lower().replace('hk', '').zfill(5)
        
        logger.info(f"[API 호출] ak.stock_hk_hist(symbol={code}, period=daily, "
                   f"start_date={start_date.replace('-', '')}, end_date={end_date.replace('-', '')}, adjust=qfq)")
        
        try:
            import time as _time
            api_start = _time.time()
            
            # akshare로 홍콩 주식 일봉 데이터 받기
            df = ak.stock_hk_hist(
                symbol=code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"  # 수정주가(과거 가격 조정)
            )
            
            api_elapsed = _time.time() - api_start
            
            # 받은 데이터 요약 기록
            if df is not None and not df.empty:
                logger.info(f"[API 응답] ak.stock_hk_hist 성공: {len(df)}행, 걸린 시간 {api_elapsed:.2f}s")
                logger.info(f"[API 응답] 열 이름: {list(df.columns)}")
                logger.info(f"[API 응답] 날짜 범위: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")
                logger.debug(f"[API 응답] 최근 3건:\n{df.tail(3).to_string()}")
            else:
                logger.warning(f"[API 응답] ak.stock_hk_hist 빈 데이터, 걸린 시간 {api_elapsed:.2f}s")
            
            return df
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 크롤링 차단 여부 확인
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '频率', 'rate', '限制']):
                logger.warning(f"차단됐을 가능성이 있음: {e}")
                raise RateLimitError(f"Akshare 요청 제한에 걸렸을 수 있음: {e}") from e
            
            raise DataFetchError(f"Akshare 홍콩 주식 데이터 받기 실패: {e}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        Akshare 데이터 정리
        
        Akshare가 주는 열 이름(중국어):
        日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
        
        표준 열 이름으로 바꿔야 함:
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # 열 이름 매핑(Akshare 중국어 열 이름 -> 표준 영어 열 이름)
        column_mapping = {
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount',
            '涨跌幅': 'pct_chg',
        }
        
        # 열 이름 바꾸기
        df = df.rename(columns=column_mapping)

        # 종목 코드 열 추가
        df['code'] = stock_code
        
        # 필요한 열만 남김
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        target = parse_analysis_target(stock_code)
        if target.asset_type != ParseStatus.INDEX or target.matched_index is None:
            return None

        import akshare as ak

        table_name = (
            "上证系列指数"
            if target.matched_index.exchange.upper() == "SH"
            else "深证系列指数"
        )
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()
            df = _akshare_call_with_timeout(
                ak.stock_zh_index_spot_em,
                timeout=self._history_call_timeout,
                call_name="ak.stock_zh_index_spot_em",
                symbol=table_name,
            )
            if df is None or df.empty or not {"代码", "名称"}.issubset(df.columns):
                return None

            bare_code = target.matched_index.bare_code

            def normalize_index_code(value: Any) -> str:
                text = str(value).strip()
                if text.endswith(".0"):
                    text = text[:-2]
                return text.zfill(6) if text.isdigit() else text

            matches = df[df["代码"].map(normalize_index_code) == bare_code]
            if matches.empty:
                return None
            for name_value in matches["名称"]:
                if pd.isna(name_value):
                    continue
                name = str(name_value).strip()
                if name:
                    return name
            return None
        except Exception:
            logger.debug(
                "Akshare index name lookup failed for %s",
                target.canonical_id,
                exc_info=True,
            )
            return None
    
    def get_realtime_quote(self, stock_code: str, source: str = "em") -> Optional[UnifiedRealtimeQuote]:
        """
        실시간 시세 받기(여러 데이터 소스 지원)

        데이터 소스 우선순위(설정 가능):
        1. em: 둥팡차이푸(akshare ak.stock_zh_a_spot_em) - 데이터가 가장 많음, 거래량 비율/PE/PB/시가총액 등 포함
        2. sina: 시나 파이낸스(akshare ak.stock_zh_a_spot) - 가벼움, 기본 시세만
        3. tencent: 텐센트 직접 연결 API - 종목 하나씩 조회, 부담이 적음

        Args:
            stock_code: 주식/ETF 코드
            source: 데이터 소스 종류, 선택지: "em", "sina", "tencent"

        Returns:
            UnifiedRealtimeQuote 객체, 실패하면 None
        """
        circuit_breaker = get_realtime_circuit_breaker()

        # 코드 종류에 따라 다른 방법으로 받기
        if _is_us_code(stock_code):
            # 미국 주식은 Akshare를 쓰지 않고 YfinanceFetcher가 처리
            logger.debug(f"[API 건너뜀] {stock_code}은(는) 미국 주식이라 Akshare 실시간 시세를 지원하지 않음")
            return None
        elif _is_hk_code(stock_code):
            return self._get_hk_realtime_quote(stock_code)
        elif _is_etf_code(stock_code):
            source_key = "akshare_etf"
            if not circuit_breaker.is_available(source_key):
                logger.info(f"[차단] 데이터 소스 {source_key} 차단 중이라 건너뜀")
                return None
            return self._get_etf_realtime_quote(stock_code)
        else:
            source_key = f"akshare_{source}"
            if not circuit_breaker.is_available(source_key):
                logger.info(f"[차단] 데이터 소스 {source_key} 차단 중이라 건너뜀")
                return None
            # 일반 A주: source에 따라 데이터 소스 선택
            if source == "sina":
                return self._get_stock_realtime_quote_sina(stock_code)
            elif source == "tencent":
                return self._get_stock_realtime_quote_tencent(stock_code)
            else:
                return self._get_stock_realtime_quote_em(stock_code)
    
    def _get_stock_realtime_quote_em(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        일반 A주 실시간 시세 받기(둥팡차이푸 데이터 소스)
        
        데이터 출처: ak.stock_zh_a_spot_em()
        장점: 데이터가 가장 많음, 거래량 비율, 회전율, PER, PBR, 시가총액, 유통 시가총액 등 포함
        단점: 전체를 한 번에 받아서 양이 많고 시간 초과/요청 제한에 걸리기 쉬움
        """
        import akshare as ak
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "akshare_em"
        
        try:
            # 캐시 확인
            current_time = time.time()
            if (_realtime_cache['data'] is not None and 
                current_time - _realtime_cache['timestamp'] < _realtime_cache['ttl']):
                df = _realtime_cache['data']
                cache_age = int(current_time - _realtime_cache['timestamp'])
                logger.debug(f"[캐시 적중] A주 실시간 시세(둥팡차이푸) - 캐시 나이 {cache_age}s/{_realtime_cache['ttl']}s")
            else:
                # 전체 새로 받기
                logger.info(f"[캐시 없음] A주 실시간 시세(둥팡차이푸) 전체 새로 받기")
                last_error: Optional[Exception] = None
                df = None
                for attempt in range(1, 3):
                    try:
                        # 차단 방지 전략
                        self._set_random_user_agent()
                        self._enforce_rate_limit()

                        logger.info(f"[API 호출] ak.stock_zh_a_spot_em() A주 실시간 시세 받는 중... (attempt {attempt}/2)")
                        import time as _time
                        api_start = _time.time()

                        df = ak.stock_zh_a_spot_em()

                        api_elapsed = _time.time() - api_start
                        logger.info(f"[API 응답] ak.stock_zh_a_spot_em 성공: {len(df)}종목, 걸린 시간 {api_elapsed:.2f}s")
                        circuit_breaker.record_success(source_key)
                        break
                    except Exception as e:
                        last_error = e
                        logger.info(f"[API 오류] ak.stock_zh_a_spot_em 받기 실패 (attempt {attempt}/2): {e}")
                        time.sleep(min(2 ** attempt, 5))

                # 캐시 갱신: 성공하면 데이터를, 실패해도 빈 데이터를 저장해서 같은 작업 중에 같은 API를 반복 호출하지 않게 함
                if df is None:
                    logger.info(f"[API 오류] ak.stock_zh_a_spot_em 최종 실패: {last_error}")
                    circuit_breaker.record_failure(source_key, str(last_error))
                    df = pd.DataFrame()
                _realtime_cache['data'] = df
                _realtime_cache['timestamp'] = current_time
                logger.info(f"[캐시 갱신] A주 실시간 시세(둥팡차이푸) 캐시 새로 고침,TTL={_realtime_cache['ttl']}s")

            if df is None or df.empty:
                logger.info(f"[실시간 시세] A주 실시간 시세 데이터가 비어 있어 건너뜀 {stock_code}")
                return None
            
            # 해당 종목 찾기
            row = df[df['代码'] == stock_code]
            if row.empty:
                logger.info(f"[API 응답] 종목 {stock_code}의 실시간 시세를 찾지 못함")
                return None
            
            row = row.iloc[0]
            
            # realtime_types.py의 공통 변환 함수 사용
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get('名称', '')),
                source=RealtimeSource.AKSHARE_EM,
                price=safe_float(row.get('最新价')),
                change_pct=safe_float(row.get('涨跌幅')),
                change_amount=safe_float(row.get('涨跌额')),
                volume=safe_int(row.get('成交量')),
                amount=safe_float(row.get('成交额')),
                volume_ratio=safe_float(row.get('量比')),
                turnover_rate=safe_float(row.get('换手率')),
                amplitude=safe_float(row.get('振幅')),
                open_price=safe_float(row.get('今开')),
                high=safe_float(row.get('最高')),
                low=safe_float(row.get('最低')),
                pe_ratio=safe_float(row.get('市盈率-动态')),
                pb_ratio=safe_float(row.get('市净率')),
                total_mv=safe_float(row.get('总市值')),
                circ_mv=safe_float(row.get('流通市值')),
                change_60d=safe_float(row.get('60日涨跌幅')),
                high_52w=safe_float(row.get('52周最高')),
                low_52w=safe_float(row.get('52周最低')),
            )
            
            logger.info(f"[실시간 시세-둥팡차이푸] {stock_code} {quote.name}: 가격={quote.price}, 등락={quote.change_pct}%, "
                       f"거래량 비율={quote.volume_ratio}, 회전율={quote.turnover_rate}%")
            return quote
            
        except Exception as e:
            logger.info(f"[API 오류] {stock_code} 실시간 시세(둥팡차이푸) 받기 실패: {e}")
            circuit_breaker.record_failure(source_key, str(e))
            return None
    
    def _get_stock_realtime_quote_sina(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        일반 A주 실시간 시세 받기(시나 파이낸스 데이터 소스)
        
        데이터 출처: 시나 파이낸스 API(직접 연결, 종목 하나씩 조회)
        장점: 종목 하나씩 조회, 부담이 적고 빠름
        단점: 필드가 적음, 거래량 비율/PE/PB 등 없음
        
        API 형식: http://hq.sinajs.cn/list=sh600519,sz000001
        """
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "akshare_sina"
        symbol = _to_sina_tx_symbol(stock_code)
        url = f"http://{SINA_REALTIME_ENDPOINT}={symbol}"
        api_start = time.time()
        
        try:
            headers = {
                'Referer': 'http://finance.sina.com.cn',
                'User-Agent': random.choice(USER_AGENTS)
            }
            
            logger.info(
                f"[API 호출] 시나 파이낸스 API로 {stock_code} 실시간 시세 받기: endpoint={SINA_REALTIME_ENDPOINT}, symbol={symbol}"
            )
            
            self._enforce_rate_limit()
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'gbk'
            api_elapsed = time.time() - api_start
            
            if response.status_code != 200:
                failure_message = _build_realtime_failure_message(
                    source_name="新浪",
                    endpoint=SINA_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="http_status",
                    detail=f"HTTP {response.status_code}",
                    elapsed=api_elapsed,
                    error_type="HTTPStatus",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            # 데이터 해석: var hq_str_sh600519="贵州茅台,1866.000,1870.000,..."
            content = response.text.strip()
            if '=""' in content or not content:
                failure_message = _build_realtime_failure_message(
                    source_name="新浪",
                    endpoint=SINA_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="empty_response",
                    detail="empty quote payload",
                    elapsed=api_elapsed,
                    error_type="EmptyResponse",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            # 따옴표 안의 데이터 꺼내기
            data_start = content.find('"')
            data_end = content.rfind('"')
            if data_start == -1 or data_end == -1:
                failure_message = _build_realtime_failure_message(
                    source_name="新浪",
                    endpoint=SINA_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="malformed_payload",
                    detail="quote payload missing quotes",
                    elapsed=api_elapsed,
                    error_type="MalformedPayload",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            data_str = content[data_start+1:data_end]
            fields = data_str.split(',')
            
            if len(fields) < 32:
                failure_message = _build_realtime_failure_message(
                    source_name="新浪",
                    endpoint=SINA_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="insufficient_fields",
                    detail=f"field_count={len(fields)}",
                    elapsed=api_elapsed,
                    error_type="InsufficientFields",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            circuit_breaker.record_success(source_key)
            
            # 시나 데이터 필드 순서:
            # 0:종목명 1:시가 2:전일 종가 3:현재가 4:고가 5:저가 6:매수1호가 7:매도1호가
            # 8:거래량(주) 9:거래대금(위안) ... 30:날짜 31:시각
            # realtime_types.py의 공통 변환 함수 사용
            price = safe_float(fields[3])
            pre_close = safe_float(fields[2])
            change_pct = None
            change_amount = None
            if price and pre_close and pre_close > 0:
                change_amount = price - pre_close
                change_pct = (change_amount / pre_close) * 100
            
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=fields[0],
                source=RealtimeSource.AKSHARE_SINA,
                price=price,
                change_pct=change_pct,
                change_amount=change_amount,
                volume=safe_int(fields[8]),  # 거래량(주)
                amount=safe_float(fields[9]),  # 거래대금(위안)
                open_price=safe_float(fields[1]),
                high=safe_float(fields[4]),
                low=safe_float(fields[5]),
                pre_close=pre_close,
            )
            
            logger.info(
                f"[实时行情-新浪] {stock_code} {quote.name}: endpoint={SINA_REALTIME_ENDPOINT}, "
                f"가격={quote.price}, 등락={quote.change_pct}, 거래량={quote.volume}, elapsed={api_elapsed:.2f}s"
            )
            return quote
            
        except Exception as e:
            api_elapsed = time.time() - api_start
            category, detail = _classify_realtime_http_error(e)
            failure_message = _build_realtime_failure_message(
                source_name="新浪",
                endpoint=SINA_REALTIME_ENDPOINT,
                stock_code=stock_code,
                symbol=symbol,
                category=category,
                detail=detail,
                elapsed=api_elapsed,
                error_type=type(e).__name__,
            )
            logger.info(failure_message)
            circuit_breaker.record_failure(source_key, failure_message)
            return None
    
    def _get_stock_realtime_quote_tencent(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        일반 A주 실시간 시세 받기(텐센트 파이낸스 데이터 소스)
        
        데이터 출처: 텐센트 파이낸스 API(직접 연결, 종목 하나씩 조회)
        장점: 종목 하나씩 조회, 부담이 적고 회전율 포함
        단점: 거래량 비율/PE/PB 같은 밸류에이션 데이터 없음
        
        API 형식: http://qt.gtimg.cn/q=sh600519,sz000001
        """
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "akshare_tencent"
        symbol = _to_sina_tx_symbol(stock_code)
        url = f"http://{TENCENT_REALTIME_ENDPOINT}={symbol}"
        api_start = time.time()
        
        try:
            headers = {
                'Referer': 'http://finance.qq.com',
                'User-Agent': random.choice(USER_AGENTS)
            }
            
            logger.info(
                f"[API 호출] 텐센트 파이낸스 API로 {stock_code} 실시간 시세 받기: endpoint={TENCENT_REALTIME_ENDPOINT}, symbol={symbol}"
            )
            
            self._enforce_rate_limit()
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'gbk'
            api_elapsed = time.time() - api_start
            
            if response.status_code != 200:
                failure_message = _build_realtime_failure_message(
                    source_name="腾讯",
                    endpoint=TENCENT_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="http_status",
                    detail=f"HTTP {response.status_code}",
                    elapsed=api_elapsed,
                    error_type="HTTPStatus",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            content = response.text.strip()
            if '=""' in content or not content:
                failure_message = _build_realtime_failure_message(
                    source_name="腾讯",
                    endpoint=TENCENT_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="empty_response",
                    detail="empty quote payload",
                    elapsed=api_elapsed,
                    error_type="EmptyResponse",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            # 데이터 꺼내기
            data_start = content.find('"')
            data_end = content.rfind('"')
            if data_start == -1 or data_end == -1:
                failure_message = _build_realtime_failure_message(
                    source_name="腾讯",
                    endpoint=TENCENT_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="malformed_payload",
                    detail="quote payload missing quotes",
                    elapsed=api_elapsed,
                    error_type="MalformedPayload",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            data_str = content[data_start+1:data_end]
            fields = data_str.split('~')

            if len(fields) < 45:
                failure_message = _build_realtime_failure_message(
                    source_name="腾讯",
                    endpoint=TENCENT_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="insufficient_fields",
                    detail=f"field_count={len(fields)}",
                    elapsed=api_elapsed,
                    error_type="InsufficientFields",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            circuit_breaker.record_success(source_key)
            
            # 텐센트 데이터 필드 순서(전체):
            # 1:종목명 2:코드 3:현재가 4:전일 종가 5:시가 6:거래량 7:매수 체결량 8:매도 체결량
            # 9-28:매수/매도 5단계 호가 30:타임스탬프 31:등락폭 32:등락률(%) 33:고가 34:저가 35:종가/거래량/거래대금
            # 36:거래량(단위가 payload마다 다름) 37:거래대금(만) 38:회전율(%) 39:PER 43:변동폭(%)
            # 44:유통 시가총액(억) 45:시가총액(억) 46:PBR 47:상한가 48:하한가 49:거래량 비율
            # realtime_types.py의 공통 변환 함수 사용
            amount = _parse_tencent_amount(fields)
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=fields[1] if len(fields) > 1 else "",
                source=RealtimeSource.TENCENT,
                price=safe_float(fields[3]),
                change_pct=safe_float(fields[32]),
                change_amount=safe_float(fields[31]) if len(fields) > 31 else None,
                volume=_normalize_tencent_volume(fields),
                amount=amount,
                open_price=safe_float(fields[5]),
                high=safe_float(fields[33]) if len(fields) > 33 else None,  # 수정: 33번 필드가 고가
                low=safe_float(fields[34]) if len(fields) > 34 else None,  # 수정: 34번 필드가 저가
                pre_close=safe_float(fields[4]),
                turnover_rate=safe_float(fields[38]) if len(fields) > 38 else None,
                amplitude=safe_float(fields[43]) if len(fields) > 43 else None,
                volume_ratio=safe_float(fields[49]) if len(fields) > 49 else None,  # 거래량 비율
                pe_ratio=safe_float(fields[39]) if len(fields) > 39 else None,  # PER
                pb_ratio=safe_float(fields[46]) if len(fields) > 46 else None,  # PBR
                circ_mv=safe_float(fields[44]) * 100000000 if len(fields) > 44 and fields[44] else None,  # 유통 시가총액(억->위안)
                total_mv=safe_float(fields[45]) * 100000000 if len(fields) > 45 and fields[45] else None,  # 시가총액(억->위안)
            )
            
            logger.info(
                f"[实时行情-腾讯] {stock_code} {quote.name}: endpoint={TENCENT_REALTIME_ENDPOINT}, "
                f"가격={quote.price}, 등락={quote.change_pct}%, 거래량 비율={quote.volume_ratio}, "
                f"회전율={quote.turnover_rate}%, elapsed={api_elapsed:.2f}s"
            )
            return quote
            
        except Exception as e:
            api_elapsed = time.time() - api_start
            category, detail = _classify_realtime_http_error(e)
            failure_message = _build_realtime_failure_message(
                source_name="腾讯",
                endpoint=TENCENT_REALTIME_ENDPOINT,
                stock_code=stock_code,
                symbol=symbol,
                category=category,
                detail=detail,
                elapsed=api_elapsed,
                error_type=type(e).__name__,
            )
            logger.info(failure_message)
            circuit_breaker.record_failure(source_key, failure_message)
            return None
    
    def _get_etf_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        ETF 실시간 시세 받기
        
        데이터 출처: ak.fund_etf_spot_em()
        포함: 현재가, 등락률, 거래량, 거래대금, 회전율 등
        
        Args:
            stock_code: ETF 코드
            
        Returns:
            UnifiedRealtimeQuote 객체, 실패하면 None
        """
        import akshare as ak
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "akshare_etf"
        
        try:
            # 캐시 확인
            current_time = time.time()
            if (_etf_realtime_cache['data'] is not None and 
                current_time - _etf_realtime_cache['timestamp'] < _etf_realtime_cache['ttl']):
                df = _etf_realtime_cache['data']
                logger.debug(f"[캐시 적중] 캐시에 있는 ETF 실시간 시세 사용")
            else:
                last_error: Optional[Exception] = None
                df = None
                for attempt in range(1, 3):
                    try:
                        # 차단 방지 전략
                        self._set_random_user_agent()
                        self._enforce_rate_limit()

                        logger.info(f"[API 호출] ak.fund_etf_spot_em() ETF 실시간 시세 받는 중... (attempt {attempt}/2)")
                        import time as _time
                        api_start = _time.time()

                        df = ak.fund_etf_spot_em()

                        api_elapsed = _time.time() - api_start
                        logger.info(f"[API 응답] ak.fund_etf_spot_em 성공: ETF {len(df)}개, 걸린 시간 {api_elapsed:.2f}s")
                        circuit_breaker.record_success(source_key)
                        break
                    except Exception as e:
                        last_error = e
                        logger.info(f"[API 오류] ak.fund_etf_spot_em 받기 실패 (attempt {attempt}/2): {e}")
                        time.sleep(min(2 ** attempt, 5))

                if df is None:
                    logger.info(f"[API 오류] ak.fund_etf_spot_em 최종 실패: {last_error}")
                    circuit_breaker.record_failure(source_key, str(last_error))
                    df = pd.DataFrame()
                _etf_realtime_cache['data'] = df
                _etf_realtime_cache['timestamp'] = current_time

            if df is None or df.empty:
                logger.info(f"[실시간 시세] ETF 실시간 시세 데이터가 비어 있어 건너뜀 {stock_code}")
                return None
            
            # 해당 ETF 찾기
            row = df[df['代码'] == stock_code]
            if row.empty:
                logger.info(f"[API 응답] ETF {stock_code}의 실시간 시세를 찾지 못함")
                return None
            
            row = row.iloc[0]
            
            # realtime_types.py의 공통 변환 함수 사용
            # ETF 시세 데이터 만들기
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get('名称', '')),
                source=RealtimeSource.AKSHARE_EM,
                price=safe_float(row.get('最新价')),
                change_pct=safe_float(row.get('涨跌幅')),
                change_amount=safe_float(row.get('涨跌额')),
                volume=safe_int(row.get('成交量')),
                amount=safe_float(row.get('成交额')),
                volume_ratio=safe_float(row.get('量比')),
                turnover_rate=safe_float(row.get('换手率')),
                amplitude=safe_float(row.get('振幅')),
                open_price=safe_float(row.get('开盘价')),
                high=safe_float(row.get('最高价')),
                low=safe_float(row.get('最低价')),
                total_mv=safe_float(row.get('总市值')),
                circ_mv=safe_float(row.get('流通市值')),
                high_52w=safe_float(row.get('52周最高')),
                low_52w=safe_float(row.get('52周最低')),
            )
            
            logger.info(f"[ETF 실시간 시세] {stock_code} {quote.name}: 가격={quote.price}, 등락={quote.change_pct}%, "
                       f"회전율={quote.turnover_rate}%")
            return quote
            
        except Exception as e:
            logger.info(f"[API 오류] ETF {stock_code} 실시간 시세 받기 실패: {e}")
            circuit_breaker.record_failure(source_key, str(e))
            return None
    
    def _get_hk_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        홍콩 주식 실시간 시세 받기

        메인 데이터 소스: ak.stock_hk_spot_em()(둥팡차이푸)
        예비 데이터 소스: ak.stock_hk_spot()(시나)
        포함: 현재가, 등락률, 거래량, 거래대금 등

        Args:
            stock_code: 홍콩 주식 코드

        Returns:
            UnifiedRealtimeQuote 객체, 실패하면 None
        """
        import akshare as ak
        circuit_breaker = get_realtime_circuit_breaker()
        em_key = "akshare_hk_em"
        sina_key = "akshare_hk_sina"

        # 코드 형식 맞추기(숫자 5자리)
        raw_code = stock_code.strip().lower()
        if raw_code.endswith('.hk'):
            raw_code = raw_code[:-3]
        if raw_code.startswith('hk'):
            raw_code = raw_code[2:]
        code = raw_code.zfill(5)

        def build_em_quote(df: pd.DataFrame) -> Optional[UnifiedRealtimeQuote]:
            if df.empty:
                logger.info(f"[API 응답] 홍콩 주식 실시간 시세 데이터가 비어 있음 (stock_hk_spot_em)")
                return None

            row = df[df['代码'] == code]
            if row.empty:
                logger.info(f"[API 응답] 홍콩 주식 {code}의 실시간 시세를 찾지 못함 (stock_hk_spot_em)")
                return None

            row = row.iloc[0]
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get('名称', '')),
                source=RealtimeSource.AKSHARE_EM,
                price=safe_float(row.get('最新价')),
                change_pct=safe_float(row.get('涨跌幅')),
                change_amount=safe_float(row.get('涨跌额')),
                volume=safe_int(row.get('成交量')),
                amount=safe_float(row.get('成交额')),
                volume_ratio=safe_float(row.get('量比')),
                turnover_rate=safe_float(row.get('换手率')),
                amplitude=safe_float(row.get('振幅')),
                pe_ratio=safe_float(row.get('市盈率')),
                pb_ratio=safe_float(row.get('市净率')),
                total_mv=safe_float(row.get('总市值')),
                circ_mv=safe_float(row.get('流通市值')),
                high_52w=safe_float(row.get('52周最高')),
                low_52w=safe_float(row.get('52周最低')),
            )
            logger.info(
                f"[홍콩 주식 실시간 시세] {stock_code} {quote.name}: 가격={quote.price}, "
                f"등락={quote.change_pct}%, 회전율={quote.turnover_rate}%"
            )
            return quote

        def read_cached_em_quote() -> Tuple[bool, Optional[UnifiedRealtimeQuote]]:
            current_time = time.time()
            cache_data = _hk_realtime_cache['data']
            cache_age = current_time - _hk_realtime_cache['timestamp']
            if (
                _hk_realtime_cache.get('last_result') == 'failure'
                and cache_age < _hk_realtime_cache.get('failure_ttl', 0)
            ):
                logger.debug(
                    f"[캐시 적중] 홍콩 주식 실시간 시세(둥팡차이푸) - 최근 실패 결과 재사용 "
                    f"{int(cache_age)}s/{_hk_realtime_cache.get('failure_ttl', 0)}s"
                )
                return True, None

            if cache_data is None or cache_age >= _hk_realtime_cache['ttl']:
                return False, None

            logger.debug(
                f"[캐시 적중] 홍콩 주식 실시간 시세(둥팡차이푸) - 캐시 나이 "
                f"{int(cache_age)}s/{_hk_realtime_cache['ttl']}s"
            )
            try:
                return True, build_em_quote(cache_data)
            except Exception as e:
                logger.warning(
                    f"[캐시 오류] 홍콩 주식 실시간 시세 캐시를 해석할 수 없음: {e}, "
                    "예비 API stock_hk_spot 시도"
                )
                return True, None

        cache_hit, quote = read_cached_em_quote()
        if quote is not None:
            return quote

        # --- 메인 데이터 소스: 둥팡차이푸 ---
        if not cache_hit:
            # 포트폴리오 스냅샷은 여러 symbol을 동시에 조회함. 락 안에서 한 번 더 확인해서 한 프로세스에서 처음 받기는 한 번만 하게 함.
            with _hk_realtime_cache_lock:
                cache_hit, quote = read_cached_em_quote()
                if quote is not None:
                    return quote

                if circuit_breaker.is_available(em_key) and not cache_hit:
                    try:
                        # 실제로 네트워크 요청을 보낼 때만 차단 방지 대기를 함. 캐시에 있으면 기다리지 않음.
                        self._set_random_user_agent()
                        self._enforce_rate_limit()

                        logger.info(f"[API 호출] ak.stock_hk_spot_em() 홍콩 주식 실시간 시세 받는 중...")
                        import time as _time
                        api_start = _time.time()

                        df = ak.stock_hk_spot_em()

                        api_elapsed = _time.time() - api_start
                        logger.info(
                            f"[API 응답] ak.stock_hk_spot_em 성공: 홍콩 주식 {len(df)}종목, "
                            f"걸린 시간 {api_elapsed:.2f}s"
                        )

                        if not isinstance(df, pd.DataFrame):
                            raise TypeError("stock_hk_spot_em이 DataFrame을 돌려주지 않음")
                        if '代码' not in df.columns:
                            raise KeyError("stock_hk_spot_em 결과에 代码(코드) 열이 없음")
                        if df.empty:
                            raise ValueError("stock_hk_spot_em이 빈 시장 스냅샷을 돌려줌")

                        _hk_realtime_cache['data'] = df
                        _hk_realtime_cache['timestamp'] = time.time()
                        _hk_realtime_cache['last_result'] = 'success'
                        logger.info(
                            f"[캐시 갱신] 홍콩 주식 실시간 시세(둥팡차이푸) 캐시 새로 고침, "
                            f"TTL={_hk_realtime_cache['ttl']}s"
                        )

                        quote = build_em_quote(df)
                        circuit_breaker.record_success(em_key)
                        if quote is not None:
                            return quote

                    except Exception as e:
                        _hk_realtime_cache['data'] = None
                        _hk_realtime_cache['timestamp'] = time.time()
                        _hk_realtime_cache['last_result'] = 'failure'
                        logger.warning(
                            f"[API 오류] ak.stock_hk_spot_em 홍콩 주식 {stock_code} "
                            f"받기 실패: {e}, 예비 API stock_hk_spot 시도"
                        )
                        circuit_breaker.record_failure(em_key, str(e))
                elif not cache_hit:
                    logger.info(
                        f"[차단] 데이터 소스 {em_key} 차단 중이라 예비 경로 시도"
                    )

        # --- 예비 데이터 소스: 시나 ---
        if not circuit_breaker.is_available(sina_key):
            logger.info(f"[차단] 데이터 소스 {sina_key} 차단 중이라 예비 경로 건너뜀")
            return None

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info(f"[API 호출] ak.stock_hk_spot() 홍콩 주식 실시간 시세 받는 중(예비)...")
            import time as _time
            api_start = _time.time()

            df_spot = ak.stock_hk_spot()

            api_elapsed = _time.time() - api_start
            logger.info(f"[API 응답] ak.stock_hk_spot 성공: 홍콩 주식 {len(df_spot)}종목, 걸린 시간 {api_elapsed:.2f}s")

            row = df_spot[df_spot['代码'] == code]
            if row.empty:
                logger.info(f"[API 응답] 홍콩 주식 {code}의 실시간 시세를 찾지 못함 (stock_hk_spot)")
                return None

            row = row.iloc[0]
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get('名称', '')),
                source=RealtimeSource.AKSHARE_EM,
                price=safe_float(row.get('最新价')),
                change_pct=safe_float(row.get('涨跌幅')),
                change_amount=safe_float(row.get('涨跌额')),
                volume=safe_int(row.get('成交量')),
                amount=safe_float(row.get('成交额')),
            )
            circuit_breaker.record_success(sina_key)
            logger.info(f"[홍콩 주식 실시간 시세-예비] {stock_code} {quote.name}: 가격={quote.price}, 등락={quote.change_pct}%")
            return quote

        except Exception as e:
            logger.info(f"[API 오류] 예비 API ak.stock_hk_spot도 실패: {e}")
            circuit_breaker.record_failure(sina_key, str(e))
            return None
    
    def get_chip_distribution(self, stock_code: str) -> Optional[ChipDistribution]:
        """
        매물대 분포 데이터 받기
        
        데이터 출처: ak.stock_cyq_em()
        포함: 수익 비율, 평균 단가, 매물 집중도
        
        참고: ETF/지수는 매물대 분포 데이터가 없어서 바로 None을 돌려줌
        
        Args:
            stock_code: 주식 코드
            
        Returns:
            ChipDistribution 객체(가장 최근 하루 데이터), 실패하면 None
        """
        import akshare as ak

        # 미국 주식은 매물대 분포 데이터가 없음(Akshare 미지원)
        if _is_us_code(stock_code):
            logger.debug(f"[API 건너뜀] {stock_code}은(는) 미국 주식이라 매물대 분포 데이터 없음")
            return None

        # 홍콩 주식은 매물대 분포 데이터가 없음(stock_cyq_em은 A주 전용 API)
        if _is_hk_code(stock_code):
            logger.debug(f"[API 건너뜀] {stock_code}은(는) 홍콩 주식이라 매물대 분포 데이터 없음")
            return None

        # ETF/지수는 매물대 분포 데이터가 없음
        if _is_etf_code(stock_code):
            logger.debug(f"[API 건너뜀] {stock_code}은(는) ETF/지수라 매물대 분포 데이터 없음")
            return None
        
        try:
            # 차단 방지 전략
            self._set_random_user_agent()
            self._enforce_rate_limit()
            
            logger.info(f"[API 호출] ak.stock_cyq_em(symbol={stock_code}) 매물대 분포 받는 중...")
            import time as _time
            api_start = _time.time()
            
            df = ak.stock_cyq_em(symbol=stock_code)
            
            api_elapsed = _time.time() - api_start
            
            if df.empty:
                logger.warning(f"[API 응답] ak.stock_cyq_em 빈 데이터, 걸린 시간 {api_elapsed:.2f}s")
                return None
            
            logger.info(f"[API 응답] ak.stock_cyq_em 성공: {len(df)}일치 데이터, 걸린 시간 {api_elapsed:.2f}s")
            logger.debug(f"[API 응답] 매물대 데이터 열 이름: {list(df.columns)}")
            
            # 가장 최근 하루 데이터 사용
            latest = df.iloc[-1]
            
            # realtime_types.py의 공통 변환 함수 사용
            chip = ChipDistribution(
                code=stock_code,
                date=str(latest.get('日期', '')),
                profit_ratio=safe_float(latest.get('获利比例')),
                avg_cost=safe_float(latest.get('平均成本')),
                cost_90_low=safe_float(latest.get('90成本-低')),
                cost_90_high=safe_float(latest.get('90成本-高')),
                concentration_90=safe_float(latest.get('90集中度')),
                cost_70_low=safe_float(latest.get('70成本-低')),
                cost_70_high=safe_float(latest.get('70成本-高')),
                concentration_70=safe_float(latest.get('70集中度')),
            )
            
            logger.info(f"[매물대 분포] {stock_code} 날짜={chip.date}: 수익 비율={chip.profit_ratio:.1%}, "
                       f"평균 단가={chip.avg_cost}, 90% 집중도={chip.concentration_90:.2%}, "
                       f"70% 집중도={chip.concentration_70:.2%}")
            return chip
            
        except Exception as e:
            logger.error(f"[API 오류] {stock_code} 매물대 분포 받기 실패: {e}")
            return None
    
    def get_enhanced_data(self, stock_code: str, days: int = 60) -> Dict[str, Any]:
        """
        추가 데이터 받기(과거 K선 + 실시간 시세 + 매물대 분포)
        
        Args:
            stock_code: 주식 코드
            days: 과거 데이터 일수
            
        Returns:
            모든 데이터를 담은 dict
        """
        result = {
            'code': stock_code,
            'daily_data': None,
            'realtime_quote': None,
            'chip_distribution': None,
        }
        
        # 일봉 데이터 받기
        try:
            df = self.get_daily_data(stock_code, days=days)
            result['daily_data'] = df
        except Exception as e:
            logger.error(f"{stock_code} 일봉 데이터 받기 실패: {e}")
        
        # 실시간 시세 받기
        result['realtime_quote'] = self.get_realtime_quote(stock_code)
        
        # 매물대 분포 받기
        result['chip_distribution'] = self.get_chip_distribution(stock_code)
        
        return result

    def get_main_indices(self, region: str = "cn") -> Optional[List[Dict[str, Any]]]:
        """
        주요 지수 실시간 시세 받기(시나 API), A주만 지원
        """
        if region != "cn":
            return None
        import akshare as ak

        # 주요 지수 코드 매핑
        indices_map = {
            'sh000001': '上证指数',
            'sz399001': '深证成指',
            'sz399006': '创业板指',
            'sh000688': '科创50',
            'sh000016': '上证50',
            'sh000300': '沪深300',
        }

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            # akshare로 지수 시세 받기(시나 파이낸스 API)
            df = ak.stock_zh_index_spot_sina()

            results = []
            if df is not None and not df.empty:
                for code, name in indices_map.items():
                    # 해당 지수 찾기
                    row = df[df['代码'] == code]
                    if row.empty:
                        # 접두어를 붙여서 다시 찾기
                        row = df[df['代码'].str.contains(code)]

                    if not row.empty:
                        row = row.iloc[0]
                        current = safe_float(row.get('最新价', 0))
                        prev_close = safe_float(row.get('昨收', 0))
                        high = safe_float(row.get('最高', 0))
                        low = safe_float(row.get('最低', 0))

                        # 변동폭 계산
                        amplitude = 0.0
                        if prev_close > 0:
                            amplitude = (high - low) / prev_close * 100

                        results.append({
                            'code': code,
                            'name': name,
                            'current': current,
                            'change': safe_float(row.get('涨跌额', 0)),
                            'change_pct': safe_float(row.get('涨跌幅', 0)),
                            'open': safe_float(row.get('今开', 0)),
                            'high': high,
                            'low': low,
                            'prev_close': prev_close,
                            'volume': safe_float(row.get('成交量', 0)),
                            'amount': safe_float(row.get('成交额', 0)),
                            'amplitude': amplitude,
                        })
            return results

        except Exception as e:
            logger.error(f"[Akshare] 지수 시세 받기 실패: {e}")
            return None

    def get_market_stats(self) -> Optional[Dict[str, Any]]:
        """
        시장 상승/하락 통계 받기

        데이터 소스 우선순위:
        1. 둥팡차이푸 API (ak.stock_zh_a_spot_em)
        2. 시나 API (ak.stock_zh_a_spot)
        """
        import akshare as ak

        # 둥팡차이푸 API 먼저
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            started_at = time.monotonic()
            logger.info(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot_em action=request_start"
            )
            df = _akshare_call_with_timeout(
                ak.stock_zh_a_spot_em,
                timeout=self._market_stats_call_timeout,
                call_name="ak.stock_zh_a_spot_em",
            )
            elapsed = time.monotonic() - started_at
            logger.info(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot_em action=request_complete elapsed=%.2fs",
                elapsed,
            )
            if df is not None and not df.empty:
                return self._calc_market_stats(df)
            logger.warning(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot_em action=parse status=empty"
            )
        except TimeoutError as e:
            elapsed = time.monotonic() - started_at
            logger.warning(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot_em action=request_timeout elapsed=%.2fs "
                "error=%s fallback=ak.stock_zh_a_spot",
                elapsed,
                e,
            )
        except Exception as e:
            logger.warning(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot_em action=failed error=%s fallback=ak.stock_zh_a_spot",
                e,
            )

        # 둥팡차이푸가 실패하면 시나 API 시도
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            started_at = time.monotonic()
            logger.info(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot action=request_start"
            )
            df = _akshare_call_with_timeout(
                ak.stock_zh_a_spot,
                timeout=self._market_stats_call_timeout,
                call_name="ak.stock_zh_a_spot",
            )
            elapsed = time.monotonic() - started_at
            logger.info(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot action=request_complete elapsed=%.2fs",
                elapsed,
            )
            if df is not None and not df.empty:
                return self._calc_market_stats(df)
            logger.warning(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot action=parse status=empty"
            )
        except TimeoutError as e:
            elapsed = time.monotonic() - started_at
            logger.error(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot action=request_timeout elapsed=%.2fs "
                "error=%s fallback=none",
                elapsed,
                e,
            )
        except Exception as e:
            logger.error(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot action=failed error=%s",
                e,
            )

        return None

    def _calc_market_stats(
        self,
        df: pd.DataFrame,
        ) -> Optional[Dict[str, Any]]:
        """시세 DataFrame으로 상승/하락 통계 계산."""
        import numpy as np

        df = df.copy()
        
        # 1. 비교에 쓸 기본 데이터 꺼내기: 현재가, 전일 종가
        # API마다 다른 열 이름 지원: sina/em efinance tushare xtdata
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
            
            # 거래정지 종목 거르기: efinance는 거래정지 종목 가격이 '-'로, em은 none으로 나올 때가 있음
            if pd.isna(current_price) or pd.isna(pre_close) or current_price in ['-'] or pre_close in ['-'] or amount == 0:
                continue
            
            # em, efinance는 str이라 float로 바꿔야 함
            current_price = float(current_price)
            pre_close = float(pre_close)
            
            # 접두어를 뗀 숫자만 있는 코드 얻기
            pure_code = normalize_stock_code(str(code)) 

            # A. 종목별 가격제한폭 비율 정하기(숫자 코드로 판단)
            if is_bse_code(pure_code): 
                ratio = 0.30
            elif is_kc_cy_stock(pure_code): #pure_code.startswith(('688', '30')):
                ratio = 0.20
            elif is_st_stock(name): #'ST' in str_name:
                ratio = 0.05
            else:
                ratio = 0.10

            # B. A주 규칙대로 상한가/하한가 계산: 전일 종가 * (1 ± 비율) -> 소수점 둘째 자리 반올림
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

    def get_sector_rankings(self, n: int = 5) -> Optional[Tuple[List[Dict], List[Dict]]]:
        """
        업종 섹터 등락 순위 받기

        데이터 소스 우선순위:
        1. 둥팡차이푸 API (ak.stock_board_industry_name_em)
        2. 시나 API (ak.stock_sector_spot)
        """
        import akshare as ak

        def _get_rank_top_n(df: pd.DataFrame, change_col: str, industry_name: str, n: int) -> Tuple[list, list]:
            df[change_col] = pd.to_numeric(df[change_col], errors='coerce')
            df = df.dropna(subset=[change_col])

            # 상승률 상위 n
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
        
        # 둥팡차이푸 API 먼저
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API 호출] ak.stock_board_industry_name_em() 섹터 순위 받는 중...")
            df = ak.stock_board_industry_name_em()
            if df is not None and not df.empty:
                change_col = '涨跌幅'
                name = '板块名称'
                return _get_rank_top_n(df, change_col, name, n)
            
        except Exception as e:
            logger.warning(f"[Akshare] 둥팡차이푸 API로 업종 섹터 순위 받기 실패: {e}, 시나 API 시도")

        # 둥팡차이푸가 실패하면 시나 API 시도
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API 호출] ak.stock_sector_spot() 업종 섹터 순위 받는 중(시나)...")
            df = ak.stock_sector_spot(indicator='行业')
            if df is None or df.empty:
                return None
            change_col = '涨跌幅'
            name = '板块'
            return _get_rank_top_n(df, change_col, name, n)
        
        except Exception as e:
            logger.error(f"[Akshare] 시나 API로 섹터 순위 받기도 실패: {e}")
            return None

    def get_concept_rankings(self, n: int = 5) -> Optional[Tuple[List[Dict], List[Dict]]]:
        """테마 등락 순위 받기."""
        import akshare as ak

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API 호출] ak.stock_board_concept_name_em() 테마 순위 받는 중...")
            df = ak.stock_board_concept_name_em()
            if df is None or df.empty:
                return None

            change_col = '涨跌幅'
            name_col = '板块名称'
            if change_col not in df.columns or name_col not in df.columns:
                return None

            df = df.copy()
            df[change_col] = pd.to_numeric(df[change_col], errors='coerce')
            df = df.dropna(subset=[change_col])
            top = df.nlargest(n, change_col)
            bottom = df.nsmallest(n, change_col)
            return (
                [
                    {'name': str(row[name_col]), 'change_pct': float(row[change_col])}
                    for _, row in top.iterrows()
                ],
                [
                    {'name': str(row[name_col]), 'change_pct': float(row[change_col])}
                    for _, row in bottom.iterrows()
                ],
            )
        except Exception as e:
            logger.warning(f"[Akshare] 테마 순위 받기 실패: {e}")
            return None

    def get_hot_stocks(self, n: int = 10) -> Optional[List[Dict[str, Any]]]:
        """인기 종목 순위 받기. 설정 없이 쓰는 인기 순위 소스를 차례로 시도."""
        import akshare as ak

        fetch_attempts = (
            ("东方财富人气榜", lambda top_n: self._get_eastmoney_hot_stocks(ak, top_n)),
            ("东方财富飙升榜", lambda top_n: self._get_eastmoney_hot_up_stocks(ak, top_n)),
            ("雪球关注榜", lambda top_n: self._get_xueqiu_hot_stocks(ak, top_n)),
        )
        last_error = ""
        for source, fetch in fetch_attempts:
            try:
                rows = fetch(n)
                if rows:
                    return rows[:n]
            except Exception as e:
                last_error = f"{source}: {e}"
                logger.debug("[Akshare] 인기 종목 후보 소스 실패 source=%s: %s", source, e)
        if last_error:
            logger.warning("[Akshare] 인기 종목 후보 소스가 모두 실패: %s", last_error)
        return None

    def _get_eastmoney_hot_stocks(self, ak: Any, n: int = 10) -> Optional[List[Dict[str, Any]]]:
        """둥팡차이푸 인기 종목 순위 받기."""
        self._set_random_user_agent()
        self._enforce_rate_limit()

        logger.info("[API 호출] ak.stock_hot_rank_em() 둥팡차이푸 인기 종목 받는 중...")
        df = ak.stock_hot_rank_em()
        if df is None or df.empty:
            return None

        rows: List[Dict[str, Any]] = []
        for _, row in df.head(n).iterrows():
            rows.append({
                'rank': self._safe_int(row.get('当前排名')),
                'code': str(row.get('代码', '')).strip(),
                'name': str(row.get('股票名称', '')).strip(),
                'price': self._safe_float(row.get('最新价')),
                'change_pct': self._safe_float(row.get('涨跌幅')),
                'source': '东方财富人气榜',
            })
        return rows

    def _get_eastmoney_hot_up_stocks(self, ak: Any, n: int = 10) -> Optional[List[Dict[str, Any]]]:
        """둥팡차이푸 급상승 순위 받기."""
        self._set_random_user_agent()
        self._enforce_rate_limit()

        logger.info("[API 호출] ak.stock_hot_up_em() 둥팡차이푸 급상승 순위 받는 중...")
        df = ak.stock_hot_up_em()
        if df is None or df.empty:
            return None

        code_col = self._find_first_column(df, ("代码", "股票代码"))
        name_col = self._find_first_column(df, ("股票名称", "名称", "股票简称"))
        rank_col = self._find_first_column(df, ("当前排名", "排名", "序号"))
        price_col = self._find_first_column(df, ("最新价", "现价"))
        change_col = self._find_column_containing(df, ("涨跌幅",))
        if not code_col or not name_col:
            return None

        rows: List[Dict[str, Any]] = []
        for _, row in df.head(n).iterrows():
            rows.append({
                'rank': self._safe_int(row.get(rank_col)) if rank_col else len(rows) + 1,
                'code': str(row.get(code_col, '')).strip(),
                'name': str(row.get(name_col, '')).strip(),
                'price': self._safe_float(row.get(price_col)) if price_col else None,
                'change_pct': self._safe_float(row.get(change_col)) if change_col else None,
                'source': '东方财富飙升榜',
            })
        return rows

    def _get_xueqiu_hot_stocks(self, ak: Any, n: int = 10) -> Optional[List[Dict[str, Any]]]:
        """최후 대안으로 쉐추(Xueqiu) 관심 순위 받기. 느린 API라 인기 순위가 실패했을 때만 시도."""
        self._set_random_user_agent()
        self._enforce_rate_limit()

        logger.info("[API 호출] ak.stock_hot_follow_xq() 쉐추 관심 순위 받는 중...")
        df = ak.stock_hot_follow_xq(symbol='最热门')
        if df is None or df.empty:
            return None

        rows: List[Dict[str, Any]] = []
        for idx, (_, row) in enumerate(df.head(n).iterrows(), 1):
            rows.append({
                'rank': idx,
                'code': str(row.get('股票代码', '')).strip(),
                'name': str(row.get('股票简称', '')).strip(),
                'price': self._safe_float(row.get('最新价')),
                'change_pct': None,
                'source': '雪球关注榜',
            })
        return rows

    def get_limit_up_pool(
        self,
        date: Optional[str] = None,
        n: int = 20,
    ) -> Optional[List[Dict[str, Any]]]:
        """상한가 종목 목록 받기. 연속 상한가 일수와 상한가 도달 시각 순으로 보여 줌."""
        import akshare as ak

        query_date = date or datetime.now().strftime('%Y%m%d')
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API 호출] ak.stock_zt_pool_em(date=%s) 상한가 종목 목록 받는 중...", query_date)
            df = ak.stock_zt_pool_em(date=query_date)
            if df is None or df.empty:
                return None

            df = df.copy()
            for col in ('连板数', '封板资金', '成交额', '换手率', '涨跌幅'):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            if '首次封板时间' in df.columns:
                df['首次封板时间'] = df['首次封板时间'].map(self._normalize_limit_time_value)
                df['_首次封板时间排序'] = df['首次封板时间'].where(df['首次封板时间'] != '', '999999')
            sort_cols = [col for col in ('连板数', '_首次封板时间排序') if col in df.columns]
            if sort_cols:
                ascending = [False if col == '连板数' else True for col in sort_cols]
                df = df.sort_values(sort_cols, ascending=ascending)

            rows: List[Dict[str, Any]] = []
            for _, row in df.head(n).iterrows():
                rows.append({
                    'code': str(row.get('代码', '')).strip(),
                    'name': str(row.get('名称', '')).strip(),
                    'change_pct': self._safe_float(row.get('涨跌幅')),
                    'price': self._safe_float(row.get('最新价')),
                    'amount': self._safe_float(row.get('成交额')),
                    'turnover_rate': self._safe_float(row.get('换手率')),
                    'seal_amount': self._safe_float(row.get('封板资金')),
                    'first_limit_time': str(row.get('首次封板时间', '')).strip(),
                    'last_limit_time': self._normalize_limit_time_value(row.get('最后封板时间')),
                    'break_count': self._safe_int(row.get('炸板次数')),
                    'limit_stat': str(row.get('涨停统计', '')).strip(),
                    'consecutive_boards': self._safe_int(row.get('连板数')),
                    'industry': str(row.get('所属行业', '')).strip(),
                })
            return rows
        except Exception as e:
            logger.warning(f"[Akshare] 상한가 종목 목록 받기 실패: {e}")
            return None

    @staticmethod
    def _normalize_limit_time_value(value: Any) -> str:
        """Normalize AkShare HHMMSS-like seal time values to zero-padded HHMMSS."""
        try:
            if pd.isna(value):
                return ""
        except TypeError:
            pass

        text = str(value).strip()
        if not text or text.lower() in {"nan", "nat", "none", "null", "-", "--"}:
            return ""

        if ":" in text:
            parts = text.split(":")
            try:
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
                second = int(parts[2]) if len(parts) > 2 else 0
                return f"{hour:02d}{minute:02d}{second:02d}"
            except (TypeError, ValueError):
                return text

        try:
            return f"{int(float(text)):06d}"
        except (TypeError, ValueError):
            digits = "".join(ch for ch in text if ch.isdigit())
            return digits.zfill(6) if digits else text

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if pd.isna(value):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            if pd.isna(value):
                return 0
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _find_first_column(df: pd.DataFrame, candidates: Tuple[str, ...]) -> Optional[str]:
        columns = [str(col) for col in df.columns]
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None

    @staticmethod
    def _find_column_containing(df: pd.DataFrame, keywords: Tuple[str, ...]) -> Optional[str]:
        for col in df.columns:
            col_text = str(col)
            if all(keyword in col_text for keyword in keywords):
                return col
        return None


if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = AkshareFetcher()
    
    # 일반 주식 테스트
    print("=" * 50)
    print("일반 주식 데이터 받기 테스트")
    print("=" * 50)
    try:
        df = fetcher.get_daily_data('600519')  # 마오타이
        print(f"[주식] 받기 성공, 총 {len(df)}건")
        print(df.tail())
    except Exception as e:
        print(f"[주식] 받기 실패: {e}")
    
    # ETF 테스트
    print("\n" + "=" * 50)
    print("ETF 데이터 받기 테스트")
    print("=" * 50)
    try:
        df = fetcher.get_daily_data('512400')  # 비철금속 대표 ETF
        print(f"[ETF] 받기 성공, 총 {len(df)}건")
        print(df.tail())
    except Exception as e:
        print(f"[ETF] 받기 실패: {e}")
    
    # ETF 실시간 시세 테스트
    print("\n" + "=" * 50)
    print("ETF 실시간 시세 받기 테스트")
    print("=" * 50)
    try:
        quote = fetcher.get_realtime_quote('512880')  # 증권 ETF
        if quote:
            print(f"[ETF 실시간] {quote.name}: 가격={quote.price}, 등락률={quote.change_pct}%")
        else:
            print("[ETF 실시간] 데이터를 받지 못함")
    except Exception as e:
        print(f"[ETF 실시간] 받기 실패: {e}")
    
    # 홍콩 주식 과거 데이터 테스트
    print("\n" + "=" * 50)
    print("홍콩 주식 과거 데이터 받기 테스트")
    print("=" * 50)
    try:
        df = fetcher.get_daily_data('00700')  # 텐센트
        print(f"[홍콩 주식] 받기 성공, 총 {len(df)}건")
        print(df.tail())
    except Exception as e:
        print(f"[홍콩 주식] 받기 실패: {e}")
    
    # 홍콩 주식 실시간 시세 테스트
    print("\n" + "=" * 50)
    print("홍콩 주식 실시간 시세 받기 테스트")
    print("=" * 50)
    try:
        quote = fetcher.get_realtime_quote('00700')  # 텐센트
        if quote:
            print(f"[홍콩 주식 실시간] {quote.name}: 가격={quote.price}, 등락률={quote.change_pct}%")
        else:
            print("[홍콩 주식 실시간] 데이터를 받지 못함")
    except Exception as e:
        print(f"[홍콩 주식 실시간] 받기 실패: {e}")

    # 시장 통계 테스트
    print("\n" + "=" * 50)
    print("Testing get_market_stats (akshare)")
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

    # 매물대 분포 데이터 테스트
    print("\n" + "=" * 50)
    print("매물대 분포 데이터 받기 테스트")
    print("=" * 50)
    try:
        chip = fetcher.get_chip_distribution('600519')  # 마오타이
    except Exception as e:
        print(f"[매물대 분포] 받기 실패: {e}")

    # 업종 섹터 순위 테스트
    print("\n" + "=" * 50)
    print("업종 섹터 순위 받기 테스트")
    print("=" * 50)
    try:
        rankings = fetcher.get_sector_rankings(n=5)
        if rankings:
            top, bottom = rankings
            print("상승률 순위 Top 5:")
            for sector in top:
                print(f"{sector['name']}: {sector['change_pct']}%")
            print("\n하락률 순위 Top 5:")
            for sector in bottom:
                print(f"{sector['name']}: {sector['change_pct']}%")
        else:
            print("업종 섹터 순위 데이터를 받지 못함")
    except Exception as e:
        print(f"[업종 섹터 순위] 받기 실패: {e}")
