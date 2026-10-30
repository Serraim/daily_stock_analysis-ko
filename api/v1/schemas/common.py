# -*- coding: utf-8 -*-
"""
===================================
공통 응답 모델
===================================

역할:
1. 공통 응답 모델 정의 (HealthResponse, ErrorResponse 등)
2. 통일된 응답 형식 제공
"""

from typing import Optional, Any

from pydantic import BaseModel, ConfigDict, Field


class RootResponse(BaseModel):
    """API 루트 라우트 응답"""
    
    message: str = Field(..., description="API 실행 상태 메시지", json_schema_extra={"example": "Daily Stock Analysis API is running"})
    version: Optional[str] = Field(None, description="API 버전", json_schema_extra={"example": "1.0.0"})
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message": "Daily Stock Analysis API is running",
            "version": "1.0.0"
        }
    })


class HealthResponse(BaseModel):
    """헬스 체크 응답"""
    
    status: str = Field(..., description="서비스 상태", json_schema_extra={"example": "ok"})
    timestamp: Optional[str] = Field(None, description="타임스탬프")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "ok",
            "timestamp": "2024-01-01T12:00:00"
        }
    })


class ErrorResponse(BaseModel):
    """오류 응답"""
    
    error: str = Field(..., description="오류 종류", json_schema_extra={"example": "validation_error"})
    message: str = Field(..., description="오류 상세", json_schema_extra={"example": "요청 파라미터 오류"})
    detail: Optional[Any] = Field(None, description="추가 오류 정보")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "error": "not_found",
            "message": "리소스 없음",
            "detail": None
        }
    })


class SuccessResponse(BaseModel):
    """공통 성공 응답"""
    
    success: bool = Field(True, description="성공 여부")
    message: Optional[str] = Field(None, description="성공 메시지")
    data: Optional[Any] = Field(None, description="응답 데이터")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "success": True,
            "message": "처리 성공",
            "data": None
        }
    })
