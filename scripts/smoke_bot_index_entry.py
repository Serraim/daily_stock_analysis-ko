# -*- coding: utf-8 -*-
"""
=============================================
Bot 지수 입력 transport-independent 온라인 E2E smoke
=============================================

실제 ``CommandDispatcher.dispatch_async -> AnalyzeCommand ->
TaskService -> StockAnalysisPipeline`` 전체를 온라인으로 거쳐 한 종목을 분석한다.
SH_ALIAS / REGISTERED_NAME / CSI_ALIAS 세 가지 시나리오를 다루며, webhook
transport는 전혀 거치지 않는다(transport 수정 없음, 온라인 의존성 mock 없음, dry-run 없음).

실행 방법(target 인자 1개, --timeout 기본값 900초)::

    .venv\\Scripts\\python.exe scripts/smoke_bot_index_entry.py "SH.000016"
    .venv\\Scripts\\python.exe scripts/smoke_bot_index_entry.py "上证50"
    .venv\\Scripts\\python.exe scripts/smoke_bot_index_entry.py "930955.CSI"
    .venv\\Scripts\\python.exe scripts/smoke_bot_index_entry.py "SH.000016" --timeout 1800

프로세스 역할:
- 부모 프로세스: deadline, 프로세스 트리 정리, 종료 코드만 담당. worker는 콘솔을 그대로 물려받는다.
- worker: 별도 자식 프로세스(부모가 내부용 ``--worker`` flag로 직접 띄우며,
  환경 변수에 의존하지 않음). 실제 dispatcher로 제출하고 같은 프로세스 안에서
  ``TaskService``를 반복 확인하며, 한 줄짜리 ``E2E_EVENT {json}`` 이벤트를 출력한다.

이벤트 형식(한 줄 ``E2E_EVENT {json}``, phase=submitted|completed|failed|timeout,
target 포함, 단계별로 task_id / stock_code / result / error 추가):
- submitted : 작업 제출됨, ``task_id`` / ``stock_code`` 포함.
- completed : 작업 완료 및 구조 검사 통과, ``result`` 포함.
- failed    : 작업 실패, 또는 completed지만 결과가 불완전함, ``error`` 포함.
- timeout   : worker가 deadline을 넘겨 정리됨(부모 프로세스가 출력).

종료 코드: 0 = 성공, 1 = 실패(구조 검사 또는 failed 이벤트), 124 = 시간 초과.

시간 초과 정리: Windows는 ``taskkill /T /F``로 프로세스 트리 전체를 끝내고, POSIX는 프로세스 그룹에
SIGKILL을 보낸다. 시간 초과 시 프로세스 트리만 정리하며, 이미 생긴 DB / 보고서 / 알림 등은 되돌리지 않는다.

Ctrl-C 중단: 부모 프로세스가 대기 중 Ctrl-C를 받으면 똑같이 프로세스 트리부터 정리한다. 정리에 성공하면
중단을 그대로 전달하고, 실패하면 정리 오류를 담은 ``failed`` 이벤트를 출력하고 1로 종료한다.
정리 실패를 조용히 넘기는 일은 절대 없다.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_env import _reconfigure_output_stream  # noqa: E402

EVENT_PREFIX = "E2E_EVENT "

# 시나리오 입력 -> (canonical code, registered display name)의 기준 매핑.
# worker가 기대하는 code/name은 여기서만 가져온다. 응답이나 작업 결과가 스스로 밝힌 값은 믿지 않으며,
# dispatcher가 잘못 연결했는데도 통과한 것처럼 보이는 일을 막는다.
EXPECTED_OUTCOMES = {
    "SH.000016": ("sh000016", "上证50"),
    "上证50": ("sh000016", "上证50"),
    "930955.CSI": ("csi930955", "红利低波100"),
}


def _resolve_expected(target: str):
    """Return ``(expected_code, expected_name)`` for a matrix target.

    Raises ``ValueError`` for targets outside the required matrix.
    """
    try:
        return EXPECTED_OUTCOMES[target]
    except KeyError:
        raise ValueError(
            f"unsupported smoke target: {target!r} (must be one of "
            f"{sorted(EXPECTED_OUTCOMES)!r})"
        )


def _emit_event(phase: str, target: str, **fields) -> None:
    """Print one single-line ``E2E_EVENT {json}`` event to stdout."""
    payload = {"phase": phase, "target": target}
    payload.update(fields)
    print(f"{EVENT_PREFIX}{json.dumps(payload, ensure_ascii=False)}", flush=True)


def _spawn_kwargs(platform_name: str) -> dict:
    """Worker spawn kwargs: inherit the console (never ``PIPE``) and detach
    the child into its own session / new process group so the parent can
    kill the whole tree on timeout."""
    if platform_name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": creationflags} if creationflags else {}
    return {"start_new_session": True}


def _terminate_process_tree(proc, platform_name: str) -> Optional[str]:
    """Kill the whole worker process tree.

    Returns ``None`` only when tree cleanup is confirmed: a successful
    ``taskkill /T /F`` (Windows) or process-group kill (POSIX), or a
    ``ProcessLookupError`` for the tree/group (already gone). A failed tree
    cleanup returns an error string even when the direct ``proc.kill()``
    best-effort fallback succeeds — direct kill only proves the worker
    process itself was killed, not its descendants, so it never erases the
    original tree-cleanup error.
    """
    if platform_name == "nt":
        try:
            result = subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                timeout=30,
            )
            if result.returncode == 0:
                return None
            taskkill_error = f"taskkill exited {result.returncode}"
        except Exception as exc:
            taskkill_error = f"taskkill failed: {exc}"
        # Best-effort damage control: kill the worker process itself, but
        # never report a confirmed tree cleanup.
        try:
            proc.kill()
            return (
                f"{taskkill_error}; direct worker kill succeeded but "
                f"tree cleanup is unconfirmed"
            )
        except ProcessLookupError:
            return (
                f"{taskkill_error}; worker process already gone but "
                f"tree cleanup is unconfirmed"
            )
        except Exception as exc:
            return f"{taskkill_error}; direct worker kill also failed: {exc}"
    kill_signal = getattr(signal, "SIGKILL", signal.SIGTERM)
    killpg = getattr(os, "killpg", None)
    try:
        if killpg is not None:
            killpg(proc.pid, kill_signal)
        else:
            # 프로세스 그룹 기능이 없음: 바로 kill하면 worker 자신이 죽은 것만 알 수 있고
            # 자식들까지 정리됐는지는 알 수 없으므로, None을 반환해 트리 정리가 확인됐다고 하면 안 된다.
            proc.kill()
            return (
                "process-group kill unavailable; direct worker kill "
                "succeeded but tree cleanup is unconfirmed"
            )
        return None
    except ProcessLookupError:
        # The process group is already gone — confirmed success.
        return None
    except OSError as exc:
        try:
            proc.kill()
            return (
                f"process-group kill failed: {exc}; "
                f"direct worker kill succeeded but tree cleanup is unconfirmed"
            )
        except ProcessLookupError:
            return (
                f"process-group kill failed: {exc}; "
                f"worker process already gone but tree cleanup is unconfirmed"
            )
        except Exception as kill_exc:
            return (
                f"process-group kill failed: {exc}; "
                f"direct worker kill also failed: {kill_exc}"
            )


def _cleanup_process_tree(proc, platform_name: str) -> Optional[str]:
    """Terminate the worker tree and wait for the worker to exit.

    Returns ``None`` only when tree cleanup is confirmed; any terminate /
    post-cleanup wait / kill failure is merged into the returned error
    string so callers never silently claim a confirmed cleanup.
    """
    cleanup_error = _terminate_process_tree(proc, platform_name)
    # Post-cleanup handling must never escape as an uncaught exception:
    # merge any failure into ``cleanup_error``.
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception as exc:
            post_error = f"post-cleanup kill failed: {exc}"
            cleanup_error = (
                f"{cleanup_error}; {post_error}"
                if cleanup_error is not None
                else post_error
            )
    except Exception as exc:
        post_error = f"post-cleanup wait failed: {exc}"
        cleanup_error = (
            f"{cleanup_error}; {post_error}"
            if cleanup_error is not None
            else post_error
        )
    return cleanup_error


def _assert_complete_result(result: dict, expected_code: str, expected_name: str):
    """Validate a completed task result.

    Returns ``None`` on success, or a human-readable failure reason string.
    A completed task is only a success when the canonical code equals the
    authoritative expected code, the name equals the registered display
    name, and the three non-empty result fields (analysis_summary /
    operation_advice / trend_prediction) are present.
    """
    if not isinstance(result, dict):
        return "completed result is not a dict"
    if result.get("code") != expected_code:
        return (
            f"result code mismatch: expected {expected_code!r}, "
            f"got {result.get('code')!r}"
        )
    if result.get("name") != expected_name:
        return (
            f"result name mismatch: expected {expected_name!r}, "
            f"got {result.get('name')!r}"
        )
    missing = [
        key
        for key in ("analysis_summary", "operation_advice", "trend_prediction")
        if not (result.get(key) or "").strip()
    ]
    if missing:
        return f"completed result missing non-empty fields: {missing}"
    return None


def _poll_once(service, task_id: str, target: str, stock_code: str):
    """One poll of the in-process ``TaskService``.

    Empty initial state (``None`` / ``running``) returns ``None`` so the
    caller keeps waiting. Terminal states return exactly one event dict:
    ``completed`` (structure assertions passed against the authoritative
    matrix expectation) or ``failed`` (task failed or completed but
    incomplete).
    """
    expected_code, expected_name = _resolve_expected(target)
    status = service.get_task_status(task_id)
    if status is None or status.get("status") in ("running", "pending"):
        return None
    if status.get("status") == "completed":
        result = status.get("result")
        reason = _assert_complete_result(result, expected_code, expected_name)
        if reason is not None:
            return {
                "phase": "failed",
                "target": target,
                "task_id": task_id,
                "stock_code": stock_code,
                "error": reason,
            }
        return {
            "phase": "completed",
            "target": target,
            "task_id": task_id,
            "stock_code": stock_code,
            "result": result,
        }
    return {
        "phase": "failed",
        "target": target,
        "task_id": task_id,
        "stock_code": stock_code,
        "error": status.get("error") or f"task status is {status.get('status')!r}",
    }


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
def _run_worker(target: str) -> int:
    """Worker entrypoint: submit via the real dispatcher in this process and
    poll the same process's TaskService until a terminal state.

    Only exits 0 when a completed event with passing structure assertions
    was produced. Authoritative target validation runs BEFORE any dispatcher
    construction or submission, so an unsupported target can never submit.
    Unexpected exceptions from dispatch / poll / event serialization are
    converted into a ``failed`` E2E event with the exception evidence on
    stderr and exit 1 — never an uncaught traceback. ``KeyboardInterrupt``
    is not treated as an ordinary failure.
    """
    expected_code = _resolve_expected(target)[0]

    try:
        return _run_worker_inner(target, expected_code)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        _emit_event("failed", target, error=f"worker exception: {exc}")
        print(f"ERROR: worker exception: {exc}", file=sys.stderr)
        return 1


def _run_worker_inner(target: str, expected_code: str) -> int:
    """Dispatch + poll loop of the worker (see :func:`_run_worker`)."""
    from datetime import datetime

    from bot.commands.analyze import AnalyzeCommand
    from bot.dispatcher import CommandDispatcher
    from bot.models import BotMessage, ChatType
    from src.services.task_service import get_task_service

    dispatcher = CommandDispatcher()
    dispatcher.register(AnalyzeCommand())

    message = BotMessage(
        platform="smoke",
        message_id="smoke-e2e",
        user_id="smoke",
        user_name="smoke",
        chat_id="smoke",
        chat_type=ChatType.PRIVATE,
        content=f"/analyze {target}",
        raw_content=f"/analyze {target}",
        mentioned=False,
        timestamp=datetime.now(),
    )

    import asyncio

    response = asyncio.run(dispatcher.dispatch_async(message))

    # 기대값은 시나리오 매핑에서만 가져온다. ``extra.stock_code``나 작업 결과가 스스로 밝힌
    # 값은 믿지 않으므로, dispatcher가 잘못 연결하면(틀린 code/name 제출) 실패로 처리된다.
    response_code = response.extra.get("stock_code")
    response_task_id = response.extra.get("task_id")
    if response_task_id and response_code == expected_code:
        task_id = response_task_id
        _emit_event(
            "submitted",
            target,
            task_id=task_id,
            stock_code=expected_code,
        )
    elif response_task_id:
        # 작업 identity는 있지만 code가 기대값과 다름: 틀린 종목이 제출된 것이므로,
        # 성공 응답 문구 대신 분명한 mismatch 오류(기대값과 실제값 포함)와
        # 구조화된 실제 code를 출력한다.
        _emit_event(
            "failed",
            target,
            task_id=response_task_id,
            stock_code=response_code,
            error=(
                f"submitted code mismatch: expected {expected_code!r}, "
                f"got {response_code!r}"
            ),
        )
        return 1
    else:
        _emit_event("failed", target, error=response.text)
        return 1

    service = get_task_service()
    while True:
        event = _poll_once(service, task_id, target, expected_code)
        if event is not None:
            _emit_event(event["phase"], target, **{
                k: v
                for k, v in event.items()
                if k not in ("phase", "target")
            })
            return 0 if event["phase"] == "completed" else 1
        time.sleep(5)


# ---------------------------------------------------------------------------
# Parent
# ---------------------------------------------------------------------------
def _run_parent(target: str, timeout: int) -> int:
    """Parent entrypoint: spawn the worker (inheriting the console), enforce
    the deadline, clean up the process tree on timeout and on Ctrl-C, and
    map to exit codes 0 / 1 / 124. Authoritative target validation runs
    before the subprocess spawn, so an unsupported target never reaches
    ``Popen``; a non-positive timeout is rejected the same way. On Ctrl-C
    the parent cleans up the worker tree first: a confirmed cleanup
    propagates the interrupt, a failed cleanup emits a structured ``failed``
    event and returns 1."""
    _resolve_expected(target)  # raises ValueError for unsupported targets
    if timeout <= 0:
        raise ValueError(f"timeout must be positive, got {timeout}")

    # ``proc.wait`` without ``timeout`` would block SIGINT handling on
    # Windows, so poll with the deadline instead.
    child_args = [sys.executable, str(Path(__file__).resolve()), "--worker", target]
    if os.name == "nt":
        proc = subprocess.Popen(
            child_args,
            cwd=str(REPO_ROOT),
            **_spawn_kwargs("nt"),
        )
    else:
        proc = subprocess.Popen(
            child_args,
            cwd=str(REPO_ROOT),
            **_spawn_kwargs("posix"),
        )
    deadline = time.monotonic() + timeout
    while True:
        try:
            exit_code = proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            exit_code = None
        except KeyboardInterrupt:
            # 사용자가 직접 중단함: worker 프로세스 트리를 정리한다. 정리 실패를 조용히 넘기면 안 된다.
            # timeout 분기와 똑같이 구조화된 failed 이벤트를 출력하고 1을 반환해,
            # 트리가 정리된 줄 알았는데 worker 자식이 계속 실제 작업을 하는 일을 막는다.
            if proc.poll() is not None:
                # worker가 이미 스스로 종료함: 정리할 것 없이 중단을 그대로 전달.
                raise
            cleanup_error = _cleanup_process_tree(
                proc, "nt" if os.name == "nt" else "posix"
            )
            if cleanup_error is not None:
                _emit_event(
                    "failed",
                    target,
                    error=f"interrupt cleanup failed: {cleanup_error}",
                )
                return 1
            raise
        if exit_code is not None:
            # 문서에 적힌 종료 코드는 0 / 1 / 124뿐이다. worker의 다른 종료 코드는
            # 모두 1로 바꿔, 아무 크래시 코드나 밖으로 새지 않게 한다.
            if exit_code in (0, 1, 124):
                return exit_code
            return 1
        if time.monotonic() >= deadline:
            cleanup_error = _cleanup_process_tree(
                proc, "nt" if os.name == "nt" else "posix"
            )
            if cleanup_error is not None:
                # 정리에 실패했는데 성공이라고 하면 안 됨: 구조화된 failed 이벤트를 출력하고 1을 반환.
                _emit_event(
                    "failed",
                    target,
                    error=f"timeout cleanup failed: {cleanup_error}",
                )
                return 1
            _emit_event("timeout", target)
            return 124


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bot 지수 입력 transport-independent 온라인 E2E smoke: "
            "실제 dispatcher에서 Pipeline까지 거쳐 한 종목을 온라인으로 분석."
        )
    )
    parser.add_argument("target", help="시나리오 입력: SH.000016 / 上证50 / 930955.CSI")
    parser.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="worker 제한 시간(초, 기본값 900초). 시간이 넘으면 프로세스 트리를 정리하며, 이미 생긴 결과는 되돌리지 않음",
    )
    parser.add_argument(
        "--worker",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    target = (args.target or "").strip()
    if not target:
        print("ERROR: target이 비어 있으면 안 됩니다", file=sys.stderr)
        return 2

    # target 검사는 역할 분기보다 먼저 해야 한다. 지원하지 않는 target이면
    # dispatcher를 만들지도, 제출하지도, 자식 프로세스를 띄우지도 않는다(인자/입력 오류, 0이 아닌 값 반환).
    try:
        _resolve_expected(target)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # ``--timeout``은 양수여야 한다. 양수가 아니면 spawn/제출 전에 바로 거절(입력 오류).
    if args.timeout <= 0:
        print(f"ERROR: --timeout은 양의 정수여야 합니다, got {args.timeout}", file=sys.stderr)
        return 2

    _reconfigure_output_stream(sys.stdout)
    _reconfigure_output_stream(sys.stderr)

    # 역할은 명시적인 ``--worker`` flag로만 정한다(부모가 자식 프로세스를 띄울 때 직접 넘김).
    # 환경 변수에는 의존하지 않아, 밖에서 미리 넣은 환경 변수로 부모의 강제 시간 제한을 우회하지 못하게 한다.
    if args.worker:
        return _run_worker(target)
    return _run_parent(target, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
