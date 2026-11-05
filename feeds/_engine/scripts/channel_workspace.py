#!/usr/bin/env python3
"""Run one feed prefetch in its channel-specific persistent worktree."""
import argparse
import datetime
import fcntl
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("/data/workspace/repos/blueyi.github.io")
BASE = Path.home() / ".cache/feeds-channel-worktrees"
LOCK_DIR = Path.home() / ".hermes/locks"


def run(args, cwd, check=True):
    p = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout or f"command failed: {args}").strip())
    return p


def channel_worktree(channel):
    BASE.mkdir(parents=True, exist_ok=True)
    path = BASE / channel
    if not path.exists():
        run(["git", "fetch", "origin", "master"], REPO)
        run(["git", "worktree", "add", "--detach", str(path), "origin/master"], REPO)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", required=True, choices=["ai-infra", "embodied-ai"])
    args = parser.parse_args()
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_DIR / f"feeds-prefetch-{args.channel}.lock"
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            worktree = channel_worktree(args.channel)
            # Rebase this channel's private checkout onto the latest published state.
            run(["git", "fetch", "origin", "master"], worktree)
            run(["git", "rebase", "origin/master"], worktree)
            publish_script = worktree / "feeds/_engine/scripts/publish_week.py"
            shutil.copy2(REPO / "feeds/_engine/scripts/publish_week.py", publish_script)
            cmd = [sys.executable, str(worktree / "feeds/_engine/scripts/prefetch.py"), "--channel", args.channel]
            p = subprocess.run(cmd, cwd=worktree, text=True, capture_output=True)
            sys.stdout.write(p.stdout)
            if p.returncode:
                sys.stderr.write(p.stderr)
                return p.returncode
            # Emit deterministic path for the editor/publisher agent.
            now = datetime.datetime.now().astimezone()
            year, week, _ = now.isocalendar()
            data = worktree / "feeds" / args.channel / "data" / f"{year}-W{week:02d}.json"
            print(f"\nPUBLISH_SOURCE={data}")
            print(f"PUBLISH_COMMAND=python3 {publish_script} --channel {args.channel} --week {year}-W{week:02d} --data {data}")
            return 0
        except Exception as exc:
            print(f"[feeds] {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
