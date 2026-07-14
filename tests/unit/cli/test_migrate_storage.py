"""Tests for `tripwire migrate storage` — v0.13.1 layout cutover.

The command moves a pre-v0.13.1 project (top-level ``sessions/``,
``issues/``, ``nodes/`` plus ``docs/issues/`` for PM-written
artifacts) to the consolidated ``instances/<type>/`` layout and
renames runtime markers under ``.tripwire/`` to the workflow-keyed
naming scheme.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from textwrap import dedent

import yaml
from click.testing import CliRunner

from tripwire.cli.main import cli

runner = CliRunner()


def _make_pre_layout_project(root: Path) -> Path:
    """Build a pre-v0.13.1 flat-layout project at *root* with seed data."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "flat",
                "key_prefix": "FLT",
                "next_issue_number": 2,
                "next_session_number": 2,
                "statuses": [
                    "planned",
                    "queued",
                    "executing",
                    "in_review",
                    "verified",
                    "completed",
                ],
                "status_transitions": {
                    "planned": ["queued"],
                    "queued": ["executing"],
                    "executing": ["in_review"],
                    "in_review": ["verified"],
                    "verified": ["completed"],
                    "completed": [],
                },
                "repos": {"SeidoAI/flat": {"local": None}},
            }
        ),
        encoding="utf-8",
    )
    (root / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                  - id: queued
                routes:
                  - id: planned-to-queued
                    actor: pm-agent
                    from: planned
                    to: queued
                    kind: forward
            """
        ),
        encoding="utf-8",
    )

    # Sessions
    (root / "sessions" / "s1").mkdir(parents=True)
    (root / "sessions" / "s1" / "session.yaml").write_text(
        "---\nid: s1\nstatus: planned\n---\n", encoding="utf-8"
    )
    (root / "sessions" / "s1" / "artifacts").mkdir()
    (root / "sessions" / "s1" / "artifacts" / "plan.md").write_text(
        "# plan\n", encoding="utf-8"
    )
    # Issues
    (root / "issues" / "FLT-1").mkdir(parents=True)
    (root / "issues" / "FLT-1" / "issue.yaml").write_text(
        "---\nid: FLT-1\ntitle: x\n---\n", encoding="utf-8"
    )
    # Nodes
    (root / "nodes").mkdir()
    (root / "nodes" / "node-a.yaml").write_text(
        "---\nid: node-a\nname: A\n---\n", encoding="utf-8"
    )
    # Legacy docs/issues subtree
    (root / "docs" / "issues" / "FLT-1").mkdir(parents=True)
    (root / "docs" / "issues" / "FLT-1" / "developer.md").write_text(
        "# dev notes\n", encoding="utf-8"
    )
    return root


def _git_init(project: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=project,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True)
    subprocess.run(["git", "add", "."], cwd=project, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial flat layout"],
        cwd=project,
        check=True,
    )


def _write_legacy_lock_and_ack(project: Path) -> None:
    """Plant a pre-v0.13.1 lock + ack so the migration renames them."""
    locks = project / ".tripwire" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    (locks / "transition-s1.lock").write_text("pid=42\n", encoding="utf-8")

    acks = project / ".tripwire" / "acks"
    acks.mkdir(parents=True, exist_ok=True)
    (acks / "self-review-s1.json").write_text(
        json.dumps({"fix_commits": ["abc"]}), encoding="utf-8"
    )


class TestMigrateStorage:
    def test_happy_path_moves_top_level_dirs(self, tmp_path: Path):
        """Pre-v0.13.1 project: dirs relocate under instances/, validate clean."""
        project = _make_pre_layout_project(tmp_path / "proj")
        _git_init(project)

        result = runner.invoke(
            cli,
            [
                "project",
                "migrate",
                "storage",
                "--project-dir",
                str(project),
                "--skip-validate",
            ],
        )
        assert result.exit_code == 0, result.output

        # Sources gone, destinations populated.
        assert not (project / "sessions").exists()
        assert not (project / "issues").exists()
        assert not (project / "nodes").exists()
        assert (project / "instances" / "sessions" / "s1" / "session.yaml").is_file()
        assert (project / "instances" / "issues" / "FLT-1" / "issue.yaml").is_file()
        assert (project / "instances" / "nodes" / "node-a.yaml").is_file()
        # docs/issues/<KEY>/* relocated under instances/issues/<KEY>/docs/
        assert (
            project / "instances" / "issues" / "FLT-1" / "docs" / "developer.md"
        ).is_file()
        assert not (project / "docs" / "issues").exists()

    def test_idempotent_second_run_is_noop(self, tmp_path: Path):
        """Running twice succeeds the second time without crashing."""
        project = _make_pre_layout_project(tmp_path / "proj")
        _git_init(project)
        first = runner.invoke(
            cli,
            [
                "project",
                "migrate",
                "storage",
                "--project-dir",
                str(project),
                "--skip-validate",
            ],
        )
        assert first.exit_code == 0, first.output

        second = runner.invoke(
            cli,
            [
                "project",
                "migrate",
                "storage",
                "--project-dir",
                str(project),
                "--skip-validate",
            ],
        )
        assert second.exit_code == 0, second.output
        assert "nothing to migrate" in second.output.lower()

    def test_refuses_to_overwrite_without_yes(self, tmp_path: Path):
        """Pre-existing files under instances/<type>/ block migration."""
        project = _make_pre_layout_project(tmp_path / "proj")
        # Pre-populate an instances/sessions entry, simulating a
        # partially-migrated tree.
        (project / "instances" / "sessions" / "preexisting").mkdir(parents=True)
        (project / "instances" / "sessions" / "preexisting" / "stub.yaml").write_text(
            "stub\n", encoding="utf-8"
        )
        _git_init(project)

        result = runner.invoke(
            cli,
            [
                "project",
                "migrate",
                "storage",
                "--project-dir",
                str(project),
                "--skip-validate",
            ],
        )
        assert result.exit_code != 0
        assert "refusing to merge" in result.output.lower()

        # With --yes, the merge proceeds.
        merged = runner.invoke(
            cli,
            [
                "project",
                "migrate",
                "storage",
                "--project-dir",
                str(project),
                "--yes",
                "--skip-validate",
            ],
        )
        assert merged.exit_code == 0, merged.output
        # Pre-existing entry survives.
        assert (
            project / "instances" / "sessions" / "preexisting" / "stub.yaml"
        ).is_file()
        # Newly-migrated entry from the legacy `sessions/` is also there.
        assert (project / "instances" / "sessions" / "s1" / "session.yaml").is_file()

    def test_detects_git_repo_and_uses_git_mv(self, tmp_path: Path):
        """git mv preserves history when the project is a repo."""
        project = _make_pre_layout_project(tmp_path / "proj")
        _git_init(project)

        result = runner.invoke(
            cli,
            [
                "project",
                "migrate",
                "storage",
                "--project-dir",
                str(project),
                "--skip-validate",
            ],
        )
        assert result.exit_code == 0, result.output

        # `git status` reports the staged rename. The migrate command
        # leaves the work staged for the operator to commit.
        status = subprocess.run(
            ["git", "status", "--porcelain=v1"],
            cwd=project,
            capture_output=True,
            text=True,
            check=True,
        )
        # Renames appear as `R  old -> new` lines.
        assert "R" in status.stdout, (
            "git mv should have staged renames; git status:\n" + status.stdout
        )
        assert "instances/sessions/s1/session.yaml" in status.stdout

    def test_non_git_project_uses_plain_mv(self, tmp_path: Path):
        """Without a .git/ dir, migrate falls back to shutil.move."""
        project = _make_pre_layout_project(tmp_path / "proj")
        # No _git_init — just a plain directory.

        result = runner.invoke(
            cli,
            [
                "project",
                "migrate",
                "storage",
                "--project-dir",
                str(project),
                "--skip-validate",
            ],
        )
        assert result.exit_code == 0, result.output
        assert (project / "instances" / "sessions" / "s1" / "session.yaml").is_file()
        assert not (project / "sessions").exists()

    def test_renames_legacy_lock_and_ack(self, tmp_path: Path):
        """Pre-v0.13.1 lock + ack filenames get the workflow segment."""
        project = _make_pre_layout_project(tmp_path / "proj")
        _write_legacy_lock_and_ack(project)
        # Not a git repo — locks/acks aren't tracked anyway.

        result = runner.invoke(
            cli,
            [
                "project",
                "migrate",
                "storage",
                "--project-dir",
                str(project),
                "--skip-validate",
            ],
        )
        assert result.exit_code == 0, result.output

        # Lock got the workflow segment.
        assert not (project / ".tripwire" / "locks" / "transition-s1.lock").exists()
        assert (
            project / ".tripwire" / "locks" / "transition-coding-session-s1.lock"
        ).is_file()

        # Ack got the workflow prefix.
        assert not (project / ".tripwire" / "acks" / "self-review-s1.json").exists()
        assert (
            project / ".tripwire" / "acks" / "coding-session-self-review-s1.json"
        ).is_file()

    def test_missing_project_yaml_rejected(self, tmp_path: Path):
        """No project.yaml at the root — refuse with explanation."""
        result = runner.invoke(
            cli, ["project", "migrate", "storage", "--project-dir", str(tmp_path)]
        )
        assert result.exit_code != 0
        assert "doesn't look like a tripwire project" in result.output

    def test_help_describes_command(self):
        """`tripwire migrate storage --help` advertises the command."""
        result = runner.invoke(cli, ["project", "migrate", "storage", "--help"])
        assert result.exit_code == 0
        assert "instances/" in result.output
        assert "--yes" in result.output
