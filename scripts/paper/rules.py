"""전문가들이 흔히 말하는 매수·매도 규칙 모음 (G~M). 모두 파라미터를 받아 최적화할 수 있게 만든다.

각 규칙은 engine.simulate() 에 넘기는 step(p, day, px, st, first, cday) 함수를 돌려준다.
ctx: 지표 DataFrame 모음 (sma50, sma200, rsi, bb_lo, bb_hi, high252)
"""
import math

import pandas as pd

from engine import rebalance_to


def indicators(krx):
    smas = {f"sma{n}": krx.rolling(n, min_periods=n).mean() for n in (20, 50, 100, 150, 200)}
    d = krx.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn.replace(0, float("nan")))
    m20 = krx.rolling(20, min_periods=20).mean()
    sd20 = krx.rolling(20, min_periods=20).std()
    return {**smas, "rsi": rsi,
            "bb_lo": m20 - 2 * sd20, "bb_hi": m20 + 2 * sd20,
            "high252": krx.rolling(252, min_periods=20).max()}


def _get(ctx, k, day, t):
    try:
        v = ctx[k].at[day, t]
    except KeyError:
        return float("nan")
    return v


def _invest_core(p, weights, px, st, reserve_ratio, cday, first):
    """입금일마다 (1-reserve_ratio)는 바로 투자, reserve_ratio 는 '총알'로 남긴다."""
    if first:
        st["bullet"] = 0.0
    if cday:
        free = p.cash - st["bullet"]
        st["bullet"] += free * reserve_ratio
        rebalance_to(p, weights, px, budget=free * (1 - reserve_ratio))


# G. 하락 분할매수(사다리): 고점 대비 -a%, -2a%, -3a% 떨어질 때마다 총알의 1/3 투입
def make_dip_ladder(ctx, weights, step_pct=0.10, reserve_ratio=0.3):
    def step(p, day, px, st, first, cday):
        _invest_core(p, weights, px, st, reserve_ratio, cday, first)
        st.setdefault("lvl", {})
        for t in weights:
            hi = _get(ctx, "high252", day, t)
            if math.isnan(px[t]) or math.isnan(hi):
                continue
            dd = 1 - px[t] / hi
            lvl = int(dd // step_pct)
            if dd < 0.01:
                st["lvl"][t] = 0          # 고점 회복 시 단계 초기화
            if lvl > st["lvl"].get(t, 0) and lvl <= 3 and st["bullet"] > 0:
                amt = min(st["bullet"], st["bullet"] / (4 - lvl) if lvl < 3 else st["bullet"])
                before = p.cash
                p.buy(t, amt, px)
                st["bullet"] -= before - p.cash
                st["lvl"][t] = lvl
    return step


# H. 손절 규칙(윌리엄 오닐): 평균 매수가 대비 -x% 이면 전량 매도, 50일선 회복 전까지 재매수 금지
def make_stop_loss(ctx, weights, stop=0.08):
    def step(p, day, px, st, first, cday):
        st.setdefault("ban", set())
        for t in list(p.sh):
            if p.sh.get(t) and px[t] < p.cost.get(t, px[t]) * (1 - stop):
                p.sell(t, px)
                st["ban"].add(t)
        for t in list(st["ban"]):
            s50 = _get(ctx, "sma50", day, t)
            if not math.isnan(s50) and px[t] > s50:
                st["ban"].discard(t)
        live = {t: w for t, w in weights.items() if t not in st["ban"]}
        if live and (cday or first or p.cash > 0):
            rebalance_to(p, live, px)
    return step


# I. 익절·손절 밴드: +tp% 이익이면 매도, -sl% 손실이면 매도, 다음 입금일에 다시 매수
def make_take_profit(ctx, weights, tp=0.25, sl=0.10):
    def step(p, day, px, st, first, cday):
        for t in list(p.sh):
            c = p.cost.get(t)
            if p.sh.get(t) and c and (px[t] >= c * (1 + tp) or px[t] <= c * (1 - sl)):
                p.sell(t, px)
                p.cost[t] = 0
        if cday or first:
            rebalance_to(p, weights, px)
    return step


# J. 골든크로스/데드크로스: 단기선(fast)이 장기선(slow) 위면 보유, 아래면 현금
def make_cross(ctx, weights, fast="sma50", slow="sma200"):
    def step(p, day, px, st, first, cday):
        on = {}
        for t in weights:
            f, s = _get(ctx, fast, day, t), _get(ctx, slow, day, t)
            on[t] = math.isnan(f) or math.isnan(s) or f > s
            if not on[t]:
                p.sell(t, px)
        live = {t: w for t, w in weights.items() if on[t]}
        if live and p.cash > 0:
            rebalance_to(p, live, px)
    return step


# K. RSI 역추세: RSI<low 이면 총알 1/3 매수, RSI>high 이면 보유분 1/3 매도해 총알로
def make_rsi(ctx, weights, low=30, high=70, reserve_ratio=0.3):
    def step(p, day, px, st, first, cday):
        _invest_core(p, weights, px, st, reserve_ratio, cday, first)
        for t in weights:
            r = _get(ctx, "rsi", day, t)
            if math.isnan(r) or math.isnan(px[t]):
                continue
            if r < low and st["bullet"] > 0:
                before = p.cash
                p.buy(t, st["bullet"] / 3, px)
                st["bullet"] -= before - p.cash
            elif r > high and p.sh.get(t, 0) >= 3:
                before = p.cash
                p.sell(t, px, p.sh[t] // 3)
                st["bullet"] += p.cash - before
    return step


# L. 볼린저 밴드: 하단 이탈 시 총알 1/3 매수, 상단 돌파 시 보유분 1/3 매도
def make_bollinger(ctx, weights, reserve_ratio=0.3):
    def step(p, day, px, st, first, cday):
        _invest_core(p, weights, px, st, reserve_ratio, cday, first)
        for t in weights:
            lo, hi = _get(ctx, "bb_lo", day, t), _get(ctx, "bb_hi", day, t)
            if math.isnan(lo) or math.isnan(px[t]):
                continue
            if px[t] < lo and st["bullet"] > 0:
                before = p.cash
                p.buy(t, st["bullet"] / 3, px)
                st["bullet"] -= before - p.cash
            elif px[t] > hi and p.sh.get(t, 0) >= 3:
                before = p.cash
                p.sell(t, px, p.sh[t] // 3)
                st["bullet"] += p.cash - before
    return step


# M. 가치 평균법(마이클 에델슨): 주식 평가액 목표를 매달 일정하게 늘리고, 모자라면 사고 넘치면 판다
def make_value_avg(ctx, weights, growth=0.005):
    def step(p, day, px, st, first, cday):
        if not (cday or first):
            return
        st["k"] = st.get("k", -1) + 1
        target = p.invested * (1 + growth) ** st["k"]
        stock = p.value(px) - p.cash
        if stock < target:
            rebalance_to(p, weights, px, budget=target - stock)
        elif stock > target * 1.02:
            excess = stock - target
            for t, w in weights.items():
                if p.sh.get(t) and not math.isnan(px[t]):
                    p.sell(t, px, int(excess * w // px[t]))
    return step


RULES = {
    "G 하락 분할매수": (make_dip_ladder, {"step_pct": 0.10, "reserve_ratio": 0.3}),
    "H 손절 -8%": (make_stop_loss, {"stop": 0.08}),
    "I 익절+25%/손절-10%": (make_take_profit, {"tp": 0.25, "sl": 0.10}),
    "J 골든크로스": (make_cross, {"fast": "sma50", "slow": "sma200"}),
    "K RSI 30/70": (make_rsi, {"low": 30, "high": 70, "reserve_ratio": 0.3}),
    "L 볼린저 밴드": (make_bollinger, {"reserve_ratio": 0.3}),
    "M 가치 평균법": (make_value_avg, {"growth": 0.005}),
}

RULES_MD = """| 규칙 | 내용 | 누가 말한 방식인가 |
|---|---|---|
| G 하락 분할매수 | 입금액 70%는 바로 투자, 30%는 '총알'로 보관. 1년 고점 대비 -10/-20/-30% 떨어질 때마다 총알을 나눠 투입 | "떨어지면 나눠서 더 사라"는 분할매수 조언 |
| H 손절 -8% | 평균 매수가보다 8% 떨어지면 전량 매도, 50일선 회복 전까지 재매수 금지 | 윌리엄 오닐(CAN SLIM)의 7~8% 손절 원칙 |
| I 익절/손절 | +25% 이익이면 팔고, -10% 손실이면 팔고, 다음 달에 다시 매수 | 흔한 '목표가·손절가' 규칙 |
| J 골든크로스 | 50일선이 200일선 위면 보유, 아래로 꺾이면(데드크로스) 현금 | 차트 투자자들의 대표 신호 |
| K RSI 30/70 | RSI 30 미만(과매도)이면 총알로 매수, 70 초과(과매수)면 1/3 매도 | 웰레스 와일더의 RSI 지표 |
| L 볼린저 밴드 | 주가가 하단 밴드 아래면 매수, 상단 위면 1/3 매도 | 존 볼린저의 밴드 지표 |
| M 가치 평균법 | 주식 평가액 목표를 매달 늘려 가며, 모자라면 사고 넘치면 판다 | 마이클 에델슨의 Value Averaging |
"""
