"""Tests for v0.7.5 C2 — `tripwire session reopen <id>`.

The `reopen` command moves a completed session back into a state
where ``tripwire session spawn <id> --resume`` can re-engage the
agent for PR-fix iteration. Per spec §2.C2 the command must:

- Refuse non-completed sessions (lifecycle stays explicit).
- Require a `--reason` flag so the audit trail explains why.
- Flip status away from `completed` so `spawn --resume` accepts it.
- Flip every recorded draft PR ready→draft via ``gh pr ready --undo``.
- Append a stub `## PM follow-up` section to the session's plan.md
  if the section isn't already there (closes the "PM forgot to update
  plan" failure mode).
- Record one audit-log entry under
  `~/.tripwire/logs/<project-slug>/audit.jsonl` capturing reason +
  timestamp.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core import paths
from tripwire.core.session_store import load_session


def _stub_gh(monkeypatch):
    """Capture every subprocess.run invocation; stub gh; pass git through."""
    from tripwire.cli import session as session_cli

    real_run = subprocess.run
    calls: list[dict] = []

    def fake_run(cmd, *args, **kwargs):
        cmd_list = list(cmd)
        calls.append({"cmd": cmd_list, "cwd": kwargs.get("cwd")})

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        if cmd_list and cmd_list[0] == "gh":
            return _R()
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(session_cli.subprocess, "run", fake_run)
    return calls


class TestSessionReopen:
    def test_flips_completed_session_to_paused(
        self, tmp_path_project, save_test_session, monkeypatch, tmp_path
    ):
        save_test_session(
            tmp_path_project,
            "s1",
            status="completed",
            plan=True,
        )
        _stub_gh(monkeypatch)
        monkeypatch.setenv("TRIPWIRE_LOG_DIR", str(tmp_path / "logs"))

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "reopen",
                "s1",
                "--reason",
                "PR review feedback",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code == 0, result.output

        s = load_session(tmp_path_project, "s1")
        # `paused` is the existing status that `spawn --resume` accepts.
        assert s.status == "paused"

    def test_requires_reason_flag(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="completed", plan=True)

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["reopen", "s1", "--project-dir", str(tmp_path_project)],
        )
        # Click exits 2 on missing required option.
        assert result.exit_code != 0
        assert "reason" in result.output.lower()

    def test_rejects_non_completed_session(
        self, tmp_path_project, save_test_session, monkeypatch, tmp_path
    ):
        save_test_session(tmp_path_project, "s1", status="planned", plan=True)
        _stub_gh(monkeypatch)
        monkeypatch.setenv("TRIPWIRE_LOG_DIR", str(tmp_path / "logs"))

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "reopen",
                "s1",
                "--reason",
                "x",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code != 0
        assert "completed" in result.output.lower()

    def test_appends_pm_followup_section_when_missing(
        self, tmp_path_project, save_test_session, monkeypatch, tmp_path
    ):
        save_test_session(
            tmp_path_project,
            "s1",
            status="completed",
            plan=True,
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": "/tmp/code",
                        "worktree_path": "/tmp/code-wt-s1",
                        "branch": "feat/s1",
                        "draft_pr_url": "https://github.com/test/code/pull/10",
                    },
                ]
            },
        )
        _stub_gh(monkeypatch)
        monkeypatch.setenv("TRIPWIRE_LOG_DIR", str(tmp_path / "logs"))

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "reopen",
                "s1",
                "--reason",
                "PR review feedback",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code == 0, result.output

        plan_text = paths.session_plan_path(tmp_path_project, "s1").read_text(
            encoding="utf-8"
        )
        assert "## PM follow-up" in plan_text
        assert "https://github.com/test/code/pull/10" in plan_text

    def test_skips_pm_followup_when_section_already_present(
        self, tmp_path_project, save_test_session, monkeypatch, tmp_path
    ):
        save_test_session(tmp_path_project, "s1", status="completed", plan=True)
        plan_path = paths.session_plan_path(tmp_path_project, "s1")
        plan_path.write_text(
            "# Plan\n\nbody\n\n## PM follow-up\n\nexisting body, do not append twice\n",
            encoding="utf-8",
        )
        _stub_gh(monkeypatch)
        monkeypatch.setenv("TRIPWIRE_LOG_DIR", str(tmp_path / "logs"))

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "reopen",
                "s1",
                "--reason",
                "x",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code == 0, result.output

        text = plan_path.read_text(encoding="utf-8")
        # Exactly one `## PM follow-up` heading.
        assert text.count("## PM follow-up") == 1
        assert "existing body, do not append twice" in text

    def test_flips_drafts_ready_to_draft_via_gh_pr_ready_undo(
        self, tmp_path_project, save_test_session, monkeypatch, tmp_path
    ):
        save_test_session(
            tmp_path_project,
            "s1",
            status="completed",
            plan=True,
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": "/tmp/code",
                        "worktree_path": "/tmp/code-wt-s1",
                        "branch": "feat/s1",
                        "draft_pr_url": "https://github.com/test/code/pull/10",
                    },
                    {
                        "repo": "tripwire-v0",
                        "clone_path": "/tmp/proj",
                        "worktree_path": "/tmp/proj-wt-s1",
                        "branch": "proj/s1",
                        "draft_pr_url": "https://github.com/test/proj/pull/11",
                    },
                ]
            },
        )
        calls = _stub_gh(monkeypatch)
        monkeypatch.setenv("TRIPWIRE_LOG_DIR", str(tmp_path / "logs"))

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "reopen",
                "s1",
                "--reason",
                "x",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code == 0, result.output

        ready_undo_calls = [
            c
            for c in calls
            if c["cmd"][:3] == ["gh", "pr", "ready"] and "--undo" in c["cmd"]
        ]
        assert len(ready_undo_calls) == 2
        urls = {c["cmd"][3] for c in ready_undo_calls}
        assert urls == {
            "https://github.com/test/code/pull/10",
            "https://github.com/test/proj/pull/11",
        }

    def test_records_audit_entry(
        self, tmp_path_project, save_test_session, monkeypatch, tmp_path
    ):
        save_test_session(
            tmp_path_project,
            "s1",
            status="completed",
            plan=True,
        )
        _stub_gh(monkeypatch)
        log_dir = tmp_path / "logs"
        monkeypatch.setenv("TRIPWIRE_LOG_DIR", str(log_dir))

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "reopen",
                "s1",
                "--reason",
                "PR review feedback",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code == 0, result.output

        # Audit log under TRIPWIRE_LOG_DIR with one record.
        candidates = list(log_dir.rglob("audit.jsonl"))
        assert candidates, f"no audit.jsonl found under {log_dir}"
        records = [
            json.loads(line)
            for line in Path(candidates[0]).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(records) == 1
        rec = records[0]
        assert rec["session_id"] == "s1"
        assert rec["action"] == "session_reopen"
        assert rec["reason"] == "PR review feedback"
