"""history/<날짜>/ 의 보고서를 노션 페이지 아래에 하위 페이지로 올린다.

필요: NOTION_TOKEN, NOTION_PAGE_ID (없으면 아무것도 하지 않고 종료).
같은 날짜 페이지가 이미 있으면 보관(archive) 후 새로 만든다(재실행 시 중복 방지).
"""
import datetime as dt
import glob
import os
import re
import sys
from zoneinfo import ZoneInfo

import requests

API = "https://api.notion.com/v1"
TOKEN = os.environ.get("NOTION_TOKEN", "").strip()
PARENT = re.sub(r"[^0-9a-fA-F]", "", os.environ.get("NOTION_PAGE_ID", ""))[-32:]
HEAD = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
ORDER = ["macro", "market_review", "report"]


def rt(text):
    text = text.replace("**", "")
    return [{"type": "text", "text": {"content": text[i:i + 1900]}} for i in range(0, max(len(text), 1), 1900)]


def to_blocks(md):
    blocks, table = [], []

    def flush():
        if table:
            blocks.append({"type": "code", "code": {"language": "markdown", "rich_text": rt("\n".join(table))}})
            table.clear()

    for line in md.splitlines():
        s = line.strip()
        if s.startswith("|"):
            table.append(s)
            continue
        flush()
        if not s or s == "---":
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m:
            t = f"heading_{len(m.group(1))}"
            blocks.append({"type": t, t: {"rich_text": rt(m.group(2))}})
        elif re.match(r"^[-*]\s+", s):
            blocks.append({"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rt(s[2:])}})
        else:
            blocks.append({"type": "paragraph", "paragraph": {"rich_text": rt(s.lstrip("> "))}})
    flush()
    return blocks


def call(method, path, **kw):
    r = requests.request(method, API + path, headers=HEAD, timeout=30, **kw)
    if r.status_code >= 300:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
    return r.json()


def main():
    if not TOKEN or len(PARENT) != 32:
        print("[notion] NOTION_TOKEN / NOTION_PAGE_ID 미설정 — 건너뜀")
        return
    day = dt.datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    files = glob.glob(f"history/{day}/*.md")
    if not files:
        print(f"[notion] history/{day} 보고서 없음 — 건너뜀")
        return
    files.sort(key=lambda p: next((i for i, k in enumerate(ORDER) if os.path.basename(p).startswith(k)), 9))
    title = f"{day} 주식 보고서"

    # 같은 제목의 기존 하위 페이지 보관
    cursor = None
    while True:
        q = f"/blocks/{PARENT}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
        res = call("GET", q)
        for b in res["results"]:
            if b["type"] == "child_page" and b["child_page"]["title"] == title:
                call("PATCH", f"/pages/{b['id']}", json={"archived": True})
        if not res.get("has_more"):
            break
        cursor = res["next_cursor"]

    blocks = []
    for f in files:
        blocks += to_blocks(open(f, encoding="utf-8").read())
        blocks.append({"type": "divider", "divider": {}})
    page = call("POST", "/pages", json={
        "parent": {"page_id": PARENT},
        "properties": {"title": {"title": rt(title)}},
        "children": blocks[:100],
    })
    for i in range(100, len(blocks), 100):
        call("PATCH", f"/blocks/{page['id']}/children", json={"children": blocks[i:i + 100]})
    print(f"[notion] 페이지 생성: {title} ({len(blocks)} blocks)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[notion] 실패: {e}", file=sys.stderr)
        sys.exit(1)
