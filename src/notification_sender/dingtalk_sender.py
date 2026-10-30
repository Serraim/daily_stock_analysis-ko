# -*- coding: utf-8 -*-
import time
import hmac
import hashlib
import base64
import urllib.parse
import requests
import logging
from typing import Optional

from src.config import Config
from src.formatters import chunk_content_by_max_bytes, strip_hidden_markdown_metadata  # <-- 프로젝트 내장 분할 함수 가져오기

logger = logging.getLogger(__name__)

class DingtalkSender:
    def __init__(self, config: Config):
        self.webhook_url = config.dingtalk_webhook_url
        self.secret = config.dingtalk_secret

    def send_to_dingtalk(self, content: str, title: str = "", timeout_seconds: int = 10) -> bool:
        """딩톡(DingTalk) 그룹에 Markdown 메시지 발송 (Send DingTalk Markdown message)"""
        if not self.webhook_url:
            return False
        sanitized_content = strip_hidden_markdown_metadata(content).strip()

        # 1. 서명 로직 (Security Signature)
        if self.secret:
            timestamp = str(round(time.time() * 1000))
            secret_enc = self.secret.encode('utf-8')
            string_to_sign = f'{timestamp}\n{self.secret}'
            string_to_sign_enc = string_to_sign.encode('utf-8')
            hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
            
            if "?" in self.webhook_url:
                url = f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"
            else:
                url = f"{self.webhook_url}?timestamp={timestamp}&sign={sign}"
        else:
            url = self.webhook_url

        # 2. 제목 길이 제한: 지나치게 긴 제목이 JSON 바이트 예산을 너무 많이 쓰지 않게 함
        safe_title = (title[:100] + "...") if title and len(title) > 100 else title

        # 3. 분할 로직 (Chunking for DingTalk's 20,000 byte limit)
        # JSON 구조, 제목, 페이지 접미사에 드는 추가 용량으로 1000 bytes 여유분을 남겨 둠
        safe_max_bytes = 19000
        chunks = chunk_content_by_max_bytes(sanitized_content, max_bytes=safe_max_bytes)
        all_success = True

        for index, chunk in enumerate(chunks):
            text = f"### {safe_title}\n\n{chunk}" if index == 0 and safe_title else chunk
            
            display_title = safe_title or "通知 (Notification)"
            if len(chunks) > 1:
                display_title = f"{display_title} ({index + 1}/{len(chunks)})"
            
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": display_title,
                    "text": text
                }
            }
            headers = {'Content-Type': 'application/json'}

            # 4. 요청 보내기
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=timeout_seconds)
                response.raise_for_status()
                
                result = response.json()
                if result.get("errcode") == 0:
                    logger.info(f"딩톡 메시지 조각 {index + 1} 발송 완료 (Chunk {index + 1} sent successfully)")
                else:
                    logger.error(f"딩톡 메시지 조각 {index + 1} 발송 실패 (DingTalk API error): {result}")
                    all_success = False
            except Exception as e:
                logger.error(f"딩톡 메시지 발송 중 예외 (Failed to send DingTalk notification chunk {index + 1}): {e}")
                all_success = False
            
            if len(chunks) > 1 and index < len(chunks) - 1:
                time.sleep(0.5)

        return all_success
