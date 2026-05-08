"""Tests for `tripwire migrate workflow` (WS6)."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from click.testing import CliRunner


def _v012_template_text() -> str:
    """Return a minimal v0.12-shape workflow.yaml that will pass the
    ``looks_like_v012`` heuristic in the migration command."""
    return dedent(
        """\
        workflows:
          coding-session:
            actor: a
            trigger: t
            statuses:
              - id: planned
                next: completed
              - id: completed
                terminal: true
          pm-scoping:
            actor: a
            trigger: t
            statuses: []
          pm-triage:
            actor: a
            trigger: t
            statuses: []
          pm-monitor:
            actor: a
            trigger: t
            statuses: []
          code-review:
            actor: a
            trigger: t
            statuses: []
        """
    )


def test_migrate_workflow_no_op_when_already_v013(tmp_path: Path) -> None:
    from tripwire.cli.migrate import migrate_cmd

    (tmp_path / "workflow.yaml").write_text(
        "workflow_schema_version: 1\nworkflows: {}\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        migrate_cmd,
        ["workflow", "--project-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "already on v0.13" in result.output


def test_migrate_workflow_overwrites_v012_template(tmp_path: Path) -> None:
    from tripwire.cli.migrate import migrate_cmd

    (tmp_path / "workflow.yaml").write_text(_v012_template_text(), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        migrate_cmd,
        ["workflow", "--project-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    new_text = (tmp_path / "workflow.yaml").read_text(encoding="utf-8")
    assert "workflow_schema_version: 1" in new_text
    bak = (tmp_path / "workflow.yaml.bak").read_text(encoding="utf-8")
    assert "workflow_schema_version: 1" not in bak  # backup is the v0.12 file


def test_migrate_workflow_dry_run_does_not_write(tmp_path: Path) -> None:
    from tripwire.cli.migrate import migrate_cmd

    original = _v012_template_text()
    (tmp_path / "workflow.yaml").write_text(original, encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        migrate_cmd,
        ["workflow", "--project-dir", str(tmp_path), "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "[dry-run]" in result.output
    assert (tmp_path / "workflow.yaml").read_text(encoding="utf-8") == original
    assert not (tmp_path / "workflow.yaml.bak").exists()


def test_migrate_workflow_refuses_unknown_shape_without_yes(tmp_path: Path) -> None:
    from tripwire.cli.migrate import migrate_cmd

    (tmp_path / "workflow.yaml").write_text(
        "workflows:\n  custom-thing:\n    actor: a\n    trigger: t\n    statuses: []\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        migrate_cmd,
        ["workflow", "--project-dir", str(tmp_path)],
    )
    assert result.exit_code != 0
    assert "--yes" in result.output


def test_migrate_workflow_overwrites_with_yes(tmp_path: Path) -> None:
    from tripwire.cli.migrate import migrate_cmd

    (tmp_path / "workflow.yaml").write_text(
        "workflows:\n  custom-thing:\n    actor: a\n    trigger: t\n    statuses: []\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        migrate_cmd,
        ["workflow", "--project-dir", str(tmp_path), "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert "Migrated" in result.output
    new_text = (tmp_path / "workflow.yaml").read_text(encoding="utf-8")
    assert "workflow_schema_version: 1" in new_text


def test_migrate_workflow_no_workflow_file(tmp_path: Path) -> None:
    from tripwire.cli.migrate import migrate_cmd

    runner = CliRunner()
    result = runner.invoke(
        migrate_cmd,
        ["workflow", "--project-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "nothing to migrate" in result.output
