# -*- coding: utf-8 -*-
"""
커스텀 Webhook 알림 발송 서비스

역할:
1. 커스텀 Webhook 메시지 발송
"""
import logging
import json
import time
from string import Template
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.config import Config
from src.formatters import (
    chunk_content_by_max_bytes,
    slice_at_max_bytes,
    strip_hidden_markdown_metadata,
)


logger = logging.getLogger(__name__)


class CustomWebhookSender:

    def __init__(self, config: Config):
        """
        커스텀 Webhook 설정 초기화

        Args:
            config: 설정 객체
        """
        self._custom_webhook_urls = getattr(config, 'custom_webhook_urls', []) or []
        self._custom_webhook_bearer_token = getattr(config, 'custom_webhook_bearer_token', None)
        self._custom_webhook_body_template = getattr(config, 'custom_webhook_body_template', None)
        self._webhook_verify_ssl = getattr(config, 'webhook_verify_ssl', True)
 
    def send_to_custom(self, content: str) -> bool:
        """
        커스텀 Webhook에 메시지 푸시
        
        POST JSON을 받는 Webhook 엔드포인트라면 무엇이든 지원
        기본 발송 형식: {"text": "메시지 내용", "content": "메시지 내용"}
        
        사용 대상:
        - 딩톡(DingTalk) 봇
        - Discord Webhook
        - Slack Incoming Webhook
        - 직접 만든 알림 서비스
        - 그 밖에 POST JSON을 지원하는 서비스
        
        Args:
            content: 메시지 내용 (Markdown 형식)
            
        Returns:
            Webhook 중 하나라도 발송에 성공했는지 여부
        """
        if not self._custom_webhook_urls:
            logger.warning("커스텀 Webhook 미설정, 푸시 건너뜀")
            return False
        
        success_count = 0
        
        for i, url in enumerate(self._custom_webhook_urls):
            try:
                # 범용 JSON 형식, 대부분의 Webhook과 호환
                # 딩톡 형식: {"msgtype": "text", "text": {"content": "xxx"}}
                # Slack 형식: {"text": "xxx"}
                # Discord 형식: {"content": "xxx"}
                
                # 딩톡 봇은 body 바이트 상한(약 20000 bytes)이 있어서 길면 나눠 보내야 함
                if self._is_dingtalk_webhook(url):
                    templated_payload = self._build_custom_webhook_template_payload(content)
                    if templated_payload is not None:
                        if self._post_custom_webhook(url, templated_payload, timeout=30):
                            logger.info(f"커스텀 Webhook {i+1} (딩톡 템플릿) 푸시 완료")
                            success_count += 1
                        elif self._send_dingtalk_chunked(url, content, max_bytes=20000):
                            logger.info(f"커스텀 Webhook {i+1} (딩톡 템플릿 실패, 분할 발송으로 대체) 푸시 완료")
                            success_count += 1
                        else:
                            logger.error(f"커스텀 Webhook {i+1} (딩톡 템플릿) 푸시 실패")
                    elif self._send_dingtalk_chunked(url, content, max_bytes=20000):
                        logger.info(f"커스텀 Webhook {i+1} (딩톡) 푸시 완료")
                        success_count += 1
                    else:
                        logger.error(f"커스텀 Webhook {i+1} (딩톡) 푸시 실패")
                    continue

                # 그 밖의 Webhook: 한 번에 발송
                payload = self._build_custom_webhook_payload(url, content)
                if self._post_custom_webhook(url, payload, timeout=30):
                    logger.info(f"커스텀 Webhook {i+1} 푸시 완료")
                    success_count += 1
                else:
                    logger.error(f"커스텀 Webhook {i+1} 푸시 실패")
                    
            except Exception as e:
                logger.error(f"커스텀 Webhook {i+1} 푸시 중 예외: {e}")
        
        logger.info(f"커스텀 Webhook 푸시 완료: 성공 {success_count}/{len(self._custom_webhook_urls)}")
        return success_count > 0

    
    def _send_custom_webhook_image(
        self, image_bytes: bytes, fallback_content: str = ""
    ) -> bool:
        """Send image to Custom Webhooks; Discord supports file attachment (Issue #289)."""
        if not self._custom_webhook_urls:
            return False
        success_count = 0
        for i, url in enumerate(self._custom_webhook_urls):
            try:
                if self._is_discord_webhook(url):
                    files = {"file": ("report.png", image_bytes, "image/png")}
                    data = {"content": "📈 股票智能分析报告"}
                    headers = {"User-Agent": "StockAnalysis/1.0"}
                    if self._custom_webhook_bearer_token:
                        headers["Authorization"] = (
                            f"Bearer {self._custom_webhook_bearer_token}"
                        )
                    response = requests.post(
                        url, data=data, files=files, headers=headers, timeout=30,
                        verify=self._webhook_verify_ssl
                    )
                    if response.status_code in (200, 204):
                        logger.info("커스텀 Webhook %d (Discord 이미지) 푸시 완료", i + 1)
                        success_count += 1
                    else:
                        logger.error(
                            "커스텀 Webhook %d (Discord 이미지) 푸시 실패: HTTP %s",
                            i + 1, response.status_code,
                        )
                else:
                    if fallback_content:
                        payload = self._build_custom_webhook_payload(url, fallback_content)
                        if self._post_custom_webhook(url, payload, timeout=30):
                            logger.info(
                                "커스텀 Webhook %d (이미지 미지원, 텍스트로 대체) 푸시 완료", i + 1
                            )
                            success_count += 1
                    else:
                        logger.warning(
                            "커스텀 Webhook %d 이미지 미지원, 대체 내용도 없어 건너뜀", i + 1
                        )
            except Exception as e:
                logger.error("커스텀 Webhook %d 이미지 푸시 중 예외: %s", i + 1, e)
        return success_count > 0

    def _post_custom_webhook(self, url: str, payload: dict, timeout: int = 30) -> bool:
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': 'StockAnalysis/1.0',
        }
        # Bearer Token 인증 지원 (#51)
        if self._custom_webhook_bearer_token:
            headers['Authorization'] = f'Bearer {self._custom_webhook_bearer_token}'
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        response = requests.post(url, data=body, headers=headers, timeout=timeout, verify=self._webhook_verify_ssl)
        if response.status_code == 200:
            return True
        logger.error(f"커스텀 Webhook 푸시 실패: HTTP {response.status_code}")
        logger.debug(f"응답 내용: {response.text[:200]}")
        return False

    def test_custom_webhooks(self, content: str, *, timeout_seconds: float = 20.0) -> List[Dict[str, Any]]:
        """Send a test message to each custom webhook and return raw per-URL attempts."""
        attempts: List[Dict[str, Any]] = []
        for index, url in enumerate(self._custom_webhook_urls):
            try:
                payload = self._build_custom_webhook_payload(url, content)
                attempts.append(
                    self._post_custom_webhook_attempt(
                        url=url,
                        payload=payload,
                        timeout_seconds=timeout_seconds,
                        index=index,
                    )
                )
            except Exception as exc:
                attempts.append({
                    "channel": "custom",
                    "success": False,
                    "message": f"커스텀 Webhook {index + 1} 테스트 중 예외: {exc}",
                    "target": url,
                    "error_code": self._classify_custom_webhook_exception(exc)[0],
                    "stage": "notification_send",
                    "retryable": self._classify_custom_webhook_exception(exc)[1],
                    "latency_ms": None,
                    "http_status": None,
                })
        return attempts

    def _post_custom_webhook_attempt(
        self,
        *,
        url: str,
        payload: dict,
        timeout_seconds: float,
        index: int,
    ) -> Dict[str, Any]:
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': 'StockAnalysis/1.0',
        }
        if self._custom_webhook_bearer_token:
            headers['Authorization'] = f'Bearer {self._custom_webhook_bearer_token}'

        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        started_at = time.perf_counter()
        try:
            response = requests.post(
                url,
                data=body,
                headers=headers,
                timeout=timeout_seconds,
                verify=self._webhook_verify_ssl,
            )
        except Exception as exc:
            error_code, retryable = self._classify_custom_webhook_exception(exc)
            return {
                "channel": "custom",
                "success": False,
                "message": f"커스텀 Webhook {index + 1} 테스트 실패: {exc}",
                "target": url,
                "error_code": error_code,
                "stage": "notification_send",
                "retryable": retryable,
                "latency_ms": int((time.perf_counter() - started_at) * 1000),
                "http_status": None,
            }

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        if response.status_code == 200:
            return {
                "channel": "custom",
                "success": True,
                "message": f"커스텀 Webhook {index + 1} 테스트 발송 완료",
                "target": url,
                "error_code": None,
                "stage": "notification_send",
                "retryable": False,
                "latency_ms": latency_ms,
                "http_status": response.status_code,
            }

        retryable = response.status_code == 429 or response.status_code >= 500
        return {
            "channel": "custom",
            "success": False,
            "message": f"커스텀 Webhook {index + 1} 테스트 실패: HTTP {response.status_code}",
            "target": url,
            "error_code": "http_error",
            "stage": "notification_send",
            "retryable": retryable,
            "latency_ms": latency_ms,
            "http_status": response.status_code,
        }

    @staticmethod
    def _classify_custom_webhook_exception(exc: Exception) -> Tuple[str, bool]:
        if isinstance(exc, requests.exceptions.Timeout):
            return "timeout", True
        if isinstance(exc, requests.exceptions.ConnectionError):
            return "network_error", True
        if isinstance(exc, requests.exceptions.RequestException):
            return "network_error", True
        return "unexpected_error", False
    
    def _build_custom_webhook_payload(self, url: str, content: str) -> dict:
        """
        URL에 맞는 Webhook payload 구성
        
        자주 쓰는 서비스를 자동으로 알아보고 그 형식을 사용
        """
        sanitized_content = strip_hidden_markdown_metadata(content).strip()
        templated_payload = self._build_custom_webhook_template_payload(sanitized_content)
        if templated_payload is not None:
            return templated_payload

        url_lower = url.lower()
        
        # 딩톡 봇
        if 'dingtalk' in url_lower or 'oapi.dingtalk.com' in url_lower:
            return {
                "msgtype": "markdown",
                "markdown": {
                    "title": "股票分析报告",
                    "text": sanitized_content
                }
            }
        
        # Discord Webhook
        if 'discord.com/api/webhooks' in url_lower or 'discordapp.com/api/webhooks' in url_lower:
            # Discord 2000자 제한
            truncated = (
                sanitized_content[:1900] + "..."
                if len(sanitized_content) > 1900
                else sanitized_content
            )
            return {
                "content": truncated
            }
        
        # Slack Incoming Webhook
        if 'hooks.slack.com' in url_lower:
            return {
                "text": sanitized_content,
                "mrkdwn": True
            }
        
        # Bark (iOS 푸시)
        if 'api.day.app' in url_lower:
            return {
                "title": "股票分析报告",
                "body": sanitized_content[:4000],  # Bark 제한
                "group": "stock"
            }
        
        # 범용 형식 (대부분 서비스와 호환)
        return {
            "text": sanitized_content,
            "content": sanitized_content,
            "message": sanitized_content,
            "body": sanitized_content
        }

    def _build_custom_webhook_template_payload(self, content: str) -> Optional[dict]:
        """Build payload from CUSTOM_WEBHOOK_BODY_TEMPLATE when configured."""
        content = strip_hidden_markdown_metadata(content).strip()
        template = (self._custom_webhook_body_template or "").strip()
        if not template:
            return None

        title = "股票分析报告"
        variables = {
            "title": title,
            "title_json": json.dumps(title, ensure_ascii=False),
            "content": content,
            "content_json": json.dumps(content, ensure_ascii=False),
        }
        rendered = Template(template).safe_substitute(variables)
        try:
            payload: Any = json.loads(rendered)
        except json.JSONDecodeError as exc:
            logger.error(
                "CUSTOM_WEBHOOK_BODY_TEMPLATE이 올바른 JSON이 아님, 기본 Webhook payload로 대체: %s",
                exc,
            )
            return None
        if not isinstance(payload, dict):
            logger.error(
                "CUSTOM_WEBHOOK_BODY_TEMPLATE 렌더링 결과가 JSON object여야 함, 기본 Webhook payload로 대체"
            )
            return None
        return payload
    
    def _send_dingtalk_chunked(self, url: str, content: str, max_bytes: int = 20000) -> bool:
        import time as _time
        content = strip_hidden_markdown_metadata(content).strip()

        # payload 부가 용량만큼 공간을 남겨 body 상한 초과 방지
        budget = max(1000, max_bytes - 1500)
        chunks = chunk_content_by_max_bytes(content, budget)
        if not chunks:
            return False

        total = len(chunks)
        ok = 0

        for idx, chunk in enumerate(chunks):
            marker = f"\n\n📄 *({idx+1}/{total})*" if total > 1 else ""
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": "股票分析报告",
                    "text": chunk + marker,
                },
            }

            # 그래도 넘으면(극단적인 경우) 바이트 기준으로 한 번 더 강제로 자름
            body_bytes = len(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
            if body_bytes > max_bytes:
                hard_budget = max(200, budget - (body_bytes - max_bytes) - 200)
                payload["markdown"]["text"], _ = slice_at_max_bytes(payload["markdown"]["text"], hard_budget)

            if self._post_custom_webhook(url, payload, timeout=30):
                ok += 1
            else:
                logger.error(f"딩톡 분할 발송 실패: {idx+1}/{total}번째 묶음")

            if idx < total - 1:
                _time.sleep(1)

        return ok == total

    
    @staticmethod
    def _is_dingtalk_webhook(url: str) -> bool:
        url_lower = (url or "").lower()
        return 'dingtalk' in url_lower or 'oapi.dingtalk.com' in url_lower

    @staticmethod
    def _is_discord_webhook(url: str) -> bool:
        url_lower = (url or "").lower()
        return (
            'discord.com/api/webhooks' in url_lower
            or 'discordapp.com/api/webhooks' in url_lower
        )
