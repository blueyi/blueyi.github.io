import importlib.util
from pathlib import Path

MODULE = Path(__file__).parents[1] / "_engine" / "text_match.py"
SPEC = importlib.util.spec_from_file_location("text_match", MODULE)
text_match = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(text_match)


def test_short_english_keywords_do_not_match_inside_words():
    pattern = text_match.compile_keywords(["roce", "ane", "rack", "tpu", "机器人"])
    assert pattern.search("Procedural Flowers in LaTeX") is None
    assert pattern.search("hyperbolic plane") is None
    assert pattern.search("planets orbiting") is None
    assert pattern.search("multitrack audio editor") is None
    assert pattern.search("line-buffered output") is None
    assert pattern.search("RoCE fabric")
    assert pattern.search("TPU pod")
    assert pattern.search("工业机器人")


def test_clean_xml_text_strips_markup_and_collapses_whitespace():
    raw = "<script>bad()</script><meta charset='utf-8'><p>Hello\n  world</p>"
    assert text_match.clean_xml_text(raw) == "Hello world"


def test_cs_lg_requires_a_keyword_hit():
    pattern = text_match.compile_keywords(["vllm"])
    assert text_match.arxiv_category_allowed("cs.LG", "Serving with vLLM", pattern)
    assert not text_match.arxiv_category_allowed("cs.LG", "A new optimizer", pattern)
    assert text_match.arxiv_category_allowed("cs.DC", "A new optimizer", pattern)


def test_normalize_url_drops_tracking_and_www():
    assert text_match.normalize_url("https://www.Example.com/a/?utm_source=x&id=1") == \
        "https://example.com/a?id=1"
