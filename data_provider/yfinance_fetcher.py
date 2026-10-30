# -*- coding: utf-8 -*-
"""
===================================
YfinanceFetcher - 최후 대체 데이터 소스 (Priority 4)
===================================

데이터 출처: Yahoo Finance(yfinance 라이브러리 사용)
특징: 해외 데이터 소스, 지연되거나 빠질 수 있음
역할: 중국 내 데이터 소스가 모두 실패했을 때의 마지막 수단

핵심 전략:
1. A주 코드를 yfinance 형식(.SS / .SZ)으로 자동 변환
2. Yahoo Finance 데이터 형식 차이 처리
3. 실패하면 점점 간격을 늘려 재시도
"""

import csv
import logging
from datetime import datetime
from io import StringIO
from typing import Optional, List, Dict, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS, _is_hk_market, is_bse_code
from .realtime_types import UnifiedRealtimeQuote, RealtimeSource
from .us_index_mapping import get_us_index_yf_symbol, is_us_stock_code
from .yfinance_fundamental_adapter import _safe_float
from src.services.market_symbol_utils import get_suffix_market, is_suffix_market_symbol

# 로컬 종목 매핑 패치를 선택적으로 import, 없으면 빈 딕셔너리로 대체
try:
    from src.data.stock_mapping import STOCK_NAME_MAP, is_meaningful_stock_name
except (ImportError, ModuleNotFoundError):
    STOCK_NAME_MAP = {}

    def is_meaningful_stock_name(name: str | None, stock_code: str) -> bool:
        """간단한 이름 유효성 검사(대체용)"""
        if not name:
            return False
        n = str(name).strip()
        return bool(n and n.upper() != str(stock_code).strip().upper())

import os

logger = logging.getLogger(__name__)


class YfinanceFetcher(BaseFetcher):
    """
    Yahoo Finance 데이터 소스 구현

    우선순위: 4(가장 낮음, 최후 대체 수단)
    데이터 출처: Yahoo Finance

    핵심 전략:
    - 종목 코드 형식 자동 변환
    - 시간대와 데이터 형식 차이 처리
    - 실패하면 점점 간격을 늘려 재시도

    주의할 점:
    - A주 데이터는 늦을 수 있음
    - 일부 종목은 데이터가 없을 수 있음
    - 데이터 정밀도가 중국 내 소스와 조금 다를 수 있음
    """

    name = "YfinanceFetcher"
    priority = int(os.getenv("YFINANCE_PRIORITY", "4"))

    def __init__(self):
        """YfinanceFetcher 초기화"""
        pass

    @staticmethod
    def _is_jp_kr_suffix_stock(stock_code: str) -> bool:
        """Return True for supported JP/KR suffix-only Yahoo symbols."""
        return is_suffix_market_symbol(stock_code, "jp") or is_suffix_market_symbol(stock_code, "kr")

    @staticmethod
    def _is_tw_suffix_stock(stock_code: str) -> bool:
        """Return True for supported Taiwan suffix-only Yahoo symbols (TWSE `.TW` / TPEx `.TWO`).

        Taiwan base codes are 4-6 digits (common stocks 4, ETFs/others up to 6,
        e.g. 00878 / 006208), wider than the JP `.T` range.
        """
        return is_suffix_market_symbol(stock_code, "tw")

    def _convert_stock_code(self, stock_code: str) -> str:
        """
        종목 코드를 Yahoo Finance 형식으로 변환

        Yahoo Finance 코드 형식:
        - A주 상하이: 600519.SS (Shanghai Stock Exchange)
        - A주 선전: 000001.SZ (Shenzhen Stock Exchange)
        - 홍콩 주식: 0700.HK (Hong Kong Stock Exchange)
        - 미국 주식: AAPL, TSLA, GOOGL (접미사 없음)

        Args:
            stock_code: 원래 코드, 예: '600519', 'hk00700', 'AAPL'

        Returns:
            Yahoo Finance 형식 코드

        Examples:
            >>> fetcher._convert_stock_code('600519')
            '600519.SS'
            >>> fetcher._convert_stock_code('hk00700')
            '0700.HK'
            >>> fetcher._convert_stock_code('AAPL')
            'AAPL'
        """
        code = stock_code.strip().upper()

        # 미국 지수: Yahoo Finance 심볼로 매핑(예: SPX -> ^GSPC)
        yf_symbol, _ = get_us_index_yf_symbol(code)
        if yf_symbol:
            logger.debug(f"미국 지수로 인식: {code} -> {yf_symbol}")
            return yf_symbol

        # 미국 주식: 대문자 1-5개(.X 접미사 선택), 그대로 반환
        if is_us_stock_code(code):
            logger.debug(f"미국 주식 코드로 인식: {code}")
            return code

        # 일본/한국/대만 주식 MVP: 접미사가 붙은 Yahoo Finance 코드는 그대로 Yahoo에 넘김.
        if self._is_jp_kr_suffix_stock(code) or self._is_tw_suffix_stock(code):
            logger.debug(f"일본/한국/대만 Yahoo 접미사 코드로 인식: {code}")
            return code

        # 홍콩 주식: hk 접두사 -> .HK 접미사
        if code.startswith('HK'):
            hk_code = code[2:].lstrip('0') or '0'  # 앞의 0을 지우되 0 하나는 남김
            hk_code = hk_code.zfill(4)  # 4자리로 맞춤
            logger.debug(f"홍콩 주식 코드 변환: {stock_code} -> {hk_code}.HK")
            return f"{hk_code}.HK"

        # 홍콩 숫자 코드: 숫자만 4-5자리(예: 00700, 02513, 0001)면 홍콩 주식으로 처리.
        # A주 코드는 모두 6자리라 4-5자리 숫자는 A주나 BSE일 수 없음(BSE는
        # 4/8/920xxx 6자리). 그래서 .SZ 기본 처리보다 먼저 .HK로 보내서, yfinance가
        # 02513 같은 신규 홍콩 주식을 선전 접미사로 잘못 붙여 Yahoo 404가 나는 것을 막음. 자세한 건 issue #2091.
        if code.isdigit() and 4 <= len(code) <= 5:
            hk_code = code.lstrip('0') or '0'
            hk_code = hk_code.zfill(4)
            logger.debug(f"홍콩 숫자 코드로 인식: {stock_code} -> {hk_code}.HK")
            return f"{hk_code}.HK"

        # 이미 접미사가 있는 경우
        if '.SS' in code or '.SZ' in code or '.HK' in code or '.BJ' in code:
            return code

        # .SH 접미사가 있으면 제거
        code = code.replace('.SH', '')

        # ETF: Shanghai ETF (51xx, 52xx, 56xx, 58xx) -> .SS; Shenzhen ETF (15xx, 16xx, 18xx) -> .SZ
        if len(code) == 6:
            if code.startswith(('51', '52', '56', '58')):
                return f"{code}.SS"
            if code.startswith(('15', '16', '18')):
                return f"{code}.SZ"

        # BSE (Beijing Stock Exchange): 8xxxxx, 4xxxxx, 920xxx
        if is_bse_code(code):
            base = code.split('.')[0] if '.' in code else code
            return f"{base}.BJ"

        # A주: 코드 앞자리로 시장 판단
        if code.startswith(('600', '601', '603', '688')):
            return f"{code}.SS"
        elif code.startswith(('000', '002', '300')):
            return f"{code}.SZ"
        else:
            logger.warning(f"종목 {code}의 시장을 알 수 없어 기본값 선전 시장 사용")
            return f"{code}.SZ"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Yahoo Finance에서 원본 데이터 가져오기

        yfinance.download()로 과거 데이터 가져오기

        흐름:
        1. 종목 코드 형식 변환
        2. yfinance API 호출
        3. 받은 데이터 처리
        """
        import yfinance as yf

        # 코드 형식 변환
        yf_code = self._convert_stock_code(stock_code)

        logger.debug(f"yfinance.download 호출({yf_code}, {start_date}, {end_date})")

        try:
            # yfinance로 데이터 다운로드
            df = yf.download(
                tickers=yf_code,
                start=start_date,
                end=end_date,
                progress=False,  # 진행 막대 끄기
                auto_adjust=True,  # 가격 자동 조정(수정주가)
                multi_level_index=True
            )

            # yf_code 열만 골라서 여러 종목 데이터가 섞이지 않게 함
            if isinstance(df.columns, pd.MultiIndex) and len(df.columns) > 1:
                ticker_level = df.columns.get_level_values(1)
                mask = ticker_level == yf_code
                if mask.any():
                    df = df.loc[:, mask].copy()

            if df.empty:
                raise DataFetchError(f"Yahoo Finance에서 {stock_code} 데이터를 찾지 못함")

            return df

        except Exception as e:
            if isinstance(e, DataFetchError):
                raise
            raise DataFetchError(f"Yahoo Finance 데이터 받기 실패: {e}") from e

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        Yahoo Finance 데이터 표준화

        yfinance가 돌려주는 열 이름:
        Open, High, Low, Close, Volume(인덱스가 날짜)

        주의: 새 버전 yfinance는 MultiIndex 열 이름을 돌려줌, 예: ('Close', 'AMD')
        열 이름을 먼저 평평하게 만든 뒤 처리해야 함

        표준 열 이름으로 매핑해야 함:
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()

        # MultiIndex 열 이름 처리(새 버전 yfinance 형식)
        # 예: ('Close', 'AMD') -> 'Close'
        if isinstance(df.columns, pd.MultiIndex):
            logger.debug("MultiIndex 열 이름 발견, 평평하게 변환")
            # 첫 번째 단계 열 이름 사용(Price level: Close, High, Low, etc.)
            df.columns = df.columns.get_level_values(0)

        # 인덱스를 초기화해 날짜를 인덱스에서 열로 옮김
        df = df.reset_index()

        # 열 이름 매핑(yfinance는 첫 글자가 대문자)
        column_mapping = {
            'Date': 'date',
            'Datetime': 'date',
            'datetime': 'date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
        }

        df = df.rename(columns=column_mapping)
        if 'date' not in df.columns:
            index_col = df.columns[0] if len(df.columns) else None
            if index_col is not None:
                candidate = df[index_col]
                if pd.api.types.is_datetime64_any_dtype(candidate):
                    df = df.rename(columns={index_col: 'date'})
                elif not pd.api.types.is_numeric_dtype(candidate):
                    parsed_dates = pd.to_datetime(candidate, errors='coerce')
                    if parsed_dates.notna().any():
                        df = df.rename(columns={index_col: 'date'})
                        df['date'] = parsed_dates

        # 등락률 계산(yfinance가 직접 주지 않아서)
        if 'close' in df.columns:
            df['pct_chg'] = df['close'].pct_change() * 100
            df['pct_chg'] = df['pct_chg'].fillna(0).round(2)

        # 거래대금 계산(yfinance가 주지 않아 추정값 사용)
        # 거래대금 ≈ 거래량 * 평균 가격
        if 'volume' in df.columns and 'close' in df.columns:
            df['amount'] = df['volume'] * df['close']
        else:
            df['amount'] = 0

        # 종목 코드 열 추가
        df['code'] = stock_code

        # 필요한 열만 남김
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]

        return df

    def _fetch_yf_ticker_data(self, yf, yf_code: str, name: str, return_code: str) -> Optional[Dict[str, Any]]:
        """
        yfinance로 지수/종목 하나의 시세 데이터를 가져옴.

        Args:
            yf: yfinance 모듈 참조
            yf_code: yfinance가 쓰는 코드(예: '000001.SS', '^GSPC')
            name: 지수 표시 이름
            return_code: 결과 dict의 code 필드에 넣을 값(예: 'sh000001', 'SPX')

        Returns:
            시세 딕셔너리, 실패하면 None
        """
        ticker = yf.Ticker(yf_code)
        # 등락률 계산을 위해 최근 이틀 데이터 사용
        hist = ticker.history(period='2d')
        if hist.empty:
            return None
        today_row = hist.iloc[-1]
        prev_row = hist.iloc[-2] if len(hist) > 1 else today_row
        price = float(today_row['Close'])
        prev_close = float(prev_row['Close'])
        change = price - prev_close
        change_pct = (change / prev_close) * 100 if prev_close else 0
        high = float(today_row['High'])
        low = float(today_row['Low'])
        # 진폭 = (고가 - 저가) / 전일 종가 * 100
        amplitude = ((high - low) / prev_close * 100) if prev_close else 0
        return {
            'code': return_code,
            'name': name,
            'current': price,
            'change': change,
            'change_pct': change_pct,
            'open': float(today_row['Open']),
            'high': high,
            'low': low,
            'prev_close': prev_close,
            'volume': float(today_row['Volume']),
            'amount': 0.0,  # Yahoo Finance는 정확한 거래대금을 주지 않음
            'amplitude': amplitude,
        }

    def get_main_indices(self, region: str = "cn") -> Optional[List[Dict[str, Any]]]:
        """
        주요 지수 시세 가져오기(Yahoo Finance). A주, 미국, 홍콩, 일본, 한국, 대만 주식 지원.
        region=us면 _get_us_main_indices에 맡김.
        region=hk면 _get_hk_main_indices에 맡김.
        region=jp/kr/tw면 각 시장의 지수 메서드에 맡김.
        """
        import yfinance as yf

        if region == "us":
            return self._get_us_main_indices(yf)
        if region == "hk":
            return self._get_hk_main_indices(yf)
        if region == "jp":
            return self._get_jp_main_indices(yf)
        if region == "kr":
            return self._get_kr_main_indices(yf)
        if region == "tw":
            return self._get_tw_main_indices(yf)

        # A주 지수: akshare 코드 -> (yfinance 코드, 표시 이름)
        yf_mapping = {
            'sh000001': ('000001.SS', '上证指数'),
            'sz399001': ('399001.SZ', '深证成指'),
            'sz399006': ('399006.SZ', '创业板指'),
            'sh000688': ('000688.SS', '科创50'),
            'sh000016': ('000016.SS', '上证50'),
            'sh000300': ('000300.SS', '沪深300'),
        }

        results = []
        try:
            for ak_code, (yf_code, name) in yf_mapping.items():
                try:
                    item = self._fetch_yf_ticker_data(yf, yf_code, name, ak_code)
                    if item:
                        results.append(item)
                        logger.debug(f"[Yfinance] 지수 {name} 받기 성공")
                except Exception as e:
                    logger.warning(f"[Yfinance] 지수 {name} 받기 실패: {e}")

            if results:
                logger.info(f"[Yfinance] A주 지수 시세 {len(results)}개 받기 성공")
                return results

        except Exception as e:
            logger.error(f"[Yfinance] A주 지수 시세 받기 실패: {e}")

        return None

    def _get_us_main_indices(self, yf) -> Optional[List[Dict[str, Any]]]:
        """미국 주요 지수 시세 가져오기(SPX, IXIC, DJI, VIX), _fetch_yf_ticker_data 재사용"""
        # 시장 복기에 필요한 핵심 미국 지수
        us_indices = ['SPX', 'IXIC', 'DJI', 'VIX']
        results = []
        try:
            for code in us_indices:
                yf_symbol, name = get_us_index_yf_symbol(code)
                if not yf_symbol:
                    continue
                try:
                    item = self._fetch_yf_ticker_data(yf, yf_symbol, name, code)
                    if item:
                        results.append(item)
                        logger.debug(f"[Yfinance] 미국 지수 {name} 받기 성공")
                except Exception as e:
                    logger.warning(f"[Yfinance] 미국 지수 {name} 받기 실패: {e}")

            if results:
                logger.info(f"[Yfinance] 미국 지수 시세 {len(results)}개 받기 성공")
                return results

        except Exception as e:
            logger.error(f"[Yfinance] 미국 지수 시세 받기 실패: {e}")

        return None

    def _get_hk_main_indices(self, yf) -> Optional[List[Dict[str, Any]]]:
        """홍콩 주요 지수 시세 가져오기(HSI, HSTECH, HSCEI), _fetch_yf_ticker_data 재사용"""
        # Yahoo Finance 홍콩 지수 심볼 매핑:
        # - HSI -> ^HSI
        # - HSTECH -> HSTECH.HK(^HSTECH 아님)
        # - HSCEI -> ^HSCE(^HSCEI 아님)
        # 이 매핑은 오프라인 단위 테스트 tests/test_yfinance_hk_indices.py로 고정해, 온라인 의존 때문에 결과가 들쭉날쭉해지는 것을 막음.
        hk_indices = {
            'HSI': ('^HSI', '恒生指数'),
            'HSTECH': ('HSTECH.HK', '恒生科技指数'),
            'HSCEI': ('^HSCE', '国企指数'),
        }
        results = []
        try:
            for code, (yf_symbol, name) in hk_indices.items():
                try:
                    item = self._fetch_yf_ticker_data(yf, yf_symbol, name, code)
                    if item:
                        results.append(item)
                        logger.debug(f"[Yfinance] 홍콩 지수 {name} 받기 성공")
                except Exception as e:
                    logger.warning(f"[Yfinance] 홍콩 지수 {name} 받기 실패: {e}")

            if results:
                logger.info(f"[Yfinance] 홍콩 지수 시세 {len(results)}개 받기 성공")
                return results

        except Exception as e:
            logger.error(f"[Yfinance] 홍콩 지수 시세 받기 실패: {e}")

        return None

    def _get_jp_main_indices(self, yf) -> Optional[List[Dict[str, Any]]]:
        """일본 주요 지수 시세 가져오기(닛케이225, TOPIX), _fetch_yf_ticker_data 재사용."""
        jp_indices = {
            'N225': ('^N225', '日经225'),
            'TOPX': ('^TOPX', '东证指数'),
        }
        results = []
        try:
            for code, (yf_symbol, name) in jp_indices.items():
                try:
                    item = self._fetch_yf_ticker_data(yf, yf_symbol, name, code)
                    if item:
                        results.append(item)
                        logger.debug(f"[Yfinance] 일본 지수 {name} 받기 성공")
                except Exception as e:
                    logger.warning(f"[Yfinance] 일본 지수 {name} 받기 실패: {e}")
            if results:
                logger.info(f"[Yfinance] 일본 지수 시세 {len(results)}개 받기 성공")
                return results
        except Exception as e:
            logger.error(f"[Yfinance] 일본 지수 시세 받기 실패: {e}")
        return None

    def _get_kr_main_indices(self, yf) -> Optional[List[Dict[str, Any]]]:
        """한국 주요 지수 시세 가져오기(KOSPI, KOSDAQ), _fetch_yf_ticker_data 재사용."""
        kr_indices = {
            'KS11': ('^KS11', 'KOSPI'),
            'KQ11': ('^KQ11', 'KOSDAQ'),
        }
        results = []
        try:
            for code, (yf_symbol, name) in kr_indices.items():
                try:
                    item = self._fetch_yf_ticker_data(yf, yf_symbol, name, code)
                    if item:
                        results.append(item)
                        logger.debug(f"[Yfinance] 한국 지수 {name} 받기 성공")
                except Exception as e:
                    logger.warning(f"[Yfinance] 한국 지수 {name} 받기 실패: {e}")
            if results:
                logger.info(f"[Yfinance] 한국 지수 시세 {len(results)}개 받기 성공")
                return results
        except Exception as e:
            logger.error(f"[Yfinance] 한국 지수 시세 받기 실패: {e}")
        return None

    def _get_tw_main_indices(self, yf) -> Optional[List[Dict[str, Any]]]:
        """대만 주요 지수 시세 가져오기(가권지수 ^TWII, 장외 지수 ^TWOII), _fetch_yf_ticker_data 재사용."""
        tw_indices = {
            'TWII': ('^TWII', '台湾加权指数'),
            'TWOII': ('^TWOII', '台湾柜买指数'),
        }
        results = []
        try:
            for code, (yf_symbol, name) in tw_indices.items():
                try:
                    item = self._fetch_yf_ticker_data(yf, yf_symbol, name, code)
                    if item:
                        results.append(item)
                        logger.debug(f"[Yfinance] 대만 지수 {name} 받기 성공")
                except Exception as e:
                    logger.warning(f"[Yfinance] 대만 지수 {name} 받기 실패: {e}")
            if results:
                logger.info(f"[Yfinance] 대만 지수 시세 {len(results)}개 받기 성공")
                return results
        except Exception as e:
            logger.error(f"[Yfinance] 대만 지수 시세 받기 실패: {e}")
        return None

    def _is_us_stock(self, stock_code: str) -> bool:
        """
        미국 개별 주식 코드인지 판단(미국 지수는 제외).

        us_index_mapping 모듈의 is_us_stock_code()에 맡김.
        """
        return is_us_stock_code(stock_code)

    def _get_us_stock_quote_from_stooq(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        Stooq로 미국 주식 실시간 시세를 API 키 없이 대체 제공.

        Stooq는 최근 거래일 시세라 분 단위 실시간 API보다 덜 정확하지만, Yahoo / yfinance가
        요청 제한에 걸렸을 때 Web UI에 쓸 수 있는 가격은 줌. 전일 종가를 얻으면 등락률 같은 파생 지표도 함께 줌.
        """
        symbol = stock_code.strip().upper()
        stooq_symbol = f"{symbol.lower()}.us"
        url = f"https://stooq.com/q/l/?s={stooq_symbol}"
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; DSA/1.0; +https://github.com/ZhuLinsen/daily_stock_analysis)",
                "Accept": "text/plain,text/csv,*/*",
            },
        )

        try:
            with urlopen(request, timeout=15) as response:
                payload = response.read().decode("utf-8", "ignore").strip()
        except (HTTPError, URLError, TimeoutError) as exc:
            logger.warning(f"[Stooq] 미국 주식 {symbol} 실시간 시세 받기 실패: {exc}")
            return None

        if not payload or payload.upper().startswith("NO DATA"):
            logger.warning(f"[Stooq] {symbol} 시세 데이터를 받을 수 없음")
            return None

        def _fetch_prev_close() -> Optional[float]:
            history_url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
            history_request = Request(
                history_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; DSA/1.0; +https://github.com/ZhuLinsen/daily_stock_analysis)",
                    "Accept": "text/plain,text/csv,*/*",
                },
            )
            try:
                with urlopen(history_request, timeout=15) as response:
                    history_payload = response.read().decode("utf-8", "ignore").strip()
            except (HTTPError, URLError, TimeoutError) as exc:
                logger.debug(f"[Stooq] 미국 주식 {symbol} 일봉 이력 받기 실패: {exc}")
                return None

            if not history_payload or history_payload.upper().startswith("NO DATA"):
                return None

            try:
                reader = csv.reader(StringIO(history_payload))
                header = next(reader, None)
                if not header:
                    return None

                header_tokens = [cell.strip().lower() for cell in header]
                has_header = "close" in header_tokens and "date" in header_tokens
                if not has_header:
                    return None

                date_index = header_tokens.index("date")
                close_index = header_tokens.index("close")

                daily_rows: list[tuple[datetime, float]] = []
                for row in reader:
                    if not row:
                        continue
                    date_text = row[date_index].strip() if len(row) > date_index else ""
                    close_text = row[close_index].strip() if len(row) > close_index else ""
                    if not date_text or not close_text:
                        continue
                    try:
                        dt = datetime.strptime(date_text, "%Y-%m-%d")
                        close_val = float(close_text)
                    except Exception:
                        continue
                    daily_rows.append((dt, close_val))

                if len(daily_rows) < 2:
                    return None

                daily_rows.sort(key=lambda item: item[0])
                return daily_rows[-2][1]
            except Exception:
                return None

        try:
            reader = csv.reader(StringIO(payload))
            first_row = next(reader, None)
            if first_row is None:
                raise ValueError(f"unexpected Stooq payload: {payload}")

            normalized_first_row = [cell.strip() for cell in first_row]
            header_tokens = {cell.lower() for cell in normalized_first_row if cell}
            has_header = 'open' in header_tokens and 'close' in header_tokens
            row = next(reader, None) if has_header else first_row
            if row is None:
                raise ValueError(f"unexpected Stooq payload: {payload}")

            normalized_row = [cell.strip() for cell in row]
            while normalized_row and normalized_row[-1] == '':
                normalized_row.pop()

            if len(normalized_row) >= 8:
                open_index, high_index, low_index, price_index, volume_index = 3, 4, 5, 6, 7
            elif len(normalized_row) >= 7:
                open_index, high_index, low_index, price_index, volume_index = 2, 3, 4, 5, 6
            else:
                raise ValueError(f"unexpected Stooq payload: {payload}")

            open_price = float(normalized_row[open_index])
            high = float(normalized_row[high_index])
            low = float(normalized_row[low_index])
            price = float(normalized_row[price_index])
            volume = int(float(normalized_row[volume_index]))

            prev_close = _fetch_prev_close()
            change_amount = None
            change_pct = None
            amplitude = None
            if prev_close is not None and prev_close > 0:
                change_amount = price - prev_close
                change_pct = (change_amount / prev_close) * 100
                amplitude = ((high - low) / prev_close) * 100

            quote = UnifiedRealtimeQuote(
                code=symbol,
                name=STOCK_NAME_MAP.get(symbol, ''),
                source=RealtimeSource.STOOQ,
                price=price,
                change_pct=round(change_pct, 2) if change_pct is not None else None,
                change_amount=round(change_amount, 4) if change_amount is not None else None,
                volume=volume,
                amount=None,
                volume_ratio=None,
                turnover_rate=None,
                amplitude=round(amplitude, 2) if amplitude is not None else None,
                open_price=open_price,
                high=high,
                low=low,
                pre_close=prev_close,
                pe_ratio=None,
                pb_ratio=None,
                total_mv=None,
                circ_mv=None,
            )
            logger.info(f"[Stooq] 미국 주식 {symbol} 대체 시세 받기 성공: 가격={price}")
            return quote
        except Exception as exc:
            logger.warning(f"[Stooq] 미국 주식 {symbol} 시세 해석 실패: {exc}")
            return None

    def _get_us_index_realtime_quote(
        self,
        user_code: str,
        yf_symbol: str,
        index_name: str,
    ) -> Optional[UnifiedRealtimeQuote]:
        """
        Get realtime quote for US index (e.g. SPX -> ^GSPC).

        Args:
            user_code: User input code (e.g. SPX)
            yf_symbol: Yahoo Finance symbol (e.g. ^GSPC)
            index_name: Chinese name for the index

        Returns:
            UnifiedRealtimeQuote or None
        """
        import yfinance as yf

        try:
            logger.debug(f"[Yfinance] 미국 지수 {user_code} ({yf_symbol}) 실시간 시세 받는 중")
            ticker = yf.Ticker(yf_symbol)

            try:
                info = ticker.fast_info
                if info is None:
                    raise ValueError("fast_info is None")
                price = getattr(info, 'lastPrice', None) or getattr(info, 'last_price', None)
                prev_close = getattr(info, 'previousClose', None) or getattr(info, 'previous_close', None)
                open_price = getattr(info, 'open', None)
                high = getattr(info, 'dayHigh', None) or getattr(info, 'day_high', None)
                low = getattr(info, 'dayLow', None) or getattr(info, 'day_low', None)
                volume = getattr(info, 'lastVolume', None) or getattr(info, 'last_volume', None)
            except Exception:
                logger.debug("[Yfinance] fast_info 실패, history 방식 시도")
                hist = ticker.history(period='2d')
                if hist.empty:
                    logger.warning(f"[Yfinance] {yf_symbol} 데이터를 받을 수 없음")
                    return None
                today = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else today
                price = float(today['Close'])
                prev_close = float(prev['Close'])
                open_price = float(today['Open'])
                high = float(today['High'])
                low = float(today['Low'])
                volume = int(today['Volume'])

            change_amount = None
            change_pct = None
            if price is not None and prev_close is not None and prev_close > 0:
                change_amount = price - prev_close
                change_pct = (change_amount / prev_close) * 100

            amplitude = None
            if high is not None and low is not None and prev_close is not None and prev_close > 0:
                amplitude = ((high - low) / prev_close) * 100

            try:
                ticker_info = ticker.info or {}
            except Exception:
                ticker_info = {}
            missing_fields = [
                field
                for field, value in {
                    "price": price,
                    "prev_close": prev_close,
                    "volume": volume,
                    "amount": None,
                    "pe_ratio": None,
                    "pb_ratio": None,
                }.items()
                if value is None
            ]

            quote = UnifiedRealtimeQuote(
                code=user_code,
                name=index_name or user_code,
                source=RealtimeSource.FALLBACK,
                market="us",
                currency=str(ticker_info.get("currency") or "").upper() or None,
                data_quality="partial" if missing_fields else "ok",
                missing_fields=missing_fields or None,
                price=price,
                change_pct=round(change_pct, 2) if change_pct is not None else None,
                change_amount=round(change_amount, 4) if change_amount is not None else None,
                volume=volume,
                amount=None,
                volume_ratio=None,
                turnover_rate=None,
                amplitude=round(amplitude, 2) if amplitude is not None else None,
                open_price=open_price,
                high=high,
                low=low,
                pre_close=prev_close,
                pe_ratio=None,
                pb_ratio=None,
                total_mv=None,
                circ_mv=None,
            )
            logger.info(f"[Yfinance] 미국 지수 {user_code} 실시간 시세 받기 성공: 가격={price}")
            return quote
        except Exception as e:
            logger.warning(f"[Yfinance] 미국 지수 {user_code} 실시간 시세 받기 실패: {e}")
            return None

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        미국/홍콩/일본/한국/대만 주식 또는 미국 지수의 실시간 시세 가져오기

        미국 주식(AAPL, TSLA)과 미국 지수(SPX, DJI 등) 지원.
        데이터 출처: yfinance Ticker.info

        Args:
            stock_code: 미국 주식 코드나 지수 코드, 예: 'AMD', 'AAPL', 'SPX', 'DJI'

        Returns:
            UnifiedRealtimeQuote 객체, 실패하면 None
        """
        import yfinance as yf

        # 미국 지수: 매핑 사용(SPX -> ^GSPC)
        yf_symbol, index_name = get_us_index_yf_symbol(stock_code)
        if yf_symbol:
            return self._get_us_index_realtime_quote(
                user_code=stock_code.strip().upper(),
                yf_symbol=yf_symbol,
                index_name=index_name,
            )

        # 미국, 홍콩, 또는 JP/KR/TW 접미사 종목만 처리
        if not (
            self._is_us_stock(stock_code)
            or _is_hk_market(stock_code)
            or self._is_jp_kr_suffix_stock(stock_code)
            or self._is_tw_suffix_stock(stock_code)
        ):
            logger.debug(f"[Yfinance] {stock_code}은(는) 지원하는 미국/홍콩/일본/한국/대만 코드가 아니라 건너뜀")
            return None

        try:
            symbol = self._convert_stock_code(stock_code)
            is_us_symbol = self._is_us_stock(symbol)
            suffix_market = get_suffix_market(symbol)
            logger.debug(f"[Yfinance] {symbol} 실시간 시세 받는 중")

            ticker = yf.Ticker(symbol)

            # fast_info 먼저 시도(빠르지만 필드가 적음)
            try:
                info = ticker.fast_info
                if info is None:
                    raise ValueError("fast_info is None")

                price = getattr(info, 'lastPrice', None) or getattr(info, 'last_price', None)
                prev_close = getattr(info, 'previousClose', None) or getattr(info, 'previous_close', None)
                open_price = getattr(info, 'open', None)
                high = getattr(info, 'dayHigh', None) or getattr(info, 'day_high', None)
                low = getattr(info, 'dayLow', None) or getattr(info, 'day_low', None)
                volume = getattr(info, 'lastVolume', None) or getattr(info, 'last_volume', None)
                market_cap = getattr(info, 'marketCap', None) or getattr(info, 'market_cap', None)

            except Exception:
                # history 방식으로 최신 데이터 가져오기
                logger.debug("[Yfinance] fast_info 실패, history 방식 시도")
                hist = ticker.history(period='2d')
                if hist.empty:
                    if is_us_symbol:
                        logger.warning(f"[Yfinance] {symbol} 데이터를 받을 수 없어 Stooq로 대체 시도")
                        return self._get_us_stock_quote_from_stooq(symbol)
                    logger.warning(f"[Yfinance] {symbol} 데이터를 받을 수 없음")
                    return None

                today = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else today

                price = float(today['Close'])
                prev_close = float(prev['Close'])
                open_price = float(today['Open'])
                high = float(today['High'])
                low = float(today['Low'])
                volume = int(today['Volume'])
                market_cap = None

            # 등락률 계산
            change_amount = None
            change_pct = None
            if price is not None and prev_close is not None and prev_close > 0:
                change_amount = price - prev_close
                change_pct = (change_amount / prev_close) * 100

            # 진폭 계산
            amplitude = None
            if high is not None and low is not None and prev_close is not None and prev_close > 0:
                amplitude = ((high - low) / prev_close) * 100

            # 종목 이름과 provider 메타데이터 가져오기
            try:
                ticker_info = ticker.info or {}
            except Exception:
                ticker_info = {}
            try:
                info_name = ticker_info.get('shortName', '') or ticker_info.get('longName', '') or ''
                name = info_name if is_meaningful_stock_name(info_name, symbol) else STOCK_NAME_MAP.get(symbol, '')
            except Exception:
                name = STOCK_NAME_MAP.get(symbol, '')

            # 위에서 받은 ticker_info 재사용, 추가 요청 없음
            pe_ratio = _safe_float(ticker_info.get('trailingPE'))
            pb_ratio = _safe_float(ticker_info.get('priceToBook'))

            missing_fields = [
                field
                for field, value in {
                    "price": price,
                    "prev_close": prev_close,
                    "volume": volume,
                    "amount": None,
                    "pe_ratio": pe_ratio,
                    "pb_ratio": pb_ratio,
                }.items()
                if value is None
            ]
            quote = UnifiedRealtimeQuote(
                code=symbol,
                name=name,
                source=RealtimeSource.FALLBACK,
                market=suffix_market or ("hk" if _is_hk_market(stock_code) else "us" if is_us_symbol else None),
                currency=str(ticker_info.get("currency") or "").upper() or None,
                data_quality="partial" if missing_fields else "ok",
                missing_fields=missing_fields or None,
                price=price,
                change_pct=round(change_pct, 2) if change_pct is not None else None,
                change_amount=round(change_amount, 4) if change_amount is not None else None,
                volume=volume,
                amount=None,  # yfinance는 거래대금을 직접 주지 않음
                volume_ratio=None,
                turnover_rate=None,
                amplitude=round(amplitude, 2) if amplitude is not None else None,
                open_price=open_price,
                high=high,
                low=low,
                pre_close=prev_close,
                pe_ratio=pe_ratio,
                pb_ratio=pb_ratio,
                total_mv=market_cap,
                circ_mv=None,
            )

            logger.info(f"[Yfinance] {symbol} 실시간 시세 받기 성공: 가격={price}")
            return quote

        except Exception as e:
            if self._is_us_stock(stock_code):
                logger.warning(f"[Yfinance] 미국 주식 {stock_code} 실시간 시세 받기 실패: {e}, Stooq로 대체 시도")
                return self._get_us_stock_quote_from_stooq(stock_code)
            logger.warning(f"[Yfinance] {stock_code} 실시간 시세 받기 실패: {e}")
            return None


if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.DEBUG)

    fetcher = YfinanceFetcher()

    try:
        df = fetcher.get_daily_data('600519')  # 마오타이
        print(f"받기 성공, 총 {len(df)}건")
        print(df.tail())
    except Exception as e:
        print(f"받기 실패: {e}")
