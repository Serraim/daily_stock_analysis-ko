# -*- coding: utf-8 -*-
"""
PushPlus 알림 발송 서비스

역할:
1. PushPlus API로 PushPlus 메시지 발송
"""
import logging
import time
from typing import Optional
from datetime import datetime
import requests

from src.config import Config
from src.formatters import chunk_content_by_max_bytes, strip_hidden_markdown_metadata


logger = logging.getLogger(__name__)


class PushplusSender:
    
    def __init__(self, config: Config):
        """
        PushPlus 설정 초기화

        Args:
            config: 설정 객체
        """
        self._pushplus_token = getattr(config, 'pushplus_token', None)
        self._pushplus_topic = getattr(config, 'pushplus_topic', None)
        self._pushplus_max_bytes = getattr(config, 'pushplus_max_bytes', 20000)
        
    def send_to_pushplus(
        self,
        content: str,
        title: Optional[str] = None,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        PushPlus에 메시지 푸시

        PushPlus API 형식:
        POST http://www.pushplus.plus/send
        {
            "token": "사용자 토큰",
            "title": "메시지 제목",
            "content": "메시지 내용",
            "template": "html/txt/json/markdown"
        }

        PushPlus 특징:
        - 중국 국내 푸시 서비스, 무료 사용량이 넉넉함
        - 위챗(WeChat) 공식계정 푸시 지원
        - 여러 메시지 형식 지원

        Args:
            content: 메시지 내용 (Markdown 형식)
            title: 메시지 제목 (선택)

        Returns:
            발송 성공 여부
        """
        if not self._pushplus_token:
            logger.warning("PushPlus Token 미설정, 푸시 건너뜀")
            return False

        api_url = "http://www.pushplus.plus/send"

        if title is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
            title = f"📈 股票分析报告 - {date_str}"
        sanitized_content = strip_hidden_markdown_metadata(content).strip()

        try:
            content_bytes = len(sanitized_content.encode('utf-8'))
            if content_bytes > self._pushplus_max_bytes:
                logger.info(
                    "PushPlus 메시지가 너무 김 (%s바이트/%s글자), 나눠서 발송",
                    content_bytes,
                    len(sanitized_content),
                )
                return self._send_pushplus_chunked(
                    api_url,
                    sanitized_content,
                    title,
                    self._pushplus_max_bytes,
                )

            return self._send_pushplus_message(
                api_url,
                sanitized_content,
                title,
                timeout_seconds=timeout_seconds,
            )
        except Exception as e:
            logger.error(f"PushPlus 메시지 발송 실패: {e}")
            return False

    def _send_pushplus_message(
        self,
        api_url: str,
        content: str,
        title: str,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        payload = {
            "token": self._pushplus_token,
            "title": title,
            "content": content,
            "template": "markdown",
        }

        if self._pushplus_topic:
            payload["topic"] = self._pushplus_topic

        response = requests.post(api_url, json=payload, timeout=timeout_seconds or 10)

        if response.status_code == 200:
            result = response.json()
            if result.get('code') == 200:
                logger.info("PushPlus 메시지 발송 완료")
                return True

            error_msg = result.get('msg', '알 수 없는 오류')
            logger.error(f"PushPlus 오류 응답: {error_msg}")
            return False

        logger.error(f"PushPlus 요청 실패: HTTP {response.status_code}")
        return False

    def _send_pushplus_chunked(self, api_url: str, content: str, title: str, max_bytes: int) -> bool:
        """긴 PushPlus 메시지를 나눠서 발송 (JSON payload 공간을 남겨 둠)."""
        budget = max(1000, max_bytes - 1500)
        chunks = chunk_content_by_max_bytes(content, budget, add_page_marker=True)
        total_chunks = len(chunks)
        success_count = 0

        logger.info(f"PushPlus 나눠서 발송: 총 {total_chunks}개 묶음")

        for i, chunk in enumerate(chunks):
            chunk_title = f"{title} ({i+1}/{total_chunks})" if total_chunks > 1 else title
            if self._send_pushplus_message(api_url, chunk, chunk_title):
                success_count += 1
                logger.info(f"PushPlus {i+1}/{total_chunks}번째 묶음 발송 완료")
            else:
                logger.error(f"PushPlus {i+1}/{total_chunks}번째 묶음 발송 실패")

            if i < total_chunks - 1:
                time.sleep(1)

        return success_count == total_chunks
