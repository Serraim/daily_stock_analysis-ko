# -*- coding: utf-8 -*-
"""
===================================
PytdxFetcher - 통달신(TDX) 데이터 소스 (Priority 2)
===================================

데이터 출처: 통달신 시세 서버(pytdx 라이브러리)
특징: 무료, Token 불필요, 시세 서버에 직접 연결
장점: 실시간 데이터, 안정적, 사용량 제한 없음

핵심 전략:
1. 여러 서버 사이 자동 전환
2. 연결 시간 초과 시 자동 재연결
3. 실패하면 점점 간격을 늘려 재시도
"""

import logging
import re
import time
from contextlib import contextmanager
from typing import Optional, Generator, List, Tuple

import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .base import (
    BaseFetcher,
    DataFetchError,
    DataSourceUnavailableError,
    STANDARD_COLUMNS,
    is_bse_code,
    normalize_stock_code,
    _is_hk_market,
)
import os

logger = logging.getLogger(__name__)

_PYTDX_CONNECTION_COOLDOWN_SECONDS = 15.0


def _parse_hosts_from_env() -> Optional[List[Tuple[str, int]]]:
    """
    환경 변수로 통달신 서버 목록을 만듦.

    우선순위:
    1. PYTDX_SERVERS: 쉼표로 구분 "ip:port,ip:port"(예: "192.168.1.1:7709,10.0.0.1:7709")
    2. PYTDX_HOST + PYTDX_PORT: 서버 하나
    3. 둘 다 없으면 None 반환(호출하는 쪽이 DEFAULT_HOSTS 사용)
    """
    servers = os.getenv("PYTDX_SERVERS", "").strip()
    if servers:
        result = []
        for part in servers.split(","):
            part = part.strip()
            if ":" in part:
                host, port_str = part.rsplit(":", 1)
                host, port_str = host.strip(), port_str.strip()
                if host and port_str:
                    try:
                        result.append((host, int(port_str)))
                    except ValueError:
                        logger.warning(f"Invalid PYTDX_SERVERS entry: {part}")
            else:
                logger.warning(f"Invalid PYTDX_SERVERS entry (missing port): {part}")
        if result:
            return result

    host = os.getenv("PYTDX_HOST", "").strip()
    port_str = os.getenv("PYTDX_PORT", "").strip()
    if host and port_str:
        try:
            return [(host, int(port_str))]
        except ValueError:
            logger.warning(f"Invalid PYTDX_HOST/PYTDX_PORT: {host}:{port_str}")

    return None


def _is_us_code(stock_code: str) -> bool:
    """
    미국 주식 코드인지 판단
    
    미국 주식 코드 규칙:
    - 대문자 1-5개, 예: 'AAPL', 'TSLA'
    - '.'이 들어갈 수 있음, 예: 'BRK.B'
    """
    code = stock_code.strip().upper()
    return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))


class PytdxFetcher(BaseFetcher):
    """
    통달신 데이터 소스 구현
    
    우선순위: 2(Tushare와 같은 등급)
    데이터 출처: 통달신 시세 서버
    
    핵심 전략:
    - 가장 좋은 서버 자동 선택
    - 연결 실패 시 서버 자동 전환
    - 실패하면 점점 간격을 늘려 재시도
    
    Pytdx 특징:
    - 무료, 가입 불필요
    - 시세 서버에 직접 연결
    - 실시간 시세와 과거 데이터 지원
    - 종목 이름 조회 지원
    """
    
    name = "PytdxFetcher"
    priority = int(os.getenv("PYTDX_PRIORITY", "2"))
    
    # 기본 통달신 시세 서버 목록
    DEFAULT_HOSTS = [
        ("119.147.212.81", 7709),  # 선전
        ("112.74.214.43", 7727),   # 선전
        ("221.231.141.60", 7709),  # 상하이
        ("101.227.73.20", 7709),   # 상하이
        ("101.227.77.254", 7709),  # 상하이
        ("14.215.128.18", 7709),   # 광저우
        ("59.173.18.140", 7709),   # 우한
        ("180.153.39.51", 7709),   # 항저우
    ]
    # Pytdx get_security_list returns at most 1000 items per page
    SECURITY_LIST_PAGE_SIZE = 1000
    
    def __init__(self, hosts: Optional[List[Tuple[str, int]]] = None):
        """
        PytdxFetcher 초기화

        Args:
            hosts: 서버 목록 [(host, port), ...]. 넘기지 않으면 환경 변수
                   PYTDX_SERVERS(ip:port,ip:port)나 PYTDX_HOST+PYTDX_PORT를 먼저 쓰고,
                   없으면 내장 DEFAULT_HOSTS 사용.
        """
        if hosts is not None:
            self._hosts = hosts
        else:
            env_hosts = _parse_hosts_from_env()
            self._hosts = env_hosts if env_hosts else self.DEFAULT_HOSTS
        self._api = None
        self._connected = False
        self._current_host_idx = 0
        self._stock_list_cache = None  # 종목 목록 캐시
        self._stock_name_cache = {}    # 종목 이름 캐시 {code: name}
        self._unavailable_until = 0.0
        self._last_unavailable_reason = ""

    def _is_in_connection_cooldown(self) -> bool:
        return time.time() < self._unavailable_until

    def _mark_connection_cooldown(self, reason: str) -> None:
        self._unavailable_until = time.time() + _PYTDX_CONNECTION_COOLDOWN_SECONDS
        self._last_unavailable_reason = str(reason or "").strip()
        logger.info(
            "Pytdx 연결 실패, %.0fs 동안 대기: %s",
            _PYTDX_CONNECTION_COOLDOWN_SECONDS,
            self._last_unavailable_reason or "unknown",
        )

    def is_available_for_request(self, capability: str = "") -> bool:
        return not self._is_in_connection_cooldown()
    
    def _get_pytdx(self):
        """
        pytdx 모듈 지연 로딩
        
        처음 쓸 때만 import해서, 설치 안 됐을 때 오류가 나지 않게 함
        """
        try:
            from pytdx.hq import TdxHq_API
            return TdxHq_API
        except ImportError:
            logger.warning("pytdx가 설치되지 않음, 다음을 실행하세요: pip install pytdx")
            return None
    
    @contextmanager
    def _pytdx_session(self) -> Generator:
        """
        Pytdx 연결 컨텍스트 매니저
        
        보장하는 것:
        1. 컨텍스트에 들어갈 때 자동 연결
        2. 컨텍스트를 나갈 때 자동 연결 해제
        3. 예외가 나도 제대로 연결 해제
        
        사용 예:
            with self._pytdx_session() as api:
                # 여기서 데이터 조회 실행
        """
        if self._is_in_connection_cooldown():
            raise DataSourceUnavailableError(
                f"Pytdx temporarily unavailable: {self._last_unavailable_reason or 'connection cooldown'}"
            )

        TdxHq_API = self._get_pytdx()
        if TdxHq_API is None:
            raise DataFetchError("pytdx 라이브러리가 설치되지 않음")
        
        api = TdxHq_API()
        connected = False
        
        try:
            # 서버 연결 시도(가장 좋은 서버 자동 선택)
            for i in range(len(self._hosts)):
                host_idx = (self._current_host_idx + i) % len(self._hosts)
                host, port = self._hosts[host_idx]
                
                try:
                    if api.connect(host, port, time_out=5):
                        connected = True
                        self._current_host_idx = host_idx
                        logger.debug(f"Pytdx 연결 성공: {host}:{port}")
                        break
                except Exception as e:
                    logger.debug(f"Pytdx {host}:{port} 연결 실패: {e}")
                    continue
            
            if not connected:
                self._mark_connection_cooldown("Pytdx 어떤 서버에도 연결할 수 없음")
                raise DataFetchError("Pytdx 어떤 서버에도 연결할 수 없음")
            
            yield api
            
        finally:
            # 반드시 연결 해제
            try:
                api.disconnect()
                logger.debug("Pytdx 연결 해제됨")
            except Exception as e:
                logger.warning(f"Pytdx 연결 해제 중 오류: {e}")
    
    def _get_market_code(self, stock_code: str) -> Tuple[int, str]:
        """
        종목 코드로 시장 판단
        
        Pytdx 시장 코드:
        - 0: 선전
        - 1: 상하이
        
        Args:
            stock_code: 종목 코드
            
        Returns:
            (market, code) 튜플
        """
        raw_code = stock_code.strip()
        upper = raw_code.upper()
        prefix, separator, suffix = raw_code.partition(".")
        if separator and prefix:
            prefix_upper = prefix.strip().upper()
            if prefix_upper in ('SH', 'SS'):
                normalized = normalize_stock_code(suffix.strip())
                if normalized.isdigit() and len(normalized) == 6:
                    return 1, normalized
            if prefix_upper == 'SZ':
                normalized = normalize_stock_code(suffix.strip())
                if normalized.isdigit() and len(normalized) == 6:
                    return 0, normalized

        code = normalize_stock_code(raw_code)

        if upper.startswith(('SH', 'SS')) or upper.endswith(('.SH', '.SS')):
            return 1, code
        if upper.startswith('SZ') or upper.endswith('.SZ'):
            return 0, code
        
        # 코드 앞자리로 시장 판단
        # 상하이: 60xxxx, 68xxxx(커촹반)
        # 선전: 00xxxx, 30xxxx(창업판), 002xxx(중소판)
        if code.startswith(('60', '68')):
            return 1, code  # 상하이
        else:
            return 0, code  # 선전

    def _build_stock_list_cache(self, api) -> None:
        """
        Build a full stock code -> name cache from paginated security lists.
        """
        self._stock_list_cache = {}

        for market in (0, 1):
            start = 0
            while True:
                stocks = api.get_security_list(market, start) or []
                for stock in stocks:
                    code = stock.get('code')
                    name = stock.get('name')
                    if code and name:
                        self._stock_list_cache[code] = name

                if len(stocks) < self.SECURITY_LIST_PAGE_SIZE:
                    break

                start += self.SECURITY_LIST_PAGE_SIZE
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        통달신에서 원본 데이터 가져오기
        
        get_security_bars()로 일봉 데이터 가져오기
        
        흐름:
        1. 미국 주식인지 확인(지원 안 함)
        2. 컨텍스트 매니저로 연결 관리
        3. 시장 코드 판단
        4. API 호출로 K선 데이터 가져오기
        """
        # 미국 주식은 지원 안 함. 예외를 던져 DataFetcherManager가 다른 데이터 소스로 바꾸게 함
        if _is_us_code(stock_code):
            raise DataFetchError(f"PytdxFetcher는 미국 주식 {stock_code}을(를) 지원하지 않음, AkshareFetcher나 YfinanceFetcher를 쓰세요")

        # 홍콩 주식은 지원 안 함. 예외를 던져 DataFetcherManager가 다른 데이터 소스로 바꾸게 함
        if _is_hk_market(stock_code):
            raise DataFetchError(f"PytdxFetcher는 홍콩 주식 {stock_code}을(를) 지원하지 않음, AkshareFetcher를 쓰세요")

        # 베이징거래소는 지원 안 함. 예외를 던져 DataFetcherManager가 다른 데이터 소스로 바꾸게 함
        if is_bse_code(stock_code):
            raise DataFetchError(
                f"PytdxFetcher는 베이징거래소 {stock_code}을(를) 지원하지 않음, 다른 데이터 소스로 자동 전환"
            )
        
        market, code = self._get_market_code(stock_code)
        
        # 가져올 거래일 수 계산(추정)
        from datetime import datetime as dt
        start_dt = dt.strptime(start_date, '%Y-%m-%d')
        end_dt = dt.strptime(end_date, '%Y-%m-%d')
        days = (end_dt - start_dt).days
        count = min(max(days * 5 // 7 + 10, 30), 800)  # 거래일 추정, 최대 800건
        
        logger.debug(f"Pytdx 호출 get_security_bars(market={market}, code={code}, count={count})")
        
        with self._pytdx_session() as api:
            try:
                # 일봉 K선 데이터 가져오기
                # category: 9-일봉, 0-5분, 1-15분, 2-30분, 3-1시간
                data = api.get_security_bars(
                    category=9,  # 일봉
                    market=market,
                    code=code,
                    start=0,  # 최신부터 시작
                    count=count
                )
                
                if data is None or len(data) == 0:
                    raise DataFetchError(f"Pytdx에서 {stock_code} 데이터를 찾지 못함")
                
                # DataFrame으로 변환
                df = api.to_df(data)
                
                # 날짜 범위 필터링
                df['datetime'] = pd.to_datetime(df['datetime'])
                df = df[(df['datetime'] >= start_date) & (df['datetime'] <= end_date)]
                
                return df
                
            except Exception as e:
                if isinstance(e, DataFetchError):
                    raise
                raise DataFetchError(f"Pytdx 데이터 받기 실패: {e}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        Pytdx 데이터 표준화
        
        Pytdx가 돌려주는 열 이름:
        datetime, open, high, low, close, vol, amount
        
        표준 열 이름으로 매핑해야 함:
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # 열 이름 매핑
        column_mapping = {
            'datetime': 'date',
            'vol': 'volume',
        }
        
        df = df.rename(columns=column_mapping)
        
        # 등락률 계산(pytdx는 등락률을 주지 않아 직접 계산)
        if 'pct_chg' not in df.columns and 'close' in df.columns:
            df['pct_chg'] = df['close'].pct_change() * 100
            df['pct_chg'] = df['pct_chg'].fillna(0).round(2)
        
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
        
        Args:
            stock_code: 종목 코드
            
        Returns:
            종목 이름, 실패하면 None
        """
        # 홍콩 주식은 지원 안 함(pytdx에는 홍콩 주식 데이터가 없음)
        if _is_hk_market(stock_code):
            return None

        # 먼저 캐시 확인
        if stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]
        
        try:
            market, code = self._get_market_code(stock_code)
            
            with self._pytdx_session() as api:
                # 종목 목록 가져오기(캐시)
                if self._stock_list_cache is None:
                    self._build_stock_list_cache(api)
                
                # 종목 이름 찾기
                name = self._stock_list_cache.get(code)
                if name:
                    self._stock_name_cache[stock_code] = name
                    return name
                
                # get_finance_info 사용 시도
                finance_info = api.get_finance_info(market, code)
                if finance_info and 'name' in finance_info:
                    name = finance_info['name']
                    self._stock_name_cache[stock_code] = name
                    return name
                
        except Exception as e:
            logger.debug(f"Pytdx 종목 이름 받기 실패 {stock_code}: {e}")
        
        return None
    
    def get_realtime_quote(self, stock_code: str) -> Optional[dict]:
        """
        실시간 시세 가져오기
        
        Args:
            stock_code: 종목 코드
            
        Returns:
            실시간 시세 데이터 딕셔너리, 실패하면 None
        """
        if is_bse_code(stock_code):
            raise DataFetchError(
                f"PytdxFetcher는 베이징거래소 {stock_code}을(를) 지원하지 않음, 다른 데이터 소스로 자동 전환"
            )
        try:
            market, code = self._get_market_code(stock_code)
            
            with self._pytdx_session() as api:
                data = api.get_security_quotes([(market, code)])
                
                if data and len(data) > 0:
                    quote = data[0]
                    return {
                        'code': stock_code,
                        'name': quote.get('name', ''),
                        'price': quote.get('price', 0),
                        'open': quote.get('open', 0),
                        'high': quote.get('high', 0),
                        'low': quote.get('low', 0),
                        'pre_close': quote.get('last_close', 0),
                        'volume': quote.get('vol', 0),
                        'amount': quote.get('amount', 0),
                        'bid_prices': [quote.get(f'bid{i}', 0) for i in range(1, 6)],
                        'ask_prices': [quote.get(f'ask{i}', 0) for i in range(1, 6)],
                    }
        except Exception as e:
            logger.warning(f"Pytdx 실시간 시세 받기 실패 {stock_code}: {e}")
        
        return None


if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = PytdxFetcher()
    
    try:
        # 과거 데이터 테스트
        df = fetcher.get_daily_data('600519')  # 마오타이
        print(f"받기 성공, 총 {len(df)}건")
        print(df.tail())
        
        # 종목 이름 테스트
        name = fetcher.get_stock_name('600519')
        print(f"종목 이름: {name}")
        
        # 실시간 시세 테스트
        quote = fetcher.get_realtime_quote('600519')
        print(f"실시간 시세: {quote}")
        
    except Exception as e:
        print(f"받기 실패: {e}")
