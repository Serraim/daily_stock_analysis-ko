# -*- coding: utf-8 -*-
"""
===================================
Bot Webhook 처리기
===================================

각 플랫폼의 Webhook 콜백을 받아 명령 처리기로 넘깁니다.
"""

import asyncio
import json
import logging
import threading
from typing import Dict, Optional, TYPE_CHECKING

from bot.models import WebhookResponse
from bot.dispatcher import get_dispatcher
from bot.platforms import ALL_PLATFORMS

if TYPE_CHECKING:
    from bot.platforms.base import BotPlatform  # noqa: F401

logger = logging.getLogger(__name__)

# 플랫폼 인스턴스 캐시
_platform_instances: Dict[str, 'BotPlatform'] = {}


def get_platform(platform_name: str) -> Optional['BotPlatform']:
    """
    플랫폼 어댑터 인스턴스 가져오기

    캐시를 써서 중복 생성을 피합니다.

    Args:
        platform_name: 플랫폼 이름

    Returns:
        플랫폼 어댑터 인스턴스 또는 None
    """
    if platform_name not in _platform_instances:
        platform_class = ALL_PLATFORMS.get(platform_name)
        if platform_class:
            _platform_instances[platform_name] = platform_class()
        else:
            logger.warning(f"[BotHandler] 알 수 없는 플랫폼: {platform_name}")
            return None

    return _platform_instances[platform_name]


def handle_webhook(
    platform_name: str,
    headers: Dict[str, str],
    body: bytes,
    query_params: Optional[Dict[str, list]] = None
) -> WebhookResponse:
    """
    Webhook 요청 처리

    모든 플랫폼 Webhook의 공통 입구입니다.

    Args:
        platform_name: 플랫폼 이름 (feishu, dingtalk, wecom, telegram)
        headers: HTTP 요청 헤더
        body: 요청 본문 원본 바이트
        query_params: URL 쿼리 파라미터(일부 플랫폼 검증용)

    Returns:
        WebhookResponse 응답 객체
    """
    logger.info(f"[BotHandler] {platform_name} Webhook 요청 받음")

    # 봇 기능이 켜져 있는지 확인
    from src.config import get_config
    config = get_config()

    if not getattr(config, 'bot_enabled', True):
        logger.info("[BotHandler] 봇 기능이 꺼져 있음")
        return WebhookResponse.success()

    # 플랫폼 어댑터 가져오기
    platform = get_platform(platform_name)
    if not platform:
        return WebhookResponse.error(f"Unknown platform: {platform_name}", 400)

    # JSON 데이터 해석
    try:
        data = json.loads(body.decode('utf-8')) if body else {}
    except json.JSONDecodeError as e:
        logger.error(f"[BotHandler] JSON 해석 실패: {e}")
        return WebhookResponse.error("Invalid JSON", 400)

    logger.debug(f"[BotHandler] 요청 데이터: {json.dumps(data, ensure_ascii=False)[:500]}")

    # Webhook 처리
    message, immediate_response = platform.handle_webhook(headers, body, data)

    # 검증/오류 응답이고 처리할 메시지가 없으면 바로 반환
    if immediate_response and not message:
        logger.info("[BotHandler] 검증 응답 반환")
        return immediate_response

    # 지연 응답(예: Discord type 5): ACK를 바로 반환하고 명령은 백그라운드에서 처리
    if immediate_response and message:
        logger.info("[BotHandler] 지연 ACK 반환, 명령은 백그라운드에서 처리")

        def _deferred_dispatch() -> None:
            try:
                dispatcher = get_dispatcher()
                response = dispatcher.dispatch(message)
                if response.text:
                    platform.send_followup(response, message)
            except Exception as exc:
                logger.error("[BotHandler] 지연 명령 처리 실패: %s", exc)

        threading.Thread(target=_deferred_dispatch, daemon=True).start()
        return immediate_response

    # 처리할 메시지가 없으면 빈 응답 반환
    if not message:
        logger.debug("[BotHandler] 처리할 메시지 없음")
        return WebhookResponse.success()

    logger.info(f"[BotHandler] 메시지 해석됨: user={message.user_name}, content={message.content[:50]}")

    # 명령 처리기로 분배
    dispatcher = get_dispatcher()
    response = dispatcher.dispatch(message)

    # 응답 서식 만들기
    if response.text:
        webhook_response = platform.format_response(response, message)
        return webhook_response

    return WebhookResponse.success()


async def handle_webhook_async(
    platform_name: str,
    headers: Dict[str, str],
    body: bytes,
    query_params: Optional[Dict[str, list]] = None
) -> WebhookResponse:
    """Async version of :func:`handle_webhook`.

    Preferred when called from an async context (e.g. FastAPI endpoint)
    to avoid blocking the event loop.
    """
    logger.info(f"[BotHandler] {platform_name} Webhook 요청 받음 (async)")

    from src.config import get_config
    config = get_config()

    if not getattr(config, 'bot_enabled', True):
        logger.info("[BotHandler] 봇 기능이 꺼져 있음")
        return WebhookResponse.success()

    platform = get_platform(platform_name)
    if not platform:
        return WebhookResponse.error(f"Unknown platform: {platform_name}", 400)

    try:
        data = json.loads(body.decode('utf-8')) if body else {}
    except json.JSONDecodeError as e:
        logger.error(f"[BotHandler] JSON 해석 실패: {e}")
        return WebhookResponse.error("Invalid JSON", 400)

    logger.debug(f"[BotHandler] 요청 데이터: {json.dumps(data, ensure_ascii=False)[:500]}")

    message, immediate_response = platform.handle_webhook(headers, body, data)

    if immediate_response and not message:
        logger.info("[BotHandler] 검증 응답 반환")
        return immediate_response

    if immediate_response and message:
        logger.info("[BotHandler] 지연 ACK 반환, 명령은 백그라운드에서 처리 (async)")

        async def _deferred_dispatch() -> None:
            try:
                dispatcher = get_dispatcher()
                response = await dispatcher.dispatch_async(message)
                if response.text:
                    await asyncio.to_thread(platform.send_followup, response, message)
            except Exception as exc:
                logger.error("[BotHandler] 지연 명령 처리 실패: %s", exc)

        asyncio.ensure_future(_deferred_dispatch())
        return immediate_response

    if not message:
        logger.debug("[BotHandler] 처리할 메시지 없음")
        return WebhookResponse.success()

    logger.info(f"[BotHandler] 메시지 해석됨: user={message.user_name}, content={message.content[:50]}")

    dispatcher = get_dispatcher()
    response = await dispatcher.dispatch_async(message)

    if response.text:
        webhook_response = platform.format_response(response, message)
        return webhook_response

    return WebhookResponse.success()


def handle_feishu_webhook(headers: Dict[str, str], body: bytes) -> WebhookResponse:
    """Feishu Webhook 처리"""
    return handle_webhook('feishu', headers, body)


def handle_dingtalk_webhook(headers: Dict[str, str], body: bytes) -> WebhookResponse:
    """DingTalk Webhook 처리"""
    return handle_webhook('dingtalk', headers, body)


def handle_wecom_webhook(headers: Dict[str, str], body: bytes) -> WebhookResponse:
    """WeCom(기업 위챗) Webhook 처리"""
    return handle_webhook('wecom', headers, body)


def handle_telegram_webhook(headers: Dict[str, str], body: bytes) -> WebhookResponse:
    """Telegram Webhook 처리"""
    return handle_webhook('telegram', headers, body)
