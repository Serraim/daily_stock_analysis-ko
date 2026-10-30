# -*- coding: utf-8 -*-
"""
===================================
일괄 분석 명령
===================================

관심 종목 목록의 모든 종목을 한꺼번에 분석합니다.
"""

import logging
import threading
import uuid
from typing import List

from bot.commands.base import BotCommand
from bot.models import BotMessage, BotResponse

logger = logging.getLogger(__name__)


class BatchCommand(BotCommand):
    """
    일괄 분석 명령
    
    설정된 관심 종목 목록을 일괄 분석하고 요약 보고서를 만듭니다.
    
    사용법:
        /batch      - 관심 종목 전체 분석
        /batch 3    - 앞의 3개만 분석
    """
    
    @property
    def name(self) -> str:
        return "batch"
    
    @property
    def aliases(self) -> List[str]:
        return ["b", "批量", "全部"]
    
    @property
    def description(self) -> str:
        return "관심 종목 일괄 분석"
    
    @property
    def usage(self) -> str:
        return "/batch [개수]"
    
    @property
    def admin_only(self) -> bool:
        """일괄 분석에 관리자 권한이 필요한지(남용 방지)"""
        return False  # 필요하면 True로 바꿀 수 있음
    
    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """일괄 분석 명령 실행"""
        from src.config import get_config
        
        config = get_config()
        config.refresh_stock_list()
        
        stock_list = config.stock_list
        
        if not stock_list:
            return BotResponse.error_response(
                "관심 종목 목록이 비어 있습니다. 먼저 STOCK_LIST를 설정해 주세요"
            )
        
        # 개수 인자 해석
        limit = None
        if args:
            try:
                limit = int(args[0])
                if limit <= 0:
                    return BotResponse.error_response("개수는 0보다 커야 합니다")
            except ValueError:
                return BotResponse.error_response(f"잘못된 개수: {args[0]}")
        
        # 분석 개수 제한
        if limit:
            stock_list = stock_list[:limit]
        
        logger.info(f"[BatchCommand] {len(stock_list)}개 종목 일괄 분석 시작")
        
        # 백그라운드 스레드에서 분석 실행
        thread = threading.Thread(
            target=self._run_batch_analysis,
            args=(stock_list, message),
            daemon=True
        )
        thread.start()
        
        return BotResponse.markdown_response(
            f"✅ **일괄 분석 작업을 시작했습니다**\n\n"
            f"• 분석 개수: {len(stock_list)}개\n"
            f"• 종목 목록: {', '.join(stock_list[:5])}"
            f"{'...' if len(stock_list) > 5 else ''}\n\n"
            f"분석이 끝나면 요약 보고서를 자동으로 보내 드립니다."
        )
    
    def _run_batch_analysis(self, stock_list: List[str], message: BotMessage) -> None:
        """백그라운드에서 일괄 분석 실행"""
        try:
            from src.config import get_config
            from main import StockAnalysisPipeline
            
            config = get_config()
            
            # 분석 파이프라인 만들기
            pipeline = StockAnalysisPipeline(
                config=config,
                source_message=message,
                query_id=uuid.uuid4().hex,
                query_source="bot"
            )
            
            # 분석 실행(요약 보고서 자동 발송)
            results = pipeline.run(
                stock_codes=stock_list,
                dry_run=False,
                send_notification=True
            )
            
            logger.info(f"[BatchCommand] 일괄 분석 완료, 성공 {len(results)}개")
            
        except Exception as e:
            logger.error(f"[BatchCommand] 일괄 분석 실패: {e}")
            logger.exception(e)
