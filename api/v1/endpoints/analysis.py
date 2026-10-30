# -*- coding: utf-8 -*-
"""
===================================
종목 분석 API
===================================

역할:
1. POST /api/v1/analysis/analyze 분석 실행 API 제공
2. GET /api/v1/analysis/status/{task_id} 작업 상태 조회 API 제공
3. GET /api/v1/analysis/tasks 작업 목록 조회 API 제공
4. GET /api/v1/analysis/tasks/stream SSE 실시간 알림 API 제공

특징:
- 비동기 작업 큐: 분석을 비동기로 실행해 요청을 막지 않음
- 중복 제출 방지: 같은 종목을 분석 중이면 409 반환
- SSE 실시간 알림: 작업 상태가 바뀌면 바로 프런트엔드에 알림
"""

import asyncio
import copy
import json
import logging
import re
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query, Body
from fastapi.responses import JSONResponse, StreamingResponse

from api.deps import get_config_dep
from api.v1.errors import api_error
from api.v1.schemas.analysis import (
    AnalyzeRequest,
    AnalysisResultResponse,
    TaskAccepted,
    BatchTaskAcceptedResponse,
    BatchTaskAcceptedItem,
    BatchDuplicateTaskItem,
    RejectedTaskItem,
    TaskStatus,
    TaskInfo,
    TaskListResponse,
    DuplicateTaskErrorResponse,
    MarketReviewRequest,
    MarketReviewAccepted,
)
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.history import (
    AnalysisReport,
    ReportMeta,
    ReportSummary,
    ReportStrategy,
    ReportDetails,
)
from api.v1.schemas.run_flow import RunFlowSnapshot
from data_provider.base import canonical_stock_code, normalize_stock_code
from src.data.stock_index_loader import resolve_index_stock_code
from src.config import Config
from src.core.market_review_lock import (
    MarketReviewExecutionLock as _MarketReviewExecutionLock,
    market_review_lock_path,
    release_market_review_lock as _release_market_review_lock,
    try_acquire_market_review_lock as _try_acquire_market_review_lock,
)
from src.core.market_review_runtime import (
    build_market_review_runtime as _runtime_build_market_review_runtime,
)
from src.analysis_context_pack_overview import (
    extract_analysis_context_pack_overview,
    sanitize_context_snapshot_for_api,
)
from src.market_phase_summary import (
    extract_market_phase_summary,
    rebuild_market_phase_summary_for_stock_code,
)
from src.services.stock_code_utils import is_code_like, resolve_index_stock_code_for_analysis
from src.services.stock_list_parser import ParseStatus, parse_analysis_target
from src.report_language import get_localized_stock_name, normalize_report_language
from src.schemas.decision_action import build_action_fields
from src.services.name_to_code_resolver import resolve_name_to_code
from src.services.task_queue import (
    get_task_queue,
    DuplicateTaskError,
    TaskStatus as TaskStatusEnum,
)
from src.services.analysis_service import asset_type_from_canonical_code
from src.services.run_diagnostics import build_run_diagnostic_summary
from src.services.run_flow import build_task_run_flow_snapshot
from src.services.empty_news import empty_news_disclosure_from_stored
from src.utils.data_processing import (
    normalize_model_used,
    parse_json_field,
    extract_fundamental_detail_fields,
    extract_board_detail_fields,
    extract_market_structure_detail_field,
    extract_realtime_detail_fields,
)
from src.utils.market_review_region import normalize_market_review_region_lenient

logger = logging.getLogger(__name__)

router = APIRouter()

_SUPPORTED_FREE_TEXT_RE = re.compile(r"^[A-Za-z0-9.*\-+\u3400-\u9fff\s]+$")


def _get_task_trace_id(task: Any) -> Optional[str]:
    trace_id = getattr(task, "trace_id", None)
    if isinstance(trace_id, str) and trace_id.strip():
        return trace_id
    task_id = getattr(task, "task_id", None)
    if isinstance(task_id, str) and task_id.strip():
        return task_id
    return None


def _task_asset_type(task: Any) -> Optional[str]:
    """Return the task's optional asset type only when it is a real literal.

    The Pydantic literal domain (``stock``/``index``) is the only allowed set:
    real in-domain strings pass through verbatim. Legacy mock/proxy tasks whose
    ``getattr`` yields a ``MagicMock`` child, and missing values, degrade to
    ``None`` so schema defaults keep legacy responses unchanged. Genuine
    out-of-domain strings are logged and degraded instead of widening the enum
    or silently masking drift.
    """
    raw = getattr(task, "asset_type", None)
    if not isinstance(raw, str):
        return None
    if raw in {"stock", "index"}:
        return raw
    # 실제 문자열이 허용 값과 정확히 같지 않으면 (빈 문자열, 공백만, 대소문자나
    # 공백이 섞인 형태 포함) 반드시 warning을 남기고 None으로 낮춤. 어긋남을 조용히 덮지 않기 위함. 문자열이 아닌
    # 대체 객체(MagicMock 하위 객체 등)만 조용히 None 처리.
    logger.warning(
        "task asset_type 이 허용 값이 아니라서 None으로 처리: task_id=%s asset_type=%r",
        getattr(task, "task_id", None),
        raw,
    )
    return None


def _market_review_lock_path(config: Config) -> Path:
    return market_review_lock_path(config)


def _build_market_review_runtime(config: Config, source_message: Optional[Any] = None) -> tuple[Any, Any, Any]:
    return _runtime_build_market_review_runtime(config, source_message)


def _with_request_report_language(config: Config, report_language: Optional[str]) -> Config:
    """Return a request-scoped config copy when the caller overrides report language."""
    normalized = normalize_report_language(report_language, default="")
    if not normalized:
        return config

    scoped_config = copy.copy(config)
    scoped_config.report_language = normalized
    return scoped_config


def _run_market_review_background(
    send_notification: bool,
    effective_region: str,
    lock_token: Optional[_MarketReviewExecutionLock] = None,
    config: Optional[Config] = None,
    query_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run market review after the API response has been accepted."""
    from src.core.market_review import run_market_review

    runtime_config = config or get_config_dep()
    try:
        notifier, analyzer, search_service = _build_market_review_runtime(runtime_config)
        review_kwargs = {
            "notifier": notifier,
            "analyzer": analyzer,
            "search_service": search_service,
            "config": runtime_config,
            "send_notification": send_notification,
            "override_region": effective_region,
            "return_structured": True,
            "trigger_source": "api",
        }
        if query_id:
            review_kwargs["query_id"] = query_id
        logger.info(
            "[MarketReview] component=market_review action=background_start "
            "trigger_source=api task_id=%s region=%s",
            query_id or "-",
            effective_region,
        )
        report = run_market_review(**review_kwargs)
        if not report:
            raise RuntimeError("大盘复盘未返回可持久化报告")
        if hasattr(report, "report"):
            return {
                "result": report.report,
                "market_review_payload": getattr(report, "market_review_payload", None),
                "region": effective_region,
            }
        return {"result": report, "region": effective_region}
    finally:
        _release_market_review_lock(lock_token)


def _coalesce_text(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _extract_guardrail_reason(raw_result: Any) -> Optional[str]:
    if not isinstance(raw_result, dict):
        return None
    for reason in (
        raw_result.get("guardrail_reason"),
        raw_result.get("downgrade_reason"),
        raw_result.get("decision_score_guardrail_reason"),
    ):
        if reason is not None:
            text = str(reason).strip()
            if text:
                return text
    metadata = raw_result.get("metadata")
    if isinstance(metadata, dict):
        metadata_reason = metadata.get("guardrail_reason") or metadata.get("downgrade_reason")
        if metadata_reason is not None:
            text = str(metadata_reason).strip()
            if text:
                return text
    return None


def _invalid_analysis_input_error() -> HTTPException:
    return api_error(400, "validation_error", "请输入有效的股票代码或股票名称")


def _is_obviously_invalid_analysis_input(text: str) -> bool:
    """Reject mixed alphanumeric noise and unsupported symbols early."""
    if not text or is_code_like(text):
        return False

    if not _SUPPORTED_FREE_TEXT_RE.fullmatch(text):
        return True

    has_letters = any(ch.isalpha() and ch.isascii() for ch in text)
    has_digits = any(ch.isdigit() for ch in text)
    return has_letters and has_digits


def _resolve_analysis_input(raw_value: str):
    """
    Resolve one analysis request input into ``(code, analysis_target)``.

    Code-like tokens go through :func:`parse_analysis_target` (the single
    asset-type authority): registered indices keep their structured
    ``AnalysisTarget`` (canonical id + index semantics), unsupported targets
    (e.g. unregistered ``930956.CSI``) are surfaced with their reason so the
    caller can reject them explicitly, and stock tokens keep the legacy
    resolution path. Non-code names (e.g. ``贵州茅台``) keep
    :func:`resolve_name_to_code` and never enter index classification.
    """
    text = (raw_value or "").strip()
    if not text:
        return None

    # CSI explicit forms (``csi930955`` / ``930955.CSI`` / ``CSI930955``) are
    # explicit code forms but ``is_code_like`` does not recognise the ``.CSI``
    # suffix; route them through parse_analysis_target so registered CSI
    # converges to its canonical index identity and unregistered CSI surfaces
    # as an explicit unsupported error (never a name-resolution fallback).
    normalized_csi = unicodedata.normalize("NFKC", text).strip().casefold()
    if re.fullmatch(r"(?:csi\d{6}|\d{6}\.csi)", normalized_csi):
        target = parse_analysis_target(text)
        if target.asset_type == ParseStatus.INDEX:
            return (target.canonical_id, target)
        return (text, target)

    # SH/SZ prefixed six-digit forms (``sh000016`` / ``SH000016``) are explicit
    # index/stock code shapes, but ``is_code_like`` rejects them when the bare
    # digits do not match the exchange's *stock* digit rules (``000016`` is an
    # SH index yet classifies as an SZ stock digit shape). Route them through
    # parse_analysis_target so registered SH/SZ indices keep their structured
    # target; unknown prefixed forms degrade to the stock path as usual.
    normalized_sh_sz = re.fullmatch(r"(sh|sz)(\d{6})", normalized_csi)
    if normalized_sh_sz is not None:
        target = parse_analysis_target(text)
        if target.asset_type == ParseStatus.INDEX:
            return (target.canonical_id, target)
        return (resolve_index_stock_code_for_analysis(text), None)

    if is_code_like(text):
        target = parse_analysis_target(text)
        if target.asset_type == ParseStatus.INDEX:
            return (target.canonical_id, target)
        if target.asset_type == ParseStatus.UNSUPPORTED:
            return (text, target)
        # Stock target: keep the existing canonical resolution path and do not
        # carry a stock target downstream (stock semantics must not change).
        return (resolve_index_stock_code_for_analysis(text), None)

    if text.isdigit() and len(text) == 4:
        resolved_index_code = resolve_index_stock_code_for_analysis(text)
        if resolved_index_code != canonical_stock_code(text):
            return (resolved_index_code, None)

    if _is_obviously_invalid_analysis_input(text):
        raise _invalid_analysis_input_error()

    resolved = resolve_name_to_code(text)
    if resolved:
        return (canonical_stock_code(resolved), None)

    raise _invalid_analysis_input_error()


# ============================================================
# POST /analyze - 종목 분석 실행
# ============================================================

@router.post(
    "/analyze",
    response_model=AnalysisResultResponse,
    responses={
        200: {"description": "분석 완료 (동기 모드)", "model": AnalysisResultResponse},
        202: {
            "description": "분석 작업 접수됨 (비동기 모드)",
            "model": Union[TaskAccepted, BatchTaskAcceptedResponse],
        },
        400: {"description": "요청 파라미터 오류", "model": ErrorResponse},
        409: {"description": "이미 분석 중인 종목이라 중복 제출 거부", "model": DuplicateTaskErrorResponse},
        500: {"description": "분석 실패", "model": ErrorResponse},
    },
    summary="종목 분석 실행",
    description="AI 분석 작업을 시작합니다. 동기/비동기 모드를 지원하며, 비동기 모드에서는 같은 종목을 중복 제출할 수 없습니다."
)
def trigger_analysis(
        request: AnalyzeRequest,
        config: Config = Depends(get_config_dep)
) -> Union[AnalysisResultResponse, JSONResponse]:
    """
    종목 분석 실행
    
    AI 분석 작업 시작. 종목 하나 또는 여러 종목 일괄 분석 지원
    
    흐름:
    1. 요청 파라미터 검사
    2. 비동기 모드: 중복 확인 -> 작업 큐에 등록 -> 202 반환
    3. 동기 모드: 바로 분석 실행 -> 200 반환
    
    Args:
        request: 분석 요청 파라미터
        config: 설정 의존성
        
    Returns:
        AnalysisResultResponse: 분석 결과 (동기 모드)
        TaskAccepted | BatchTaskAcceptedResponse: 작업 접수됨 (비동기 모드, 202 반환)
        
    Raises:
        HTTPException: 400 - 요청 파라미터 오류
        HTTPException: 409 - 이미 분석 중인 종목
        HTTPException: 500 - 분석 실패
    """
    # 요청 파라미터 검사
    stock_codes = []
    if request.stock_code:
        stock_codes.append(request.stock_code)
    if request.stock_codes:
        stock_codes.extend(request.stock_codes)

    if not stock_codes:
        raise api_error(400, "validation_error", "必须提供 stock_code 或 stock_codes 参数")

    # Limit the number of non-blank raw tokens BEFORE resolution. Rejected and
    # duplicate tokens must also count toward the cap, otherwise a request that
    # mixes one valid token with many rejected/duplicate tokens could bypass the
    # DoS limit via the post-dedup check below.
    MAX_BATCH_SIZE = 50
    non_empty_raw_tokens = [c for c in stock_codes if str(c or "").strip()]
    if len(non_empty_raw_tokens) > MAX_BATCH_SIZE:
        raise api_error(400, "validation_error", f"单次分析请求最多支持 {MAX_BATCH_SIZE} 只股票")

    # Normalize and de-duplicate inputs while preserving compatibility.
    # Code-like tokens go through parse_analysis_target (the single asset-type
    # authority) so registered indices keep their structured target; non-code
    # names keep the legacy stock-name resolution path.
    resolved_entries = [_resolve_analysis_input(c) for c in stock_codes]

    seen = set()
    unique_codes = []
    unique_targets = []
    rejected_entries = []
    for entry in resolved_entries:
        if entry is None:
            continue
        code, target = entry
        if not code:
            continue
        if target is not None and target.asset_type == ParseStatus.UNSUPPORTED:
            rejected_entries.append((code, target))
            continue
        # 중복 제거 키는 asset_type 에 따라 다름: INDEX 는 canonical_id 사용 (지수와 같은 코드의 종목을 합치지 않고,
        # CSI alias 는 하나로 모음), STOCK 은 기존 normalize_stock_code 동작 유지
        # ('600519' 와 '600519.SH' 를 합침).
        if target is not None and target.asset_type == ParseStatus.INDEX:
            norm = target.canonical_id
        else:
            norm = normalize_stock_code(code)
        if norm not in seen:
            seen.add(norm)
            unique_codes.append(code)
            unique_targets.append(target)

    stock_codes = unique_codes

    if not stock_codes:
        if not rejected_entries:
            raise api_error(400, "validation_error", "股票代码不能为空或仅包含空白字符")
        # 모든 대상이 거부됨 (단건 또는 일괄 전부 거부): 접수된 작업이 없는데 202를 주면
        # 클라이언트가 오해하므로 항상 400. 일부만 거부되면 아래 rejected 처리로 감.
        code, target = rejected_entries[0]
        reason = target.unsupported_reason or f"지원하지 않는 대상: {code}"
        raise api_error(400, "validation_error", reason)

    # Sync mode only supports single-stock analysis.
    if not request.async_mode:
        if len(stock_codes) > 1:
            raise api_error(
                400,
                "validation_error",
                "동기 모드는 종목 하나만 분석할 수 있어요. 여러 종목은 async_mode=true 로 요청하세요",
            )
        if rejected_entries:
            # 동기 모드는 rejected 처리를 지원하지 않음: 거부된 대상이 하나라도 있으면 (전부 거부 포함)
            # 첫 번째 미등록 대상의 검사 오류로 4xx 반환.
            code, target = rejected_entries[0]
            reason = target.unsupported_reason or f"지원하지 않는 대상: {code}"
            raise api_error(400, "validation_error", reason)
        return _handle_sync_analysis(stock_codes[0], request, analysis_target=unique_targets[0] if unique_targets else None)

    # Async mode submits one task per stock.
    return _handle_async_analysis_batch(stock_codes, request, analysis_targets=unique_targets, rejected_entries=rejected_entries)


def _handle_async_analysis_batch(
    stock_codes: list,
    request: AnalyzeRequest,
    analysis_targets: Optional[list] = None,
    rejected_entries: Optional[list] = None,
) -> JSONResponse:
    """
    Handle asynchronous analysis requests, including batch submission.

    Args:
        stock_codes: canonical codes to submit
        request: the analysis request
        analysis_targets: optional per-code structured targets (index targets
            flow through to the pipeline)
        rejected_entries: optional list of ``(code, target)`` pairs that were
            explicitly rejected (e.g. unregistered CSI); returned in the
            ``rejected`` field for batch requests only.
    """
    task_queue = get_task_queue()
    
    # Preserve metadata for single-stock requests. For batch requests,
    # only carry through metadata that semantically applies to the whole
    # batch, such as import/image source tracking.
    # A single "accepted" code alongside any rejected entries is a batch:
    # rejected entries mean the server has not fully disposed of a single-stock
    # request, so single-stock metadata/409/single-202 semantics must not apply.
    is_single = len(stock_codes) == 1 and not rejected_entries
    preserve_batch_metadata = request.selection_source in {"import", "image"}

    stock_name = request.stock_name if is_single else None
    original_query = request.original_query if (is_single or preserve_batch_metadata) else None
    selection_source = request.selection_source if (is_single or preserve_batch_metadata) else None
    notify = getattr(request, "notify", True)
    skills = getattr(request, "skills", None)
    analysis_phase = request.analysis_phase
    report_language = normalize_report_language(getattr(request, "report_language", None), default="")

    submit_kwargs = dict(
        stock_codes=stock_codes,
        stock_name=stock_name,
        original_query=original_query,
        selection_source=selection_source,
        report_type=request.report_type,
        analysis_phase=analysis_phase,
        force_refresh=request.force_refresh,
        notify=notify,
    )
    if report_language:
        submit_kwargs["report_language"] = report_language
    if skills is not None:
        submit_kwargs["skills"] = skills
    # None 이 아닌 구조화 target (지수 등) 이 있을 때만 넘김. 일반 종목 요청의
    # 기존 kwargs 형식은 그대로 유지.
    if analysis_targets is not None and any(t is not None for t in analysis_targets):
        submit_kwargs["analysis_targets"] = analysis_targets

    accepted_tasks, duplicate_errors = task_queue.submit_tasks_batch(**submit_kwargs)

    accepted = [
        BatchTaskAcceptedItem(
            task_id=task.task_id,
            trace_id=_get_task_trace_id(task),
            stock_code=task.stock_code,
            status="pending",
            message=f"분석 작업을 큐에 넣었어요: {task.stock_code}",
            analysis_phase=task.analysis_phase,
            asset_type=_task_asset_type(task),
        )
        for task in accepted_tasks
    ]
    duplicates = [
        BatchDuplicateTaskItem(
            stock_code=dup.stock_code,
            existing_task_id=dup.existing_task_id,
            message=str(dup),
        )
        for dup in duplicate_errors
    ]
    rejected = [
        RejectedTaskItem(
            stock_code=code,
            message=(target.unsupported_reason or f"지원하지 않는 대상: {code}"),
        )
        for code, target in (rejected_entries or [])
    ]
    
    # 종목 하나가 거부된 경우: 기존과 같이 409 유지
    if is_single and duplicates:
        dup = duplicates[0]
        error_response = DuplicateTaskErrorResponse(
            error="duplicate_task",
            message=dup.message,
            stock_code=dup.stock_code,
            existing_task_id=dup.existing_task_id,
        )
        return JSONResponse(
            status_code=409,
            content=error_response.model_dump()
        )
    
    # 종목 하나 성공 (rejected 없음): 기존 응답 형식 유지
    if is_single and accepted and not rejected:
        task_accepted = TaskAccepted(
            task_id=accepted[0].task_id,
            trace_id=accepted[0].trace_id,
            status="pending",
            message=accepted[0].message,
            analysis_phase=accepted[0].analysis_phase,
        )
        return JSONResponse(
            status_code=202,
            content=task_accepted.model_dump()
        )
    
    # 일괄: 요약 결과 반환 (rejected 는 async 일괄에서만 반환)
    rejected_count = len(rejected)
    if rejected_count:
        message = f"작업 {len(accepted)}개 제출, 중복 {len(duplicates)}개 건너뜀, {rejected_count}개 거부됨"
    else:
        message = f"작업 {len(accepted)}개 제출, 중복 {len(duplicates)}개 건너뜀"
    batch_response = BatchTaskAcceptedResponse(
        accepted=accepted,
        duplicates=duplicates,
        rejected=rejected if rejected else None,
        message=message,
    )
    return JSONResponse(
        status_code=202,
        content=batch_response.model_dump()
    )


def _handle_sync_analysis(
    stock_code: str,
    request: AnalyzeRequest,
    analysis_target: Optional[Any] = None,
) -> AnalysisResultResponse:
    """
    동기 분석 요청 처리
    
    바로 분석을 실행하고, 끝나면 결과 반환
    """
    import uuid
    from src.services.analysis_service import AnalysisService
    
    query_id = uuid.uuid4().hex
    
    try:
        service = AnalysisService()
        result = service.analyze_stock(
            stock_code=stock_code,
            report_type=request.report_type,
            force_refresh=request.force_refresh,
            query_id=query_id,
            send_notification=getattr(request, "notify", True),
            skills=getattr(request, "skills", None),
            analysis_phase=request.analysis_phase,
            report_language=getattr(request, "report_language", None),
            analysis_target=analysis_target,
        )

        if result is None:
            error_message = service.last_error or f"종목 {stock_code} 분석 실패"
            raise api_error(500, "analysis_failed", error_message)

        # 리포트 구조 만들기
        report_data = result.get("report", {})
        context_snapshot, fundamental_snapshot, raw_result_snapshot = _load_sync_fundamental_sources(
            query_id=query_id,
            stock_code=result.get("stock_code", stock_code),
        )
        report = _build_analysis_report(
            report_data,
            query_id,
            stock_code,
            result.get("stock_name"),
            context_snapshot=context_snapshot,
            fallback_fundamental_payload=fundamental_snapshot,
            fallback_raw_result_payload=raw_result_snapshot or result,
        )

        return AnalysisResultResponse(
            query_id=query_id,
            trace_id=result.get("trace_id") or query_id,
            stock_code=result.get("stock_code", stock_code),
            stock_name=result.get("stock_name"),
            report=report.model_dump() if report else None,
            diagnostic_summary=result.get("diagnostic_summary"),
            created_at=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"분석 실패: {e}", exc_info=True)
        raise api_error(500, "internal_error", f"분석 중 오류 발생: {str(e)}")


# ============================================================
# POST /market-review - 시장 리뷰 실행
# ============================================================

@router.post(
    "/market-review",
    response_model=MarketReviewAccepted,
    status_code=202,
    responses={
        202: {"description": "시장 리뷰 작업 접수됨", "model": MarketReviewAccepted},
        409: {"description": "시장 리뷰 실행 중", "model": ErrorResponse},
        500: {"description": "제출 실패", "model": ErrorResponse},
    },
    summary="시장 리뷰 실행",
    description="백그라운드 시장 리뷰 작업을 하나 제출합니다. CLI 의 시장 리뷰 실행 구성을 그대로 쓰고 리포트를 저장합니다. 수동 실행이라 거래일 여부로 건너뛰지 않습니다. 중복 방지는 프로세스 안/단일 서버 범위에서만 되므로, 여러 인스턴스(Worker/컨테이너 여러 개)로 배포하면 외부 멱등 처리로 중복 실행을 막아야 합니다.",
)
def trigger_market_review(
    request: Optional[MarketReviewRequest] = Body(None),
    config: Config = Depends(get_config_dep),
) -> MarketReviewAccepted:
    """Trigger market review from Web/API without blocking the request."""
    request = request or MarketReviewRequest()

    runtime_config = _with_request_report_language(config, request.report_language)
    effective_region = request.region or (
        normalize_market_review_region_lenient(runtime_config.market_review_region) or "cn"
    )

    lock_token = _try_acquire_market_review_lock(runtime_config)
    if lock_token is None:
        raise api_error(409, "duplicate_market_review", "시장 리뷰가 이미 실행 중이에요. 잠시 후 다시 시도하세요")

    try:
        task_id = uuid.uuid4().hex
        logger.info(
            "[MarketReview] component=market_review action=submit trigger_source=api "
            "task_id=%s region=%s send_notification=%s",
            task_id,
            effective_region,
            request.send_notification,
        )
        task = get_task_queue().submit_background_task(
            lambda: _run_market_review_background(
                request.send_notification,
                effective_region=effective_region,
                lock_token=lock_token,
                config=runtime_config,
                query_id=task_id,
            ),
            stock_code="market_review",
            stock_name="大盘复盘",
            message="大盘复盘任务已提交",
            task_id=task_id,
            region=effective_region,
        )
    except Exception:
        _release_market_review_lock(lock_token)
        raise

    return MarketReviewAccepted(
        status="accepted",
        message="시장 리뷰 작업을 제출했어요. 끝나면 리포트를 저장하고 설정에 따라 알림을 보냅니다",
        send_notification=request.send_notification,
        region=effective_region,
        task_id=task.task_id,
        trace_id=_get_task_trace_id(task),
    )


# ============================================================
# GET /tasks - 작업 목록 조회
# ============================================================

@router.get(
    "/tasks",
    response_model=TaskListResponse,
    responses={
        200: {"description": "작업 목록"},
    },
    summary="분석 작업 목록 조회",
    description="현재 모든 분석 작업 조회. 상태로 거를 수 있음"
)
def get_task_list(
    status: Optional[str] = Query(
        None,
        description="거를 상태: pending, processing, completed, failed, cancel_requested, cancelled(쉼표로 여러 개 지정 가능)"
    ),
    limit: int = Query(20, description="최대 반환 개수", ge=1, le=100),
) -> TaskListResponse:
    """
    분석 작업 목록 조회
    
    Args:
        status: 상태 필터 (선택)
        limit: 최대 반환 개수
        
    Returns:
        TaskListResponse: 작업 목록 응답
    """
    task_queue = get_task_queue()
    
    # 모든 작업 가져오기
    all_tasks = task_queue.list_all_tasks(limit=limit)
    
    # 상태로 거르기
    if status:
        status_list = [s.strip().lower() for s in status.split(",")]
        all_tasks = [t for t in all_tasks if t.status.value in status_list]
    
    # 통계
    stats = task_queue.get_task_stats()
    
    # Schema 로 변환
    task_infos = [
        TaskInfo(
            task_id=t.task_id,
            trace_id=_get_task_trace_id(t),
            stock_code=t.stock_code,
            stock_name=t.stock_name,
            status=t.status.value,
            progress=t.progress,
            message=t.message,
            report_type=t.report_type,
            created_at=t.created_at.isoformat(),
            started_at=t.started_at.isoformat() if t.started_at else None,
            completed_at=t.completed_at.isoformat() if t.completed_at else None,
            error=t.error,
            original_query=t.original_query,
            selection_source=t.selection_source,
            analysis_phase=t.analysis_phase,
            skills=getattr(t, "skills", None),
            region=t.region,
            asset_type=_task_asset_type(t),
        )
        for t in all_tasks
    ]
    
    return TaskListResponse(
        total=stats["total"],
        pending=stats["pending"],
        processing=stats["processing"],
        tasks=task_infos,
    )


# ============================================================
# GET /tasks/stream - SSE 실시간 알림
# ============================================================

@router.get(
    "/tasks/stream",
    responses={
        200: {"description": "SSE 이벤트 스트림", "content": {"text/event-stream": {}}},
    },
    summary="작업 상태 SSE 스트림",
    description="Server-Sent Events 로 작업 상태 변화를 실시간 전송"
)
async def task_stream():
    """
    SSE 작업 상태 스트림
    
    이벤트 종류:
    - connected: 연결 성공
    - task_created: 새 작업 생성
    - task_started: 작업 실행 시작
    - task_progress: 작업 단계 진행 상황 갱신
    - task_completed: 작업 완료
    - task_failed: 작업 실패
    - heartbeat: 하트비트 (30초마다)
    
    Returns:
        StreamingResponse: SSE 이벤트 스트림
    """
    async def event_generator():
        task_queue = get_task_queue()
        event_queue: asyncio.Queue = asyncio.Queue()
        
        # 연결 성공 이벤트 보내기
        yield _format_sse_event("connected", {"message": "Connected to task stream"})
        
        # 현재 진행 중인 작업 보내기
        pending_tasks = task_queue.list_pending_tasks()
        for task in pending_tasks:
            yield _format_sse_event("task_created", task.to_dict())
        
        # 작업 이벤트 구독
        task_queue.subscribe(event_queue)
        
        try:
            while True:
                try:
                    # 이벤트를 기다리다 시간 초과면 하트비트 전송
                    event = await asyncio.wait_for(event_queue.get(), timeout=30)
                    yield _format_sse_event(event["type"], event["data"])
                except asyncio.TimeoutError:
                    # 하트비트
                    yield _format_sse_event("heartbeat", {
                        "timestamp": datetime.now().isoformat()
                    })
        except asyncio.CancelledError:
            logger.debug("SSE client disconnected, cancelling event generator")
            raise
        finally:
            task_queue.unsubscribe(event_queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx 버퍼링 끄기
        }
    )


def _format_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """
    SSE 이벤트 포맷
    
    Args:
        event_type: 이벤트 종류
        data: 이벤트 데이터
        
    Returns:
        SSE 형식 문자열
    """
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _load_history_run_flow_by_query_id(
    query_id: str,
    *,
    code: Optional[str] = None,
    report_type: Optional[str] = None,
    fail_open: bool = False,
) -> Optional[RunFlowSnapshot]:
    try:
        from src.storage import DatabaseManager
        from src.services.history_service import HistoryService

        service = HistoryService(DatabaseManager.get_instance())
        return service.resolve_and_get_run_flow(
            query_id,
            code=code,
            report_type=report_type,
        )
    except Exception as e:
        if fail_open:
            logger.debug(
                "load history run-flow failed, falling back to task skeleton: query_id=%s err=%s",
                query_id,
                e,
            )
            return None
        raise


@router.get(
    "/tasks/{task_id}/flow",
    response_model=RunFlowSnapshot,
    responses={
        200: {"description": "작업 실행 흐름 스냅샷"},
        404: {"description": "작업 없음", "model": ErrorResponse},
        500: {"description": "서버 오류", "model": ErrorResponse},
    },
    summary="분석 작업 실행 흐름 조회",
    description="task_id 로 작업의 데이터/정보 흐름 스냅샷을 조회합니다. 진행 중인 작업에 진단 정보가 없으면 기본 뼈대 흐름을 반환합니다.",
)
def get_task_run_flow(task_id: str) -> RunFlowSnapshot:
    """
    분석 작업 실행 흐름 조회.

    Active tasks are served from the in-memory task queue. Completed tasks try
    to hydrate from persisted history diagnostics using the same task_id/query_id.
    """
    task_queue = get_task_queue()
    task = task_queue.get_task(task_id)

    if task:
        if task.status == TaskStatusEnum.COMPLETED:
            task_report_type = _history_report_type_for_task_flow(
                getattr(task, "report_type", None)
            )
            task_stock_code = _safe_task_flow_text(getattr(task, "stock_code", None), max_length=32)
            if task_report_type == "market_review":
                task_stock_code = "MARKET"
            history_snapshot = _load_history_run_flow_by_query_id(
                task_id,
                code=task_stock_code,
                report_type=task_report_type,
                fail_open=True,
            )
            if history_snapshot is not None:
                return history_snapshot
        return build_task_run_flow_snapshot(task)

    try:
        history_snapshot = _load_history_run_flow_by_query_id(task_id)
        if history_snapshot is not None:
            return history_snapshot
    except Exception as e:
        logger.error(f"작업 실행 흐름 조회 실패: {e}", exc_info=True)
        raise api_error(500, "internal_error", f"작업 실행 흐름 조회 실패: {str(e)}")

    raise api_error(404, "not_found", f"작업 {task_id} 이(가) 없거나 만료됐어요")


def _safe_task_flow_text(value: Any, *, max_length: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length]


def _history_report_type_for_task_flow(value: Any) -> Optional[str]:
    text = _safe_task_flow_text(value, max_length=64)
    if text is None:
        return None
    normalized = text.lower().strip().replace("-", "_")
    aliases = {
        "detailed": "full",
        "simple": "simple",
        "full": "full",
        "brief": "brief",
        "market": "market_review",
        "market_review": "market_review",
    }
    return aliases.get(normalized, normalized)


def _datetime_to_iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value
    return None


def _extract_report_created_at(payload: Dict[str, Any]) -> Optional[str]:
    report = payload.get("report")
    if not isinstance(report, dict):
        return None

    meta = report.get("meta")
    if not isinstance(meta, dict):
        return None

    return _datetime_to_iso(meta.get("created_at"))


def _display_stock_code_from_index(stock_code: Any) -> str:
    code = str(stock_code or "").strip()
    if not code:
        return code
    return resolve_index_stock_code(code) or code


def _display_market_phase_summary(stock_code: Any, context_snapshot: Any) -> Any:
    return rebuild_market_phase_summary_for_stock_code(
        _display_stock_code_from_index(stock_code),
        context_snapshot,
    )


def _prepare_report_for_task_enrichment(
    report_data: Dict[str, Any],
    created_at: Optional[str],
) -> Dict[str, Any]:
    enriched_report = dict(report_data)
    meta = dict(enriched_report.get("meta") or {})
    if created_at and not _datetime_to_iso(meta.get("created_at")):
        meta["created_at"] = created_at
    enriched_report["meta"] = meta
    return enriched_report


def _first_non_empty_report_value(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _ensure_report_action_fields(report_data: Dict[str, Any]) -> Dict[str, Any]:
    enriched_report = dict(report_data)
    meta = dict(enriched_report.get("meta") or {})
    summary = dict(enriched_report.get("summary") or {})
    details = enriched_report.get("details") if isinstance(enriched_report.get("details"), dict) else {}
    raw_result = details.get("raw_result") if isinstance(details.get("raw_result"), dict) else {}
    report_language = normalize_report_language(
        meta.get("report_language") or raw_result.get("report_language")
    )
    action_fields = build_action_fields(
        operation_advice=raw_result.get("operation_advice") or summary.get("operation_advice"),
        explicit_action=raw_result.get("action") or summary.get("action"),
        report_type=meta.get("report_type"),
        report_language=report_language,
        sentiment_score=_first_non_empty_report_value(
            summary.get("sentiment_score"),
            raw_result.get("sentiment_score"),
        ),
        guardrail_reason=_extract_guardrail_reason(raw_result),
        align_with_score=True,
    )
    summary["action"] = action_fields["action"]
    summary["action_label"] = action_fields["action_label"]
    enriched_report["summary"] = summary
    return enriched_report


def _build_task_analysis_result(task: Any) -> AnalysisResultResponse:
    """
    Normalize an in-memory completed task result to the public API contract.

    Older AnalysisService payloads contain stock_code/stock_name/report only.
    The status endpoint owns the task metadata, so it can supply the missing
    response fields without waiting for the database fallback path.
    """
    payload = dict(task.result)
    if not payload.get("query_id"):
        payload["query_id"] = task.task_id
    if not payload.get("trace_id"):
        payload["trace_id"] = _get_task_trace_id(task) or task.task_id
    if not payload.get("stock_code"):
        payload["stock_code"] = task.stock_code
    display_stock_code = _display_stock_code_from_index(payload.get("stock_code"))
    if display_stock_code:
        payload["stock_code"] = display_stock_code

    if not payload.get("stock_name") and getattr(task, "stock_name", None):
        payload["stock_name"] = task.stock_name

    if not payload.get("created_at"):
        payload["created_at"] = (
            _extract_report_created_at(payload)
            or _datetime_to_iso(getattr(task, "created_at", None))
            or _datetime_to_iso(getattr(task, "completed_at", None))
            or datetime.now().isoformat()
        )

    report_data = payload.get("report")
    stock_code = payload.get("stock_code")
    query_id = payload.get("query_id")
    report_enriched = False

    if isinstance(report_data, dict) and stock_code and query_id:
        context_snapshot, fundamental_snapshot, raw_result_snapshot = _load_sync_fundamental_sources(
            query_id=query_id,
            stock_code=stock_code,
        )
        report_task_details = report_data.get("details")
        report_task_raw_result = (
            report_task_details.get("raw_result")
            if isinstance(report_task_details, dict)
            else None
        )
        should_rebuild_report = (
            context_snapshot is not None
            or fundamental_snapshot is not None
            or raw_result_snapshot is not None
            or report_task_raw_result is not None
        )
        if should_rebuild_report:
            try:
                report = _build_analysis_report(
                    _prepare_report_for_task_enrichment(
                        report_data,
                        payload.get("created_at"),
                    ),
                    query_id,
                    stock_code,
                    payload.get("stock_name") or getattr(task, "stock_name", None),
                    context_snapshot=context_snapshot,
                    fallback_fundamental_payload=fundamental_snapshot,
                    fallback_raw_result_payload=raw_result_snapshot or payload,
                )
                payload["report"] = report.model_dump()
                report_enriched = True
            except Exception as e:
                logger.debug(
                    "enrich in-memory task report failed (fail-open): task_id=%s err=%s",
                    getattr(task, "task_id", None),
                    e,
                )

    if not report_enriched and isinstance(report_data, dict):
        meta = report_data.get("meta")
        if isinstance(meta, dict) and display_stock_code:
            raw_meta_code = meta.get("stock_code") or getattr(task, "stock_code", None)
            meta["stock_code"] = display_stock_code
            meta["market_phase_summary"] = _display_market_phase_summary(
                raw_meta_code,
                {"market_phase_summary": meta.get("market_phase_summary")},
            )
        payload["report"] = _ensure_report_action_fields(report_data)

    return AnalysisResultResponse.model_validate(payload)


# ============================================================
# GET /status/{task_id} - 작업 하나의 상태 조회
# ============================================================

@router.get(
    "/status/{task_id}",
    response_model=TaskStatus,
    responses={
        200: {"description": "작업 상태"},
        404: {"description": "작업 없음", "model": ErrorResponse},
    },
    summary="분석 작업 상태 조회",
    description="task_id 로 작업 하나의 상태 조회"
)
def get_analysis_status(task_id: str) -> TaskStatus:
    """
    분석 작업 상태 조회
    
    먼저 작업 큐에서 찾고, 없으면 DB 의 분석 기록에서 찾음
    
    Args:
        task_id: 작업 ID
        
    Returns:
        TaskStatus: 작업 상태 정보
        
    Raises:
        HTTPException: 404 - 작업 없음
    """
    # 1. 먼저 작업 큐에서 조회
    task_queue = get_task_queue()
    task = task_queue.get_task(task_id)
    
    if task:
        result: Optional[AnalysisResultResponse] = None
        market_review_report = None
        market_review_payload = None

        if task.status == TaskStatusEnum.COMPLETED and isinstance(task.result, dict):
            if task.stock_code == "market_review":
                report_text = task.result.get("result")
                if isinstance(report_text, str) and report_text.strip():
                    market_review_report = report_text
                payload = task.result.get("market_review_payload")
                if isinstance(payload, dict):
                    market_review_payload = payload
            else:
                try:
                    result = _build_task_analysis_result(task)
                except Exception:
                    logger.warning(
                        "작업 결과 해석 실패, 빈 결과로 대체: task_id=%s",
                        task.task_id,
                    )

        return TaskStatus(
            task_id=task.task_id,
            trace_id=_get_task_trace_id(task),
            status=task.status.value,
            progress=task.progress,
            result=result,
            market_review_report=market_review_report,
            market_review_payload=market_review_payload,
            region=task.region,
            error=task.error,
            stock_name=task.stock_name,
            original_query=task.original_query,
            selection_source=task.selection_source,
            analysis_phase=task.analysis_phase,
            skills=getattr(task, "skills", None),
        )
    
    # 2. DB 에서 완료된 기록 조회
    try:
        from src.storage import DatabaseManager
        db = DatabaseManager.get_instance()
        records = db.get_analysis_history(query_id=task_id, limit=1)

        if records:
            record = records[0]
            raw_result = parse_json_field(record.raw_result)
            if getattr(record, "report_type", None) == "market_review":
                market_review_report = None
                context_snapshot = parse_json_field(getattr(record, "context_snapshot", None))
                market_review_payload = None
                region = None
                if isinstance(context_snapshot, dict):
                    raw_region = context_snapshot.get("market_review_region")
                    if isinstance(raw_region, str) and raw_region.strip():
                        region = raw_region.strip()
                    payload = context_snapshot.get("market_review_payload")
                    if isinstance(payload, dict):
                        market_review_payload = payload
                        if region is None:
                            payload_region = payload.get("region")
                            if isinstance(payload_region, str) and payload_region.strip():
                                region = payload_region.strip()
                if isinstance(raw_result, dict):
                    report_text = raw_result.get("raw_response") or raw_result.get("market_review_report")
                    if isinstance(report_text, str) and report_text.strip():
                        market_review_report = report_text
                if not market_review_report and record.news_content:
                    market_review_report = record.news_content

                return TaskStatus(
                    task_id=task_id,
                    trace_id=task_id,
                    status="completed",
                    progress=100,
                    result=None,
                    market_review_report=market_review_report,
                    market_review_payload=market_review_payload,
                    region=region,
                    error=None,
                    stock_name=record.name,
                )

            model_used = normalize_model_used(
                (raw_result or {}).get("model_used") if isinstance(raw_result, dict) else None
            )
            report_language = normalize_report_language(
                (raw_result or {}).get("report_language") if isinstance(raw_result, dict) else None
            )
            stock_name = get_localized_stock_name(record.name, record.code, report_language)
            display_stock_code = _display_stock_code_from_index(record.code)

            # Extract current_price / change_pct from context_snapshot
            skills = None
            context_snapshot = parse_json_field(getattr(record, 'context_snapshot', None))
            analysis_context_pack_overview = extract_analysis_context_pack_overview(context_snapshot)
            market_phase_summary = _display_market_phase_summary(record.code, context_snapshot)
            api_context_snapshot = sanitize_context_snapshot_for_api(context_snapshot)
            if context_snapshot and isinstance(context_snapshot, dict):
                raw_skills = context_snapshot.get("skills")
                if isinstance(raw_skills, list):
                    skills = [str(skill) for skill in raw_skills]
            realtime_fields = extract_realtime_detail_fields(context_snapshot)
            current_price = realtime_fields.get("current_price")
            change_pct = realtime_fields.get("change_pct")
            fallback_fundamental = db.get_latest_fundamental_snapshot(
                query_id=task_id,
                code=record.code,
            )
            extracted_fundamental = extract_fundamental_detail_fields(
                context_snapshot=context_snapshot,
                fallback_fundamental_payload=fallback_fundamental,
            )
            extracted_boards = extract_board_detail_fields(
                context_snapshot=context_snapshot,
                fallback_fundamental_payload=fallback_fundamental,
            )
            market_structure = extract_market_structure_detail_field(
                context_snapshot,
                raw_result,
            )
            news_disclosure = empty_news_disclosure_from_stored(
                raw_result,
                context_snapshot,
                report_language,
            )
            has_board_details = (
                bool(extracted_boards.get("belong_boards"))
                or extracted_boards.get("sector_rankings") is not None
                or extracted_boards.get("concept_rankings") is not None
            )
            details = None
            if (
                any(extracted_fundamental.values())
                or has_board_details
                or market_structure is not None
                or context_snapshot is not None
                or analysis_context_pack_overview is not None
                or news_disclosure is not None
            ):
                details = ReportDetails(
                    news_content=getattr(record, "news_content", None),
                    empty_news_disclosure=news_disclosure,
                    raw_result=raw_result,
                    context_snapshot=api_context_snapshot,
                    analysis_context_pack_overview=analysis_context_pack_overview,
                    financial_report=extracted_fundamental.get("financial_report"),
                    dividend_metrics=extracted_fundamental.get("dividend_metrics"),
                    belong_boards=extracted_boards.get("belong_boards"),
                    sector_rankings=extracted_boards.get("sector_rankings"),
                    concept_rankings=extracted_boards.get("concept_rankings"),
                    market_structure=market_structure,
                )

            raw_dict = raw_result if isinstance(raw_result, dict) else {}
            action_fields = build_action_fields(
                operation_advice=raw_dict.get("operation_advice") or record.operation_advice,
                explicit_action=raw_dict.get("action"),
                report_type=getattr(record, 'report_type', None),
                report_language=report_language,
                sentiment_score=record.sentiment_score if record.sentiment_score is not None else raw_dict.get("sentiment_score"),
                guardrail_reason=_extract_guardrail_reason(raw_dict),
                align_with_score=True,
            )

            # Build report from DB record so completed tasks return real data
            report_dict = AnalysisReport(
                meta=ReportMeta(
                    id=record.id,
                    query_id=task_id,
                    stock_code=display_stock_code,
                    stock_name=stock_name,
                    report_type=getattr(record, 'report_type', None),
                    report_language=report_language,
                    created_at=record.created_at.isoformat() if record.created_at else None,
                    model_used=model_used,
                    current_price=current_price,
                    change_pct=change_pct,
                    market_phase_summary=market_phase_summary,
                    asset_type=asset_type_from_canonical_code(record.code),
                ),
                summary=ReportSummary(
                    sentiment_score=record.sentiment_score,
                    operation_advice=record.operation_advice,
                    action=action_fields["action"],
                    action_label=action_fields["action_label"],
                    trend_prediction=record.trend_prediction,
                    analysis_summary=record.analysis_summary,
                ),
                strategy=ReportStrategy(
                    ideal_buy=_stringify_report_strategy_value(getattr(record, 'ideal_buy', None)),
                    secondary_buy=_stringify_report_strategy_value(getattr(record, 'secondary_buy', None)),
                    stop_loss=_stringify_report_strategy_value(getattr(record, 'stop_loss', None)),
                    take_profit=_stringify_report_strategy_value(getattr(record, 'take_profit', None)),
                ),
                details=details,
            ).model_dump()
            return TaskStatus(
                task_id=task_id,
                trace_id=task_id,
                status="completed",
                progress=100,
                result=AnalysisResultResponse(
                    query_id=task_id,
                    trace_id=task_id,
                    stock_code=display_stock_code,
                    stock_name=stock_name,
                    report=report_dict,
                    diagnostic_summary=build_run_diagnostic_summary(
                        context_snapshot=context_snapshot,
                        raw_result=raw_result,
                        report_saved=True,
                        query_id=task_id,
                        stock_code=display_stock_code,
                    ),
                    created_at=record.created_at.isoformat() if record.created_at else datetime.now().isoformat()
                ),
                error=None,
                skills=skills,
            )

    except Exception as e:
        logger.error(f"작업 상태 조회 실패: {e}", exc_info=True)
        raise api_error(500, "internal_error", f"작업 상태 조회 실패: {str(e)}")

    # 3. 작업 없음
    raise api_error(404, "not_found", f"작업 {task_id} 이(가) 없거나 만료됐어요")


# ============================================================
# 보조 함수
# ============================================================

def _load_sync_fundamental_sources(
    query_id: str,
    stock_code: str,
) -> tuple[Optional[Any], Optional[Dict[str, Any]], Optional[Any]]:
    """
    Load report enrichment payloads for sync analyze response.
    """
    try:
        from src.storage import DatabaseManager

        db = DatabaseManager.get_instance()
        records = db.get_analysis_history(query_id=query_id, code=stock_code, limit=1)
        context_snapshot = None
        raw_result_snapshot = None
        if records:
            latest_record = records[0]
            context_snapshot = parse_json_field(getattr(latest_record, "context_snapshot", None))
            raw_result_snapshot = parse_json_field(getattr(latest_record, "raw_result", None))

        fallback_fundamental = db.get_latest_fundamental_snapshot(
            query_id=query_id,
            code=stock_code,
        )
        return context_snapshot, fallback_fundamental, raw_result_snapshot
    except Exception as e:
        logger.debug(
            "load sync fundamental sources failed (fail-open): query_id=%s stock_code=%s err=%s",
            query_id,
            stock_code,
            e,
        )
        return None, None, None


def _stringify_report_strategy_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _build_analysis_report(
        report_data: Dict[str, Any],
        query_id: str,
        stock_code: str,
        stock_name: Optional[str] = None,
        context_snapshot: Optional[Any] = None,
        fallback_fundamental_payload: Optional[Dict[str, Any]] = None,
        fallback_raw_result_payload: Optional[Any] = None,
) -> AnalysisReport:
    """
    API 규격에 맞는 분석 리포트 만들기
    
    Args:
        report_data: 원본 리포트 데이터
        query_id: 조회 ID
        stock_code: 종목 코드
        stock_name: 종목명
        context_snapshot: 컨텍스트 스냅샷 (선택)
        fallback_fundamental_payload: 기본 지표 스냅샷 payload (선택)
        fallback_raw_result_payload: 원본 분석 결과 payload (선택)
        
    Returns:
        AnalysisReport: 구조화된 분석 리포트
    """
    meta_data = report_data.get("meta", {})
    summary_data = report_data.get("summary", {})
    strategy_data = report_data.get("strategy", {})
    details_data = report_data.get("details", {})
    report_language = normalize_report_language(
        meta_data.get("report_language")
        or (context_snapshot or {}).get("report_language")
        or getattr(Config.get_instance(), "report_language", "zh")
    )
    display_stock_code = _display_stock_code_from_index(meta_data.get("stock_code", stock_code))
    localized_stock_name = get_localized_stock_name(
        meta_data.get("stock_name", stock_name),
        display_stock_code,
        report_language,
    )
    realtime_fields = extract_realtime_detail_fields(context_snapshot)
    current_price = meta_data.get("current_price")
    if current_price is None:
        current_price = realtime_fields.get("current_price")
    change_pct = meta_data.get("change_pct")
    if change_pct is None:
        change_pct = realtime_fields.get("change_pct")
    raw_stock_code = meta_data.get("stock_code", stock_code)
    market_phase_summary = _display_market_phase_summary(raw_stock_code, context_snapshot)
    if market_phase_summary is None:
        meta_phase_summary = meta_data.get("market_phase_summary")
        if meta_phase_summary is not None:
            market_phase_summary = _display_market_phase_summary(
                raw_stock_code,
                {"market_phase_summary": meta_phase_summary},
            )

    meta = ReportMeta(
        query_id=meta_data.get("query_id", query_id),
        stock_code=display_stock_code,
        stock_name=localized_stock_name,
        report_type=meta_data.get("report_type", "detailed"),
        report_language=report_language,
        created_at=meta_data.get("created_at", datetime.now().isoformat()),
        current_price=current_price,
        change_pct=change_pct,
        model_used=normalize_model_used(meta_data.get("model_used")),
        market_phase_summary=market_phase_summary,
        asset_type=asset_type_from_canonical_code(raw_stock_code),
    )

    def _looks_like_raw_result_payload(candidate: Any) -> bool:
        return (
            isinstance(candidate, dict)
            and (
                "analysis_summary" in candidate
                or "operation_advice" in candidate
                or "trend_prediction" in candidate
                or "sentiment_score" in candidate
                or "market_structure_context" in candidate
                or "model_used" in candidate
                or "dashboard" in candidate
                or "action" in candidate
            )
        )

    raw_result_data = details_data.get("raw_result")
    if not isinstance(raw_result_data, dict):
        raw_result_data = {}
        if isinstance(fallback_raw_result_payload, dict):
            if isinstance(fallback_raw_result_payload.get("raw_result"), dict):
                raw_result_data = fallback_raw_result_payload["raw_result"]
            elif _looks_like_raw_result_payload(fallback_raw_result_payload):
                raw_result_data = fallback_raw_result_payload
        if not raw_result_data and isinstance(details_data, dict):
            raw_result_data = details_data
    action_fields = build_action_fields(
        operation_advice=(
            raw_result_data.get("operation_advice")
            or details_data.get("operation_advice")
            or summary_data.get("operation_advice")
        ),
        explicit_action=raw_result_data.get("action") or details_data.get("action") or summary_data.get("action"),
        report_type=meta.report_type,
        report_language=report_language,
        sentiment_score=_first_non_empty_report_value(
            summary_data.get("sentiment_score"),
            raw_result_data.get("sentiment_score"),
            details_data.get("sentiment_score"),
        ),
        guardrail_reason=_extract_guardrail_reason(raw_result_data),
        align_with_score=True,
    )

    summary = ReportSummary(
        analysis_summary=summary_data.get("analysis_summary"),
        operation_advice=summary_data.get("operation_advice"),
        action=action_fields["action"],
        action_label=action_fields["action_label"],
        trend_prediction=summary_data.get("trend_prediction"),
        sentiment_score=summary_data.get("sentiment_score"),
        sentiment_label=summary_data.get("sentiment_label")
    )

    strategy = None
    if strategy_data:
        strategy = ReportStrategy(
            ideal_buy=_stringify_report_strategy_value(strategy_data.get("ideal_buy")),
            secondary_buy=_stringify_report_strategy_value(strategy_data.get("secondary_buy")),
            stop_loss=_stringify_report_strategy_value(strategy_data.get("stop_loss")),
            take_profit=_stringify_report_strategy_value(strategy_data.get("take_profit"))
        )

    extracted_fundamental = extract_fundamental_detail_fields(
        context_snapshot=context_snapshot,
        fallback_fundamental_payload=fallback_fundamental_payload,
    )
    extracted_boards = extract_board_detail_fields(
        context_snapshot=context_snapshot,
        fallback_fundamental_payload=fallback_fundamental_payload,
    )
    market_structure = None
    for raw_candidate in (fallback_raw_result_payload, raw_result_data, details_data):
        if raw_candidate is None:
            continue
        market_structure = extract_market_structure_detail_field(
            context_snapshot,
            raw_candidate,
        )
        if market_structure is not None:
            break
    analysis_context_pack_overview = extract_analysis_context_pack_overview(context_snapshot)
    api_context_snapshot = sanitize_context_snapshot_for_api(context_snapshot)
    news_disclosure = empty_news_disclosure_from_stored(
        raw_result_data,
        context_snapshot,
        report_language,
    )
    if news_disclosure is None and isinstance(details_data, dict):
        news_disclosure = details_data.get("empty_news_disclosure")
    details = None
    has_board_details = (
        bool(extracted_boards.get("belong_boards"))
        or extracted_boards.get("sector_rankings") is not None
        or extracted_boards.get("concept_rankings") is not None
    )
    if (
        details_data
        or any(extracted_fundamental.values())
        or has_board_details
        or market_structure is not None
        or context_snapshot is not None
        or analysis_context_pack_overview is not None
        or news_disclosure is not None
    ):
        details = ReportDetails(
            news_content=details_data.get("news_summary") or details_data.get("news_content"),
            empty_news_disclosure=news_disclosure,
            raw_result=raw_result_data,
            context_snapshot=api_context_snapshot,
            analysis_context_pack_overview=analysis_context_pack_overview,
            financial_report=extracted_fundamental.get("financial_report"),
            dividend_metrics=extracted_fundamental.get("dividend_metrics"),
            belong_boards=extracted_boards.get("belong_boards"),
            sector_rankings=extracted_boards.get("sector_rankings"),
            concept_rankings=extracted_boards.get("concept_rankings"),
            market_structure=market_structure,
        )

    return AnalysisReport(
        meta=meta,
        summary=summary,
        strategy=strategy,
        details=details
    )
