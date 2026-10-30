# -*- coding: utf-8 -*-
"""
===================================
DingTalk Stream 방식 어댑터
===================================

DingTalk 공식 Stream SDK로 봇을 연결합니다. 공인 IP와 Webhook 설정이 필요 없습니다.

장점:
- 공인 IP나 도메인이 필요 없음
- Webhook URL 설정이 필요 없음
- WebSocket 상시 연결로 메시지 수신
- 더 간단한 연결 방식

의존성:
pip install dingtalk-stream

DingTalk Stream SDK:
https://github.com/open-dingtalk/dingtalk-stream-sdk-python
"""

import logging
import inspect
import threading
from datetime import datetime
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)

# DingTalk Stream SDK import 시도
try:
    import dingtalk_stream
    from dingtalk_stream import AckMessage

    DINGTALK_STREAM_AVAILABLE = True
except ImportError:
    DINGTALK_STREAM_AVAILABLE = False
    logger.warning("[DingTalk Stream] dingtalk-stream SDK가 설치되지 않아 Stream 방식을 쓸 수 없음")
    logger.warning("[DingTalk Stream] 다음을 실행해 주세요: pip install dingtalk-stream")

from bot.models import BotMessage, BotResponse, ChatType


class DingtalkStreamHandler:
    """
    DingTalk Stream 방식 메시지 처리기

    Stream SDK 콜백을 공통 BotMessage 형식으로 바꾸고,
    명령 분배기를 호출해 처리합니다.
    """

    def __init__(self, on_message: Callable[[BotMessage], Any]):
        """
        Args:
            on_message: 메시지 처리 콜백 함수. BotMessage를 받아 BotResponse를 반환
        """
        self._on_message = on_message
        self._logger = logger

    @staticmethod
    def _truncate_log_content(text: str, max_len: int = 200) -> str:
        cleaned = text.replace("\n", " ").strip()
        if len(cleaned) > max_len:
            return f"{cleaned[:max_len]}..."
        return cleaned

    def _log_incoming_message(self, message: BotMessage) -> None:
        content = message.raw_content or message.content or ""
        summary = self._truncate_log_content(content)
        self._logger.info(
            "[DingTalk Stream] Incoming message: msg_id=%s user_id=%s chat_id=%s chat_type=%s content=%s",
            message.message_id,
            message.user_id,
            message.chat_id,
            getattr(message.chat_type, "value", message.chat_type),
            summary,
        )

    if DINGTALK_STREAM_AVAILABLE:
        class _ChatbotHandler(dingtalk_stream.ChatbotHandler):
            """내부 메시지 처리기"""

            def __init__(self, parent: 'DingtalkStreamHandler'):
                super().__init__()
                self._parent = parent
                self.logger = logger

            async def process(self, callback: dingtalk_stream.CallbackMessage):
                """받은 메시지 처리"""
                try:
                    # 메시지 해석
                    incoming = dingtalk_stream.ChatbotMessage.from_dict(callback.data)

                    # 공통 형식으로 변환
                    bot_message = self._parent._parse_stream_message(incoming, callback.data)

                    if bot_message:
                        self._parent._log_incoming_message(bot_message)
                        # 메시지 처리 콜백 호출
                        response = self._parent._on_message(bot_message)
                        if inspect.isawaitable(response):
                            response = await response

                        # 답장 보내기
                        if response and response.text:
                            # @사용자 접두사 만들기(그룹 채팅에서는 본문에 @사용자이름이 들어가야 함)
                            if response.at_user and incoming.sender_nick:
                                if response.markdown:
                                    self.reply_markdown(
                                        title="주식 분석 도우미",
                                        text=f"@{incoming.sender_nick} " + response.text,
                                        incoming_message=incoming
                                    )
                                else:
                                    self.reply_text(response.text, incoming)

                    return AckMessage.STATUS_OK, 'OK'

                except Exception as e:
                    self.logger.error(f"[DingTalk Stream] 메시지 처리 실패: {e}")
                    self.logger.exception(e)
                    return AckMessage.STATUS_SYSTEM_EXCEPTION, str(e)

        def create_handler(self) -> '_ChatbotHandler':
            """SDK에 필요한 처리기 인스턴스 만들기"""
            return self._ChatbotHandler(self)

    def _parse_stream_message(self, incoming: Any, raw_data: dict) -> Optional[BotMessage]:
        """
        Stream 메시지를 공통 형식으로 해석

        Args:
            incoming: ChatbotMessage 객체
            raw_data: 원본 콜백 데이터
        """
        try:
            raw_data = dict(raw_data or {})

            # 메시지 내용 가져오기
            raw_content = incoming.text.content if incoming.text else ''

            # 명령 추출(@봇 제거)
            content = self._extract_command(raw_content)

            # 대화 유형
            conversation_type = getattr(incoming, 'conversation_type', None)
            if conversation_type == '1':
                chat_type = ChatType.PRIVATE
            elif conversation_type == '2':
                chat_type = ChatType.GROUP
            else:
                chat_type = ChatType.UNKNOWN

            # 봇을 @멘션했는지(Stream 방식에서 받는 메시지는 대개 봇 @멘션임)
            mentioned = True

            # 비동기 발송용 sessionWebhook 추출
            session_webhook = (
                    getattr(incoming, 'session_webhook', None)
                    or raw_data.get('sessionWebhook')
                    or raw_data.get('session_webhook')
            )
            if session_webhook:
                raw_data['_session_webhook'] = session_webhook

            return BotMessage(
                platform='dingtalk',
                message_id=getattr(incoming, 'msg_id', '') or '',
                user_id=getattr(incoming, 'sender_id', '') or '',
                user_name=getattr(incoming, 'sender_nick', '') or '',
                chat_id=getattr(incoming, 'conversation_id', '') or '',
                chat_type=chat_type,
                content=content,
                raw_content=raw_content,
                mentioned=mentioned,
                mentions=[],
                timestamp=datetime.now(),
                raw_data=raw_data,
            )

        except Exception as e:
            logger.error(f"[DingTalk Stream] 메시지 해석 실패: {e}")
            return None

    def _extract_command(self, text: str) -> str:
        """명령 내용 추출(@봇 제거)"""
        import re
        text = re.sub(r'^@[\S]+\s*', '', text.strip())
        return text.strip()


class DingtalkStreamClient:
    """
    DingTalk Stream 방식 클라이언트

    dingtalk-stream SDK를 감싸 간단한 시작 함수를 제공합니다.

    사용 방법:
        client = DingtalkStreamClient()
        client.start()  # 블로킹 실행

        # 또는 백그라운드 실행
        client.start_background()
    """

    def __init__(
            self,
            client_id: Optional[str] = None,
            client_secret: Optional[str] = None
    ):
        """
        Args:
            client_id: 앱 AppKey(안 주면 설정에서 읽음)
            client_secret: 앱 AppSecret(안 주면 설정에서 읽음)
        """
        if not DINGTALK_STREAM_AVAILABLE:
            raise ImportError(
                "dingtalk-stream SDK가 설치되지 않았습니다.\n"
                "다음을 실행해 주세요: pip install dingtalk-stream"
            )

        from src.config import get_config
        config = get_config()

        self._client_id = client_id or getattr(config, 'dingtalk_app_key', None)
        self._client_secret = client_secret or getattr(config, 'dingtalk_app_secret', None)

        if not self._client_id or not self._client_secret:
            raise ValueError(
                "DingTalk Stream 방식에는 DINGTALK_APP_KEY와 DINGTALK_APP_SECRET 설정이 필요합니다"
            )

        self._client: Optional[dingtalk_stream.DingTalkStreamClient] = None
        self._background_thread: Optional[threading.Thread] = None
        self._running = False

    def _create_message_handler(self) -> Callable[[BotMessage], Any]:
        """메시지 처리 함수 만들기"""

        async def handle_message(message: BotMessage) -> BotResponse:
            from bot.dispatcher import get_dispatcher
            dispatcher = get_dispatcher()
            return await dispatcher.dispatch_async(message)

        return handle_message

    def start(self) -> None:
        """
        Stream 클라이언트 시작(블로킹)

        클라이언트가 멈출 때까지 현재 스레드를 막습니다.
        """
        logger.info("[DingTalk Stream] 시작하는 중...")

        # 인증 정보 만들기
        credential = dingtalk_stream.Credential(
            self._client_id,
            self._client_secret
        )

        # 클라이언트 만들기
        self._client = dingtalk_stream.DingTalkStreamClient(credential)

        # 메시지 처리기 등록
        handler = DingtalkStreamHandler(self._create_message_handler())
        self._client.register_callback_handler(
            dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
            handler.create_handler()
        )

        self._running = True
        logger.info("[DingTalk Stream] 클라이언트 시작됨, 메시지 기다리는 중...")

        # 시작(블로킹)
        self._client.start_forever()

    def start_background(self) -> None:
        """
        백그라운드 스레드에서 Stream 클라이언트 시작(논블로킹)

        다른 서비스(예: WebUI)와 함께 돌릴 때 씁니다.
        """
        if self._background_thread and self._background_thread.is_alive():
            logger.warning("[DingTalk Stream] 클라이언트가 이미 실행 중")
            return

        self._running = True
        self._background_thread = threading.Thread(
            target=self._run_in_background,
            daemon=True,
            name="DingtalkStreamClient"
        )
        self._background_thread.start()
        logger.info("[DingTalk Stream] 백그라운드 클라이언트 시작됨")

    def _run_in_background(self) -> None:
        """백그라운드 실행(예외 처리와 재연결)"""
        import time

        while self._running:
            try:
                self.start()
            except Exception as e:
                logger.error(f"[DingTalk Stream] 실행 예외: {e}")
                if self._running:
                    logger.info("[DingTalk Stream] 5초 후 재연결...")
                    time.sleep(5)

    def stop(self) -> None:
        """클라이언트 중지"""
        self._running = False
        logger.info("[DingTalk Stream] 클라이언트 중지됨")

    @property
    def is_running(self) -> bool:
        """실행 중인지 여부"""
        return self._running


# 전역 클라이언트 인스턴스
_stream_client: Optional[DingtalkStreamClient] = None


def get_dingtalk_stream_client() -> Optional[DingtalkStreamClient]:
    """전역 Stream 클라이언트 인스턴스 가져오기"""
    global _stream_client

    if _stream_client is None and DINGTALK_STREAM_AVAILABLE:
        try:
            _stream_client = DingtalkStreamClient()
        except (ImportError, ValueError) as e:
            logger.warning(f"[DingTalk Stream] 클라이언트를 만들 수 없음: {e}")
            return None

    return _stream_client


def start_dingtalk_stream_background() -> bool:
    """
    백그라운드에서 DingTalk Stream 클라이언트 시작

    Returns:
        시작 성공 여부
    """
    client = get_dingtalk_stream_client()
    if client:
        client.start_background()
        return True
    return False
