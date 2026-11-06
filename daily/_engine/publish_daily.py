#!/usr/bin/env python3
"""Publish AI Infra daily snapshots through an isolated Git worktree.

The parent process creates a clean worktree from origin/master. The worker then
backfills every missing/changed snapshot, rebuilds indexes, commits, pushes, and
verifies the newest page. This keeps unrelated feed jobs and conflicted files in
the shared checkout from breaking daily publication.
"""
import glob
import json
import os
import re
from datetime import datetime
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

IS_WORKER = os.environ.get("AI_INFRA_DAILY_WORKER") == "1"
SCRIPT_PATH = Path(__file__).resolve()
DAILY_DIR = SCRIPT_PATH.parent.parent
REPO_DIR = DAILY_DIR.parent
DATA_DIR = DAILY_DIR / "data"
SNAPSHOT_GLOB = os.path.expanduser("~/.hermes/cron/output/5b1b9320afe7_*.txt")
LOCK_PATH = Path.home() / ".hermes/locks/blueyi-pages-publish.lock"

sys.path.insert(0, str(SCRIPT_PATH.parent))
import render_daily  # noqa: E402
import rebuild_daily  # noqa: E402


def run(cmd, cwd, check=False):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        detail = (p.stderr or p.stdout or "unknown error").strip()
        raise RuntimeError(f"{' '.join(cmd)} failed: {detail}")
    return p


def snapshot_date(path):
    m = re.search(r"_(\d{8})_", os.path.basename(path)) or re.search(
        r"(\d{8})", os.path.basename(path)
    )
    if not m:
        return None
    value = m.group(1)
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def snapshots_by_date():
    snapshots = {}
    for path in sorted(glob.glob(SNAPSHOT_GLOB)):
        date = snapshot_date(path)
        if date:
            snapshots[date] = path
    return snapshots


def clean_markdown(raw):
    lines = raw.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith("# "))
    except StopIteration as exc:
        raise ValueError("snapshot has no markdown title") from exc
    end = next(
        (i for i, line in enumerate(lines) if line.startswith("To stop or manage this job")),
        len(lines),
    )
    return "\n".join(lines[start:end]).strip() + "\n"


def publish_commit(latest, changed_dates):
    run(["git", "add", "--", "daily/", "search-index.json"], REPO_DIR, check=True)
    if run(["git", "diff", "--cached", "--quiet"], REPO_DIR).returncode == 0:
        return run(["git", "rev-parse", "--short", "HEAD"], REPO_DIR, check=True).stdout.strip()

    message = f"daily: publish through {latest} AI Infra daily digest"
    run(["git", "commit", "-q", "-m", message], REPO_DIR, check=True)
    pushed = False
    push = None
    for _attempt in range(3):
        push = run(["git", "push", "origin", "HEAD:master"], REPO_DIR)
        if push.returncode == 0:
            pushed = True
            break
        run(["git", "fetch", "origin", "master"], REPO_DIR, check=True)
        run(["git", "rebase", "origin/master"], REPO_DIR, check=True)
    if not pushed:
        detail = "git push failed" if push is None else (push.stderr or push.stdout or "git push failed").strip()
        raise RuntimeError(detail)
    return run(["git", "rev-parse", "--short", "HEAD"], REPO_DIR, check=True).stdout.strip()


def worker_main():
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    snapshots = snapshots_by_date()
    if today not in snapshots:
        raise RuntimeError(f"no daily news snapshot for {today}")
    changed_dates = []
    for date, snap_path in snapshots_by_date().items():
        clean = clean_markdown(Path(snap_path).read_text(encoding="utf-8"))
        target = DATA_DIR / f"{date}.md"
        if target.exists() and target.read_text(encoding="utf-8") == clean:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(clean, encoding="utf-8")
        (DAILY_DIR / f"{date}.html").write_text(render_daily.render(date), encoding="utf-8")
        changed_dates.append(date)

    if not changed_dates:
        latest_available = max(snapshots) if snapshots else "none"
        print(f"[daily] STATUS=no_changes latest_available={latest_available}")
        return 0

    rebuild_daily.main()
    latest = max(changed_dates)
    sha = publish_commit(latest, changed_dates)

    url = f"https://yulong.wang/daily/{latest}.html"
    for _ in range(12):
        time.sleep(10)
        result = run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-L", url],
            REPO_DIR,
        )
        if result.stdout.strip() == "200":
            print(json.dumps({"STATUS": "published", "dates": changed_dates, "commit": sha,
                              "url": url, "http_status": 200}, ensure_ascii=False))
            return 0
    print(f"[daily] deployment verification failed for {url}", file=sys.stderr)
    return 1


def parent_main():
    import fcntl

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('[daily] STATUS=skipped reason=publish_lock_busy')
            return 0

        run(["git", "fetch", "-q", "origin", "master"], REPO_DIR, check=True)
        worktree = Path(tempfile.mkdtemp(prefix="ai-infra-daily-"))
        try:
            run(
                ["git", "worktree", "add", "-q", "--detach", str(worktree), "origin/master"],
                REPO_DIR,
                check=True,
            )
            worker_script = worktree / "daily/_engine/publish_daily.py"
            # Run the exact scheduler version being tested, even before this fix is pushed.
            shutil.copy2(SCRIPT_PATH, worker_script)
            env = os.environ.copy()
            env["AI_INFRA_DAILY_WORKER"] = "1"
            child = subprocess.run(
                [sys.executable, str(worker_script)],
                cwd=worktree,
                env=env,
                capture_output=True,
                text=True,
            )
            if child.stdout:
                sys.stdout.write(child.stdout)
            if child.stderr:
                sys.stderr.write(child.stderr)
            return child.returncode
        finally:
            run(["git", "worktree", "remove", "--force", str(worktree)], REPO_DIR)
            shutil.rmtree(worktree, ignore_errors=True)


def main():
    try:
        return worker_main() if IS_WORKER else parent_main()
    except Exception as exc:
        print(json.dumps({"STATUS": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
