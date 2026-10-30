# -*- coding: utf-8 -*-
"""
===================================
명령 기본 클래스
===================================

명령 처리기의 추상 기본 클래스를 정의합니다. 모든 명령은 이 클래스를 상속해야 합니다.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional

from bot.models import BotMessage, BotResponse


class BotCommand(ABC):
    """
    명령 처리기 추상 기본 클래스

    모든 명령은 이 클래스를 상속하고 추상 메서드를 구현해야 합니다.

    사용 예:
        class MyCommand(BotCommand):
            @property
            def name(self) -> str:
                return "mycommand"

            @property
            def aliases(self) -> List[str]:
                return ["mc", "내명령"]

            @property
            def description(self) -> str:
                return "내가 만든 명령입니다"

            @property
            def usage(self) -> str:
                return "/mycommand [인자]"

            def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
                return BotResponse.text_response("명령 실행 성공")
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        명령 이름(접두사 제외)

        예: "analyze" — 사용자가 "/analyze"를 입력하면 실행
        """
        pass

    @property
    @abstractmethod
    def aliases(self) -> List[str]:
        """
        명령 별칭 목록

        예: ["a", "分析"] — 사용자가 "/a"나 "分析"을 입력해도 실행
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """명령 설명(도움말에 표시)"""
        pass

    @property
    @abstractmethod
    def usage(self) -> str:
        """
        사용법(도움말에 표시)

        예: "/analyze <종목코드>"
        """
        pass

    @property
    def hidden(self) -> bool:
        """
        도움말 목록에서 숨길지 여부

        기본값 False. True면 /help 목록에 나오지 않음
        """
        return False

    @property
    def admin_only(self) -> bool:
        """
        관리자 전용 여부

        기본값 False. True면 관리자 권한 필요
        """
        return False

    @abstractmethod
    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """
        명령 실행

        Args:
            message: 원본 메시지 객체
            args: 명령 인자 목록(이미 분리됨)

        Returns:
            BotResponse 응답 객체
        """
        pass

    async def execute_async(self, message: BotMessage, args: List[str]) -> BotResponse:
        """명령을 비동기로 실행합니다.

        기본으로 동기 `execute()`를 스레드 풀에서 돌려, 비동기 분배 흐름에서 이벤트 루프가 막히지 않게 합니다.
        """
        return await asyncio.to_thread(self.execute, message, args)

    def validate_args(self, args: List[str]) -> Optional[str]:
        """
        인자 검증

        하위 클래스에서 이 메서드를 재정의해 인자를 검사할 수 있습니다.

        Args:
            args: 명령 인자 목록

        Returns:
            인자가 올바르면 None, 아니면 오류 메시지를 반환
        """
        return None

    def get_help_text(self) -> str:
        """도움말 텍스트 가져오기"""
        return f"**{self.name}** - {self.description}\n사용법: `{self.usage}`"
