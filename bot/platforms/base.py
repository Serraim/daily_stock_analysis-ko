# -*- coding: utf-8 -*-
"""
===================================
플랫폼 어댑터 기본 클래스
===================================

플랫폼 어댑터의 추상 기본 클래스를 정의합니다. 각 플랫폼은 이 클래스를 상속해야 합니다.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple

from bot.models import BotMessage, BotResponse, WebhookResponse


class BotPlatform(ABC):
    """
    플랫폼 어댑터 추상 기본 클래스
    
    역할:
    1. Webhook 요청 서명 검증
    2. 플랫폼 메시지를 공통 형식으로 해석
    3. 응답을 플랫폼 형식으로 변환
    
    사용 예:
        class MyPlatform(BotPlatform):
            @property
            def platform_name(self) -> str:
                return "myplatform"
            
            def verify_request(self, headers, body) -> bool:
                # 서명 검증 로직
                return True
            
            def parse_message(self, data) -> Optional[BotMessage]:
                # 메시지 해석 로직
                return BotMessage(...)
            
            def format_response(self, response, message) -> WebhookResponse:
                # 응답 서식 로직
                return WebhookResponse.success({"text": response.text})
    """
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """
        플랫폼 식별 이름
        
        라우팅 매칭과 로그 표시에 씀. 예: "feishu", "dingtalk"
        """
        pass
    
    @abstractmethod
    def verify_request(self, headers: Dict[str, str], body: bytes) -> bool:
        """
        요청 서명 검증
        
        플랫폼마다 서명 검증 방식이 달라 따로 구현해야 합니다.
        
        Args:
            headers: HTTP 요청 헤더
            body: 요청 본문 원본 바이트
            
        Returns:
            서명이 유효한지 여부
        """
        pass
    
    @abstractmethod
    def parse_message(self, data: Dict[str, Any]) -> Optional[BotMessage]:
        """
        플랫폼 메시지를 공통 형식으로 해석
        
        플랫폼별 메시지 형식을 BotMessage로 바꿉니다.
        처리할 메시지 유형이 아니면(예: 이벤트 콜백) None을 반환합니다.
        
        Args:
            data: 해석된 JSON 데이터
            
        Returns:
            BotMessage 객체 또는 None(처리 불필요)
        """
        pass
    
    @abstractmethod
    def format_response(
        self, 
        response: BotResponse, 
        message: BotMessage
    ) -> WebhookResponse:
        """
        공통 응답을 플랫폼 형식으로 변환
        
        Args:
            response: 공통 응답 객체
            message: 원본 메시지 객체(답장 대상 등 정보 확인용)
            
        Returns:
            WebhookResponse 객체
        """
        pass
    
    def send_followup(
        self,
        response: 'BotResponse',
        message: 'BotMessage',
    ) -> bool:
        """Send a follow-up message after a deferred webhook response.

        Override in platforms that return a deferred acknowledgement
        (e.g. Discord type 5) so the final command result can be delivered
        asynchronously.  The default implementation is a no-op.

        Returns:
            ``True`` if the follow-up was sent successfully.
        """
        return False

    def handle_challenge(self, data: Dict[str, Any]) -> Optional[WebhookResponse]:
        """
        플랫폼 검증 요청 처리
        
        일부 플랫폼은 Webhook 설정 때 검증 요청을 보내므로 정해진 응답을 돌려줘야 합니다.
        하위 클래스에서 재정의할 수 있습니다.
        
        Args:
            data: 요청 데이터
            
        Returns:
            검증 응답 또는 None(검증 요청이 아님)
        """
        return None
    
    def handle_webhook(
        self, 
        headers: Dict[str, str], 
        body: bytes,
        data: Dict[str, Any]
    ) -> Tuple[Optional[BotMessage], Optional[WebhookResponse]]:
        """
        Webhook 요청 처리
        
        주 입구 메서드로, 검증과 해석 등 흐름을 조율합니다.
        
        Args:
            headers: HTTP 요청 헤더
            body: 요청 본문 원본 바이트
            data: 해석된 JSON 데이터
            
        Returns:
            (BotMessage, WebhookResponse) 튜플
            - 검증 요청이면:(None, challenge_response)
            - 일반 메시지면: (message, None) - 응답은 명령 처리 후 생성
            - 검증 실패 또는 처리 불필요면: (None, error_response 또는 None)
        """
        # 1. 검증 요청인지 확인
        challenge_response = self.handle_challenge(data)
        if challenge_response:
            return None, challenge_response
        
        # 2. 요청 서명 검증
        if not self.verify_request(headers, body):
            return None, WebhookResponse.error("Invalid signature", 403)
        
        # 3. 메시지 해석
        message = self.parse_message(data)
        
        return message, None
