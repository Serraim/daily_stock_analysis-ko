# -*- coding: utf-8 -*-
"""
Discord 알림 발송 서비스

역할:
1. webhook 또는 Discord bot API로 Discord 메시지 발송
"""
import logging
import time
from typing import Optional

import requests

from src.config import Config
from src.formatters import (
    MIN_MAX_WORDS,
    chunk_content_by_max_words,
    strip_hidden_markdown_metadata,
)


logger = logging.getLogger(__name__)


DISCORD_MAX_CONTENT_LENGTH = 2000
DISCORD_MAX_RETRIES = 3
DISCORD_CHUNK_SLEEP_SECONDS = 1


class DiscordSender:
    
    def __init__(self, config: Config):
        """
        Discord 설정 초기화

        Args:
            config: 설정 객체
        """
        self._discord_config = {
            'bot_token': getattr(config, 'discord_bot_token', None),
            'channel_id': getattr(config, 'discord_main_channel_id', None),
            'webhook_url': getattr(config, 'discord_webhook_url', None),
        }
        self._discord_max_words = self._normalize_max_words(
            getattr(config, 'discord_max_words', DISCORD_MAX_CONTENT_LENGTH)
        )
        self._webhook_verify_ssl = getattr(config, 'webhook_verify_ssl', True)

    @staticmethod
    def _normalize_max_words(value) -> int:
        try:
            configured = int(value)
        except (TypeError, ValueError):
            configured = DISCORD_MAX_CONTENT_LENGTH
        return max(MIN_MAX_WORDS, min(configured, DISCORD_MAX_CONTENT_LENGTH))
    
    def _is_discord_configured(self) -> bool:
        """Discord 설정이 다 갖춰졌는지 확인 (Bot 또는 Webhook 지원)"""
        # Webhook 또는 Bot Token+Channel이 다 설정돼 있으면 사용 가능으로 봄
        bot_ok = bool(self._discord_config['bot_token'] and self._discord_config['channel_id'])
        webhook_ok = bool(self._discord_config['webhook_url'])
        return bot_ok or webhook_ok
    
    def send_to_discord(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        Discord에 메시지 푸시 (Webhook, Bot API 지원)
        
        Args:
            content: Markdown 형식 메시지 내용
            
        Returns:
            발송 성공 여부
        """
        sanitized_content = strip_hidden_markdown_metadata(content).strip()
        if not sanitized_content:
            logger.warning("Discord 메시지 내용이 비어 있어 푸시 건너뜀")
            return False

        # 내용을 나눠 메시지 1건이 Discord 제한을 넘지 않게 함
        chunks = self._split_discord_content(sanitized_content)

        # Webhook 우선 사용 (설정이 간단하고 권한이 낮음)
        if self._discord_config['webhook_url']:
            return self._send_discord_chunks(
                chunks,
                self._send_discord_webhook,
                "Webhook",
                timeout_seconds=timeout_seconds,
            )

        # 그다음 Bot API 사용 (권한이 높고 channel_id 필요)
        if self._discord_config['bot_token'] and self._discord_config['channel_id']:
            return self._send_discord_chunks(
                chunks,
                self._send_discord_bot,
                "Bot",
                timeout_seconds=timeout_seconds,
            )

        logger.warning("Discord 설정이 불완전해 푸시 건너뜀")
        return False

    def _split_discord_content(self, content: str) -> list[str]:
        """Discord content 상한에 맞춰 메시지 분할."""
        try:
            chunks = chunk_content_by_max_words(content, self._discord_max_words)
            if len(chunks) > 1:
                chunks = chunk_content_by_max_words(
                    content,
                    self._discord_max_words,
                    add_page_marker=True,
                )
            return chunks
        except ValueError as e:
            logger.error("Discord 메시지 나누기 실패: %s", e)
            return chunk_content_by_max_words(
                content,
                DISCORD_MAX_CONTENT_LENGTH,
                add_page_marker=True,
            )

    def _send_discord_chunks(
        self,
        chunks: list[str],
        send_once,
        channel_name: str,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """Discord 메시지를 조각별로 발송. 한 조각이 실패해도 다음 조각은 계속 시도함."""
        total_chunks = len(chunks)
        success_count = 0

        if total_chunks > 1:
            logger.info("Discord %s 나눠서 발송: 총 %d개 묶음", channel_name, total_chunks)

        for i, chunk in enumerate(chunks):
            if send_once(chunk, timeout_seconds=timeout_seconds):
                success_count += 1
                if total_chunks > 1:
                    logger.info("Discord %s %d/%d번째 묶음 발송 완료", channel_name, i + 1, total_chunks)
            else:
                logger.error("Discord %s %d/%d번째 묶음 발송 실패", channel_name, i + 1, total_chunks)

            if i < total_chunks - 1:
                time.sleep(DISCORD_CHUNK_SLEEP_SECONDS)

        return success_count == total_chunks

  
    def _send_discord_webhook(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        Webhook으로 Discord에 메시지 발송
        
        Discord Webhook은 Markdown 형식 지원
        
        Args:
            content: Markdown 형식 메시지 내용
            
        Returns:
            발송 성공 여부
        """
        payload = {
            'content': content,
            'username': 'A股分析机器人',
            'avatar_url': 'https://picsum.photos/200'
        }

        return self._post_discord_message(
            self._discord_config['webhook_url'],
            payload,
            success_statuses=(200, 204),
            verify=self._webhook_verify_ssl,
            timeout_seconds=timeout_seconds,
            channel_name="Webhook",
        )
    
    def _send_discord_bot(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        Bot API로 Discord에 메시지 발송
        
        Args:
            content: Markdown 형식 메시지 내용
            
        Returns:
            발송 성공 여부
        """
        headers = {
            'Authorization': f'Bot {self._discord_config["bot_token"]}',
            'Content-Type': 'application/json'
        }
        payload = {'content': content}
        url = f'https://discord.com/api/v10/channels/{self._discord_config["channel_id"]}/messages'

        return self._post_discord_message(
            url,
            payload,
            headers=headers,
            success_statuses=(200,),
            timeout_seconds=timeout_seconds,
            channel_name="Bot",
        )

    def _post_discord_message(
        self,
        url: str,
        payload: dict,
        *,
        success_statuses: tuple[int, ...],
        headers: Optional[dict] = None,
        verify: Optional[bool] = None,
        timeout_seconds: Optional[float] = None,
        channel_name: str,
    ) -> bool:
        """Discord 메시지 1건 발송. 429/5xx는 Telegram과 같은 방식의 제한된 재시도로 처리."""
        request_kwargs = {
            'json': payload,
            'timeout': timeout_seconds or 10,
        }
        if headers:
            request_kwargs['headers'] = headers
        if verify is not None:
            request_kwargs['verify'] = verify

        for attempt in range(1, DISCORD_MAX_RETRIES + 1):
            try:
                response = requests.post(url, **request_kwargs)
            except requests.exceptions.RequestException as e:
                if attempt < DISCORD_MAX_RETRIES:
                    delay = 2 ** attempt
                    logger.warning(
                        "Discord %s 요청 오류 (%d/%d): %s, %s초 뒤 재시도",
                        channel_name,
                        attempt,
                        DISCORD_MAX_RETRIES,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                logger.error("Discord %s 재시도 후에도 요청 실패: %s", channel_name, e)
                return False

            if response.status_code in success_statuses:
                logger.info("Discord %s 메시지 발송 완료", channel_name)
                return True

            if response.status_code == 429 and attempt < DISCORD_MAX_RETRIES:
                retry_after = self._get_retry_after_seconds(response, attempt)
                logger.warning(
                    "Discord %s 빈도 제한 걸림, %s초 뒤 재시도 (%d/%d)",
                    channel_name,
                    retry_after,
                    attempt,
                    DISCORD_MAX_RETRIES,
                )
                time.sleep(retry_after)
                continue

            if response.status_code >= 500 and attempt < DISCORD_MAX_RETRIES:
                delay = 2 ** attempt
                logger.warning(
                    "Discord %s 서버 오류 HTTP %s (%d/%d), %s초 뒤 재시도",
                    channel_name,
                    response.status_code,
                    attempt,
                    DISCORD_MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue

            logger.error(
                "Discord %s 발송 실패: %s %s",
                channel_name,
                response.status_code,
                response.text,
            )
            return False

        return False

    @staticmethod
    def _get_retry_after_seconds(response, attempt: int) -> float:
        try:
            retry_after = response.json().get('retry_after')
            if retry_after is not None:
                return max(0.0, float(retry_after))
        except (AttributeError, TypeError, ValueError):
            pass

        try:
            retry_after = response.headers.get('Retry-After')
            if retry_after is not None:
                return max(0.0, float(retry_after))
        except AttributeError:
            pass

        return float(2 ** attempt)
