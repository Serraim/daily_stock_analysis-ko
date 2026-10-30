# -*- coding: utf-8 -*-
"""
===================================
예약 실행(스케줄러) 모듈
===================================

역할:
1. 매일 정해진 시간에 종목 분석 실행
2. 정해진 시간에 시장 전체 복기 실행
3. 종료 신호를 깔끔하게 처리해 안전하게 종료

의존성:
- schedule: 가벼운 예약 작업 라이브러리
"""

import logging
import re
import signal
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

logger = logging.getLogger(__name__)


def normalize_schedule_times(
    schedule_times: Optional[Union[Sequence[str], str]],
    *,
    fallback_time: str = "18:00",
) -> List[str]:
    """Return sorted unique HH:MM schedule times with SCHEDULE_TIME fallback."""
    if isinstance(schedule_times, str):
        raw_items = [item.strip() for item in schedule_times.split(",")]
    elif schedule_times is None:
        raw_items = []
    else:
        raw_items = [str(item).strip() for item in schedule_times]

    valid = {
        item
        for item in raw_items
        if item and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item)
    }
    if not valid:
        fallback = (fallback_time or "18:00").strip() or "18:00"
        valid.add(fallback if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", fallback) else "18:00")
    return sorted(valid)


class GracefulShutdown:
    """
    안전 종료 처리기

    SIGTERM/SIGINT 신호를 받으면 진행 중인 작업이 끝난 뒤 종료
    """

    def __init__(self, register_signals: bool = True):
        self.shutdown_requested = False
        self._lock = threading.Lock()
        if not register_signals:
            return

        # 신호 처리기 등록
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """신호 처리 함수"""
        with self._lock:
            if not self.shutdown_requested:
                logger.info(f"종료 신호 수신 ({signum}), 현재 작업이 끝날 때까지 대기...")
                self.shutdown_requested = True

    @property
    def should_shutdown(self) -> bool:
        """종료해야 하는지 확인"""
        with self._lock:
            return self.shutdown_requested


class Scheduler:
    """
    예약 작업 스케줄러

    schedule 라이브러리 기반, 지원 기능:
    - 매일 정해진 시간에 실행
    - 시작 시 즉시 실행
    - 안전 종료
    """

    def __init__(
        self,
        schedule_time: str = "18:00",
        schedule_time_provider: Optional[Callable[[], str]] = None,
        schedule_times: Optional[Sequence[str]] = None,
        schedule_times_provider: Optional[Callable[[], Union[Sequence[str], str]]] = None,
        register_signals: bool = True,
        pass_scheduled_for: bool = False,
    ):
        """
        스케줄러 초기화

        Args:
            schedule_time: 매일 실행 시각, 형식 "HH:MM"
        """
        try:
            import schedule
            self.schedule = schedule
        except ImportError:
            logger.error("schedule 라이브러리가 설치되지 않았습니다. 실행: pip install schedule")
            raise ImportError("schedule 라이브러리를 설치하세요: pip install schedule")

        self.schedule_time = schedule_time
        self.schedule_times = (
            normalize_schedule_times(schedule_times, fallback_time=schedule_time)
            if schedule_times is not None
            else [(schedule_time or "").strip()]
        )
        self._schedule_time_provider = schedule_time_provider
        self._schedule_times_provider = schedule_times_provider
        self.shutdown_handler = GracefulShutdown(register_signals=register_signals)
        self._task_callback: Optional[Callable] = None
        self._pass_scheduled_for = pass_scheduled_for
        self._daily_job: Optional[Any] = None
        self._daily_jobs: List[Any] = []
        self._background_tasks: List[Dict[str, Any]] = []
        self._lifecycle_lock = threading.Lock()
        self._running = False
        self._stop_requested = False

    def set_daily_task(self, task: Callable, run_immediately: bool = True):
        """
        매일 실행할 예약 작업 설정

        Args:
            task: 실행할 작업 함수(인자 없음)
            run_immediately: 설정 직후 한 번 바로 실행할지 여부
        """
        self._task_callback = task
        if not self._configure_daily_tasks(self.schedule_times):
            raise ValueError(f"잘못된 예약 실행 시각: {self.schedule_time!r}")

        if run_immediately:
            logger.info("작업을 지금 한 번 실행...")
            self._safe_run_task()

    @staticmethod
    def _is_valid_schedule_time(schedule_time: str) -> bool:
        """Validate time string in HH:MM 24-hour format."""
        candidate = (schedule_time or "").strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", candidate):
            return False
        return True

    def _cancel_daily_job(self) -> None:
        """Remove the currently registered daily job if one exists."""
        if self._daily_job is None and not self._daily_jobs:
            return

        for job in list(self._daily_jobs or [self._daily_job]):
            if job is None:
                continue
            if hasattr(self.schedule, "cancel_job"):
                self.schedule.cancel_job(job)
            else:  # pragma: no cover - compatibility fallback
                jobs = getattr(self.schedule, "jobs", None)
                if isinstance(jobs, list) and job in jobs:
                    jobs.remove(job)

        self._daily_job = None
        self._daily_jobs = []

    def _register_daily_job(self, schedule_time: str) -> Any:
        job = self.schedule.every().day.at(schedule_time)
        # schedule updates next_run after the callback, so preserve the original
        # due date/time through delayed polling and asynchronous dispatch.
        return job.do(lambda: self._safe_run_task(scheduled_for=job.next_run))

    def _configure_daily_task(self, schedule_time: str) -> bool:
        """(Re)register the daily job at the requested time."""
        candidate = (schedule_time or "").strip()
        if not self._is_valid_schedule_time(candidate):
            logger.warning(
                "잘못된 예약 실행 시각 %r 감지, 기존 시각 %s 유지",
                schedule_time,
                self.schedule_time,
            )
            return False

        previous_time = self.schedule_time
        self._cancel_daily_job()
        self._daily_job = self._register_daily_job(candidate)
        self.schedule_time = candidate

        if previous_time == candidate:
            logger.info("매일 예약 작업 설정됨, 실행 시각: %s", self.schedule_time)
        else:
            logger.info(
                "SCHEDULE_TIME 변경 감지, 매일 예약 작업을 %s 에서 %s 로 변경함",
                previous_time,
                self.schedule_time,
            )
        return True

    def _refresh_daily_schedule_if_needed(self) -> None:
        """Reload daily schedule time from the latest runtime config if needed."""
        if self._task_callback is None or self._schedule_time_provider is None:
            return

        try:
            latest_schedule_time = (self._schedule_time_provider() or "").strip()
        except Exception as exc:  # pragma: no cover - defensive branch
            logger.warning("최신 SCHEDULE_TIME 읽기 실패, 기존 %s 유지: %s", self.schedule_time, exc)
            return

        if not latest_schedule_time or latest_schedule_time == self.schedule_time:
            return

        if self._configure_daily_task(latest_schedule_time):
            logger.info("변경 후 다음 실행 시각: %s", self._get_next_run_time())

    def _configure_daily_tasks(self, schedule_times: Union[Sequence[str], str]) -> bool:
        """(Re)register daily jobs at the requested times."""
        raw_items = (
            [item.strip() for item in schedule_times.split(",")]
            if isinstance(schedule_times, str)
            else [str(item).strip() for item in schedule_times]
        )
        invalid_items = [item for item in raw_items if item and not self._is_valid_schedule_time(item)]
        if invalid_items:
            logger.warning(
                "Invalid schedule time values %r; keeping current times %s",
                invalid_items,
                ",".join(self.schedule_times),
            )
            return False

        candidates = normalize_schedule_times(raw_items, fallback_time=self.schedule_time)
        previous_times = list(self.schedule_times)
        self._cancel_daily_job()
        self._daily_jobs = [
            self._register_daily_job(candidate)
            for candidate in candidates
        ]
        self._daily_job = self._daily_jobs[0] if self._daily_jobs else None
        self.schedule_times = candidates
        self.schedule_time = candidates[0] if candidates else "18:00"

        if previous_times == candidates:
            logger.info("Daily scheduled jobs configured at: %s", ",".join(self.schedule_times))
        else:
            logger.info(
                "Schedule times changed from %s to %s",
                ",".join(previous_times),
                ",".join(self.schedule_times),
            )
        return True

    def _refresh_daily_schedule_if_needed(self) -> None:
        """Reload daily schedule times from the latest runtime config if needed."""
        if self._task_callback is None:
            return

        try:
            if self._schedule_times_provider is not None:
                latest_schedule_times = self._schedule_times_provider()
            elif self._schedule_time_provider is not None:
                latest_schedule_times = [(self._schedule_time_provider() or "").strip()]
            else:
                return
        except Exception as exc:  # pragma: no cover - defensive branch
            logger.warning(
                "Failed to read latest schedule times; keeping %s: %s",
                ",".join(self.schedule_times),
                exc,
            )
            return

        latest = normalize_schedule_times(latest_schedule_times, fallback_time=self.schedule_time)
        if latest == self.schedule_times:
            return

        if self._configure_daily_tasks(latest):
            logger.info("Schedule refreshed; next run: %s", self._get_next_run_time())

    def refresh_daily_schedule_if_needed(self) -> None:
        """Public wrapper for runtime scheduler reconciliation."""
        self._refresh_daily_schedule_if_needed()

    def _safe_run_task(self, scheduled_for: Optional[datetime] = None):
        """작업을 안전하게 실행(예외 처리 포함)"""
        if self._task_callback is None:
            return

        try:
            logger.info("=" * 50)
            logger.info(f"예약 작업 시작 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 50)

            if self._pass_scheduled_for:
                self._task_callback(scheduled_for=scheduled_for)
            else:
                self._task_callback()

            logger.info(f"예약 작업 완료 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        except Exception as e:
            logger.exception(f"예약 작업 실패: {e}")

    def add_background_task(
        self,
        task: Callable,
        interval_seconds: int,
        run_immediately: bool = False,
        name: Optional[str] = None,
    ) -> None:
        """Register a periodic background task executed inside the scheduler loop.

        Note: The scheduler loop polls every 30 seconds, so *interval_seconds*
        below 30 will be clamped to 30 to avoid promising unreachable precision.
        """
        clamped_interval = max(30, int(interval_seconds))
        if int(interval_seconds) < 30:
            logger.warning(
                "백그라운드 작업 %s 의 요청 간격은 %ds 이지만 스케줄러는 30초마다 확인하므로 30초로 자동 조정함",
                name or getattr(task, "__name__", "background_task"),
                interval_seconds,
            )
        entry = {
            "task": task,
            "interval_seconds": clamped_interval,
            "last_run": 0.0,
            "name": name or getattr(task, "__name__", "background_task"),
            "thread": None,
            "running": False,
        }
        if not run_immediately:
            entry["last_run"] = time.time()
        self._background_tasks.append(entry)
        logger.info(
            "백그라운드 작업 등록됨: %s (간격 %s초, 즉시 실행=%s)",
            entry["name"],
            entry["interval_seconds"],
            run_immediately,
        )
        if run_immediately:
            self._start_background_task(entry)

    def _start_background_task(self, entry: Dict[str, Any]) -> bool:
        """Start one background task in a dedicated daemon thread."""
        worker = entry.get("thread")
        if worker is not None and worker.is_alive():
            return False

        def _runner() -> None:
            try:
                logger.info("백그라운드 작업 시작: %s", entry["name"])
                entry["task"]()
            except Exception as exc:
                logger.exception("백그라운드 작업 실패 [%s]: %s", entry["name"], exc)
            finally:
                entry["running"] = False
                entry["thread"] = None

        entry["last_run"] = time.time()
        entry["running"] = True
        worker = threading.Thread(
            target=_runner,
            daemon=True,
            name=f"scheduler-bg-{entry['name']}",
        )
        entry["thread"] = worker
        worker.start()
        return True

    def _run_background_tasks(self) -> None:
        """Execute any background tasks whose interval has elapsed."""
        if not self._background_tasks:
            return

        now = time.time()
        for entry in self._background_tasks:
            worker = entry.get("thread")
            if worker is not None and worker.is_alive():
                continue
            if entry.get("running"):
                entry["running"] = False
                entry["thread"] = None
            if now - entry["last_run"] < entry["interval_seconds"]:
                continue
            self._start_background_task(entry)

    def _dispatch_background_tasks_if_running(self) -> bool:
        """Dispatch due background tasks before a concurrent stop can return."""
        with self._lifecycle_lock:
            if not self._running or self.shutdown_handler.should_shutdown:
                return False
            self._run_background_tasks()
            return True

    def run(self):
        """
        스케줄러 메인 루프 실행

        종료 신호를 받을 때까지 계속 실행(블로킹)
        """
        with self._lifecycle_lock:
            if self._stop_requested:
                logger.info("스케줄러가 이미 멈춤, 늦게 들어온 시작 요청은 무시")
                return
            self._running = True
        logger.info("스케줄러 실행 시작...")
        logger.info(f"다음 실행 시각: {self._get_next_run_time()}")

        while self._running and not self.shutdown_handler.should_shutdown:
            self._refresh_daily_schedule_if_needed()
            self.schedule.run_pending()
            if not self._dispatch_background_tasks_if_running():
                break
            time.sleep(30)  # 30초마다 확인

            # 1시간마다 동작 확인 로그 출력
            if datetime.now().minute == 0 and datetime.now().second < 30:
                logger.info(f"스케줄러 실행 중... 다음 실행: {self._get_next_run_time()}")

        logger.info("스케줄러 멈춤")

    def _get_next_run_time(self) -> str:
        """다음 실행 시각 가져오기"""
        jobs = self.schedule.get_jobs()
        if jobs:
            next_run = min(job.next_run for job in jobs)
            return next_run.strftime('%Y-%m-%d %H:%M:%S')
        return "설정 안 됨"

    def stop(self):
        """스케줄러 멈추기"""
        with self._lifecycle_lock:
            self._stop_requested = True
            self._running = False
        self._cancel_daily_job()


def run_with_schedule(
    task: Callable,
    schedule_time: str = "18:00",
    run_immediately: bool = True,
    background_tasks: Optional[List[Dict[str, Any]]] = None,
    schedule_time_provider: Optional[Callable[[], str]] = None,
    schedule_times: Optional[Sequence[str]] = None,
    schedule_times_provider: Optional[Callable[[], Union[Sequence[str], str]]] = None,
    pass_scheduled_for: bool = False,
):
    """
    편의 함수: 예약 실행으로 작업 돌리기

    Args:
        task: 실행할 작업 함수
        schedule_time: 매일 실행 시각
        run_immediately: 바로 한 번 실행할지 여부
        background_tasks: 선택 사항인 백그라운드 작업 정의 목록. 각 항목은 딕셔너리이며
            `task` 와 `interval_seconds` 는 필수, `name` 과
            `run_immediately` 는 선택. `interval_seconds` 단위는 초.
        schedule_time_provider: 선택 사항인 시각 제공 함수. 스케줄러가 매번 확인 전에 읽고,
            값이 바뀌면 daily job 을 자동으로 다시 만든다.
    """
    scheduler_kwargs: Dict[str, Any] = {
        "schedule_time": schedule_time,
        "schedule_time_provider": schedule_time_provider,
    }
    if schedule_times is not None:
        scheduler_kwargs["schedule_times"] = schedule_times
    if schedule_times_provider is not None:
        scheduler_kwargs["schedule_times_provider"] = schedule_times_provider
    if pass_scheduled_for:
        scheduler_kwargs["pass_scheduled_for"] = True
    scheduler = Scheduler(**scheduler_kwargs)
    for entry in background_tasks or []:
        scheduler.add_background_task(
            task=entry["task"],
            interval_seconds=entry["interval_seconds"],
            run_immediately=entry.get("run_immediately", False),
            name=entry.get("name"),
        )
    scheduler.set_daily_task(task, run_immediately=run_immediately)
    scheduler.run()


if __name__ == "__main__":
    # 예약 실행 테스트
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    )

    def test_task():
        print(f"작업 실행 중... {datetime.now()}")
        time.sleep(2)
        print("작업 완료!")

    print("테스트 스케줄러 시작 (Ctrl+C 로 종료)")
    run_with_schedule(test_task, schedule_time="23:59", run_immediately=True)
