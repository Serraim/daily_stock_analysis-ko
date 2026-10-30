# -*- coding: utf-8 -*-
"""
Server酱3 알림 발송 서비스

역할:
1. Server酱3 API로 Server酱3 메시지 발송
"""
import logging
from typing import Optional
import requests
from datetime import datetime
import re

from src.config import Config
from src.formatters import strip_hidden_markdown_metadata


logger = logging.getLogger(__name__)


class Serverchan3Sender:
    
    def __init__(self, config: Config):
        """
        Server酱3 설정 초기화

        Args:
            config: 설정 객체
        """
        self._serverchan3_sendkey = getattr(config, 'serverchan3_sendkey', None)
        
    def send_to_serverchan3(
        self,
        content: str,
        title: Optional[str] = None,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        Server酱3에 메시지 푸시

        Server酱3 API 형식:
        POST https://sctapi.ftqq.com/{sendkey}.send
        또는
        POST https://{num}.push.ft07.com/send/{sendkey}.send
        {
            "title": "메시지 제목",
            "desp": "메시지 내용",
            "options": {}
        }

        Server酱3 특징:
        - 중국 국내 푸시 서비스. 여러 중국 휴대폰 제조사 푸시 채널을 지원해 앱이 백그라운드에 없어도 푸시 가능
        - 쓰기 쉬운 API

        Args:
            content: 메시지 내용 (Markdown 형식)
            title: 메시지 제목 (선택)

        Returns:
            발송 성공 여부
        """
        if not self._serverchan3_sendkey:
            logger.warning("Server酱3 SendKey 미설정, 푸시 건너뜀")
            return False

        # 메시지 제목 처리
        if title is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
            title = f"📈 股票分析报告 - {date_str}"
        sanitized_content = strip_hidden_markdown_metadata(content).strip()

        try:
            # sendkey 형식에 맞춰 URL 만들기
            sendkey = self._serverchan3_sendkey
            if sendkey.startswith('sctp'):
                match = re.match(r'sctp(\d+)t', sendkey)
                if match:
                    num = match.group(1)
                    url = f"https://{num}.push.ft07.com/send/{sendkey}.send"
                else:
                    logger.error("Invalid sendkey format for sctp")
                    return False
            else:
                url = f"https://sctapi.ftqq.com/{sendkey}.send"

            # 요청 파라미터 구성
            params = {
                'title': title,
                'desp': sanitized_content,
                'options': {}
            }

            # 요청 보내기
            headers = {
                'Content-Type': 'application/json;charset=utf-8'
            }
            response = requests.post(url, json=params, headers=headers, timeout=timeout_seconds or 10)

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Server酱3 메시지 발송 완료: {result}")
                return True
            else:
                logger.error(f"Server酱3 요청 실패: HTTP {response.status_code}")
                logger.error(f"응답 내용: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Server酱3 메시지 발송 실패: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
