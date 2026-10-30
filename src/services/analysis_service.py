# -*- coding: utf-8 -*-
"""
===================================
분석 서비스 계층
===================================

역할:
1. 종목 분석 로직 캡슐화
2. analyzer와 pipeline을 호출해 분석 실행
3. 분석 결과를 데이터베이스에 저장
"""

import logging
import copy
import uuid
from typing import Optional, Dict, Any, Callable, List

from src.repositories.analysis_repo import AnalysisRepository
from src.report_language import (
    get_sentiment_label,
    get_localized_stock_name,
    localize_operation_advice,
    localize_trend_prediction,
    normalize_report_language,
)
from src.market_phase_summary import extract_market_phase_summary
from src.schemas.decision_action import build_action_fields
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    build_run_diagnostic_summary,
    get_current_diagnostic_context,
    reset_run_diagnostic_context,
)
from src.services.empty_news import empty_news_disclosure

logger = logging.getLogger(__name__)


def asset_type_from_canonical_code(code: Any) -> Optional[str]:
    """Derive the authoritative ``asset_type`` for a canonical stock/index code.

    Uses :func:`parse_analysis_target` — the single asset-type authority — on
    the *canonical* code, never the display code, so ``sh000016`` (index) and
    bare ``000016`` (stock) are distinguished by the parser rather than by
    display normalization. Returns ``None`` for market review / empty /
    unsupported codes, so legacy clients and market reviews simply omit the
    optional field.
    """
    text = str(code or "").strip()
    if not text:
        return None
    if text.upper() == "MARKET":
        return None

    from src.services.stock_list_parser import ParseStatus, parse_analysis_target

    target = parse_analysis_target(text)
    if target.asset_type == ParseStatus.INDEX:
        return "index"
    if target.asset_type == ParseStatus.STOCK:
        return "stock"
    return None


class AnalysisService:
    """
    분석 서비스
    
    종목 분석 관련 업무 로직을 캡슐화한다
    """
    
    def __init__(self):
        """분석 서비스 초기화"""
        self.repo = AnalysisRepository()
        self.last_error: Optional[str] = None
    
    def analyze_stock(
        self,
        stock_code: str,
        report_type: str = "detailed",
        force_refresh: bool = False,
        query_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        send_notification: bool = True,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        skills: Optional[List[str]] = None,
        analysis_phase: str = "auto",
        query_source: str = "api",
        portfolio_context: Optional[Dict[str, Any]] = None,
        report_language: Optional[str] = None,
        analysis_target: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        종목 분석 실행
        
        Args:
            stock_code: 종목 코드
            report_type: 리포트 유형 (simple/detailed)
            force_refresh: 강제 새로고침 여부
            query_id: 조회 ID(선택)
            send_notification: 알림 전송 여부(API 호출 시 기본 전송)
            analysis_phase: 요청한 분석 단계 덮어쓰기(auto/premarket/intraday/postmarket)
            analysis_target: 선택적 구조화 분석 대상(지수 대상을 pipeline까지 전달,
                그렇지 않으면 지수가 종목처럼 취급됨)
            
        Returns:
            분석 결과 딕셔너리, 포함 항목:
            - stock_code: 종목 코드
            - stock_name: 종목명
            - report: 분석 리포트
        """
        try:
            self.last_error = None
            # 분석 관련 모듈 불러오기
            from src.config import get_config
            from src.core.pipeline import StockAnalysisPipeline
            from src.enums import ReportType
            
            # query_id 생성
            if query_id is None:
                query_id = uuid.uuid4().hex
            effective_trace_id = trace_id or query_id
            diag_token = None
            if get_current_diagnostic_context() is None:
                diag_token = activate_run_diagnostic_context(
                    trace_id=effective_trace_id,
                    query_id=query_id,
                    stock_code=stock_code,
                    trigger_source=query_source or "api",
                )
            
            # 설정 가져오기
            config = get_config()
            normalized_report_language = normalize_report_language(report_language, default="")
            if normalized_report_language:
                config = copy.copy(config)
                config.report_language = normalized_report_language
            
            # 분석 파이프라인 생성
            pipeline = StockAnalysisPipeline(
                config=config,
                query_id=query_id,
                trace_id=effective_trace_id,
                query_source=query_source or "api",
                progress_callback=progress_callback,
                analysis_skills=skills,
                analysis_phase=analysis_phase,
                portfolio_context=portfolio_context,
            )
            
            # 리포트 유형 결정 (API: simple/detailed/full/brief -> ReportType)
            rt = ReportType.from_str(report_type)
            
            # 분석 실행
            result = pipeline.process_single_stock(
                code=stock_code,
                skip_analysis=False,
                single_stock_notify=send_notification,
                report_type=rt,
                analysis_target=analysis_target,
            )
            
            if result is None:
                logger.warning(f"종목 {stock_code} 분석 결과가 비어 있음")
                self.last_error = self.last_error or f"分析股票 {stock_code} 返回空结果"
                return None

            if not getattr(result, "success", True):
                self.last_error = getattr(result, "error_message", None) or f"分析股票 {stock_code} 失败"
                logger.warning(f"종목 {stock_code} 분석이 끝나지 못함: {self.last_error}")
                return None
            
            # 응답 만들기
            return self._build_analysis_response(result, query_id, report_type=rt.value)
            
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"종목 {stock_code} 분석 실패: {e}", exc_info=True)
            return None
        finally:
            reset_run_diagnostic_context(locals().get("diag_token"))
    
    def _build_analysis_response(
        self, 
        result: Any, 
        query_id: str,
        report_type: str = "detailed",
    ) -> Dict[str, Any]:
        """
        분석 응답 만들기
        
        Args:
            result: AnalysisResult 객체
            query_id: 조회 ID
            report_type: 정규화된 리포트 유형
            
        Returns:
            정리된 응답 딕셔너리
        """
        # 매매 가격대 가져오기
        sniper_points = {}
        if hasattr(result, 'get_sniper_points'):
            sniper_points = result.get_sniper_points() or {}
        
        # 심리 라벨 계산
        report_language = normalize_report_language(getattr(result, "report_language", "zh"))
        sentiment_label = get_sentiment_label(result.sentiment_score, report_language)
        stock_name = get_localized_stock_name(getattr(result, "name", None), result.code, report_language)
        action_fields = build_action_fields(
            operation_advice=getattr(result, "operation_advice", None),
            explicit_action=getattr(result, "action", None),
            report_type=report_type,
            report_language=report_language,
            sentiment_score=getattr(result, "sentiment_score", None),
            guardrail_reason=getattr(result, "guardrail_reason", None),
            align_with_score=True,
        )
        diagnostic_context = get_current_diagnostic_context()
        trace_id = diagnostic_context.trace_id if diagnostic_context is not None else query_id
        diagnostic_snapshot = diagnostic_context.snapshot() if diagnostic_context is not None else None
        diagnostic_context_snapshot = getattr(result, "diagnostic_context_snapshot", None)
        market_phase_summary = extract_market_phase_summary(diagnostic_context_snapshot)
        if isinstance(diagnostic_context_snapshot, dict):
            context_snapshot = dict(diagnostic_context_snapshot)
            if diagnostic_snapshot is not None:
                context_snapshot["diagnostics"] = diagnostic_snapshot
        elif diagnostic_snapshot is not None:
            context_snapshot = {"diagnostics": diagnostic_snapshot}
        else:
            context_snapshot = None
        diagnostic_summary = build_run_diagnostic_summary(
            context_snapshot=context_snapshot,
            raw_result=result.to_dict() if hasattr(result, "to_dict") else None,
            report_saved=True,
            query_id=query_id,
            stock_code=result.code,
        )
        
        # 리포트 구조 만들기
        report = {
            "meta": {
                "query_id": query_id,
                "trace_id": trace_id,
                "stock_code": result.code,
                "stock_name": stock_name,
                "report_type": report_type,
                "report_language": report_language,
                "current_price": result.current_price,
                "change_pct": result.change_pct,
                "model_used": getattr(result, "model_used", None),
                "market_phase_summary": market_phase_summary,
                "asset_type": asset_type_from_canonical_code(result.code),
            },
            "summary": {
                "analysis_summary": result.analysis_summary,
                "operation_advice": localize_operation_advice(result.operation_advice, report_language),
                "action": action_fields["action"],
                "action_label": action_fields["action_label"],
                "trend_prediction": localize_trend_prediction(result.trend_prediction, report_language),
                "sentiment_score": result.sentiment_score,
                "sentiment_label": sentiment_label,
            },
            "strategy": {
                "ideal_buy": sniper_points.get("ideal_buy"),
                "secondary_buy": sniper_points.get("secondary_buy"),
                "stop_loss": sniper_points.get("stop_loss"),
                "take_profit": sniper_points.get("take_profit"),
            },
            "details": {
                "news_summary": result.news_summary,
                "empty_news_disclosure": empty_news_disclosure(result, report_language),
                "technical_analysis": result.technical_analysis,
                "fundamental_analysis": result.fundamental_analysis,
                "risk_warning": result.risk_warning,
            }
        }
        if hasattr(result, "to_dict"):
            raw_result_payload = result.to_dict()
            if isinstance(raw_result_payload, dict):
                report["details"]["raw_result"] = raw_result_payload

        return {
            "query_id": query_id,
            "trace_id": trace_id,
            "stock_code": result.code,
            "stock_name": stock_name,
            "report": report,
            "diagnostic_summary": diagnostic_summary,
        }
