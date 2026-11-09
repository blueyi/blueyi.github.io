import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "feeds" / "_engine" / "scripts" / "rebuild_index.py"
SPEC = importlib.util.spec_from_file_location("rebuild_index", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
rebuild_index = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rebuild_index)


def test_week_highlight_normalizes_legacy_object():
    doc = {"curated": {"highlights": [{"title": "Paper", "summary": "Impact", "url": "https://example.com"}]}}
    assert rebuild_index.week_highlight(doc) == "Paper：Impact"


def test_week_highlight_uses_string_as_is():
    assert rebuild_index.week_highlight({"curated": {"highlights": ["Editorial highlight"]}}) == "Editorial highlight"
