# -*- coding: utf-8 -*-
"""
===================================
DingTalk 플랫폼 어댑터
===================================

DingTalk 봇의 Webhook 콜백을 처리합니다.

DingTalk 봇 문서:
https://open.dingtalk.com/document/robots/robot-overview
"""

import hashlib
import hmac
import base64
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.parse import quote_plus

from bot.platforms.base import BotPlatform
from bot.models import BotMessage, BotResponse, WebhookResponse, ChatType

logger = logging.getLogger(__name__)


class DingtalkPlatform(BotPlatform):
    """
    DingTalk 플랫폼 어댑터
    
    지원:
    - 사내 봇 콜백
    - 그룹 봇 Outgoing 콜백
    - 메시지 서명 검증
    
    필요한 설정:
    - DINGTALK_APP_KEY: 앱 AppKey
    - DINGTALK_APP_SECRET: 앱 AppSecret(서명 검증용)
    """
    
    def __init__(self):
        from src.config import get_config
        config = get_config()
        
        self._app_key = getattr(config, 'dingtalk_app_key', None)
        self._app_secret = getattr(config, 'dingtalk_app_secret', None)
    
    @property
    def platform_name(self) -> str:
        return "dingtalk"
    
    def verify_request(self, headers: Dict[str, str], body: bytes) -> bool:
        """
        DingTalk 요청 서명 검증
        
        DingTalk 서명 방식:
        1. timestamp와 sign 가져오기
        2. 계산:base64(hmac_sha256(timestamp + "\n" + app_secret))
        3. 서명 비교
        """
        if not self._app_secret:
            logger.warning("[DingTalk] app_secret이 설정되지 않아 서명 검증 건너뜀")
            return True
        
        timestamp = headers.get('timestamp', '')
        sign = headers.get('sign', '')
        
        if not timestamp or not sign:
            logger.warning("[DingTalk] 서명 파라미터 없음")
            return True  # 서명이 필요 없는 요청일 수 있음
        
        # 타임스탬프 검증(1시간 안에만 유효)
        try:
            request_time = int(timestamp)
            current_time = int(time.time() * 1000)
            if abs(current_time - request_time) > 3600 * 1000:
                logger.warning("[DingTalk] 타임스탬프 만료")
                return False
        except ValueError:
            logger.warning("[DingTalk] 잘못된 타임스탬프")
            return False
        
        # 서명 계산
        string_to_sign = f"{timestamp}\n{self._app_secret}"
        hmac_code = hmac.new(
            self._app_secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        expected_sign = base64.b64encode(hmac_code).decode('utf-8')
        
        if sign != expected_sign:
            logger.warning(f"[DingTalk] 서명 검증 실패")
            return False
        
        return True
    
    def handle_challenge(self, data: Dict[str, Any]) -> Optional[WebhookResponse]:
        """DingTalk는 URL 검증이 필요 없음"""
        return None
    
    def parse_message(self, data: Dict[str, Any]) -> Optional[BotMessage]:
        """
        DingTalk 메시지 해석
        
        DingTalk Outgoing 봇 메시지 형식:
        {
            "msgtype": "text",
            "text": {
                "content": "@봇 /analyze 600519"
            },
            "msgId": "xxx",
            "createAt": "1234567890",
            "conversationType": "2",  # 1=1:1 채팅, 2=그룹 채팅
            "conversationId": "xxx",
            "conversationTitle": "그룹 이름",
            "senderId": "xxx",
            "senderNick": "사용자 닉네임",
            "senderCorpId": "xxx",
            "senderStaffId": "xxx",
            "chatbotUserId": "xxx",
            "atUsers": [{"dingtalkId": "xxx", "staffId": "xxx"}],
            "isAdmin": false,
            "sessionWebhook": "https://oapi.dingtalk.com/robot/sendBySession?session=xxx",
            "sessionWebhookExpiredTime": 1234567890
        }
        """
        # 메시지 유형 확인
        msg_type = data.get('msgtype', '')
        if msg_type != 'text':
            logger.debug(f"[DingTalk] 텍스트가 아닌 메시지 무시: {msg_type}")
            return None
        
        # 메시지 내용 가져오기
        text_content = data.get('text', {})
        raw_content = text_content.get('content', '')
        
        # 명령 추출(@봇 제거)
        content = self._extract_command(raw_content)
        
        # 봇을 @멘션했는지 확인
        at_users = data.get('atUsers', [])
        mentioned = len(at_users) > 0
        
        # 대화 유형
        conversation_type = data.get('conversationType', '')
        if conversation_type == '1':
            chat_type = ChatType.PRIVATE
        elif conversation_type == '2':
            chat_type = ChatType.GROUP
        else:
            chat_type = ChatType.UNKNOWN
        
        # 생성 시간
        create_at = data.get('createAt', '')
        try:
            timestamp = datetime.fromtimestamp(int(create_at) / 1000)
        except (ValueError, TypeError):
            timestamp = datetime.now()
        
        # 답장용 session webhook 저장
        session_webhook = data.get('sessionWebhook', '')
        
        return BotMessage(
            platform=self.platform_name,
            message_id=data.get('msgId', ''),
            user_id=data.get('senderId', ''),
            user_name=data.get('senderNick', ''),
            chat_id=data.get('conversationId', ''),
            chat_type=chat_type,
            content=content,
            raw_content=raw_content,
            mentioned=mentioned,
            mentions=[u.get('dingtalkId', '') for u in at_users],
            timestamp=timestamp,
            raw_data={
                **data,
                '_session_webhook': session_webhook,
            },
        )
    
    def _extract_command(self, text: str) -> str:
        """
        명령 내용 추출(@봇 제거)
        
        DingTalk의 @사용자 형식은 보통 @닉네임 뒤에 공백이 옴
        """
        # 단순 처리: 맨 앞의 @xxx 부분 제거
        import re
        # 맨 앞의 @xxx 매칭(중국어/영어 모두 가능)
        text = re.sub(r'^@[\S]+\s*', '', text.strip())
        return text.strip()
    
    def format_response(
        self, 
        response: BotResponse, 
        message: BotMessage
    ) -> WebhookResponse:
        """
        DingTalk 응답 서식 만들기
        
        DingTalk Outgoing 봇은 응답에 메시지를 바로 담아 보낼 수 있습니다.
        sessionWebhook으로 비동기 전송도 할 수 있습니다.
        
        응답 형식:
        {
            "msgtype": "text" | "markdown",
            "text": {"content": "xxx"},
            "markdown": {"title": "xxx", "text": "xxx"},
            "at": {"atUserIds": ["xxx"], "isAtAll": false}
        }
        """
        if not response.text:
            return WebhookResponse.success()
        
        # 응답 만들기
        if response.markdown:
            body = {
                "msgtype": "markdown",
                "markdown": {
                    "title": "주식 분석 도우미",
                    "text": response.text,
                }
            }
        else:
            body = {
                "msgtype": "text",
                "text": {
                    "content": response.text,
                }
            }
        
        # 보낸 사람 @멘션
        if response.at_user and message.user_id:
            body["at"] = {
                "atUserIds": [message.user_id],
                "isAtAll": False,
            }
        
        return WebhookResponse.success(body)
    
    def send_by_session_webhook(
        self, 
        session_webhook: str, 
        response: BotResponse,
        message: BotMessage
    ) -> bool:
        """
        sessionWebhook으로 메시지 보내기
        
        비동기 전송이나 여러 메시지를 보낼 때 씁니다.
        
        Args:
            session_webhook: DingTalk가 주는 대화 Webhook URL
            response: 응답 객체
            message: 원본 메시지 객체
            
        Returns:
            전송 성공 여부
        """
        if not session_webhook:
            logger.warning("[DingTalk] 사용할 수 있는 sessionWebhook 없음")
            return False
        
        import requests
        
        try:
            # 메시지 만들기
            if response.markdown:
                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "title": "주식 분석 도우미",
                        "text": response.text,
                    }
                }
            else:
                payload = {
                    "msgtype": "text",
                    "text": {
                        "content": response.text,
                    }
                }
            
            # 보낸 사람 @멘션
            if response.at_user and message.user_id:
                payload["at"] = {
                    "atUserIds": [message.user_id],
                    "isAtAll": False,
                }
            
            # 요청 보내기
            resp = requests.post(
                session_webhook,
                json=payload,
                timeout=10
            )
            
            if resp.status_code == 200:
                result = resp.json()
                if result.get('errcode') == 0:
                    logger.info("[DingTalk] sessionWebhook 전송 성공")
                    return True
                else:
                    logger.error(f"[DingTalk] sessionWebhook 전송 실패: {result}")
                    return False
            else:
                logger.error(f"[DingTalk] sessionWebhook 요청 실패: {resp.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"[DingTalk] sessionWebhook 전송 예외: {e}")
            return False
