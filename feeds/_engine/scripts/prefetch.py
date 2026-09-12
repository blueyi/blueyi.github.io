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

# 宽泛中文源(kind=cn_broad)机器人/具身关键词过滤器：泛科技源(InfoQ/cnBeta/ITHome 等)
# 内容庞杂，只保留命中以下具身/机器人术语的条目，避免灌入大模型/消费电子噪音。
# 涵盖国内龙头本体公司名（宇树/智元/银河通用等未上市或新上市龙头），确保它们的动态必被留存。
CN_ROBOT_KEYWORDS = [
    # 通用具身/机器人术语（去掉 vla/本体/抓取 等裸词——智驾座舱等已借用，避免污染）
    "机器人", "具身", "人形", "灵巧手", "机械臂", "双足", "四足", "仿生",
    "遥操作", "sim2real", "仿真到真实", "操作策略",
    "视觉-语言-动作", "视觉语言动作", "世界模型", "扩散策略", "模仿学习",
    "具身智能", "具身大模型", "机器狗", "机械狗", "外骨骼", "手术机器人", "工业机器人",
    "物流机器人", "配送机器人", "仓储机器人", "谐波减速器", "触觉传感",
    # 国内龙头本体公司（含未上市/新上市，保证动态必留）。
    # 只收中文全称/无歧义品牌名——英文裸词(figure/booster/kepler/optimus 等常义词)
    # 在中文泛科技源里易误命中，故不入表；国内报道通常带中文名，够用。
    "宇树", "unitree", "智元", "银河通用", "星动纪元",
    "傅利叶", "优必选", "ubtech", "云深处", "逐际动力",
    "众擎", "加速进化", "松延动力", "乐聚机器人", "帕西尼", "跨维智能",
    "自变量", "穹彻", "千寻智能", "灵初", "它石智航",
    "地平线机器人", "特斯拉机器人", "擎朗", "普渡机器人",
]
CN_ROBOT_RE = re.compile("|".join(re.escape(k) for k in CN_ROBOT_KEYWORDS), re.I)

# 宽泛中文源(kind=cn_broad)AI-Infra 关键词过滤器：给 ai-infra 频道用。
# cnBeta/IT之家 等泛科技源充斥手机/显卡游戏评测/消费电子噪音，只保留命中以下
# 基础设施术语的条目。刻意去掉会撞消费电子的裸词(如裸"显卡""GPU"→游戏卡评测)，
# 只收 infra 语境下无歧义的强词——宁缺毋滥，cn_broad 只是补盲安全网。
CN_INFRA_KEYWORDS = [
    # 芯片 / 算力硬件（避免裸"显卡/GPU"，用集群/训练/数据中心语境强词）
    "算力", "HBM", "台积电", "中芯国际", "华虹", "寒武纪", "海光", "昇腾", "壁仞", "摩尔线程",
    "先进制程", "晶圆", "光刻", "存算一体", "GPU集群", "AI芯片", "训练芯片", "推理芯片",
    "英伟达", "nvidia", "blackwell", "hopper", "cuda",
    # 编译器 / 框架
    "编译器", "mlir", "tvm", "triton", "torch.compile", "算子", "自动调优", "编译优化",
    # 推理 / 训练优化（数据中心）
    "大模型推理", "推理优化", "推理框架", "投机解码", "vllm", "sglang", "tensorrt",
    "kv cache", "kv缓存", "moe", "专家并行", "张量并行", "流水线并行", "分布式训练",
    # 数据中心 / 基础设施
    "数据中心", "算力中心", "智算中心", "液冷", "infiniband", "超大规模", "机架", "超算",
    # 安全治理 / 出口管制（infra 相关）
    "出口管制", "芯片禁令", "算力管制", "先进计算",
    # 端侧 / 边缘推理
    "端侧推理", "边缘推理", "npu", "llama.cpp", "端侧大模型", "端侧llm",
]
CN_INFRA_RE = re.compile("|".join(re.escape(k) for k in CN_INFRA_KEYWORDS), re.I)


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


def _apply_shared_config(channel: str, spec: dict) -> dict:
    """ai-infra 频道：源+关键词统一从 _engine/news_config.json 读取（与日报共用）。
    领域显示结构(domains 的 id/emoji/name/desc)仍来自本 yaml；关键词/源/arxiv/hn 来自共享配置。
    embodied-ai 频道：保持原有 yaml 全量配置不动。"""
    if channel != "ai-infra":
        return spec
    cfg_path = FEEDS_DIR.parent / "_engine" / "news_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cat_kw = {c["id"]: c.get("keywords", []) for c in cfg["categories"]}
    for d in spec.get("domains", []):
        if d.get("id") in cat_kw:
            d["keywords"] = cat_kw[d["id"]]
    spec["rss_feeds"] = cfg["sources"]["english"] + cfg["sources"]["finance"]
    spec["cn_rss_feeds"] = cfg["sources"]["chinese"]
    spec["arxiv_categories"] = cfg["arxiv_categories"]
    spec["hn_min_score"] = cfg["hn_min_score"]
    return spec


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


def fetch_arxiv(all_re, per_domain, excl_re, cats, per_cat: int = 15) -> list:
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


def fetch_rss(all_re, per_domain, excl_re, feeds, per_feed: int = 12, cn_mode: bool = False, broad_re=CN_ROBOT_RE) -> list:
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
                # cn_broad：泛科技中文源(InfoQ/cnBeta/ITHome 等)，只保留命中机器人/具身
                # 关键词的条目——覆盖国内龙头本体公司名，确保宇树/智元等动态必被留存。
                if kind == "cn_broad":
                    # 仅按标题过滤：summary 常含"算力/智能座舱"等词，
                    # 会把车机、消费电子噪音误判为 infra，故不纳入匹配。
                    if not broad_re.search(r["title"]):
                        continue
                # 中文垂直源/融资源：放宽（agent 再判定）；其余英文源：关键词过滤 + 频道去重
                elif not cn_mode and not is_finance:
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


def fetch_hf_papers(all_re, per_domain, excl_re, days: int = 7, min_upvotes: int = 1) -> list:
    """抓取 HuggingFace Daily Papers 最近 N 天的论文。
    API: https://huggingface.co/api/daily_papers?date=YYYY-MM-DD&limit=30
    无需登录，返回社区精选（已过一轮人工筛选，信噪比远高于 arXiv 原始 RSS）。
    upvotes 作为热度信号（相当于 HN score）。
    """
    from datetime import date, timedelta

    out = []
    seen_ids: set = set()

    for delta in range(days):
        day = (date.today() - timedelta(days=delta)).isoformat()
        try:
            time.sleep(0.5)  # be polite
            url = f"https://huggingface.co/api/daily_papers?date={day}&limit=30"
            raw_bytes = http_get(url, timeout=12)
            papers = json.loads(raw_bytes)
        except Exception as e:
            out.append({"_error": f"hf_papers {day}: {e}"})
            continue

        if not isinstance(papers, list):
            continue

        for p in papers:
            paper = p.get("paper", {})
            pid = paper.get("id", "")  # arxiv id e.g. "2609.09143"
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            upvotes = paper.get("upvotes", 0) or 0
            if upvotes < min_upvotes:
                continue

            title = p.get("title") or paper.get("title", "")
            # 优先用 ai_summary（更简洁），fallback 到 summary
            abstract = (paper.get("ai_summary") or paper.get("summary") or "")[:400]
            arxiv_url = f"https://arxiv.org/abs/{pid}"

            text = f"{title} {abstract}"
            # 关键词过滤（与 arxiv 一致）
            if all_re and not all_re.search(text):
                continue
            domains = tag_domains(text, per_domain)
            if excl_re and excl_re.search(text) and not domains:
                continue

            out.append({
                "source": "hf_papers",
                "hf_date": day,
                "upvotes": upvotes,
                "title": title,
                "url": arxiv_url,
                "abstract": abstract,
                "ai_keywords": paper.get("ai_keywords") or [],
                "github_repo": paper.get("githubRepo") or "",
                "domains": domains,
            })

    # 按 upvotes 降序排列，最热的在前
    out_items = [x for x in out if "_error" not in x]
    out_errs  = [x for x in out if "_error" in x]
    out_items.sort(key=lambda x: x.get("upvotes", 0), reverse=True)
    return out_errs + out_items


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
    spec = _apply_shared_config(args.channel, spec)
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
        "hf_papers": [],
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
        hfp = fetch_hf_papers(all_re, per_domain, excl_re)
        raw["hf_papers"] = [x for x in hfp if "_error" not in x]
        raw["errors"] += [x["_error"] for x in hfp if "_error" in x]
    except Exception as e:
        raw["errors"].append(f"hf_papers outer: {e}")

    try:
        rss = fetch_rss(all_re, per_domain, excl_re, spec.get("rss_feeds", []))
        raw["rss"] = [x for x in rss if "_error" not in x]
        raw["errors"] += [x["_error"] for x in rss if "_error" in x]
    except Exception as e:
        raw["errors"].append(f"rss outer: {e}")

    try:
        broad_re = CN_INFRA_RE if args.channel == "ai-infra" else CN_ROBOT_RE
        cn_rss = fetch_rss(all_re, per_domain, excl_re, spec.get("cn_rss_feeds", []), cn_mode=True, broad_re=broad_re)
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
        "hf_papers": len(raw["hf_papers"]),
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
