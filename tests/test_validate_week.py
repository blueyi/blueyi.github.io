import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "feeds" / "_engine" / "scripts" / "validate_week.py"
SPEC = importlib.util.spec_from_file_location("validate_week", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validate_week = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_week)


def valid_doc(channel="ai-infra"):
    count = 8 if channel == "ai-infra" else 7
    domains = [{"id": f"d{i}", "items": []} for i in range(count)]
    domains[0]["items"] = [{"title": "News", "summary": "Impact", "url": "https://example.com/news"}]
    return {"channel": channel, "week": "2026-W45", "curated": {
        "domains": domains,
        "highlights": ["one", "two", "three"],
        "industry": {}
    }}


def test_valid_weekly_document():
    assert validate_week.validate_weekly("ai-infra", valid_doc())


def test_rejects_more_than_five_highlights():
    doc = valid_doc(); doc["curated"]["highlights"] = list("123456")
    try: validate_week.validate_weekly("ai-infra", doc)
    except ValueError as exc: assert "3-5" in str(exc)
    else: raise AssertionError("excessive highlights must fail")


def test_rejects_missing_summary():
    doc=valid_doc(); doc["curated"]["domains"][0]["items"][0]["summary"]=""
    try: validate_week.validate_weekly("ai-infra",doc)
    except ValueError as exc: assert "title and summary" in str(exc)
    else: raise AssertionError("missing summary must fail")


def test_rejects_duplicate_urls():
    doc=valid_doc(); doc["curated"]["domains"][1]["items"]=[dict(doc["curated"]["domains"][0]["items"][0])]
    try: validate_week.validate_weekly("ai-infra",doc)
    except ValueError as exc: assert "duplicate" in str(exc)
    else: raise AssertionError("duplicate URL must fail")


def test_rejects_operational_status():
    doc=valid_doc(); doc["curated"]["highlights"][1]="PUBLISH: job succeeded"
    try: validate_week.validate_weekly("ai-infra",doc)
    except ValueError as exc: assert "operational" in str(exc)
    else: raise AssertionError("status text must fail")


def test_rejects_channel_mismatch():
    doc=valid_doc("embodied-ai")
    try: validate_week.validate_weekly("ai-infra",doc)
    except ValueError as exc: assert "channel mismatch" in str(exc)
    else: raise AssertionError("cross-channel document must fail")
