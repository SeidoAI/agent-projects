"""``tripwire git`` Layer-1 wrappers (v0.13).

Each wrapper is a thin click adapter; tests verify the underlying
helper is invoked and that conflict / failure paths surface as click
errors.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner


def test_git_rebase_pt_invokes_fetch_and_rebase(tmp_path: Path, monkeypatch) -> None:
    """Happy path: ``fetch_origin`` + ``rebase_branch_onto`` are called
    once each with the worktree resolved to an absolute path."""
    import tripwire.core.git_helpers as gh
    from tripwire.cli._tools import git as git_mod

    wt = tmp_path / "wt"
    wt.mkdir()

    calls: list[tuple[str, Path, str | None]] = []

    def fake_fetch(p: Path) -> None:
        calls.append(("fetch", p, None))

    def fake_rebase(p: Path, upstream: str) -> None:
        calls.append(("rebase", p, upstream))

    monkeypatch.setattr(gh, "fetch_origin", fake_fetch)
    monkeypatch.setattr(gh, "rebase_branch_onto", fake_rebase)

    runner = CliRunner()
    result = runner.invoke(git_mod.git_cmd, ["rebase-pt", str(wt)])

    assert result.exit_code == 0, result.output
    assert calls == [
        ("fetch", wt.resolve(), None),
        ("rebase", wt.resolve(), "origin/main"),
    ]
    assert "rebased" in result.output


def test_git_rebase_pt_surfaces_rebase_conflict(tmp_path: Path, monkeypatch) -> None:
    """A ``RebaseConflict`` raised by the helper becomes a non-zero exit
    with the conflict message preserved."""
    import tripwire.core.git_helpers as gh
    from tripwire.cli._tools import git as git_mod

    wt = tmp_path / "wt"
    wt.mkdir()

    monkeypatch.setattr(gh, "fetch_origin", lambda p: None)

    def fake_rebase(p: Path, upstream: str) -> None:
        raise gh.RebaseConflict("conflict in plan.md")

    monkeypatch.setattr(gh, "rebase_branch_onto", fake_rebase)

    runner = CliRunner()
    result = runner.invoke(git_mod.git_cmd, ["rebase-pt", str(wt)])

    assert result.exit_code != 0
    assert "pt_rebase_conflict" in result.output
    assert "conflict in plan.md" in result.output


def test_git_rebase_pt_rejects_missing_worktree(tmp_path: Path) -> None:
    """Click's ``exists=True`` guard rejects a non-existent path."""
    from tripwire.cli._tools import git as git_mod

    runner = CliRunner()
    result = runner.invoke(
        git_mod.git_cmd, ["rebase-pt", str(tmp_path / "does-not-exist")]
    )
    assert result.exit_code != 0
    assert "does not exist" in result.output.lower()
