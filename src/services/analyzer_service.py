# -*- coding: utf-8 -*-
"""
===================================
A주 관심종목 지능형 분석 시스템 - 분석 서비스 계층
===================================

역할:
1. 핵심 분석 로직을 캡슐화해 여러 호출자(CLI, WebUI, Bot)를 지원
2. 명령줄 인자에 의존하지 않는 명확한 API 제공
3. 의존성 주입을 지원해 테스트와 확장이 쉬움
4. 분석 흐름과 설정을 한곳에서 관리
"""

import uuid
from typing import List, Optional

from src.analyzer import AnalysisResult
from src.core.market_review import run_market_review
from src.core.pipeline import StockAnalysisPipeline
from src.config import Config, get_config
from src.enums import ReportType
from src.notification import NotificationService


def analyze_stock(
    stock_code: str,
    config: Config = None,
    full_report: bool = False,
    notifier: Optional[NotificationService] = None,
) -> Optional[AnalysisResult]:
    """
    종목 하나 분석

    Args:
        stock_code: 종목 코드
        config: 설정 객체(선택, 기본은 싱글턴 사용)
        full_report: 전체 리포트 생성 여부
        notifier: 알림 서비스(선택)

    Returns:
        분석 결과 객체
    """
    if config is None:
        config = get_config()

    # 분석 파이프라인 생성
    pipeline = StockAnalysisPipeline(
        config=config,
        query_id=uuid.uuid4().hex,
        query_source="cli"
    )

    # 알림 서비스 사용(전달된 경우)
    if notifier:
        pipeline.notifier = notifier

    # full_report 인자로 리포트 유형 설정
    report_type = ReportType.FULL if full_report else ReportType.SIMPLE

    # 종목 하나 분석 실행
    result = pipeline.process_single_stock(
        code=stock_code,
        skip_analysis=False,
        single_stock_notify=notifier is not None,
        report_type=report_type,
    )

    return result


def analyze_stocks(
    stock_codes: List[str],
    config: Config = None,
    full_report: bool = False,
    notifier: Optional[NotificationService] = None,
) -> List[AnalysisResult]:
    """
    여러 종목 분석

    Args:
        stock_codes: 종목 코드 목록
        config: 설정 객체(선택, 기본은 싱글턴 사용)
        full_report: 전체 리포트 생성 여부
        notifier: 알림 서비스(선택)

    Returns:
        분석 결과 목록
    """
    if config is None:
        config = get_config()

    results = []
    for stock_code in stock_codes:
        result = analyze_stock(stock_code, config, full_report, notifier)
        if result:
            results.append(result)

    return results


def perform_market_review(
    config: Config = None,
    notifier: Optional[NotificationService] = None,
) -> Optional[str]:
    """
    시장 전체 복기 실행

    Args:
        config: 설정 객체(선택, 기본은 싱글턴 사용)
        notifier: 알림 서비스(선택)

    Returns:
        복기 리포트 내용
    """
    if config is None:
        config = get_config()

    # analyzer와 search_service를 얻으려고 분석 파이프라인 생성
    pipeline = StockAnalysisPipeline(
        config=config,
        query_id=uuid.uuid4().hex,
        query_source="cli",
    )

    # 전달된 알림 서비스를 쓰거나 새로 만든다
    review_notifier = notifier or pipeline.notifier

    # 시장 복기 함수 호출
    return run_market_review(
        notifier=review_notifier,
        analyzer=pipeline.analyzer,
        search_service=pipeline.search_service,
        config=config,
        trigger_source="service",
    )
