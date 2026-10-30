# -*- coding: utf-8 -*-
"""
===================================
플랫폼 어댑터 모듈
===================================

플랫폼별 Webhook 처리와 메시지 해석 로직이 들어 있습니다.

두 가지 연결 방식을 지원합니다:
1. Webhook 방식: 공인 IP가 필요하고 콜백 URL을 설정해야 함
2. Stream 방식: 공인 IP 없이 WebSocket 상시 연결 사용(DingTalk, Feishu 지원)
"""

from bot.platforms.base import BotPlatform
from bot.platforms.dingtalk import DingtalkPlatform

# 사용 가능한 모든 플랫폼(Webhook 방식)
ALL_PLATFORMS = {
    'dingtalk': DingtalkPlatform,
}

# DingTalk Stream 방식(선택)
try:
    from bot.platforms.dingtalk_stream import (
        DingtalkStreamClient,
        DingtalkStreamHandler,
        get_dingtalk_stream_client,
        start_dingtalk_stream_background,
        DINGTALK_STREAM_AVAILABLE,
    )
except ImportError:
    DINGTALK_STREAM_AVAILABLE = False
    DingtalkStreamClient = None
    DingtalkStreamHandler = None
    get_dingtalk_stream_client = lambda: None
    start_dingtalk_stream_background = lambda: False

# Feishu Stream 방식(선택)
try:
    from bot.platforms.feishu_stream import (
        FeishuStreamClient,
        FeishuStreamHandler,
        FeishuReplyClient,
        get_feishu_stream_client,
        start_feishu_stream_background,
        FEISHU_SDK_AVAILABLE,
    )
except ImportError:
    FEISHU_SDK_AVAILABLE = False
    FeishuStreamClient = None
    FeishuStreamHandler = None
    FeishuReplyClient = None
    get_feishu_stream_client = lambda: None
    start_feishu_stream_background = lambda: False

__all__ = [
    'BotPlatform',
    'DingtalkPlatform',
    'ALL_PLATFORMS',
    # DingTalk Stream 방식
    'DingtalkStreamClient',
    'DingtalkStreamHandler',
    'get_dingtalk_stream_client',
    'start_dingtalk_stream_background',
    'DINGTALK_STREAM_AVAILABLE',
    # Feishu Stream 방식
    'FeishuStreamClient',
    'FeishuStreamHandler',
    'FeishuReplyClient',
    'get_feishu_stream_client',
    'start_feishu_stream_background',
    'FEISHU_SDK_AVAILABLE',
]
