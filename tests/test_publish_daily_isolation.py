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
