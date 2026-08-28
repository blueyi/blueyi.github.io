#!/usr/bin/env python3
"""publish_daily.py — 把 ai-infra-daily-news cron 的最新投递快照发布到 daily/ 站。

流程：
1. 找 ~/.hermes/cron/output/5b1b9320afe7_*.txt 最新一份
2. 从文件名提取日期，剥离头尾得到干净 markdown
3. 若 data/<date>.md 已存在且内容相同 -> 无变化，静默退出（exit 0，无 stdout）
4. 写 data/<date>.md，render + rebuild
5. git add/commit/pull --rebase/push（origin 双远程同推）
6. stdout 输出一行摘要（日期 + commit SHA），供 cron 投递

仅用 Python 标准库 + subprocess。幂等：同一天重跑不产生重复提交。
"""
import glob
import os
import re
import subprocess
import sys
from pathlib import Path

DAILY_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = DAILY_DIR.parent
DATA_DIR = DAILY_DIR / "data"
SNAPSHOT_GLOB = os.path.expanduser("~/.hermes/cron/output/5b1b9320afe7_*.txt")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_daily  # noqa: E402
import rebuild_daily  # noqa: E402


def latest_snapshot():
    files = sorted(glob.glob(SNAPSHOT_GLOB))
    if not files:
        return None, None
    return files[-1], os.path.basename(files[-1])


def clean_markdown(raw: str) -> str:
    lines = raw.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("# "))
    end = next((i for i, l in enumerate(lines)
                if l.startswith("To stop or manage this job")), len(lines))
    return "\n".join(lines[start:end]).strip() + "\n"


def run(cmd, cwd):
    """运行 shell 命令，返回 (returncode, stdout)。用 list 避免 shell 注入。"""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout or "").strip()


def main():
    snap_path, snap_name = latest_snapshot()
    if not snap_path or not snap_name:
        print("[daily] no digest snapshot found; nothing to publish", file=sys.stderr)
        return 1
    m = re.search(r"_(\d{8})_", snap_name)
    if not m:
        print(f"[daily] cannot parse date from snapshot name {snap_name}", file=sys.stderr)
        return 1
    date = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}"
    clean = clean_markdown(open(snap_path, encoding="utf-8").read())

    target = DATA_DIR / f"{date}.md"
    if target.exists() and target.read_text(encoding="utf-8") == clean:
        # 已发布且内容一致 -> 静默，无输出，exit 0
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(clean, encoding="utf-8")
    (DAILY_DIR / f"{date}.html").write_text(render_daily.render(date), encoding="utf-8")
    rebuild_daily.main()

    # git add -> commit -> pull --rebase -> push（顺序不可颠倒；分号语义，逐条判码）
    rc, _ = run(["git", "add", "daily/", "index.html"], REPO_DIR)
    if rc != 0:
        print("[daily] git add failed", file=sys.stderr)
        return 1
    rc, _ = run(["git", "commit", "-q", "-m", f"daily: {date} AI Infra daily digest"], REPO_DIR)
    if rc != 0:
        print("[daily] git commit failed (nothing changed?)", file=sys.stderr)
        return 1
    rc, _ = run(["git", "pull", "--rebase", "-q", "origin", "master"], REPO_DIR)
    if rc != 0:
        print("[daily] git pull --rebase failed", file=sys.stderr)
        return 1
    rc, _ = run(["git", "push", "-q", "origin", "master"], REPO_DIR)
    if rc != 0:
        print("[daily] git push failed", file=sys.stderr)
        return 1
    rc, sha = run(["git", "rev-parse", "--short", "HEAD"], REPO_DIR)
    print(f"[daily] published {date} -> {sha}  (https://yulong.wang/daily/)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
