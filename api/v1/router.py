# -*- coding: utf-8 -*-
"""
===================================
API v1 라우트 모음
===================================

역할:
1. v1 버전 endpoint 라우트를 모두 모음
2. /api/v1 접두사를 한곳에서 붙임
"""

from fastapi import APIRouter

from api.v1.endpoints import (
    agent,
    alerts,
    screening,
    analysis,
    auth,
    backtest,
    data,
    decision_signals,
    health,
    history,
    intelligence,
    portfolio,
    stocks,
    system_config,
    usage,
)

# v1 버전 메인 라우터 생성.
# /api/v1 접두사는 api.app 에서 붙임. 최신 FastAPI 가 하위 라우트 "" 를 empty path 로 잘못 보는 것을 막기 위함.
router = APIRouter()

router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Auth"]
)

router.include_router(
    agent.router,
    prefix="/agent",
    tags=["Agent"]
)

router.include_router(
    analysis.router,
    prefix="/analysis",
    tags=["Analysis"]
)

router.include_router(
    history.router,
    prefix="/history",
    tags=["History"]
)

router.include_router(
    stocks.router,
    prefix="/stocks",
    tags=["Stocks"]
)

router.include_router(
    backtest.router,
    prefix="/backtest",
    tags=["Backtest"]
)

router.include_router(
    system_config.router,
    prefix="/system",
    tags=["SystemConfig"]
)

router.include_router(
    usage.router,
    prefix="/usage",
    tags=["Usage"]
)

router.include_router(
    portfolio.router,
    prefix="/portfolio",
    tags=["Portfolio"]
)

router.include_router(
    alerts.router,
    prefix="/alerts",
    tags=["Alerts"]
)

router.include_router(
    decision_signals.router,
    prefix="/decision-signals",
    tags=["DecisionSignals"]
)

router.include_router(
    screening.router,
    prefix="/screening",
    tags=["Screening"]
)

router.include_router(
    data.router,
    prefix="/data",
    tags=["Data"]
)

router.include_router(
    intelligence.router,
    prefix="/intelligence",
    tags=["Intelligence"]
)

router.include_router(
    health.router,
    tags=["Health"]
)
