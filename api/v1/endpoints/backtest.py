# -*- coding: utf-8 -*-
"""Backtest endpoints."""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_database_manager
from api.v1.schemas.backtest import (
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestResultItem,
    BacktestResultsResponse,
    PerformanceMetrics,
)
from api.v1.schemas.common import ErrorResponse
from src.services.backtest_service import BacktestService
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()

BacktestAnalysisPhaseQuery = Literal["premarket", "intraday", "postmarket", "unknown"]


def _validate_analysis_date_range(
    analysis_date_from: Optional[date],
    analysis_date_to: Optional[date],
) -> None:
    if analysis_date_from and analysis_date_to and analysis_date_from > analysis_date_to:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_params",
                "message": "analysis_date_from cannot be after analysis_date_to",
            },
        )


@router.post(
    "/run",
    response_model=BacktestRunResponse,
    responses={
        200: {"description": "백테스트 실행 완료"},
        400: {"description": "요청 파라미터 오류", "model": ErrorResponse},
        500: {"description": "서버 오류", "model": ErrorResponse},
    },
    summary="백테스트 실행",
    description="과거 분석 기록으로 백테스트 평가를 하고 backtest_results/backtest_summaries 에 기록",
)
def run_backtest(
    request: BacktestRunRequest,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> BacktestRunResponse:
    try:
        _validate_analysis_date_range(request.analysis_date_from, request.analysis_date_to)
        service = BacktestService(db_manager)
        stats = service.run_backtest(
            code=request.code,
            force=request.force,
            eval_window_days=request.eval_window_days,
            min_age_days=request.min_age_days,
            analysis_date_from=request.analysis_date_from,
            analysis_date_to=request.analysis_date_to,
            limit=request.limit,
        )
        return BacktestRunResponse(**stats)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_params", "message": str(exc)},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"백테스트 실행 실패: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"백테스트 실행 실패: {str(exc)}"},
        )


@router.get(
    "/results",
    response_model=BacktestResultsResponse,
    responses={
        200: {"description": "백테스트 결과 목록"},
        400: {"description": "요청 파라미터 오류", "model": ErrorResponse},
        500: {"description": "서버 오류", "model": ErrorResponse},
    },
    summary="백테스트 결과 조회",
    description="백테스트 결과를 페이지 단위로 조회. 종목 코드로 거를 수 있음",
)
def get_backtest_results(
    code: Optional[str] = Query(None, description="종목 코드 필터"),
    eval_window_days: Optional[int] = Query(None, ge=1, le=120, description="평가 기간 필터"),
    analysis_date_from: Optional[date] = Query(None, description="분석일 시작 (포함)"),
    analysis_date_to: Optional[date] = Query(None, description="분석일 끝 (포함)"),
    analysis_phase: Optional[BacktestAnalysisPhaseQuery] = Query(None, description="분석 시점 필터: premarket/intraday/postmarket/unknown"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    limit: int = Query(20, ge=1, le=200, description="페이지당 개수"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> BacktestResultsResponse:
    try:
        _validate_analysis_date_range(analysis_date_from, analysis_date_to)
        service = BacktestService(db_manager)
        data = service.get_recent_evaluations(
            code=code,
            eval_window_days=eval_window_days,
            limit=limit,
            page=page,
            analysis_date_from=analysis_date_from,
            analysis_date_to=analysis_date_to,
            analysis_phase=analysis_phase,
        )
        items = [BacktestResultItem(**item) for item in data.get("items", [])]
        return BacktestResultsResponse(
            total=int(data.get("total", 0)),
            page=page,
            limit=limit,
            items=items,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_params", "message": str(exc)},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"백테스트 결과 조회 실패: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"백테스트 결과 조회 실패: {str(exc)}"},
        )


@router.get(
    "/performance",
    response_model=PerformanceMetrics,
    responses={
        200: {"description": "전체 백테스트 성과"},
        400: {"description": "요청 파라미터 오류", "model": ErrorResponse},
        404: {"description": "백테스트 요약 없음", "model": ErrorResponse},
        500: {"description": "서버 오류", "model": ErrorResponse},
    },
    summary="전체 백테스트 성과 조회",
)
def get_overall_performance(
    eval_window_days: Optional[int] = Query(None, ge=1, le=120, description="평가 기간 필터"),
    analysis_date_from: Optional[date] = Query(None, description="분석일 시작 (포함)"),
    analysis_date_to: Optional[date] = Query(None, description="분석일 끝 (포함)"),
    analysis_phase: Optional[BacktestAnalysisPhaseQuery] = Query(None, description="분석 시점 필터: premarket/intraday/postmarket/unknown"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> PerformanceMetrics:
    try:
        _validate_analysis_date_range(analysis_date_from, analysis_date_to)
        service = BacktestService(db_manager)
        summary = service.get_summary(
            scope="overall",
            code=None,
            eval_window_days=eval_window_days,
            analysis_date_from=analysis_date_from,
            analysis_date_to=analysis_date_to,
            analysis_phase=analysis_phase,
        )
        if summary is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "전체 백테스트 요약이 없어요"},
            )
        return PerformanceMetrics(**summary)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_params", "message": str(exc)},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"전체 성과 조회 실패: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"전체 성과 조회 실패: {str(exc)}"},
        )


@router.get(
    "/performance/{code}",
    response_model=PerformanceMetrics,
    responses={
        200: {"description": "종목별 백테스트 성과"},
        400: {"description": "요청 파라미터 오류", "model": ErrorResponse},
        404: {"description": "백테스트 요약 없음", "model": ErrorResponse},
        500: {"description": "서버 오류", "model": ErrorResponse},
    },
    summary="종목별 백테스트 성과 조회",
)
def get_stock_performance(
    code: str,
    eval_window_days: Optional[int] = Query(None, ge=1, le=120, description="평가 기간 필터"),
    analysis_date_from: Optional[date] = Query(None, description="분석일 시작 (포함)"),
    analysis_date_to: Optional[date] = Query(None, description="분석일 끝 (포함)"),
    analysis_phase: Optional[BacktestAnalysisPhaseQuery] = Query(None, description="분석 시점 필터: premarket/intraday/postmarket/unknown"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> PerformanceMetrics:
    try:
        _validate_analysis_date_range(analysis_date_from, analysis_date_to)
        service = BacktestService(db_manager)
        summary = service.get_summary(
            scope="stock",
            code=code,
            eval_window_days=eval_window_days,
            analysis_date_from=analysis_date_from,
            analysis_date_to=analysis_date_to,
            analysis_phase=analysis_phase,
        )
        if summary is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"{code} 의 백테스트 요약이 없어요"},
            )
        return PerformanceMetrics(**summary)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_params", "message": str(exc)},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"종목별 성과 조회 실패: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"종목별 성과 조회 실패: {str(exc)}"},
        )
