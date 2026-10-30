# -*- coding: utf-8 -*-
"""
===================================
실시간 시세 공통 타입 정의 & 서킷 브레이커
===================================

설계 목표:
1. 데이터 소스마다 다른 실시간 시세 응답을 하나의 구조로 통일
2. 서킷 브레이커/쿨다운으로 연속 실패 시 같은 요청을 반복하지 않음
3. 여러 데이터 소스 간 자동 전환 지원

사용 방법:
- 모든 Fetcher의 get_realtime_quote()는 UnifiedRealtimeQuote를 반환
- CircuitBreaker 가 데이터 소스별 차단 상태를 관리
"""

import logging
import time
from threading import RLock
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Union
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================
# 공통 타입 변환 헬퍼 함수
# ============================================
# 설계 메모:
# 데이터 소스마다 원본 데이터 타입이 제각각이라(str/float/int/NaN)
# 이 함수들로 한 번에 변환해서 Fetcher마다 중복 정의하지 않게 함.

def safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    """
    안전하게 float로 변환
    
    처리하는 경우:
    - None / 빈 문자열 → default
    - pandas NaN / numpy NaN → default
    - 숫자 문자열 → float
    - 이미 숫자 → float
    
    Args:
        val: 변환할 값
        default: 변환에 실패했을 때 쓸 기본값
        
    Returns:
        변환된 float 또는 기본값
    """
    try:
        if val is None:
            return default
        
        # 문자열 처리
        if isinstance(val, str):
            val = val.strip()
            if val == "" or val == "-" or val == "--":
                return default
        
        # pandas/numpy NaN 처리
        # pd.isna 대신 math.isnan을 써서 pandas 의존을 피함
        import math
        try:
            if math.isnan(float(val)):
                return default
        except (ValueError, TypeError):
            pass
        
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    """
    안전하게 int로 변환
    
    먼저 float로 바꾼 뒤 정수로 만들어 "123.0" 같은 값도 처리
    
    Args:
        val: 변환할 값
        default: 변환에 실패했을 때 쓸 기본값
        
    Returns:
        변환된 int 또는 기본값
    """
    f_val = safe_float(val, default=None)
    if f_val is not None:
        return int(f_val)
    return default


class RealtimeSource(Enum):
    """실시간 시세 데이터 소스"""
    EFINANCE = "efinance"           # 둥팡차이푸(efinance 라이브러리)
    AKSHARE_EM = "akshare_em"       # 둥팡차이푸(akshare 라이브러리)
    AKSHARE_SINA = "akshare_sina"   # 시나 파이낸스
    AKSHARE_QQ = "akshare_qq"       # 텐센트 파이낸스
    TUSHARE = "tushare"             # Tushare Pro
    TICKFLOW = "tickflow"           # TickFlow
    TENCENT = "tencent"             # 텐센트 직접 연결
    SINA = "sina"                   # 시나 직접 연결
    STOOQ = "stooq"                 # Stooq 미국 주식 최후 대안
    LONGBRIDGE = "longbridge"       # 롱브리지(미국/홍콩 주식 최후 대안)
    FUTU = "futu"                   # 푸투 OpenD(홍콩 주식)
    FALLBACK = "fallback"           # 최후 대안(기능 축소)


@dataclass
class UnifiedRealtimeQuote:
    """
    공통 실시간 시세 데이터 구조
    
    설계 원칙:
    - 데이터 소스마다 필드가 다를 수 있으니 없는 필드는 None으로 둠
    - 메인 흐름은 getattr(quote, field, None)로 읽어서 호환성을 지킴
    - source 필드에 데이터 출처를 적어 디버깅을 쉽게 함
    """
    code: str
    name: str = ""
    source: RealtimeSource = RealtimeSource.FALLBACK

    # === 데이터 품질 메타데이터(DataFetcherManager가 한꺼번에 채움)===
    fetched_at: Optional[str] = None             # 이 시스템이 받아 온 시각(ISO 8601 datetime)
    provider_timestamp: Optional[str] = None     # Provider가 준 실제 시세 시각(ISO 8601 datetime)
    is_stale: Optional[bool] = None              # provider_timestamp가 최소 TTL 기준을 넘으면 True
    stale_seconds: Optional[int] = None          # provider_timestamp와 fetched_at 사이의 초
    fallback_from: Optional[str] = None          # 소스 전체를 대체했을 때 실패한 1순위 소스 token
    market: Optional[str] = None                 # 시장 라벨(cn/hk/us/jp/kr/tw)
    currency: Optional[str] = None               # 호가 통화(JPY/KRW/TWD/USD/HKD/CNY 등)
    data_quality: Optional[str] = None           # ok/partial/unavailable
    missing_fields: Optional[list[str]] = None   # provider 응답에서 빠진 핵심 필드
    
    # === 핵심 가격 데이터(거의 모든 소스에 있음)===
    price: Optional[float] = None           # 현재가
    change_pct: Optional[float] = None      # 등락률(%)
    change_amount: Optional[float] = None   # 등락폭
    
    # === 거래량·거래대금 지표(일부 소스에는 없을 수 있음)===
    volume: Optional[int] = None            # 거래량(주 단위, 과거 일봉과 같은 기준)
    amount: Optional[float] = None          # 거래대금(위안)
    volume_ratio: Optional[float] = None    # 거래량 비율
    turnover_rate: Optional[float] = None   # 회전율(%)
    amplitude: Optional[float] = None       # 변동폭(%)
    
    # === 가격 범위 ===
    open_price: Optional[float] = None      # 시가
    high: Optional[float] = None            # 고가
    low: Optional[float] = None             # 저가
    pre_close: Optional[float] = None       # 전일 종가
    
    # === 밸류에이션 지표(둥팡차이푸처럼 전체 데이터를 주는 API에만 있음)===
    pe_ratio: Optional[float] = None        # PER(동적)
    pb_ratio: Optional[float] = None        # PBR
    total_mv: Optional[float] = None        # 시가총액(위안)
    circ_mv: Optional[float] = None         # 유통 시가총액(위안)
    
    # === 기타 지표 ===
    change_60d: Optional[float] = None      # 60일 등락률(%)
    high_52w: Optional[float] = None        # 52주 최고가
    low_52w: Optional[float] = None         # 52주 최저가
    
    def to_dict(self) -> Dict[str, Any]:
        """dict로 변환(None 값은 뺌)"""
        result = {
            'code': self.code,
            'name': self.name,
            'source': self.source.value,
        }
        # None이 아닌 필드만 넣음
        optional_fields = [
            'fetched_at', 'provider_timestamp', 'is_stale', 'stale_seconds',
            'fallback_from', 'market', 'currency', 'data_quality', 'missing_fields',
            'price', 'change_pct', 'change_amount', 'volume', 'amount',
            'volume_ratio', 'turnover_rate', 'amplitude',
            'open_price', 'high', 'low', 'pre_close',
            'pe_ratio', 'pb_ratio', 'total_mv', 'circ_mv',
            'change_60d', 'high_52w', 'low_52w'
        ]
        for f in optional_fields:
            val = getattr(self, f, None)
            if val is not None:
                result[f] = val
        return result
    
    def has_basic_data(self) -> bool:
        """기본 가격 데이터가 있는지 확인"""
        return self.price is not None and self.price > 0
    
    def has_volume_data(self) -> bool:
        """거래량·거래대금 데이터가 있는지 확인"""
        return self.volume_ratio is not None or self.turnover_rate is not None


@dataclass
class ChipDistribution:
    """
    매물대 분포 데이터
    
    보유 단가 분포와 수익 상황을 보여 줌
    """
    code: str
    date: str = ""
    source: str = "akshare"
    
    # 수익 상황
    profit_ratio: float = 0.0     # 수익 비율(0-1)
    avg_cost: float = 0.0         # 평균 단가
    
    # 매물 집중도
    cost_90_low: float = 0.0      # 90% 매물 단가 하한
    cost_90_high: float = 0.0     # 90% 매물 단가 상한
    concentration_90: float = 0.0  # 90% 매물 집중도(작을수록 집중)
    
    cost_70_low: float = 0.0      # 70% 매물 단가 하한
    cost_70_high: float = 0.0     # 70% 매물 단가 상한
    concentration_70: float = 0.0  # 70% 매물 집중도
    
    def to_dict(self) -> Dict[str, Any]:
        """dict로 변환"""
        return {
            'code': self.code,
            'date': self.date,
            'source': self.source,
            'profit_ratio': self.profit_ratio,
            'avg_cost': self.avg_cost,
            'cost_90_low': self.cost_90_low,
            'cost_90_high': self.cost_90_high,
            'concentration_90': self.concentration_90,
            'concentration_70': self.concentration_70,
        }
    
    def get_chip_status(self, current_price: float) -> str:
        """
        매물대 상태 설명을 만듦
        
        Args:
            current_price: 현재 주가
            
        Returns:
            매물대 상태 설명
        """
        status_parts = []
        
        # 수익 비율 분석
        if self.profit_ratio >= 0.9:
            status_parts.append("获利盘极高(获利盘>90%)")
        elif self.profit_ratio >= 0.7:
            status_parts.append("获利盘较高(获利盘70-90%)")
        elif self.profit_ratio >= 0.5:
            status_parts.append("获利盘中等(获利盘50-70%)")
        elif self.profit_ratio >= 0.3:
            status_parts.append("套牢盘中等(套牢盘50-70%)")
        elif self.profit_ratio >= 0.1:
            status_parts.append("套牢盘较高(套牢盘70-90%)")
        else:
            status_parts.append("套牢盘极高(套牢盘>90%)")
        
        # 매물 집중도 분석 (90% 집중도 < 10% 이면 집중)
        if self.concentration_90 < 0.08:
            status_parts.append("筹码高度集中")
        elif self.concentration_90 < 0.15:
            status_parts.append("筹码较集中")
        elif self.concentration_90 < 0.25:
            status_parts.append("筹码分散度中等")
        else:
            status_parts.append("筹码较分散")
        
        # 평균 단가와 현재가 비교
        if current_price > 0 and self.avg_cost > 0:
            cost_diff = (current_price - self.avg_cost) / self.avg_cost * 100
            if cost_diff > 20:
                status_parts.append(f"现价高于平均成本{cost_diff:.1f}%")
            elif cost_diff > 5:
                status_parts.append(f"现价略高于成本{cost_diff:.1f}%")
            elif cost_diff > -5:
                status_parts.append("现价接近平均成本")
            else:
                status_parts.append(f"现价低于平均成本{abs(cost_diff):.1f}%")
        
        return "，".join(status_parts)


class CircuitBreaker:
    """
    서킷 브레이커 - 데이터 소스의 차단/쿨다운 상태 관리
    
    전략:
    - N번 연속 실패하면 차단 상태로 전환
    - 차단 중에는 이 데이터 소스를 건너뜀
    - 쿨다운이 끝나면 자동으로 반개방 상태가 됨
    - 반개방 상태에서 한 번 성공하면 완전히 복구, 실패하면 다시 차단
    
    상태 전이:
    CLOSED(정상) --N번 실패--> OPEN(차단) --쿨다운 끝--> HALF_OPEN(반개방)
    HALF_OPEN --성공--> CLOSED
    HALF_OPEN --실패--> OPEN
    """
    
    # 상태 상수
    CLOSED = "closed"      # 정상 상태
    OPEN = "open"          # 차단 상태(사용 불가)
    HALF_OPEN = "half_open"  # 반개방 상태(시험 삼아 요청)
    
    def __init__(
        self,
        failure_threshold: int = 3,       # 연속 실패 횟수 기준
        cooldown_seconds: float = 300.0,  # 쿨다운 시간(초), 기본 5분
        half_open_max_calls: int = 1      # 반개방 상태에서 최대 시도 횟수
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_max_calls = half_open_max_calls
        
        # 데이터 소스별 상태 {source_name: {state, failures, last_failure_time, half_open_calls}}
        self._states: Dict[str, Dict[str, Any]] = {}
        self._lock = RLock()
    
    def _get_state_locked(self, source: str) -> Dict[str, Any]:
        """데이터 소스 상태를 가져오거나 새로 만듦(호출하는 쪽이 락을 잡고 있어야 함)."""
        if source not in self._states:
            self._states[source] = {
                'state': self.CLOSED,
                'failures': 0,
                'last_failure_time': 0.0,
                'half_open_calls': 0
            }
        return self._states[source]
    
    def is_available(self, source: str) -> bool:
        """
        데이터 소스를 쓸 수 있는지 확인
        
        True면 요청을 시도해도 됨
        False면 이 데이터 소스를 건너뛰어야 함
        """
        with self._lock:
            state = self._get_state_locked(source)
            current_time = time.time()

            if state['state'] == self.CLOSED:
                return True

            if state['state'] == self.OPEN:
                # 쿨다운 시간 확인
                time_since_failure = current_time - state['last_failure_time']
                if time_since_failure >= self.cooldown_seconds:
                    # 쿨다운 끝, 반개방 상태로 전환(시도 횟수는 미리 잡지 않고 HALF_OPEN 분기에서 관리)
                    state['state'] = self.HALF_OPEN
                    state['half_open_calls'] = 0
                    state['last_failure_time'] = current_time
                    logger.info(f"[서킷 브레이커] {source} 쿨다운 끝, 반개방 상태로 전환")
                    # Fall through to HALF_OPEN check below
                else:
                    remaining = self.cooldown_seconds - time_since_failure
                    logger.debug(f"[서킷 브레이커] {source} 차단 중, 남은 쿨다운: {remaining:.0f}s")
                    return False

            if state['state'] == self.HALF_OPEN:
                if state['half_open_calls'] < self.half_open_max_calls:
                    state['half_open_calls'] += 1
                    return True
                # 시험 요청 횟수를 다 썼는데 쿨다운이 또 끝날 때까지
                # record_success/record_failure 호출이 없으면 횟수를 초기화해서 다시 시험하게 함.
                # HALF_OPEN 상태에 영원히 갇히지 않게 하려는 것.
                time_since_failure = current_time - state['last_failure_time']
                if time_since_failure >= self.cooldown_seconds:
                    state['half_open_calls'] = 1
                    state['last_failure_time'] = current_time
                    logger.info(f"[서킷 브레이커] {source} 반개방 시험 요청 시간 초과, 다시 시험")
                    return True
                return False

            return True
    
    def record_inconclusive(self, source: str) -> None:
        """결과가 애매한 시험 요청(None 반환 등)을 기록.

        HALF_OPEN 상태에만 영향: OPEN으로 되돌려 쿨다운 뒤 다시 시험하게 함.
        CLOSED 상태에서는 아무것도 안 하고 실패 횟수에도 영향 없음.
        """
        with self._lock:
            state = self._get_state_locked(source)
            if state['state'] == self.HALF_OPEN:
                state['state'] = self.OPEN
                state['half_open_calls'] = 0
                state['last_failure_time'] = time.time()
                logger.info(f"[서킷 브레이커] {source} 반개방 시험 결과가 애매해서 다시 쿨다운")

    def record_success(self, source: str) -> None:
        """성공한 요청 기록"""
        with self._lock:
            state = self._get_state_locked(source)

            if state['state'] == self.HALF_OPEN:
                # 반개방 상태에서 성공, 완전히 복구
                logger.info(f"[서킷 브레이커] {source} 반개방 요청 성공, 정상으로 복구")

            # 상태 초기화
            state['state'] = self.CLOSED
            state['failures'] = 0
            state['half_open_calls'] = 0
    
    def record_failure(self, source: str, error: Optional[str] = None) -> None:
        """실패한 요청 기록"""
        with self._lock:
            state = self._get_state_locked(source)
            current_time = time.time()

            state['failures'] += 1
            state['last_failure_time'] = current_time

            if state['state'] == self.HALF_OPEN:
                # 반개방 상태에서 실패, 계속 차단
                state['state'] = self.OPEN
                state['half_open_calls'] = 0
                logger.warning(f"[서킷 브레이커] {source} 반개방 요청 실패, {self.cooldown_seconds}s 동안 계속 차단")
            elif state['failures'] >= self.failure_threshold:
                # 기준 횟수에 도달, 차단 시작
                state['state'] = self.OPEN
                logger.warning(f"[서킷 브레이커] {source} {state['failures']}번 연속 실패, 차단 상태로 전환 "
                              f"(쿨다운 {self.cooldown_seconds}s)")
                if error:
                    logger.warning(f"[서킷 브레이커] 마지막 오류: {error}")
    
    def get_status(self) -> Dict[str, str]:
        """모든 데이터 소스 상태 조회"""
        with self._lock:
            return {source: info['state'] for source, info in self._states.items()}
    
    def reset(self, source: Optional[str] = None) -> None:
        """서킷 브레이커 상태 초기화"""
        with self._lock:
            if source:
                if source in self._states:
                    del self._states[source]
            else:
                self._states.clear()


# 전역 서킷 브레이커 인스턴스(실시간 시세 전용)
_realtime_circuit_breaker = CircuitBreaker(
    failure_threshold=3,      # 3번 연속 실패하면 차단
    cooldown_seconds=300.0,   # 5분 쿨다운
    half_open_max_calls=1
)

# 매물대 API 서킷 브레이커(이 API가 더 불안정해서 더 보수적으로 설정)
_chip_circuit_breaker = CircuitBreaker(
    failure_threshold=2,      # 2번 연속 실패하면 차단
    cooldown_seconds=600.0,   # 10분 쿨다운
    half_open_max_calls=1
)


def get_realtime_circuit_breaker() -> CircuitBreaker:
    """실시간 시세 서킷 브레이커 조회"""
    return _realtime_circuit_breaker


def get_chip_circuit_breaker() -> CircuitBreaker:
    """매물대 API 서킷 브레이커 조회"""
    return _chip_circuit_breaker
