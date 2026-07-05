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
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import yaml

ENGINE_DIR = Path(__file__).resolve().parent.parent
FEEDS_DIR = ENGINE_DIR.parent
CHANNELS = ["ai-infra", "embodied-ai"]


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


# ─────────────────────────────────────────────────────────────────────────────
# Format normalization —— agent 写 curated 时格式会飘（全角/半角括号、～/~/→ 等
# 都出现过），统一在这里 normalize，避免不同周次显示混乱。见 skill pitfall #13。
# ─────────────────────────────────────────────────────────────────────────────

_DATE_MMDD = r'\d{1,2}-\d{1,2}'
_DATE_YMD  = r'\d{4}-\d{1,2}-\d{1,2}'

def _normalize_range(text: str) -> str:
    """把日期范围里的分隔符统一成 ' ~ '，去掉 →、～、  ..、to 等变体。"""
    if not text:
        return text
    # 常见分隔符统一
    text = re.sub(r'\s*(?:→|➔|➜|—|–|~|～|\.\.|to)\s*', ' ~ ', text)
    # 多空格压缩
    text = re.sub(r'\s+~\s+', ' ~ ', text)
    return text.strip()

def normalize_title_date(td, week: str = "") -> str:
    """把 title_date 统一成 'YYYY-Www（MM-DD ~ MM-DD）' 格式。
    容忍以下 agent 常见变体:
      '2026-W27 (06-28 → 07-05)'   -> '2026-W27（06-28 ~ 07-05）'
      '2026-W27（06-27 ~ 07-03）'  -> 原样(已合规)
      '2026-W27'                    -> '2026-W27' (无日期段就保留)
      '(06-27~07-03)'               -> '{week}（06-27 ~ 07-03）'
    """
    if td is None or td == "":
        return week or ""
    td = str(td)  # 防御 agent 传了非字符串
    # 先规范括号内的日期范围
    def _rep(m):
        inner = _normalize_range(m.group(1))
        return f'（{inner}）'
    # 处理任一种括号
    td = re.sub(r'[（(]\s*(' + _DATE_YMD + r'|' + _DATE_MMDD + r'[^)）]*?)\s*[)）]', _rep, td)
    # 若还没有 week 号前缀而是纯日期段,补上
    if week and not re.match(r'^\s*\d{4}-W\d{2}', td):
        td = f'{week}{td}' if td.startswith('（') else f'{week} {td}'
    # 合并 ")(" 之间可能出现的多余空格,并把 " （" 收紧成 "（"
    td = re.sub(r'\s+（', '（', td)
    td = re.sub(r'）\s+', '）', td)
    # 收尾去多余空格
    return re.sub(r'\s+', ' ', td).strip()

def normalize_window(win) -> str:
    """把 window 统一成 'YYYY-MM-DD ~ YYYY-MM-DD'。
    容忍 dict 输入(agent 有时把 raw 里的 {start,end} 结构直接抄进 curated)。
    """
    if win is None or win == "":
        return ""
    if isinstance(win, dict):
        s, e = win.get("start", ""), win.get("end", "")
        win = f'{s} ~ {e}' if s and e else (s or e or "")
    return _normalize_range(str(win))


# ─────────────────────────────────────────────────────────────────────────────
# HTML lint —— 生成后简单校验,防再引入嵌套 <a> 之类的合规问题(见 pitfall #14)。
# ─────────────────────────────────────────────────────────────────────────────
class _NestedAnchorChecker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.errors = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.depth += 1
            if self.depth > 1:
                self.errors.append(f'nested <a> at line {self.getpos()[0]}')
    def handle_endtag(self, tag):
        if tag == 'a' and self.depth > 0:
            self.depth -= 1

def lint_html(html_text: str, source: str) -> None:
    """快速合法性检查,发现问题打印警告(不阻断,但会在 CI 里显眼)。"""
    ck = _NestedAnchorChecker()
    ck.feed(html_text)
    if ck.errors:
        print(f'[lint warning] {source}: {"; ".join(ck.errors[:3])}', file=sys.stderr)


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
        title_date = normalize_title_date(cur.get("title_date", week), week)
        window = normalize_window(cur.get("window", ""))
        hl = week_highlight(doc)
        cards.append(
            '    <a class="card" href="weeks/' + esc(week) + '.html">\n'
            f'      <h3>{esc(title_date)}</h3>\n'
            f'      <div class="when">{esc(week)} · 覆盖 {esc(window)}</div>\n'
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
    lint_html(page, f'{channel}/index.html')
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
                "title_date": normalize_title_date((doc.get("curated") or {}).get("title_date", week), week),
                "window": normalize_window(
                    (doc.get("curated") or {}).get("window", (doc.get("raw") or {}).get("window", ""))
                ),
                "highlight": ((doc.get("curated") or {}).get("highlights") or [None])[0],
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
            td = normalize_title_date(cur.get("title_date", week), week)
            latest.append(f'<a href="{esc(channel)}/weeks/{esc(week)}.html">{esc(td)}</a>')
        latest_html = " · ".join(latest) if latest else "暂无周报"
        # 用 <div> 外层 + 内部标题 <a>,避免嵌套 <a> 的非法 HTML(浏览器会把内部 <a> 抽出,破坏 DOM)
        chans.append(
            f'    <div class="chan">\n'
            f'      <h2><a class="chan-title" href="{esc(channel)}/index.html">{esc(zh)} →</a></h2>\n'
            f'      <p>{esc(desc)}</p>\n'
            f'      <div class="latest">最新：{latest_html}</div>\n'
            '    </div>'
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
    lint_html(page, 'feeds/index.html')
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
