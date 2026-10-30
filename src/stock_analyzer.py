# -*- coding: utf-8 -*-
"""
===================================
추세 매매 분석기 - 사용자의 매매 원칙 기반
===================================

매매 원칙 핵심:
1. 신중한 진입 - 고점 추격 금지, 매매마다 성공률을 높인다
2. 추세 매매 - MA5>MA10>MA20 정배열, 추세를 따른다
3. 효율 우선 - 매물(보유 물량) 구조가 좋은 종목에 집중
4. 매수 지점 - MA5/MA10 근처로 눌렸을 때 매수

기술적 기준:
- 정배열: MA5 > MA10 > MA20
- 이격도: (Close - MA5) / MA5 < 5% (고점 추격 금지)
- 거래량 패턴: 거래량 줄며 눌리는 조정을 우선
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List
from enum import Enum

import pandas as pd
import numpy as np

from src.config import get_config
from src.schemas.decision_scale import signal_key_for_score

logger = logging.getLogger(__name__)


class TrendStatus(Enum):
    """추세 상태 열거형"""
    STRONG_BULL = "强势多头"      # MA5 > MA10 > MA20, 간격이 벌어지는 중
    BULL = "多头排列"             # MA5 > MA10 > MA20
    WEAK_BULL = "弱势多头"        # MA5 > MA10, 단 MA10 < MA20
    CONSOLIDATION = "盘整"        # 이동평균선이 서로 얽힘
    WEAK_BEAR = "弱势空头"        # MA5 < MA10, 단 MA10 > MA20
    BEAR = "空头排列"             # MA5 < MA10 < MA20
    STRONG_BEAR = "强势空头"      # MA5 < MA10 < MA20, 간격이 벌어지는 중


class VolumeStatus(Enum):
    """거래량 상태 열거형"""
    HEAVY_VOLUME_UP = "放量上涨"       # 거래량과 가격이 함께 상승
    HEAVY_VOLUME_DOWN = "放量下跌"     # 거래량 늘며 급락
    SHRINK_VOLUME_UP = "缩量上涨"      # 거래량 없이 상승
    SHRINK_VOLUME_DOWN = "缩量回调"    # 거래량 줄며 조정 (좋음)
    NORMAL = "量能正常"


class BuySignal(Enum):
    """매수 신호 열거형"""
    STRONG_BUY = "强烈买入"       # 여러 조건 충족
    BUY = "买入"                  # 기본 조건 충족
    HOLD = "持有"                 # 보유 중이면 계속 보유
    WAIT = "观望"                 # 더 좋은 시점을 기다림
    SELL = "卖出"                 # 추세 약화
    STRONG_SELL = "强烈卖出"      # 추세 붕괴


class MACDStatus(Enum):
    """MACD 상태 열거형"""
    GOLDEN_CROSS_ZERO = "零轴上金叉"      # DIF가 DEA를 상향 돌파, 0선 위에서
    GOLDEN_CROSS = "金叉"                # DIF가 DEA를 상향 돌파
    BULLISH = "多头"                    # DIF>DEA>0
    CROSSING_UP = "上穿零轴"             # DIF가 0선을 상향 돌파
    CROSSING_DOWN = "下穿零轴"           # DIF가 0선을 하향 돌파
    BEARISH = "空头"                    # DIF<DEA<0
    DEATH_CROSS = "死叉"                # DIF가 DEA를 하향 돌파


class RSIStatus(Enum):
    """RSI 상태 열거형"""
    OVERBOUGHT = "超买"        # RSI > 70
    STRONG_BUY = "强势买入"    # 50 < RSI < 70
    NEUTRAL = "中性"          # 40 <= RSI <= 60
    WEAK = "弱势"             # 30 < RSI < 40
    OVERSOLD = "超卖"         # RSI < 30


@dataclass
class TrendAnalysisResult:
    """추세 분석 결과"""
    code: str
    
    # 추세 판단
    trend_status: TrendStatus = TrendStatus.CONSOLIDATION
    ma_alignment: str = ""           # 이동평균선 배열 설명
    trend_strength: float = 0.0      # 추세 강도 0-100
    
    # 이동평균선 데이터
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0
    current_price: float = 0.0
    
    # 이격도 (MA5와 벌어진 정도)
    bias_ma5: float = 0.0            # (Close - MA5) / MA5 * 100
    bias_ma10: float = 0.0
    bias_ma20: float = 0.0
    
    # 거래량 분석
    volume_status: VolumeStatus = VolumeStatus.NORMAL
    volume_ratio_5d: float = 0.0     # 당일 거래량 / 5일 평균 거래량
    volume_trend: str = ""           # 거래량 추세 설명
    
    # 지지와 저항
    support_ma5: bool = False        # MA5가 지지선 역할을 하는지
    support_ma10: bool = False       # MA10이 지지선 역할을 하는지
    resistance_levels: List[float] = field(default_factory=list)
    support_levels: List[float] = field(default_factory=list)

    # MACD 지표
    macd_dif: float = 0.0          # DIF 빠른 선
    macd_dea: float = 0.0          # DEA 느린 선
    macd_bar: float = 0.0           # MACD 막대(히스토그램)
    macd_status: MACDStatus = MACDStatus.BULLISH
    macd_signal: str = ""            # MACD 신호 설명

    # RSI 지표
    rsi_6: float = 0.0              # RSI(6) 단기
    rsi_12: float = 0.0             # RSI(12) 중기
    rsi_24: float = 0.0             # RSI(24) 장기
    rsi_status: RSIStatus = RSIStatus.NEUTRAL
    rsi_signal: str = ""              # RSI 신호 설명

    # 매수 신호
    buy_signal: BuySignal = BuySignal.WAIT
    signal_score: int = 0            # 종합 점수 0-100
    signal_reasons: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'code': self.code,
            'trend_status': self.trend_status.value,
            'ma_alignment': self.ma_alignment,
            'trend_strength': self.trend_strength,
            'ma5': self.ma5,
            'ma10': self.ma10,
            'ma20': self.ma20,
            'ma60': self.ma60,
            'current_price': self.current_price,
            'bias_ma5': self.bias_ma5,
            'bias_ma10': self.bias_ma10,
            'bias_ma20': self.bias_ma20,
            'volume_status': self.volume_status.value,
            'volume_ratio_5d': self.volume_ratio_5d,
            'volume_trend': self.volume_trend,
            'support_ma5': self.support_ma5,
            'support_ma10': self.support_ma10,
            'buy_signal': self.buy_signal.value,
            'signal_score': self.signal_score,
            'signal_reasons': self.signal_reasons,
            'risk_factors': self.risk_factors,
            'macd_dif': self.macd_dif,
            'macd_dea': self.macd_dea,
            'macd_bar': self.macd_bar,
            'macd_status': self.macd_status.value,
            'macd_signal': self.macd_signal,
            'rsi_6': self.rsi_6,
            'rsi_12': self.rsi_12,
            'rsi_24': self.rsi_24,
            'rsi_status': self.rsi_status.value,
            'rsi_signal': self.rsi_signal,
        }


class StockTrendAnalyzer:
    """
    주식 추세 분석기

    사용자의 매매 원칙을 바탕으로 구현:
    1. 추세 판단 - MA5>MA10>MA20 정배열
    2. 이격도 점검 - 고점 추격 금지, MA5에서 5% 넘게 벌어지면 매수 안 함
    3. 거래량 분석 - 거래량 줄며 눌리는 조정을 선호
    4. 매수 지점 찾기 - MA5/MA10 지지선까지 눌림
    5. MACD 지표 - 추세 확인, 골든크로스/데드크로스 신호
    6. RSI 지표 - 과매수/과매도 판단
    """
    
    # 매매 파라미터 설정 (BIAS_THRESHOLD는 Config에서 읽음, _generate_signal 참고)
    VOLUME_SHRINK_RATIO = 0.7   # 거래량 감소 판단 기준 (당일 거래량 / 5일 평균)
    VOLUME_HEAVY_RATIO = 1.5    # 거래량 증가 판단 기준
    MA_SUPPORT_TOLERANCE = 0.02  # MA 지지 판단 허용 오차 (2%)

    # MACD 파라미터 (표준 12/26/9)
    MACD_FAST = 12              # 빠른 선 기간
    MACD_SLOW = 26             # 느린 선 기간
    MACD_SIGNAL = 9             # 신호선 기간

    # RSI 파라미터
    RSI_SHORT = 6               # 단기 RSI 기간
    RSI_MID = 12               # 중기 RSI 기간
    RSI_LONG = 24              # 장기 RSI 기간
    RSI_OVERBOUGHT = 70        # 과매수 기준
    RSI_OVERSOLD = 30          # 과매도 기준
    
    def __init__(self):
        """분석기 초기화"""
        pass
    
    def analyze(self, df: pd.DataFrame, code: str) -> TrendAnalysisResult:
        """
        주식 추세 분석
        
        Args:
            df: OHLCV 데이터가 담긴 DataFrame
            code: 종목 코드
            
        Returns:
            TrendAnalysisResult 분석 결과
        """
        result = TrendAnalysisResult(code=code)
        
        if df is None or df.empty or len(df) < 20:
            logger.warning(f"{code} 데이터가 부족해 추세 분석을 할 수 없음")
            result.risk_factors.append("数据不足，无法完成分析")
            return result
        
        # 날짜 순으로 정렬되어 있는지 확인
        df = df.sort_values('date').reset_index(drop=True)
        
        # 이동평균선 계산
        df = self._calculate_mas(df)

        # MACD와 RSI 계산
        df = self._calculate_macd(df)
        df = self._calculate_rsi(df)

        # 최신 데이터 가져오기
        latest = df.iloc[-1]
        result.current_price = float(latest['close'])
        result.ma5 = float(latest['MA5'])
        result.ma10 = float(latest['MA10'])
        result.ma20 = float(latest['MA20'])
        result.ma60 = float(latest.get('MA60', 0))

        # 1. 추세 판단
        self._analyze_trend(df, result)

        # 2. 이격도 계산
        self._calculate_bias(result)

        # 3. 거래량 분석
        self._analyze_volume(df, result)

        # 4. 지지/저항 분석
        self._analyze_support_resistance(df, result)

        # 5. MACD 분석
        self._analyze_macd(df, result)

        # 6. RSI 분석
        self._analyze_rsi(df, result)

        # 7. 매수 신호 생성
        self._generate_signal(result)

        return result
    
    def _calculate_mas(self, df: pd.DataFrame) -> pd.DataFrame:
        """이동평균선 계산"""
        df = df.copy()
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        if len(df) >= 60:
            df['MA60'] = df['close'].rolling(window=60).mean()
        else:
            df['MA60'] = df['MA20']  # 데이터가 부족하면 MA20으로 대신함
        return df

    def _calculate_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        MACD 지표 계산

        공식:
        - EMA(12): 12일 지수이동평균
        - EMA(26): 26일 지수이동평균
        - DIF = EMA(12) - EMA(26)
        - DEA = EMA(DIF, 9)
        - MACD = (DIF - DEA) * 2
        """
        df = df.copy()

        # 빠른 선/느린 선 EMA 계산
        ema_fast = df['close'].ewm(span=self.MACD_FAST, adjust=False).mean()
        ema_slow = df['close'].ewm(span=self.MACD_SLOW, adjust=False).mean()

        # 빠른 선 DIF 계산
        df['MACD_DIF'] = ema_fast - ema_slow

        # 신호선 DEA 계산
        df['MACD_DEA'] = df['MACD_DIF'].ewm(span=self.MACD_SIGNAL, adjust=False).mean()

        # 막대(히스토그램) 계산
        df['MACD_BAR'] = (df['MACD_DIF'] - df['MACD_DEA']) * 2

        return df

    def _calculate_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        RSI 지표 계산 (Wilder's EMA / SMMA 방식)

        공식:
        - avg_gain / avg_loss 는 ewm(alpha=1/period, adjust=False) 사용
        - RS = avg_gain / avg_loss
        - RSI = 100 - (100 / (1 + RS))
        """
        df = df.copy()

        for period in [self.RSI_SHORT, self.RSI_MID, self.RSI_LONG]:
            # 가격 변화 계산
            delta = df['close'].diff()

            # 상승분과 하락분 분리
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)

            # Wilder's EMA / SMMA 방식 사용, 흔한 RSI 차트 도구와 같은 값이 나오게 함.
            avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

            # RS와 RSI 계산
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            # NaN 값 채우기
            rsi = rsi.fillna(50)  # 기본값은 중립(50)

            # DataFrame에 추가
            col_name = f'RSI_{period}'
            df[col_name] = rsi

        return df
    
    def _analyze_trend(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        추세 상태 분석
        
        핵심 로직: 이동평균선 배열과 추세 강도를 판단
        """
        ma5, ma10, ma20 = result.ma5, result.ma10, result.ma20
        
        # 이동평균선 배열 판단
        if ma5 > ma10 > ma20:
            # 간격이 벌어지는지 확인 (강세)
            prev = df.iloc[-5] if len(df) >= 5 else df.iloc[-1]
            prev_spread = (prev['MA5'] - prev['MA20']) / prev['MA20'] * 100 if prev['MA20'] > 0 else 0
            curr_spread = (ma5 - ma20) / ma20 * 100 if ma20 > 0 else 0
            
            if curr_spread > prev_spread and curr_spread > 5:
                result.trend_status = TrendStatus.STRONG_BULL
                result.ma_alignment = "强势多头排列，均线发散上行"
                result.trend_strength = 90
            else:
                result.trend_status = TrendStatus.BULL
                result.ma_alignment = "多头排列 MA5>MA10>MA20"
                result.trend_strength = 75
                
        elif ma5 > ma10 and ma10 <= ma20:
            result.trend_status = TrendStatus.WEAK_BULL
            result.ma_alignment = "弱势多头，MA5>MA10 但 MA10≤MA20"
            result.trend_strength = 55
            
        elif ma5 < ma10 < ma20:
            prev = df.iloc[-5] if len(df) >= 5 else df.iloc[-1]
            prev_spread = (prev['MA20'] - prev['MA5']) / prev['MA5'] * 100 if prev['MA5'] > 0 else 0
            curr_spread = (ma20 - ma5) / ma5 * 100 if ma5 > 0 else 0
            
            if curr_spread > prev_spread and curr_spread > 5:
                result.trend_status = TrendStatus.STRONG_BEAR
                result.ma_alignment = "强势空头排列，均线发散下行"
                result.trend_strength = 10
            else:
                result.trend_status = TrendStatus.BEAR
                result.ma_alignment = "空头排列 MA5<MA10<MA20"
                result.trend_strength = 25
                
        elif ma5 < ma10 and ma10 >= ma20:
            result.trend_status = TrendStatus.WEAK_BEAR
            result.ma_alignment = "弱势空头，MA5<MA10 但 MA10≥MA20"
            result.trend_strength = 40
            
        else:
            result.trend_status = TrendStatus.CONSOLIDATION
            result.ma_alignment = "均线缠绕，趋势不明"
            result.trend_strength = 50
    
    def _calculate_bias(self, result: TrendAnalysisResult) -> None:
        """
        이격도 계산
        
        이격도 = (현재가 - 이동평균) / 이동평균 * 100%
        
        신중한 진입: 이격도가 5%를 넘으면 추격 매수하지 않음
        """
        price = result.current_price
        
        if result.ma5 > 0:
            result.bias_ma5 = (price - result.ma5) / result.ma5 * 100
        if result.ma10 > 0:
            result.bias_ma10 = (price - result.ma10) / result.ma10 * 100
        if result.ma20 > 0:
            result.bias_ma20 = (price - result.ma20) / result.ma20 * 100
    
    def _analyze_volume(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        거래량 분석
        
        선호 순서: 거래량 줄며 조정 > 거래량 늘며 상승 > 거래량 줄며 상승 > 거래량 늘며 하락
        """
        if len(df) < 5:
            return
        
        latest = df.iloc[-1]
        vol_5d_avg = df['volume'].iloc[-6:-1].mean()
        
        if vol_5d_avg > 0:
            result.volume_ratio_5d = float(latest['volume']) / vol_5d_avg
        
        # 가격 변화 판단
        prev_close = df.iloc[-2]['close']
        price_change = (latest['close'] - prev_close) / prev_close * 100
        
        # 거래량 상태 판단
        if result.volume_ratio_5d >= self.VOLUME_HEAVY_RATIO:
            if price_change > 0:
                result.volume_status = VolumeStatus.HEAVY_VOLUME_UP
                result.volume_trend = "放量上涨，多头力量强劲"
            else:
                result.volume_status = VolumeStatus.HEAVY_VOLUME_DOWN
                result.volume_trend = "放量下跌，注意风险"
        elif result.volume_ratio_5d <= self.VOLUME_SHRINK_RATIO:
            if price_change > 0:
                result.volume_status = VolumeStatus.SHRINK_VOLUME_UP
                result.volume_trend = "缩量上涨，上攻动能不足"
            else:
                result.volume_status = VolumeStatus.SHRINK_VOLUME_DOWN
                result.volume_trend = "缩量回调，洗盘特征明显（好）"
        else:
            result.volume_status = VolumeStatus.NORMAL
            result.volume_trend = "量能正常"
    
    def _analyze_support_resistance(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        지지/저항 위치 분석
        
        선호 매수 지점: MA5/MA10까지 눌린 뒤 지지받을 때
        """
        price = result.current_price
        
        # MA5 근처에서 지지받는지 확인
        if result.ma5 > 0:
            ma5_distance = abs(price - result.ma5) / result.ma5
            if ma5_distance <= self.MA_SUPPORT_TOLERANCE and price >= result.ma5:
                result.support_ma5 = True
                result.support_levels.append(result.ma5)
        
        # MA10 근처에서 지지받는지 확인
        if result.ma10 > 0:
            ma10_distance = abs(price - result.ma10) / result.ma10
            if ma10_distance <= self.MA_SUPPORT_TOLERANCE and price >= result.ma10:
                result.support_ma10 = True
                if result.ma10 not in result.support_levels:
                    result.support_levels.append(result.ma10)
        
        # MA20은 중요한 지지선
        if result.ma20 > 0 and price >= result.ma20:
            result.support_levels.append(result.ma20)
        
        # 최근 고점은 저항선
        if len(df) >= 20:
            recent_high = df['high'].iloc[-20:].max()
            if recent_high > price:
                result.resistance_levels.append(recent_high)

    def _analyze_macd(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        MACD 지표 분석

        핵심 신호:
        - 0선 위 골든크로스: 가장 강한 매수 신호
        - 골든크로스: DIF가 DEA를 상향 돌파
        - 데드크로스: DIF가 DEA를 하향 돌파
        """
        if len(df) < self.MACD_SLOW:
            result.macd_signal = "数据不足"
            return

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # MACD 데이터 가져오기
        result.macd_dif = float(latest['MACD_DIF'])
        result.macd_dea = float(latest['MACD_DEA'])
        result.macd_bar = float(latest['MACD_BAR'])

        # 골든크로스/데드크로스 판단
        prev_dif_dea = prev['MACD_DIF'] - prev['MACD_DEA']
        curr_dif_dea = result.macd_dif - result.macd_dea

        # 골든크로스: DIF가 DEA를 상향 돌파
        is_golden_cross = prev_dif_dea <= 0 and curr_dif_dea > 0

        # 데드크로스: DIF가 DEA를 하향 돌파
        is_death_cross = prev_dif_dea >= 0 and curr_dif_dea < 0

        # 0선 돌파
        prev_zero = prev['MACD_DIF']
        curr_zero = result.macd_dif
        is_crossing_up = prev_zero <= 0 and curr_zero > 0
        is_crossing_down = prev_zero >= 0 and curr_zero < 0

        # MACD 상태 판단
        if is_golden_cross and curr_zero > 0:
            result.macd_status = MACDStatus.GOLDEN_CROSS_ZERO
            result.macd_signal = "⭐ 零轴上金叉，强烈买入信号！"
        elif is_crossing_up:
            result.macd_status = MACDStatus.CROSSING_UP
            result.macd_signal = "⚡ DIF上穿零轴，趋势转强"
        elif is_golden_cross:
            result.macd_status = MACDStatus.GOLDEN_CROSS
            result.macd_signal = "✅ 金叉，趋势向上"
        elif is_death_cross:
            result.macd_status = MACDStatus.DEATH_CROSS
            result.macd_signal = "❌ 死叉，趋势向下"
        elif is_crossing_down:
            result.macd_status = MACDStatus.CROSSING_DOWN
            result.macd_signal = "⚠️ DIF下穿零轴，趋势转弱"
        elif result.macd_dif > 0 and result.macd_dea > 0:
            result.macd_status = MACDStatus.BULLISH
            result.macd_signal = "✓ 多头排列，持续上涨"
        elif result.macd_dif < 0 and result.macd_dea < 0:
            result.macd_status = MACDStatus.BEARISH
            result.macd_signal = "⚠ 空头排列，持续下跌"
        else:
            result.macd_status = MACDStatus.BULLISH
            result.macd_signal = " MACD 中性区域"

    def _analyze_rsi(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        RSI 지표 분석

        핵심 판단:
        - RSI > 70: 과매수, 추격 매수 주의
        - RSI < 30: 과매도, 반등 가능성 주목
        - 40-60: 중립 구간
        """
        if len(df) < self.RSI_LONG:
            result.rsi_signal = "数据不足"
            return

        latest = df.iloc[-1]

        # RSI 데이터 가져오기
        result.rsi_6 = float(latest[f'RSI_{self.RSI_SHORT}'])
        result.rsi_12 = float(latest[f'RSI_{self.RSI_MID}'])
        result.rsi_24 = float(latest[f'RSI_{self.RSI_LONG}'])

        # 중기 RSI(12)를 기준으로 판단
        rsi_mid = result.rsi_12

        # RSI 상태 판단
        if rsi_mid > self.RSI_OVERBOUGHT:
            result.rsi_status = RSIStatus.OVERBOUGHT
            result.rsi_signal = f"⚠️ RSI超买({rsi_mid:.1f}>70)，短期回调风险高"
        elif rsi_mid > 60:
            result.rsi_status = RSIStatus.STRONG_BUY
            result.rsi_signal = f"✅ RSI强势({rsi_mid:.1f})，多头力量充足"
        elif rsi_mid >= 40:
            result.rsi_status = RSIStatus.NEUTRAL
            result.rsi_signal = f" RSI中性({rsi_mid:.1f})，震荡整理中"
        elif rsi_mid >= self.RSI_OVERSOLD:
            result.rsi_status = RSIStatus.WEAK
            result.rsi_signal = f"⚡ RSI弱势({rsi_mid:.1f})，关注反弹"
        else:
            result.rsi_status = RSIStatus.OVERSOLD
            result.rsi_signal = f"⭐ RSI超卖({rsi_mid:.1f}<30)，反弹机会大"

    def _generate_signal(self, result: TrendAnalysisResult) -> None:
        """
        매수 신호 생성

        종합 점수 체계:
        - 추세 (30점): 정배열일수록 높음
        - 이격도 (20점): MA5에 가까울수록 높음
        - 거래량 (15점): 거래량 줄며 조정이면 높음
        - 지지 (10점): 이동평균선 지지를 받으면 높음
        - MACD (15점): 골든크로스·상승 국면이면 높음
        - RSI (10점): 과매도·강세면 높음
        """
        score = 0
        reasons = []
        risks = []

        # === 추세 점수 (30점) ===
        trend_scores = {
            TrendStatus.STRONG_BULL: 30,
            TrendStatus.BULL: 26,
            TrendStatus.WEAK_BULL: 18,
            TrendStatus.CONSOLIDATION: 12,
            TrendStatus.WEAK_BEAR: 8,
            TrendStatus.BEAR: 4,
            TrendStatus.STRONG_BEAR: 0,
        }
        trend_score = trend_scores.get(result.trend_status, 12)
        score += trend_score

        if result.trend_status in [TrendStatus.STRONG_BULL, TrendStatus.BULL]:
            reasons.append(f"✅ {result.trend_status.value}，顺势做多")
        elif result.trend_status in [TrendStatus.BEAR, TrendStatus.STRONG_BEAR]:
            risks.append(f"⚠️ {result.trend_status.value}，不宜做多")

        # === 이격도 점수 (20점, 강한 추세는 보정) ===
        bias = result.bias_ma5
        if bias != bias or bias is None:  # NaN or None defense
            bias = 0.0
        base_threshold = get_config().bias_threshold

        # Strong trend compensation: relax threshold for STRONG_BULL with high strength
        trend_strength = result.trend_strength if result.trend_strength == result.trend_strength else 0.0
        if result.trend_status == TrendStatus.STRONG_BULL and (trend_strength or 0) >= 70:
            effective_threshold = base_threshold * 1.5
            is_strong_trend = True
        else:
            effective_threshold = base_threshold
            is_strong_trend = False

        if bias < 0:
            # Price below MA5 (pullback)
            if bias > -3:
                score += 20
                reasons.append(f"✅ 价格略低于MA5({bias:.1f}%)，回踩买点")
            elif bias > -5:
                score += 16
                reasons.append(f"✅ 价格回踩MA5({bias:.1f}%)，观察支撑")
            else:
                score += 8
                risks.append(f"⚠️ 乖离率过大({bias:.1f}%)，可能破位")
        elif bias < 2:
            score += 18
            reasons.append(f"✅ 价格贴近MA5({bias:.1f}%)，介入好时机")
        elif bias < base_threshold:
            score += 14
            reasons.append(f"⚡ 价格略高于MA5({bias:.1f}%)，可小仓介入")
        elif bias > effective_threshold:
            score += 4
            risks.append(
                f"❌ 乖离率过高({bias:.1f}%>{effective_threshold:.1f}%)，严禁追高！"
            )
        elif bias > base_threshold and is_strong_trend:
            score += 10
            reasons.append(
                f"⚡ 强势趋势中乖离率偏高({bias:.1f}%)，可轻仓追踪"
            )
        else:
            score += 4
            risks.append(
                f"❌ 乖离率过高({bias:.1f}%>{base_threshold:.1f}%)，严禁追高！"
            )

        # === 거래량 점수 (15점) ===
        volume_scores = {
            VolumeStatus.SHRINK_VOLUME_DOWN: 15,  # 거래량 줄며 조정이 가장 좋음
            VolumeStatus.HEAVY_VOLUME_UP: 12,     # 거래량 늘며 상승이 그다음
            VolumeStatus.NORMAL: 10,
            VolumeStatus.SHRINK_VOLUME_UP: 6,     # 거래량 없이 상승은 약함
            VolumeStatus.HEAVY_VOLUME_DOWN: 0,    # 거래량 늘며 하락이 가장 나쁨
        }
        vol_score = volume_scores.get(result.volume_status, 8)
        score += vol_score

        if result.volume_status == VolumeStatus.SHRINK_VOLUME_DOWN:
            reasons.append("✅ 缩量回调，主力洗盘")
        elif result.volume_status == VolumeStatus.HEAVY_VOLUME_DOWN:
            risks.append("⚠️ 放量下跌，注意风险")

        # === 지지 점수 (10점) ===
        if result.support_ma5:
            score += 5
            reasons.append("✅ MA5支撑有效")
        if result.support_ma10:
            score += 5
            reasons.append("✅ MA10支撑有效")

        # === MACD 점수 (15점) ===
        macd_scores = {
            MACDStatus.GOLDEN_CROSS_ZERO: 15,  # 0선 위 골든크로스가 가장 강함
            MACDStatus.GOLDEN_CROSS: 12,      # 골든크로스
            MACDStatus.CROSSING_UP: 10,       # 0선 상향 돌파
            MACDStatus.BULLISH: 8,            # 상승 국면
            MACDStatus.BEARISH: 2,            # 하락 국면
            MACDStatus.CROSSING_DOWN: 0,       # 0선 하향 돌파
            MACDStatus.DEATH_CROSS: 0,        # 데드크로스
        }
        macd_score = macd_scores.get(result.macd_status, 5)
        score += macd_score

        if result.macd_status in [MACDStatus.GOLDEN_CROSS_ZERO, MACDStatus.GOLDEN_CROSS]:
            reasons.append(f"✅ {result.macd_signal}")
        elif result.macd_status in [MACDStatus.DEATH_CROSS, MACDStatus.CROSSING_DOWN]:
            risks.append(f"⚠️ {result.macd_signal}")
        else:
            reasons.append(result.macd_signal)

        # === RSI 점수 (10점) ===
        rsi_scores = {
            RSIStatus.OVERSOLD: 10,       # 과매도가 가장 좋음
            RSIStatus.STRONG_BUY: 8,     # 강세
            RSIStatus.NEUTRAL: 5,        # 중립
            RSIStatus.WEAK: 3,            # 약세
            RSIStatus.OVERBOUGHT: 0,       # 과매수가 가장 나쁨
        }
        rsi_score = rsi_scores.get(result.rsi_status, 5)
        score += rsi_score

        if result.rsi_status in [RSIStatus.OVERSOLD, RSIStatus.STRONG_BUY]:
            reasons.append(f"✅ {result.rsi_signal}")
        elif result.rsi_status == RSIStatus.OVERBOUGHT:
            risks.append(f"⚠️ {result.rsi_signal}")
        else:
            reasons.append(result.rsi_signal)

        # === 종합 판단 ===
        result.signal_score = score
        result.signal_reasons = reasons
        result.risk_factors = risks

        # 매수 신호 생성 (canonical decision scale 과 일치시킴)
        score_signal = signal_key_for_score(score)
        if score_signal == "strong_buy" and result.trend_status in [TrendStatus.STRONG_BULL, TrendStatus.BULL]:
            result.buy_signal = BuySignal.STRONG_BUY
        elif score_signal in {"strong_buy", "buy"} and result.trend_status in [
            TrendStatus.STRONG_BULL,
            TrendStatus.BULL,
            TrendStatus.WEAK_BULL,
        ]:
            result.buy_signal = BuySignal.BUY
        elif score_signal in {"strong_buy", "buy"} and result.trend_status in [
            TrendStatus.CONSOLIDATION,
            TrendStatus.WEAK_BEAR,
        ]:
            result.buy_signal = BuySignal.WAIT
        elif score_signal == "watch":
            result.buy_signal = BuySignal.WAIT
        elif score_signal == "sell" or result.trend_status in [TrendStatus.BEAR, TrendStatus.STRONG_BEAR]:
            result.buy_signal = BuySignal.STRONG_SELL
        else:
            result.buy_signal = BuySignal.SELL
    
    def format_analysis(self, result: TrendAnalysisResult) -> str:
        """
        분석 결과를 텍스트로 정리

        Args:
            result: 분석 결과

        Returns:
            정리된 분석 텍스트
        """
        lines = [
            f"=== {result.code} 추세 분석 ===",
            f"",
            f"📊 추세 판단: {result.trend_status.value}",
            f"   이동평균선 배열: {result.ma_alignment}",
            f"   추세 강도: {result.trend_strength}/100",
            f"",
            f"📈 이동평균선 데이터:",
            f"   현재가: {result.current_price:.2f}",
            f"   MA5:  {result.ma5:.2f} (이격 {result.bias_ma5:+.2f}%)",
            f"   MA10: {result.ma10:.2f} (이격 {result.bias_ma10:+.2f}%)",
            f"   MA20: {result.ma20:.2f} (이격 {result.bias_ma20:+.2f}%)",
            f"",
            f"📊 거래량 분석: {result.volume_status.value}",
            f"   거래량 비율(5일 대비): {result.volume_ratio_5d:.2f}",
            f"   거래량 추세: {result.volume_trend}",
            f"",
            f"📈 MACD 지표: {result.macd_status.value}",
            f"   DIF: {result.macd_dif:.4f}",
            f"   DEA: {result.macd_dea:.4f}",
            f"   MACD: {result.macd_bar:.4f}",
            f"   신호: {result.macd_signal}",
            f"",
            f"📊 RSI 지표: {result.rsi_status.value}",
            f"   RSI(6): {result.rsi_6:.1f}",
            f"   RSI(12): {result.rsi_12:.1f}",
            f"   RSI(24): {result.rsi_24:.1f}",
            f"   신호: {result.rsi_signal}",
            f"",
            f"🎯 매매 제안: {result.buy_signal.value}",
            f"   종합 점수: {result.signal_score}/100",
        ]

        if result.signal_reasons:
            lines.append(f"")
            lines.append(f"✅ 매수 근거:")
            for reason in result.signal_reasons:
                lines.append(f"   {reason}")

        if result.risk_factors:
            lines.append(f"")
            lines.append(f"⚠️ 위험 요인:")
            for risk in result.risk_factors:
                lines.append(f"   {risk}")

        return "\n".join(lines)


def analyze_stock(df: pd.DataFrame, code: str) -> TrendAnalysisResult:
    """
    편의 함수: 종목 하나 분석
    
    Args:
        df: OHLCV 데이터가 담긴 DataFrame
        code: 종목 코드
        
    Returns:
        TrendAnalysisResult 분석 결과
    """
    analyzer = StockTrendAnalyzer()
    return analyzer.analyze(df, code)


if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.INFO)
    
    # 가짜 데이터로 테스트
    import numpy as np
    
    dates = pd.date_range(start='2025-01-01', periods=60, freq='D')
    np.random.seed(42)
    
    # 정배열 형태의 가짜 데이터
    base_price = 10.0
    prices = [base_price]
    for i in range(59):
        change = np.random.randn() * 0.02 + 0.003  # 완만한 상승 추세
        prices.append(prices[-1] * (1 + change))
    
    df = pd.DataFrame({
        'date': dates,
        'open': prices,
        'high': [p * (1 + np.random.uniform(0, 0.02)) for p in prices],
        'low': [p * (1 - np.random.uniform(0, 0.02)) for p in prices],
        'close': prices,
        'volume': [np.random.randint(1000000, 5000000) for _ in prices],
    })
    
    analyzer = StockTrendAnalyzer()
    result = analyzer.analyze(df, '000001')
    print(analyzer.format_analysis(result))
