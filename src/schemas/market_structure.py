# -*- coding: utf-8 -*-
"""Versioned market-structure context shared by reports, Agent and API."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


MARKET_THEME_SCHEMA_VERSION = "market-theme-v1"
STOCK_MARKET_POSITION_SCHEMA_VERSION = "stock-market-position-v1"
MARKET_STRUCTURE_SCHEMA_VERSION = "market-structure-v1"

MarketStructureStatus = Literal["ok", "partial", "unknown", "not_supported"]
ThemeRankSource = Literal["industry", "concept", "mixed", "unknown"]
ThemePhase = Literal["warming", "accelerating", "cooling", "unknown"]
StockRole = Literal["leader", "follower", "edge", "unknown"]


class MarketStructureSource(BaseModel):
    provider: str = Field(..., description="데이터 소스 식별자. 스냅샷 메타데이터용이며 런타임 provider/model 라우팅에는 쓰지 않음")
    dataset: str = Field(..., description="데이터셋 식별자. 과거 추적용 스냅샷에만 사용")
    status: str = Field("ok", description="소스 가용성 스냅샷")
    message: Optional[str] = Field(None, description="소스 안내 메시지. 표시/문제 해결용")


class MarketStructureDataQuality(BaseModel):
    status: MarketStructureStatus = Field("unknown", description="데이터 품질 스냅샷 상태(표시용 의미)")
    missing_fields: List[str] = Field(default_factory=list)
    sources: List[MarketStructureSource] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class RankedThemeItem(BaseModel):
    name: str
    change_pct: Optional[float] = None
    rank: Optional[int] = None
    source: ThemeRankSource = "unknown"
    code: Optional[str] = None
    updated_at: Optional[str] = None


class MarketThemeItem(RankedThemeItem):
    phase: ThemePhase = "unknown"
    strength_score: Optional[int] = None
    reason: Optional[str] = None


class ThemeBreadth(BaseModel):
    active_count: int = 0
    leading_industry_count: int = 0
    leading_concept_count: int = 0
    lagging_count: int = 0


class MarketThemeContext(BaseModel):
    schema_version: str = MARKET_THEME_SCHEMA_VERSION
    status: MarketStructureStatus = "unknown"
    market: str = "cn"
    trade_date: Optional[str] = None
    active_themes: List[MarketThemeItem] = Field(default_factory=list)
    leading_industries: List[RankedThemeItem] = Field(default_factory=list)
    leading_concepts: List[RankedThemeItem] = Field(default_factory=list)
    lagging_themes: List[RankedThemeItem] = Field(default_factory=list)
    hotspot_constituents: List[Any] = Field(default_factory=list)
    leader_stocks: List[Any] = Field(default_factory=list)
    theme_breadth: ThemeBreadth = Field(default_factory=ThemeBreadth)
    data_quality: MarketStructureDataQuality = Field(default_factory=MarketStructureDataQuality)


class StockBoardPosition(BaseModel):
    name: str
    type: Optional[str] = None
    code: Optional[str] = None
    rank: Optional[int] = None
    change_pct: Optional[float] = None
    source: ThemeRankSource = "unknown"


class PrimaryTheme(BaseModel):
    name: str
    source: ThemeRankSource = "unknown"
    phase: ThemePhase = "unknown"
    rank: Optional[int] = None
    change_pct: Optional[float] = None


class MarketStructureRiskTag(BaseModel):
    code: str
    message: str


class StockMarketPosition(BaseModel):
    schema_version: str = STOCK_MARKET_POSITION_SCHEMA_VERSION
    status: MarketStructureStatus = "unknown"
    stock_code: str
    stock_name: Optional[str] = None
    market: str = "cn"
    primary_theme: Optional[PrimaryTheme] = None
    related_boards: List[StockBoardPosition] = Field(default_factory=list)
    stock_role: StockRole = "unknown"
    theme_phase: ThemePhase = "unknown"
    risk_tags: List[MarketStructureRiskTag] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)


class MarketStructureContext(BaseModel):
    schema_version: str = MARKET_STRUCTURE_SCHEMA_VERSION
    status: MarketStructureStatus = "unknown"
    market: str = "cn"
    trade_date: Optional[str] = None
    market_theme_context: MarketThemeContext
    stock_market_position: StockMarketPosition


def dump_market_structure_model(model: BaseModel) -> Dict[str, Any]:
    """Return a low-sensitive dict using stable snake_case keys."""
    return model.model_dump(exclude_none=True)
