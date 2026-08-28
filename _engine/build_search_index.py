#!/usr/bin/env python3
"""build_search_index.py — 聚合 daily/ + feeds/ 历史条目,生成根目录 search-index.json。

供 search/index.html 前端搜索（纯静态站,无后端）。由 rebuild_daily.py 与
rebuild_index.py 在各自重建末尾调用,保持索引与站点内容同步。

数据来源:
- daily/data/*.md —— 解析每篇日报的 8 分类条目（复用 render_daily.parse）
- feeds/{ai-infra,embodied-ai}/data/*.json —— curated.domains[].items[] + curated.industry.funding[]

输出: search-index.json = {"generated_at": ..., "entries": [{type, channel, date, week, category, title, summary, url, page}]}
仅用 Python 标准库。
"""
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAILY_DATA = ROOT / "daily" / "data"
FEEDS_DIR = ROOT / "feeds"
OUT_PATH = ROOT / "search-index.json"

# 复用 daily 的 markdown 解析（单一日报事实源，避免重复实现）
sys.path.insert(0, str(ROOT / "daily" / "_engine"))
import render_daily  # noqa: E402

CHANNELS = ["ai-infra", "embodied-ai"]


def daily_entries():
    out = []
    if not DAILY_DATA.exists():
        return out
    for p in sorted(DAILY_DATA.glob("*.md")):
        date = p.stem
        doc = render_daily.parse(p.read_text(encoding="utf-8"))
        for d in doc["domains"]:
            cat = f'{d["emoji"]} {d["name"]}'.strip()
            for it in d["items"]:
                out.append({
                    "type": "daily",
                    "channel": "ai-infra-daily",
                    "date": date,
                    "week": "",
                    "category": cat,
                    "title": it["title"],
                    "summary": it["summary"],
                    "url": it.get("url", ""),
                    "page": f"/daily/{date}.html",
                })
    return out


def weekly_entries():
    out = []
    for ch in CHANNELS:
        data_dir = FEEDS_DIR / ch / "data"
        if not data_dir.exists():
            continue
        for p in sorted(data_dir.glob("*.json")):
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            week = doc.get("week", p.stem)
            cur = doc.get("curated") or {}
            page = f"/feeds/{ch}/weeks/{week}.html"
            for d in cur.get("domains", []):
                cat = f'{d.get("emoji", "")} {d.get("name", "")}'.strip()
                for it in d.get("items", []):
                    out.append({
                        "type": "weekly",
                        "channel": ch,
                        "date": "",
                        "week": week,
                        "category": cat,
                        "title": it.get("title", ""),
                        "summary": it.get("summary", ""),
                        "url": it.get("url", ""),
                        "page": page,
                    })
            for f in (cur.get("industry") or {}).get("funding", []):
                out.append({
                    "type": "weekly",
                    "channel": ch,
                    "date": "",
                    "week": week,
                    "category": "📈 产业动态 · 融资",
                    "title": f.get("title", ""),
                    "summary": f.get("summary", ""),
                    "url": f.get("url", ""),
                    "page": page,
                })
    return out


def main():
    entries = daily_entries() + weekly_entries()
    payload = {
        "generated_at": datetime.datetime.now().astimezone().isoformat(),
        "entries": entries,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    n_daily = sum(1 for e in entries if e["type"] == "daily")
    n_weekly = sum(1 for e in entries if e["type"] == "weekly")
    print(f"[search] wrote {OUT_PATH} ({len(entries)} entries: daily {n_daily}, weekly {n_weekly})")


if __name__ == "__main__":
    main()
