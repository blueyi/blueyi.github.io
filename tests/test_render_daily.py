import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "daily" / "_engine" / "render_daily.py"
SPEC = importlib.util.spec_from_file_location("render_daily", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
render_daily = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_daily)


def test_highlights_stop_at_separator_and_ignore_status_bullets():
    md = """# Daily
## 1 AI chip
- **Chip news**: summary
## 🌟 今日亮点
1. **Chip news**: impact
2. **Infra news**: impact
3. **Compiler news**: impact

---
### Status report
- **PREFETCH**: ok
- **PUBLISH**: done
"""
    doc = render_daily.parse(md)
    assert [item["title"] for item in doc["highlights"]] == [
        "Chip news",
        "Infra news",
        "Compiler news",
    ]
