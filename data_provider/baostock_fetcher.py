# -*- coding: utf-8 -*-
"""
===================================
BaostockFetcher - 예비 데이터 소스 2 (Priority 3)
===================================

데이터 출처: Baostock(증권보)
특징: 무료, Token 불필요, 로그인 관리 필요
장점: 안정적, 사용량 제한 없음

핵심 전략:
1. bs.login()과 bs.logout() 수명 주기 관리
2. 컨텍스트 매니저로 연결 누수 방지
3. 실패하면 점점 간격을 늘려 재시도
"""

import logging
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Generator

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
    STANDARD_COLUMNS,
    is_bse_code,
    normalize_stock_code,
    _is_hk_market,
)
import os

logger = logging.getLogger(__name__)


def _is_us_code(stock_code: str) -> bool:
    """
    미국 주식 코드인지 판단
    
    미국 주식 코드 규칙:
    - 대문자 1-5개, 예: 'AAPL', 'TSLA'
    - '.'이 들어갈 수 있음, 예: 'BRK.B'
    """
    code = stock_code.strip().upper()
    return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))


class BaostockFetcher(BaseFetcher):
    """
    Baostock 데이터 소스 구현
    
    우선순위: 3
    데이터 출처: Baostock(증권보) API
    
    핵심 전략:
    - 컨텍스트 매니저로 연결 수명 주기 관리
    - 요청마다 로그인/로그아웃을 다시 해서 연결 누수 방지
    - 실패하면 점점 간격을 늘려 재시도
    
    Baostock 특징:
    - 무료, 가입 불필요
    - 로그인/로그아웃을 직접 해야 함
    - 데이터 갱신이 조금 늦음(T+1)
    """
    
    name = "BaostockFetcher"
    priority = int(os.getenv("BAOSTOCK_PRIORITY", "3"))
    
    def __init__(self):
        """BaostockFetcher 초기화"""
        self._bs_module = None
    
    def _get_baostock(self):
        """
        baostock 모듈 지연 로딩
        
        처음 쓸 때만 import해서, 설치 안 됐을 때 오류가 나지 않게 함
        """
        if self._bs_module is None:
            import baostock as bs
            self._bs_module = bs
        return self._bs_module
    
    @contextmanager
    def _baostock_session(self) -> Generator:
        """
        Baostock 연결 컨텍스트 매니저
        
        보장하는 것:
        1. 컨텍스트에 들어갈 때 자동 로그인
        2. 컨텍스트를 나갈 때 자동 로그아웃
        3. 예외가 나도 제대로 로그아웃
        
        사용 예:
            with self._baostock_session():
                # 여기서 데이터 조회 실행
        """
        bs = self._get_baostock()
        login_result = None
        
        try:
            # Baostock 로그인
            login_result = bs.login()
            
            if login_result.error_code != '0':
                raise DataFetchError(f"Baostock 로그인 실패: {login_result.error_msg}")
            
            logger.debug("Baostock 로그인 성공")
            
            yield bs
            
        finally:
            # 연결 누수를 막으려고 반드시 로그아웃
            try:
                logout_result = bs.logout()
                if logout_result.error_code == '0':
                    logger.debug("Baostock 로그아웃 성공")
                else:
                    logger.warning(f"Baostock 로그아웃 이상: {logout_result.error_msg}")
            except Exception as e:
                logger.warning(f"Baostock 로그아웃 중 오류: {e}")
    
    def _convert_stock_code(self, stock_code: str) -> str:
        """
        종목 코드를 Baostock 형식으로 변환
        
        Baostock이 요구하는 형식:
        - 상하이: sh.600519
        - 선전: sz.000001
        
        Args:
            stock_code: 원래 코드, 예: '600519', '000001'
            
        Returns:
            Baostock 형식 코드, 예: 'sh.600519', 'sz.000001'
        """
        raw_code = stock_code.strip()
        upper = raw_code.upper()

        # HK stocks are not supported by Baostock
        if _is_hk_market(raw_code):
            raise DataFetchError(f"BaostockFetcher는 홍콩 주식 {raw_code}을(를) 지원하지 않음, AkshareFetcher를 쓰세요")

        # 기존 소문자 baostock 형식 입력도 내부적으로 받아주지만, 사용자 설정에는 6자리 숫자 코드를 권장.
        if raw_code.startswith(('sh.', 'sz.')):
            return raw_code.lower()

        exchange_hint = None
        if upper.startswith(('SH', 'SS')) or upper.endswith(('.SH', '.SS')):
            exchange_hint = 'sh'
        elif upper.startswith('SZ') or upper.endswith('.SZ'):
            exchange_hint = 'sz'

        code = normalize_stock_code(raw_code)

        if exchange_hint in ('sh', 'sz') and code.isdigit() and len(code) == 6:
            return f"{exchange_hint}.{code}"
        
        # ETF: Shanghai ETF (51xx, 52xx, 56xx, 58xx) -> sh; Shenzhen ETF (15xx, 16xx, 18xx) -> sz
        if len(code) == 6:
            if code.startswith(('51', '52', '56', '58')):
                return f"sh.{code}"
            if code.startswith(('15', '16', '18')):
                return f"sz.{code}"

        # 코드 앞자리로 시장 판단
        if code.startswith(('600', '601', '603', '605', '688')):
            return f"sh.{code}"
        elif code.startswith(('000', '001', '002', '003', '300', '301')):
            return f"sz.{code}"
        else:
            logger.warning(f"종목 {code}의 시장을 알 수 없어 기본값 선전 시장 사용")
            return f"sz.{code}"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Baostock에서 원본 데이터 가져오기
        
        query_history_k_data_plus()로 일봉 데이터 가져오기
        
        흐름:
        1. 미국 주식인지 확인(지원 안 함)
        2. 컨텍스트 매니저로 연결 관리
        3. 종목 코드 형식 변환
        4. API 호출로 데이터 조회
        5. 결과를 DataFrame으로 변환
        """
        # 미국 주식은 지원 안 함. 예외를 던져 DataFetcherManager가 다른 데이터 소스로 바꾸게 함
        if _is_us_code(stock_code):
            raise DataFetchError(f"BaostockFetcher는 미국 주식 {stock_code}을(를) 지원하지 않음, AkshareFetcher나 YfinanceFetcher를 쓰세요")

        # 홍콩 주식은 지원 안 함. 예외를 던져 DataFetcherManager가 다른 데이터 소스로 바꾸게 함
        if _is_hk_market(stock_code):
            raise DataFetchError(f"BaostockFetcher는 홍콩 주식 {stock_code}을(를) 지원하지 않음, AkshareFetcher를 쓰세요")

        # 베이징거래소는 지원 안 함. 예외를 던져 DataFetcherManager가 다른 데이터 소스로 바꾸게 함
        if is_bse_code(stock_code):
            raise DataFetchError(
                f"BaostockFetcher는 베이징거래소 {stock_code}을(를) 지원하지 않음, 다른 데이터 소스로 자동 전환"
            )
        
        # 코드 형식 변환
        bs_code = self._convert_stock_code(stock_code)
        
        logger.debug(f"Baostock 호출 query_history_k_data_plus({bs_code}, {start_date}, {end_date})")
        
        with self._baostock_session() as bs:
            try:
                # 일봉 데이터 조회
                # adjustflag: 1-후복권, 2-전복권, 3-복권 안 함
                rs = bs.query_history_k_data_plus(
                    code=bs_code,
                    fields="date,open,high,low,close,volume,amount,pctChg",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",  # 일봉
                    adjustflag="2"  # 전복권
                )
                
                if rs.error_code != '0':
                    raise DataFetchError(f"Baostock 조회 실패: {rs.error_msg}")
                
                # DataFrame으로 변환
                data_list = []
                while rs.next():
                    data_list.append(rs.get_row_data())
                
                if not data_list:
                    raise DataFetchError(f"Baostock에서 {stock_code} 데이터를 찾지 못함")
                
                df = pd.DataFrame(data_list, columns=rs.fields)
                
                return df
                
            except Exception as e:
                if isinstance(e, DataFetchError):
                    raise
                raise DataFetchError(f"Baostock 데이터 받기 실패: {e}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        Baostock 데이터 표준화
        
        Baostock이 돌려주는 열 이름:
        date, open, high, low, close, volume, amount, pctChg
        
        표준 열 이름으로 매핑해야 함:
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # 열 이름 매핑(pctChg만 처리하면 됨)
        column_mapping = {
            'pctChg': 'pct_chg',
        }
        
        df = df.rename(columns=column_mapping)
        
        # 숫자형 변환(Baostock은 전부 문자열로 돌려줌)
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
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
        
        Baostock의 query_stock_basic API로 종목 기본 정보 가져오기
        
        Args:
            stock_code: 종목 코드
            
        Returns:
            종목 이름, 실패하면 None
        """
        # 캐시 확인
        if hasattr(self, '_stock_name_cache') and stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]
        
        # 캐시 초기화
        if not hasattr(self, '_stock_name_cache'):
            self._stock_name_cache = {}
        
        try:
            bs_code = self._convert_stock_code(stock_code)
            
            with self._baostock_session() as bs:
                # 종목 기본 정보 조회
                rs = bs.query_stock_basic(code=bs_code)
                
                if rs.error_code == '0':
                    data_list = []
                    while rs.next():
                        data_list.append(rs.get_row_data())
                    
                    if data_list:
                        # Baostock이 돌려주는 필드:code, code_name, ipoDate, outDate, type, status
                        fields = rs.fields
                        name_idx = fields.index('code_name') if 'code_name' in fields else None
                        if name_idx is not None and len(data_list[0]) > name_idx:
                            name = data_list[0][name_idx]
                            self._stock_name_cache[stock_code] = name
                            logger.debug(f"Baostock 종목 이름 받기 성공: {stock_code} -> {name}")
                            return name
                
        except Exception as e:
            logger.warning(f"Baostock 종목 이름 받기 실패 {stock_code}: {e}")
        
        return None
    
    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """
        종목 목록 가져오기
        
        Baostock의 query_stock_basic API로 전체 종목 목록 가져오기
        
        Returns:
            code, name 열이 있는 DataFrame, 실패하면 None
        """
        try:
            with self._baostock_session() as bs:
                # 전체 종목 기본 정보 조회
                rs = bs.query_stock_basic()
                
                if rs.error_code == '0':
                    data_list = []
                    while rs.next():
                        data_list.append(rs.get_row_data())
                    
                    if data_list:
                        df = pd.DataFrame(data_list, columns=rs.fields)
                        
                        # 코드 형식 변환(sh. 또는 sz. 접두사 제거)
                        df['code'] = df['code'].apply(lambda x: x.split('.')[1] if '.' in x else x)
                        df = df.rename(columns={'code_name': 'name'})
                        
                        # 캐시 갱신
                        if not hasattr(self, '_stock_name_cache'):
                            self._stock_name_cache = {}
                        for _, row in df.iterrows():
                            self._stock_name_cache[row['code']] = row['name']
                        
                        logger.info(f"Baostock 종목 목록 받기 성공: {len(df)}건")
                        return df[['code', 'name']]
                
        except Exception as e:
            logger.warning(f"Baostock 종목 목록 받기 실패: {e}")
        
        return None


if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = BaostockFetcher()
    
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
