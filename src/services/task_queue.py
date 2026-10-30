# -*- coding: utf-8 -*-
"""
===================================
A주 관심종목 지능형 분석 시스템 - 비동기 작업 큐
===================================

역할:
1. 비동기 분석 작업의 생명주기 관리
2. 같은 종목 코드의 중복 제출 방지
3. SSE 이벤트 방송 기능 제공
4. 작업 완료 후 데이터베이스에 저장
"""

from __future__ import annotations

import asyncio
import copy
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any, TYPE_CHECKING, Tuple, Literal, Callable

if TYPE_CHECKING:
    from asyncio import Queue as AsyncQueue

from data_provider.base import canonical_stock_code, normalize_stock_code
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    get_current_diagnostic_context,
    reset_run_diagnostic_context,
)
from src.utils.analysis_metadata import SELECTION_SOURCES
from src.services.stock_code_utils import resolve_index_stock_code_for_analysis

logger = logging.getLogger(__name__)


def _dedupe_stock_code_key(stock_code: str) -> str:
    """
    Build the internal duplicate-detection key for a stock code.

    The task queue should treat equivalent market code shapes as the same
    underlying stock, e.g. ``600519`` and ``600519.SH``.
    """
    return resolve_index_stock_code_for_analysis(normalize_stock_code(stock_code))


def _dedupe_task_key(
    stock_code: str,
    analysis_target: Optional[Any] = None,
) -> str:
    """
    Build the duplicate-detection key for a submitted task.

    Index targets dedupe by their canonical id (``sh000016`` / ``csi930955``),
    so an index never collapses with a same-digit stock (``000016``) and
    registered CSI aliases converge to one key. Stock targets keep the legacy
    code-based key, preserving existing dedup semantics for
    ``600519``/``600519.SH`` and friends.
    """
    from src.services.stock_list_parser import ParseStatus

    if analysis_target is not None and analysis_target.asset_type == ParseStatus.INDEX:
        return analysis_target.canonical_id
    return _dedupe_stock_code_key(stock_code)


def asset_type_from_analysis_target(analysis_target: Optional[Any]) -> Optional[str]:
    """Derive the optional ``asset_type`` from a submitted analysis target.

    Uses the parser target only (never re-guesses from the code). Registered
    index targets (``ParseStatus.INDEX``) yield ``"index"``, explicit stock
    targets yield ``"stock"``, and targets that were not carried downstream
    (plain stock submissions, market review) yield ``None`` so the field is
    simply omitted from task payloads — keeping legacy clients compatible.
    """
    from src.services.stock_list_parser import ParseStatus

    if analysis_target is None:
        return None
    asset_type = getattr(analysis_target, "asset_type", None)
    if asset_type == ParseStatus.INDEX:
        return "index"
    if asset_type == ParseStatus.STOCK:
        return "stock"
    return None


class TaskStatus(str, Enum):
    """Task status enumeration"""
    PENDING = "pending"        # Waiting for execution
    PROCESSING = "processing"  # In progress
    COMPLETED = "completed"    # Completed
    FAILED = "failed"          # Failed
    CANCEL_REQUESTED = "cancel_requested"  # Cancellation requested
    CANCELLED = "cancelled"    # Cancelled by user/system


@dataclass
class TaskInfo:
    """
    Task information dataclass.

    Used for API responses and internal task management.
    """
    task_id: str
    stock_code: str
    stock_name: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    report_type: str = "detailed"
    analysis_phase: str = "auto"
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    original_query: Optional[str] = None
    selection_source: Optional[str] = None
    query_source: str = "api"
    portfolio_context: Optional[Dict[str, Any]] = None
    skills: Optional[List[str]] = None
    report_language: Optional[str] = None
    trace_id: Optional[str] = None
    region: Optional[str] = None
    flow_events: List[Dict[str, Any]] = field(default_factory=list)
    # 중복 제거 키 고정: submit 때 asset_type별로 미리 계산해 두고, 완료/실패로 제거할 때 그대로 쓴다.
    # 키 생성/제거가 어긋나 _analyzing_stocks에 찌꺼기가 남는 것을 막는다.
    dedupe_key: Optional[str] = None
    analysis_target: Optional[Any] = None
    # parser가 준 선택적 자산 유형(``index``/``stock``/``None``). SSE와 작업 목록은
    # 여기서 그대로 전달받으며, 사용하는 쪽에서 다시 추측하면 안 된다.
    asset_type: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task info into an API-friendly dictionary."""
        payload = {
            "task_id": self.task_id,
            "trace_id": self.trace_id or self.task_id,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "report_type": self.report_type,
            "analysis_phase": self.analysis_phase,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "original_query": self.original_query,
            "selection_source": self.selection_source,
            "skills": self.skills,
        }
        if self.region is not None:
            payload["region"] = self.region
        if self.asset_type is not None:
            payload["asset_type"] = self.asset_type
        return payload
    
    def copy(self) -> 'TaskInfo':
        """Create a shallow copy of the task information."""
        return TaskInfo(
            task_id=self.task_id,
            stock_code=self.stock_code,
            stock_name=self.stock_name,
            status=self.status,
            progress=self.progress,
            message=self.message,
            result=self.result,
            error=self.error,
            report_type=self.report_type,
            analysis_phase=self.analysis_phase,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            original_query=self.original_query,
            selection_source=self.selection_source,
            query_source=self.query_source,
            portfolio_context=dict(self.portfolio_context) if isinstance(self.portfolio_context, dict) else None,
            skills=list(self.skills) if self.skills is not None else None,
            report_language=self.report_language,
            trace_id=self.trace_id or self.task_id,
            region=self.region,
            flow_events=copy.deepcopy(self.flow_events),
            dedupe_key=self.dedupe_key,
            analysis_target=self.analysis_target,
            asset_type=self.asset_type,
        )


class DuplicateTaskError(Exception):
    """
    중복 제출 예외
    
    종목이 이미 분석 중일 때 발생한다
    """
    def __init__(self, stock_code: str, existing_task_id: str):
        self.stock_code = stock_code
        self.existing_task_id = existing_task_id
        super().__init__(f"股票 {stock_code} 正在分析中 (task_id: {existing_task_id})")


class AnalysisTaskQueue:
    """
    비동기 분석 작업 큐
    
    싱글턴 패턴, 전역에 인스턴스 하나
    
    특징:
    1. 같은 종목 코드의 중복 제출 방지
    2. 스레드 풀에서 분석 작업 실행
    3. SSE 이벤트 방송 기능
    4. 작업 완료 후 자동 저장
    """
    
    _instance: Optional['AnalysisTaskQueue'] = None
    _instance_lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, max_workers: int = 3):
        # 중복 초기화 방지
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self._max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None
        
        # 핵심 데이터 구조
        self._tasks: Dict[str, TaskInfo] = {}           # task_id -> TaskInfo
        self._analyzing_stocks: Dict[str, str] = {}     # dedupe_key -> task_id
        self._futures: Dict[str, Future] = {}           # task_id -> Future
        
        # SSE 구독자 목록(asyncio.Queue 인스턴스)
        self._subscribers: List['AsyncQueue'] = []
        self._subscribers_lock = threading.Lock()
        
        # 메인 이벤트 루프 참조(스레드 간 방송용)
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        
        # 스레드 안전 락
        self._data_lock = threading.RLock()
        
        # 메모리에 남길 작업 기록 수
        self._max_history = 100
        self._max_flow_events_per_task = 200
        
        self._initialized = True
        logger.info(f"[TaskQueue] 초기화 완료, 최대 동시 실행 수: {max_workers}")
    
    @property
    def executor(self) -> ThreadPoolExecutor:
        """스레드 풀 지연 로드"""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="analysis_task_"
            )
        return self._executor

    @property
    def max_workers(self) -> int:
        """Return current executor max worker setting."""
        return self._max_workers

    def _has_inflight_tasks_locked(self) -> bool:
        """Check whether queue has any pending/processing tasks."""
        if self._analyzing_stocks:
            return True
        return any(
            task.status in (TaskStatus.PENDING, TaskStatus.PROCESSING)
            for task in self._tasks.values()
        )

    def sync_max_workers(
        self,
        max_workers: int,
        *,
        log: bool = True,
    ) -> Literal["applied", "unchanged", "deferred_busy"]:
        """
        Try to sync queue concurrency without replacing singleton instance.

        Returns:
            - "applied": new value applied immediately (idle queue only)
            - "unchanged": target equals current value or invalid target
            - "deferred_busy": queue is busy, apply is deferred
        """
        try:
            target = max(1, int(max_workers))
        except (TypeError, ValueError):
            if log:
                logger.warning("[TaskQueue] 잘못된 MAX_WORKERS 값 무시: %r", max_workers)
            return "unchanged"

        executor_to_shutdown: Optional[ThreadPoolExecutor] = None
        previous: int
        with self._data_lock:
            previous = self._max_workers
            if target == previous:
                return "unchanged"

            if self._has_inflight_tasks_locked():
                if log:
                    logger.info(
                        "[TaskQueue] 최대 동시 실행 수 변경 보류: 현재 작업 중 (%s -> %s)",
                        previous,
                        target,
                    )
                return "deferred_busy"

            self._max_workers = target
            executor_to_shutdown = self._executor
            self._executor = None

        if executor_to_shutdown is not None:
            executor_to_shutdown.shutdown(wait=False)

        if log:
            logger.info("[TaskQueue] 최대 동시 실행 수 변경됨: %s -> %s", previous, target)
        return "applied"
    
    # ========== 작업 제출과 조회 ==========
    
    def is_analyzing(self, stock_code: str) -> bool:
        """
        종목이 분석 중인지 확인
        
        Args:
            stock_code: 종목 코드
            
        Returns:
            분석 중이면 True
        """
        dedupe_key = _dedupe_stock_code_key(stock_code)
        with self._data_lock:
            return dedupe_key in self._analyzing_stocks
    
    def get_analyzing_task_id(self, stock_code: str) -> Optional[str]:
        """
        해당 종목을 분석 중인 작업 ID 조회
        
        Args:
            stock_code: 종목 코드
            
        Returns:
            작업 ID, 없으면 None
        """
        dedupe_key = _dedupe_stock_code_key(stock_code)
        with self._data_lock:
            return self._analyzing_stocks.get(dedupe_key)

    def validate_selection_source(self, selection_source: Optional[str]) -> None:
        """
        Validate the selection source parameter.

        Args:
            selection_source: Selection source label.

        Raises:
            ValueError: Raised when the selection source is invalid.
        """
        if selection_source is not None and selection_source not in SELECTION_SOURCES:
            raise ValueError(
                f"Invalid selection_source: {selection_source}. "
                f"Must be one of {SELECTION_SOURCES}"
            )
    
    def submit_task(
        self,
        stock_code: str,
        stock_name: Optional[str] = None,
        original_query: Optional[str] = None,
        selection_source: Optional[str] = None,
        query_source: str = "api",
        portfolio_context: Optional[Dict[str, Any]] = None,
        report_type: str = "detailed",
        analysis_phase: str = "auto",
        force_refresh: bool = False,
        skills: Optional[List[str]] = None,
        report_language: Optional[str] = None,
        analysis_target: Optional[Any] = None,
    ) -> TaskInfo:
        """
        Submit a single analysis task.

        Args:
            stock_code: Stock code
            stock_name: Optional stock name
            original_query: Optional raw user input
            selection_source: Optional source label
            report_type: Report type
            analysis_phase: Requested analysis phase override
            force_refresh: Whether to bypass cache
            analysis_target: Optional structured analysis target (index targets
                dedupe by canonical id and flow through to the pipeline)

        Returns:
            TaskInfo: Accepted task information

        Raises:
            DuplicateTaskError: Raised when the stock is already being analyzed
        """
        stock_code = resolve_index_stock_code_for_analysis(stock_code)
        if not stock_code:
            raise ValueError("股票代码不能为空或仅包含空白字符")

        accepted, duplicates = self.submit_tasks_batch(
            [stock_code],
            stock_name=stock_name,
            original_query=original_query,
            selection_source=selection_source,
            query_source=query_source,
            portfolio_context=portfolio_context,
            report_type=report_type,
            analysis_phase=analysis_phase,
            force_refresh=force_refresh,
            skills=skills,
            report_language=report_language,
            analysis_targets=([analysis_target] if analysis_target is not None else None),
        )
        if duplicates:
            raise duplicates[0]
        return accepted[0]

    def submit_tasks_batch(
        self,
        stock_codes: List[str],
        stock_name: Optional[str] = None,
        original_query: Optional[str] = None,
        selection_source: Optional[str] = None,
        query_source: str = "api",
        portfolio_context: Optional[Dict[str, Any]] = None,
        report_type: str = "detailed",
        analysis_phase: str = "auto",
        force_refresh: bool = False,
        notify: bool = True,
        skills: Optional[List[str]] = None,
        report_language: Optional[str] = None,
        analysis_targets: Optional[List[Any]] = None,
    ) -> Tuple[List[TaskInfo], List[DuplicateTaskError]]:
        """
        Submit analysis tasks in batch.

        - Duplicate stocks are skipped and recorded in duplicates.
        - If executor submission fails, the current batch is rolled back.
        - ``analysis_targets`` is an optional per-code structured target list.
          Index targets dedupe by ``canonical_id`` (never collapsing with a
          same-digit stock); stock targets keep the legacy code-based key.
        """
        self.validate_selection_source(selection_source)

        accepted: List[TaskInfo] = []
        duplicates: List[DuplicateTaskError] = []
        created_task_ids: List[str] = []

        # Align per-code targets with the canonicalized code list. Index targets
        # keep their parser canonical id (lowercase ``sh000016`` / ``csi930955``)
        # so the pipeline and fetchers see the exact identity the API resolved;
        # stock codes keep the legacy canonicalization path.
        targets_by_index: Dict[int, Any] = {}
        for idx, code in enumerate(stock_codes):
            target = (
                analysis_targets[idx]
                if analysis_targets is not None and idx < len(analysis_targets)
                else None
            )
            if target is not None and getattr(target, "asset_type", None) == "index":
                targets_by_index[idx] = target

        canonical_codes = []
        for idx, code in enumerate(stock_codes):
            target = targets_by_index.get(idx)
            if target is not None:
                canonical_codes.append(target.canonical_id)
            else:
                normalized = resolve_index_stock_code_for_analysis(code)
                if normalized:
                    canonical_codes.append(normalized)

        with self._data_lock:
            for idx, stock_code in enumerate(canonical_codes):
                analysis_target = targets_by_index.get(idx)
                dedupe_key = _dedupe_task_key(stock_code, analysis_target)
                if dedupe_key in self._analyzing_stocks:
                    existing_task_id = self._analyzing_stocks[dedupe_key]
                    duplicates.append(DuplicateTaskError(stock_code, existing_task_id))
                    continue

                task_id = uuid.uuid4().hex
                task_skills = list(skills) if skills is not None else None
                task_info = TaskInfo(
                    task_id=task_id,
                    trace_id=task_id,
                    stock_code=stock_code,
                    stock_name=stock_name,
                    status=TaskStatus.PENDING,
                    message="任务已加入队列",
                    report_type=report_type,
                    analysis_phase=analysis_phase or "auto",
                    original_query=original_query,
                    selection_source=selection_source,
                    query_source=query_source or "api",
                    portfolio_context=dict(portfolio_context) if isinstance(portfolio_context, dict) else None,
                    skills=task_skills,
                    report_language=report_language,
                    dedupe_key=dedupe_key,
                    analysis_target=analysis_target,
                    asset_type=asset_type_from_analysis_target(analysis_target),
                )
                self._tasks[task_id] = task_info
                self._analyzing_stocks[dedupe_key] = task_id

                try:
                    future = self.executor.submit(
                        self._execute_task,
                        task_id,
                        stock_code,
                        report_type,
                        force_refresh,
                        notify,
                        task_skills,
                        report_language,
                        analysis_target,
                    )
                except Exception:
                    # Roll back the current batch to avoid partial submission.
                    self._rollback_submitted_tasks_locked(created_task_ids + [task_id])
                    raise

                self._futures[task_id] = future
                accepted.append(task_info)
                created_task_ids.append(task_id)
                logger.info(f"[TaskQueue] 작업 제출됨: {stock_code} -> {task_id}")

            # Keep task_created ordered before worker-emitted task_started/task_completed.
            # Broadcasting here also preserves batch rollback semantics because we only
            # reach this point after every submit in the batch has succeeded.
            for task_info in accepted:
                self._broadcast_event("task_created", task_info.to_dict())

        return accepted, duplicates

    def submit_background_task(
        self,
        run_task: Callable[[], Optional[Any]],
        *,
        stock_code: str,
        stock_name: Optional[str] = None,
        report_type: str = "detailed",
        message: Optional[str] = "任务已加入队列",
        task_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        region: Optional[str] = None,
    ) -> TaskInfo:
        """
        Submit a generic background callable with task lifecycle tracking.

        This is used by callers that need task status visibility but do not
        map to standard per-stock async analysis flow.
        """
        task_id = task_id or uuid.uuid4().hex
        task_info = TaskInfo(
            task_id=task_id,
            trace_id=trace_id or task_id,
            stock_code=stock_code,
            stock_name=stock_name,
            status=TaskStatus.PENDING,
            message=message,
            report_type=report_type,
            region=region,
        )

        with self._data_lock:
            if task_id in self._tasks:
                raise ValueError(f"작업 ID가 이미 있습니다: {task_id}")
            self._tasks[task_id] = task_info
            try:
                future = self.executor.submit(self._execute_background_task, task_id, run_task)
            except Exception:
                del self._tasks[task_id]
                raise

            self._futures[task_id] = future
            self._broadcast_event("task_created", task_info.to_dict())

        return task_info.copy()

    def _rollback_submitted_tasks_locked(self, task_ids: List[str]) -> None:
        """이번 묶음에서 만들었지만 아직 호출자에게 확실히 돌려주지 못한 작업을 되돌린다."""
        for task_id in task_ids:
            future = self._futures.pop(task_id, None)
            if future is not None:
                future.cancel()

            task = self._tasks.pop(task_id, None)
            if task:
                # submit 때 고정한 dedupe_key(있으면)를 쓴다. code로 다시 계산하면
                # 제출 경로와 어긋나 _analyzing_stocks에 찌꺼기가 남는다.
                dedupe_key = task.dedupe_key or _dedupe_task_key(
                    task.stock_code,
                    getattr(task, "analysis_target", None),
                )
                if self._analyzing_stocks.get(dedupe_key) == task_id:
                    del self._analyzing_stocks[dedupe_key]
    
    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """
        작업 정보 조회
        
        Args:
            task_id: 작업 ID
            
        Returns:
            TaskInfo 또는 None
        """
        with self._data_lock:
            task = self._tasks.get(task_id)
            return task.copy() if task else None

    def append_task_flow_event(
        self,
        task_id: str,
        flow_event: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Append a recent run-flow event to an active task and broadcast it.

        The event cache is deliberately bounded and fail-open; diagnostics must
        never affect the analysis pipeline.
        """
        try:
            event_payload = copy.deepcopy(flow_event)
        except Exception:
            logger.debug("[TaskQueue] 복사할 수 없는 실행 흐름 이벤트 무시: task_id=%s", task_id)
            return None

        with self._data_lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.flow_events.append(event_payload)
            if len(task.flow_events) > self._max_flow_events_per_task:
                task.flow_events = task.flow_events[-self._max_flow_events_per_task:]
            task_snapshot = task.copy()

        payload = task_snapshot.to_dict()
        payload["flow_event"] = event_payload
        self._broadcast_event("task_progress", payload)
        return event_payload

    def get_task_flow_events(self, task_id: str) -> List[Dict[str, Any]]:
        """Return a copy of the recent run-flow events for a task."""
        with self._data_lock:
            task = self._tasks.get(task_id)
            if not task:
                return []
            return copy.deepcopy(task.flow_events)
    
    def list_pending_tasks(self) -> List[TaskInfo]:
        """
        진행 중인 모든 작업 조회(pending + processing)
        
        Returns:
            작업 목록(사본)
        """
        with self._data_lock:
            return [
                task.copy() for task in self._tasks.values()
                if task.status in (TaskStatus.PENDING, TaskStatus.PROCESSING, TaskStatus.CANCEL_REQUESTED)
            ]
    
    def list_all_tasks(self, limit: int = 50) -> List[TaskInfo]:
        """
        모든 작업 조회(생성 시각 내림차순)
        
        Args:
            limit: 반환 개수 제한
            
        Returns:
            작업 목록(사본)
        """
        with self._data_lock:
            tasks = sorted(
                self._tasks.values(),
                key=lambda t: t.created_at,
                reverse=True
            )
            return [t.copy() for t in tasks[:limit]]
    
    def get_task_stats(self) -> Dict[str, int]:
        """
        작업 통계 조회
        
        Returns:
            통계 딕셔너리
        """
        with self._data_lock:
            stats = {
                "total": len(self._tasks),
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
            }
            for task in self._tasks.values():
                stats[task.status.value] = stats.get(task.status.value, 0) + 1
            return stats

    def update_task_progress(
        self,
        task_id: str,
        progress: int,
        message: Optional[str] = None,
        *,
        event_type: str = "task_progress",
    ) -> Optional[TaskInfo]:
        """
        Update in-flight task progress and broadcast an SSE event.

        Only pending/processing tasks are updated. Progress is clamped to
        [0, 99] so terminal states remain controlled by completion/failure.
        """
        with self._data_lock:
            task = self._tasks.get(task_id)
            if not task or task.status not in (TaskStatus.PENDING, TaskStatus.PROCESSING):
                return None

            next_progress = max(task.progress, max(0, min(99, int(progress))))
            changed = False
            if next_progress != task.progress:
                task.progress = next_progress
                changed = True
            if message is not None and message != task.message:
                task.message = message
                changed = True

            if not changed:
                return task.copy()

            task_snapshot = task.copy()

        self._broadcast_event(event_type, task_snapshot.to_dict())
        return task_snapshot
    
    # ========== 작업 실행 ==========
    
    def _execute_task(
        self,
        task_id: str,
        stock_code: str,
        report_type: str,
        force_refresh: bool,
        notify: bool = True,
        skills: Optional[List[str]] = None,
        report_language: Optional[str] = None,
        analysis_target: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        분석 작업 실행(스레드 풀에서 실행)
        
        Args:
            task_id: 작업 ID
            stock_code: 종목 코드
            report_type: 리포트 유형
            force_refresh: 강제 새로고침 여부
            analysis_target: 선택적 구조화 분석 대상(지수 대상은 pipeline으로 그대로 전달)
            
        Returns:
            분석 결과 딕셔너리
        """
        # 상태를 처리 중으로 변경
        with self._data_lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            trace_id = task.trace_id or task_id
            analysis_phase = task.analysis_phase
            query_source = task.query_source or "api"
            portfolio_context = dict(task.portfolio_context) if isinstance(task.portfolio_context, dict) else None
            task.status = TaskStatus.PROCESSING
            task.started_at = datetime.now()
            task.message = "正在分析中..."
            task.progress = 10
        
        self._broadcast_event("task_started", task.to_dict())
        
        try:
            # 분석 서비스 불러오기(순환 의존을 피하려고 지연 import)
            from src.services.analysis_service import AnalysisService
            
            # 분석 실행
            service = AnalysisService()

            def _on_progress(progress: int, message: str) -> None:
                self.update_task_progress(task_id, progress, message)

            diag_token = None
            if get_current_diagnostic_context() is None:
                diag_token = activate_run_diagnostic_context(
                    trace_id=trace_id,
                    task_id=task_id,
                    query_id=task_id,
                    stock_code=stock_code,
                    trigger_source=query_source,
                    event_sink=lambda event: self.append_task_flow_event(task_id, event),
                )
            result = service.analyze_stock(
                stock_code=stock_code,
                report_type=report_type,
                force_refresh=force_refresh,
                query_id=task_id,
                trace_id=trace_id,
                send_notification=notify,
                progress_callback=_on_progress,
                skills=skills,
                analysis_phase=analysis_phase,
                query_source=query_source,
                portfolio_context=portfolio_context,
                report_language=report_language,
                analysis_target=analysis_target,
            )
            reset_run_diagnostic_context(diag_token)
            diag_token = None
            
            if result:
                # 작업 상태를 완료로 변경
                with self._data_lock:
                    task = self._tasks.get(task_id)
                    if task:
                        task.status = TaskStatus.COMPLETED
                        task.progress = 100
                        task.completed_at = datetime.now()
                        task.result = result
                        task.message = "分析完成"
                        task.stock_name = result.get("stock_name", task.stock_name)
                        
                        # 분석 중 집합에서 제거(submit 때 고정한 key를 써서 어긋난 찌꺼기 방지)
                        dedupe_key = task.dedupe_key or _dedupe_task_key(
                            task.stock_code,
                            getattr(task, "analysis_target", None),
                        )
                        if dedupe_key in self._analyzing_stocks:
                            del self._analyzing_stocks[dedupe_key]
                
                self._broadcast_event("task_completed", task.to_dict())
                logger.info(f"[TaskQueue] 작업 완료: {task_id} ({stock_code})")
                
                # 오래된 작업 정리
                self._cleanup_old_tasks()
                
                return result
            else:
                # 분석 결과가 비어 있음
                raise Exception(service.last_error or "분석 결과가 비어 있습니다")
                
        except Exception as e:
            if "diag_token" in locals():
                reset_run_diagnostic_context(diag_token)
            error_msg = str(e)
            logger.error(f"[TaskQueue] 작업 실패: {task_id} ({stock_code}), 오류: {error_msg}")
            
            with self._data_lock:
                task = self._tasks.get(task_id)
                if task:
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now()
                    task.error = error_msg[:200]  # 오류 메시지 길이 제한
                    task.message = f"分析失败: {error_msg[:50]}"
                    
                    # 분석 중 집합에서 제거(submit 때 고정한 key를 써서 어긋난 찌꺼기 방지)
                    dedupe_key = task.dedupe_key or _dedupe_task_key(
                        task.stock_code,
                        getattr(task, "analysis_target", None),
                    )
                    if dedupe_key in self._analyzing_stocks:
                        del self._analyzing_stocks[dedupe_key]
            
            self._broadcast_event("task_failed", task.to_dict())
            
            # 오래된 작업 정리
            self._cleanup_old_tasks()
            
            return None

    def _execute_background_task(
        self,
        task_id: str,
        run_task: Callable[[], Optional[Dict[str, Any]]],
    ) -> Optional[Dict[str, Any]]:
        """
        일반 백그라운드 작업 실행(사용자 정의 실행 로직 지원)

        Args:
            task_id: 작업 ID
            run_task: 작업 실행 함수

        Returns:
            작업 실행 결과 딕셔너리(선택)
        """
        with self._data_lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            trace_id = task.trace_id or task_id
            task.status = TaskStatus.PROCESSING
            task.started_at = datetime.now()
            task.message = "任务执行中"
            task.progress = 10
            self._broadcast_event("task_started", task.to_dict())

        try:
            diag_token = None
            if get_current_diagnostic_context() is None:
                diag_token = activate_run_diagnostic_context(
                    trace_id=trace_id,
                    task_id=task_id,
                    query_id=task_id,
                    stock_code=task.stock_code,
                    trigger_source="api",
                    event_sink=lambda event: self.append_task_flow_event(task_id, event),
                )
            try:
                result = run_task()
            finally:
                reset_run_diagnostic_context(diag_token)
            if result is None:
                raise RuntimeError("작업 결과가 비어 있어 저장할 내용이 만들어지지 않았습니다")

            with self._data_lock:
                task = self._tasks.get(task_id)
                if task:
                    task.status = TaskStatus.COMPLETED
                    task.progress = 100
                    task.completed_at = datetime.now()
                    task.result = result
                    task.message = "任务执行完成"

            self._broadcast_event("task_completed", task.to_dict())
            logger.info(f"[TaskQueue] 사용자 정의 작업 완료: {task_id}")

            self._cleanup_old_tasks()
            return result

        except Exception as e:  # pragma: no cover - behavior verified in downstream tests
            error_msg = str(e)
            logger.error(
                f"[TaskQueue] 사용자 정의 작업 실패: {task_id}, 오류: {error_msg}"
            )

            with self._data_lock:
                task = self._tasks.get(task_id)
                if task:
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now()
                    task.error = error_msg[:200]
                    task.message = f"任务失败: {error_msg[:80]}"

            if task:
                self._broadcast_event("task_failed", task.to_dict())

            self._cleanup_old_tasks()
            return None
    
    def _cleanup_old_tasks(self) -> int:
        """
        끝난 지 오래된 작업 정리
        
        최근 _max_history개 작업만 남긴다
        
        Returns:
            정리한 작업 수
        """
        with self._data_lock:
            if len(self._tasks) <= self._max_history:
                return 0
            
            # 시간순으로 정렬해 오래된 완료 작업 삭제
            completed_tasks = sorted(
                [t for t in self._tasks.values()
                 if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)],
                key=lambda t: t.created_at
            )
            
            to_remove = len(self._tasks) - self._max_history
            removed = 0
            
            for task in completed_tasks[:to_remove]:
                del self._tasks[task.task_id]
                if task.task_id in self._futures:
                    del self._futures[task.task_id]
                removed += 1
            
            if removed > 0:
                logger.debug(f"[TaskQueue] 오래된 작업 {removed}개 정리")
            
            return removed
    
    # ========== SSE 이벤트 방송 ==========
    
    def subscribe(self, queue: 'AsyncQueue') -> None:
        """
        작업 이벤트 구독
        
        Args:
            queue: 이벤트를 받을 asyncio.Queue 인스턴스
        """
        with self._subscribers_lock:
            self._subscribers.append(queue)
            # 현재 이벤트 루프 저장(메인 스레드의 async 컨텍스트에서 호출해야 함)
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError:
                # async 컨텍스트가 아니면 이벤트 루프 가져오기를 시도
                try:
                    self._main_loop = asyncio.get_event_loop()
                except RuntimeError:
                    pass
            logger.debug(f"[TaskQueue] 새 구독자 추가, 현재 구독자 수: {len(self._subscribers)}")
    
    def unsubscribe(self, queue: 'AsyncQueue') -> None:
        """
        작업 이벤트 구독 해제
        
        Args:
            queue: 구독을 해제할 asyncio.Queue 인스턴스
        """
        with self._subscribers_lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)
                logger.debug(f"[TaskQueue] 구독자 나감, 현재 구독자 수: {len(self._subscribers)}")
    
    def _broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        모든 구독자에게 이벤트 방송
        
        call_soon_threadsafe로 스레드 간 안전 보장
        
        Args:
            event_type: 이벤트 유형
            data: 이벤트 데이터
        """
        event = {"type": event_type, "data": data}
        
        with self._subscribers_lock:
            subscribers = self._subscribers.copy()
            loop = self._main_loop
        
        if not subscribers:
            return
        
        if loop is None:
            logger.warning("[TaskQueue] 이벤트 방송 불가: 메인 이벤트 루프가 설정되지 않음")
            return
        
        for queue in subscribers:
            try:
                # call_soon_threadsafe로 이벤트를 asyncio 큐에 넣는다
                # 작업 스레드에서 메인 이벤트 루프로 메시지를 보내는 안전한 방법이다
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError as e:
                # 이벤트 루프가 이미 닫힘
                logger.debug(f"[TaskQueue] 이벤트 방송 건너뜀(루프 닫힘): {e}")
            except Exception as e:
                logger.warning(f"[TaskQueue] 이벤트 방송 실패: {e}")
    
    # ========== 정리 메서드 ==========
    
    def shutdown(self) -> None:
        """작업 큐 종료"""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None
            logger.info("[TaskQueue] 스레드 풀 종료됨")


# ========== 편의 함수 ==========

def get_task_queue() -> AnalysisTaskQueue:
    """
    작업 큐 싱글턴 가져오기
    
    Returns:
        AnalysisTaskQueue 인스턴스
    """
    queue = AnalysisTaskQueue()
    try:
        from src.config import get_config

        config = get_config()
        target_workers = max(1, int(getattr(config, "max_workers", queue.max_workers)))
        queue.sync_max_workers(target_workers, log=False)
    except Exception as exc:
        logger.debug("[TaskQueue] MAX_WORKERS 읽기 실패, 현재 동시 실행 설정 사용: %s", exc)

    return queue
