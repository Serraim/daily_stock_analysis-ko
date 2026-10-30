# -*- coding: utf-8 -*-
"""
===================================
API v1 모듈 초기화
===================================

역할:
1. v1 API 라우터를 필요할 때 내보냄. schema 를 import 할 때 endpoint 전체가 줄줄이 import 되지 않게 함
"""

from typing import Any

__all__ = ["api_v1_router"]


def __getattr__(name: str) -> Any:
    if name != "api_v1_router":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from api.v1.router import router

    return router
