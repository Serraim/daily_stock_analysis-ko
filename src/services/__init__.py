# -*- coding: utf-8 -*-
"""
===================================
서비스 계층 모듈 초기화
===================================

역할:
1. 내보낼 서비스 클래스 선언(지연 import로 시작 시 LLM 같은 무거운 의존성을 불러오지 않음)

사용법:
    하위 모듈에서 직접 import, 예:
    from src.services.history_service import HistoryService
"""


def __getattr__(name: str):
    """지연 import: src.services.X로 접근할 때만 해당 하위 모듈을 불러온다."""
    _lazy_map = {
        "AnalysisService": "src.services.analysis_service",
        "BacktestService": "src.services.backtest_service",
        "HistoryService": "src.services.history_service",
        "StockService": "src.services.stock_service",
        "TaskService": "src.services.task_service",
        "get_task_service": "src.services.task_service",
    }
    if name in _lazy_map:
        import importlib
        module = importlib.import_module(_lazy_map[name])
        return getattr(module, name)
    raise AttributeError(f"module 'src.services' has no attribute {name!r}")


__all__ = [
    "AnalysisService",
    "BacktestService",
    "HistoryService",
    "StockService",
    "TaskService",
    "get_task_service",
]
