# -*- coding: utf-8 -*-
"""
===================================
분석 기록 관련 모델
===================================

역할:
1. 기록 목록·상세 모델 정의
2. 분석 리포트 전체 모델 정의
"""

from typing import Optional, List, Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.v1.schemas.market_phase import MarketPhaseSummary
from api.v1.schemas.research_artifact import ResearchArtifact
from src.schemas.decision_action import DecisionAction


class HistoryItem(BaseModel):
    """분석 기록 요약 (목록 표시용)"""

    id: Optional[int] = Field(None, description="분석 기록 기본키 ID")
    query_id: str = Field(..., description="분석 기록에 연결된 query_id (일괄 분석 시 중복됨)")
    stock_code: str = Field(..., description="종목 코드")
    stock_name: Optional[str] = Field(None, description="종목명")
    report_type: Optional[str] = Field(None, description="리포트 종류")
    region: Optional[str] = Field(
        None,
        description="시장 리뷰가 실제로 실행된 canonical 시장 범위",
    )
    trend_prediction: Optional[str] = Field(None, description="추세 예측")
    analysis_summary: Optional[str] = Field(None, description="분석 요약")
    sentiment_score: Optional[int] = Field(
        None,
        description="심리 점수 (과거 데이터는 0-100을 벗어날 수 있으며, 읽을 때 제한하지 않음)",
    )
    operation_advice: Optional[str] = Field(None, description="매매 의견")
    action: Optional[DecisionAction] = Field(None, description="구조화된 추천 행동 taxonomy")
    action_label: Optional[str] = Field(None, description="추천 행동 표시 라벨")
    current_price: Optional[float] = Field(None, description="분석 시점 주가")
    change_pct: Optional[float] = Field(None, description="분석 시점 등락률(%)")
    volume_ratio: Optional[float] = Field(None, description="분석 시점 거래량 비율")
    turnover_rate: Optional[float] = Field(None, description="분석 시점 회전율")
    model_used: Optional[str] = Field(
        None,
        description="분석 기록에 남은 모델 스냅샷. 기록 메타데이터 표시용일 뿐, 모델 설정이나 실행 중 라우팅에는 쓰지 않음",
    )
    market_phase_summary: Optional[MarketPhaseSummary] = Field(
        None,
        description="이번 분석의 시장 국면 요약 (민감 정보 제외)",
    )
    created_at: Optional[str] = Field(None, description="생성 시각")
    asset_type: Optional[Literal["stock", "index"]] = Field(
        None,
        description="백엔드 기준 자산 유형 (stock/index). 저장된 코드를 parser로 해석해 만듦. 구버전 클라이언트와 market review에서는 생략 가능.",
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": 1234,
            "query_id": "abc123",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "report_type": "detailed",
            "sentiment_score": 75,
            "operation_advice": "持有",
            "created_at": "2024-01-01T12:00:00"
        }
    })


class HistoryListResponse(BaseModel):
    """분석 기록 목록 응답"""

    total: int = Field(..., description="전체 기록 수")
    page: int = Field(..., description="현재 페이지 번호")
    limit: int = Field(..., description="페이지당 개수")
    items: List[HistoryItem] = Field(default_factory=list, description="기록 목록")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "total": 100,
            "page": 1,
            "limit": 20,
            "items": []
        }
    })


class DeleteHistoryRequest(BaseModel):
    """분석 기록 삭제 요청"""

    record_ids: List[int] = Field(default_factory=list, description="삭제할 분석 기록 기본키 ID 목록")


class DeleteHistoryResponse(BaseModel):
    """분석 기록 삭제 응답"""

    deleted: int = Field(..., description="실제로 삭제된 기록 수")


class NewsIntelItem(BaseModel):
    """뉴스 정보 항목"""

    title: str = Field(..., description="뉴스 제목")
    snippet: str = Field("", description="뉴스 요약 (최대 200자)")
    url: str = Field(..., description="뉴스 링크")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "title": "公司发布业绩快报，营收同比增长 20%",
            "snippet": "公司公告显示，季度营收同比增长 20%...",
            "url": "https://example.com/news/123"
        }
    })


class NewsIntelResponse(BaseModel):
    """뉴스 정보 응답"""

    total: int = Field(..., description="뉴스 개수")
    items: List[NewsIntelItem] = Field(default_factory=list, description="뉴스 목록")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "total": 2,
            "items": []
        }
    })


class ReportMeta(BaseModel):
    """리포트 메타 정보"""

    model_config = ConfigDict(protected_namespaces=("model_validate", "model_dump"))

    id: Optional[int] = Field(None, description="분석 기록 기본키 ID (기록에서 불러온 리포트에만 있음)")
    query_id: str = Field(..., description="분석 기록에 연결된 query_id (일괄 분석 시 중복됨)")
    stock_code: str = Field(..., description="종목 코드")
    stock_name: Optional[str] = Field(None, description="종목명")
    report_type: Optional[str] = Field(None, description="리포트 종류")
    report_language: Optional[str] = Field(None, description="리포트 출력 언어 (zh/en/ko)")
    created_at: Optional[str] = Field(None, description="생성 시각")
    current_price: Optional[float] = Field(None, description="분석 시점 주가")
    change_pct: Optional[float] = Field(None, description="분석 시점 등락률(%)")
    model_used: Optional[str] = Field(
        None,
        description="기록 리포트 메타데이터의 모델 스냅샷. 표시용일 뿐, 실행 중 모델 호출이나 설정 라우팅에는 쓰지 않음",
    )
    market_phase_summary: Optional[MarketPhaseSummary] = Field(
        None,
        description="이번 분석의 시장 국면 요약 (민감 정보 제외)",
    )
    asset_type: Optional[Literal["stock", "index"]] = Field(
        None,
        description="백엔드 기준 자산 유형 (stock/index). 지수 리포트에서는 종목 전용 관심종목 버튼을 숨기는 데 씀. market review와 구버전 클라이언트에서는 생략 가능.",
    )


class ReportSummary(BaseModel):
    """리포트 개요 영역"""

    analysis_summary: Optional[str] = Field(None, description="핵심 결론")
    operation_advice: Optional[str] = Field(None, description="매매 의견")
    action: Optional[DecisionAction] = Field(None, description="구조화된 추천 행동 taxonomy")
    action_label: Optional[str] = Field(None, description="추천 행동 표시 라벨")
    trend_prediction: Optional[str] = Field(None, description="추세 예측")
    sentiment_score: Optional[int] = Field(
        None,
        description="심리 점수 (과거 데이터는 0-100을 벗어날 수 있으며, 읽을 때 제한하지 않음)",
    )
    sentiment_label: Optional[str] = Field(None, description="심리 라벨")


class ReportStrategy(BaseModel):
    """매매 가격대 영역"""

    ideal_buy: Optional[str] = Field(None, description="적정 매수가")
    secondary_buy: Optional[str] = Field(None, description="2차 매수가")
    stop_loss: Optional[str] = Field(None, description="손절가")
    take_profit: Optional[str] = Field(None, description="익절가")


class AnalysisContextPackOverviewSubject(BaseModel):
    """AnalysisContextPack 공개 요약 - 종목 정보"""

    code: str = Field(..., description="종목 코드")
    stock_name: Optional[str] = Field(None, description="종목명")
    market: Optional[str] = Field(None, description="시장")


class AnalysisContextPackOverviewBlock(BaseModel):
    """AnalysisContextPack 可见摘要数据块"""

    key: str = Field(..., description="数据块稳定 key")
    label: str = Field(..., description="数据块展示名称")
    status: Literal[
        "available",
        "missing",
        "not_supported",
        "fallback",
        "stale",
        "estimated",
        "partial",
        "fetch_failed",
    ] = Field(..., description="数据块质量状态")
    source: Optional[str] = Field(None, description="数据来源")
    timestamp: Optional[str] = Field(None, description="上下文原始时间，可能为抓取时间")
    provider_timestamp: Optional[str] = Field(None, description="来源记录的观测时间")
    fetched_at: Optional[str] = Field(None, description="数据抓取时间，不代表观测时间")
    warnings: List[str] = Field(default_factory=list, description="数据块告警码")
    missing_reasons: List[str] = Field(default_factory=list, description="缺失原因")


class AnalysisContextPackOverviewCounts(BaseModel):
    """AnalysisContextPack 공개 요약 - 상태별 개수"""

    available: int = 0
    missing: int = 0
    not_supported: int = 0
    fallback: int = 0
    stale: int = 0
    estimated: int = 0
    partial: int = 0
    fetch_failed: int = 0


class AnalysisContextPackOverviewMetadata(BaseModel):
    """AnalysisContextPack 공개 요약 - 메타데이터"""

    trigger_source: Optional[str] = Field(None, description="실행 경로")
    news_result_count: Optional[int] = Field(None, description="뉴스 검색 결과 수")


class AnalysisContextPackOverviewDataQuality(BaseModel):
    """AnalysisContextPack 공개 요약 - 데이터 품질 점수"""

    overall_score: Optional[int] = Field(None, ge=0, le=100, description="입력 데이터 품질 총점")
    level: Optional[Literal["good", "usable", "limited", "poor"]] = Field(
        None,
        description="입력 데이터 품질 등급",
    )
    block_scores: Dict[str, int] = Field(default_factory=dict, description="고정 데이터 블록별 품질 점수")
    limitations: List[str] = Field(default_factory=list, description="데이터 한계 설명 (민감 정보 제외)")


class AnalysisContextPackOverview(BaseModel):
    """기록/API에 공개되는 AnalysisContextPack 요약 (민감 정보 제외)"""

    pack_version: str = Field(..., description="AnalysisContextPack 버전")
    created_at: Optional[str] = Field(None, description="생성 시각")
    subject: AnalysisContextPackOverviewSubject
    blocks: List[AnalysisContextPackOverviewBlock] = Field(default_factory=list)
    counts: AnalysisContextPackOverviewCounts
    data_quality: Optional[AnalysisContextPackOverviewDataQuality] = Field(
        None,
        description="이번 분석 입력 데이터 품질 요약 (민감 정보 제외)",
    )
    warnings: List[str] = Field(default_factory=list, description="전체 데이터 품질 알림")
    metadata: AnalysisContextPackOverviewMetadata = Field(default_factory=AnalysisContextPackOverviewMetadata)


class ReportDetails(BaseModel):
    """리포트 상세 영역"""

    news_content: Optional[str] = Field(None, description="뉴스 요약")
    empty_news_disclosure: Optional[str] = Field(
        None,
        description="뉴스 검색을 안 했거나 결과가 0건일 때 사용자에게 보여 줄 안내",
    )
    raw_result: Optional[Any] = Field(None, description="원본 분석 결과 (JSON)")
    context_snapshot: Optional[Any] = Field(None, description="분석 시점 컨텍스트 스냅샷 (JSON)")
    analysis_context_pack_overview: Optional[AnalysisContextPackOverview] = Field(
        None,
        description="이번 분석 입력 컨텍스트 묶음 요약 (민감 정보 제외)",
    )
    financial_report: Optional[Any] = Field(None, description="구조화된 재무제표 요약 (fundamental_context에서 가져옴)")
    dividend_metrics: Optional[Any] = Field(None, description="구조화된 배당 지표 (TTM 기준 포함)")
    belong_boards: Optional[Any] = Field(None, description="관련 업종 목록")
    sector_rankings: Optional[Any] = Field(None, description="업종 등락 순위 (구조 {top, bottom})")
    concept_rankings: Optional[Any] = Field(None, description="테마 업종 등락 순위 (구조 {top, bottom})")
    market_structure: Optional[Any] = Field(None, description="시장 구조 컨텍스트 (테마 층 + 개별 종목 위치 층)")

    @model_validator(mode="after")
    def populate_context_derived_details(self) -> "ReportDetails":
        if self.concept_rankings is None and self.context_snapshot is not None:
            try:
                from src.utils.data_processing import extract_board_detail_fields

                extracted = extract_board_detail_fields(self.context_snapshot)
                self.concept_rankings = extracted.get("concept_rankings")
            except Exception:
                self.concept_rankings = None
        if self.market_structure is None:
            try:
                from src.utils.data_processing import extract_market_structure_detail_field

                self.market_structure = extract_market_structure_detail_field(
                    self.context_snapshot,
                    self.raw_result,
                )
            except Exception:
                self.market_structure = None
        return self


class AnalysisReport(BaseModel):
    """분석 리포트 전체"""

    meta: ReportMeta = Field(..., description="메타 정보")
    summary: ReportSummary = Field(..., description="개요 영역")
    strategy: Optional[ReportStrategy] = Field(None, description="매매 가격대 영역")
    details: Optional[ReportDetails] = Field(None, description="상세 영역")
    structured_report: Optional[ResearchArtifact] = Field(
        None,
        description="结构化研究产物，供看板、个股研究页、监控和 Copilot 复用",
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "meta": {
                "query_id": "abc123",
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "report_type": "detailed",
                "report_language": "zh",
                "created_at": "2024-01-01T12:00:00"
            },
            "summary": {
                "analysis_summary": "技术面向好，建议持有",
                "operation_advice": "持有",
                "trend_prediction": "看多",
                "sentiment_score": 75,
                "sentiment_label": "乐观"
            },
            "strategy": {
                "ideal_buy": "1800.00",
                "secondary_buy": "1750.00",
                "stop_loss": "1700.00",
                "take_profit": "2000.00"
            },
            "details": None
        }
    })


class MarkdownReportResponse(BaseModel):
    """Markdown 형식 리포트 응답"""

    content: str = Field(..., description="Markdown 형식의 리포트 전체 내용")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "content": "# 📊 贵州茅台 (600519) 分析报告\n\n> 分析日期：**2024-01-01**\n\n..."
        }
    })


class StockBarItem(BaseModel):
    """종목 목록 항목 (중복 제거 후 종목별 요약)"""

    id: int = Field(..., description="이 종목의 가장 최근 분석 기록 기본키 ID")
    stock_code: str = Field(..., description="종목 코드")
    stock_name: Optional[str] = Field(None, description="종목명")
    report_type: Optional[str] = Field(None, description="리포트 종류")
    sentiment_score: Optional[int] = Field(
        None,
        description="최신 심리 점수",
    )
    operation_advice: Optional[str] = Field(None, description="최신 매매 의견")
    action: Optional[DecisionAction] = Field(None, description="구조화된 추천 행동 taxonomy")
    action_label: Optional[str] = Field(None, description="추천 행동 표시 라벨")
    analysis_count: int = Field(..., description="이 종목의 누적 분석 횟수")
    last_analysis_time: Optional[str] = Field(None, description="최근 분석 시각")
    model_used: Optional[str] = Field(
        None,
        description="최근 분석에 쓴 모델 스냅샷. 목록 표시용일 뿐, 실행 중 호출이나 설정에는 영향 없음",
    )
    market_phase_summary: Optional[MarketPhaseSummary] = Field(
        None,
        description="최근 분석의 시장 국면 요약 (민감 정보 제외)",
    )
    asset_type: Optional[Literal["stock", "index"]] = Field(
        None,
        description="백엔드 기준 자산 유형 (stock/index). 저장된 코드를 parser로 해석해 만듦. 구버전 클라이언트에서는 생략 가능.",
    )
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": 1234,
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "report_type": "detailed",
            "sentiment_score": 75,
            "operation_advice": "持有",
            "analysis_count": 18,
            "last_analysis_time": "2024-01-01T12:00:00",
            "model_used": "Gemini 2.5 Pro",
        }
    })


class StockBarResponse(BaseModel):
    """종목 목록 응답"""

    total: int = Field(..., description="중복 제외 종목 수")
    items: List[StockBarItem] = Field(default_factory=list, description="종목 목록")


class WatchlistRequest(BaseModel):
    """관심종목 목록 변경 요청"""

    stock_code: str = Field(..., description="종목 코드", min_length=1)


class WatchlistResponse(BaseModel):
    """관심종목 목록 응답"""

    stock_codes: List[str] = Field(default_factory=list, description="현재 관심종목 코드 목록")
    message: str = Field(..., description="처리 결과 설명")


class RunDiagnosticComponent(BaseModel):
    """실행 진단 구성 요소 하나의 요약."""

    key: str = Field(..., description="구성 요소 키")
    label: str = Field(..., description="구성 요소 표시 이름")
    status: str = Field(..., description="구성 요소 상태: ok/degraded/failed/unknown/not_configured/skipped")
    message: str = Field(..., description="사용자용 요약")
    details: Optional[Dict[str, Any]] = Field(None, description="접어서 보여 주는 진단 세부 정보")


class RunDiagnosticSummaryResponse(BaseModel):
    """기록 리포트의 실행 진단 요약."""

    trace_id: Optional[str] = Field(None, description="진단 trace ID")
    task_id: Optional[str] = Field(None, description="작업 ID")
    query_id: Optional[str] = Field(None, description="분석 query ID")
    stock_code: Optional[str] = Field(None, description="종목 코드")
    trigger_source: Optional[str] = Field(None, description="실행 경로")
    status: str = Field(..., description="전체 상태: normal/degraded/failed/unknown")
    status_label: str = Field(..., description="전체 상태 표시 라벨")
    reason: str = Field(..., description="가장 주요한 진단 원인")
    components: Dict[str, RunDiagnosticComponent] = Field(default_factory=dict, description="핵심 경로 진단 구성 요소")
    copy_text: str = Field(..., description="복사해 쓸 수 있는 문제 해결용 텍스트 (민감 정보 제거됨)")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "trace_id": "task_abc123",
            "query_id": "task_abc123",
            "stock_code": "600519",
            "status": "degraded",
            "status_label": "部分降级",
            "reason": "实时行情失败：timeout",
            "components": {},
            "copy_text": "trace_id: task_abc123\nstock_code: 600519\n...",
        }
    })
