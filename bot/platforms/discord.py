# -*- coding: utf-8 -*-
"""
===================================
Discord 플랫폼 어댑터
===================================

역할:
1. Discord Webhook 요청 검증
2. Discord 메시지를 공통 형식으로 해석
3. 응답을 Discord 형식으로 변환
"""

import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

import requests
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from bot.platforms.base import BotPlatform
from bot.models import BotMessage, WebhookResponse, ChatType


logger = logging.getLogger(__name__)


class DiscordPlatform(BotPlatform):
    """Discord 플랫폼 어댑터"""

    def __init__(self):
        from src.config import get_config

        config = get_config()
        self._interactions_public_key = (
            getattr(config, "discord_interactions_public_key", None) or ""
        ).strip()
    
    @property
    def platform_name(self) -> str:
        """플랫폼 식별 이름"""
        return "discord"
    
    def verify_request(self, headers: Dict[str, str], body: bytes) -> bool:
        """Discord Webhook 요청 서명 검증
        
        Discord Webhook 서명 검증:
        1. 요청 헤더에서 X-Signature-Ed25519와 X-Signature-Timestamp를 가져옴
        2. 공개 키로 서명 검증
        
        Args:
            headers: HTTP 요청 헤더
            body: 요청 본문 원본 바이트
            
        Returns:
            서명이 유효한지 여부
        """
        if not self._interactions_public_key:
            logger.warning("[Discord] interactions public key가 설정되지 않아 요청 거부")
            return False

        normalized_headers = {str(k).lower(): v for k, v in headers.items()}
        signature = normalized_headers.get("x-signature-ed25519", "")
        timestamp = normalized_headers.get("x-signature-timestamp", "")

        if not signature or not timestamp:
            logger.warning("[Discord] 서명 헤더가 없어 요청 거부")
            return False

        # timestamp 형식과 유효 시간을 검사해 재전송 공격 방지
        try:
            ts_int = int(timestamp)
        except (TypeError, ValueError):
            logger.warning("[Discord] 잘못된 timestamp: Unix 초 단위 정수여야 함, 요청 거부")
            return False

        try:
            now_ts = int(time.time())
        except Exception as exc:
            logger.warning("[Discord] 현재 시간 확인 실패: %s, 요청 거부", exc)
            return False

        # 허용 시간 범위: ±5분
        if abs(now_ts - ts_int) > 300:
            logger.warning(
                "[Discord] 요청 timestamp가 허용 범위를 벗어남, 재전송 공격일 수 있음:timestamp=%s, now=%s",
                ts_int,
                now_ts,
            )
            return False

        try:
            verify_key = VerifyKey(bytes.fromhex(self._interactions_public_key))
            signature_bytes = bytes.fromhex(signature)
        except ValueError:
            logger.warning("[Discord] 공개 키나 서명이 올바른 16진수가 아님, 요청 거부")
            return False
        except Exception as exc:
            logger.warning("[Discord] 서명 공개 키를 불러올 수 없음: %s", exc)
            return False

        try:
            verify_key.verify(timestamp.encode("utf-8") + body, signature_bytes)
        except BadSignatureError:
            logger.warning("[Discord] 서명 검증 실패")
            return False
        except Exception as exc:
            logger.warning("[Discord] 서명 검사 중 예외: %s", exc)
            return False

        return True

    def handle_webhook(
        self,
        headers: Dict[str, str],
        body: bytes,
        data: Dict[str, Any],
    ) -> Tuple[Optional[BotMessage], Optional[WebhookResponse]]:
        """Discord는 서명을 먼저 검증한 뒤 ping/challenge를 처리해야 합니다."""
        if not self.verify_request(headers, body):
            return None, WebhookResponse.error("Invalid Discord signature", 401)

        challenge_response = self.handle_challenge(data)
        if challenge_response:
            return None, challenge_response

        message = self.parse_message(data)
        if message is not None and data.get("type") == 2:
            # Discord requires an initial response within 3 s.  Return a
            # deferred acknowledgement (type 5 = DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE)
            # so the handler can dispatch the command in the background and
            # deliver the result via follow-up webhook.
            return message, WebhookResponse.success({"type": 5})

        return message, None
    
    def parse_message(self, data: Dict[str, Any]) -> Optional[BotMessage]:
        """Discord 메시지를 공통 형식으로 해석
        
        Args:
            data: 해석된 JSON 데이터
            
        Returns:
            BotMessage 객체 또는 None(처리 불필요)
        """
        interaction_type = data.get("type")
        if interaction_type != 2:
            return None

        interaction_data = data.get("data", {})
        content = self._build_command_content(interaction_data)
        if not content:
            return None

        author = (
            data.get("user")
            or (data.get("member") or {}).get("user")
            or data.get("author", {})
        )
        user_id = str(author.get("id") or "")
        user_name = author.get("username", "unknown")
        channel_id = str(data.get("channel_id") or "")
        guild_id = str(data.get("guild_id") or "")

        if guild_id:
            chat_type = ChatType.GROUP
        elif channel_id:
            chat_type = ChatType.PRIVATE
        else:
            chat_type = ChatType.UNKNOWN

        return BotMessage(
            platform=self.platform_name,
            message_id=str(data.get("id") or ""),
            user_id=user_id,
            user_name=user_name,
            chat_id=channel_id or guild_id or user_id,
            chat_type=chat_type,
            content=content,
            raw_content=content,
            mentioned=False,
            mentions=[],
            timestamp=self._parse_timestamp(data.get("timestamp")),
            raw_data={
                **data,
                "_interaction_name": interaction_data.get("name", ""),
            },
        )
    
    def format_response(self, response: Any, message: BotMessage) -> WebhookResponse:
        """공통 응답을 Discord 형식으로 변환
        
        Interaction(type=2) 요청에는 Discord Interaction Response
        callback 형식(type=4 CHANNEL_MESSAGE_WITH_SOURCE + nested data)으로 반환합니다.
        
        Args:
            response: 공통 응답 객체
            message: 원본 메시지 객체
            
        Returns:
            WebhookResponse 객체
        """
        content = response.text if hasattr(response, "text") else str(response)

        message_data = {
            "content": content,
            "tts": False,
            "embeds": [],
            "allowed_mentions": {
                "parse": ["users", "roles", "everyone"]
            },
        }

        # Interaction(slash-command)에는 Interaction Response 콜백 형식이 필요
        if message.raw_data.get("type") == 2:
            discord_response = {
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": message_data,
            }
        else:
            discord_response = message_data

        return WebhookResponse.success(discord_response)
    
    # Discord message content hard limit
    DISCORD_MAX_CONTENT_LENGTH = 2000

    def send_followup(self, response: Any, message: BotMessage) -> bool:
        """Edit the deferred interaction placeholder with the real result.

        Uses ``PATCH /webhooks/{application_id}/{token}/messages/@original``
        to update the original deferred message, then sends additional
        follow-up messages via ``POST`` if the content exceeds Discord's
        2 000-character limit.
        """
        raw = message.raw_data
        application_id = raw.get("application_id", "")
        interaction_token = raw.get("token", "")
        if not application_id or not interaction_token:
            logger.warning(
                "[Discord] application_id나 interaction token이 없어 follow-up을 보낼 수 없음"
            )
            return False

        content = response.text if hasattr(response, "text") else str(response)

        from src.formatters import chunk_content_by_max_words

        try:
            chunks = chunk_content_by_max_words(
                content, self.DISCORD_MAX_CONTENT_LENGTH
            )
        except (ValueError, Exception) as exc:
            logger.warning("[Discord] 메시지 분할 실패: %s, 통째로 보내기 시도", exc)
            chunks = [content]

        base_url = (
            f"https://discord.com/api/v10/webhooks/"
            f"{application_id}/{interaction_token}"
        )

        success = True
        for idx, chunk in enumerate(chunks):
            try:
                if idx == 0:
                    # PATCH the original deferred message
                    resp = requests.patch(
                        f"{base_url}/messages/@original",
                        json={"content": chunk},
                        timeout=10,
                    )
                else:
                    # POST additional follow-up messages
                    resp = requests.post(
                        base_url,
                        json={"content": chunk},
                        timeout=10,
                    )
                if resp.status_code >= 300:
                    logger.error(
                        "[Discord] follow-up chunk %d/%d 전송 실패: %s %s",
                        idx + 1,
                        len(chunks),
                        resp.status_code,
                        resp.text[:200],
                    )
                    success = False
            except Exception as exc:
                logger.error(
                    "[Discord] follow-up chunk %d/%d 요청 예외: %s",
                    idx + 1,
                    len(chunks),
                    exc,
                )
                success = False

        if success:
            logger.info("[Discord] follow-up 메시지 전송 성공 (%d개 조각)", len(chunks))
        return success

    def handle_challenge(self, data: Dict[str, Any]) -> Optional[WebhookResponse]:
        """Discord 검증 요청 처리
        
        Discord는 Webhook 설정 때 검증 요청을 보냅니다
        
        Args:
            data: 요청 데이터
            
        Returns:
            검증 응답 또는 None(검증 요청이 아님)
        """
        # Discord Webhook 검증 요청 유형은 1
        if data.get("type") == 1:
            return WebhookResponse.success({
                "type": 1
            })
        
        # Discord 명령 상호작용 검증
        if "challenge" in data:
            return WebhookResponse.success({
                "challenge": data["challenge"]
            })
        
        return None

    def _build_command_content(self, interaction_data: Dict[str, Any]) -> str:
        command_name = str(interaction_data.get("name", "")).strip()
        if not command_name:
            return ""

        parts = [f"/{command_name}"]
        self._append_option_parts(parts, interaction_data.get("options", []))
        return " ".join(parts).strip()

    def _append_option_parts(self, parts: List[str], options: Any) -> None:
        if not isinstance(options, list):
            return

        for option in options:
            if not isinstance(option, dict):
                continue

            nested_options = option.get("options")
            if nested_options:
                nested_name = str(option.get("name", "")).strip()
                if nested_name:
                    parts.append(nested_name)
                self._append_option_parts(parts, nested_options)
                continue

            value = option.get("value")
            if value is None:
                continue
            if isinstance(value, bool):
                # Emit the option name for truthy flags so downstream
                # commands receive a semantic token (e.g. "full") instead
                # of a literal "true"/"false" string.  False flags are
                # simply omitted.
                if value:
                    opt_name = str(option.get("name", "")).strip()
                    if opt_name:
                        parts.append(opt_name)
            else:
                parts.append(str(value))

    def _parse_timestamp(self, value: Any) -> datetime:
        if not value:
            return datetime.now()

        if isinstance(value, datetime):
            return value

        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return datetime.now()
