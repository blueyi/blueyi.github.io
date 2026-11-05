#!/usr/bin/env python3
"""Publish a curated weekly feed through a locked clean worktree."""
import argparse
import fcntl
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path("/data/workspace/repos/blueyi.github.io")
LOCK = Path.home() / ".hermes/locks/blueyi-pages-publish.lock"
BASE = Path.home() / ".cache/feeds-publish-worktrees"


def run(args, cwd, check=True):
    p = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout or f"command failed: {args}").strip())
    return p


def publish(channel, week, source_data):
    source_data = Path(source_data).resolve()
    doc = json.loads(source_data.read_text(encoding="utf-8"))
    if doc.get("week") != week or doc.get("channel") != channel:
        raise RuntimeError("channel/week mismatch in curated source")
    curated = doc.get("curated") or {}
    if not curated.get("domains") or not curated.get("highlights"):
        raise RuntimeError("curated content is incomplete")

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    BASE.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run(["git", "fetch", "origin", "master"], REPO)
        path = Path(tempfile.mkdtemp(prefix=f"{channel}-{week}-", dir=BASE))
        try:
            run(["git", "worktree", "add", "--detach", str(path), "origin/master"], REPO)
            data = path / "feeds" / channel / "data" / f"{week}.json"
            data.parent.mkdir(parents=True, exist_ok=True)
            data.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            run([sys.executable, "feeds/_engine/scripts/render_week.py", "--channel", channel, "--week", week], path)
            run([sys.executable, "feeds/_engine/scripts/rebuild_index.py"], path)
            allowed = [f"feeds/{channel}/data/{week}.json", f"feeds/{channel}/weeks/{week}.html",
                       f"feeds/{channel}/index.html", f"feeds/{channel}/manifest.json",
                       "feeds/index.html", "search-index.json"]
            run(["git", "add", "--", *allowed], path)
            staged = run(["git", "diff", "--cached", "--name-only"], path).stdout.splitlines()
            if not staged:
                print(f"[feeds] {channel} {week}: no changes")
                return 0
            unexpected = sorted(set(staged) - set(allowed))
            if unexpected:
                raise RuntimeError(f"unexpected staged paths: {unexpected}")
            current_branch = run(["git", "branch", "--show-current"], path).stdout.strip()
            run(["git", "commit", "-m", f"feeds({channel}): {week} weekly"], path)
            pushed = False
            push = None
            for _attempt in range(3):
                push = run(["git", "push", "origin", "HEAD:master"], path, False)
                if push.returncode == 0:
                    pushed = True
                    break
                # Another publisher advanced master. Rebase this exact scoped commit and retry.
                run(["git", "fetch", "origin", "master"], path)
                run(["git", "rebase", "origin/master"], path)
            if not pushed:
                detail = "git push failed" if push is None else (push.stderr or push.stdout or "git push failed").strip()
                raise RuntimeError(detail)
            url = f"https://yulong.wang/feeds/{channel}/weeks/{week}.html"
            for _ in range(18):
                time.sleep(10)
                r = run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-L", url], path, False)
                if r.stdout.strip() == "200":
                    print(f"[feeds] published {channel} {week}: {url} HTTP 200")
                    return 0
            raise RuntimeError(f"deployment check timed out: {url}")
        finally:
            run(["git", "worktree", "remove", "--force", str(path)], REPO, False)
            shutil.rmtree(path, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", required=True, choices=["ai-infra", "embodied-ai"])
    parser.add_argument("--week", required=True)
    parser.add_argument("--data", required=True)
    args = parser.parse_args()
    try:
        return publish(args.channel, args.week, args.data)
    except Exception as exc:
        print(f"[feeds] publish failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
