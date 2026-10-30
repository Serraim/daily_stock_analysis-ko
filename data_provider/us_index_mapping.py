# -*- coding: utf-8 -*-
"""
===================================
미국 지수·종목 코드 도구
===================================

제공 기능:
1. 미국 지수 코드 매핑 (예: SPX -> ^GSPC)
2. 미국 종목 코드 판별 (AAPL, TSLA 등)

Yahoo Finance에서 미국 지수는 종목 코드와 달리 ^ 접두어를 붙여야 합니다.
"""

import re

# 미국 종목 코드 정규식: 대문자 1~5자, .X 접미어는 선택 (예: BRK.B)
_US_STOCK_PATTERN = re.compile(r'^[A-Z]{1,5}(\.[A-Z])?$')


# 사용자 입력 -> (Yahoo Finance 심볼, 중국어 이름)
US_INDEX_MAPPING = {
    # S&P 500
    'SPX': ('^GSPC', '标普500指数'),
    '^GSPC': ('^GSPC', '标普500指数'),
    'GSPC': ('^GSPC', '标普500指数'),
    # 다우존스 산업평균지수
    'DJI': ('^DJI', '道琼斯工业指数'),
    '^DJI': ('^DJI', '道琼斯工业指数'),
    'DJIA': ('^DJI', '道琼斯工业指数'),
    # 나스닥 종합지수
    'IXIC': ('^IXIC', '纳斯达克综合指数'),
    '^IXIC': ('^IXIC', '纳斯达克综合指数'),
    'NASDAQ': ('^IXIC', '纳斯达克综合指数'),
    # 나스닥 100
    'NDX': ('^NDX', '纳斯达克100指数'),
    '^NDX': ('^NDX', '纳斯达克100指数'),
    # VIX 변동성 지수
    'VIX': ('^VIX', 'VIX恐慌指数'),
    '^VIX': ('^VIX', 'VIX恐慌指数'),
    # 러셀 2000
    'RUT': ('^RUT', '罗素2000指数'),
    '^RUT': ('^RUT', '罗素2000指数'),
}


def is_us_index_code(code: str) -> bool:
    """
    코드가 미국 지수 심볼인지 판별합니다.

    Args:
        code: 종목/지수 코드, 예: 'SPX', 'DJI'

    Returns:
        알려진 미국 지수 심볼이면 True, 아니면 False

    Examples:
        >>> is_us_index_code('SPX')
        True
        >>> is_us_index_code('AAPL')
        False
    """
    return (code or '').strip().upper() in US_INDEX_MAPPING


def is_us_stock_code(code: str) -> bool:
    """
    코드가 미국 종목 심볼인지 판별합니다 (미국 지수는 제외).

    미국 종목 코드는 대문자 1~5자이며, BRK.B처럼 .X 접미어가 붙을 수 있습니다.
    미국 지수(SPX, DJI 등)는 명시적으로 제외합니다.

    Args:
        code: 종목 코드, 예: 'AAPL', 'TSLA', 'BRK.B'

    Returns:
        미국 종목 심볼이면 True, 아니면 False

    Examples:
        >>> is_us_stock_code('AAPL')
        True
        >>> is_us_stock_code('TSLA')
        True
        >>> is_us_stock_code('BRK.B')
        True
        >>> is_us_stock_code('SPX')
        False
        >>> is_us_stock_code('600519')
        False
    """
    normalized = (code or '').strip().upper()
    # 미국 지수는 종목이 아님
    if normalized in US_INDEX_MAPPING:
        return False
    return bool(_US_STOCK_PATTERN.match(normalized))


def get_us_index_yf_symbol(code: str) -> tuple:
    """
    미국 지수의 Yahoo Finance 심볼과 중국어 이름을 가져옵니다.

    Args:
        code: 사용자 입력, 예: 'SPX', '^GSPC', 'DJI'

    Returns:
        (yf_symbol, chinese_name) 튜플. 찾지 못하면 (None, None)을 반환합니다.

    Examples:
        >>> get_us_index_yf_symbol('SPX')
        ('^GSPC', '标普500指数')
        >>> get_us_index_yf_symbol('AAPL')
        (None, None)
    """
    normalized = (code or '').strip().upper()
    return US_INDEX_MAPPING.get(normalized, (None, None))
