#!/usr/bin/env python3
"""Run feed prefetch in an isolated channel worktree and emit bounded context."""
import argparse
import datetime
import fcntl
import json
import subprocess
import sys
from pathlib import Path

REPO = Path("/data/workspace/repos/blueyi.github.io")
BASE = Path.home() / ".cache/feeds-channel-worktrees"
LOCK_DIR = Path.home() / ".hermes/locks"


def run(args, cwd, check=True):
    p = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout or f"command failed: {args}").strip())
    return p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", required=True, choices=["ai-infra", "embodied-ai"])
    args = parser.parse_args()
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_DIR / f"feeds-prefetch-{args.channel}.lock"
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            worktree = BASE / args.channel
            if not worktree.exists():
                BASE.mkdir(parents=True, exist_ok=True)
                run(["git", "fetch", "origin", "master"], REPO)
                run(["git", "worktree", "add", "--detach", str(worktree), "origin/master"], REPO)
            status = run(["git", "status", "--porcelain"], worktree).stdout.strip()
            if not status:
                run(["git", "fetch", "origin", "master"], worktree)
                run(["git", "merge", "--ff-only", "origin/master"], worktree)
            cmd = [sys.executable, str(worktree / "feeds/_engine/scripts/prefetch.py"), "--channel", args.channel]
            p = subprocess.run(cmd, cwd=worktree, text=True, capture_output=True)
            if p.returncode:
                sys.stderr.write(p.stderr)
                print(json.dumps({"STATUS": "prefetch_failed", "channel": args.channel,
                                  "error": p.stderr.strip()}, ensure_ascii=False), file=sys.stderr)
                return p.returncode
            today = datetime.date.today().isocalendar()
            source = worktree / "feeds" / args.channel / "data" / f"{today.year}-W{today.week:02d}.json"
            raw = json.loads(source.read_text(encoding="utf-8"))["raw"]
            week = raw["week"]
            print(json.dumps({"STATUS": "prefetched", "channel": args.channel, "week": week,
                              "counts": raw.get("counts", {}), "errors": raw.get("errors", []),
                              "data_file": str(source)}, ensure_ascii=False))
            print(f"PUBLISH_SOURCE={source}")
            print(f"PUBLISH_COMMAND=python3 {Path.home()}/.hermes/scripts/feeds_publish_week.py --channel {args.channel} --week {week} --data {source}")
            return 0
        except Exception as exc:
            print(json.dumps({"STATUS": "prefetch_failed", "channel": args.channel,
                              "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
