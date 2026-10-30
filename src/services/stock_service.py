# -*- coding: utf-8 -*-
"""
===================================
종목 데이터 서비스 계층
===================================

역할:
1. 종목 데이터 가져오기 로직 캡슐화
2. 실시간 시세와 과거 데이터 인터페이스 제공
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from src.repositories.stock_repo import StockRepository

logger = logging.getLogger(__name__)


class StockService:
    """
    종목 데이터 서비스
    
    종목 데이터 가져오기 업무 로직을 캡슐화한다
    """
    
    def __init__(self):
        """종목 데이터 서비스 초기화"""
        self.repo = StockRepository()
    
    def get_realtime_quote(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        종목 실시간 시세 가져오기
        
        Args:
            stock_code: 종목 코드
            
        Returns:
            실시간 시세 데이터 딕셔너리
        """
        try:
            # 데이터 가져오기 도구로 실시간 시세 조회
            from data_provider.base import DataFetcherManager
            
            manager = DataFetcherManager()
            quote = manager.get_realtime_quote(stock_code)
            
            if quote is None:
                logger.warning(f"종목 {stock_code} 실시간 시세 가져오기 실패")
                return None
            
            # UnifiedRealtimeQuote는 dataclass이므로 getattr로 안전하게 필드에 접근
            # 필드 매핑: UnifiedRealtimeQuote -> API 응답
            # - code -> stock_code
            # - name -> stock_name
            # - price -> current_price
            # - change_amount -> change
            # - change_pct -> change_percent
            # - open_price -> open
            # - high -> high
            # - low -> low
            # - pre_close -> prev_close
            # - volume -> volume
            # - amount -> amount
            return {
                "stock_code": getattr(quote, "code", stock_code),
                "stock_name": getattr(quote, "name", None),
                "current_price": getattr(quote, "price", 0.0) or 0.0,
                "change": getattr(quote, "change_amount", None),
                "change_percent": getattr(quote, "change_pct", None),
                "open": getattr(quote, "open_price", None),
                "high": getattr(quote, "high", None),
                "low": getattr(quote, "low", None),
                "prev_close": getattr(quote, "pre_close", None),
                "volume": getattr(quote, "volume", None),
                "amount": getattr(quote, "amount", None),
                "update_time": datetime.now().isoformat(),
            }
            
        except ImportError:
            logger.warning("DataFetcherManager를 찾지 못해 임시 데이터 사용")
            return self._get_placeholder_quote(stock_code)
        except Exception as e:
            logger.error(f"실시간 시세 가져오기 실패: {e}", exc_info=True)
            return None
    
    def get_history_data(
        self,
        stock_code: str,
        period: str = "daily",
        days: int = 30
    ) -> Dict[str, Any]:
        """
        종목 과거 시세 가져오기
        
        Args:
            stock_code: 종목 코드
            period: K선 주기 (daily/weekly/monthly)
            days: 가져올 일수
            
        Returns:
            과거 시세 데이터 딕셔너리
            
        Raises:
            ValueError: period가 daily가 아닐 때 발생(weekly/monthly는 아직 구현 안 됨)
        """
        # period 인자 검증, daily만 지원
        if period != "daily":
            raise ValueError(
                f"'{period}' 주기는 아직 지원하지 않습니다. 현재는 'daily'만 지원합니다. "
                "weekly/monthly 집계 기능은 이후 버전에서 구현할 예정입니다."
            )
        
        try:
            # 데이터 가져오기 도구로 과거 데이터 조회
            from data_provider.base import DataFetcherManager
            
            manager = DataFetcherManager()
            df, source = manager.get_daily_data(stock_code, days=days)
            
            if df is None or df.empty:
                logger.warning(f"종목 {stock_code} 과거 데이터 가져오기 실패")
                return {"stock_code": stock_code, "period": period, "data": []}
            
            # 종목명 가져오기
            stock_name = manager.get_stock_name(stock_code)
            
            # 응답 형식으로 변환
            data = []
            for _, row in df.iterrows():
                date_val = row.get("date")
                if hasattr(date_val, "strftime"):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)
                
                data.append({
                    "date": date_str,
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0)) if row.get("volume") else None,
                    "amount": float(row.get("amount", 0)) if row.get("amount") else None,
                    "change_percent": float(row.get("pct_chg", 0)) if row.get("pct_chg") else None,
                })
            
            return {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "period": period,
                "data": data,
            }
            
        except ImportError:
            logger.warning("DataFetcherManager를 찾지 못해 빈 데이터 반환")
            return {"stock_code": stock_code, "period": period, "data": []}
        except Exception as e:
            logger.error(f"과거 데이터 가져오기 실패: {e}", exc_info=True)
            return {"stock_code": stock_code, "period": period, "data": []}
    
    def _get_placeholder_quote(self, stock_code: str) -> Dict[str, Any]:
        """
        임시 시세 데이터 가져오기(테스트용)
        
        Args:
            stock_code: 종목 코드
            
        Returns:
            임시 시세 데이터
        """
        return {
            "stock_code": stock_code,
            "stock_name": f"股票{stock_code}",
            "current_price": 0.0,
            "change": None,
            "change_percent": None,
            "open": None,
            "high": None,
            "low": None,
            "prev_close": None,
            "volume": None,
            "amount": None,
            "update_time": datetime.now().isoformat(),
        }
