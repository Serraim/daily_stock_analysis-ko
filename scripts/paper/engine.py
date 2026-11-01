"""가상투자(모의투자) 엔진 — 공부용. 실제 계좌와 연결되지 않는다.

사용법
  python scripts/paper/engine.py forward    # 2026-11-02부터 오늘까지 → reports/paper_YYYYMMDD.md
  python scripts/paper/engine.py backtest   # 과거 시험 → paper/backtest.md

매번 가격 데이터로 처음부터 다시 계산하므로 상태 파일이 필요 없다(AI 신호는 history/ 보고서에서 읽음).
가정: 종가 체결, 정수 주 매매, 수수료 0.015%, 배당은 수정주가(auto_adjust)로 재투자 효과 반영.
"""
import datetime as dt
import glob
import math
import os
import re
import sys
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FEE = 0.00015
INITIAL = 1_000_000
MONTHLY = 100_000
FEAR_EXTRA = 50_000
FORWARD_START = "2026-11-02"

SPX = "360750.KS"      # TIGER 미국S&P500
GOLD = "411060.KS"     # ACE KRX금현물 (2021-12 상장, 과거 시험용으로 이력이 긴 금 ETF)
BOND = "305080.KS"     # TIGER 미국채10년선물
VIX = "^VIX"

# 2026-10-30 ISA 평가금액 기준 실제 보유 비중 (QBTS는 달러 자산이라 제외)
MY = {
    "360750.KS": ("TIGER 미국S&P500", 1_189_570),
    "005930.KS": ("삼성전자", 880_000),
    "395160.KS": ("KODEX AI반도체TOP2플러스", 500_700),
    "368590.KS": ("RISE 미국나스닥100", 398_090),
    "483340.KS": ("ACE 구글밸류체인액티브", 295_040),
    "402970.KS": ("ACE 미국배당다우존스", 169_950),
    "305720.KS": ("KODEX 2차전지산업", 107_440),
    "0072R0.KS": ("TIGER KRX금현물", 102_600),
    "0167Z0.KS": ("KODEX 미국우주항공", 24_260),
}
_tot = sum(v for _, v in MY.values())
MY_W = {t: v / _tot for t, (_, v) in MY.items()}
NAMES = {t: n for t, (n, _) in MY.items()} | {GOLD: "ACE KRX금현물", BOND: "TIGER 미국채10년선물"}


# ---------------------------------------------------------------- 데이터
def load_prices(tickers, start, end=None):
    lookback = (pd.Timestamp(start) - pd.Timedelta(days=420)).strftime("%Y-%m-%d")
    df = yf.download(sorted(set(tickers)), start=lookback, end=end, auto_adjust=True,
                     progress=False, group_by="column")["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(tickers[0])
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df


def load_ai_signals():
    """history/<날짜>/report_*.md 의 요약 줄에서 (날짜, 종목코드) → 매수/관망/매도."""
    pat = re.compile(r"\(([0-9A-Z]{6}\.K[SQ]|[A-Z]{1,5})\)\*\*:\s*(매수|보유|관망|매도)")
    out = {}
    for f in sorted(glob.glob("history/*/report_*.md")):
        day = pd.Timestamp(os.path.basename(os.path.dirname(f)))
        for t, s in pat.findall(open(f, encoding="utf-8").read()):
            out.setdefault(day, {})[t] = s
    return out


# ---------------------------------------------------------------- 포트폴리오
class Port:
    def __init__(self):
        self.cash = 0.0
        self.sh = {}
        self.cost = {}   # 종목별 평균 매수가
        self.units = 0.0
        self.invested = 0.0
        self.trades = 0
        self.rows = []

    def value(self, px):
        return self.cash + sum(n * px[t] for t, n in self.sh.items() if n and not math.isnan(px[t]))

    def contribute(self, amt, px):
        v = self.value(px)
        nav = v / self.units if self.units else 1000.0
        self.units += amt / nav
        self.invested += amt
        self.cash += amt

    def buy(self, t, amt, px):
        p = px[t]
        if math.isnan(p) or p <= 0:
            return
        n = math.floor(min(amt, self.cash) / (p * (1 + FEE)))
        if n > 0:
            self.cash -= n * p * (1 + FEE)
            old = self.sh.get(t, 0)
            self.cost[t] = (self.cost.get(t, 0) * old + p * n) / (old + n)
            self.sh[t] = old + n
            self.trades += 1

    def sell(self, t, px, n=None):
        have = self.sh.get(t, 0)
        n = have if n is None else min(n, have)
        if n > 0 and not math.isnan(px[t]):
            self.cash += n * px[t] * (1 - FEE)
            self.sh[t] = have - n
            self.trades += 1

    def record(self, day, px):
        v = self.value(px)
        self.rows.append((day, v, self.invested, v / self.units if self.units else 1000.0))


def contribution_days(idx, start):
    days = idx[idx >= pd.Timestamp(start)]
    firsts = days.to_series().groupby([days.year, days.month]).min()
    return set(firsts.values) | {days[0]}


def rebalance_to(p, weights, px, threshold=None, budget=None):
    """목표 비중으로 맞추기. budget: 이번에 쓸 최대 현금(없으면 보유 현금 전부).
    threshold 를 주면 비중이 그만큼 틀어졌을 때 초과분을 먼저 판다.
    정수 주라서 비싼 종목은 못 살 수 있으므로, 가장 모자란 종목부터 1주씩 채운다."""
    live = {t: w for t, w in weights.items() if not math.isnan(px[t])}
    s_ = sum(live.values()) or 1
    live = {t: w / s_ for t, w in live.items()}
    total = p.value(px)
    if total <= 0:
        return 0.0
    if threshold is not None:
        cur = {t: p.sh.get(t, 0) * px[t] / total for t in live}
        if max(abs(cur[t] - w) for t, w in live.items()) > threshold:
            for t, w in live.items():
                excess = p.sh.get(t, 0) * px[t] - w * total
                if excess > px[t]:
                    p.sell(t, px, int(excess // px[t]))
    start_cash = p.cash
    cap = p.cash if budget is None else min(budget, p.cash)
    floor = start_cash - cap
    while True:
        total = p.value(px)
        gaps = {t: w * total - p.sh.get(t, 0) * px[t] for t, w in live.items()}
        cands = [t for t in sorted(gaps, key=lambda t: -gaps[t] / (live[t] * total))
                 if gaps[t] > 0 and p.cash - px[t] * (1 + FEE) >= floor]
        if not cands:
            break
        t = cands[0]
        n = max(1, int(min(gaps[t], p.cash - floor) // (px[t] * (1 + FEE))))
        before = p.cash
        p.buy(t, n * px[t] * (1 + FEE) + 1e-6, px)
        if p.cash == before:
            break
    return start_cash - p.cash


# ---------------------------------------------------------------- 전략
def simulate(name, prices, start, step, extra=None):
    idx = prices.index[prices.index >= pd.Timestamp(start)]
    cdays = contribution_days(prices.index, start)
    p = Port()
    st = {"reserve": 0.0}
    for i, day in enumerate(idx):
        px = prices.loc[day]
        if day in cdays:
            p.contribute(INITIAL if i == 0 else MONTHLY, px)
        if extra:
            extra(p, day, px, st)
        step(p, day, px, st, i == 0, day in cdays)
        p.record(day, px)
    return name, p


def _buy_w(p, weights, amt, px):
    live = {t: w for t, w in weights.items() if not math.isnan(px[t])}
    tot = sum(live.values()) or 1
    for t, w in live.items():
        p.buy(t, amt * w / tot, px)


def make_dca(weights):
    def step(p, day, px, st, first, cday):
        if first:
            st["reserve"] = INITIAL
            st["carry"] = 0.0
        if cday:
            spend = st["carry"] + (0 if first else MONTHLY) + min(st["reserve"], INITIAL / 10)
            st["reserve"] = max(st["reserve"] - INITIAL / 10, 0)
            used = rebalance_to(p, weights, px, budget=spend)
            st["carry"] = spend - used   # 못 산 돈은 다음 달로
    return step


def make_lump(weights):
    def step(p, day, px, st, first, cday):
        rebalance_to(p, weights, px)
    return step


def make_alloc(weights, threshold):
    def step(p, day, px, st, first, cday):
        if cday or first:
            rebalance_to(p, weights, px)
        if threshold is not None:
            rebalance_to(p, weights, px, threshold)
    return step


def make_trend(sma, tickers_w):
    def step(p, day, px, st, first, cday):
        on = {t: (pd.isna(sma.at[day, t]) or px[t] > sma.at[day, t]) for t in tickers_w}
        for t, ok in on.items():
            if not ok:
                p.sell(t, px)
        live = {t: w for t, w in tickers_w.items() if on[t]}
        if live and p.cash > 0 and (cday or first or any(not p.sh.get(t) for t in live)):
            rebalance_to(p, live, px)
    return step


def make_ai(signals, universe):
    def step(p, day, px, st, first, cday):
        sig = signals.get(day, {})
        for t in universe:
            if sig.get(t) == "매도":
                p.sell(t, px)
        buys = [t for t in universe if sig.get(t) == "매수" and not p.sh.get(t)]
        for t in buys:
            p.buy(t, p.cash / len(buys), px)
    return step


def make_fear(vix, weights):
    def extra(p, day, px, st):
        v = vix.get(day)
        last = st.get("last_fear")
        if v is not None and v > 30 and (last is None or (day - last).days >= 7):
            p.contribute(FEAR_EXTRA, px)
            used = rebalance_to(p, weights, px, budget=FEAR_EXTRA)
            st["carry"] = st.get("carry", 0.0) + FEAR_EXTRA - used
            st["last_fear"] = day
            st["fear_n"] = st.get("fear_n", 0) + 1
    return extra


# ---------------------------------------------------------------- 지표·출력
def metrics(p):
    df = pd.DataFrame(p.rows, columns=["day", "value", "invested", "nav"]).set_index("day")
    nav = df["nav"]
    mdd = (nav / nav.cummax() - 1).min()
    years = max((df.index[-1] - df.index[0]).days / 365.25, 1e-9)
    twr = nav.iloc[-1] / 1000 - 1
    cagr = (1 + twr) ** (1 / years) - 1 if years >= 1 else None
    last = df.iloc[-1]
    return {"value": last.value, "invested": last.invested, "profit": last.value - last.invested,
            "ret": last.value / last.invested - 1, "twr": twr, "cagr": cagr, "mdd": mdd,
            "trades": p.trades, "start": df.index[0].date(), "end": df.index[-1].date()}


def table(results):
    lines = ["| 전략 | 투입금 | 평가액 | 손익 | 투입 대비 | 기간 수익률 | 연평균 | 최대 하락폭 | 매매 횟수 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, p in results:
        m = metrics(p)
        cagr = f"{m['cagr']:+.1%}" if m["cagr"] is not None else "-"
        lines.append(f"| {name} | {m['invested']:,.0f} | {m['value']:,.0f} | {m['profit']:+,.0f} | "
                     f"{m['ret']:+.1%} | {m['twr']:+.1%} | {cagr} | {m['mdd']:.1%} | {m['trades']} |")
    return "\n".join(lines)


GUIDE = """**읽는 법**
- **투입 대비**: 넣은 돈 전체 대비 지금 얼마나 늘었나 (가장 직관적)
- **기간 수익률**: 돈을 넣은 시점과 상관없이 전략 자체의 성적 (전략끼리 공정하게 비교할 때)
- **최대 하락폭**: 가장 많이 떨어졌을 때 고점 대비 몇 %였나 (낮을수록 마음이 편한 전략)
- 공통 조건: 시작 100만 원 + 매달 첫 거래일 10만 원, 종가 체결, 정수 주, 수수료 0.015%. F는 VIX>30인 날 5만 원을 추가로 넣어 투입금이 다를 수 있다.
"""

_OLD_STRATS = """| 전략 | 규칙 |
|---|---|
| A 적립식 | 시작금 100만 원을 10개월에 나눠, 매달 추가분과 함께 S&P500 ETF 매수 |
| B 일시 투자 | 들어온 돈은 즉시 전부 S&P500 ETF 매수 |
| C 자산배분 | S&P500 60% · 금 20% · 미국채10년 20%, 비중이 5%p 넘게 틀어지면 재조정 |
| D 추세 추종 | S&P500이 200일 이동평균선 위면 보유, 아래면 전부 현금 |
| E AI 신호 | 매일 AI 보고서가 '매수'면 사고 '매도'면 팔기 (보고서에 있는 종목 대상) |
| F 공포 매수 | A와 같되, VIX가 30을 넘는 날 5만 원 추가 매수 (최소 1주 간격) |
| P1 내 비중 그대로 | 10/30 ISA 실제 비중대로 사고 그대로 보유, 추가금도 같은 비중 |
| P2 내 비중 + 재조정 | P1 비중을 목표로 5%p 넘게 틀어지면 재조정 |
| P3 내 종목 + 추세 | 내 9개 종목 각각 200일선 위에서만 보유 (이력 짧은 종목은 보유) |
"""


def six(krx, sma, vix, sig, start, base, alloc_w, tag, ctx=None):
    """같은 6가지 규칙을 한 종목 묶음(base)에 적용."""
    uni = sorted(t for t in base if t in krx.columns)
    out = [
        simulate(f"A 적립식", krx, start, make_dca(base)),
        simulate(f"B 일시 투자", krx, start, make_lump(base)),
        simulate(f"C {tag}", krx, start, make_alloc(alloc_w, .05)),
        simulate(f"D 추세 추종", krx, start, make_trend(sma, base)),
    ]
    lo, hi = pd.Timestamp(start), krx.index[-1]
    ai_uni = [t for t in uni if any(t in d for day, d in sig.items() if lo <= day <= hi)]
    if ai_uni:
        out.append(simulate(f"E AI 신호", krx, start, make_ai(sig, ai_uni)))
    out.append(simulate(f"F 공포 매수", krx, start, make_dca(base), extra=make_fear(vix, base)))
    if ctx is not None:
        import rules
        for name, (fn, params) in rules.RULES.items():
            out.append(simulate(name, krx, start, fn(ctx, base, **params)))
    return out


def run(start, end=None, with_ai=True, portfolio=True):
    tickers = [SPX, GOLD, BOND] + list(MY)
    prices = load_prices(tickers + [VIX], start, end)
    krx = prices.drop(columns=[VIX], errors="ignore")
    krx = krx[krx[SPX].notna()].ffill()
    vix = (prices[VIX].ffill().shift(1).reindex(krx.index).to_dict() if VIX in prices else {})
    sma = krx.rolling(200, min_periods=200).mean()
    sig = load_ai_signals() if with_ai else {}
    import rules
    ctx = rules.indicators(krx)
    market = six(krx, sma, vix, sig, start, {SPX: 1.0}, {SPX: .6, GOLD: .2, BOND: .2}, "자산배분", ctx)
    mine = six(krx, sma, vix, sig, start, MY_W, MY_W, "비중 재조정", ctx) if portfolio else []
    return market, mine, krx


MARKET_RULES = """| 전략 | 규칙 (시장 기준: S&P500 ETF 하나) |
|---|---|
| A 적립식 | 시작금 100만 원을 10개월에 나눠, 매달 추가분과 함께 매수 |
| B 일시 투자 | 들어온 돈은 즉시 전부 매수 |
| C 자산배분 | S&P500 60% · 금 20% · 미국채10년 20%, 비중이 5%p 넘게 틀어지면 재조정 |
| D 추세 추종 | 200일 이동평균선 위면 보유, 아래면 현금 |
| E AI 신호 | AI 보고서가 '매수'면 사고 '매도'면 팔기 |
| F 공포 매수 | A와 같되, VIX가 30을 넘는 날 5만 원 추가 매수 (최소 1주 간격) |
"""

MY_RULES = """| 전략 | 규칙 (내 종목 기준: 10/30 ISA 9개 종목, 실제 비중대로) |
|---|---|
| A 적립식 | 시작금을 10개월에 나눠, 매달 내 비중대로 나눠 매수 |
| B 일시 투자 | 들어온 돈은 즉시 내 비중대로 매수 후 그대로 보유 |
| C 비중 재조정 | 내 비중을 목표로, 5%p 넘게 틀어지면 재조정 |
| D 추세 추종 | 종목마다 200일선 위에서만 보유 (이력 짧은 종목은 보유) |
| E AI 신호 | 내 종목 중 AI 보고서에 있는 종목만, '매수'면 사고 '매도'면 팔기 |
| F 공포 매수 | A와 같되, VIX>30인 날 5만 원을 내 비중대로 추가 매수 |
"""


def compare_note(market, mine):
    """같은 규칙끼리 시장 vs 내 종목 한 줄 비교."""
    mm = {n: metrics(p) for n, p in market}
    my = {n: metrics(p) for n, p in mine}
    lines = ["| 규칙 | 시장 기준 투입 대비 | 내 종목 기준 투입 대비 | 시장 최대 하락 | 내 종목 최대 하락 |",
             "|---|---:|---:|---:|---:|"]
    for n in my:
        key = n.split()[0]
        m = next((v for k, v in mm.items() if k.split()[0] == key), None)
        if m:
            lines.append(f"| {n} | {m['ret']:+.1%} | {my[n]['ret']:+.1%} | {m['mdd']:.1%} | {my[n]['mdd']:.1%} |")
    return "\n".join(lines)


def section(title, period, market, mine):
    txt = f"## {title}\n\n{period}\n\n### ① 시장 기준 (S&P500 ETF)\n\n" + table(market) + "\n\n"
    if mine:
        txt += "### ② 내 종목 기준 (ISA 9개, 실제 비중)\n\n" + table(mine) + "\n\n"
        txt += "### ③ 같은 규칙, 어디에 쓰는 게 나았나\n\n" + compare_note(market, mine) + "\n\n"
    return txt


def main(mode):
    now = dt.datetime.now(ZoneInfo("Asia/Seoul"))
    import rules
    tail = GUIDE + "\n" + MARKET_RULES + "\n" + MY_RULES + "\n**매수·매도 규칙 모음 (시장·내 종목 둘 다에 적용)**\n\n" + rules.RULES_MD
    if mode == "forward":
        if now.date() < pd.Timestamp(FORWARD_START).date() + dt.timedelta(days=1):
            body = f"가상투자는 {FORWARD_START} 장 마감 후부터 기록이 시작됩니다.\n\n" + tail
        else:
            market, mine, krx = run(FORWARD_START)
            body = section("실전 기록", f"기간: {FORWARD_START} ~ {krx.index[-1].date()}", market, mine) + tail
        os.makedirs("reports", exist_ok=True)
        path = f"reports/paper_{now:%Y%m%d}.md"
        open(path, "w", encoding="utf-8").write(f"# 🧪 가상투자 비교 ({now:%Y-%m-%d})\n\n{body}\n")
    else:
        os.makedirs("paper", exist_ok=True)
        m1, _, k1 = run("2022-01-03", with_ai=False, portfolio=False)
        m2, y2, k2 = run("2026-03-17", with_ai=False, portfolio=True)
        body = (section("1) 시장 기준, 약 4.8년",
                        f"2022-01-03 ~ {k1.index[-1].date()}. 금 ETF(411060)가 2021-12 상장이라 2022년 초부터. 과거 AI 신호는 없어 E 제외.",
                        m1, []) +
                section("2) 시장 vs 내 종목, 약 7개월",
                        f"2026-03-17 ~ {k2.index[-1].date()}. 내 종목 중 가장 늦게 상장한 KODEX 미국우주항공 상장일부터. 짧은 기간이라 참고만.",
                        m2, y2) + tail + "\n*과거 성과는 미래를 보장하지 않습니다. 공부용 가상 계산입니다.*\n")
        path = "paper/backtest.md"
        open(path, "w", encoding="utf-8").write(f"# 📜 과거 시험 결과 (계산일 {now:%Y-%m-%d})\n\n{body}")
    print(f"[paper] saved {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "forward")
