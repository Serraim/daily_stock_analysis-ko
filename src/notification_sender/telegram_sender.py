# -*- coding: utf-8 -*-
"""
Telegram 알림 발송 서비스

역할:
1. Telegram Bot API로 텍스트 메시지 발송
2. Telegram Bot API로 이미지 메시지 발송
"""
import logging
from typing import Optional
import requests
import time
import re

from src.config import Config
from src.formatters import _custom_unit_to_index, strip_hidden_markdown_metadata, utf16_len


logger = logging.getLogger(__name__)


class TelegramSender:

    def __init__(self, config: Config):
        """
        Telegram 설정 초기화

        Args:
            config: 설정 객체
        """
        self._telegram_config = {
            'bot_token': getattr(config, 'telegram_bot_token', None),
            'chat_id': getattr(config, 'telegram_chat_id', None),
            'message_thread_id': getattr(config, 'telegram_message_thread_id', None),
        }

    def _is_telegram_configured(self) -> bool:
        """Telegram 설정이 다 갖춰졌는지 확인"""
        return bool(self._telegram_config['bot_token'] and self._telegram_config['chat_id'])

    def send_to_telegram(
        self,
        content: str,
        *,
        chat_id: Optional[str] = None,
        message_thread_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        Telegram 봇에 메시지 푸시

        Telegram Bot API 형식:
        POST https://api.telegram.org/bot<token>/sendMessage
        {
            "chat_id": "xxx",
            "text": "메시지 내용",
            "parse_mode": "Markdown"
        }

        Args:
            content: 메시지 내용 (Markdown 형식)

        Returns:
            발송 성공 여부
        """
        target_chat_id = chat_id if chat_id is not None else self._telegram_config.get("chat_id")
        target_message_thread_id = (
            message_thread_id
            if message_thread_id is not None
            else self._telegram_config.get("message_thread_id")
        )

        if not (self._telegram_config["bot_token"] and target_chat_id):
            logger.warning("Telegram 설정이 불완전해 푸시 건너뜀")
            return False

        bot_token = self._telegram_config['bot_token']
        chat_id = target_chat_id
        message_thread_id = target_message_thread_id

        try:
            # Telegram API 엔드포인트
            api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

            # Telegram 메시지 최대 길이 4096 (UTF-16 code unit 기준)
            max_length = 4096

            sanitized_content = strip_hidden_markdown_metadata(content).strip()
            if not sanitized_content:
                logger.warning("Telegram 메시지 내용이 비어 있어 푸시 건너뜀")
                return False

            telegram_content = self._convert_to_telegram_markdown(sanitized_content)

            if utf16_len(telegram_content) <= max_length:
                # 한 번에 발송
                return self._send_telegram_message(
                    api_url,
                    chat_id,
                    sanitized_content,
                    message_thread_id,
                    timeout_seconds=timeout_seconds,
                )
            else:
                # Markdown 이스케이프를 마친 최종 payload 기준으로 나눔 (이스케이프 문자 때문에 요청이 상한을 넘지 않게)
                return self._send_telegram_chunked(
                    api_url,
                    chat_id,
                    telegram_content,
                    max_length,
                    message_thread_id,
                    timeout_seconds=timeout_seconds,
                )

        except Exception as e:
            logger.error(f"Telegram 메시지 발송 실패: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False

    def _send_telegram_message(
        self,
        api_url: str,
        chat_id: str,
        text: str,
        message_thread_id: Optional[str] = None,
        *,
        timeout_seconds: Optional[float] = None,
        markdown_converted: bool = False,
    ) -> bool:
        """Send a single Telegram message with exponential backoff retry (Fixes #287)"""
        # Convert Markdown to Telegram-compatible format
        telegram_text = text if markdown_converted else self._convert_to_telegram_markdown(text)

        payload = {
            "chat_id": chat_id,
            "text": telegram_text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }

        if message_thread_id:
            payload['message_thread_id'] = message_thread_id

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(api_url, json=payload, timeout=timeout_seconds or 10)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt < max_retries:
                    delay = 2 ** attempt  # 2s, 4s
                    logger.warning(f"Telegram request failed (attempt {attempt}/{max_retries}): {e}, "
                                   f"retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Telegram request failed after {max_retries} attempts: {e}")
                    return False

            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    logger.info("Telegram 메시지 발송 완료")
                    return True
                else:
                    error_desc = result.get('description', '알 수 없는 오류')
                    logger.error(f"Telegram 오류 응답: {error_desc}")

                    # If Markdown parsing failed, fall back to plain text
                    if self._should_fallback_to_plain_text(error_desc=error_desc):
                        if self._send_plain_text_fallback(api_url, payload, text, timeout_seconds=timeout_seconds):
                            return True

                    return False
            elif response.status_code == 429:
                # Rate limited — respect Retry-After header
                retry_after = int(response.headers.get('Retry-After', 2 ** attempt))
                if attempt < max_retries:
                    logger.warning(f"Telegram rate limited, retrying in {retry_after}s "
                                   f"(attempt {attempt}/{max_retries})...")
                    time.sleep(retry_after)
                    continue
                else:
                    logger.error(f"Telegram rate limited after {max_retries} attempts")
                    return False
            else:
                if attempt < max_retries and response.status_code >= 500:
                    delay = 2 ** attempt
                    logger.warning(f"Telegram server error HTTP {response.status_code} "
                                   f"(attempt {attempt}/{max_retries}), retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                if self._should_fallback_to_plain_text(response_text=response.text):
                    if self._send_plain_text_fallback(api_url, payload, text, timeout_seconds=timeout_seconds):
                        return True
                logger.error(f"Telegram 요청 실패: HTTP {response.status_code}")
                logger.error(f"응답 내용: {response.text}")
                return False

        return False

    @staticmethod
    def _should_fallback_to_plain_text(error_desc: str = "", response_text: str = "") -> bool:
        """Detect Telegram Markdown parsing failures that should retry as plain text."""
        haystack = f"{error_desc}\n{response_text}".lower()
        markers = (
            "can't parse entities",
            "can't parse entity",
            "can't find end of the entity",
            "parse entities",
            "parse_mode",
            "markdown",
        )
        return any(marker in haystack for marker in markers)

    def _send_plain_text_fallback(
        self,
        api_url: str,
        payload: dict,
        text: str,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """Retry Telegram send without parse_mode when Markdown parsing fails."""
        logger.info("Telegram Markdown 해석 실패, 일반 텍스트로 다시 발송 시도...")
        plain_payload = dict(payload)
        plain_payload.pop('parse_mode', None)
        plain_payload['text'] = text

        try:
            response = requests.post(api_url, json=plain_payload, timeout=timeout_seconds or 10)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.error(f"Telegram plain-text fallback failed: {e}")
            return False

        if response.status_code == 200:
            try:
                result = response.json()
            except ValueError:
                logger.error("Telegram 일반 텍스트 대체 발송 실패: 응답이 올바른 JSON이 아님")
                logger.error(f"응답 내용: {response.text}")
                return False

            if result.get('ok'):
                logger.info("Telegram 메시지 발송 완료 (일반 텍스트)")
                return True

            logger.error("Telegram 일반 텍스트 대체 발송 실패: Telegram API가 ok=false 반환")
            logger.error(f"응답 내용: {response.text}")
            return False

        logger.error(f"Telegram 일반 텍스트 대체 발송 실패: HTTP {response.status_code}")
        logger.error(f"응답 내용: {response.text}")
        return False

    def _send_telegram_chunked(
        self,
        api_url: str,
        chat_id: str,
        content: str,
        max_length: int,
        message_thread_id: Optional[str] = None,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """변환된 Telegram Markdown payload 기준으로 긴 메시지를 나눠서 발송."""
        # 문단 단위로 나눔
        sections = content.split("\n---\n")
        delimiter = "\n---\n"
        delimiter_length = len(delimiter)

        current_chunk = []
        current_length = 0
        all_success = True
        chunk_index = 1

        def _flush_chunk() -> bool:
            nonlocal current_chunk, current_length, chunk_index, all_success
            if not current_chunk:
                return all_success

            chunk_content = "\n---\n".join(current_chunk)
            logger.info(f"Telegram 메시지 조각 {chunk_index} 발송 중...")
            chunk_index += 1
            current_chunk = []
            current_length = 0
            if not self._send_telegram_message(
                api_url,
                chat_id,
                chunk_content,
                message_thread_id,
                timeout_seconds=timeout_seconds,
                markdown_converted=True,
            ):
                all_success = False
            return all_success

        def _split_long_section(section: str, limit: int) -> list[str]:
            chunks: list[str] = []
            while utf16_len(section) > limit:
                cut = max(1, _custom_unit_to_index(section, limit, utf16_len))
                chunks.append(section[:cut])
                section = section[cut:]
            chunks.append(section)
            return chunks

        for section in sections:
            if utf16_len(section) > max_length:
                # 한 문단이 상한을 넘으면 강제로 자름 (“\\n---\\n” 경계만 믿다가 너무 긴 덩어리를 보내는 일 방지)
                if not _flush_chunk():
                    return False
                for long_chunk in _split_long_section(section, max_length):
                    logger.info(f"Telegram 메시지 조각 {chunk_index} 발송 중...")
                    chunk_index += 1
                    if not self._send_telegram_message(
                        api_url,
                        chat_id,
                        long_chunk,
                        message_thread_id,
                        timeout_seconds=timeout_seconds,
                        markdown_converted=True,
                    ):
                        all_success = False
                continue

            additional_length = utf16_len(section)
            if current_chunk:
                additional_length += delimiter_length

            if current_length + additional_length > max_length:
                _flush_chunk()
                current_chunk = [section]
                current_length = utf16_len(section)
                continue

            current_chunk.append(section)
            current_length += additional_length

        # 마지막 조각 발송
        if not _flush_chunk():
            return False

        return all_success

    def _send_telegram_photo(self, image_bytes: bytes) -> bool:
        """Send image via Telegram sendPhoto API (Issue #289)."""
        if not self._is_telegram_configured():
            return False
        bot_token = self._telegram_config['bot_token']
        chat_id = self._telegram_config['chat_id']
        message_thread_id = self._telegram_config.get('message_thread_id')
        api_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
        try:
            data = {"chat_id": chat_id}
            if message_thread_id:
                data['message_thread_id'] = message_thread_id
            files = {"photo": ("report.png", image_bytes, "image/png")}
            response = requests.post(api_url, data=data, files=files, timeout=30)
            if response.status_code == 200 and response.json().get('ok'):
                logger.info("Telegram 이미지 발송 완료")
                return True
            logger.error("Telegram 이미지 발송 실패: %s", response.text[:200])
            return False
        except Exception as e:
            logger.error("Telegram 이미지 발송 중 예외: %s", e)
            return False

    def _convert_to_telegram_markdown(self, text: str) -> str:
        """
        표준 Markdown을 Telegram이 지원하는 형식으로 변환

        Telegram Markdown 제약:
        - # 제목 미지원
        - **bold** 대신 *bold* 사용
        - _italic_ 사용
        """
        result = strip_hidden_markdown_metadata(text)

        # # 제목 표시 제거 (Telegram 미지원)
        result = re.sub(r'^#{1,6}\s+', '', result, flags=re.MULTILINE)

        # **bold**를 *bold*로 변환
        result = re.sub(r'\*\*(.+?)\*\*', r'*\1*', result)

        # Escape special characters for Telegram Markdown, but preserve link syntax [text](url)
        # Step 1: temporarily protect markdown links
        import uuid as _uuid
        _link_placeholder = f"__LINK_{_uuid.uuid4().hex[:8]}__"
        _links = []
        def _save_link(m):
            _links.append(m.group(0))
            return f"{_link_placeholder}{len(_links) - 1}"
        result = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _save_link, result)

        # Step 2: escape remaining special chars
        for char in ['[', ']', '(', ')']:
            result = result.replace(char, f'\\{char}')

        # Step 3: restore links
        for i, link in enumerate(_links):
            result = result.replace(f"{_link_placeholder}{i}", link)

        return result
