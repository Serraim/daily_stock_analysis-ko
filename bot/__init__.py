# -*- coding: utf-8 -*-
"""
===================================
봇 명령 실행 시스템
===================================

@봇 멘션이나 명령으로 주식 분석 등을 실행합니다.
Feishu, DingTalk, WeCom(기업 위챗), Telegram 등 여러 플랫폼을 지원합니다.

모듈 구성:
- models.py: 공통 메시지/응답 모델
- dispatcher.py: 명령 분배기
- commands/: 명령 처리기
- platforms/: 플랫폼 어댑터
- handler.py: Webhook 처리기

사용 방법:
1. 환경 변수 설정(플랫폼별 Token 등)
2. WebUI 서비스 시작
3. 각 플랫폼에 Webhook URL 등록:
   - Feishu: http://your-server/bot/feishu
   - DingTalk: http://your-server/bot/dingtalk
   - WeCom: http://your-server/bot/wecom
   - Telegram: http://your-server/bot/telegram

지원 명령:
- /analyze <종목코드>  - 지정 종목 분석
- /market             - 시장 전체 복기
- /batch              - 관심 종목 일괄 분석
- /help               - 도움말 보기
- /status             - 시스템 상태
"""

from bot.models import BotMessage, BotResponse, ChatType, WebhookResponse
from bot.dispatcher import CommandDispatcher, get_dispatcher

__all__ = [
    'BotMessage',
    'BotResponse',
    'ChatType',
    'WebhookResponse',
    'CommandDispatcher',
    'get_dispatcher',
]
