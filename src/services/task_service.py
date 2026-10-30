# -*- coding: utf-8 -*-
"""
===================================
비동기 작업 서비스 계층
===================================

역할:
1. 비동기 분석 작업 관리(스레드 풀)
2. 종목 분석 실행 및 결과 전송
3. 작업 상태와 기록 조회

web/services.py의 AnalysisService 클래스에서 옮겨 옴
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional, Dict, Any, List, Union

from src.enums import ReportType
from src.storage import get_db
from bot.models import BotMessage
from src.services.stock_code_utils import resolve_index_stock_code_for_analysis
from src.services.stock_list_parser import AnalysisTarget, ParseStatus

logger = logging.getLogger(__name__)


class TaskService:
    """
    비동기 작업 서비스

    담당:
    1. 비동기 분석 작업 관리
    2. 종목 분석 실행
    3. 알림 전송 트리거
    """

    _instance: Optional['TaskService'] = None
    _lock = threading.Lock()

    def __init__(self, max_workers: int = 3):
        self._executor: Optional[ThreadPoolExecutor] = None
        self._max_workers = max_workers
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._tasks_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'TaskService':
        """싱글턴 인스턴스 가져오기"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @property
    def executor(self) -> ThreadPoolExecutor:
        """스레드 풀 가져오기 또는 생성"""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="analysis_"
            )
        return self._executor

    def submit_analysis(
        self,
        code: str,
        report_type: Union[ReportType, str] = ReportType.SIMPLE,
        source_message: Optional[BotMessage] = None,
        save_context_snapshot: Optional[bool] = None,
        query_source: str = "bot",
        analysis_target: Optional[AnalysisTarget] = None
    ) -> Dict[str, Any]:
        """
        비동기 분석 작업 제출

        Args:
            code: 종목 코드
            report_type: 리포트 유형 열거형
            source_message: 원본 메시지(답장용)
            save_context_snapshot: 컨텍스트 스냅샷 저장 여부
            query_source: 작업 출처 표시(bot/api/cli/system)
            analysis_target: 선택적 구조화 분석 대상(INDEX면
                ``target.canonical_id``를 그대로 쓰고 종목 코드 정규화를 건너뛰어
                ``sh000016``이 ``SH000016``으로 바뀌는 것을 막음)

        Returns:
            작업 정보 딕셔너리
        """
        # report_type이 열거형인지 확인
        if isinstance(report_type, str):
            report_type = ReportType.from_str(report_type)

        if (
            analysis_target is not None
            and analysis_target.asset_type != ParseStatus.INDEX
        ):
            raise ValueError("analysis_target must be an INDEX target")
        if analysis_target is not None:
            # INDEX target이 있으면 canonical_id를 그대로 쓰고 종목 코드
            # 정규화 경로를 타지 않는다(``sh000016``이 ``SH000016``으로 바뀌는 것 방지).
            normalized_code = analysis_target.canonical_id
        else:
            normalized_code = resolve_index_stock_code_for_analysis(code)
        if not normalized_code:
            raise ValueError("股票代码不能为空或仅包含空白字符")

        task_id = f"{normalized_code}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        # 스레드 풀에 제출
        self.executor.submit(
            self._run_analysis,
            normalized_code,
            task_id,
            report_type,
            source_message,
            save_context_snapshot,
            query_source,
            analysis_target
        )

        logger.info(
            f"[TaskService] 종목 {normalized_code} 분석 작업 제출됨, "
            f"task_id={task_id}, report_type={report_type.value}"
        )

        return {
            "success": True,
            "message": "分析任务已提交，将异步执行并推送通知",
            "code": normalized_code,
            "task_id": task_id,
            "report_type": report_type.value
        }

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """작업 상태 조회"""
        with self._tasks_lock:
            return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """최근 작업 목록"""
        with self._tasks_lock:
            tasks = list(self._tasks.values())
        # 시작 시각 내림차순
        tasks.sort(key=lambda x: x.get('start_time', ''), reverse=True)
        return tasks[:limit]

    def get_analysis_history(
        self,
        code: Optional[str] = None,
        query_id: Optional[str] = None,
        days: int = 30,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """분석 기록 조회"""
        db = get_db()
        records = db.get_analysis_history(code=code, query_id=query_id, days=days, limit=limit)
        return [r.to_dict() for r in records]

    def _run_analysis(
        self,
        code: str,
        task_id: str,
        report_type: ReportType = ReportType.SIMPLE,
        source_message: Optional[BotMessage] = None,
        save_context_snapshot: Optional[bool] = None,
        query_source: str = "bot",
        analysis_target: Optional[AnalysisTarget] = None
    ) -> Dict[str, Any]:
        """
        종목 하나 분석 실행

        내부 메서드, 스레드 풀에서 실행
        """
        # 작업 상태 초기화
        with self._tasks_lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "code": code,
                "status": "running",
                "start_time": datetime.now().isoformat(),
                "result": None,
                "error": None,
                "report_type": report_type.value
            }

        try:
            # 순환 의존을 피하려고 지연 import
            from src.config import get_config
            from main import StockAnalysisPipeline

            logger.info(f"[TaskService] 종목 분석 시작: {code}")

            # 분석 파이프라인 생성
            config = get_config()
            pipeline = StockAnalysisPipeline(
                config=config,
                max_workers=1,
                source_message=source_message,
                query_id=task_id,
                query_source=query_source,
                save_context_snapshot=save_context_snapshot
            )

            # 종목 하나 분석 실행(종목별 알림 전송 사용)
            process_kwargs = {
                "code": code,
                "skip_analysis": False,
                "single_stock_notify": True,
                "report_type": report_type,
            }
            if analysis_target is not None:
                process_kwargs["analysis_target"] = analysis_target
            result = pipeline.process_single_stock(**process_kwargs)

            if result and result.success:
                result_data = {
                    "code": result.code,
                    "name": result.name,
                    "sentiment_score": result.sentiment_score,
                    "operation_advice": result.operation_advice,
                    "trend_prediction": result.trend_prediction,
                    "analysis_summary": result.analysis_summary,
                }

                with self._tasks_lock:
                    self._tasks[task_id].update({
                        "status": "completed",
                        "end_time": datetime.now().isoformat(),
                        "result": result_data
                    })

                logger.info(f"[TaskService] 종목 {code} 분석 완료: {result.operation_advice}")
                return {"success": True, "task_id": task_id, "result": result_data}
            else:
                fail_message = "分析返回空结果"
                if result is not None:
                    fail_message = result.error_message or fail_message
                with self._tasks_lock:
                    self._tasks[task_id].update({
                        "status": "failed",
                        "end_time": datetime.now().isoformat(),
                        "error": fail_message
                    })

                logger.warning(f"[TaskService] 종목 {code} 분석 실패: {fail_message}")
                return {"success": False, "task_id": task_id, "error": fail_message}

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[TaskService] 종목 {code} 분석 오류: {error_msg}")

            with self._tasks_lock:
                self._tasks[task_id].update({
                    "status": "failed",
                    "end_time": datetime.now().isoformat(),
                    "error": error_msg
                })

            return {"success": False, "task_id": task_id, "error": error_msg}


# ============================================================
# 편의 함수
# ============================================================

def get_task_service() -> TaskService:
    """작업 서비스 싱글턴 가져오기"""
    return TaskService.get_instance()
