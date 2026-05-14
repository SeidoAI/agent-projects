"""``tripwire session`` Layer-1 wrappers (v0.13).

These commands lift one side-effect body each into the public CLI.
Tests confirm:

- the underlying helper is invoked with the right inputs
- no-op paths (no recorded worktrees, no pid, etc.) exit cleanly
- failure paths surface as click errors or warnings, never silent
"""

from __future__ import annotations

import errno
from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.session import session_cmd


def _mk_completed(returncode: int, stderr: str = "", stdout: str = ""):
    class _R:
        pass

    r = _R()
    r.returncode = returncode
    r.stderr = stderr
    r.stdout = stdout
    return r


def _mk_runtime_state(tmp_path_project, *, pid=None, draft_url=None):
    """Build a RuntimeState with one worktree binding for tests."""
    from tripwire.models.session import RuntimeState, WorktreeEntry

    rs = RuntimeState(
        pid=pid,
        worktrees=[
            WorktreeEntry(
                repo="SeidoAI/code",
                clone_path=str(tmp_path_project / "code"),
                worktree_path=str(tmp_path_project / "code-wt-s1"),
                branch="feat/s1",
                draft_pr_url=draft_url,
            )
        ],
    )
    return rs


# ---------------------------------------------------------------------------
# kill-runtime
# ---------------------------------------------------------------------------


def test_kill_runtime_sigterm_recorded_pid(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    rs = _mk_runtime_state(tmp_path_project, pid=4242)
    save_test_session(
        tmp_path_project, "s1", status="executing", runtime_state=rs.model_dump()
    )

    seen: list[tuple[int, int]] = []

    def fake_kill(pid: int, sig: int) -> None:
        seen.append((pid, sig))

    import os
    import signal

    monkeypatch.setattr(os, "kill", fake_kill)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["kill-runtime", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code == 0, result.output
    assert seen == [(4242, signal.SIGTERM)]
    assert "SIGTERM" in result.output


def test_kill_runtime_no_pid_skips(
    tmp_path_project: Path, save_test_session
) -> None:
    save_test_session(tmp_path_project, "s1", status="planned")
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["kill-runtime", "s1", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code == 0, result.output
    assert "no runtime pid recorded" in result.output


def test_kill_runtime_swallows_esrch(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    """A pid that's already dead exits 0 — best-effort by contract."""
    rs = _mk_runtime_state(tmp_path_project, pid=1234)
    save_test_session(
        tmp_path_project, "s1", status="executing", runtime_state=rs.model_dump()
    )

    def fake_kill(pid: int, sig: int) -> None:
        raise ProcessLookupError(errno.ESRCH, "No such process")

    import os

    monkeypatch.setattr(os, "kill", fake_kill)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["kill-runtime", "s1", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code == 0, result.output
    assert "already dead" in result.output


def test_kill_runtime_surfaces_other_oserror(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    rs = _mk_runtime_state(tmp_path_project, pid=1234)
    save_test_session(
        tmp_path_project, "s1", status="executing", runtime_state=rs.model_dump()
    )

    def fake_kill(pid: int, sig: int) -> None:
        raise PermissionError(errno.EPERM, "Operation not permitted")

    import os

    monkeypatch.setattr(os, "kill", fake_kill)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["kill-runtime", "s1", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code != 0
    assert "failed to signal" in result.output


def test_kill_runtime_missing_session(tmp_path_project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["kill-runtime", "missing", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code != 0
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# close-prs
# ---------------------------------------------------------------------------


def test_close_prs_invokes_per_branch_helper(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    rs = _mk_runtime_state(tmp_path_project)
    save_test_session(
        tmp_path_project, "s1", status="executing", runtime_state=rs.model_dump()
    )

    from tripwire.cli import session as cli_session
    from tripwire.core import session_abandon as sa

    calls: list[tuple[str, str]] = []

    def fake_close(branch: str, worktree_path: str):
        calls.append((branch, worktree_path))
        v = sa._PrCloseVerdict()
        v.closed_pr = 17
        return v

    # CLI does `from ... import _close_pr_for_branch` at runtime, so
    # patching the source module is sufficient.
    monkeypatch.setattr(sa, "_close_pr_for_branch", fake_close)
    # Belt-and-braces: any future re-export on cli.session is also patched.
    monkeypatch.setattr(
        cli_session, "_close_pr_for_branch", fake_close, raising=False
    )

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["close-prs", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0][0] == "feat/s1"
    assert "closed PR #17" in result.output


def test_close_prs_no_worktrees(
    tmp_path_project: Path, save_test_session
) -> None:
    save_test_session(tmp_path_project, "s1", status="planned")
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["close-prs", "s1", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code == 0, result.output
    assert "no recorded worktrees" in result.output


def test_close_prs_reports_helper_error(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    rs = _mk_runtime_state(tmp_path_project)
    save_test_session(
        tmp_path_project, "s1", status="executing", runtime_state=rs.model_dump()
    )

    from tripwire.core import session_abandon as sa

    def fake_close(branch: str, worktree_path: str):
        v = sa._PrCloseVerdict()
        v.error = "gh: rate-limited"
        return v

    monkeypatch.setattr(sa, "_close_pr_for_branch", fake_close)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["close-prs", "s1", "--project-dir", str(tmp_path_project)],
    )
    # Best-effort: command still exits 0, error surfaces as warning.
    assert result.exit_code == 0, result.output
    assert "rate-limited" in result.output


# ---------------------------------------------------------------------------
# remove-worktrees
# ---------------------------------------------------------------------------


def test_remove_worktrees_invokes_helper(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    rs = _mk_runtime_state(tmp_path_project)
    save_test_session(
        tmp_path_project, "s1", status="executing", runtime_state=rs.model_dump()
    )

    from tripwire.cli import session as cli_session

    calls: list[tuple[Path, Path]] = []

    def fake_remove(clone: Path, wt: Path) -> None:
        calls.append((clone, wt))

    # cli/session.py imports `worktree_remove` at top-level — patch
    # it on that module directly.
    monkeypatch.setattr(cli_session, "worktree_remove", fake_remove)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["remove-worktrees", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert "removed worktree" in result.output


def test_remove_worktrees_no_worktrees(
    tmp_path_project: Path, save_test_session
) -> None:
    save_test_session(tmp_path_project, "s1", status="planned")
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["remove-worktrees", "s1", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code == 0, result.output
    assert "no recorded worktrees" in result.output


def test_remove_worktrees_records_failure(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    rs = _mk_runtime_state(tmp_path_project)
    save_test_session(
        tmp_path_project, "s1", status="executing", runtime_state=rs.model_dump()
    )

    from tripwire.cli import session as cli_session

    def fake_remove(clone: Path, wt: Path) -> None:
        raise OSError("locked")

    monkeypatch.setattr(cli_session, "worktree_remove", fake_remove)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["remove-worktrees", "s1", "--project-dir", str(tmp_path_project)],
    )
    # Best-effort: keep going, warn.
    assert result.exit_code == 0, result.output
    assert "locked" in result.output


# ---------------------------------------------------------------------------
# flip-drafts-ready / flip-drafts-draft
# ---------------------------------------------------------------------------


def test_flip_drafts_ready_invokes_helper(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    rs = _mk_runtime_state(
        tmp_path_project, draft_url="https://github.com/org/repo/pull/9"
    )
    save_test_session(
        tmp_path_project, "s1", status="executing", runtime_state=rs.model_dump()
    )

    seen: list = []

    def fake_flip(session) -> None:
        seen.append(session.id)

    import tripwire.core.session_complete as sc

    monkeypatch.setattr(sc, "_flip_drafts_to_ready", fake_flip)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["flip-drafts-ready", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code == 0, result.output
    assert seen == ["s1"]
    assert "ready" in result.output


def test_flip_drafts_draft_runs_gh_undo(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    rs = _mk_runtime_state(
        tmp_path_project, draft_url="https://github.com/org/repo/pull/9"
    )
    save_test_session(
        tmp_path_project, "s1", status="executing", runtime_state=rs.model_dump()
    )

    from tripwire.cli import session as cli_session

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return _mk_completed(0)

    monkeypatch.setattr(cli_session.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["flip-drafts-draft", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        ["gh", "pr", "ready", "https://github.com/org/repo/pull/9", "--undo"]
    ]
    assert "draft" in result.output.lower()


def test_flip_drafts_draft_no_draft_url(
    tmp_path_project: Path, save_test_session
) -> None:
    rs = _mk_runtime_state(tmp_path_project)  # no draft_url
    save_test_session(
        tmp_path_project, "s1", status="executing", runtime_state=rs.model_dump()
    )

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["flip-drafts-draft", "s1", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code == 0, result.output
    assert "no draft URLs" in result.output


# ---------------------------------------------------------------------------
# normalise-branch
# ---------------------------------------------------------------------------


def test_normalise_branch_resets_squash_merged(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    """PR is merged, branch is ahead of origin/main → reset."""
    wt_dir = tmp_path_project / "code-wt-s1"
    wt_dir.mkdir()

    rs = _mk_runtime_state(tmp_path_project)
    # Patch the worktree path to point at a real dir.
    rs.worktrees[0].worktree_path = str(wt_dir)
    save_test_session(
        tmp_path_project, "s1", status="in_review", runtime_state=rs.model_dump()
    )

    from tripwire.cli import session as cli_session

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:3] == ["gh", "pr", "list"]:
            payload = '[{"number": 9, "mergedAt": "2026-01-01T00:00:00Z"}]'
            return _mk_completed(0, stdout=payload)
        if "rev-list" in cmd:
            return _mk_completed(0, stdout="3\n")
        if "reset" in cmd:
            return _mk_completed(0)
        raise AssertionError(f"unexpected cmd: {cmd}")

    monkeypatch.setattr(cli_session.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["normalise-branch", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code == 0, result.output
    # We expect gh pr list → rev-list → reset.
    assert any(c[:3] == ["gh", "pr", "list"] for c in calls)
    assert any("rev-list" in c for c in calls)
    assert any("reset" in c for c in calls)
    assert "reset to origin/main" in result.output


def test_normalise_branch_skips_when_pr_not_merged(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    wt_dir = tmp_path_project / "code-wt-s1"
    wt_dir.mkdir()

    rs = _mk_runtime_state(tmp_path_project)
    rs.worktrees[0].worktree_path = str(wt_dir)
    save_test_session(
        tmp_path_project, "s1", status="in_review", runtime_state=rs.model_dump()
    )

    from tripwire.cli import session as cli_session

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["gh", "pr", "list"]:
            return _mk_completed(0, stdout="[]")
        raise AssertionError(f"unexpected: {cmd}")

    monkeypatch.setattr(cli_session.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["normalise-branch", "s1", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code == 0, result.output
    assert "PR not merged" in result.output


def test_normalise_branch_idempotent_when_already_at_main(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    """rev-list returns 0 (no commits ahead) → skip reset."""
    wt_dir = tmp_path_project / "code-wt-s1"
    wt_dir.mkdir()

    rs = _mk_runtime_state(tmp_path_project)
    rs.worktrees[0].worktree_path = str(wt_dir)
    save_test_session(
        tmp_path_project, "s1", status="in_review", runtime_state=rs.model_dump()
    )

    from tripwire.cli import session as cli_session

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:3] == ["gh", "pr", "list"]:
            return _mk_completed(
                0, stdout='[{"number": 9, "mergedAt": "2026-01-01T00:00:00Z"}]'
            )
        if "rev-list" in cmd:
            return _mk_completed(0, stdout="0\n")
        raise AssertionError(f"reset should not run: {cmd}")

    monkeypatch.setattr(cli_session.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["normalise-branch", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code == 0, result.output
    assert "already at origin/main" in result.output
    assert not any("reset" in c for c in calls)


def test_normalise_branch_skips_missing_worktree_dir(
    tmp_path_project: Path, save_test_session
) -> None:
    """A worktree whose path is gone (e.g. cleaned up) is a clean skip."""
    rs = _mk_runtime_state(tmp_path_project)  # path does not exist
    save_test_session(
        tmp_path_project, "s1", status="in_review", runtime_state=rs.model_dump()
    )

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["normalise-branch", "s1", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code == 0, result.output
    assert "worktree missing" in result.output


# ---------------------------------------------------------------------------
# followup-stub
# ---------------------------------------------------------------------------


def test_followup_stub_appends_when_absent(
    tmp_path_project: Path, save_test_session
) -> None:
    from tripwire.core import paths as _paths

    save_test_session(tmp_path_project, "s1", status="completed", plan=True)
    plan_path = _paths.session_plan_path(tmp_path_project, "s1")
    assert plan_path.is_file()
    before = plan_path.read_text(encoding="utf-8")
    assert "## PM follow-up" not in before

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "followup-stub",
            "s1",
            "--reason",
            "PR rework needed",
            "--project-dir",
            str(tmp_path_project),
        ],
    )

    assert result.exit_code == 0, result.output
    after = plan_path.read_text(encoding="utf-8")
    assert "## PM follow-up" in after
    assert "PR rework needed" in after
    assert "tripwire session spawn s1 --resume" in after


def test_followup_stub_idempotent(
    tmp_path_project: Path, save_test_session
) -> None:
    """Re-running once the section is present is a clean no-op."""
    from tripwire.core import paths as _paths

    save_test_session(tmp_path_project, "s1", status="completed", plan=True)
    plan_path = _paths.session_plan_path(tmp_path_project, "s1")
    plan_path.write_text(
        plan_path.read_text(encoding="utf-8") + "\n\n## PM follow-up\nalready here\n",
        encoding="utf-8",
    )
    before = plan_path.read_text(encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "followup-stub",
            "s1",
            "--reason",
            "ignored",
            "--project-dir",
            str(tmp_path_project),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "already present" in result.output
    # File contents unchanged.
    assert plan_path.read_text(encoding="utf-8") == before


def test_followup_stub_missing_plan_reports(
    tmp_path_project: Path, save_test_session
) -> None:
    """No plan.md on disk → emit a warning but don't blow up."""
    save_test_session(tmp_path_project, "s1", status="completed")

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "followup-stub",
            "s1",
            "--project-dir",
            str(tmp_path_project),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "plan.md not found" in result.output


# ---------------------------------------------------------------------------
# prepare-for-completion (Layer-2)
# ---------------------------------------------------------------------------


def _mk_clean_report():
    """A ValidationReport with no errors / warnings."""
    from tripwire.core.validator import ValidationReport

    return ValidationReport(
        errors=[],
        warnings=[],
        fixed=[],
        duration_ms=1,
        cache_rebuilt=False,
        exit_code=0,
    )


def _mk_error_report(code: str = "test/err", message: str = "boom"):
    from tripwire.core.validator import CheckResult, ValidationReport

    return ValidationReport(
        errors=[CheckResult(code=code, severity="error", message=message)],
        warnings=[],
        fixed=[],
        duration_ms=1,
        cache_rebuilt=False,
        exit_code=2,
    )


def test_prepare_for_completion_happy_path(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    """validate clean → drafts flip → all PRs MERGEABLE → exit 0."""
    wt_dir = tmp_path_project / "code-wt-s1"
    wt_dir.mkdir()

    rs = _mk_runtime_state(
        tmp_path_project, draft_url="https://github.com/o/r/pull/9"
    )
    rs.worktrees[0].worktree_path = str(wt_dir)
    save_test_session(
        tmp_path_project, "s1", status="verified", runtime_state=rs.model_dump()
    )

    from tripwire.cli import session as cli_session
    from tripwire.cli import validate as cli_validate
    from tripwire.core import session_complete as sc
    from tripwire.core import validator as core_validator

    monkeypatch.setattr(
        core_validator, "validate_project", lambda *a, **k: _mk_clean_report()
    )
    monkeypatch.setattr(
        cli_validate, "_filter_report_by_selector", lambda r, p, s: None
    )
    monkeypatch.setattr(sc, "_flip_drafts_to_ready", lambda session: None)

    def fake_run(cmd, **kwargs):
        # Step 3: gh pr view
        if cmd[:3] == ["gh", "pr", "view"]:
            payload = '{"number": 9, "state": "OPEN", "mergeStateStatus": "CLEAN"}'
            return _mk_completed(0, stdout=payload)
        raise AssertionError(f"unexpected cmd: {cmd}")

    monkeypatch.setattr(cli_session.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["prepare-for-completion", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code == 0, result.output
    assert "validate clean" in result.output
    assert "ready for completion" in result.output


def test_prepare_for_completion_validate_fails(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    """validate errors → exit 1, findings printed, PR check never runs."""
    save_test_session(tmp_path_project, "s1", status="verified")

    from tripwire.cli import session as cli_session
    from tripwire.cli import validate as cli_validate
    from tripwire.core import validator as core_validator

    monkeypatch.setattr(
        core_validator, "validate_project", lambda *a, **k: _mk_error_report()
    )
    monkeypatch.setattr(
        cli_validate, "_filter_report_by_selector", lambda r, p, s: None
    )

    def fake_run(cmd, **kwargs):
        raise AssertionError(f"subprocess should not run: {cmd}")

    monkeypatch.setattr(cli_session.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["prepare-for-completion", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code != 0
    assert "validate" in result.output.lower()
    assert "boom" in result.output


def test_prepare_for_completion_pr_blocked(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    """validate clean, drafts flip, but gh reports BLOCKED → exit 1."""
    wt_dir = tmp_path_project / "code-wt-s1"
    wt_dir.mkdir()

    rs = _mk_runtime_state(tmp_path_project)
    rs.worktrees[0].worktree_path = str(wt_dir)
    save_test_session(
        tmp_path_project, "s1", status="verified", runtime_state=rs.model_dump()
    )

    from tripwire.cli import session as cli_session
    from tripwire.cli import validate as cli_validate
    from tripwire.core import session_complete as sc
    from tripwire.core import validator as core_validator

    monkeypatch.setattr(
        core_validator, "validate_project", lambda *a, **k: _mk_clean_report()
    )
    monkeypatch.setattr(
        cli_validate, "_filter_report_by_selector", lambda r, p, s: None
    )
    monkeypatch.setattr(sc, "_flip_drafts_to_ready", lambda session: None)

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["gh", "pr", "view"]:
            payload = (
                '{"number": 42, "state": "OPEN", "mergeStateStatus": "BLOCKED"}'
            )
            return _mk_completed(0, stdout=payload)
        raise AssertionError(f"unexpected cmd: {cmd}")

    monkeypatch.setattr(cli_session.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["prepare-for-completion", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code != 0
    assert "PR #42" in result.output
    assert "BLOCKED" in result.output


# ---------------------------------------------------------------------------
# prepare-for-abandon (Layer-2)
# ---------------------------------------------------------------------------


def test_prepare_for_abandon_happy_path(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    """kill → close-prs → remove-worktrees, all succeed → exit 0."""
    rs = _mk_runtime_state(tmp_path_project, pid=4321)
    save_test_session(
        tmp_path_project, "s1", status="executing", runtime_state=rs.model_dump()
    )

    seen_kill: list[tuple[int, int]] = []

    def fake_kill(pid: int, sig: int) -> None:
        seen_kill.append((pid, sig))

    import os
    import signal

    monkeypatch.setattr(os, "kill", fake_kill)

    from tripwire.cli import session as cli_session
    from tripwire.core import session_abandon as sa

    def fake_close(branch, worktree_path):
        v = sa._PrCloseVerdict()
        v.closed_pr = 17
        return v

    monkeypatch.setattr(sa, "_close_pr_for_branch", fake_close)

    removed: list[Path] = []

    def fake_remove(clone, wt):
        removed.append(wt)

    monkeypatch.setattr(cli_session, "worktree_remove", fake_remove)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["prepare-for-abandon", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code == 0, result.output
    assert seen_kill == [(4321, signal.SIGTERM)]
    assert "closed PR #17" in result.output
    assert "removed worktree" in result.output
    assert "ready for abandon" in result.output


def test_prepare_for_abandon_no_pid_proceeds(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    """No recorded pid → kill is a no-op, but close-prs + remove still run."""
    rs = _mk_runtime_state(tmp_path_project)  # pid=None
    save_test_session(
        tmp_path_project, "s1", status="executing", runtime_state=rs.model_dump()
    )

    from tripwire.cli import session as cli_session
    from tripwire.core import session_abandon as sa

    def fake_close(branch, worktree_path):
        v = sa._PrCloseVerdict()
        v.closed_pr = 5
        return v

    monkeypatch.setattr(sa, "_close_pr_for_branch", fake_close)
    monkeypatch.setattr(cli_session, "worktree_remove", lambda c, w: None)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["prepare-for-abandon", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code == 0, result.output
    assert "no runtime pid recorded" in result.output
    assert "closed PR #5" in result.output


def test_prepare_for_abandon_close_prs_fails_continues(
    tmp_path_project: Path, save_test_session, monkeypatch
) -> None:
    """A hard close-prs error continues to remove-worktrees but exits non-zero."""
    rs = _mk_runtime_state(tmp_path_project, pid=99)
    save_test_session(
        tmp_path_project, "s1", status="executing", runtime_state=rs.model_dump()
    )

    import os

    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    from tripwire.cli import session as cli_session
    from tripwire.core import session_abandon as sa

    def fake_close(branch, worktree_path):
        v = sa._PrCloseVerdict()
        v.error = "gh: auth required"
        return v

    monkeypatch.setattr(sa, "_close_pr_for_branch", fake_close)

    remove_calls: list[Path] = []

    def fake_remove(clone, wt):
        remove_calls.append(wt)

    monkeypatch.setattr(cli_session, "worktree_remove", fake_remove)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["prepare-for-abandon", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code != 0
    # remove-worktrees still ran
    assert len(remove_calls) == 1
    # summary names the failing step
    assert "close-prs" in result.output
    assert "auth required" in result.output


# ---------------------------------------------------------------------------
# sweep-issues-forward (Layer-2)
# ---------------------------------------------------------------------------


def test_sweep_issues_forward_happy_path(
    tmp_path_project: Path, save_test_issue, save_test_session, monkeypatch
) -> None:
    """Two member issues, both transition cleanly → exit 0."""
    save_test_issue(tmp_path_project, "TMP-1")
    save_test_issue(tmp_path_project, "TMP-2")
    save_test_session(
        tmp_path_project,
        "s1",
        status="verified",
        issues=["TMP-1", "TMP-2"],
    )

    from tripwire.cli import session as cli_session

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return _mk_completed(0, stdout="ok")

    monkeypatch.setattr(cli_session.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["sweep-issues-forward", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code == 0, result.output
    # One call per issue; each invokes the issue-closure workflow.
    assert len(calls) == 2
    for c in calls:
        assert c[:3] == ["tripwire", "transition", "issue-closure"]
        # target = sweep_target_for("verified") = "verified"
        assert c[4] == "verified"
    assert "swept 2 issue(s)" in result.output


def test_sweep_issues_forward_one_rejected(
    tmp_path_project: Path, save_test_issue, save_test_session, monkeypatch
) -> None:
    """One issue's transition is rejected → exit 1 with per-issue summary."""
    save_test_issue(tmp_path_project, "TMP-1")
    save_test_issue(tmp_path_project, "TMP-2")
    save_test_session(
        tmp_path_project,
        "s1",
        status="verified",
        issues=["TMP-1", "TMP-2"],
    )

    from tripwire.cli import session as cli_session

    def fake_run(cmd, **kwargs):
        # Reject TMP-2 only.
        if "TMP-2" in cmd:
            return _mk_completed(1, stderr="transition rejected: not_reachable")
        return _mk_completed(0)

    monkeypatch.setattr(cli_session.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["sweep-issues-forward", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code != 0
    assert "TMP-2" in result.output
    assert "not_reachable" in result.output


def test_sweep_issues_forward_no_member_issues(
    tmp_path_project: Path, save_test_session
) -> None:
    """A session with no member issues is a clean no-op."""
    save_test_session(tmp_path_project, "s1", status="verified", issues=[])

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["sweep-issues-forward", "s1", "--project-dir", str(tmp_path_project)],
    )

    assert result.exit_code == 0, result.output
    assert "no member issues" in result.output
