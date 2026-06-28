#!/usr/bin/env python3
"""
通用资讯 prefetch 抓取器（feeds/ 独立资讯站专用，不依赖任何其它方案）。

用法:
    python3 prefetch.py --channel ai-infra
    python3 prefetch.py --channel embodied-ai

读取 feeds/_engine/domains/<channel>.yaml,抓取最近 N 天的:
  - Hacker News topstories（score >= 频道阈值,关键词过滤）
  - arXiv RSS（频道指定分类的最新一批）
按领域 keywords 给每条打 domain 标签;命中 exclude_to_channel 的条目剔除（划归其它频道）。
输出 JSON 到本周 data/<YYYY-Www>.json 的 raw 段（保留已有 curated 段不动）。

容错:任何单源失败不影响整体;最终始终写出 JSON。
仅用 Python 标准库 + pyyaml。
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

UA = {"User-Agent": "Mozilla/5.0 (compatible; blueyi-feeds/1.0)"}
ENGINE_DIR = Path(__file__).resolve().parent.parent          # feeds/_engine
FEEDS_DIR = ENGINE_DIR.parent                                # feeds/


def iso_week_id(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def http_get(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def load_domain_spec(channel: str) -> dict:
    path = ENGINE_DIR / "domains" / f"{channel}.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_keyword_index(spec: dict):
    """返回 (全频道命中正则, [(domain_id, 编译正则), ...], 排除正则 or None)。"""
    per_domain = []
    all_kw = []
    for d in spec["domains"]:
        kws = d.get("keywords", []) or []
        all_kw.extend(kws)
        if kws:
            rgx = re.compile("|".join(re.escape(k) for k in kws), re.I)
            per_domain.append((d["id"], rgx))
    all_re = re.compile("|".join(re.escape(k) for k in all_kw), re.I) if all_kw else None
    excl = spec.get("exclude_to_channel") or {}
    excl_kw = []
    for _ch, kws in excl.items():
        excl_kw.extend(kws or [])
    excl_re = re.compile("|".join(re.escape(k) for k in excl_kw), re.I) if excl_kw else None
    return all_re, per_domain, excl_re


def tag_domains(text: str, per_domain) -> list:
    return [did for (did, rgx) in per_domain if rgx.search(text)]


def fetch_hn(all_re, per_domain, excl_re, min_score: int, max_items: int = 40) -> list:
    out = []
    try:
        ids = json.loads(http_get(
            "https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10))[:150]
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
        if score < min_score:
            continue
        if all_re is None or not all_re.search(text):
            continue
        # 频道间去重：命中排除词且未被本频道强领域命中 -> 跳过
        domains = tag_domains(text, per_domain)
        if excl_re and excl_re.search(text) and not domains:
            continue
        out.append({
            "source": "hn",
            "score": score,
            "title": title,
            "url": url,
            "hn_url": f"https://news.ycombinator.com/item?id={sid}",
            "domains": domains,
        })
        seen += 1
    return out


def _clean_xml(s: str) -> str:
    s = s.replace("<![CDATA[", "").replace("]]>", "")
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(re.sub(r"\s+", " ", s).strip())


def _arxiv_from_rss(cat: str, per_cat: int) -> list:
    """旧 RSS 源（工作日有料，周末常为空）。"""
    xml = http_get(f"http://export.arxiv.org/rss/{cat}", timeout=15)
    rows = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S)[:per_cat]:
        t = re.search(r"<title>(.*?)</title>", it, re.S)
        l = re.search(r"<link>(.*?)</link>", it, re.S)
        d = re.search(r"<description>(.*?)</description>", it, re.S)
        if not (t and l):
            continue
        title = _clean_xml(t.group(1))
        link = l.group(1).strip()
        desc = _clean_xml(d.group(1)) if d else ""
        desc = re.sub(r"^arXiv:[^\s]+\s*Announce Type:\s*\w+\s*", "", desc)
        desc = re.sub(r"^Abstract:\s*", "", desc)
        rows.append({"source": f"arxiv:{cat}", "title": title, "url": link, "abstract": desc})
    return rows


def _arxiv_from_api(cat: str, per_cat: int) -> list:
    """Atom API 源:按最近提交时间返回,不受公告日历影响(周末兜底)。"""
    url = (
        "http://export.arxiv.org/api/query?"
        f"search_query=cat:{cat}&sortBy=submittedDate&sortOrder=descending"
        f"&max_results={per_cat}"
    )
    xml = http_get(url, timeout=20)
    rows = []
    for ent in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        t = re.search(r"<title>(.*?)</title>", ent, re.S)
        l = re.search(r'<id>(.*?)</id>', ent, re.S)
        d = re.search(r"<summary>(.*?)</summary>", ent, re.S)
        if not (t and l):
            continue
        rows.append({
            "source": f"arxiv:{cat}",
            "title": _clean_xml(t.group(1)),
            "url": l.group(1).strip(),
            "abstract": _clean_xml(d.group(1)) if d else "",
        })
    return rows


def fetch_arxiv(all_re, per_domain, excl_re, cats, per_cat: int = 10) -> list:
    out = []
    for cat in cats:
        rows = []
        try:
            time.sleep(2)  # be polite
            rows = _arxiv_from_rss(cat, per_cat)
        except Exception as e:
            out.append({"_error": f"arxiv rss {cat}: {e}"})
        # RSS 为空(周末/公告间隙) -> API 兜底,保证 feed 不空
        if not rows:
            try:
                time.sleep(2)
                rows = _arxiv_from_api(cat, per_cat)
            except Exception as e:
                out.append({"_error": f"arxiv api {cat}: {e}"})
        for r in rows:
            text = f"{r['title']} {r.get('abstract','')}"
            domains = tag_domains(text, per_domain)
            if excl_re and excl_re.search(text) and not domains:
                continue
            r = dict(r)
            r["abstract"] = r.get("abstract", "")[:400]
            r["domains"] = domains
            out.append(r)
    return out


def _parse_feed_items(xml: str, limit: int) -> list:
    """解析 RSS <item> 或 Atom <entry>，返回 [{title,url,summary}]。"""
    rows = []
    blocks = re.findall(r"<item[ >].*?</item>", xml, re.S) or re.findall(r"<entry[ >].*?</entry>", xml, re.S)
    for b in blocks[:limit]:
        t = re.search(r"<title[^>]*>(.*?)</title>", b, re.S)
        # link: RSS <link>url</link>; Atom <link href="url"/>
        l = re.search(r"<link[^>]*>(.*?)</link>", b, re.S)
        href = re.search(r'<link[^>]*href="([^"]+)"', b)
        d = re.search(r"<description[^>]*>(.*?)</description>", b, re.S) or \
            re.search(r"<summary[^>]*>(.*?)</summary>", b, re.S)
        if not t:
            continue
        url = ""
        if l and l.group(1).strip():
            url = l.group(1).strip()
        elif href:
            url = href.group(1).strip()
        rows.append({
            "title": _clean_xml(t.group(1)),
            "url": url,
            "summary": _clean_xml(d.group(1))[:300] if d else "",
        })
    return rows


def fetch_rss(all_re, per_domain, excl_re, feeds, per_feed: int = 12, cn_mode: bool = False) -> list:
    """并发抓取 RSS 媒体源；单源超时/失败跳过，不影响整体。
    media/official/analysis 走关键词过滤；finance(融资源)放宽——
    融资条目常不含技术关键词，保留交给 agent 判断领域相关性。
    cn_mode=True：中文源，英文关键词过滤不适用，全部保留交 agent 编辑判定。"""
    out = []
    if not feeds:
        return out
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _one(feed):
        try:
            xml = http_get(feed["url"], timeout=12)
            return feed, _parse_feed_items(xml, per_feed), None
        except Exception as e:
            return feed, [], f"rss {feed['name']}: {e}"

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(_one, f) for f in feeds]
        for fu in as_completed(futs):
            feed, rows, err = fu.result()
            if err:
                out.append({"_error": err})
                continue
            kind = feed.get("kind", "media")
            for r in rows:
                text = f"{r['title']} {r.get('summary','')}"
                domains = tag_domains(text, per_domain)
                is_finance = (kind in ("finance", "cn_finance"))
                # 中文源/融资源：放宽（agent 再判定）；其余英文源：关键词过滤 + 频道去重
                if not cn_mode and not is_finance:
                    if all_re is None or not all_re.search(text):
                        continue
                    if excl_re and excl_re.search(text) and not domains:
                        continue
                out.append({
                    "source": "cn_rss" if cn_mode else "rss",
                    "feed": feed["name"],
                    "kind": kind,
                    "title": r["title"],
                    "url": r["url"],
                    "summary": r.get("summary", ""),
                    "domains": domains,
                })
    return out


def fetch_cn_markets(cn_tickers) -> list:
    """东方财富 push2 API 取国内龙头股最新价 + 涨跌幅。无需 key。单只失败跳过。
    f43=价格(×100), f170=涨跌幅(×100), f58=名称, f59=小数位。"""
    out = []
    if not cn_tickers:
        return out
    for tk in cn_tickers:
        secid = tk["secid"]
        try:
            url = (f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}"
                   f"&fields=f43,f57,f58,f59,f169,f170")
            data = json.loads(http_get(url, timeout=10))
            d = data.get("data")
            if not d:
                out.append({"secid": secid, "name": tk.get("name", secid), "_error": "null data"})
                continue
            dec = d.get("f59", 2)
            div = 10 ** dec if isinstance(dec, int) and dec >= 0 else 100
            price = d.get("f43")
            pct = d.get("f170")
            out.append({
                "secid": secid,
                "name": tk.get("name") or d.get("f58", secid),
                "market": tk.get("market", ""),
                "price": round(price / div, 2) if isinstance(price, (int, float)) else None,
                "pct_5d": round(pct / 100, 2) if isinstance(pct, (int, float)) else None,
                "currency": "HKD" if secid.startswith("116.") else "CNY",
            })
        except Exception as e:
            out.append({"secid": secid, "name": tk.get("name", secid), "_error": str(e)[:80]})
    return out


def fetch_markets(tickers) -> list:
    """Yahoo Finance chart API 取最新价 + 近5日涨跌幅。无需 key。单只失败跳过。"""
    out = []
    if not tickers:
        return out
    for tk in tickers:
        sym = tk["sym"]
        try:
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
                   f"?interval=1d&range=5d")
            data = json.loads(http_get(url, timeout=10))
            res = data["chart"]["result"][0]
            meta = res.get("meta", {})
            price = meta.get("regularMarketPrice")
            closes = [c for c in res["indicators"]["quote"][0].get("close", []) if c is not None]
            prev = closes[0] if closes else None
            pct = None
            if price is not None and prev:
                pct = round((price - prev) / prev * 100, 2)
            out.append({
                "sym": sym,
                "name": tk.get("name", sym),
                "price": round(price, 2) if price is not None else None,
                "pct_5d": pct,
                "currency": meta.get("currency", ""),
            })
        except Exception as e:
            out.append({"sym": sym, "name": tk.get("name", sym), "_error": str(e)[:80]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True, choices=["ai-infra", "embodied-ai"])
    ap.add_argument("--week", default=None, help="ISO week id like 2026-W27 (default: now)")
    args = ap.parse_args()

    spec = load_domain_spec(args.channel)
    all_re, per_domain, excl_re = build_keyword_index(spec)

    now = datetime.now(timezone.utc).astimezone()
    week = args.week or iso_week_id(now)
    window_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    raw = {
        "channel": args.channel,
        "week": week,
        "generated_at": now.isoformat(),
        "window": {"start": window_start, "end": now.strftime("%Y-%m-%d")},
        "hn": [],
        "arxiv": [],
        "rss": [],
        "cn_rss": [],
        "markets": [],
        "cn_markets": [],
        "errors": [],
    }

    try:
        hn = fetch_hn(all_re, per_domain, excl_re, int(spec.get("hn_min_score", 60)))
        raw["hn"] = [x for x in hn if "_error" not in x]
        raw["errors"] += [x["_error"] for x in hn if "_error" in x]
    except Exception as e:
        raw["errors"].append(f"hn outer: {e}")

    try:
        ax = fetch_arxiv(all_re, per_domain, excl_re, spec.get("arxiv_categories", []))
        raw["arxiv"] = [x for x in ax if "_error" not in x]
        raw["errors"] += [x["_error"] for x in ax if "_error" in x]
    except Exception as e:
        raw["errors"].append(f"arxiv outer: {e}")

    try:
        rss = fetch_rss(all_re, per_domain, excl_re, spec.get("rss_feeds", []))
        raw["rss"] = [x for x in rss if "_error" not in x]
        raw["errors"] += [x["_error"] for x in rss if "_error" in x]
    except Exception as e:
        raw["errors"].append(f"rss outer: {e}")

    try:
        cn_rss = fetch_rss(all_re, per_domain, excl_re, spec.get("cn_rss_feeds", []), cn_mode=True)
        raw["cn_rss"] = [x for x in cn_rss if "_error" not in x]
        raw["errors"] += [x["_error"] for x in cn_rss if "_error" in x]
    except Exception as e:
        raw["errors"].append(f"cn_rss outer: {e}")

    try:
        raw["markets"] = fetch_markets(spec.get("tickers", []))
    except Exception as e:
        raw["errors"].append(f"markets outer: {e}")

    try:
        raw["cn_markets"] = fetch_cn_markets(spec.get("cn_tickers", []))
    except Exception as e:
        raw["errors"].append(f"cn_markets outer: {e}")

    raw["counts"] = {
        "hn": len(raw["hn"]), "arxiv": len(raw["arxiv"]),
        "rss": len(raw["rss"]), "cn_rss": len(raw["cn_rss"]),
        "markets": len([m for m in raw["markets"] if "_error" not in m]),
        "cn_markets": len([m for m in raw["cn_markets"] if "_error" not in m]),
        "errors": len(raw["errors"]),
    }

    # 写入 data/<week>.json：保留已有 curated 段
    data_path = FEEDS_DIR / args.channel / "data" / f"{week}.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if data_path.exists():
        try:
            existing = json.loads(data_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    doc = {
        "channel": args.channel,
        "week": week,
        "raw": raw,
        "curated": existing.get("curated", {}),  # 由 agent 编辑后填充
        "meta": existing.get("meta", {}),
    }
    data_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    # stdout 给 agent 当素材（只输出 raw，curated 由 agent 产出）
    print(json.dumps(raw, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
