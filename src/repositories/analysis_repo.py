# -*- coding: utf-8 -*-
"""
===================================
분석 이력 데이터 접근 계층
===================================

역할:
1. 분석 이력 데이터의 DB 작업 캡슐화
2. CRUD 인터페이스 제공
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from src.storage import DatabaseManager, AnalysisHistory

logger = logging.getLogger(__name__)


class AnalysisRepository:
    """
    분석 이력 데이터 접근 계층
    
    AnalysisHistory 테이블의 DB 작업 캡슐화
    """
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        데이터 접근 계층 초기화
        
        Args:
            db_manager: 데이터베이스 관리자 (선택, 기본값은 싱글턴)
        """
        self.db = db_manager or DatabaseManager.get_instance()
    
    def get_by_query_id(self, query_id: str) -> Optional[AnalysisHistory]:
        """
        query_id로 분석 기록 가져오기
        
        Args:
            query_id: 조회 ID
            
        Returns:
            AnalysisHistory 객체, 없으면 None 반환
        """
        try:
            records = self.db.get_analysis_history(query_id=query_id, limit=1)
            return records[0] if records else None
        except Exception as e:
            logger.error(f"분석 기록 조회 실패: {e}")
            return None
    
    def get_list(
        self,
        code: Optional[str] = None,
        days: int = 30,
        limit: int = 50
    ) -> List[AnalysisHistory]:
        """
        분석 기록 목록 가져오기
        
        Args:
            code: 종목 코드 필터
            days: 기간 (일)
            limit: 반환 개수 제한
            
        Returns:
            AnalysisHistory 객체 리스트
        """
        try:
            return self.db.get_analysis_history(
                code=code,
                days=days,
                limit=limit
            )
        except Exception as e:
            logger.error(f"분석 목록 가져오기 실패: {e}")
            return []
    
    def save(
        self,
        result: Any,
        query_id: str,
        report_type: str,
        news_content: Optional[str] = None,
        context_snapshot: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        분석 결과 저장
        
        Args:
            result: 분석 결과 객체
            query_id: 조회 ID
            report_type: 보고서 유형
            news_content: 뉴스 내용
            context_snapshot: 맥락 스냅샷
            
        Returns:
            새로 저장한 AnalysisHistory.id, 저장 실패 시 0 반환.
        """
        try:
            return self.db.save_analysis_history(
                result=result,
                query_id=query_id,
                report_type=report_type,
                news_content=news_content,
                context_snapshot=context_snapshot
            )
        except Exception as e:
            logger.error(f"분석 결과 저장 실패: {e}")
            return 0
    
    def count_by_code(self, code: str, days: int = 30) -> int:
        """
        지정 종목의 분석 기록 수 세기
        
        Args:
            code: 종목 코드
            days: 기간 (일)
            
        Returns:
            기록 수
        """
        try:
            records = self.db.get_analysis_history(code=code, days=days, limit=1000)
            return len(records)
        except Exception as e:
            logger.error(f"분석 기록 집계 실패: {e}")
            return 0
