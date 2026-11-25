"""Git publish helpers shared by the daily and weekly automation publishers."""
import sys
from pathlib import Path


def rebase_and_refresh_search_index(run, cwd, git_prefix):
    """Rebase onto origin/master and rebuild search-index.json instead of merging it.

    The daily job (08:00 HKT) and the Saturday weekly job both commit this file.
    Cloud automations do not share a filesystem lock, so a rebase is the race
    control. A JSON merge of the index is not meaningful; the index is derived
    from daily/ and feeds/ after those trees are combined.
    """
    cwd = Path(cwd)
    rebase = run(["git", "rebase", "origin/master"], cwd, False)
    if rebase.returncode != 0:
        unmerged = run(["git", "diff", "--name-only", "--diff-filter=U"], cwd, False)
        names = [line.strip() for line in (unmerged.stdout or "").splitlines() if line.strip()]
        other = [name for name in names if name != "search-index.json"]
        if other or not names:
            run(["git", "rebase", "--abort"], cwd, False)
            detail = (rebase.stderr or rebase.stdout or "git rebase failed").strip()
            raise RuntimeError(detail)
        run(["git", "checkout", "--ours", "--", "search-index.json"], cwd, True)
        run(["git", "add", "--", "search-index.json"], cwd, True)
        continued = run(["git", "-c", "core.editor=true", "rebase", "--continue"], cwd, False)
        if continued.returncode != 0:
            run(["git", "rebase", "--abort"], cwd, False)
            detail = (continued.stderr or continued.stdout or "git rebase --continue failed").strip()
            raise RuntimeError(detail)

    script = cwd / "_engine" / "build_search_index.py"
    if script.exists():
        run([sys.executable, str(script)], cwd, True)
    run(["git", "add", "--", "search-index.json"], cwd, True)
    staged = run(["git", "diff", "--cached", "--quiet"], cwd, False)
    if staged.returncode != 0:
        run([*git_prefix(cwd), "commit", "--amend", "--no-edit"], cwd, True)
