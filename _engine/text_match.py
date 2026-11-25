"""Keyword matching and feed-text cleaning shared by the daily and weekly prefetchers."""
import html
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_CJK = re.compile(r"[\u3400-\u9fff]")
_ALNUM = re.compile(r"[A-Za-z0-9]")


def compile_keywords(keywords):
    """Compile a keyword list.

    Latin and numeric keywords match on token boundaries so short stems such as
    ``roce`` or ``tpu`` do not fire inside ordinary English words. Keywords that
    contain CJK characters stay substring matches.
    """
    parts = []
    for raw in keywords or []:
        keyword = str(raw).strip()
        if not keyword:
            continue
        escaped = re.escape(keyword)
        if _ALNUM.search(keyword) and not _CJK.search(keyword):
            parts.append(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])")
        else:
            parts.append(escaped)
    if not parts:
        return None
    return re.compile("|".join(parts), re.I)


def arxiv_category_allowed(category, text, keyword_re):
    """cs.LG is only kept when the infra/channel keywords hit. Other cats pass through."""
    if category != "cs.LG":
        return True
    return bool(keyword_re and keyword_re.search(text or ""))


def clean_xml_text(value):
    """Strip markup and collapse whitespace from an RSS/Atom text node."""
    text = (value or "").replace("<![CDATA[", "").replace("]]>", "")
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<meta\b[^>]*>", " ", text)
    text = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(re.sub(r"\s+", " ", text).strip())


def normalize_url(url):
    """Canonical form for grounding and search de-duplication."""
    raw = (url or "").replace("&amp;", "&").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return raw
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = urlencode(
        [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
         if not key.lower().startswith("utm_")]
    )
    return urlunparse((parsed.scheme.lower(), host, parsed.path.rstrip("/"), "", query, ""))
