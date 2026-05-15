"""Tests for PM-handoff #6 D3 + D4.

D3 — ``tripwire session spawn --from-remote <branch>``: after the
local worktree is created, fetch the named remote branch and check
it out so the spawned agent inherits partial work. Verified by
mocking ``subprocess.run`` and asserting on the git argv sequence
that fires after ``prep_run`` returns.

D4 — generalized ``--resume`` precondition: resume is now allowed
from any non-terminal source state (executing, in_review, paused,
failed). Terminal states (verified, completed, abandoned) and
pre-spawn states (planned, queued) fail loudly with a state-specific
hint.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_store import load_session


@pytest.fixture(autouse=True)
def _stub_v075_prereqs():
    """Bypass the v0.7.5 gh + draft-PR prerequisites for these tests —
    they live in their own prep_draft_pr tests; here we just exercise
    the CLI gates around them."""
    with (
        patch("tripwire.runtimes.prep._check_gh_available"),
        patch("tripwire.runtimes.prep._open_draft_pr", return_value=None),
    ):
        yield


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            "init",
        ],
        cwd=path,
        check=True,
    )


class TestSpawnFromRemote:
    """D3 — --from-remote hydrates the worktree from a named remote branch."""

    def test_from_remote_runs_fetch_then_checkout_in_worktree(
        self,
        tmp_path,
        tmp_path_project,
        save_test_session,
        save_test_issue,
        write_handoff_yaml,
    ):
        """The CLI must invoke ``git fetch origin <branch>`` followed
        by ``git checkout -B <branch> origin/<branch>`` in the code
        worktree after prep returns. Both calls must run with
        ``cwd=<worktree>``."""
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)

        save_test_issue(tmp_path_project, key="TMP-1")
        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="queued",
            issues=["TMP-1"],
            repos=[
                {"repo": "SeidoAI/tripwire", "base_branch": "main", "branch": "feat/s1"}
            ],
            spawn_config={"invocation": {"runtime": "manual"}},
        )
        write_handoff_yaml(tmp_path_project, "s1", branch="feat/s1")

        # Capture every subprocess.run invocation through the CLI's
        # session module so we can introspect the git sequence.
        from tripwire.cli import session as session_cli

        real_run = subprocess.run
        captured: list[dict] = []

        def fake_run(cmd, *args, **kwargs):
            cmd_list = list(cmd)
            captured.append({"cmd": cmd_list, "cwd": kwargs.get("cwd")})
            # Pretend any git fetch / checkout succeeds. Everything
            # else (validation, etc.) passes through to the real run
            # so the rest of the spawn pipeline works.
            if cmd_list[:2] == ["git", "fetch"] or cmd_list[:2] == [
                "git",
                "checkout",
            ]:

                class _R:
                    returncode = 0
                    stdout = ""
                    stderr = ""

                return _R()
            return real_run(cmd, *args, **kwargs)

        # We have to stub `execute_transition` too: the worktree's
        # in-flight workflow-validation work (loader.py / schema.py /
        # workflow.yaml.j2) currently emits a `workflow/instance_missing`
        # tripwire on every transition. That's an unrelated in-flight
        # change; we only care that the fetch/checkout happens at the
        # right point, so we short-circuit the transition to make the
        # assertion possible in isolation.
        from tripwire.core.workflow import transitions as _txn

        class _OkResult:
            ok = True
            message = None
            reason = None

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch("tripwire.cli.session._resolve_clone_path", return_value=clone),
            patch.object(session_cli.subprocess, "run", fake_run),
            patch.object(_txn, "execute_transition", return_value=_OkResult()),
        ):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                [
                    "spawn",
                    "s1",
                    "--from-remote",
                    "feat/partial-work",
                    "--project-dir",
                    str(tmp_path_project),
                ],
            )

        assert result.exit_code == 0, result.output

        # We expect at least one fetch and one checkout for the
        # supplied branch, scoped to the code worktree.
        fetches = [
            c
            for c in captured
            if c["cmd"][:3] == ["git", "fetch", "origin"]
            and c["cmd"][3:] == ["feat/partial-work"]
        ]
        checkouts = [
            c
            for c in captured
            if c["cmd"][:3] == ["git", "checkout", "-B"]
            and c["cmd"][3:5] == ["feat/partial-work", "origin/feat/partial-work"]
        ]
        assert len(fetches) >= 1, captured
        assert len(checkouts) >= 1, captured

        # Both must run inside the code worktree, not from project_dir.
        s = load_session(tmp_path_project, "s1")
        wt = s.runtime_state.worktrees[0].worktree_path
        assert any(str(c["cwd"]) == str(wt) for c in fetches)
        assert any(str(c["cwd"]) == str(wt) for c in checkouts)

    def test_from_remote_help_flag_visible(self):
        runner = CliRunner()
        result = runner.invoke(session_cmd, ["spawn", "--help"])
        assert result.exit_code == 0
        assert "--from-remote" in result.output

    def test_from_remote_and_resume_are_mutually_exclusive(
        self, tmp_path_project, save_test_session
    ):
        """The two ``unclean slot`` recoveries can't be combined — the
        worktree state would scramble. CLI rejects up front."""
        save_test_session(tmp_path_project, "s1", status="paused", plan=True)

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "spawn",
                "s1",
                "--resume",
                "--from-remote",
                "feat/x",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()


class TestResumePreconditionWidened:
    """D4 — ``--resume`` accepts any non-terminal source state."""

    @pytest.mark.parametrize(
        "status",
        ["executing", "in_review", "paused", "failed"],
    )
    def test_resume_accepted_from_non_terminal_status(
        self, tmp_path_project, save_test_session, status
    ):
        """The four non-terminal post-spawn states must all be valid
        resume sources. We only assert that the status gate does NOT
        reject — the spawn itself short-circuits early because we
        don't stub the rest of the pipeline, but the gate is what we
        care about here."""
        save_test_session(tmp_path_project, "s1", status=status, plan=True)

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "spawn",
                "s1",
                "--resume",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        # Whatever happens later, the message must NOT be the
        # precondition rejection. The widening is the contract.
        assert "--resume rejected" not in result.output, (
            f"resume from {status} was rejected: {result.output}"
        )

    def test_resume_rejected_from_verified_with_backslide_message(
        self, tmp_path_project, save_test_session
    ):
        """VERIFIED is the spec-called-out failure: resume after
        verification is a backslide. The error must call this out so
        operators know to use ``reopen`` instead."""
        save_test_session(tmp_path_project, "s1", status="verified", plan=True)

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "spawn",
                "s1",
                "--resume",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code != 0
        assert "backslide" in result.output.lower()
        # Operator-recovery hint.
        assert "reopen" in result.output.lower()

    @pytest.mark.parametrize("status", ["completed", "abandoned"])
    def test_resume_rejected_from_other_terminal_statuses(
        self, tmp_path_project, save_test_session, status
    ):
        save_test_session(tmp_path_project, "s1", status=status, plan=True)

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "spawn",
                "s1",
                "--resume",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code != 0
        assert "terminal" in result.output.lower()

    @pytest.mark.parametrize("status", ["planned", "queued"])
    def test_resume_rejected_from_pre_spawn_statuses(
        self, tmp_path_project, save_test_session, status
    ):
        """planned/queued have never been spawned — ``--resume`` makes
        no sense. The error must tell the operator to drop --resume."""
        save_test_session(tmp_path_project, "s1", status=status, plan=True)

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "spawn",
                "s1",
                "--resume",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code != 0
        # Hint must call out the never-been-spawned recovery.
        assert "never been spawned" in result.output.lower()
