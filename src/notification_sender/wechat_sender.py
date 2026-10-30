# -*- coding: utf-8 -*-
"""
Wechat 알림 발송 서비스

역할:
1. 위챗 워크(WeCom, 企业微信) Webhook으로 텍스트 메시지 발송
2. 위챗 워크 Webhook으로 이미지 메시지 발송
"""
import logging
import base64
import hashlib
import requests
import time
from typing import Optional

from src.config import Config
from src.formatters import chunk_content_by_max_bytes, strip_hidden_markdown_metadata


logger = logging.getLogger(__name__)


# WeChat Work image msgtype limit ~2MB (base64 payload)
WECHAT_IMAGE_MAX_BYTES = 2 * 1024 * 1024

class WechatSender:
    
    def __init__(self, config: Config):
        """
        위챗 워크 설정 초기화

        Args:
            config: 설정 객체
        """
        self._wechat_url = config.wechat_webhook_url
        self._wechat_max_bytes = getattr(config, 'wechat_max_bytes', 4000)
        self._wechat_msg_type = getattr(config, 'wechat_msg_type', 'markdown')
        self._webhook_verify_ssl = getattr(config, 'webhook_verify_ssl', True)
        
    def send_to_wechat(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        위챗 워크 봇에 메시지 푸시
        
        위챗 워크 Webhook 메시지 형식:
        markdown 타입과 text 타입을 지원. markdown 타입은 위챗에서 표시되지 않으니 text 타입을 써도 됨.
        markdown 타입은 markdown 형식을 해석하고, text 타입은 일반 텍스트를 그대로 보냄.

        markdown 타입 예시:
        {
            "msgtype": "markdown",
            "markdown": {
                "content": "## 제목\n\n내용"
            }
        }
        
        text 타입 예시:
        {
            "msgtype": "text",
            "text": {
                "content": "내용"
            }
        }

        주의: 위챗 워크 Markdown은 4096 바이트(글자 수 아님), Text 타입은 2048 바이트 제한. 길면 자동으로 나눠서 발송
        환경 변수 WECHAT_MAX_BYTES로 제한값 조정 가능
        
        Args:
            content: Markdown 형식 메시지 내용
            
        Returns:
            발송 성공 여부
        """
        if not self._wechat_url:
            logger.warning("위챗 워크 Webhook 미설정, 푸시 건너뜀")
            return False
        
        sanitized_content = strip_hidden_markdown_metadata(content).strip()
        if not sanitized_content:
            logger.warning("위챗 워크 메시지 내용이 비어 있어 푸시 건너뜀")
            return False

        # 메시지 타입에 따라 상한을 정함 (text 타입이 위챗 워크 2048 바이트 제한을 넘지 않게)
        if self._wechat_msg_type == 'text':
            max_bytes = min(self._wechat_max_bytes, 2000)  # 시스템/페이지 표시용 바이트를 조금 남겨 둠
        else:
            max_bytes = self._wechat_max_bytes  # markdown 기본값 4000 바이트

        # 바이트 길이 확인, 길면 나눠서 발송
        content_bytes = len(sanitized_content.encode('utf-8'))
        if content_bytes > max_bytes:
            logger.info(f"메시지가 너무 김 ({content_bytes}바이트/{len(content)}글자), 나눠서 발송")
            return self._send_wechat_chunked(sanitized_content, max_bytes)
        
        try:
            return self._send_wechat_message(sanitized_content, timeout_seconds=timeout_seconds)
        except Exception as e:
            logger.error(f"위챗 워크 메시지 발송 실패: {e}")
            return False

    def _send_wechat_image(self, image_bytes: bytes) -> bool:
        """Send image via WeChat Work webhook msgtype image (Issue #289)."""
        if not self._wechat_url:
            return False
        if len(image_bytes) > WECHAT_IMAGE_MAX_BYTES:
            logger.warning(
                "위챗 워크 이미지 용량 초과 (%d > %d bytes), 발송 거부. 호출한 쪽에서 텍스트로 대체해야 함",
                len(image_bytes), WECHAT_IMAGE_MAX_BYTES,
            )
            return False
        try:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            md5_hash = hashlib.md5(image_bytes).hexdigest()
            payload = {
                "msgtype": "image",
                "image": {"base64": b64, "md5": md5_hash},
            }
            response = requests.post(
                self._wechat_url, json=payload, timeout=30, verify=self._webhook_verify_ssl
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("errcode") == 0:
                    logger.info("위챗 워크 이미지 발송 완료")
                    return True
                logger.error("위챗 워크 이미지 발송 실패: %s", result.get("errmsg", ""))
            else:
                logger.error("위챗 워크 요청 실패: HTTP %s", response.status_code)
            return False
        except Exception as e:
            logger.error("위챗 워크 이미지 발송 중 예외: %s", e)
            return False
    
    def _send_wechat_message(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """위챗 워크 메시지 발송"""
        payload = self._gen_wechat_payload(content)
        
        response = requests.post(
            self._wechat_url,
            json=payload,
            timeout=timeout_seconds or 10,
            verify=self._webhook_verify_ssl
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('errcode') == 0:
                logger.info("위챗 워크 메시지 발송 완료")
                return True
            else:
                logger.error(f"위챗 워크 오류 응답: {result}")
                return False
        else:
            logger.error(f"위챗 워크 요청 실패: {response.status_code}")
            return False
        
    def _send_wechat_chunked(self, content: str, max_bytes: int) -> bool:
        """
        긴 메시지를 위챗 워크에 나눠서 발송
        
        종목 분석 블록(--- 또는 ### 로 구분) 단위로 나눠 묶음마다 제한을 넘지 않게 함
        
        Args:
            content: 전체 메시지 내용
            max_bytes: 메시지 1건 최대 바이트 수
            
        Returns:
            전부 발송 성공 여부
        """
        chunks = chunk_content_by_max_bytes(content, max_bytes, add_page_marker=True)
        total_chunks = len(chunks)
        success_count = 0
        for i, chunk in enumerate(chunks):
            if self._send_wechat_message(chunk):
                success_count += 1
            else:
                logger.error(f"위챗 워크 {i+1}/{total_chunks}번째 묶음 발송 실패")
            if i < total_chunks - 1:
                time.sleep(1)
        return success_count == len(chunks)

    def _gen_wechat_payload(self, content: str) -> dict:
        """위챗 워크 메시지 payload 생성"""
        sanitized_content = strip_hidden_markdown_metadata(content).strip()
        if self._wechat_msg_type == 'text':
            return {
                "msgtype": "text",
                "text": {
                    "content": sanitized_content
                }
            }
        else:
            return {
                "msgtype": "markdown",
                "markdown": {
                    "content": sanitized_content
                }
            }
