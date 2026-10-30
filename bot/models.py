# -*- coding: utf-8 -*-
"""
===================================
봇 메시지 모델
===================================

플랫폼마다 다른 형식을 감추는 공통 메시지/응답 모델을 정의합니다.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List


class ChatType(str, Enum):
    """대화 유형"""
    GROUP = "group"      # 그룹 채팅
    PRIVATE = "private"  # 1:1 채팅
    UNKNOWN = "unknown"  # 알 수 없음


class Platform(str, Enum):
    """플랫폼 유형"""
    FEISHU = "feishu"        # Feishu
    DINGTALK = "dingtalk"    # DingTalk
    WECOM = "wecom"          # WeCom(기업 위챗)
    TELEGRAM = "telegram"    # Telegram
    UNKNOWN = "unknown"      # 알 수 없음


@dataclass
class BotMessage:
    """
    공통 봇 메시지 모델
    
    각 플랫폼의 메시지 형식을 이 모델로 맞춰 명령 처리기가 다루기 쉽게 합니다.
    
    Attributes:
        platform: 플랫폼 식별자
        message_id: 메시지 ID(플랫폼 원본 ID)
        user_id: 보낸 사람 ID
        user_name: 보낸 사람 이름
        chat_id: 대화 ID(그룹 채팅 ID 또는 1:1 채팅 ID)
        chat_type: 대화 유형
        content: 메시지 본문(@봇 부분은 제거됨)
        raw_content: 원본 메시지 내용
        mentioned: 봇을 @멘션했는지 여부
        mentions: @멘션된 사용자 목록
        timestamp: 메시지 타임스탬프
        raw_data: 원본 요청 데이터(플랫폼별, 디버깅용)
    """
    platform: str
    message_id: str
    user_id: str
    user_name: str
    chat_id: str
    chat_type: ChatType
    content: str
    raw_content: str = ""
    mentioned: bool = False
    mentions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def get_command_and_args(self, prefix: str = "/") -> tuple:
        """
        명령과 인자 해석
        
        Args:
            prefix: 명령 접두사, 기본값 "/"
            
        Returns:
            (command, args) 튜플, 예: ("analyze", ["600519"])
            명령이 아니면 (None, []) 반환
        """
        text = self.content.strip()
        
        # 명령 접두사로 시작하는지 확인
        if not text.startswith(prefix):
            # 중국어 명령 매칭 시도(접두사 없음)
            chinese_commands = {
                '分析': 'analyze',
                '大盘': 'market',
                '批量': 'batch',
                '帮助': 'help',
                '状态': 'status',
            }
            for cn_cmd, en_cmd in chinese_commands.items():
                if text.startswith(cn_cmd):
                    args = text[len(cn_cmd):].strip().split()
                    return en_cmd, args
            return None, []
        
        # 접두사 제거
        text = text[len(prefix):]
        
        # 명령과 인자 분리
        parts = text.split()
        if not parts:
            return None, []
        
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        return command, args
    
    def is_command(self, prefix: str = "/") -> bool:
        """메시지가 명령인지 확인"""
        cmd, _ = self.get_command_and_args(prefix)
        return cmd is not None


@dataclass
class BotResponse:
    """
    공통 봇 응답 모델
    
    명령 처리기가 이 모델을 반환하면 플랫폼 어댑터가 플랫폼별 형식으로 바꿉니다.
    
    Attributes:
        text: 답장 텍스트
        markdown: Markdown 형식 여부
        at_user: 보낸 사람을 @멘션할지 여부
        reply_to_message: 원래 메시지에 답장할지 여부
        extra: 추가 데이터(플랫폼별)
    """
    text: str
    markdown: bool = False
    at_user: bool = True
    reply_to_message: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def text_response(cls, text: str, at_user: bool = True) -> 'BotResponse':
        """일반 텍스트 응답 만들기"""
        return cls(text=text, markdown=False, at_user=at_user)
    
    @classmethod
    def markdown_response(cls, text: str, at_user: bool = True) -> 'BotResponse':
        """Markdown 응답 만들기"""
        return cls(text=text, markdown=True, at_user=at_user)
    
    @classmethod
    def error_response(cls, message: str) -> 'BotResponse':
        """오류 응답 만들기"""
        return cls(text=f"❌ 错误：{message}", markdown=False, at_user=True)


@dataclass
class WebhookResponse:
    """
    Webhook 응답 모델
    
    플랫폼 어댑터가 반환하는 모델로, HTTP 응답 내용을 담습니다.
    
    Attributes:
        status_code: HTTP 상태 코드
        body: 응답 본문(dict, JSON으로 직렬화됨)
        headers: 추가 응답 헤더
    """
    status_code: int = 200
    body: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    
    @classmethod
    def success(cls, body: Optional[Dict] = None) -> 'WebhookResponse':
        """성공 응답 만들기"""
        return cls(status_code=200, body=body or {})
    
    @classmethod
    def challenge(cls, challenge: str) -> 'WebhookResponse':
        """검증 응답 만들기(플랫폼 URL 검증용)"""
        return cls(status_code=200, body={"challenge": challenge})
    
    @classmethod
    def error(cls, message: str, status_code: int = 400) -> 'WebhookResponse':
        """오류 응답 만들기"""
        return cls(status_code=status_code, body={"error": message})
