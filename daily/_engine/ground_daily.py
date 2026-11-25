"""Ground a daily digest in that day's prefetch JSON and recent issues."""
import json
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
import sys

ENGINE = Path(__file__).resolve().parent
REPO = ENGINE.parent.parent
sys.path.insert(0, str(REPO / "_engine"))
sys.path.insert(0, str(ENGINE))

from text_match import normalize_url  # noqa: E402
import render_daily  # noqa: E402

_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)")
_FIGURE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:%|％)"
    r"|(\d+(?:\.\d+)?)\s*(万亿|亿|万)"
)
_REPEAT_RATIO = 0.82


def prefetch_urls(payload):
    found = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("url", "hn_url") and isinstance(value, str):
                    norm = normalize_url(value)
                    if norm:
                        found.add(norm)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found


def cited_urls(markdown):
    return [match.group(1).strip() for match in _LINK_RE.finditer(markdown or "")]


def _source_blob(payload, urls):
    wanted = set(urls)
    blobs = []

    def walk(node):
        if isinstance(node, dict):
            raw = node.get("url") or node.get("hn_url") or ""
            if raw and normalize_url(str(raw)) in wanted:
                blobs.append(json.dumps(node, ensure_ascii=False))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return "\n".join(blobs)


def _figures(text):
    claims = []
    for match in _FIGURE_RE.finditer(text or ""):
        if match.group(1) is not None:
            claims.append(("pct", match.group(1), ""))
        else:
            claims.append(("amount", match.group(2), match.group(3)))
    return claims


def _figure_supported(kind, value, unit, source):
    compact = source.replace(",", "").replace(" ", "")
    if kind == "pct":
        return re.search(rf"(?<!\d){re.escape(value)}\s*(?:%|％|percent\b)", source, re.I) is not None \
            or re.search(rf"(?<!\d){re.escape(value)}(?:%|％)", compact, re.I) is not None
    if value not in compact:
        return False
    if unit == "万亿":
        return re.search(r"万亿|trillion", source, re.I) is not None
    if unit == "亿":
        return re.search(r"亿|billion", source, re.I) is not None
    if unit == "万":
        return "万" in source
    return False


def _new_figure(summary, prior_blob):
    for kind, value, unit in _figures(summary):
        if not _figure_supported(kind, value, unit, prior_blob):
            return True
    return False


def has_new_fact(summary, prior_summaries):
    summary = (summary or "").strip()
    priors = [item.strip() for item in prior_summaries if item and item.strip()]
    if not summary or not priors:
        return True
    if _new_figure(summary, "\n".join(priors)):
        return True
    ratio = max(SequenceMatcher(None, summary, prior).ratio() for prior in priors)
    return ratio < _REPEAT_RATIO


def prior_summaries(data_dir, today, days=14):
    """Map normalized URL -> summaries published in the previous ``days`` days."""
    end = datetime.strptime(today, "%Y-%m-%d").date()
    start = end - timedelta(days=days)
    found = {}
    data_dir = Path(data_dir)
    if not data_dir.exists():
        return found
    for path in sorted(data_dir.glob("*.md")):
        try:
            published = datetime.strptime(path.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (start <= published < end):
            continue
        doc = render_daily.parse(path.read_text(encoding="utf-8"))
        for domain in doc["domains"]:
            for item in domain["items"]:
                url = normalize_url(item.get("url") or "")
                summary = (item.get("summary") or item.get("title") or "").strip()
                if url and summary:
                    found.setdefault(url, []).append(summary)
    return found


def ground_digest(markdown, date, prefetch, data_dir):
    """Raise ValueError when today's digest is not supported by prefetch or repeats an old item."""
    if not isinstance(prefetch, dict):
        raise ValueError(f"{date}: prefetch JSON is missing. 只能根据当日 prefetch JSON 写日报。")
    if prefetch.get("date") not in (None, date):
        raise ValueError(
            f"{date}: prefetch date is {prefetch.get('date')!r}. 只能使用当日 prefetch JSON。"
        )
    known = prefetch_urls(prefetch)
    unknown = []
    for url in cited_urls(markdown):
        if normalize_url(url) not in known:
            unknown.append(url)
    if unknown:
        sample = ", ".join(unknown[:5])
        raise ValueError(
            f"{date}: article URL is not in today's prefetch JSON: {sample}. "
            "只能从当日 prefetch JSON 里替换这条，不要新造 URL。"
        )

    doc = render_daily.parse(markdown)
    cited = {normalize_url(url) for url in cited_urls(markdown)}
    source = _source_blob(prefetch, cited)
    for highlight in doc["highlights"]:
        text = f"{highlight.get('title', '')} {highlight.get('summary', '')}"
        for kind, value, unit in _figures(text):
            if not _figure_supported(kind, value, unit, source):
                shown = f"{value}%" if kind == "pct" else f"{value}{unit}"
                raise ValueError(
                    f"{date}: highlight figure {shown} is not in the cited source summaries. "
                    "只能使用当日 prefetch JSON 来源摘要里出现的金额或百分比。"
                )

    priors = prior_summaries(data_dir, date)
    for domain in doc["domains"]:
        for item in domain["items"]:
            url = normalize_url(item.get("url") or "")
            text = f"{item.get('title', '')} {item.get('summary', '')}"
            blob = _source_blob(prefetch, {url}) if url else ""
            for kind, value, unit in _figures(text):
                if not _figure_supported(kind, value, unit, blob):
                    shown = f"{value}%" if kind == "pct" else f"{value}{unit}"
                    raise ValueError(
                        f"{date}: article figure {shown} is not in the prefetch summary for {item.get('url')}. "
                        "只能使用当日 prefetch JSON 来源摘要里出现的金额或百分比。"
                    )
            if not url or url not in priors:
                continue
            summary = (item.get("summary") or "").strip()
            if not has_new_fact(summary, priors[url]):
                raise ValueError(
                    f"{date}: {item.get('url')} repeated within 14 days without a new fact. "
                    "写明今日新增事实，或从当日 prefetch JSON 换一条。"
                )
    return True
