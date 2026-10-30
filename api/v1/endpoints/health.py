# -*- coding: utf-8 -*-
"""
===================================
헬스 체크 API
===================================

역할:
1. /api/v1/health 헬스 체크 API 제공
2. 로드 밸런서와 모니터링 시스템용
"""

from datetime import datetime

from fastapi import APIRouter

from api.v1.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    헬스 체크 API
    
    로드 밸런서나 모니터링 시스템이 서비스 상태를 확인하는 용도
    
    Returns:
        HealthResponse: 서비스 상태와 타임스탬프 포함
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat()
    )
