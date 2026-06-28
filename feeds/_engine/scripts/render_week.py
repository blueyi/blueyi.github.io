#!/usr/bin/env python3
"""
render_week.py — 把 data/<week>.json 的 curated 段渲染成 weeks/<week>.html。

curated 数据契约（由 agent 编辑后写入 data/<week>.json["curated"]）:
{
  "title_date": "2026-W27 (06-27 ~ 07-03)",
  "window": "2026-06-27 ~ 2026-07-03",
  "domains": [
    {"id":"chips","emoji":"1️⃣","name":"AI 芯片",
     "items":[
        {"title":"...","summary":"...","url":"https://...",
         "source":"hn"|"arxiv","score":312,"hot":true}
     ]}        # items 为空 -> 渲染占位语
  ],
  "highlights": ["...","...","..."]
}

用法: python3 render_week.py --channel ai-infra --week 2026-W27
仅用 Python 标准库。
"""
import argparse
import html
import json
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent
FEEDS_DIR = ENGINE_DIR.parent

CHANNEL_TITLES = {
    "ai-infra": ("AI Infra 每周资讯", "AI Infra Weekly"),
    "embodied-ai": ("具身智能每周资讯", "Embodied AI Weekly"),
}


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def render_item(it: dict) -> str:
    src = it.get("source", "")
    badge = ""
    if src == "hn":
        sc = it.get("score")
        badge = '<span class="badge hn">HN</span>'
        if sc:
            badge += f'<span class="badge score">{esc(sc)}★</span>'
    elif src == "arxiv":
        badge = '<span class="badge arxiv">arXiv</span>'
    hot = ' <span class="hot">🔥</span>' if it.get("hot") else ""
    url = esc(it.get("url", "#"))
    title = esc(it.get("title", "(无标题)"))
    summary = esc(it.get("summary", ""))
    return (
        '    <li>\n'
        f'      <div class="it-title">{badge}<a href="{url}" target="_blank" rel="noopener">{title}</a>{hot}</div>\n'
        f'      <div class="it-sum">{summary}</div>\n'
        '    </li>'
    )


def render_domain(d: dict) -> str:
    head = (
        f'  <section class="domain" id="{esc(d.get("id"))}">\n'
        f'    <h2>{esc(d.get("emoji",""))} {esc(d.get("name",""))}</h2>\n'
    )
    items = d.get("items") or []
    if not items:
        body = '    <div class="empty">本周该方向公开源未见重大动态。</div>\n'
    else:
        body = '    <ul class="items">\n' + "\n".join(render_item(i) for i in items) + "\n    </ul>\n"
    return head + body + "  </section>"


def render(channel: str, week: str) -> str:
    data_path = FEEDS_DIR / channel / "data" / f"{week}.json"
    doc = json.loads(data_path.read_text(encoding="utf-8"))
    cur = doc.get("curated") or {}
    zh, en = CHANNEL_TITLES.get(channel, (channel, channel))
    title_date = cur.get("title_date", week)
    window = cur.get("window", "")
    domains_html = "\n".join(render_domain(d) for d in cur.get("domains", []))
    hl = cur.get("highlights") or []
    hl_html = ""
    if hl:
        lis = "\n".join(f"      <li>{esc(h)}</li>" for h in hl)
        hl_html = (
            '  <div class="highlights">\n'
            '    <h2>🌟 本周亮点</h2>\n'
            f'    <ol>\n{lis}\n    </ol>\n'
            '  </div>'
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(zh)} · {esc(title_date)}</title>
<link rel="stylesheet" href="../../assets/feeds.css">
</head>
<body>
<div class="wrap">
  <div class="crumb"><a href="../../index.html">资讯</a> / <a href="../index.html">{esc(zh)}</a> / {esc(week)}</div>
  <header class="site">
    <h1>{esc(zh)} · {esc(title_date)}</h1>
    <div class="sub">{esc(en)} weekly digest</div>
  </header>
  <div class="meta-bar">
    <span>覆盖窗口：<b>{esc(window)}</b></span>
    <span>信息源：<b>Hacker News / arXiv</b></span>
    <span>周编号：<b>{esc(week)}</b></span>
  </div>
{domains_html}
{hl_html}
  <div class="wk-nav">
    <span><a href="../index.html">← 返回全部周报</a></span>
    <span><a href="../../index.html">资讯首页 →</a></span>
  </div>
  <footer class="site">由 blueyi.github.io/feeds 自动生成 · 数据源 HN + arXiv · 站点 master 直发 GitHub Pages</footer>
</div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True, choices=["ai-infra", "embodied-ai"])
    ap.add_argument("--week", required=True)
    args = ap.parse_args()
    out_html = render(args.channel, args.week)
    out_path = FEEDS_DIR / args.channel / "weeks" / f"{args.week}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_html, encoding="utf-8")
    print(f"wrote {out_path} ({len(out_html)} bytes)")


if __name__ == "__main__":
    main()
