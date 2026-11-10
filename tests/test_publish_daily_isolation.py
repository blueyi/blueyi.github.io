import importlib.util
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "daily" / "_engine" / "publish_daily.py"
SPEC = importlib.util.spec_from_file_location("publish_daily", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
publish_daily = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish_daily)


def test_daily_and_feeds_share_global_publish_lock():
    assert publish_daily.LOCK_PATH == Path.home() / ".hermes/locks/blueyi-pages-publish.lock"


def test_worker_requires_today_snapshot(monkeypatch):
    monkeypatch.setattr(publish_daily, "snapshots_by_date", lambda: {})
    try:
        publish_daily.worker_main()
    except RuntimeError as exc:
        assert "no daily news snapshot" in str(exc)
    else:
        raise AssertionError("worker must fail when today's snapshot is missing")

def test_validate_digest_rejects_operational_status():
    md = """# Daily
## 1️⃣ AI 芯片
- **News**: summary
## 🌟 今日亮点
1. **News**: impact
2. **News 2**: impact
3. **News 3**: impact
### 状态报告
- **PUBLISH**: done
"""
    try:
        publish_daily.validate_digest(md, "2026-11-09")
    except ValueError as exc:
        assert "operational status" in str(exc)
    else:
        raise AssertionError("operational status must be rejected")


def test_validate_digest_requires_three_to_five_highlights():
    md = """# Daily
## 1️⃣ AI 芯片
- **News**: summary
## 🌟 今日亮点
1. **News**: impact
2. **News 2**: impact
"""
    try:
        publish_daily.validate_digest(md, "2026-11-09")
    except ValueError as exc:
        assert "expected 3-5" in str(exc)
    else:
        raise AssertionError("too few highlights must be rejected")


def test_validate_digest_requires_article_summaries_for_new_digest():
    md = """# Daily
## 1️⃣ AI 芯片
- **Title only**
## 🌟 今日亮点
1. **News**: impact
2. **News 2**: impact
3. **News 3**: impact
"""
    try:
        publish_daily.validate_digest(md, "2026-11-09")
    except ValueError as exc:
        assert "article summaries are required" in str(exc)
    else:
        raise AssertionError("missing article summary must be rejected")


def test_historical_status_snapshot_does_not_block_today(monkeypatch, tmp_path):
    class FrozenDateTime:
        @classmethod
        def now(cls):
            from datetime import datetime
            return datetime(2026, 11, 10, 9, 0)

    old_snapshot = tmp_path / "snapshot_20261109.txt"
    old_snapshot.write_text("# Old\n## 状态报告\n- **PUBLISH**: done\n", encoding="utf-8")
    today_snapshot = tmp_path / "snapshot_20261110.txt"
    today_snapshot.write_text("""# Daily
## 1️⃣ AI 芯片
- **News**: summary
## 🌟 今日亮点
1. **News**: impact
2. **News 2**: impact
3. **News 3**: impact
""", encoding="utf-8")
    data_dir = tmp_path / "data"
    daily_dir = tmp_path / "daily"
    data_dir.mkdir()
    daily_dir.mkdir()
    (data_dir / "2026-11-09.md").write_text("# Published historical digest\n", encoding="utf-8")
    (daily_dir / "2026-11-09.html").write_text("<html>", encoding="utf-8")
    monkeypatch.setattr(publish_daily, "datetime", FrozenDateTime)
    monkeypatch.setattr(publish_daily, "snapshots_by_date", lambda: {
        "2026-11-09": str(old_snapshot), "2026-11-10": str(today_snapshot)
    })
    monkeypatch.setattr(publish_daily, "DATA_DIR", data_dir)
    monkeypatch.setattr(publish_daily, "DAILY_DIR", daily_dir)
    monkeypatch.setattr(publish_daily.render_daily, "DATA_DIR", data_dir)
    monkeypatch.setattr(publish_daily, "rebuild_daily", type("R", (), {"main": staticmethod(lambda: None)}))
    monkeypatch.setattr(publish_daily, "publish_commit", lambda latest, dates: "testsha")
    monkeypatch.setattr(publish_daily, "verify_deployment", lambda latest: True)
    monkeypatch.setattr(publish_daily, "run", lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "200", ""))
    monkeypatch.setattr(publish_daily.time, "sleep", lambda _: None)
    assert publish_daily.worker_main() == 0
    assert (data_dir / "2026-11-09.md").read_text() == "# Published historical digest\n"


def test_publish_retries_after_remote_fast_forward(monkeypatch, tmp_path):
    calls = []
    outcomes = [1, 0]

    def fake_run(cmd, cwd, check=True):
        calls.append(cmd)
        if cmd[:3] == ["git", "diff", "--cached"]:
            return subprocess.CompletedProcess(cmd, 1, "", "")
        if cmd[:2] == ["git", "push"]:
            rc = outcomes.pop(0)
            return subprocess.CompletedProcess(cmd, rc, "", "non-fast-forward" if rc else "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(publish_daily, "run", fake_run)
    monkeypatch.setattr(publish_daily, "REPO_DIR", tmp_path)
    publish_daily.publish_commit("2026-11-05", ["2026-11-05"])

    assert sum(call[:2] == ["git", "push"] for call in calls) == 2
    assert ["git", "fetch", "origin", "master"] in calls
    assert ["git", "rebase", "origin/master"] in calls
