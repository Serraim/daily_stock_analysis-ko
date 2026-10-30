# -*- coding: utf-8 -*-
"""
Pushover 알림 발송 서비스

역할:
1. Pushover API로 Pushover 메시지 발송
"""
import logging
from typing import Optional
from datetime import datetime
import requests

from src.config import Config
from src.formatters import markdown_to_plain_text


logger = logging.getLogger(__name__)


class PushoverSender:
    
    def __init__(self, config: Config):
        """
        Pushover 설정 초기화

        Args:
            config: 설정 객체
        """
        self._pushover_config = {
            'user_key': getattr(config, 'pushover_user_key', None),
            'api_token': getattr(config, 'pushover_api_token', None),
        }
        
    def _is_pushover_configured(self) -> bool:
        """Pushover 설정이 다 갖춰졌는지 확인"""
        return bool(self._pushover_config['user_key'] and self._pushover_config['api_token'])

    def send_to_pushover(
        self,
        content: str,
        title: Optional[str] = None,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        Pushover에 메시지 푸시
        
        Pushover API 형식:
        POST https://api.pushover.net/1/messages.json
        {
            "token": "앱 API Token",
            "user": "사용자 Key",
            "message": "메시지 내용",
            "title": "제목 (선택)"
        }
        
        Pushover 특징:
        - iOS/Android/데스크톱 등 여러 플랫폼 푸시 지원
        - 메시지 길이 제한 1024자
        - 우선순위 설정 지원
        - HTML 형식 지원
        
        Args:
            content: 메시지 내용 (Markdown 형식, 일반 텍스트로 변환됨)
            title: 메시지 제목 (선택, 기본값 "股票分析报告")

        Returns:
            발송 성공 여부
        """
        if not self._is_pushover_configured():
            logger.warning("Pushover 설정이 불완전해 푸시 건너뜀")
            return False
        
        user_key = self._pushover_config['user_key']
        api_token = self._pushover_config['api_token']
        
        # Pushover API 엔드포인트
        api_url = "https://api.pushover.net/1/messages.json"
        
        # 메시지 제목 처리
        if title is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
            title = f"📈 股票分析报告 - {date_str}"
        
        # Pushover 메시지 길이 제한 1024자
        max_length = 1024
        
        # Markdown을 일반 텍스트로 변환 (Pushover는 HTML도 되지만 일반 텍스트가 더 무난함)
        plain_content = markdown_to_plain_text(content)
        
        if len(plain_content) <= max_length:
            # 한 번에 발송
            return self._send_pushover_message(api_url, user_key, api_token, plain_content, title, timeout_seconds=timeout_seconds)
        else:
            # 긴 메시지는 나눠서 발송
            return self._send_pushover_chunked(
                api_url,
                user_key,
                api_token,
                plain_content,
                title,
                max_length,
                timeout_seconds=timeout_seconds,
            )
      
    def _send_pushover_message(
        self, 
        api_url: str, 
        user_key: str, 
        api_token: str, 
        message: str, 
        title: str,
        priority: int = 0,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        Pushover 메시지 1건 발송
        
        Args:
            api_url: Pushover API 엔드포인트
            user_key: 사용자 Key
            api_token: 앱 API Token
            message: 메시지 내용
            title: 메시지 제목
            priority: 우선순위 (-2 ~ 2, 기본값 0)
        """
        try:
            payload = {
                "token": api_token,
                "user": user_key,
                "message": message,
                "title": title,
                "priority": priority,
            }
            
            response = requests.post(api_url, data=payload, timeout=timeout_seconds or 30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 1:
                    logger.info("Pushover 메시지 발송 완료")
                    return True
                else:
                    errors = result.get('errors', ['알 수 없는 오류'])
                    logger.error(f"Pushover 오류 응답: {errors}")
                    return False
            else:
                logger.error(f"Pushover 요청 실패: HTTP {response.status_code}")
                logger.debug(f"응답 내용: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Pushover 메시지 발송 실패: {e}")
            return False
    
    def _send_pushover_chunked(
        self, 
        api_url: str, 
        user_key: str, 
        api_token: str, 
        content: str, 
        title: str,
        max_length: int,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        긴 Pushover 메시지를 나눠서 발송
        
        문단 단위로 나눠 각 조각이 최대 길이를 넘지 않게 함
        """
        import time
        
        # 문단(구분선 또는 빈 줄 두 개) 기준으로 나눔
        if "────────" in content:
            sections = content.split("────────")
            separator = "────────"
        else:
            sections = content.split("\n\n")
            separator = "\n\n"
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for section in sections:
            # 이 section을 더했을 때의 실제 길이 계산
            # join()은 구분자를 요소 사이에만 넣음 (요소마다 뒤에 붙이지 않음)
            # 그래서 첫 요소는 구분자가 필요 없고, 이후 요소는 구분자 하나로 이어 붙임
            if current_chunk:
                # 이미 요소가 있으면 새 요소 추가 시: 현재 길이 + 구분자 + 새 section
                new_length = current_length + len(separator) + len(section)
            else:
                # 첫 요소라 구분자 불필요
                new_length = len(section)
            
            if new_length > max_length:
                if current_chunk:
                    chunks.append(separator.join(current_chunk))
                current_chunk = [section]
                current_length = len(section)
            else:
                current_chunk.append(section)
                current_length = new_length
        
        if current_chunk:
            chunks.append(separator.join(current_chunk))
        
        total_chunks = len(chunks)
        success_count = 0
        
        logger.info(f"Pushover 나눠서 발송: 총 {total_chunks}개 묶음")
        
        for i, chunk in enumerate(chunks):
            # 제목에 페이지 표시 추가
            chunk_title = f"{title} ({i+1}/{total_chunks})" if total_chunks > 1 else title
            
            if self._send_pushover_message(
                api_url,
                user_key,
                api_token,
                chunk,
                chunk_title,
                timeout_seconds=timeout_seconds,
            ):
                success_count += 1
                logger.info(f"Pushover {i+1}/{total_chunks}번째 묶음 발송 완료")
            else:
                logger.error(f"Pushover {i+1}/{total_chunks}번째 묶음 발송 실패")
            
            # 묶음 사이에 간격을 둬 빈도 제한(rate limit) 피하기
            if i < total_chunks - 1:
                time.sleep(1)

        return success_count == total_chunks
