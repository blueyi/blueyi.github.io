import importlib.util
from pathlib import Path

MODULE = Path(__file__).parents[1] / "daily" / "_engine" / "ground_daily.py"
SPEC = importlib.util.spec_from_file_location("ground_daily", MODULE)
ground = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ground)


PREFETCH = {
    "date": "2026-11-25",
    "hn": [{
        "title": "Chip story",
        "url": "https://example.com/chip",
        "summary": "Revenue rose 13% and the package is quoted at 6200亿美元.",
    }],
}


def digest(body, highlights):
    lines = ["# Daily", "## 1️⃣ AI 芯片", body, "## 🌟 今日亮点", *highlights]
    return "\n".join(lines) + "\n"


def test_accepts_url_and_figure_present_in_prefetch(tmp_path):
    md = digest(
        "- **Chip**: revenue [source](https://example.com/chip)",
        ["1. revenue rose 13%", "2. second", "3. third"],
    )
    assert ground.ground_digest(md, "2026-11-25", PREFETCH, tmp_path)


def test_rejects_url_missing_from_prefetch(tmp_path):
    md = digest(
        "- **Chip**: revenue [source](https://example.com/invented)",
        ["1. one", "2. two", "3. three"],
    )
    try:
        ground.ground_digest(md, "2026-11-25", PREFETCH, tmp_path)
    except ValueError as exc:
        assert "不要新造 URL" in str(exc)
    else:
        raise AssertionError("unknown URL must fail")


def test_rejects_highlight_figure_missing_from_source(tmp_path):
    md = digest(
        "- **Chip**: revenue [source](https://example.com/chip)",
        ["1. market cap fell 3万亿", "2. second", "3. third"],
    )
    try:
        ground.ground_digest(md, "2026-11-25", PREFETCH, tmp_path)
    except ValueError as exc:
        assert "3万亿" in str(exc)
    else:
        raise AssertionError("ungrounded highlight figure must fail")


def test_repeated_url_needs_a_new_fact(tmp_path):
    prior = tmp_path / "2026-11-20.md"
    prior.write_text(digest(
        "- **Chip**: revenue rose 13% [source](https://example.com/chip)",
        ["1. one", "2. two", "3. three"],
    ), encoding="utf-8")
    same = digest(
        "- **Chip**: revenue rose 13% [source](https://example.com/chip)",
        ["1. revenue rose 13%", "2. second", "3. third"],
    )
    try:
        ground.ground_digest(same, "2026-11-25", PREFETCH, tmp_path)
    except ValueError as exc:
        assert "new fact" in str(exc)
    else:
        raise AssertionError("unchanged repeat must fail")

    updated = digest(
        "- **Chip**: board named an interim operator today [source](https://example.com/chip)",
        ["1. revenue rose 13%", "2. second", "3. third"],
    )
    assert ground.ground_digest(updated, "2026-11-25", PREFETCH, tmp_path)
