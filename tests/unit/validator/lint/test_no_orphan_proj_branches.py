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


def _stub_empty(monkeypatch, empty_branches: set[str]) -> None:
    """Mark the named branches as having 0 commits ahead of base."""
    monkeypatch.setattr(
        no_orphan_proj_branches,
        "branch_is_empty",
        lambda _repo, branch, _base: branch in empty_branches,
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
    save_test_session(tmp_path_project, "alive", status="executing")
    _stub_branches(monkeypatch, ["proj/alive"])
    _stub_empty(monkeypatch, set())

    ctx = load_context(tmp_path_project)
    assert no_orphan_proj_branches.check(ctx) == []


def test_queued_session_empty_branch_errors(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    """Spawn created branch, agent never started — session.status is
    queued AND branch has no commits ahead of base → orphan."""
    save_test_session(tmp_path_project, "lazy", status="queued")
    _stub_branches(monkeypatch, ["proj/lazy"])
    _stub_empty(monkeypatch, {"proj/lazy"})

    ctx = load_context(tmp_path_project)
    results = no_orphan_proj_branches.check(ctx)

    assert len(results) == 1
    assert results[0].code == "no_orphan_proj_branches/empty_queued"
    assert results[0].severity == "error"
    assert "proj/lazy" in results[0].message


def test_queued_session_with_commits_passes(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    """Queued session whose branch has commits — agent did start work
    but the runtime didn't flip the status. Not an orphan; a different
    kind of drift."""
    save_test_session(tmp_path_project, "started", status="queued")
    _stub_branches(monkeypatch, ["proj/started"])
    _stub_empty(monkeypatch, set())

    ctx = load_context(tmp_path_project)
    assert no_orphan_proj_branches.check(ctx) == []


def test_executing_session_empty_branch_passes(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    """A just-spawned executing session may have an empty branch
    momentarily. Don't fire."""
    save_test_session(tmp_path_project, "fresh", status="executing")
    _stub_branches(monkeypatch, ["proj/fresh"])
    _stub_empty(monkeypatch, {"proj/fresh"})

    ctx = load_context(tmp_path_project)
    assert no_orphan_proj_branches.check(ctx) == []


def test_no_proj_branches_passes(tmp_path_project: Path, monkeypatch):
    _stub_branches(monkeypatch, [])
    _stub_empty(monkeypatch, set())
    ctx = load_context(tmp_path_project)
    assert no_orphan_proj_branches.check(ctx) == []


def test_multiple_orphans_each_reported(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    """Today's actual orphans on tripwire-v0: queued sessions whose
    proj/ branches have zero commits ahead of main."""
    save_test_session(tmp_path_project, "kept", status="executing")
    save_test_session(tmp_path_project, "code-ci-cleanup", status="queued")
    save_test_session(tmp_path_project, "v075-agent-loop", status="queued")
    save_test_session(
        tmp_path_project, "v076-concept-drift-lint", status="queued"
    )
    _stub_branches(
        monkeypatch,
        [
            "proj/kept",
            "proj/code-ci-cleanup",
            "proj/v075-agent-loop",
            "proj/v076-concept-drift-lint",
        ],
    )
    _stub_empty(
        monkeypatch,
        {
            "proj/code-ci-cleanup",
            "proj/v075-agent-loop",
            "proj/v076-concept-drift-lint",
        },
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


def test_branch_is_empty_returns_false_on_non_repo(tmp_path: Path):
    """Bare temp dir → can't compute → assume non-empty (don't fire)."""
    assert (
        no_orphan_proj_branches.branch_is_empty(tmp_path, "any", "main") is False
    )


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
