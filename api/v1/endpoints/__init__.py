# -*- coding: utf-8 -*-
"""
===================================
API v1 Endpoints 모듈 초기화
===================================

역할:
1. endpoint 라우트 모듈 전부 선언
"""

from api.v1.endpoints import (
    health,
    analysis,
    history,
    stocks,
    backtest,
    data,
    system_config,
    auth,
    agent,
    usage,
    portfolio,
    alerts,
    decision_signals,
    screening,
)
__all__ = [
    "health",
    "analysis",
    "history",
    "stocks",
    "backtest",
    "data",
    "system_config",
    "auth",
    "agent",
    "usage",
    "portfolio",
    "alerts",
    "decision_signals",
    "screening",
]
