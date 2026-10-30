# -*- coding: utf-8 -*-
"""
===================================
데이터 소스 전략 계층 - 패키지 초기화
===================================

이 패키지는 전략 패턴으로 여러 데이터 소스를 관리하며, 다음을 제공합니다:
1. 통일된 데이터 조회 인터페이스
2. 장애 시 자동 전환
3. 차단 방지용 요청 속도 제어

데이터 소스 우선순위 (동적으로 조정):
[TUSHARE_TOKEN을 설정한 경우]
1. TushareFetcher (Priority 0) - 🔥 최우선 (동적으로 상향)
2. EfinanceFetcher (Priority 0) - 같은 우선순위
3. AkshareFetcher (Priority 1) - akshare 라이브러리
4. PytdxFetcher (Priority 2) - pytdx 라이브러리 (통다신)
5. BaostockFetcher (Priority 3) - baostock 라이브러리
6. YfinanceFetcher (Priority 4) - yfinance 라이브러리
7. TencentFetcher (Priority 5) - 텐센트 직접 연결 일봉, 최후의 대비책

[TUSHARE_TOKEN을 설정하지 않은 경우]
1. EfinanceFetcher (Priority 0) - 최우선, efinance 라이브러리
2. AkshareFetcher (Priority 1) - akshare 라이브러리
3. PytdxFetcher (Priority 2) - pytdx 라이브러리 (통다신)
4. TushareFetcher (Priority 2) - tushare 라이브러리 (사용 불가)
5. BaostockFetcher (Priority 3) - baostock 라이브러리
6. YfinanceFetcher (Priority 4) - yfinance 라이브러리
7. TencentFetcher (Priority 5) - 텐센트 직접 연결 일봉, 최후의 대비책
8. LongbridgeFetcher (Priority 5) - 롱브리지 OpenAPI (미국·홍콩 주식 대비책, Tencent와 시장이 겹치지 않음)

참고: 우선순위 숫자가 작을수록 먼저 쓰며, 같은 우선순위는 초기화 순서대로 씁니다
"""

from .base import BaseFetcher, DataFetcherManager
from .efinance_fetcher import EfinanceFetcher
from .tencent_fetcher import TencentFetcher
from .akshare_fetcher import AkshareFetcher, is_hk_stock_code
from .tushare_fetcher import TushareFetcher
from .pytdx_fetcher import PytdxFetcher
from .baostock_fetcher import BaostockFetcher
from .yfinance_fetcher import YfinanceFetcher
from .longbridge_fetcher import LongbridgeFetcher
from .finnhub_fetcher import FinnhubFetcher
from .alphavantage_fetcher import AlphaVantageFetcher
from .us_index_mapping import is_us_index_code, is_us_stock_code, get_us_index_yf_symbol, US_INDEX_MAPPING

__all__ = [
    'BaseFetcher',
    'DataFetcherManager',
    'EfinanceFetcher',
    'TencentFetcher',
    'AkshareFetcher',
    'TushareFetcher',
    'PytdxFetcher',
    'BaostockFetcher',
    'YfinanceFetcher',
    'LongbridgeFetcher',
    'FinnhubFetcher',
    'AlphaVantageFetcher',
    'is_us_index_code',
    'is_us_stock_code',
    'is_hk_stock_code',
    'get_us_index_yf_symbol',
    'US_INDEX_MAPPING',
]
