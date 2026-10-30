# -*- coding: utf-8 -*-
"""Agent 실행 중 실제로 사용한 뉴스 근거 건수.

empty-news disclosure는 "이번 분석이 정말 사용한 뉴스 근거"를 반영해야 한다. Agent 모드에서는 정보를
Agent가 직접 검색 도구를 호출해 얻으므로, 건수는 이 도구들의 실제 반환값에서만 나와야 한다. 분석이
끝난 뒤 따로 한 번 호출하는 `search_stock_news()`로 대신하면 안 된다: 그 추가 조회는 Agent가 쓴 근거와 무관해서
양쪽 모두 틀어진다 — Agent가 뉴스를 썼는데 추가 조회가 실패해 "뉴스 근거 미포함"으로 표시되거나,
Agent가 뉴스를 못 얻었는데 추가 조회에 결과가 있어 안내가 잘못 빠진다.

사용법: pipeline이 `executor.run()` 앞뒤로 범위를 열고 읽는다. 검색 도구는 결과를 반환할 때
이번에 실제로 Agent에게 넘긴 건수를 기록한다. 도구는 ThreadPoolExecutor에서 실행되고
`src/agent/runner.py`가 `contextvars.copy_context()`로 작업을 제출하므로, ContextVar 안의
**가변** 누적기는 작업 스레드와 부모 스레드에서 같은 객체다. 그래서 도구 스레드에서 누적한 값이
pipeline에 보인다. 불변 값을 담는 ContextVar로 바꾸지 말 것. 그러면 부모 스레드가 읽지 못한다.
"""

from __future__ import annotations

import logging
import threading
from contextvars import ContextVar, Token
from typing import Optional

logger = logging.getLogger(__name__)


class NewsEvidenceAccumulator:
    """Agent가 이번 분석에서 실제로 사용한 뉴스 건수를 스레드 안전하게 누적한다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total = 0

    def record(self, count: int) -> None:
        """검색 도구가 실제로 반환한 건수를 한 번 기록한다. 0건이어도 반드시 기록한다(0으로)."""
        try:
            value = int(count)
        except (TypeError, ValueError):
            value = 0
        if value < 0:
            value = 0
        with self._lock:
            self._total += value

    @property
    def total(self) -> int:
        with self._lock:
            return self._total

    def resolve(self, *, search_available: bool) -> Optional[int]:
        """`news_result_count`의 세 가지 상태로 정리한다.

        - 검색 채널 사용 불가: `None`, 즉 검색을 안 함. "검색 채널 미설정"으로 안내.
        - 채널 사용 가능: `0`부터 시작해 Agent가 도구로 얻은 만큼 센다.

        채널은 쓸 수 있는데 Agent가 한 번도 검색하지 않은 경우는 일부러 `None`이 아닌 `0`으로 둔다: 이때 리포트에는
        정말 뉴스 근거가 없지만 "검색 채널 미설정"은 사실과 반대되는 설명이고, "쓸 수 있는
        뉴스 데이터를 얻지 못함"은 두 경우 모두에 맞는다.
        """
        if not search_available:
            return None
        return self.total


_CURRENT_ACCUMULATOR: ContextVar[Optional[NewsEvidenceAccumulator]] = ContextVar(
    "news_evidence_accumulator",
    default=None,
)


def activate_news_evidence_scope() -> Token:
    """Agent 실행 한 번의 근거 범위를 열고, 되돌리기 토큰을 반환한다."""
    return _CURRENT_ACCUMULATOR.set(NewsEvidenceAccumulator())


def get_current_news_evidence() -> Optional[NewsEvidenceAccumulator]:
    return _CURRENT_ACCUMULATOR.get()


def reset_news_evidence_scope(token: Optional[Token]) -> None:
    if token is None:
        return
    try:
        _CURRENT_ACCUMULATOR.reset(token)
    except Exception as exc:  # pragma: no cover - 방어적 fail-open
        logger.warning("news evidence scope reset failed: %s", exc)


def record_news_evidence(count: int) -> None:
    """Agent 검색 도구가 호출한다.

    활성 범위가 없으면 조용히 무시한다: Agent가 아닌 경로는 건수를 직접 관리하고, 도구가
    Agent 분석 밖에서 호출될 수도 있다(예: 리포트 페이지의 후속 뉴스 검색). 이런 호출은 이번 분석의
    안내 판단에 영향을 주면 안 된다.
    """
    accumulator = _CURRENT_ACCUMULATOR.get()
    if accumulator is None:
        return
    accumulator.record(count)
