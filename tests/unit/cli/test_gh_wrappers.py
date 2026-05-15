"""``tripwire gh`` Layer-1 wrappers (v0.13).

The three commands shell out to ``gh`` via
:mod:`tripwire.core.gh_helpers`. Tests patch ``subprocess.run`` at the
``gh_helpers`` module level (the single place gh is invoked now) and
assert the right command was issued. The ``pr-close`` path still
routes through ``session_abandon._close_pr_by_num``; that helper now
also delegates to ``gh_helpers``, so the same patch target applies.
"""

from __future__ import annotations

from click.testing import CliRunner


def _mk_completed(returncode: int, stderr: str = "", stdout: str = ""):
    class _R:
        pass

    r = _R()
    r.returncode = returncode
    r.stderr = stderr
    r.stdout = stdout
    return r


def test_gh_pr_ready_invokes_gh(monkeypatch) -> None:
    from tripwire.cli import gh as gh_mod
    from tripwire.core import gh_helpers

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return _mk_completed(0)

    monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
    runner = CliRunner()
    result = runner.invoke(gh_mod.gh_cmd, ["pr-ready", "42"])

    assert result.exit_code == 0, result.output
    assert calls == [["gh", "pr", "ready", "42"]]
    assert "ready-for-review" in result.output


def test_gh_pr_ready_surfaces_failure(monkeypatch) -> None:
    from tripwire.cli import gh as gh_mod
    from tripwire.core import gh_helpers

    def fake_run(cmd, **kwargs):
        return _mk_completed(1, stderr="not a PR")

    monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
    runner = CliRunner()
    result = runner.invoke(gh_mod.gh_cmd, ["pr-ready", "42"])

    assert result.exit_code != 0
    assert "not a PR" in result.output
    assert "gh pr ready #42" in result.output


def test_gh_pr_ready_undo_invokes_gh_with_undo(monkeypatch) -> None:
    from tripwire.cli import gh as gh_mod
    from tripwire.core import gh_helpers

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return _mk_completed(0)

    monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
    runner = CliRunner()
    result = runner.invoke(gh_mod.gh_cmd, ["pr-ready-undo", "42"])

    assert result.exit_code == 0, result.output
    assert calls == [["gh", "pr", "ready", "42", "--undo"]]
    assert "draft" in result.output


def test_gh_pr_ready_undo_surfaces_failure(monkeypatch) -> None:
    from tripwire.cli import gh as gh_mod
    from tripwire.core import gh_helpers

    def fake_run(cmd, **kwargs):
        return _mk_completed(2, stderr="already draft")

    monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
    runner = CliRunner()
    result = runner.invoke(gh_mod.gh_cmd, ["pr-ready-undo", "42"])

    assert result.exit_code != 0
    assert "already draft" in result.output


def test_gh_pr_close_invokes_helper(monkeypatch) -> None:
    """``pr-close`` routes through ``_close_pr_by_num`` so the same
    error-capture semantics apply as in session_abandon. The subprocess
    call itself now lives in :mod:`tripwire.core.gh_helpers` — patch
    there to intercept it."""
    from tripwire.cli import gh as gh_mod
    from tripwire.core import gh_helpers

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return _mk_completed(0)

    monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
    runner = CliRunner()
    result = runner.invoke(gh_mod.gh_cmd, ["pr-close", "42"])

    assert result.exit_code == 0, result.output
    assert calls == [["gh", "pr", "close", "42"]]
    assert "closed PR #42" in result.output


def test_gh_pr_close_surfaces_failure(monkeypatch) -> None:
    from tripwire.cli import gh as gh_mod
    from tripwire.core import gh_helpers

    def fake_run(cmd, **kwargs):
        return _mk_completed(1, stderr="PR already merged")

    monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
    runner = CliRunner()
    result = runner.invoke(gh_mod.gh_cmd, ["pr-close", "42"])

    assert result.exit_code != 0
    assert "PR already merged" in result.output


def test_close_pr_by_num_returns_closed_on_success(monkeypatch) -> None:
    """Unit test the helper directly — it's the contract the gh CLI rides on."""
    from tripwire.core import gh_helpers
    from tripwire.core import session_abandon as sa

    def fake_run(cmd, **kwargs):
        return _mk_completed(0)

    monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
    verdict = sa._close_pr_by_num(99)
    assert verdict.closed_pr == 99
    assert verdict.error is None


def test_close_pr_by_num_captures_error(monkeypatch) -> None:
    from tripwire.core import gh_helpers
    from tripwire.core import session_abandon as sa

    def fake_run(cmd, **kwargs):
        return _mk_completed(1, stderr="boom")

    monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
    verdict = sa._close_pr_by_num(99)
    assert verdict.closed_pr is None
    assert verdict.error is not None
    assert "boom" in verdict.error
