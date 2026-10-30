# -*- coding: utf-8 -*-
"""
Slack 알림 발송 서비스

역할:
1. Slack Bot API 또는 Incoming Webhook으로 Slack 메시지 발송
   (둘 다 설정되면 Bot API 우선 사용 - 텍스트와 이미지가 같은 채널로 가게 함)
"""
import logging
import json
from typing import Optional

import requests

from src.config import Config
from src.formatters import chunk_content_by_max_bytes, strip_hidden_markdown_metadata

logger = logging.getLogger(__name__)

# Slack Block Kit의 section block 하나당 text 필드 상한은 3000자
_BLOCK_TEXT_LIMIT = 3000
# Slack chat.postMessage / Webhook의 text 필드 상한은 약 40000자, 여유 있게 39000으로 잡음
_TEXT_LIMIT = 39000


class SlackSender:

    def __init__(self, config: Config):
        """
        Slack 설정 초기화

        Args:
            config: 설정 객체
        """
        self._slack_webhook_url = getattr(config, 'slack_webhook_url', None)
        self._slack_bot_token = getattr(config, 'slack_bot_token', None)
        self._slack_channel_id = getattr(config, 'slack_channel_id', None)
        self._webhook_verify_ssl = getattr(config, 'webhook_verify_ssl', True)

    @property
    def _use_bot(self) -> bool:
        """Bot 설정이 다 있으면 Bot API를 우선 사용해 텍스트와 이미지가 같은 경로로 가게 함."""
        return bool(self._slack_bot_token and self._slack_channel_id)

    def _is_slack_configured(self) -> bool:
        """Slack 설정이 다 갖춰졌는지 확인 (Webhook 또는 Bot API 지원)"""
        return self._use_bot or bool(self._slack_webhook_url)

    def send_to_slack(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        Slack에 메시지 푸시 (Webhook, Bot API 지원)

        전송 우선순위는 _send_slack_image()와 같음: Bot > Webhook.
        텍스트는 Webhook, 이미지는 Bot으로 가서 서로 다른 채널에 올라가는 일을 막음.

        Args:
            content: Markdown 형식 메시지 내용

        Returns:
            발송 성공 여부
        """
        sanitized_content = strip_hidden_markdown_metadata(content).strip()
        if not sanitized_content:
            logger.warning("Slack 메시지 내용이 비어 있어 푸시 건너뜀")
            return False

        # 바이트 기준으로 나눠 메시지 1건이 상한을 넘지 않게 함
        try:
            chunks = chunk_content_by_max_bytes(sanitized_content, _TEXT_LIMIT, add_page_marker=True)
        except Exception as e:
            logger.error(f"Slack 메시지 나누기 실패: {e}, 통째로 발송 시도.")
            chunks = [sanitized_content]

        # Bot API 우선 사용 (_send_slack_image와 동일)
        if self._use_bot:
            return all(self._send_slack_bot(chunk, timeout_seconds=timeout_seconds) for chunk in chunks)

        # 그다음 Webhook 사용
        if self._slack_webhook_url:
            return all(self._send_slack_webhook(chunk, timeout_seconds=timeout_seconds) for chunk in chunks)

        logger.warning("Slack 설정이 불완전해 푸시 건너뜀")
        return False

    def _build_blocks(self, content: str) -> list:
        """
        내용을 Slack Block Kit 형식으로 구성

        내용이 section block 하나의 한도를 넘으면 여러 block으로 자동 분할함.
        """
        blocks = []
        # block text 상한 기준으로 분할
        pos = 0
        while pos < len(content):
            segment = content[pos:pos + _BLOCK_TEXT_LIMIT]
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": segment
                }
            })
            pos += _BLOCK_TEXT_LIMIT
        return blocks

    def _send_slack_webhook(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        Incoming Webhook으로 Slack에 메시지 발송

        Args:
            content: 메시지 내용

        Returns:
            발송 성공 여부
        """
        try:
            payload = {
                "text": content,
                "blocks": self._build_blocks(content),
            }
            response = requests.post(
                self._slack_webhook_url,
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                headers={'Content-Type': 'application/json; charset=utf-8'},
                timeout=timeout_seconds or 15,
                verify=self._webhook_verify_ssl,
            )
            if response.status_code == 200 and response.text == "ok":
                logger.info("Slack Webhook 메시지 발송 완료")
                return True
            logger.error(f"Slack Webhook 발송 실패: HTTP {response.status_code} {response.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"Slack Webhook 발송 중 예외: {e}")
            return False

    def _send_slack_bot(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        Bot API(chat.postMessage)로 Slack에 메시지 발송

        Args:
            content: 메시지 내용

        Returns:
            발송 성공 여부
        """
        try:
            headers = {
                'Authorization': f'Bearer {self._slack_bot_token}',
                'Content-Type': 'application/json; charset=utf-8',
            }
            payload = {
                "channel": self._slack_channel_id,
                "text": content,
                "blocks": self._build_blocks(content),
            }
            response = requests.post(
                'https://slack.com/api/chat.postMessage',
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                headers=headers,
                timeout=timeout_seconds or 15,
            )
            result = response.json()
            if result.get("ok"):
                logger.info("Slack Bot 메시지 발송 완료")
                return True
            logger.error(f"Slack Bot 발송 실패: {result.get('error', 'unknown')}")
            return False
        except Exception as e:
            logger.error(f"Slack Bot 발송 중 예외: {e}")
            return False

    def _send_slack_image(self, image_bytes: bytes, fallback_content: str = "") -> bool:
        """
        Slack에 이미지 발송

        Bot 모드에서는 files.getUploadURLExternal + files.completeUploadExternal 사용
        (Slack 새 파일 업로드 API). Webhook 모드에서는 텍스트로 대체.

        Args:
            image_bytes: PNG 이미지 바이트
            fallback_content: 이미지 발송 실패 시 대신 보낼 텍스트

        Returns:
            발송 성공 여부
        """
        # Bot 모드: 새 파일 업로드 API 사용
        if self._use_bot:
            headers = {'Authorization': f'Bearer {self._slack_bot_token}'}
            try:
                # Step 1: 업로드 URL 받기
                resp1 = requests.post(
                    'https://slack.com/api/files.getUploadURLExternal',
                    headers=headers,
                    data={
                        'filename': 'report.png',
                        'length': len(image_bytes),
                    },
                    timeout=30,
                )
                result1 = resp1.json()
                if not result1.get("ok"):
                    logger.error("Slack 업로드 URL 받기 실패: %s", result1.get('error', 'unknown'))
                    raise RuntimeError(result1.get('error', 'unknown'))

                upload_url = result1['upload_url']
                file_id = result1['file_id']

                # Step 2: 파일 내용 업로드 (raw body, multipart 사용 불가)
                resp2 = requests.post(
                    upload_url,
                    data=image_bytes,
                    headers={'Content-Type': 'application/octet-stream'},
                    timeout=30,
                )
                if resp2.status_code != 200:
                    logger.error("Slack 파일 업로드 실패: HTTP %s", resp2.status_code)
                    raise RuntimeError(f"HTTP {resp2.status_code}")

                # Step 3: 업로드 마무리 후 채널에 공유
                resp3 = requests.post(
                    'https://slack.com/api/files.completeUploadExternal',
                    headers={**headers, 'Content-Type': 'application/json'},
                    json={
                        'files': [{'id': file_id, 'title': '股票分析报告'}],
                        'channel_id': self._slack_channel_id,
                    },
                    timeout=30,
                )
                result3 = resp3.json()
                if result3.get("ok"):
                    logger.info("Slack Bot 이미지 발송 완료")
                    return True
                logger.error("Slack 업로드 마무리 실패: %s", result3.get('error', 'unknown'))
            except Exception as e:
                logger.error("Slack Bot 이미지 발송 중 예외: %s", e)

        # Webhook 모드이거나 Bot 업로드 실패: 텍스트로 대체
        if fallback_content:
            logger.info("Slack 이미지 미지원 또는 실패, 텍스트로 대신 발송")
            return self.send_to_slack(fallback_content)

        logger.warning("Slack 이미지 발송 실패, 대체 내용도 없음")
        return False
