import importlib.util
import subprocess
from pathlib import Path

MODULE = Path(__file__).parents[1] / "_engine" / "publish_git.py"
SPEC = importlib.util.spec_from_file_location("publish_git", MODULE)
publish_git = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish_git)


def _run(outcomes):
    calls = []

    def fake(cmd, cwd, check=False):
        calls.append(list(cmd))
        for prefix, result in outcomes:
            if list(cmd)[:len(prefix)] == prefix:
                return result
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return calls, fake


def test_search_index_conflict_is_rebuilt_not_merged(tmp_path):
    calls, fake = _run([
        (["git", "rebase", "origin/master"], subprocess.CompletedProcess([], 1, "", "conflict")),
        (["git", "diff", "--name-only", "--diff-filter=U"],
         subprocess.CompletedProcess([], 0, "search-index.json\n", "")),
        (["git", "diff", "--cached", "--quiet"], subprocess.CompletedProcess([], 0, "", "")),
    ])
    publish_git.rebase_and_refresh_search_index(fake, tmp_path, lambda cwd: ["git"])
    assert ["git", "checkout", "--ours", "--", "search-index.json"] in calls
    assert ["git", "-c", "core.editor=true", "rebase", "--continue"] in calls
    assert ["git", "rebase", "--abort"] not in calls


def test_other_rebase_conflict_aborts(tmp_path):
    calls, fake = _run([
        (["git", "rebase", "origin/master"], subprocess.CompletedProcess([], 1, "", "conflict")),
        (["git", "diff", "--name-only", "--diff-filter=U"],
         subprocess.CompletedProcess([], 0, "daily/index.html\nsearch-index.json\n", "")),
    ])
    try:
        publish_git.rebase_and_refresh_search_index(fake, tmp_path, lambda cwd: ["git"])
    except RuntimeError as exc:
        assert "conflict" in str(exc)
    else:
        raise AssertionError("non-index conflicts must abort")
    assert ["git", "rebase", "--abort"] in calls
