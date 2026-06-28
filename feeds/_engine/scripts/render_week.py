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


def _stock_table(stocks: list, region_label: str) -> list:
    """生成一个股票表（含地区小标题）。"""
    rows = [f'      <div class="stock-region">{esc(region_label)}</div>',
            '      <table class="stocks"><thead><tr><th>公司</th><th>最新价</th><th>周涨跌</th><th>关键事件</th></tr></thead><tbody>']
    for s in stocks:
        pct = s.get("pct")
        cls = "up" if (isinstance(pct, (int, float)) and pct >= 0) else "down"
        pct_str = (f'+{pct}%' if isinstance(pct, (int, float)) and pct >= 0
                   else (f'{pct}%' if isinstance(pct, (int, float)) else '—'))
        price = s.get("price")
        price_str = f'{price} {esc(s.get("currency",""))}'.strip() if price is not None else '—'
        code = s.get("sym") or s.get("secid", "")
        mkt = f' · {esc(s.get("market"))}' if s.get("market") else ''
        rows.append(
            f'        <tr><td>{esc(s.get("name",""))} <span class="tk">{esc(code)}{mkt}</span></td>'
            f'<td>{esc(price_str)}</td><td class="{cls}">{esc(pct_str)}</td>'
            f'<td>{esc(s.get("note",""))}</td></tr>'
        )
    rows.append('      </tbody></table>')
    return rows


def render_industry(ind: dict) -> str:
    """产业动态板块：上市公司风向（默认折叠，海外+国内分区）+ 融资/独角兽（列表）。"""
    if not ind:
        return ""
    stocks = ind.get("stocks") or []          # 海外（Yahoo）
    cn_stocks = ind.get("cn_stocks") or []    # 国内（东财）
    funding = ind.get("funding") or []
    if not stocks and not cn_stocks and not funding:
        return ""
    parts = ['  <section class="domain industry" id="industry">', '    <h2>📈 产业动态</h2>']
    # 上市公司风向 —— 默认折叠，点击展开
    if stocks or cn_stocks:
        n = len(stocks) + len(cn_stocks)
        parts.append('    <details class="stocks-fold">')
        parts.append(f'      <summary>上市公司风向（{n} 只，点击展开 · 截至最近收盘）</summary>')
        if stocks:
            parts += _stock_table(stocks, "🌍 海外")
        if cn_stocks:
            parts += _stock_table(cn_stocks, "🇨🇳 国内（A股/港股）")
        parts.append('    </details>')
    # 融资 / 独角兽（默认展开）
    if funding:
        parts.append('    <h3 class="sub-h">融资与独角兽</h3>')
        parts.append('    <ul class="items">')
        for f in funding:
            amt = f.get("amount")
            amt_badge = f'<span class="badge amt">{esc(amt)}</span>' if amt else ''
            reg = f'<span class="badge region">{esc(f.get("region"))}</span>' if f.get("region") else ''
            url = esc(f.get("url", "#"))
            parts.append(
                '      <li>'
                f'<div class="it-title">{amt_badge}{reg}<a href="{url}" target="_blank" rel="noopener">{esc(f.get("title",""))}</a></div>'
                f'<div class="it-sum">{esc(f.get("summary",""))}</div></li>'
            )
        parts.append('    </ul>')
    parts.append('  </section>')
    return "\n".join(parts)


def render(channel: str, week: str) -> str:
    data_path = FEEDS_DIR / channel / "data" / f"{week}.json"
    doc = json.loads(data_path.read_text(encoding="utf-8"))
    cur = doc.get("curated") or {}
    zh, en = CHANNEL_TITLES.get(channel, (channel, channel))
    title_date = cur.get("title_date", week)
    window = cur.get("window", "")
    domains_html = "\n".join(render_domain(d) for d in cur.get("domains", []))
    industry_html = render_industry(cur.get("industry") or {})
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
    <span>信息源：<b>HN / arXiv / 产业媒体 / 公司官方 / 融资 / 行情</b></span>
    <span>周编号：<b>{esc(week)}</b></span>
  </div>
{domains_html}
{industry_html}
{hl_html}
  <div class="wk-nav">
    <span><a href="../index.html">← 返回全部周报</a></span>
    <span><a href="../../index.html">资讯首页 →</a></span>
  </div>
  <footer class="site">由 blueyi.github.io/feeds 自动生成 · 数据源 HN/arXiv/产业媒体/公司官方/融资/Yahoo Finance 行情 · 站点 master 直发 GitHub Pages</footer>
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
