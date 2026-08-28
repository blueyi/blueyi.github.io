#!/usr/bin/env python3
"""render_daily.py — 把 data/<date>.md 的日报 markdown 渲染成 <date>.html。

日报 markdown 契约（来自 ai-infra-daily-news cron 的投递快照，剥离头尾后）:
# 📡 AI Infra 日报 · 2026-08-28（周五）
> 覆盖窗口：2026-08-27 ~ 2026-08-28 · 信息源：...
## 1️⃣ AI 芯片
- 🔥 **标题**：摘要。[来源](url)
...
## 🌟 今日亮点
1. **标题**：摘要

用法: python3 render_daily.py --date 2026-08-28
仅用 Python 标准库。
"""
import argparse
import datetime
import html
import re
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
DAILY_DIR = ENGINE_DIR.parent
DATA_DIR = DAILY_DIR / "data"

# 站点外壳统一英文（正文内容仍中文）——与 feeds 站约定一致
TITLE = "AI Infra Daily"
DESC = "AI Infra daily news digest — chips / compilers / inference / datacenters / safety / embodied / autokernels / edge"
SOURCES_LABEL = "HN / arXiv / tech blogs / Chinese media / embodied RSS"
SCHEDULE = "Updated every day 08:30 HKT"

# feather 风格描边 home SVG，与主页/feeds 站图标一致
HOME_SVG = ('<svg class="home-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M3 9.5L12 3l9 6.5"/><path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/></svg>')

_WEEKDAYS_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)\s*$')
_BOLD_RE = re.compile(r'\*\*(.+?)\*\*')


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def weekday_zh(date_str: str) -> str:
    try:
        y, m, d = (int(x) for x in date_str.split("-"))
        return _WEEKDAYS_ZH[datetime.date(y, m, d).weekday()]
    except Exception:
        return ""


def _parse_item(raw: str) -> dict:
    """解析一条 '- ' bullet -> {title, summary, url, source, hot}"""
    s = raw.strip()
    hot = False
    if s.startswith("🔥"):
        hot = True
        s = s[1:].lstrip()
    source, url = "", ""
    m = _LINK_RE.search(s)
    if m:
        source = m.group(1).strip()
        url = m.group(2).strip()
        s = s[:m.start()].rstrip()
    title, summary = "", ""
    bm = _BOLD_RE.search(s)
    if bm:
        title = bm.group(1).strip()
        summary = s[bm.end():].strip()
    else:
        title = s.strip()
    summary = re.sub(r'^[：:。，,、\s]+', '', summary).strip()
    return {"title": title, "summary": summary, "url": url, "source": source, "hot": hot}


def _parse_highlight(raw: str) -> dict:
    s = re.sub(r'^\d+[\.、)]\s*', '', raw.strip())
    return _parse_item(s)


def parse(md: str) -> dict:
    """解析日报 markdown -> {title, window, domains:[{emoji,name,items}], highlights:[...]}"""
    title = ""
    window = ""
    domains = []
    highlights = []
    cur = None
    in_highlights = False
    for line in md.splitlines():
        ls = line.strip()
        if not ls:
            continue
        if ls.startswith("# ") and not title:
            title = ls[2:].strip()
            continue
        if ls.startswith("> "):
            m = re.search(r'覆盖窗口[：:]\s*([^·]+)', ls[2:])
            if m:
                window = m.group(1).strip()
            continue
        if ls.startswith("## "):
            name = ls[3:].strip()
            if "亮点" in name:
                in_highlights = True
                cur = None
            else:
                in_highlights = False
                m = re.match(r'^(\S+)\s*(.*)$', name)
                emoji = m.group(1) if m else ""
                rest = m.group(2).strip() if m else name
                cur = {"emoji": emoji, "name": rest, "items": []}
                domains.append(cur)
            continue
        if in_highlights:
            if re.match(r'^\d+[\.、)]', ls):
                highlights.append(_parse_highlight(ls))
            elif ls.startswith("- "):
                highlights.append(_parse_item(ls[2:]))
            continue
        if cur is not None and ls.startswith("- "):
            cur["items"].append(_parse_item(ls[2:]))
    return {"title": title, "window": window, "domains": domains, "highlights": highlights}


def first_highlight(md: str) -> str:
    """manifest 用的单句亮点：优先今日亮点第一条，否则首分类首条。"""
    doc = parse(md)
    hs = doc["highlights"]
    if hs:
        h = hs[0]
        return (h["title"] + ("：" + h["summary"] if h["summary"] else "")).strip()
    for d in doc["domains"]:
        if d["items"]:
            it = d["items"][0]
            return (it["title"] + ("：" + it["summary"] if it["summary"] else "")).strip()
    return ""


def render_item(it: dict) -> str:
    src = it.get("source", "")
    badge = f'<span class="badge score">{esc(src)}</span>' if src else ""
    hot = ' <span class="hot">🔥</span>' if it.get("hot") else ""
    url = esc(it.get("url", "#"))
    title = esc(it.get("title", "(无标题)"))
    summary = esc(it.get("summary", ""))
    sum_html = f'      <div class="it-sum">{summary}</div>\n' if summary else ""
    return (
        '    <li>\n'
        f'      <div class="it-title">{badge}<a href="{url}" target="_blank" rel="noopener">{title}</a>{hot}</div>\n'
        f'{sum_html}'
        '    </li>'
    )


def _neighbors(date: str):
    files = sorted(p.stem for p in DATA_DIR.glob("*.md"))
    if date not in files:
        return None, None
    i = files.index(date)
    return (files[i - 1] if i > 0 else None), (files[i + 1] if i < len(files) - 1 else None)


def render(date: str) -> str:
    md = (DATA_DIR / f"{date}.md").read_text(encoding="utf-8")
    doc = parse(md)
    window = doc["window"]
    wd = weekday_zh(date)
    title_date = f"{date} · {wd}" if wd else date

    domains_html = []
    for d in doc["domains"]:
        items = d["items"]
        if items:
            body = "    <ul class=\"items\">\n" + "\n".join(render_item(i) for i in items) + "\n    </ul>"
        else:
            body = '    <div class="empty">今日该方向公开源未见重大动态。</div>'
        domains_html.append(
            f'  <section class="domain">\n'
            f'    <h2>{esc(d["emoji"])} {esc(d["name"])}</h2>\n'
            f'{body}\n'
            f'  </section>'
        )
    domains_html = "\n".join(domains_html)

    hl_html = ""
    if doc["highlights"]:
        lis = "\n".join(
            f'      <li><b>{esc(h["title"])}</b>{"：" + esc(h["summary"]) if h["summary"] else ""}</li>'
            for h in doc["highlights"]
        )
        hl_html = (
            '  <div class="highlights">\n'
            '    <h2>🌟 今日亮点</h2>\n'
            f'    <ol>\n{lis}\n    </ol>\n'
            '  </div>'
        )

    prev, nxt = _neighbors(date)
    left = f'<span><a href="{prev}.html">← {prev}</a></span>' if prev else \
           '<span><a href="index.html">← All days</a></span>'
    right = f'<span><a href="{nxt}.html">{nxt} →</a></span>' if nxt else \
            '<span><a href="/">Home →</a></span>'

    window_span = f'    <span>Window: <b>{esc(window)}</b></span>\n' if window else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(TITLE)} · {esc(date)}</title>
<link rel="stylesheet" href="assets/daily.css">
</head>
<body>
<div class="wrap">
  <div class="crumb"><a href="/">{HOME_SVG}Home</a> / <a href="index.html">Daily</a> / {esc(date)}</div>
  <header class="site">
    <h1>{esc(TITLE)} · {esc(title_date)}</h1>
    <div class="sub">{esc(DESC)}</div>
  </header>
  <div class="meta-bar">
{window_span}    <span>Sources: <b>{esc(SOURCES_LABEL)}</b></span>
    <span>Date: <b>{esc(date)}</b></span>
  </div>
{hl_html}
{domains_html}
  <div class="wk-nav">
    {left}
    {right}
  </div>
  <footer class="site">Auto-generated · AI Infra daily digest · GitHub Pages</footer>
</div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()
    out = render(args.date)
    out_path = DAILY_DIR / f"{args.date}.html"
    out_path.write_text(out, encoding="utf-8")
    print(f"wrote {out_path} ({len(out)} bytes)")


if __name__ == "__main__":
    main()
