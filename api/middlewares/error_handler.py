# -*- coding: utf-8 -*-
"""
===================================
전역 예외 처리 미들웨어
===================================

역할:
1. 처리되지 않은 예외 잡기
2. 오류 응답 형식 통일
3. 오류 로그 기록
"""

import logging
import traceback
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    전역 예외 처리 미들웨어
    
    처리되지 않은 예외를 모두 잡아서 같은 형식의 오류 응답으로 반환
    """
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: Callable
    ) -> Response:
        """
        요청을 처리하고 예외를 잡음
        
        Args:
            request: 요청 객체
            call_next: 다음 처리기
            
        Returns:
            Response: 응답 객체
        """
        try:
            response = await call_next(request)
            return response
            
        except Exception as e:
            # 오류 로그 기록
            logger.error(
                f"처리되지 않은 예외: {e}\n"
                f"요청 경로: {request.url.path}\n"
                f"요청 메서드: {request.method}\n"
                f"스택: {traceback.format_exc()}"
            )
            
            # 통일된 형식의 오류 응답 반환
            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_error",
                    "message": "서버 내부 오류예요. 잠시 후 다시 시도하세요",
                    "detail": str(e) if logger.isEnabledFor(logging.DEBUG) else None
                }
            )


def add_error_handlers(app) -> None:
    """
    전역 예외 처리기 추가
    
    FastAPI 앱에 예외 종류별 처리기 추가
    
    Args:
        app: FastAPI 앱 인스턴스
    """
    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """HTTP 예외 처리"""
        # detail 이 이미 ErrorResponse 형식 dict 면 그대로 사용
        if isinstance(exc.detail, dict) and "error" in exc.detail and "message" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail
            )
        # 아니면 detail 을 ErrorResponse 형식으로 감쌈
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "http_error",
                "message": str(exc.detail) if exc.detail else "HTTP Error",
                "detail": None
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """요청 검사 예외 처리"""
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "요청 파라미터 검사 실패",
                "detail": exc.errors()
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """일반 예외 처리"""
        logger.error(
            f"처리되지 않은 예외: {exc}\n"
            f"요청 경로: {request.url.path}\n"
            f"스택: {traceback.format_exc()}"
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "서버 내부 오류",
                "detail": None
            }
        )
