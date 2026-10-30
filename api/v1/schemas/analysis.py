# -*- coding: utf-8 -*-
"""
===================================
분석 관련 모델
===================================

역할:
1. 분석 요청·응답 모델 정의
2. 작업 상태 모델 정의
3. 비동기 작업 큐 관련 모델 정의
"""

from typing import Optional, List, Any, Literal
from enum import Enum

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from src.utils.analysis_metadata import SELECTION_SOURCE_PATTERN
from src.utils.market_review_region import normalize_market_review_region_strict


class TaskStatusEnum(str, Enum):
    """작업 상태 열거형"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"


AnalysisPhase = Literal["auto", "premarket", "intraday", "postmarket"]


class AnalyzeRequest(BaseModel):
    """Analysis request parameters"""
    
    stock_code: Optional[str] = Field(
        None, 
        description="종목 코드 하나", 
        json_schema_extra={"example": "600519"},
    )
    stock_codes: Optional[List[str]] = Field(
        None, 
        description="여러 종목 코드 (stock_code 와 둘 중 하나만)",
        json_schema_extra={"example": ["600519", "000858"]},
    )
    report_type: str = Field(
        "detailed",
        description="리포트 종류: simple(간단) / detailed(전체) / full(전체) / brief(요약)",
        pattern="^(simple|detailed|full|brief)$",
    )
    force_refresh: bool = Field(
        False,
        description="강제 새로고침 여부 (캐시 무시)"
    )
    async_mode: bool = Field(
        False,
        description="비동기 모드 사용 여부"
    )
    analysis_phase: AnalysisPhase = Field(
        "auto",
        description="분석 시점 지정: auto(자동 판단) / premarket(장 시작 전) / intraday(장중) / postmarket(장 마감 후)",
    )
    stock_name: Optional[str] = Field(
        None,
        description="사용자가 고른 종목명 (자동완성 때 전달)",
        json_schema_extra={"example": "贵州茅台"},
    )
    original_query: Optional[str] = Field(
        None,
        description="사용자가 입력한 원래 값 (예: 茅台, gzmt, 600519)",
        json_schema_extra={"example": "茅台"},
    )
    selection_source: Optional[str] = Field(
        None,
        description="종목 선택 경로: manual(직접 입력) | autocomplete(자동완성) | import(가져오기) | image(이미지 인식)",
        pattern=SELECTION_SOURCE_PATTERN,
        json_schema_extra={"example": "autocomplete"},
    )
    notify: bool = Field(
        True,
        description="알림 전송 여부 (Telegram/WeCom 등)"
    )
    report_language: Optional[Literal["zh", "en", "ko"]] = Field(
        None,
        validation_alias=AliasChoices("report_language", "reportLanguage"),
        description="이번 분석 리포트 출력 언어. 비우면 전역 REPORT_LANGUAGE 사용",
    )
    skills: Optional[List[str]] = Field(
        None,
        validation_alias=AliasChoices("skills", "strategies"),
        description="이번 분석에 쓸 전략 skill ID 목록. 예전 strategies 필드와도 호환",
        json_schema_extra={"example": ["bull_trend", "growth_quality"]},
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stock_code": "600519",
            "report_type": "detailed",
            "force_refresh": False,
            "async_mode": False,
            "analysis_phase": "auto",
            "stock_name": "贵州茅台",
            "original_query": "茅台",
            "selection_source": "autocomplete",
            "notify": True,
            "report_language": "zh",
            "skills": ["bull_trend"]
        }
    })


class MarketReviewRequest(BaseModel):
    """Market review trigger parameters."""

    send_notification: bool = Field(
        True,
        description="시장 리뷰가 끝난 뒤 알림을 보낼지 여부",
    )
    report_language: Optional[Literal["zh", "en", "ko"]] = Field(
        None,
        validation_alias=AliasChoices("report_language", "reportLanguage"),
        description="이번 시장 리뷰 리포트 출력 언어. 비우면 전역 REPORT_LANGUAGE 사용",
    )
    region: Optional[str] = Field(
        None,
        min_length=1,
        max_length=64,
        description=(
            "本次大盘复盘市场覆盖。合法 token 为 cn、hk、us、jp、kr、both；"
            "both 只能单独使用，其余 token 可用逗号组合。输入会忽略大小写和 token 两侧空格、"
            "去重并按 cn,hk,us,jp,kr 排序；空值、空 token、未知 token、both 混用或超过 "
            "64 个字符会整体返回 4xx，不会部分执行。未传时使用运行时全局 MARKET_REVIEW_REGION。"
        ),
        json_schema_extra={
            "example": "cn,us",
            "examples": ["cn", "jp,kr", "both"],
        },
    )

    @field_validator("region")
    @classmethod
    def normalize_region(cls, value: Optional[str]) -> Optional[str]:
        """Strictly validate request input and return its canonical ordering."""
        if value is None:
            return None
        return normalize_market_review_region_strict(value)


class MarketReviewAccepted(BaseModel):
    """Market review background task accepted response."""

    status: str = Field("accepted", description="제출 상태")
    message: str = Field(..., description="안내 메시지")
    send_notification: bool = Field(..., description="알림 전송 여부")
    region: str = Field(
        ...,
        description="이번 작업이 실제로 실행한 canonical 시장 범위",
        examples=["us", "jp,kr"],
    )
    trace_id: Optional[str] = Field(
        None,
        description="이번 백그라운드 작업의 진단 trace ID",
    )
    task_id: Optional[str] = Field(
        None,
        description="작업 ID (작업이 실제로 제출됐을 때만 반환)",
    )


class AnalysisResultResponse(BaseModel):
    """분석 결과 응답 모델"""
    
    query_id: str = Field(..., description="분석 기록 고유 ID")
    trace_id: Optional[str] = Field(None, description="진단 trace ID")
    stock_code: str = Field(..., description="종목 코드")
    stock_name: Optional[str] = Field(None, description="종목명")
    report: Optional[Any] = Field(None, description="분석 리포트")
    diagnostic_summary: Optional[Any] = Field(None, description="실행 진단 요약")
    created_at: str = Field(..., description="생성 시각")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "query_id": "abc123def456",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "report": {
                "summary": {
                    "sentiment_score": 75,
                    "operation_advice": "持有"
                }
            },
            "created_at": "2024-01-01T12:00:00"
        }
    })


class TaskAccepted(BaseModel):
    """비동기 작업 접수 응답"""
    
    task_id: str = Field(..., description="작업 ID (상태 조회용)")
    trace_id: Optional[str] = Field(None, description="진단 trace ID")
    status: str = Field(
        ..., 
        description="작업 상태",
        pattern="^(pending|processing)$"
    )
    message: Optional[str] = Field(None, description="안내 메시지")
    analysis_phase: AnalysisPhase = Field("auto", description="요청한 분석 시점")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "task_id": "task_abc123",
            "status": "pending",
            "message": "Analysis task accepted",
            "analysis_phase": "auto"
        }
    })


class BatchTaskAcceptedItem(BaseModel):
    """일괄 비동기 작업 중 제출에 성공한 항목 하나."""

    task_id: str = Field(..., description="작업 ID (상태 조회용)")
    trace_id: Optional[str] = Field(None, description="진단 trace ID")
    stock_code: str = Field(..., description="종목 코드")
    status: str = Field(
        ...,
        description="작업 상태",
        pattern="^(pending|processing)$"
    )
    message: Optional[str] = Field(None, description="안내 메시지")
    analysis_phase: AnalysisPhase = Field("auto", description="요청한 분석 시점")
    asset_type: Optional[Literal["stock", "index"]] = Field(
        None,
        description="parser 가 정한 자산 유형 (stock/index, 선택). 제출된 analysis_target 에서 그대로 넘어옴. 구버전 클라이언트는 생략 가능",
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "task_id": "task_abc123",
            "stock_code": "600519",
            "status": "pending",
            "message": "분석 작업을 큐에 넣었어요: 600519",
            "analysis_phase": "auto"
        }
    })


class BatchDuplicateTaskItem(BaseModel):
    """일괄 비동기 작업 중 중복 제출된 항목."""

    stock_code: str = Field(..., description="종목 코드")
    existing_task_id: str = Field(..., description="이미 있는 작업 ID")
    message: str = Field(..., description="오류 메시지")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stock_code": "600519",
            "existing_task_id": "task_existing_123",
            "message": "股票 600519 正在分析中 (task_id: task_existing_123)"
        }
    })


class RejectedTaskItem(BaseModel):
    """일괄 비동기 작업 중 명확히 거부된 대상 하나 (예: 미등록 CSI 지수)."""

    stock_code: str = Field(..., description="거부된 대상 코드")
    message: str = Field(..., description="거부 사유")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stock_code": "930956.CSI",
            "message": "unregistered CSI index: '930956.CSI' is not in the index registry",
        }
    })


class BatchTaskAcceptedResponse(BaseModel):
    """일괄 비동기 작업 접수 응답."""

    accepted: List[BatchTaskAcceptedItem] = Field(default_factory=list, description="제출에 성공한 작업 목록")
    duplicates: List[BatchDuplicateTaskItem] = Field(default_factory=list, description="중복이라 건너뛴 작업 목록")
    rejected: Optional[List[RejectedTaskItem]] = Field(
        None,
        description="일괄 요청 중 명확히 거부된 대상 목록 (예: 미등록 CSI 지수). 비동기 일괄 요청에서만 반환",
    )
    message: str = Field(..., description="요약 메시지")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "accepted": [
                {
                    "task_id": "task_abc123",
                    "stock_code": "600519",
                    "status": "pending",
                    "message": "분석 작업을 큐에 넣었어요: 600519",
                    "analysis_phase": "auto"
                }
            ],
            "duplicates": [
                {
                    "stock_code": "000858",
                    "existing_task_id": "task_existing_456",
                    "message": "股票 000858 正在分析中 (task_id: task_existing_456)"
                }
            ],
            "message": "작업 1개 제출, 중복 1개 건너뜀"
        }
    })


class TaskStatus(BaseModel):
    """Task status model"""
    
    task_id: str = Field(..., description="작업 ID")
    trace_id: Optional[str] = Field(None, description="진단 trace ID")
    status: TaskStatusEnum = Field(
        ..., 
        description="작업 상태",
    )
    progress: Optional[int] = Field(
        None, 
        description="진행률 (0-100)",
        ge=0,
        le=100
    )
    result: Optional[AnalysisResultResponse] = Field(
        None, 
        description="분석 결과 (completed 일 때만 있음)"
    )
    market_review_report: Optional[str] = Field(
        None,
        description="시장 리뷰 작업이 돌려준 리포트 텍스트 (시장 리뷰 작업만)",
    )
    market_review_payload: Optional[Any] = Field(
        None,
        description="Structured market-review payload for API/Web consumers.",
    )
    region: Optional[str] = Field(
        None,
        description="시장 리뷰 작업이 실제로 실행한 canonical 시장 범위",
    )
    error: Optional[str] = Field(
        None, 
        description="오류 메시지 (failed 일 때만 있음)"
    )
    stock_name: Optional[str] = Field(None, description="종목명")
    original_query: Optional[str] = Field(None, description="사용자가 입력한 원래 값")
    selection_source: Optional[str] = Field(
        None,
        description="선택 경로",
        pattern=SELECTION_SOURCE_PATTERN,
    )
    analysis_phase: Optional[AnalysisPhase] = Field(
        None,
        description="요청한 분석 시점. 이 필드가 저장되지 않은 예전 DB 기록에서 가져오면 비어 있을 수 있음",
    )
    skills: Optional[List[str]] = Field(None, description="이번 작업에 쓴 전략 skill ID 목록")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "task_id": "task_abc123",
            "status": "completed",
            "progress": 100,
            "result": None,
            "market_review_report": None,
            "error": None,
            "stock_name": "贵州茅台",
            "original_query": "茅台",
            "selection_source": "autocomplete",
            "analysis_phase": "auto",
            "skills": ["bull_trend"]
        }
    })


class TaskInfo(BaseModel):
    """
    Task details model

    Used for task list and SSE event delivery
    """
    
    task_id: str = Field(..., description="작업 ID")
    trace_id: Optional[str] = Field(None, description="진단 trace ID")
    stock_code: str = Field(..., description="종목 코드")
    stock_name: Optional[str] = Field(None, description="종목명")
    status: TaskStatusEnum = Field(..., description="작업 상태")
    progress: int = Field(0, description="진행률 (0-100)", ge=0, le=100)
    message: Optional[str] = Field(None, description="상태 메시지")
    report_type: str = Field("detailed", description="리포트 종류")
    created_at: str = Field(..., description="생성 시각")
    started_at: Optional[str] = Field(None, description="실행 시작 시각")
    completed_at: Optional[str] = Field(None, description="완료 시각")
    error: Optional[str] = Field(None, description="오류 메시지 (failed 일 때만 있음)")
    original_query: Optional[str] = Field(None, description="사용자가 입력한 원래 값")
    selection_source: Optional[str] = Field(
        None,
        description="선택 경로",
        pattern=SELECTION_SOURCE_PATTERN,
    )
    analysis_phase: AnalysisPhase = Field("auto", description="요청한 분석 시점")
    skills: Optional[List[str]] = Field(None, description="이번 작업에 쓴 전략 skill ID 목록")
    region: Optional[str] = Field(
        None,
        description="시장 리뷰 작업이 실제로 실행한 canonical 시장 범위",
    )
    asset_type: Optional[Literal["stock", "index"]] = Field(
        None,
        description="parser 가 정한 자산 유형 (stock/index, 선택). 제출된 analysis_target 에서 그대로 넘어옴. 구버전 클라이언트는 생략 가능",
    )
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "task_id": "abc123def456",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "status": "processing",
            "progress": 50,
            "message": "正在分析中...",
            "report_type": "detailed",
            "created_at": "2026-02-05T10:30:00",
            "started_at": "2026-02-05T10:30:01",
            "completed_at": None,
            "error": None,
            "original_query": "茅台",
            "selection_source": "autocomplete",
            "analysis_phase": "auto",
            "skills": ["bull_trend"]
        }
    })


class TaskListResponse(BaseModel):
    """작업 목록 응답 모델"""
    
    total: int = Field(..., description="전체 작업 수")
    pending: int = Field(..., description="대기 중인 작업 수")
    processing: int = Field(..., description="처리 중인 작업 수")
    tasks: List[TaskInfo] = Field(..., description="작업 목록")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "total": 3,
            "pending": 1,
            "processing": 2,
            "tasks": []
        }
    })


class DuplicateTaskErrorResponse(BaseModel):
    """중복 작업 오류 응답 모델"""
    
    error: str = Field("duplicate_task", description="오류 종류")
    message: str = Field(..., description="오류 메시지")
    stock_code: str = Field(..., description="종목 코드")
    existing_task_id: str = Field(..., description="이미 있는 작업 ID")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "error": "duplicate_task",
            "message": "股票 600519 正在分析中",
            "stock_code": "600519",
            "existing_task_id": "abc123def456"
        }
    })
