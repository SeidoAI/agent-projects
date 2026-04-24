"""Tests for I7 — `tripwire session scaffold <id>`.

The artifact manifest declares every file a session must produce,
including `verification-checklist.md` (planning-phase, PM-owned,
required). Queue-time readiness checks this file exists, but until
I7 there was no scaffolder — PM copy-pasted from other sessions.

Scope of scaffold is intentionally narrow: planning-phase PM-owned
required artifacts only. task-checklist.md (execution-agent-owned,
in_progress phase) is NOT scaffolded — that artifact is the agent's
to write.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from tripwire.cli.session import session_cmd


def _seed_manifest_with_verification(project_dir: Path) -> None:
    """Overwrite the minimal conftest manifest with a realistic entry
    for verification-checklist.md. Leaves task-checklist.md absent so
    the "planning-phase-only" filter has something to exclude."""
    manifest = {
        "artifacts": [
            {
                "name": "plan",
                "file": "plan.md",
                "template": "plan.md.j2",
                "produced_at": "planning",
                "produced_by": "pm",
                "owned_by": "pm",
                "required": True,
            },
            {
                "name": "verification-checklist",
                "file": "verification-checklist.md",
                "template": "verification-checklist.md.j2",
                "produced_at": "planning",
                "produced_by": "pm",
                "owned_by": "pm",
                "required": True,
            },
            {
                "name": "task-checklist",
                "file": "task-checklist.md",
                "template": "task-checklist.md.j2",
                "produced_at": "in_progress",
                "produced_by": "execution-agent",
                "owned_by": "execution-agent",
                "required": True,
            },
        ]
    }
    (project_dir / "templates" / "artifacts" / "manifest.yaml").write_text(
        yaml.safe_dump(manifest)
    )
    # Templates under the project-local artifacts dir. Scaffold reads
    # these (init copies them from the package at project-create time).
    tpl_dir = project_dir / "templates" / "artifacts"
    (tpl_dir / "plan.md.j2").write_text("# Plan — {{ session_id }}\n")
    (tpl_dir / "verification-checklist.md.j2").write_text(
        "# Verification Checklist — {{ session_id }}\n\n"
        "Agent: {{ agent }}\n"
        "Issues: {{ issues | length }}\n"
    )
    (tpl_dir / "task-checklist.md.j2").write_text("# Tasks — {{ session_id }}\n")


class TestSessionScaffold:
    def test_scaffold_writes_verification_checklist(
        self, tmp_path_project, save_test_session
    ):
        _seed_manifest_with_verification(tmp_path_project)
        save_test_session(
            tmp_path_project, "s1", status="planned", issues=["T-1", "T-2"]
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["scaffold", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        vc_path = tmp_path_project / "sessions" / "s1" / "verification-checklist.md"
        assert vc_path.is_file()
        body = vc_path.read_text()
        # Rendered with session context — not just a placeholder.
        assert "s1" in body
        assert "Agent: backend-coder" in body
        assert "Issues: 2" in body

    def test_scaffold_skips_in_progress_phase_artifacts(
        self, tmp_path_project, save_test_session
    ):
        """task-checklist.md is produced_at=in_progress, not planning.
        Default scaffold must not touch it — it's the execution agent's
        to write."""
        _seed_manifest_with_verification(tmp_path_project)
        save_test_session(tmp_path_project, "s1", status="planned")

        runner = CliRunner()
        runner.invoke(
            session_cmd,
            ["scaffold", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert not (tmp_path_project / "sessions" / "s1" / "task-checklist.md").exists()

    def test_scaffold_refuses_existing_without_force(
        self, tmp_path_project, save_test_session
    ):
        _seed_manifest_with_verification(tmp_path_project)
        save_test_session(tmp_path_project, "s1", status="planned")

        sess_dir = tmp_path_project / "sessions" / "s1"
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "verification-checklist.md").write_text("CUSTOM\n")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["scaffold", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        assert "Skipping" in result.output
        # File preserved — scaffold is refusing to overwrite.
        assert (sess_dir / "verification-checklist.md").read_text() == "CUSTOM\n"

    def test_scaffold_force_overwrites(self, tmp_path_project, save_test_session):
        _seed_manifest_with_verification(tmp_path_project)
        save_test_session(tmp_path_project, "s1", status="planned")

        sess_dir = tmp_path_project / "sessions" / "s1"
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "verification-checklist.md").write_text("CUSTOM\n")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "scaffold",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--force",
            ],
        )
        assert result.exit_code == 0, result.output
        body = (sess_dir / "verification-checklist.md").read_text()
        assert "CUSTOM" not in body
        assert "Verification Checklist — s1" in body

    def test_scaffold_specific_artifact_by_name(
        self, tmp_path_project, save_test_session
    ):
        _seed_manifest_with_verification(tmp_path_project)
        save_test_session(tmp_path_project, "s1", status="planned")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "scaffold",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--artifact",
                "verification-checklist.md",
            ],
        )
        assert result.exit_code == 0, result.output
        sess_dir = tmp_path_project / "sessions" / "s1"
        assert (sess_dir / "verification-checklist.md").is_file()
        # plan.md is ALSO a planning-phase pm-owned required artifact in
        # the test manifest, but --artifact scoped us to one.
        assert not (sess_dir / "plan.md").is_file()

    def test_scaffold_unknown_artifact_errors(
        self, tmp_path_project, save_test_session
    ):
        _seed_manifest_with_verification(tmp_path_project)
        save_test_session(tmp_path_project, "s1", status="planned")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "scaffold",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--artifact",
                "nonsense.md",
            ],
        )
        assert result.exit_code != 0
        assert "not declared in manifest" in result.output


class TestSessionScaffoldHandoff:
    """Default scaffold also writes handoff.yaml with a derived branch.

    Covers the v0.7.3 item E gap: handoff.yaml lives outside the
    artifact manifest but is a planning-phase PM-owned file. PMs
    shouldn't have to hand-craft it.
    """

    def test_default_writes_handoff_with_derived_branch(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_manifest_with_verification(tmp_path_project)
        save_test_issue(tmp_path_project, "T-1", kind="feat")
        save_test_session(
            tmp_path_project, "auth-rework", status="planned", issues=["T-1"]
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["scaffold", "auth-rework", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        handoff_path = tmp_path_project / "sessions" / "auth-rework" / "handoff.yaml"
        assert handoff_path.is_file()
        body = handoff_path.read_text()
        # Branch derived from kind=feat + session-id slug.
        assert "branch: feat/auth-rework" in body
        # Sentinel fields rendered correctly.
        assert "session_id: auth-rework" in body
        assert "handed_off_by: pm" in body

    def test_no_handoff_flag_suppresses_write(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_manifest_with_verification(tmp_path_project)
        save_test_issue(tmp_path_project, "T-1", kind="feat")
        save_test_session(tmp_path_project, "s1", status="planned", issues=["T-1"])

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "scaffold",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--no-handoff",
            ],
        )
        assert result.exit_code == 0, result.output
        assert not (tmp_path_project / "sessions" / "s1" / "handoff.yaml").is_file()

    def test_handoff_skipped_when_already_exists_without_force(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_manifest_with_verification(tmp_path_project)
        save_test_issue(tmp_path_project, "T-1", kind="feat")
        save_test_session(tmp_path_project, "s1", status="planned", issues=["T-1"])

        sess_dir = tmp_path_project / "sessions" / "s1"
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "handoff.yaml").write_text("CUSTOM HANDOFF\n")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["scaffold", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        # User's existing handoff is preserved.
        assert (sess_dir / "handoff.yaml").read_text() == "CUSTOM HANDOFF\n"
