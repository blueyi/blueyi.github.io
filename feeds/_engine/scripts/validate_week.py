#!/usr/bin/env python3
"""Validate curated weekly feed documents before rendering or publishing."""
import re
from urllib.parse import urlparse

OPERATIONAL = re.compile(
    r"(?im)(?:^|\n)\s*(?:[-*]\s*)?(?:PREFETCH|CURATION|PUBLISH|DEPLOY|DELIVERY)\s*[:=]\s*|"
    r"状态报告|cron job|http_status|exit code"
)


def validate_weekly(channel, doc, require_grounding=False):
    if not isinstance(doc, dict) or doc.get("channel") != channel:
        raise ValueError(f"channel mismatch: expected {channel}")
    week = str(doc.get("week", ""))
    if not re.fullmatch(r"\d{4}-W\d{2}", week):
        raise ValueError(f"invalid ISO week: {week!r}")
    curated = doc.get("curated")
    if not isinstance(curated, dict):
        raise ValueError("curated content is missing")
    domains = curated.get("domains")
    expected = 8 if channel == "ai-infra" else 7
    if not isinstance(domains, list) or len(domains) != expected:
        raise ValueError(f"expected {expected} domains, got {len(domains) if isinstance(domains,list) else 'invalid'}")
    # Early issues used display-only domains without stable ids.
    if all(isinstance(d, dict) and not d.get("id") for d in domains):
        ids = [f"legacy-{i}" for i in range(expected)]
    else:
        ids = [d.get("id") for d in domains if isinstance(d, dict)]
    if len(ids) != expected or len(set(ids)) != expected:
        raise ValueError("domain definitions are invalid or duplicated")
    highlights = curated.get("highlights")
    if not isinstance(highlights, list) or not 3 <= len(highlights) <= 5:
        raise ValueError("expected 3-5 curated weekly highlights")
    if any(not isinstance(item, str) or not item.strip() for item in highlights):
        raise ValueError("highlights must be non-empty editorial strings")
    text = "\n".join(highlights)
    if OPERATIONAL.search(text):
        raise ValueError("operational status must not appear in editorial highlights")

    raw = doc.get("raw") or {}
    raw_urls = set()
    for key in ("hn", "arxiv", "hf_papers", "rss", "cn_rss"):
        for entry in raw.get(key, []) or []:
            if entry.get("url"):
                raw_urls.add(str(entry["url"]).replace("&amp;", "&"))
    seen_urls = set()
    for domain in domains:
        for item in domain.get("items", []):
            if not isinstance(item, dict):
                raise ValueError(f"invalid item in {domain.get('id')}")
            title = str(item.get("title", "")).strip()
            summary = str(item.get("summary", "")).strip()
            url = str(item.get("url", "")).strip()
            parsed = urlparse(url)
            if not title or not summary:
                raise ValueError(f"title and summary are required in {domain.get('id')}")
            if re.search(r"(?is)<(?:meta|script|style|html|body)\b|<!--", summary):
                raise ValueError(f"summary contains scraped HTML in {domain.get('id')}")
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError(f"invalid article URL in {domain.get('id')}: {url!r}")
            if url in seen_urls:
                raise ValueError(f"duplicate article URL: {url}")
            if require_grounding and url.replace("&amp;", "&") not in raw_urls:
                raise ValueError(f"article URL is not present in raw source data: {url}")
            seen_urls.add(url)
            if OPERATIONAL.search(title + "\n" + summary):
                raise ValueError("operational status must not appear in article content")

    for key, entries in (curated.get("industry") or {}).items():
        if key == "funding":
            for item in entries or []:
                if not item.get("title") or not item.get("summary"):
                    raise ValueError("industry funding entries require title and summary")
                url = str(item.get("url", ""))
                parsed = urlparse(url)
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    raise ValueError("industry funding entry has invalid URL")
                if url in seen_urls:
                    raise ValueError(f"duplicate article URL: {url}")
                if require_grounding and url.replace("&amp;", "&") not in raw_urls:
                    raise ValueError(f"industry URL is not present in raw source data: {url}")
                seen_urls.add(url)
    return True
