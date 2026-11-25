import importlib.util
from pathlib import Path

MODULE = Path(__file__).parents[1] / "_engine" / "build_search_index.py"
SPEC = importlib.util.spec_from_file_location("build_search_index", MODULE)
index = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(index)


def test_collapse_keeps_the_newest_url():
    entries = [
        {"type": "daily", "date": "2026-11-01", "week": "", "title": "Old", "summary": "a",
         "url": "https://www.example.com/story?utm_source=x", "page": "/daily/2026-11-01.html"},
        {"type": "daily", "date": "2026-11-20", "week": "", "title": "New", "summary": "longer summary",
         "url": "https://example.com/story", "page": "/daily/2026-11-20.html"},
        {"type": "weekly", "date": "", "week": "2026-W45", "title": "Week", "summary": "w",
         "url": "", "page": "/feeds/ai-infra/weeks/2026-W45.html"},
    ]
    collapsed = index.collapse_entries(entries)
    urls = [item["url"] for item in collapsed if item["url"]]
    assert urls == ["https://example.com/story"]
    assert collapsed[0]["title"] == "New"
    assert collapsed[0]["sort_date"] == "2026-11-20"
    assert any(item["title"] == "Week" for item in collapsed)
