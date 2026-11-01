"""규칙 파라미터 최적화 (격자 탐색 + 훈련/검증 분리) → paper/optimize.md

- 대상: S&P500 ETF(360750) 하나. 이력이 가장 길어서(2020-08 상장).
- 훈련 기간에서 목적함수가 가장 좋은 파라미터를 찾고, 그 값을 '처음 보는' 검증 기간에 그대로 적용한다.
- 목적함수: 위험 대비 수익 = 연평균 수익률(CAGR) / |최대 하락폭|  (칼마 비율과 같은 개념)
- 검증 기간에서도 기본값·적립식보다 나으면 '쓸 만한 규칙', 훈련에서만 좋으면 '과적합 의심'.
"""
import datetime as dt
import itertools
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd

import engine as E
import rules as R

TRAIN = ("2021-06-01", "2024-05-31")
TEST = ("2024-06-03", "2026-12-31")
UNI = {E.SPX: 1.0}

GRID = {
    "D 추세 추종(이평선 n일)": (lambda ctx, w, n: E.make_trend(ctx[f"sma{n}"], w), {"n": [50, 100, 150, 200]}),
    "G 하락 분할매수": (R.make_dip_ladder, {"step_pct": [0.05, 0.075, 0.10, 0.15], "reserve_ratio": [0.1, 0.2, 0.3, 0.5]}),
    "H 손절": (R.make_stop_loss, {"stop": [0.05, 0.08, 0.10, 0.15, 0.20]}),
    "I 익절/손절": (R.make_take_profit, {"tp": [0.10, 0.15, 0.25, 0.40], "sl": [0.05, 0.10, 0.15, 0.25]}),
    "J 이평선 교차": (R.make_cross, {"fast_slow": [("sma20", "sma50"), ("sma20", "sma100"), ("sma50", "sma100"),
                                                   ("sma50", "sma200"), ("sma100", "sma200")]}),
    "K RSI": (R.make_rsi, {"low": [20, 25, 30, 35], "high": [65, 70, 75, 80], "reserve_ratio": [0.2, 0.3]}),
    "L 볼린저": (R.make_bollinger, {"reserve_ratio": [0.1, 0.2, 0.3, 0.5]}),
    "M 가치 평균": (R.make_value_avg, {"growth": [0.0, 0.0025, 0.005, 0.01]}),
}
DEFAULT = {"D 추세 추종(이평선 n일)": {"n": 200}, "G 하락 분할매수": {"step_pct": 0.10, "reserve_ratio": 0.3},
           "H 손절": {"stop": 0.08}, "I 익절/손절": {"tp": 0.25, "sl": 0.10},
           "J 이평선 교차": {"fast_slow": ("sma50", "sma200")}, "K RSI": {"low": 30, "high": 70, "reserve_ratio": 0.3},
           "L 볼린저": {"reserve_ratio": 0.3}, "M 가치 평균": {"growth": 0.005}}


def score(m):
    cagr = m["cagr"] if m["cagr"] is not None else m["twr"]
    return cagr / max(abs(m["mdd"]), 0.02)


def build(fn, ctx, params):
    p = dict(params)
    if "fast_slow" in p:
        f, s = p.pop("fast_slow")
        p["fast"], p["slow"] = f, s
    return fn(ctx, UNI, **p)


def evaluate(krx, ctx, period, fn, params):
    k = krx.loc[:period[1]]
    _, port = E.simulate("x", k, period[0], build(fn, ctx, params))
    return E.metrics(port)


def fmt(m):
    c = m["cagr"] if m["cagr"] is not None else m["twr"]
    return f"{m['ret']:+.1%} / 연 {c:+.1%} / 최대하락 {m['mdd']:.1%} / 점수 {score(m):.2f}"


def label(params):
    return ", ".join(f"{k}={v[0][3:]}-{v[1][3:]}" if k == "fast_slow" else f"{k}={v}" for k, v in params.items())


def main():
    prices = E.load_prices([E.SPX], TRAIN[0])
    krx = prices[prices[E.SPX].notna()].ffill()
    ctx = R.indicators(krx)
    base_tr = E.metrics(E.simulate("A", krx.loc[:TRAIN[1]], TRAIN[0], E.make_dca(UNI))[1])
    base_te = E.metrics(E.simulate("A", krx, TEST[0], E.make_dca(UNI))[1])
    rows, detail = [], []
    for name, (fn, grid) in GRID.items():
        keys = list(grid)
        results = []
        for combo in itertools.product(*grid.values()):
            params = dict(zip(keys, combo))
            results.append((score(evaluate(krx, ctx, TRAIN, fn, params)), params))
        results.sort(key=lambda x: -x[0])
        best = results[0][1]
        d_tr, d_te = evaluate(krx, ctx, TRAIN, fn, DEFAULT[name]), evaluate(krx, ctx, TEST, fn, DEFAULT[name])
        b_tr, b_te = evaluate(krx, ctx, TRAIN, fn, best), evaluate(krx, ctx, TEST, fn, best)
        verdict = ("✅ 검증에서도 적립식보다 나음" if score(b_te) > score(base_te) else
                   "⚠️ 검증에선 적립식보다 못함")
        if score(b_te) < score(d_te):
            verdict += " · 최적값이 기본값보다 못함(과적합 의심)"
        rows.append(f"| {name} | {label(best)} | {score(b_tr):.2f} | {score(b_te):.2f} | {score(d_te):.2f} | {verdict} |")
        detail.append(f"### {name}\n- 탐색한 조합 수: {len(results)}\n- 기본값 ({label(DEFAULT[name])}): 훈련 {fmt(d_tr)} → 검증 {fmt(d_te)}\n"
                      f"- 훈련 최적값 ({label(best)}): 훈련 {fmt(b_tr)} → 검증 {fmt(b_te)}\n"
                      f"- 훈련 상위 3개: " + " · ".join(f"{label(p)}({s:.2f})" for s, p in results[:3]) + "\n")
        print(name, best)
    now = dt.datetime.now(ZoneInfo("Asia/Seoul"))
    body = f"""# 🔧 규칙 최적화 결과 (계산일 {now:%Y-%m-%d})

**방법**: S&P500 ETF 하나로, 각 규칙의 파라미터를 격자 탐색(모든 조합 시험).
- 훈련 기간 {TRAIN[0]} ~ {TRAIN[1]} 에서 가장 점수가 높은 값을 고르고,
- 그 값을 **처음 보는** 검증 기간 {TEST[0]} ~ {krx.index[-1].date()} 에 그대로 적용.
- **점수 = 연평균 수익률 ÷ |최대 하락폭|** (위험 대비 수익, 칼마 비율). 높을수록 좋음.

**기준선 A 적립식**: 훈련 {fmt(base_tr)} → 검증 {fmt(base_te)}

| 규칙 | 훈련 최적 파라미터 | 훈련 점수 | 검증 점수 | 기본값 검증 점수 | 판정 |
|---|---|---:|---:|---:|---|
""" + "\n".join(rows) + f"""

**읽는 법**
- 훈련 점수가 높아도 검증 점수가 떨어지면, 과거에 '우연히' 잘 맞은 값(과적합)일 가능성이 큼.
- 검증에서도 적립식(A)보다 점수가 높으면 그나마 믿을 만한 규칙. 그래도 한 번의 검증일 뿐이라 확신은 금물.

## 상세
""" + "\n".join(detail) + "\n*공부용 가상 계산. 과거 성과는 미래를 보장하지 않습니다.*\n"
    os.makedirs("paper", exist_ok=True)
    open("paper/optimize.md", "w", encoding="utf-8").write(body)
    print("[optimize] saved paper/optimize.md")


if __name__ == "__main__":
    main()
