#!/usr/bin/env python3
"""
rebuild_index.py — 扫描 data/*.json,重建：
  - 每个频道的 index.html（周报列表，倒序）
  - 每个频道的 manifest.json（所有周 + 领域定义 + 元信息，迁移用）
  - feeds/index.html（总入口，两频道卡片 + 各最新 3 期）

无参数运行即可重建全部（幂等）。新增周报无需手改任何索引。
仅用 Python 标准库 + pyyaml。
"""
import argparse
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

# 各频道的更新时间（cron 触发时间）—— 用于在总入口页展示，避免用户看到当天未更新以为坏掉了
# 与 skill/cron 保持一致：AI Infra 周六 06:00 HKT / 具身智能 周日 22:00 HKT
CHANNEL_SCHEDULES = {
    "ai-infra": "Updated every Sat 06:00 HKT",
    "embodied-ai": "Updated every Sun 22:00 HKT",
}

# 频道 emoji（复用主页宽卡片风格）
CHANNEL_EMOJIS = {
    "ai-infra": "📡",
    "embodied-ai": "🤖",
}

# 总入口页频道卡片英文描述（导航区固定 UI，与英文站点外壳一致；周报正文内容仍中文）
CHANNEL_DESC_EN = {
    "ai-infra": "Full-stack AI infrastructure — chips / compilers / inference / datacenters / safety / autokernels / edge",
    "embodied-ai": "Embodied AI progress — VLA / dexterous manipulation / sim2real / embodied models / chips / manufacturing / market",
}

# 返回主页图标 —— feather 风格描边 home SVG，与主页 index.html 的图标风格一致
# 取代跳脱的 🏠 emoji，融入暗色极简风。inline 复用于面包屑第一层。
HOME_SVG = ('<svg class="home-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M3 9.5L12 3l9 6.5"/><path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/></svg>')


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


# ─────────────────────────────────────────────────────────────────────────────
# Format normalization —— agent 写 curated 时格式会飘（全角/半角括号、～/~/→ 等
# 都出现过），统一在这里 normalize，避免不同周次显示混乱。见 skill pitfall #13。
# ─────────────────────────────────────────────────────────────────────────────

import datetime as _dt

_WEEK_RE = re.compile(r'(\d{4})-W(\d{1,2})')

def week_range(week: str):
    """由 ISO 周编号 'YYYY-Www' 推算该周 周一~周日 的 (start_date, end_date)。
    返回 datetime.date 二元组；无法解析时返回 (None, None)。
    这是标题/窗口日期范围的**唯一事实源**——不再依赖 agent 手写的 title_date，
    从根本上杜绝格式与日期飘忽（见 skill 标题统一方案 2026-07-13）。
    """
    if not week:
        return (None, None)
    m = _WEEK_RE.search(str(week))
    if not m:
        return (None, None)
    year, wk = int(m.group(1)), int(m.group(2))
    try:
        start = _dt.date.fromisocalendar(year, wk, 1)  # 周一
        end = _dt.date.fromisocalendar(year, wk, 7)    # 周日
    except ValueError:
        return (None, None)
    return (start, end)

def _week_id(week: str) -> str:
    """把任意含周编号的字符串收敛成规范 'YYYY-Www'（两位周号）。"""
    m = _WEEK_RE.search(str(week or ""))
    if not m:
        return str(week or "").strip()
    return f'{m.group(1)}-W{int(m.group(2)):02d}'

def normalize_title_date(td, week: str = "") -> str:
    """统一标题为 'YYYY-Www · MM-DD ~ MM-DD'（周一~周日，省略年份，靠周号已含年）。
    完全忽略 agent 手写的 td，只按 week 重算——彻底根治历史各期格式混乱。
    week 无法解析日期范围时降级为纯周号 'YYYY-Www'。
    """
    # td 优先取自身若含周号，否则用 week
    src = td if (td and _WEEK_RE.search(str(td))) else week
    wid = _week_id(src)
    start, end = week_range(wid)
    if start and end:
        return f'{wid} · {start:%m-%d} ~ {end:%m-%d}'
    return wid or (week or "")

def normalize_window(win, week: str = "") -> str:
    """统一 window 为 'YYYY-MM-DD ~ YYYY-MM-DD'（周一~周日）。
    优先按 week 重算；week 不可解析时才退回容忍 dict/字符串输入。
    """
    start, end = week_range(week)
    if start and end:
        return f'{start:%Y-%m-%d} ~ {end:%Y-%m-%d}'
    # 降级：沿用旧的容忍逻辑
    if win is None or win == "":
        return ""
    if isinstance(win, dict):
        s, e = win.get("start", ""), win.get("end", "")
        win = f'{s} ~ {e}' if s and e else (s or e or "")
    win = str(win)
    win = re.sub(r'\s*(?:→|➔|➜|—|–|~|～|\.\.|to)\s*', ' ~ ', win)
    return re.sub(r'\s+~\s+', ' ~ ', win).strip()


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
    zh = spec.get("title_en", spec.get("title", channel))  # 站点外壳统一英文
    en = spec.get("title_en", channel)
    desc = CHANNEL_DESC_EN.get(channel, spec.get("description", ""))
    weeks = list_weeks(channel)
    cards = []
    for week, doc, html_exists in weeks:
        if not html_exists:
            continue
        cur = doc.get("curated") or {}
        title_date = normalize_title_date(cur.get("title_date", week), week)
        window = normalize_window(cur.get("window", ""), week)
        hl = week_highlight(doc)
        cards.append(
            '    <a class="card" href="weeks/' + esc(week) + '.html">\n'
            f'      <h3>{esc(title_date)}</h3>\n'
            f'      <div class="when">{esc(window)}</div>\n'
            f'      <div class="hl">{esc(hl)}</div>\n'
            '    </a>'
        )
    cards_html = "\n".join(cards) if cards else '    <div class="empty">No issues published yet.</div>'
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
  <div class="crumb"><a href="/">{HOME_SVG}Home</a> / <a href="../index.html">Feeds</a> / {esc(zh)}</div>
  <header class="site">
    <h1>{esc(zh)}</h1>
    <div class="sub">{esc(desc)}</div>
  </header>
  <div class="card-grid">
{cards_html}
  </div>
  <footer class="site">Auto-generated · {len([c for c in cards])} issues</footer>
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
                    (doc.get("curated") or {}).get("window", (doc.get("raw") or {}).get("window", "")), week
                ),
                "highlight": ((doc.get("curated") or {}).get("highlights") or [None])[0],
                "published": html_exists,
            }
            for (week, doc, html_exists) in weeks
        ],
    }
    (FEEDS_DIR / channel / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def build_site_index(channel_specs: dict, recent_weeks: int = 3, highlights_per_week: int = 3):
    """渲染 feeds/index.html —— 两频道并排卡片，每卡默认展示近 3 期 × 3 条 highlights。

    参数化目的：未来只需 `python3 rebuild_index.py --recent-weeks 4` 即可调整密度，
    不需改代码。data 里 highlights 少于要求条数时按实际数量渲染（不会填充空占位）。
    """
    chans = []
    for channel in CHANNELS:
        spec = channel_specs[channel]
        zh = spec.get("title_en", spec.get("title", channel))
        desc = CHANNEL_DESC_EN.get(channel, spec.get("description", ""))
        emoji = CHANNEL_EMOJIS.get(channel, "")
        schedule = CHANNEL_SCHEDULES.get(channel, "")
        weeks = [w for w in list_weeks(channel) if w[2]]  # 只取已发布

        # 渲染近 N 期的亮点块
        wk_blocks = []
        for week, doc, _ in weeks[:recent_weeks]:
            cur = doc.get("curated") or {}
            # 标题范围统一由周编号推算（周一~周日，MM-DD），badge 拆成周号 + 日期段
            wk_label = _week_id(week)
            _s, _e = week_range(week)
            wk_range = f'{_s:%m-%d} ~ {_e:%m-%d}' if _s and _e else ""

            highlights = (cur.get("highlights") or [])[:highlights_per_week]
            if not highlights:
                # 没有 highlights 的一期也保留占位，展示 window
                hl_html = '        <div class="wk-empty">No highlights this issue</div>'
            else:
                lis = "\n".join(f"          <li>{esc(h)}</li>" for h in highlights)
                hl_html = f"        <ol>\n{lis}\n        </ol>"

            wk_href = f'{esc(channel)}/weeks/{esc(week)}.html'
            wk_blocks.append(
                f'      <div class="wk-block" data-href="{wk_href}" role="link" tabindex="0" '
                f'aria-label="{esc(wk_label)} 周报详情">\n'
                f'        <a class="wk-badge" href="{wk_href}">'
                f'{esc(wk_label)}{(" · " + esc(wk_range)) if wk_range else ""} →</a>\n'
                f'{hl_html}\n'
                f'      </div>'
            )
        blocks_html = "\n".join(wk_blocks) if wk_blocks else '      <div class="wk-empty">No issues published yet</div>'

        # 用 <div> 外层 + 内部标题 <a>,避免嵌套 <a> 的非法 HTML(浏览器会把内部 <a> 抽出,破坏 DOM)
        chans.append(
            f'    <div class="chan">\n'
            f'      <h2><a class="chan-title" href="{esc(channel)}/index.html">{esc(emoji)} {esc(zh)} →</a></h2>\n'
            f'      <p class="chan-desc">{esc(desc)}</p>\n'
            f'      <div class="chan-schedule">{esc(schedule)}</div>\n'
            f'      <div class="chan-highlights">\n'
            f'{blocks_html}\n'
            f'      </div>\n'
            f'      <div class="chan-footer"><a href="{esc(channel)}/index.html">View all issues →</a></div>\n'
            '    </div>'
        )
    chans_html = "\n".join(chans)
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Weekly Feeds</title>
<link rel="stylesheet" href="assets/feeds.css">
</head>
<body>
<div class="wrap">
  <div class="crumb"><a href="/">{HOME_SVG}Home</a> / Feeds</div>
  <header class="site">
    <h1>📡 Weekly Feeds</h1>
    <div class="sub">Weekly AI Infra &amp; Embodied AI digest · HN / arXiv / industry media / markets</div>
  </header>
  <div class="chan-grid">
{chans_html}
  </div>
  <footer class="site">Auto-generated · GitHub Pages</footer>
</div>
<script>
// 每周亮点卡片整块可点击 → 跳转当周周报详情。
// badge 内的 <a> 保留原生行为；点击卡片其它区域或键盘 Enter/Space 也跳转。
(function () {{
  document.querySelectorAll('.wk-block[data-href]').forEach(function (el) {{
    var go = function () {{ window.location.href = el.getAttribute('data-href'); }};
    el.addEventListener('click', function (e) {{
      if (e.target.closest('a')) return; // 点到 badge 链接就走原生
      go();
    }});
    el.addEventListener('keydown', function (e) {{
      if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); go(); }}
    }});
  }});
}})();
</script>
</body>
</html>
"""
    lint_html(page, 'feeds/index.html')
    (FEEDS_DIR / "index.html").write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Rebuild feeds site index / channel index / manifests")
    parser.add_argument("--recent-weeks", type=int, default=3,
                        help="总入口页每频道展示的最近期数（默认 3）")
    parser.add_argument("--highlights-per-week", type=int, default=3,
                        help="总入口页每期展示的亮点条数上限（默认 3）")
    args = parser.parse_args()

    specs = {c: load_spec(c) for c in CHANNELS}
    for c in CHANNELS:
        n = build_channel_index(c, specs[c])
        build_manifest(c, specs[c])
        print(f"[{c}] index rebuilt: {n} published week(s)")
    build_site_index(specs, recent_weeks=args.recent_weeks, highlights_per_week=args.highlights_per_week)
    print(f"[site] feeds/index.html rebuilt (recent_weeks={args.recent_weeks}, highlights_per_week={args.highlights_per_week})")


if __name__ == "__main__":
    main()
