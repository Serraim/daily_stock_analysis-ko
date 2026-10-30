# -*- coding: utf-8 -*-
"""
===================================
Feishu Stream 방식 어댑터
===================================

Feishu 공식 lark-oapi SDK의 WebSocket 상시 연결 방식으로 봇을 연결합니다.
공인 IP와 Webhook 설정이 필요 없습니다.

장점:
- 공인 IP나 도메인이 필요 없음
- Webhook URL 설정이 필요 없음
- WebSocket 상시 연결로 메시지 수신
- 더 간단한 연결 방식
- 자동 재연결과 하트비트 연결 유지 내장

의존성:
pip install lark-oapi

Feishu 상시 연결 문서:
https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/handle-events
"""

import json
import logging
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional, Callable
import time

logger = logging.getLogger(__name__)

FEISHU_DOMAIN = "https://open.feishu.cn"
LARK_DOMAIN = "https://open.larksuite.com"

# Feishu SDK import 시도
try:
    import lark_oapi as lark
    from lark_oapi import ws
    from lark_oapi.api.im.v1 import (
        P2ImMessageReceiveV1,
        ReplyMessageRequest,
        ReplyMessageRequestBody,
        CreateMessageRequest,
        CreateMessageRequestBody,
    )
    from lark_oapi.core.const import (
        FEISHU_DOMAIN as SDK_FEISHU_DOMAIN,
        LARK_DOMAIN as SDK_LARK_DOMAIN,
    )

    FEISHU_DOMAIN = SDK_FEISHU_DOMAIN
    LARK_DOMAIN = SDK_LARK_DOMAIN
    FEISHU_SDK_AVAILABLE = True
except ImportError:
    FEISHU_SDK_AVAILABLE = False
    logger.warning("[Feishu Stream] lark-oapi SDK가 설치되지 않아 Stream 방식을 쓸 수 없음")
    logger.warning("[Feishu Stream] 다음을 실행해 주세요: pip install lark-oapi")

from bot.models import BotMessage, BotResponse, ChatType
from src.formatters import format_feishu_markdown, chunk_content_by_max_bytes
from src.config import get_config


def _resolve_feishu_domain(domain: Optional[str]) -> str:
    """Resolve the configured Feishu/Lark region to an SDK API domain."""
    raw_domain = str(domain or "feishu").strip().lower()
    if raw_domain in ("feishu", FEISHU_DOMAIN.lower()):
        return FEISHU_DOMAIN
    if raw_domain in ("lark", LARK_DOMAIN.lower()):
        return LARK_DOMAIN

    logger.warning(
        "[Feishu Stream] 无效的 FEISHU_DOMAIN=%s，回退为 feishu",
        raw_domain,
    )
    return FEISHU_DOMAIN


class FeishuReplyClient:
    """
    Feishu 메시지 답장 클라이언트

    Feishu API로 답장 메시지를 보냅니다.
    """

    def __init__(
            self,
            app_id: str,
            app_secret: str,
            domain: Optional[str] = None
    ):
        """
        Args:
            app_id: Feishu 앱 ID
            app_secret: Feishu 앱 시크릿
            domain: Feishu API 지역(feishu/lark) 또는 SDK API 도메인
        """
        if not FEISHU_SDK_AVAILABLE:
            raise ImportError("lark-oapi SDK가 설치되지 않음")

        config = get_config()
        configured_domain = (
            domain
            if domain is not None
            else getattr(config, 'feishu_domain', 'feishu')
        )
        self._domain = _resolve_feishu_domain(configured_domain)

        self._client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .domain(self._domain) \
            .log_level(lark.LogLevel.WARNING) \
            .build()

        # 설정된 최대 바이트 수 가져오기
        self._max_bytes = getattr(config, 'feishu_max_bytes', 20000)

    def _send_interactive_card(self, content: str, message_id: Optional[str] = None,
                               chat_id: Optional[str] = None,
                               receive_id_type: str = "chat_id",
                               at_user: bool = False, user_id: Optional[str] = None) -> bool:
        """
        인터랙티브 카드 메시지 보내기(Markdown 렌더링 지원)

        Args:
            content: Markdown 형식 내용
            message_id: 원래 메시지 ID(답장할 때 사용)
            chat_id: 대화 ID(먼저 보낼 때 사용)
            receive_id_type: 받는 사람 ID 유형
            at_user: 사용자를 @멘션할지 여부
            user_id: 사용자 open_id(at_user=True일 때 필요)

        Returns:
            전송 성공 여부
        """
        try:
            # 사용자를 @멘션해야 하면 내용 앞에 @ 표시 추가
            final_content = content
            if at_user and user_id:
                final_content = f"<at user_id=\"{user_id}\"></at> {content}"

            # 인터랙티브 카드 payload 만들기
            card_data = {
                "config": {"wide_screen_mode": True},
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": final_content
                        }
                    }
                ]
            }

            content_json = json.dumps(card_data)

            if message_id:
                # 메시지에 답장
                request = ReplyMessageRequest.builder() \
                    .message_id(message_id) \
                    .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(content_json)
                    .msg_type("interactive")
                    .build()
                ) \
                    .build()
                response = self._client.im.v1.message.reply(request)
            else:
                # 먼저 메시지 보내기
                request = CreateMessageRequest.builder() \
                    .receive_id_type(receive_id_type) \
                    .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .content(content_json)
                    .msg_type("interactive")
                    .build()
                ) \
                    .build()
                response = self._client.im.v1.message.create(request)

            if not response.success():
                logger.error(
                    f"[Feishu Stream] 인터랙티브 카드 전송 실패: code={response.code}, "
                    f"msg={response.msg}, log_id={response.get_log_id()}"
                )
                return False

            logger.debug("[Feishu Stream] 인터랙티브 카드 전송 성공")
            return True

        except Exception as e:
            logger.error(f"[Feishu Stream] 인터랙티브 카드 전송 예외: {e}")
            return False

    def reply_text(self, message_id: str, text: str, at_user: bool = False,
                   user_id: Optional[str] = None) -> bool:
        """
        텍스트 메시지로 답장(인터랙티브 카드와 나눠 보내기 지원)

        Args:
            message_id: 원래 메시지 ID
            text: 답장 텍스트
            at_user: 사용자를 @멘션할지 여부
            user_id: 사용자 open_id(at_user=True일 때 필요)

        Returns:
            전송 성공 여부
        """
        # 텍스트를 Feishu Markdown 형식으로 변환
        formatted_text = format_feishu_markdown(text)

        # 나눠 보내야 하는지 확인
        content_bytes = len(formatted_text.encode('utf-8'))
        if content_bytes > self._max_bytes:
            logger.info(
                f"[Feishu Stream] 답장 내용이 너무 김({content_bytes}바이트), 나눠서 보냄"
            )
            return self._send_to_chat_chunked(
                formatted_text,
                lambda chunk: self._send_interactive_card(
                    chunk,
                    message_id=message_id,
                    at_user=at_user,
                    user_id=user_id,
                ),
            )

        # 메시지 하나면 인터랙티브 카드 사용
        return self._send_interactive_card(
            formatted_text, message_id=message_id, at_user=at_user, user_id=user_id
        )

    def send_to_chat(self, chat_id: str, text: str,
                     receive_id_type: str = "chat_id") -> bool:
        """
        지정한 대화로 메시지 보내기(인터랙티브 카드와 나눠 보내기 지원)

        Args:
            chat_id: 대화 ID
            text: 메시지 텍스트
            receive_id_type: 받는 사람 ID 유형, 기본값 chat_id

        Returns:
            전송 성공 여부
        """
        # 텍스트를 Feishu Markdown 형식으로 변환
        formatted_text = format_feishu_markdown(text)

        # 나눠 보내야 하는지 확인
        content_bytes = len(formatted_text.encode('utf-8'))
        if content_bytes > self._max_bytes:
            logger.info(
                f"[Feishu Stream] 보낼 내용이 너무 김({content_bytes}바이트), 나눠서 보냄"
            )
            return self._send_to_chat_chunked(
                formatted_text,
                lambda chunk: self._send_interactive_card(
                    chunk,
                    chat_id=chat_id,
                    receive_id_type=receive_id_type,
                ),
            )

        # 메시지 하나면 인터랙티브 카드 사용
        return self._send_interactive_card(formatted_text, chat_id=chat_id, receive_id_type=receive_id_type)

    def _send_to_chat_chunked(self, content: str, send_func: Callable[[str], bool]) -> bool:
        """
        메시지를 나눠 보내기(인터랙티브 카드와 나눠 보내기 지원)

        Args:
            content: 메시지 텍스트
            send_func: 조각 하나를 보내는 함수, 전송 성공 여부를 반환

        Returns:
            모두 전송 성공했는지 여부
        """
        chunks = chunk_content_by_max_bytes(content, self._max_bytes, add_page_marker=True)
        success_count = 0
        for i, chunk in enumerate(chunks):
            if send_func(chunk):
                success_count += 1
            else:
                logger.error(f"[Feishu Stream] 메시지 전송 실패: {chunk}")
            if i < len(chunks) - 1:
                time.sleep(1)
        return success_count == len(chunks)


class FeishuStreamHandler:
    """
    Feishu Stream 방식 메시지 처리기

    SDK 이벤트를 공통 BotMessage 형식으로 바꾸고,
    명령 분배기를 호출해 처리합니다.
    """

    def __init__(
            self,
            on_message: Callable[[BotMessage], BotResponse],
            reply_client: FeishuReplyClient
    ):
        """
        Args:
            on_message: 메시지 처리 콜백 함수. BotMessage를 받아 BotResponse를 반환
            reply_client: Feishu 답장 클라이언트
        """
        self._on_message = on_message
        self._reply_client = reply_client
        self._logger = logger
        # Different conversations can run in parallel, but one conversation
        # must stay FIFO so multi-turn chat and replies do not get reordered.
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="feishu-msg")
        self._pending_messages: dict[str, deque[BotMessage]] = {}
        self._active_conversations: set[str] = set()
        self._queue_lock = threading.Lock()
        self._shutdown = False

    def _conversation_key(self, bot_message: BotMessage) -> str:
        """Return the ordering key used for per-conversation FIFO processing."""
        if bot_message.chat_type == ChatType.PRIVATE:
            return bot_message.chat_id or bot_message.user_id or bot_message.message_id

        chat_id = bot_message.chat_id or "unknown-chat"
        user_id = bot_message.user_id or "unknown-user"
        return f"{chat_id}:{user_id}"

    def _enqueue_message(self, bot_message: BotMessage) -> None:
        """Queue a message and start a worker when its conversation is idle."""
        if self._shutdown:
            self._logger.debug("[Feishu Stream] Handler already stopped, dropping message")
            return

        conversation_key = self._conversation_key(bot_message)
        should_start_worker = False

        with self._queue_lock:
            self._pending_messages.setdefault(conversation_key, deque()).append(bot_message)
            if conversation_key not in self._active_conversations:
                self._active_conversations.add(conversation_key)
                should_start_worker = True

        if should_start_worker:
            try:
                self._executor.submit(self._drain_conversation, conversation_key)
            except RuntimeError as exc:
                with self._queue_lock:
                    self._active_conversations.discard(conversation_key)
                    self._pending_messages.pop(conversation_key, None)
                self._logger.error("[Feishu Stream] 메시지 처리 스레드를 시작할 수 없음: %s", exc)

    def _drain_conversation(self, conversation_key: str) -> None:
        """Drain one conversation queue in FIFO order."""
        while True:
            with self._queue_lock:
                queue = self._pending_messages.get(conversation_key)
                if not queue:
                    self._pending_messages.pop(conversation_key, None)
                    self._active_conversations.discard(conversation_key)
                    return
                bot_message = queue.popleft()

            self._process_message(bot_message)

    def _process_message(self, bot_message: BotMessage) -> None:
        """Execute command handling off the SDK callback thread."""
        try:
            response = self._on_message(bot_message)

            if response and response.text:
                self._reply_client.reply_text(
                    message_id=bot_message.message_id,
                    text=response.text,
                    at_user=response.at_user,
                    user_id=bot_message.user_id if response.at_user else None,
                )
        except Exception as e:
            self._logger.error(f"[Feishu Stream] 비동기 메시지 처리 실패: {e}")
            self._logger.exception(e)

    @staticmethod
    def _truncate_log_content(text: str, max_len: int = 200) -> str:
        """로그 내용 자르기"""
        cleaned = text.replace("\n", " ").strip()
        if len(cleaned) > max_len:
            return f"{cleaned[:max_len]}..."
        return cleaned

    def _log_incoming_message(self, message: BotMessage) -> None:
        """받은 메시지 로그 남기기"""
        content = message.raw_content or message.content or ""
        summary = self._truncate_log_content(content)
        self._logger.info(
            "[Feishu Stream] Incoming message: msg_id=%s user_id=%s "
            "chat_id=%s chat_type=%s content=%s",
            message.message_id,
            message.user_id,
            message.chat_id,
            getattr(message.chat_type, "value", message.chat_type),
            summary,
        )

    def handle_message(self, event: 'P2ImMessageReceiveV1') -> None:
        """
        받은 메시지 이벤트 처리

        Args:
            event: Feishu 메시지 수신 이벤트
        """
        try:
            # 메시지 해석
            bot_message = self._parse_event_message(event)

            if bot_message is None:
                return

            self._log_incoming_message(bot_message)

            self._enqueue_message(bot_message)

        except Exception as e:
            self._logger.error(f"[Feishu Stream] 메시지 처리 실패: {e}")
            self._logger.exception(e)

    def _parse_event_message(self, event: 'P2ImMessageReceiveV1') -> Optional[BotMessage]:
        """
        Feishu 이벤트 메시지를 공통 형식으로 해석

        Args:
            event: P2ImMessageReceiveV1 이벤트 객체
        """
        try:
            event_data = event.event
            if event_data is None:
                return None

            message_data = event_data.message
            sender_data = event_data.sender

            if message_data is None:
                return None

            # 텍스트 메시지만 처리
            message_type = message_data.message_type or ""
            if message_type != "text":
                self._logger.debug(f"[Feishu Stream] 텍스트가 아닌 메시지 무시: {message_type}")
                return None

            # 메시지 내용 해석
            content_str = message_data.content or "{}"
            try:
                content_json = json.loads(content_str)
                raw_content = content_json.get("text", "")
            except json.JSONDecodeError:
                raw_content = content_str

            # 명령 추출(@봇 제거)
            content = self._extract_command(raw_content, message_data.mentions)
            mentioned = "@" in raw_content or bool(message_data.mentions)

            # 보낸 사람 정보 가져오기
            user_id = ""
            if sender_data and sender_data.sender_id:
                user_id = sender_data.sender_id.open_id or sender_data.sender_id.user_id or ""

            # 대화 유형 가져오기
            chat_type_str = message_data.chat_type or ""
            if chat_type_str == "group":
                chat_type = ChatType.GROUP
            elif chat_type_str == "p2p":
                chat_type = ChatType.PRIVATE
            else:
                chat_type = ChatType.UNKNOWN

            # 생성 시간
            create_time = message_data.create_time
            try:
                if create_time:
                    timestamp = datetime.fromtimestamp(int(create_time) / 1000)
                else:
                    timestamp = datetime.now()
            except (ValueError, TypeError):
                timestamp = datetime.now()

            # 원본 데이터 만들기
            raw_data = {
                "header": {
                    "event_id": event.header.event_id if event.header else "",
                    "event_type": event.header.event_type if event.header else "",
                    "create_time": event.header.create_time if event.header else "",
                    "token": event.header.token if event.header else "",
                    "app_id": event.header.app_id if event.header else "",
                },
                "event": {
                    "message_id": message_data.message_id,
                    "chat_id": message_data.chat_id,
                    "chat_type": message_data.chat_type,
                    "content": message_data.content,
                }
            }

            return BotMessage(
                platform="feishu",
                message_id=message_data.message_id or "",
                user_id=user_id,
                user_name=user_id,  # Feishu는 사용자 이름을 바로 주지 않음
                chat_id=message_data.chat_id or "",
                chat_type=chat_type,
                content=content,
                raw_content=raw_content,
                mentioned=mentioned,
                mentions=[m.key or "" for m in (message_data.mentions or [])],
                timestamp=timestamp,
                raw_data=raw_data,
            )

        except Exception as e:
            self._logger.error(f"[Feishu Stream] 메시지 해석 실패: {e}")
            return None

    def _extract_command(self, text: str, mentions: list) -> str:
        """
        명령 내용 추출(@봇 제거)

        Feishu의 @사용자 형식: @_user_1, @_user_2 등

        Args:
            text: 원본 메시지 텍스트
            mentions: @멘션 목록
        """
        import re

        # 방법 1: mentions 목록으로 제거(정확히 일치)
        for mention in (mentions or []):
            key = getattr(mention, 'key', '') or ''
            if key:
                text = text.replace(key, '')

        # 방법 2: 정규식으로 보완, Feishu @사용자 형식(@_user_N) 제거
        # mentions가 비었거나 제대로 전달되지 않았을 때 작동
        text = re.sub(r'@_user_\d+\s*', '', text)

        # 남는 공백 정리
        return ' '.join(text.split())

    def shutdown(self, wait: bool = False) -> None:
        """Stop accepting new messages and tear down worker threads."""
        self._shutdown = True
        with self._queue_lock:
            self._pending_messages.clear()
            self._active_conversations.clear()
        self._executor.shutdown(wait=wait)


class FeishuStreamClient:
    """
    Feishu Stream 방식 클라이언트

    lark-oapi SDK의 WebSocket 클라이언트를 감싸 간단한 시작 함수를 제공합니다.

    사용 방법:
        client = FeishuStreamClient()
        client.start()  # 블로킹 실행

        # 또는 백그라운드 실행
        client.start_background()
    """

    def __init__(
            self,
            app_id: Optional[str] = None,
            app_secret: Optional[str] = None,
            domain: Optional[str] = None
    ):
        """
        Args:
            app_id: 앱 ID(안 주면 설정에서 읽음)
            app_secret: 앱 시크릿(안 주면 설정에서 읽음)
            domain: Feishu API 지역(feishu/lark) 또는 SDK API 도메인
        """
        if not FEISHU_SDK_AVAILABLE:
            raise ImportError(
                "lark-oapi SDK가 설치되지 않았습니다.\n"
                "다음을 실행해 주세요: pip install lark-oapi"
            )

        from src.config import get_config
        config = get_config()

        self._app_id = app_id or getattr(config, 'feishu_app_id', None)
        self._app_secret = app_secret or getattr(config, 'feishu_app_secret', None)
        configured_domain = (
            domain
            if domain is not None
            else getattr(config, 'feishu_domain', 'feishu')
        )
        self._domain = _resolve_feishu_domain(configured_domain)

        if not self._app_id or not self._app_secret:
            raise ValueError(
                "Feishu Stream 방식에는 FEISHU_APP_ID와 FEISHU_APP_SECRET 설정이 필요합니다"
            )

        self._ws_client: Optional[ws.Client] = None
        self._reply_client: Optional[FeishuReplyClient] = None
        self._message_handler: Optional[FeishuStreamHandler] = None
        self._background_thread: Optional[threading.Thread] = None
        self._running = False

    def _create_message_handler(self) -> Callable[[BotMessage], BotResponse]:
        """메시지 처리 함수 만들기"""

        def handle_message(message: BotMessage) -> BotResponse:
            from bot.dispatcher import get_dispatcher
            dispatcher = get_dispatcher()
            return dispatcher.dispatch(message)

        return handle_message

    def _create_event_handler(self) -> 'lark.EventDispatcherHandler':
        """이벤트 분배 처리기 만들기"""
        # 답장 클라이언트 만들기
        self._reply_client = FeishuReplyClient(
            self._app_id,
            self._app_secret,
            domain=self._domain,
        )

        # 메시지 처리기 만들기
        handler = FeishuStreamHandler(
            self._create_message_handler(),
            self._reply_client
        )
        self._message_handler = handler

        # 이벤트 처리기 만들고 등록
        # 참고: 상시 연결 방식에서는 encrypt_key와 verification_token이 꼭 필요하지는 않음
        # 하지만 SDK가 값을 요구함(빈 문자열 가능)
        from src.config import get_config
        config = get_config()

        encrypt_key = getattr(config, 'feishu_encrypt_key', '') or ''
        verification_token = getattr(config, 'feishu_verification_token', '') or ''

        event_handler = lark.EventDispatcherHandler.builder(
            encrypt_key=encrypt_key,
            verification_token=verification_token,
            level=lark.LogLevel.WARNING
        ).register_p2_im_message_receive_v1(
            handler.handle_message
        ).build()

        return event_handler

    def start(self) -> None:
        """
        Stream 클라이언트 시작(블로킹)

        클라이언트가 멈출 때까지 현재 스레드를 막습니다.
        """
        logger.info("[Feishu Stream] 시작하는 중...")

        # 이벤트 처리기 만들기
        event_handler = self._create_event_handler()

        # WebSocket 클라이언트 만들기
        self._ws_client = ws.Client(
            app_id=self._app_id,
            app_secret=self._app_secret,
            event_handler=event_handler,
            domain=self._domain,
            log_level=lark.LogLevel.WARNING,
            auto_reconnect=True
        )

        self._running = True
        logger.info("[Feishu Stream] 클라이언트 시작됨, 메시지 기다리는 중...")

        # 시작(블로킹)
        self._ws_client.start()

    def start_background(self) -> None:
        """
        백그라운드 스레드에서 Stream 클라이언트 시작(논블로킹)

        다른 서비스(예: WebUI)와 함께 돌릴 때 씁니다.
        """
        if self._background_thread and self._background_thread.is_alive():
            logger.warning("[Feishu Stream] 클라이언트가 이미 실행 중")
            return

        self._running = True
        self._background_thread = threading.Thread(
            target=self._run_in_background,
            daemon=True,
            name="FeishuStreamClient"
        )
        self._background_thread.start()
        logger.info("[Feishu Stream] 백그라운드 클라이언트 시작됨")

    def _run_in_background(self) -> None:
        """백그라운드 실행(예외 처리와 재연결)"""
        import time

        while self._running:
            try:
                self.start()
            except Exception as e:
                logger.error(f"[Feishu Stream] 실행 예외: {e}")
                if self._running:
                    logger.info("[Feishu Stream] 5초 후 재연결...")
                    time.sleep(5)

    def stop(self) -> None:
        """클라이언트 중지"""
        self._running = False
        if self._message_handler is not None:
            self._message_handler.shutdown(wait=False)
        logger.info("[Feishu Stream] 클라이언트 중지됨")

    @property
    def is_running(self) -> bool:
        """실행 중인지 여부"""
        return self._running


# 전역 클라이언트 인스턴스
_stream_client: Optional[FeishuStreamClient] = None


def get_feishu_stream_client() -> Optional[FeishuStreamClient]:
    """전역 Stream 클라이언트 인스턴스 가져오기"""
    global _stream_client

    if _stream_client is None and FEISHU_SDK_AVAILABLE:
        try:
            _stream_client = FeishuStreamClient()
        except (ImportError, ValueError) as e:
            logger.warning(f"[Feishu Stream] 클라이언트를 만들 수 없음: {e}")
            return None

    return _stream_client


def start_feishu_stream_background() -> bool:
    """
    백그라운드에서 Feishu Stream 클라이언트 시작

    Returns:
        시작 성공 여부
    """
    client = get_feishu_stream_client()
    if client:
        client.start_background()
        return True
    return False
