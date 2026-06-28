#!/usr/bin/env python3
"""
rebuild_index.py — 扫描 data/*.json,重建：
  - 每个频道的 index.html（周报列表，倒序）
  - 每个频道的 manifest.json（所有周 + 领域定义 + 元信息，迁移用）
  - feeds/index.html（总入口，两频道卡片 + 各最新 3 期）

无参数运行即可重建全部（幂等）。新增周报无需手改任何索引。
仅用 Python 标准库 + pyyaml。
"""
import html
import json
from pathlib import Path

import yaml

ENGINE_DIR = Path(__file__).resolve().parent.parent
FEEDS_DIR = ENGINE_DIR.parent
CHANNELS = ["ai-infra", "embodied-ai"]


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def load_spec(channel: str) -> dict:
    return yaml.safe_load((ENGINE_DIR / "domains" / f"{channel}.yaml").read_text(encoding="utf-8"))


def list_weeks(channel: str):
    """返回该频道所有周的 (week_id, doc) 倒序列表（仅含已渲染的）。"""
    data_dir = FEEDS_DIR / channel / "data"
    weeks = []
    if not data_dir.exists():
        return weeks
    for p in sorted(data_dir.glob("*.json"), reverse=True):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        week = doc.get("week", p.stem)
        html_exists = (FEEDS_DIR / channel / "weeks" / f"{week}.html").exists()
        weeks.append((week, doc, html_exists))
    return weeks


def week_highlight(doc: dict) -> str:
    cur = doc.get("curated") or {}
    hl = cur.get("highlights") or []
    return hl[0] if hl else cur.get("window", "")


def build_channel_index(channel: str, spec: dict) -> int:
    zh = spec.get("title", channel)
    en = spec.get("title_en", channel)
    desc = spec.get("description", "")
    weeks = list_weeks(channel)
    cards = []
    for week, doc, html_exists in weeks:
        if not html_exists:
            continue
        cur = doc.get("curated") or {}
        title_date = cur.get("title_date", week)
        hl = week_highlight(doc)
        cards.append(
            '    <a class="card" href="weeks/' + esc(week) + '.html">\n'
            f'      <h3>{esc(title_date)}</h3>\n'
            f'      <div class="when">{esc(week)} · 覆盖 {esc(cur.get("window",""))}</div>\n'
            f'      <div class="hl">{esc(hl)}</div>\n'
            '    </a>'
        )
    cards_html = "\n".join(cards) if cards else '    <div class="empty">暂无已发布周报。</div>'
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(zh)}</title>
<link rel="stylesheet" href="../assets/feeds.css">
</head>
<body>
<div class="wrap">
  <div class="crumb"><a href="../index.html">资讯</a> / {esc(zh)}</div>
  <header class="site">
    <h1>{esc(zh)}</h1>
    <div class="sub">{esc(en)} · {esc(desc)}</div>
  </header>
  <div class="card-grid">
{cards_html}
  </div>
  <footer class="site">由 blueyi.github.io/feeds 自动生成 · 共 {len([c for c in cards])} 期</footer>
</div>
</body>
</html>
"""
    (FEEDS_DIR / channel / "index.html").write_text(page, encoding="utf-8")
    return len(cards)


def build_manifest(channel: str, spec: dict):
    weeks = list_weeks(channel)
    manifest = {
        "channel": channel,
        "title": spec.get("title"),
        "title_en": spec.get("title_en"),
        "description": spec.get("description"),
        "domains": [{"id": d["id"], "name": d["name"], "emoji": d.get("emoji", "")} for d in spec["domains"]],
        "arxiv_categories": spec.get("arxiv_categories", []),
        "hn_min_score": spec.get("hn_min_score"),
        "weeks": [
            {
                "week": week,
                "html": f"weeks/{week}.html" if html_exists else None,
                "data": f"data/{week}.json",
                "window": (doc.get("curated") or {}).get("window", (doc.get("raw") or {}).get("window")),
                "published": html_exists,
            }
            for (week, doc, html_exists) in weeks
        ],
    }
    (FEEDS_DIR / channel / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def build_site_index(channel_specs: dict):
    chans = []
    for channel in CHANNELS:
        spec = channel_specs[channel]
        zh = spec.get("title", channel)
        desc = spec.get("description", "")
        weeks = [w for w in list_weeks(channel) if w[2]]
        latest = []
        for week, doc, _ in weeks[:3]:
            cur = doc.get("curated") or {}
            latest.append(f'<a href="{esc(channel)}/weeks/{esc(week)}.html">{esc(cur.get("title_date", week))}</a>')
        latest_html = " · ".join(latest) if latest else "暂无周报"
        chans.append(
            f'    <a class="chan" href="{esc(channel)}/index.html">\n'
            f'      <h2>{esc(zh)}</h2>\n'
            f'      <p>{esc(desc)}</p>\n'
            f'      <div class="latest">最新：{latest_html}</div>\n'
            '    </a>'
        )
    chans_html = "\n".join(chans)
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>最新资讯 · Feeds</title>
<link rel="stylesheet" href="assets/feeds.css">
</head>
<body>
<div class="wrap">
  <header class="site">
    <h1>📡 最新资讯 Feeds</h1>
    <div class="sub">每周自动整理的 AI Infra 与具身智能技术资讯 · 数据源 Hacker News + arXiv</div>
  </header>
  <div class="chan-grid">
{chans_html}
  </div>
  <footer class="site">由 blueyi.github.io/feeds 自动生成 · 自包含引擎见 _engine/ · master 直发 GitHub Pages</footer>
</div>
</body>
</html>
"""
    (FEEDS_DIR / "index.html").write_text(page, encoding="utf-8")


def main():
    specs = {c: load_spec(c) for c in CHANNELS}
    for c in CHANNELS:
        n = build_channel_index(c, specs[c])
        build_manifest(c, specs[c])
        print(f"[{c}] index rebuilt: {n} published week(s)")
    build_site_index(specs)
    print("[site] feeds/index.html rebuilt")


if __name__ == "__main__":
    main()
