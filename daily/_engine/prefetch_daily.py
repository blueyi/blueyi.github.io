#!/usr/bin/env python3
"""
AI Infra 日报 prefetch 脚本。

输出 JSON 到 stdout，供 Cursor 定时 Agent 挑选、分类并写成中文日报。
配置读取仓库内 `_engine/news_config.json`。日期使用 Asia/Hong_Kong。

源(2026-08-27 扩充,降低 arXiv 占比,补产业/中文动态):
- Hacker News topstories(score >= 60,过滤 AI Infra 相关关键词)
- arXiv RSS:cs.DC / cs.AR / cs.PL / cs.LG / cs.RO(最新一批)
- 具身智能媒体 RSS(IEEE Spectrum Robotics / TechCrunch Robotics /
  Robotics & Automation News / ExplainX)——喂「具身智能」分类
- 科技博客 / 产业媒体 RSS(英文:SemiAnalysis / SemiEngineering / EE Times /
  VentureBeat / SiliconANGLE / The Verge / NVIDIA / HuggingFace / OpenAI /
  Google AI / Import AI / Next Platform / ServeTheHome / Blocks&Files /
  Data Center Dynamics / The Register / Tom's Hardware / Chips and Cheese /
  TechCrunch AI / Microsoft Research)——用全量 KW_RE 过滤,
  喂 8 个分类里的产业动态(公司/产品/融资/分析)
- 融资/独角兽源(TechCrunch Fundraising / TechCrunch Venture / Crunchbase News)
  ——放宽过滤(全保留),喂产业动态里的融资/公司动态
- 中文科技媒体 RSS(量子位 / InfoQ中国 / 雷锋网 / 新智元)——微信公众号内容
  的公开 web 镜像,用中文关键词过滤,喂产业动态与国内视角

容错:任何单一源失败不影响整体输出。
"""
import json
import re
import sys
import time
import html
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "Mozilla/5.0 (compatible; ai-infra-news/1.2)"}

# ─── 统一源+关键词：从 blueyi.github.io 仓库共享配置读取（与周报共用，单一事实源）───
_REPO = Path(__file__).resolve().parents[2]
_CONFIG = json.loads((_REPO / "_engine" / "news_config.json").read_text(encoding="utf-8"))

_all_kw = []
for _c in _CONFIG["categories"]:
    _all_kw.extend(_c.get("keywords", []))
KEYWORDS = list(dict.fromkeys(_all_kw))
KW_RE = re.compile("|".join(re.escape(k) for k in KEYWORDS), re.I)

EMBODIED_KEYWORDS = _CONFIG["embodied_keywords"]
EMBODIED_KW_RE = re.compile("|".join(re.escape(k) for k in EMBODIED_KEYWORDS), re.I)

CN_KEYWORDS = _CONFIG["cn_keywords"]
CN_KW_RE = re.compile("|".join(re.escape(k) for k in CN_KEYWORDS), re.I)

RSS_FEEDS = _CONFIG["sources"]["embodied"]
BLOG_FEEDS = _CONFIG["sources"]["english"]
CN_FEEDS = _CONFIG["sources"]["chinese"]
FINANCE_FEEDS = _CONFIG["sources"]["finance"]
FINANCE_MATCH_ALL = re.compile("")

_ARXIV_CATS = tuple(_CONFIG["arxiv_categories"])
_HN_MIN_SCORE = _CONFIG["hn_min_score"]


def http_get(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def _clean(s: str) -> str:
    s = s.replace("<![CDATA[", "").replace("]]>", "")
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(re.sub(r"\s+", " ", s).strip())


def fetch_hn(limit_score: int = _HN_MIN_SCORE, max_items: int = 50) -> list:
    out = []
    try:
        ids = json.loads(http_get(
            "https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10))[:120]
    except Exception as e:
        return [{"_error": f"HN topstories: {e}"}]
    seen = 0
    for sid in ids:
        if seen >= max_items:
            break
        try:
            s = json.loads(http_get(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=8))
        except Exception:
            continue
        if not s:
            continue
        score = s.get("score", 0)
        title = s.get("title", "") or ""
        url = s.get("url", "") or ""
        text = f"{title} {url}"
        if score >= limit_score and KW_RE.search(text):
            out.append({
                "source": "hn",
                "score": score,
                "title": title,
                "url": url,
                "hn_url": f"https://news.ycombinator.com/item?id={sid}",
            })
            seen += 1
    return out


def fetch_arxiv(cats=_ARXIV_CATS, per_cat: int = 12) -> list:
    out = []
    for cat in cats:
        try:
            time.sleep(2)  # be polite
            xml = http_get(f"http://export.arxiv.org/rss/{cat}", timeout=15)
        except Exception as e:
            out.append({"_error": f"arxiv {cat}: {e}"})
            continue
        items = re.findall(r"<item>(.*?)</item>", xml, re.S)
        for it in items[:per_cat]:
            t = re.search(r"<title>(.*?)</title>", it, re.S)
            l = re.search(r"<link>(.*?)</link>", it, re.S)
            d = re.search(r"<description>(.*?)</description>", it, re.S)
            if not (t and l):
                continue
            title = _clean(t.group(1))
            link = l.group(1).strip()
            desc = _clean(d.group(1)) if d else ""
            # Strip "arXiv:XXXX Announce Type: ... Abstract:" prefix
            desc = re.sub(r"^arXiv:[^\s]+\s*Announce Type:\s*\w+\s*", "", desc)
            desc = re.sub(r"^Abstract:\s*", "", desc)
            out.append({
                "source": f"arxiv:{cat}",
                "title": title,
                "url": link,
                "abstract": desc[:400],
            })
    return out


def fetch_rss(feeds, kw_re, per_feed: int = 8, source_label: str = "rss") -> list:
    """并发抓取 RSS;标题+摘要命中 kw_re 才保留;单源失败跳过。"""
    out = []

    def _one(feed):
        try:
            xml = http_get(feed["url"], timeout=12)
            items = re.findall(r"<item>(.*?)</item>", xml, re.S) or \
                re.findall(r"<entry>(.*?)</entry>", xml, re.S)
            rows = []
            for it in items[:per_feed]:
                t = re.search(r"<title[^>]*>(.*?)</title>", it, re.S)
                l = re.search(r"<link[^>]*>(.*?)</link>", it, re.S)
                href = re.search(r'<link[^>]*href="([^"]+)"', it)
                d = re.search(r"<description[^>]*>(.*?)</description>", it, re.S) or \
                    re.search(r"<summary[^>]*>(.*?)</summary>", it, re.S)
                if not t:
                    continue
                title = _clean(t.group(1))
                if href:
                    link = href.group(1)
                elif l:
                    link = _clean(l.group(1))
                else:
                    link = ""
                desc = _clean(d.group(1)) if d else ""
                text = f"{title} {desc}"
                if kw_re.search(text):
                    rows.append({"title": title, "url": link, "summary": desc[:300]})
            return feed, rows, None
        except Exception as e:
            return feed, [], f"{source_label} {feed['name']}: {e}"

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(_one, f) for f in feeds]
        for fu in as_completed(futs):
            feed, rows, err = fu.result()
            if err:
                out.append({"_error": err})
                continue
            for r in rows:
                out.append({
                    "source": source_label,
                    "feed": feed["name"],
                    "title": r["title"],
                    "url": r["url"],
                    "summary": r["summary"],
                })
    return out


def main():
    now = datetime.now(timezone(timedelta(hours=8)))  # Asia/Hong_Kong, independent of VM timezone
    payload = {
        "generated_at": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "weekday": now.strftime("%A"),
        "hn": [],
        "arxiv": [],
        "rss": [],
        "blog": [],
        "cn": [],
        "errors": [],
    }
    try:
        hn = fetch_hn()
        payload["hn"] = [x for x in hn if "_error" not in x]
        payload["errors"] += [x["_error"] for x in hn if "_error" in x]
    except Exception as e:
        payload["errors"].append(f"hn outer: {e}")
    try:
        arxiv = fetch_arxiv()
        payload["arxiv"] = [x for x in arxiv if "_error" not in x]
        payload["errors"] += [x["_error"] for x in arxiv if "_error" in x]
    except Exception as e:
        payload["errors"].append(f"arxiv outer: {e}")
    try:
        rss = fetch_rss(RSS_FEEDS, EMBODIED_KW_RE, source_label="rss")
        payload["rss"] = [x for x in rss if "_error" not in x]
        payload["errors"] += [x["_error"] for x in rss if "_error" in x]
    except Exception as e:
        payload["errors"].append(f"rss outer: {e}")
    try:
        blog = fetch_rss(BLOG_FEEDS, KW_RE, source_label="blog")
        finance = fetch_rss(FINANCE_FEEDS, FINANCE_MATCH_ALL, source_label="blog")
        payload["blog"] = [x for x in blog if "_error" not in x] + [x for x in finance if "_error" not in x]
        payload["errors"] += [x["_error"] for x in blog if "_error" in x]
        payload["errors"] += [x["_error"] for x in finance if "_error" in x]
    except Exception as e:
        payload["errors"].append(f"blog outer: {e}")
    try:
        cn = fetch_rss(CN_FEEDS, CN_KW_RE, source_label="cn")
        payload["cn"] = [x for x in cn if "_error" not in x]
        payload["errors"] += [x["_error"] for x in cn if "_error" in x]
    except Exception as e:
        payload["errors"].append(f"cn outer: {e}")

    payload["counts"] = {
        "hn": len(payload["hn"]),
        "arxiv": len(payload["arxiv"]),
        "rss": len(payload["rss"]),
        "blog": len(payload["blog"]),
        "cn": len(payload["cn"]),
        "errors": len(payload["errors"]),
    }

    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
