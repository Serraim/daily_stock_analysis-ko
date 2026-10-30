# -*- coding: utf-8 -*-
"""
===================================
열거형(Enum) 정의
===================================

시스템에서 쓰는 열거형을 한곳에서 관리해 타입 안전성과 가독성을 높입니다.
"""

from enum import Enum


class ReportType(str, Enum):
    """
    리포트 유형 열거형

    API로 분석을 실행할 때 보낼 리포트 형식을 고르는 데 씁니다.
    str을 상속해서 문자열과 바로 비교하고 직렬화할 수 있습니다.
    """
    SIMPLE = "simple"  # 간단 리포트: generate_single_stock_report 사용
    FULL = "full"      # 전체 리포트: generate_dashboard_report 사용
    BRIEF = "brief"    # 요약 모드: 3-5문장 요약, 모바일/푸시 알림용

    @classmethod
    def from_str(cls, value: str) -> "ReportType":
        """
        문자열을 열거형 값으로 안전하게 변환
        
        Args:
            value: 문자열 값
            
        Returns:
            해당 열거형 값. 잘못된 입력이면 기본값 SIMPLE 반환
        """
        try:
            normalized = value.lower().strip()
            if normalized == "detailed":
                normalized = cls.FULL.value
            return cls(normalized)
        except (ValueError, AttributeError):
            return cls.SIMPLE
    
    @property
    def display_name(self) -> str:
        """화면 표시용 이름 반환"""
        return {
            ReportType.SIMPLE: "精简报告",
            ReportType.FULL: "完整报告",
            ReportType.BRIEF: "简洁报告",
        }.get(self, "精简报告")
