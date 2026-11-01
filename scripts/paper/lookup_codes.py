"""종목명으로 네이버 자동완성을 조회해 6자리 코드를 찾고 paper/codes_lookup.json 에 저장 (1회성 확인용)."""
import json
import os

import requests
import yfinance as yf

NAMES = [
    "TIGER 미국S&P500", "삼성전자", "KODEX AI반도체TOP2플러스", "RISE 미국나스닥100",
    "ACE 구글밸류체인액티브", "ACE 미국배당다우존스", "KODEX 2차전지산업", "TIGER KRX금현물",
    "KODEX 미국우주항공", "KODEX 200", "ACE 미국10년국채액티브", "TIGER 미국채10년선물",
    "KODEX 미국10년국채선물", "ACE KRX금현물",
]

out = {}
for n in NAMES:
    try:
        r = requests.get("https://ac.stock.naver.com/ac", params={"q": n, "target": "stock,index,etf"},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        items = r.json().get("items", [])
        cands = [{"code": i.get("code"), "name": i.get("name"), "type": i.get("typeName")} for i in items[:5]]
    except Exception as e:
        cands = [{"error": str(e)}]
    # 첫 후보가 야후에서 시세가 나오는지 확인
    for c in cands:
        code = c.get("code")
        if code and len(code) == 6:
            try:
                h = yf.Ticker(f"{code}.KS").history(period="5d")
                c["yahoo_KS_rows"] = len(h)
                c["first_date_5y"] = str(yf.Ticker(f"{code}.KS").history(period="max").index.min().date()) if len(h) else None
            except Exception as e:
                c["yahoo_err"] = str(e)[:80]
            break
    out[n] = cands
    print(n, "->", cands[:2])

os.makedirs("paper", exist_ok=True)
json.dump(out, open("paper/codes_lookup.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
