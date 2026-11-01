"""거시 지표 스냅샷: 지수·환율·미국 금리·VIX 종가를 reports/macro_YYYYMMDD.md 로 저장.

데이터: Yahoo Finance (yfinance, 키 불필요). 실패한 지표는 '데이터 없음'으로 남기고 계속 진행.
"""
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

import yfinance as yf

INDICATORS = [
    ("코스피", "^KS11", "지수", "한국 대표 지수"),
    ("S&P500", "^GSPC", "지수", "미국 대표 500개 기업"),
    ("나스닥", "^IXIC", "지수", "미국 기술주 중심"),
    ("원·달러 환율", "KRW=X", "원", "오르면 원화 약세, 미국 ETF 원화 수익률에 유리"),
    ("미국 10년물 금리", "^TNX", "%", "오르면 주식(특히 성장주)에 부담"),
    ("VIX(공포지수)", "^VIX", "", "15 미만 안정 · 30 이상 공포"),
]


def last_two(ticker):
    hist = yf.Ticker(ticker).history(period="10d", auto_adjust=False)
    closes = hist["Close"].dropna()
    if len(closes) < 2:
        return None
    return closes.index[-1].date(), float(closes.iloc[-1]), float(closes.iloc[-2])


def main():
    today = dt.datetime.now(ZoneInfo("Asia/Seoul"))
    rows = []
    for name, ticker, unit, note in INDICATORS:
        try:
            r = last_two(ticker)
        except Exception as e:  # 한 지표 실패가 전체를 멈추지 않게
            print(f"[macro] {ticker} 실패: {e}", file=sys.stderr)
            r = None
        if r is None:
            rows.append(f"| {name} | 데이터 없음 | - | - | {note} |")
            continue
        day, last, prev = r
        chg = (last - prev) / prev * 100 if prev else 0.0
        arrow = "🔴" if chg < 0 else "🟢"
        rows.append(f"| {name} | {last:,.2f} {unit} | {arrow} {chg:+.2f}% | {day} | {note} |")

    os.makedirs("reports", exist_ok=True)
    path = f"reports/macro_{today:%Y%m%d}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 🌐 거시 지표 ({today:%Y-%m-%d})\n\n")
        f.write("| 지표 | 종가 | 전일 대비 | 기준일 | 읽는 법 |\n|---|---|---|---|---|\n")
        f.write("\n".join(rows) + "\n\n")
        f.write("*출처: Yahoo Finance. 기준일은 각 시장의 마지막 거래일입니다.*\n")
    print(f"[macro] saved {path}")


if __name__ == "__main__":
    main()
