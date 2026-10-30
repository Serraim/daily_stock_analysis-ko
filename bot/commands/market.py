# -*- coding: utf-8 -*-
"""
===================================
시장 복기 명령
===================================

시장 전체 복기 분석을 실행하고 시장 개요 보고서를 만듭니다.
"""

import logging
import threading
from typing import Any, List, Optional

from bot.commands.base import BotCommand
from bot.models import BotMessage, BotResponse

logger = logging.getLogger(__name__)


class MarketCommand(BotCommand):
    """
    시장 복기 명령

    시장 전체 복기 분석을 실행합니다. 포함 내용:
    - 주요 지수 흐름
    - 업종별 이슈
    - 시장 심리
    - 향후 전망

    사용법:
        /market - 시장 복기 실행
    """

    @property
    def name(self) -> str:
        return "market"

    @property
    def aliases(self) -> List[str]:
        return ["m", "大盘", "复盘", "行情"]

    @property
    def description(self) -> str:
        return "시장 전체 복기 분석"

    @property
    def usage(self) -> str:
        return "/market"

    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """시장 복기 명령 실행"""
        config = self._get_config()
        lock_token = self._try_acquire_market_review_lock(config)
        if lock_token is None:
            return BotResponse.markdown_response("⚠️ 시장 복기가 이미 실행 중입니다. 잠시 후 다시 시도해 주세요.")

        thread = threading.Thread(
            target=self._run_market_review,
            args=(message, config, lock_token),
            daemon=True,
        )
        try:
            thread.start()
        except Exception as exc:
            logger.error(
                "[MarketCommand] 시장 복기 백그라운드 스레드 시작 실패: %s",
                exc,
            )
            self._release_market_review_lock(lock_token)
            return BotResponse.error_response(
                "大盘复盘启动失败，已释放运行锁；请稍后重试"
            )

        return BotResponse.markdown_response(
            "✅ **시장 복기 작업을 시작했습니다**\n\n"
            "분석 중:\n"
            "• 주요 지수 흐름\n"
            "• 업종별 이슈 분석\n"
            "• 시장 심리 판단\n"
            "• 향후 전망\n\n"
            "분석이 끝나면 결과를 자동으로 보내 드립니다."
        )

    def _get_config(self):
        from src.config import get_config
        return get_config()

    def _try_acquire_market_review_lock(self, config):
        from src.core.market_review_lock import try_acquire_market_review_lock
        return try_acquire_market_review_lock(config)

    def _release_market_review_lock(self, lock_token: Optional[Any]) -> None:
        from src.core.market_review_lock import release_market_review_lock
        release_market_review_lock(lock_token)

    def _compute_market_review_override_region(self, config) -> Optional[str]:
        if not getattr(config, "trading_day_check_enabled", True):
            return None

        try:
            from src.core.trading_calendar import (
                get_open_markets_today,
                compute_effective_region,
            )

            open_markets = get_open_markets_today()
            return compute_effective_region(
                getattr(config, "market_review_region", "cn") or "cn",
                open_markets,
            )
        except Exception as exc:
            logger.warning("거래일 확인 실패, 설정대로 시장 복기를 계속 진행: %s", exc)
            return None

    def _run_market_review(
        self,
        message: BotMessage,
        config,
        lock_token: Optional[Any],
    ) -> None:
        """백그라운드에서 시장 복기 실행"""
        try:
            override_region = self._compute_market_review_override_region(config)
            if override_region == "":
                from src.notification import NotificationService
                notifier = NotificationService(source_message=message)
                logger.info("[MarketCommand] 오늘 해당 시장 휴장, 시장 복기 건너뜀")
                if notifier.is_available():
                    notifier.send(
                        "🎯 大盘复盘\n\n今日相关市场休市，已跳过大盘复盘。",
                        email_send_to_all=True,
                        route_type="report",
                    )
                return

            from src.core.market_review_runtime import build_market_review_runtime
            from src.core.market_review import run_market_review

            notifier, analyzer, search_service = build_market_review_runtime(
                config,
                source_message=message,
            )
            review_report = run_market_review(
                notifier=notifier,
                analyzer=analyzer,
                search_service=search_service,
                send_notification=True,
                override_region=override_region,
                trigger_source="bot",
            )
            if review_report:
                logger.info("[MarketCommand] 시장 복기 완료, 발송함")
            else:
                logger.warning("[MarketCommand] 시장 복기 결과가 비어 있음")
        except Exception as e:
            logger.error("[MarketCommand] 시장 복기 실패: %s", e)
            logger.exception(e)
        finally:
            self._release_market_review_lock(lock_token)
