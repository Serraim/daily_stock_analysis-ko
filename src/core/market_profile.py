# -*- coding: utf-8 -*-
"""
시장 전체 복기용 시장 지역 설정

시장 지역별 지수, 뉴스 검색어, Prompt 힌트 등 메타데이터를 정의해
MarketAnalyzer 가 region 에 따라 A주/홍콩/미국/일본·한국 복기 동작을 바꿀 수 있게 한다.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class MarketProfile:
    """시장 전체 복기용 시장 지역 설정"""

    region: str  # "cn" | "hk" | "us" | "jp" | "kr"
    # 전체 흐름 판단용 지수 코드, cn 은 상하이종합 000001, us 는 S&P SPX
    mood_index_code: str
    # 뉴스 검색 키워드
    news_queries: List[str]
    # 지수 코멘트용 Prompt 힌트
    prompt_index_hint: str
    # 시장 개요에 상승·하락 종목 수, 상한가·하한가 포함 여부 (A주는 있음, 미국은 없음)
    has_market_stats: bool
    # 시장 개요에 섹터 등락 포함 여부 (A주는 있음, 미국은 아직 없음)
    has_sector_rankings: bool


CN_PROFILE = MarketProfile(
    region="cn",
    mood_index_code="000001",
    news_queries=[
        "A股 大盘 复盘",
        "股市 行情 分析",
        "A股 市场 热点 板块",
    ],
    prompt_index_hint="分析上证、深证、创业板等各指数走势特点",
    has_market_stats=True,
    has_sector_rankings=True,
)

US_PROFILE = MarketProfile(
    region="us",
    mood_index_code="SPX",
    news_queries=[
        "美股 大盘",
        "US stock market",
        "S&P 500 NASDAQ",
    ],
    prompt_index_hint="分析标普500、纳斯达克、道指等各指数走势特点",
    has_market_stats=False,
    has_sector_rankings=False,
)

HK_PROFILE = MarketProfile(
    region="hk",
    mood_index_code="HSI",
    news_queries=[
        "港股 大盘 复盘",
        "Hong Kong stock market",
        "恒生指数 行情",
    ],
    prompt_index_hint="分析恒生指数、恒生科技指数、国企指数等各指数走势特点",
    has_market_stats=False,
    has_sector_rankings=False,
)

JP_PROFILE = MarketProfile(
    region="jp",
    mood_index_code="N225",
    news_queries=[
        "日本股市 日经225",
        "Japan stock market Nikkei TOPIX",
        "日经225 东证指数 行情",
    ],
    prompt_index_hint="分析日经225、东证指数等日本主要指数走势特点",
    has_market_stats=False,
    has_sector_rankings=False,
)

KR_PROFILE = MarketProfile(
    region="kr",
    mood_index_code="KS11",
    news_queries=[
        "韩国股市 KOSPI",
        "Korea stock market KOSPI KOSDAQ",
        "KOSPI KOSDAQ 行情",
    ],
    prompt_index_hint="分析 KOSPI、KOSDAQ 等韩国主要指数走势特点",
    has_market_stats=False,
    has_sector_rankings=False,
)


def get_profile(region: str) -> MarketProfile:
    """region 에 맞는 MarketProfile 반환"""
    if region == "us":
        return US_PROFILE
    if region == "hk":
        return HK_PROFILE
    if region == "jp":
        return JP_PROFILE
    if region == "kr":
        return KR_PROFILE
    return CN_PROFILE
