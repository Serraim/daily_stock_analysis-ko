# -*- coding: utf-8 -*-
"""
AstrBot 알림 발송 서비스

역할:
1. Astrbot API로 AstrBot 메시지 발송
"""
import logging
import json
import hmac
import hashlib
from typing import Optional

import requests

from src.config import Config
from src.formatters import markdown_to_html_document, strip_hidden_markdown_metadata


logger = logging.getLogger(__name__)


class AstrbotSender:
    
    def __init__(self, config: Config):
        """
        AstrBot 설정 초기화

        Args:
            config: 설정 객체
        """
        self._astrbot_config = {
            'astrbot_url': getattr(config, 'astrbot_url', None),
            'astrbot_token': getattr(config, 'astrbot_token', None),
        }
        self._webhook_verify_ssl = getattr(config, 'webhook_verify_ssl', True)
        
    def _is_astrbot_configured(self) -> bool:
        """AstrBot 설정이 다 갖춰졌는지 확인 (Bot 또는 Webhook 지원)"""
        # URL만 설정돼 있으면 사용 가능으로 봄
        url_ok = bool(self._astrbot_config['astrbot_url'])
        return url_ok

    def send_to_astrbot(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        AstrBot에 메시지 푸시 (어댑터로 지원)

        Args:
            content: Markdown 형식 메시지 내용

        Returns:
            발송 성공 여부
        """
        if self._astrbot_config['astrbot_url']:
            return self._send_astrbot(content, timeout_seconds=timeout_seconds)

        logger.warning("AstrBot 설정이 불완전해 푸시 건너뜀")
        return False


    def _send_astrbot(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        import time
        """
        Bot API로 AstrBot에 메시지 발송

        Args:
            content: Markdown 형식 메시지 내용

        Returns:
            발송 성공 여부
        """

        sanitized_content = strip_hidden_markdown_metadata(content).strip()
        html_content = markdown_to_html_document(sanitized_content)

        try:
            payload = {
                'content': html_content
            }
            signature =  ""
            timestamp = str(int(time.time()))
            if self._astrbot_config['astrbot_token']:
                """요청 서명 계산"""
                payload_json = json.dumps(payload, sort_keys=True)
                sign_data = f"{timestamp}.{payload_json}".encode('utf-8')
                key = self._astrbot_config['astrbot_token']
                signature = hmac.new(
                    key.encode('utf-8'),
                    sign_data,
                    hashlib.sha256
                ).hexdigest()
            url = self._astrbot_config['astrbot_url']
            response = requests.post(
                url, json=payload, timeout=timeout_seconds or 10,
                headers={
                    "Content-Type": "application/json",
                    "X-Signature": signature,
                    "X-Timestamp": timestamp
                },
                verify=self._webhook_verify_ssl
            )

            if response.status_code == 200:
                logger.info("AstrBot 메시지 발송 완료")
                return True
            else:
                logger.error(f"AstrBot 발송 실패: {response.status_code} {response.text}")
                return False
        except Exception as e:
            logger.error(f"AstrBot 발송 중 예외: {e}")
            return False
