# -*- coding: utf-8 -*-
"""
===================================
주식 데이터 접근 계층
===================================

역할:
1. 주식 데이터의 DB 작업 캡슐화
2. 일봉 데이터 조회 인터페이스 제공
"""

import logging
from datetime import date
from typing import Optional, List, Dict, Any

import pandas as pd
from sqlalchemy import and_, desc, select

from src.storage import DatabaseManager, StockDaily

logger = logging.getLogger(__name__)


class StockRepository:
    """
    주식 데이터 접근 계층
    
    StockDaily 테이블의 DB 작업 캡슐화
    """
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        데이터 접근 계층 초기화
        
        Args:
            db_manager: 데이터베이스 관리자 (선택, 기본값은 싱글턴)
        """
        self.db = db_manager or DatabaseManager.get_instance()
    
    def get_latest(self, code: str, days: int = 2) -> List[StockDaily]:
        """
        최근 N일의 데이터 가져오기
        
        Args:
            code: 종목 코드
            days: 가져올 일수
            
        Returns:
            StockDaily 객체 리스트 (날짜 내림차순)
        """
        try:
            return self.db.get_latest_data(code, days)
        except Exception as e:
            logger.error(f"최신 데이터 가져오기 실패: {e}")
            return []
    
    def get_range(
        self,
        code: str,
        start_date: date,
        end_date: date
    ) -> List[StockDaily]:
        """
        지정한 날짜 범위의 데이터 가져오기
        
        Args:
            code: 종목 코드
            start_date: 시작일
            end_date: 종료일
            
        Returns:
            StockDaily 객체 리스트
        """
        try:
            return self.db.get_data_range(code, start_date, end_date)
        except Exception as e:
            logger.error(f"날짜 범위 데이터 가져오기 실패: {e}")
            return []
    
    def save_dataframe(
        self,
        df: pd.DataFrame,
        code: str,
        data_source: str = "Unknown"
    ) -> int:
        """
        DataFrame을 데이터베이스에 저장
        
        Args:
            df: 일봉 데이터가 담긴 DataFrame
            code: 종목 코드
            data_source: 데이터 출처
            
        Returns:
            저장한 기록 수
        """
        try:
            return self.db.save_daily_data(df, code, data_source)
        except Exception as e:
            logger.error(f"일봉 데이터 저장 실패: {e}")
            return 0
    
    def has_today_data(self, code: str, target_date: Optional[date] = None) -> bool:
        """
        지정한 날짜의 데이터가 있는지 확인
        
        Args:
            code: 종목 코드
            target_date: 대상 날짜 (기본값 오늘)
            
        Returns:
            데이터 존재 여부
        """
        try:
            return self.db.has_today_data(code, target_date)
        except Exception as e:
            logger.error(f"데이터 존재 확인 실패: {e}")
            return False
    
    def get_analysis_context(
        self, 
        code: str, 
        target_date: Optional[date] = None
    ) -> Optional[Dict[str, Any]]:
        """
        분석 맥락 가져오기
        
        Args:
            code: 종목 코드
            target_date: 대상 날짜
            
        Returns:
            분석 맥락 딕셔너리
        """
        try:
            return self.db.get_analysis_context(code, target_date)
        except Exception as e:
            logger.error(f"분석 맥락 가져오기 실패: {e}")
            return None

    def get_start_daily(self, *, code: str, analysis_date: date) -> Optional[StockDaily]:
        """Return StockDaily for analysis_date (preferred) or nearest previous date."""
        with self.db.get_session() as session:
            row = session.execute(
                select(StockDaily)
                .where(and_(StockDaily.code == code, StockDaily.date <= analysis_date))
                .order_by(desc(StockDaily.date))
                .limit(1)
            ).scalar_one_or_none()
            return row

    def get_daily_on_date(self, *, code: str, target_date: date) -> Optional[StockDaily]:
        """Return StockDaily for the exact target_date without trading-day fallback."""
        with self.db.get_session() as session:
            row = session.execute(
                select(StockDaily)
                .where(and_(StockDaily.code == code, StockDaily.date == target_date))
                .limit(1)
            ).scalar_one_or_none()
            return row

    def get_forward_bars(self, *, code: str, analysis_date: date, eval_window_days: int) -> List[StockDaily]:
        """Return forward daily bars after analysis_date, up to eval_window_days."""
        with self.db.get_session() as session:
            rows = session.execute(
                select(StockDaily)
                .where(and_(StockDaily.code == code, StockDaily.date > analysis_date))
                .order_by(StockDaily.date)
                .limit(eval_window_days)
            ).scalars().all()
            return list(rows)
