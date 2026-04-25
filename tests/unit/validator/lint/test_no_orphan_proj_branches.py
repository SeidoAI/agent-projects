"""Validator rule `no_orphan_proj_branches` (v0.7.9 §A9).

For every local ``proj/<sid>`` branch in the project tracking repo,
a session with id ``<sid>`` must exist. Catches the "spawn created a
branch, agent never used it, branch is now stranded" pattern that
accumulates as orphan refs over time.
"""

from pathlib import Path

from tripwire.core.validator import load_context
from tripwire.core.validator.lint import no_orphan_proj_branches


def _stub_branches(monkeypatch, branches: list[str]) -> None:
    monkeypatch.setattr(
        no_orphan_proj_branches,
        "local_proj_branches",
        lambda _repo_dir: list(branches),
    )


def test_orphan_branch_errors(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    """proj/ghost has no matching session → 1 error."""
    save_test_session(tmp_path_project, "alive")
    _stub_branches(monkeypatch, ["proj/alive", "proj/ghost"])

    ctx = load_context(tmp_path_project)
    results = no_orphan_proj_branches.check(ctx)

    assert len(results) == 1
    assert results[0].code == "no_orphan_proj_branches/orphan"
    assert results[0].severity == "error"
    assert "proj/ghost" in results[0].message


def test_branch_with_session_passes(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    save_test_session(tmp_path_project, "alive")
    _stub_branches(monkeypatch, ["proj/alive"])

    ctx = load_context(tmp_path_project)
    assert no_orphan_proj_branches.check(ctx) == []


def test_no_proj_branches_passes(tmp_path_project: Path, monkeypatch):
    _stub_branches(monkeypatch, [])
    ctx = load_context(tmp_path_project)
    assert no_orphan_proj_branches.check(ctx) == []


def test_multiple_orphans_each_reported(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    """Today's actual orphans on tripwire-v0:
    proj/code-ci-cleanup, proj/v075-agent-loop, proj/v076-concept-drift-lint."""
    save_test_session(tmp_path_project, "kept")
    _stub_branches(
        monkeypatch,
        [
            "proj/kept",
            "proj/code-ci-cleanup",
            "proj/v075-agent-loop",
            "proj/v076-concept-drift-lint",
        ],
    )

    ctx = load_context(tmp_path_project)
    results = no_orphan_proj_branches.check(ctx)

    assert len(results) == 3
    flagged = sorted(
        b for r in results for b in (
            "proj/code-ci-cleanup",
            "proj/v075-agent-loop",
            "proj/v076-concept-drift-lint",
        ) if b in r.message
    )
    assert flagged == [
        "proj/code-ci-cleanup",
        "proj/v075-agent-loop",
        "proj/v076-concept-drift-lint",
    ]


def test_local_proj_branches_returns_empty_on_non_repo(tmp_path: Path):
    """The git helper degrades gracefully — bare temp dir → []."""
    assert no_orphan_proj_branches.local_proj_branches(tmp_path) == []


def test_local_proj_branches_real_git_repo(tmp_path: Path):
    """End-to-end: in a real git repo with a proj/foo branch, the
    helper returns ['proj/foo']."""
    import subprocess

    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init", "-q"],
        check=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "branch", "proj/foo"], check=True
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "branch", "feat/x"], check=True
    )

    branches = no_orphan_proj_branches.local_proj_branches(tmp_path)
    assert branches == ["proj/foo"]
