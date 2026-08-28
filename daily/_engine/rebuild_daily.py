#!/usr/bin/env python3
"""rebuild_daily.py — 扫描 data/*.md，重建 daily/index.html + daily/manifest.json。

无参数运行即幂等重建。新增日报无需手改任何索引。
仅用 Python 标准库。
"""
import json
import subprocess
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
DAILY_DIR = ENGINE_DIR.parent
DATA_DIR = DAILY_DIR / "data"

from render_daily import (  # noqa: E402
    TITLE, DESC, SCHEDULE, HOME_SVG, esc, weekday_zh, parse, first_highlight,
)


def list_days():
    """返回 [(date, md_text)] 倒序（仅含已生成 html 的）。"""
    out = []
    if not DATA_DIR.exists():
        return out
    for p in sorted(DATA_DIR.glob("*.md"), reverse=True):
        date = p.stem
        if (DAILY_DIR / f"{date}.html").exists():
            out.append((date, p.read_text(encoding="utf-8")))
    return out


def build_index(days):
    cards = []
    for date, md in days:
        wd = weekday_zh(date)
        hl = first_highlight(md)
        cards.append(
            f'    <a class="card" href="{esc(date)}.html">\n'
            f'      <h3>{esc(date)} · {esc(wd)}</h3>\n'
            f'      <div class="hl">{esc(hl)}</div>\n'
            '    </a>'
        )
    cards_html = "\n".join(cards) if cards else '    <div class="empty">No issues published yet.</div>'
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(TITLE)}</title>
<link rel="stylesheet" href="assets/daily.css">
</head>
<body>
<div class="wrap">
  <div class="crumb"><a href="/">{HOME_SVG}Home</a> / Daily</div>
  <header class="site">
    <h1>📡 {esc(TITLE)}</h1>
    <div class="sub">{esc(DESC)} · <a href="/search/">🔍 搜索全部资讯</a></div>
  </header>
  <div class="meta-bar">
    <span>Schedule: <b>{esc(SCHEDULE)}</b></span>
    <span>Issues: <b>{len(cards)}</b></span>
  </div>
  <div class="card-grid">
{cards_html}
  </div>
  <footer class="site">Auto-generated · {len(cards)} issues</footer>
</div>
</body>
</html>
"""
    (DAILY_DIR / "index.html").write_text(page, encoding="utf-8")
    return len(cards)


def build_manifest(days):
    manifest = {
        "channel": "ai-infra-daily",
        "title": "AI Infra 日报",
        "title_en": TITLE,
        "description": DESC,
        "schedule": SCHEDULE,
        "days": [
            {
                "date": date,
                "html": f"{date}.html",
                "title_date": f"{date} · {weekday_zh(date)}",
                "highlight": first_highlight(md),
                "published": True,
            }
            for date, md in days
        ],
    }
    (DAILY_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    days = list_days()
    n = build_index(days)
    build_manifest(days)
    print(f"[daily] index rebuilt: {n} published day(s)")
    # 重建统一搜索索引（聚合 daily + feeds 历史条目）
    try:
        r = subprocess.run([sys.executable, str(DAILY_DIR.parent / "_engine" / "build_search_index.py")],
                           capture_output=True, text=True)
        if r.stdout.strip():
            print(r.stdout.strip())
        if r.returncode != 0 and r.stderr.strip():
            print(f"[search] {r.stderr.strip()}", file=sys.stderr)
    except Exception as e:
        print(f"[search] build failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
