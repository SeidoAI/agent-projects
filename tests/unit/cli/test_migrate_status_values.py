"""Tests for `tripwire migrate status-values` — pre-v0.9.4 status rewrite."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.main import cli
from tripwire.core.parser import parse_frontmatter_body, serialize_frontmatter_body

runner = CliRunner()


def _make_project(root: Path) -> Path:
    """Build a minimal tripwire project skeleton at *root*."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.yaml").write_text(
        "name: status-mig\nkey_prefix: SM\n"
        "next_issue_number: 1\nnext_session_number: 1\n",
        encoding="utf-8",
    )
    return root


def _write_issue(project: Path, key: str, status: str) -> Path:
    """Write an issue.yaml with a hand-set ``status:`` value."""
    idir = project / "issues" / key
    idir.mkdir(parents=True, exist_ok=True)
    fm = {
        "uuid": "11111111-2222-4333-8444-555555555555",
        "id": key,
        "title": f"Test {key}",
        "status": status,
        "priority": "medium",
        "executor": "ai",
        "verifier": "required",
    }
    text = serialize_frontmatter_body(fm, "## Context\n")
    path = idir / "issue.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _write_session(project: Path, sid: str, status: str) -> Path:
    """Write a session.yaml with a hand-set ``status:`` value."""
    sdir = project / "sessions" / sid
    sdir.mkdir(parents=True, exist_ok=True)
    fm = {
        "uuid": "11111111-2222-4333-8444-555555555556",
        "id": sid,
        "name": "Test session",
        "agent": "backend-coder",
        "issues": [],
        "status": status,
        "repos": [],
    }
    text = serialize_frontmatter_body(fm, "")
    path = sdir / "session.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _read_status(path: Path) -> str:
    fm, _ = parse_frontmatter_body(path.read_text(encoding="utf-8"))
    return fm["status"]


class TestMigrateStatusValues:
    def test_rewrites_legacy_issue_statuses(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path / "p")
        a = _write_issue(project, "SM-1", "backlog")
        b = _write_issue(project, "SM-2", "in_progress")
        c = _write_issue(project, "SM-3", "done")
        d = _write_issue(project, "SM-4", "todo")
        e = _write_issue(project, "SM-5", "canceled")

        result = runner.invoke(
            cli, ["migrate", "status-values", "--project-dir", str(project)]
        )
        assert result.exit_code == 0, result.output
        assert _read_status(a) == "planned"
        assert _read_status(b) == "executing"
        assert _read_status(c) == "completed"
        assert _read_status(d) == "queued"
        assert _read_status(e) == "abandoned"
        assert "5 file(s) rewritten" in result.output

    def test_rewrites_legacy_session_statuses(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path / "p")
        a = _write_session(project, "sess-1", "active")
        b = _write_session(project, "sess-2", "waiting_for_ci")
        c = _write_session(project, "sess-3", "waiting_for_review")
        d = _write_session(project, "sess-4", "waiting_for_deploy")
        e = _write_session(project, "sess-5", "re_engaged")

        result = runner.invoke(
            cli, ["migrate", "status-values", "--project-dir", str(project)]
        )
        assert result.exit_code == 0, result.output
        assert _read_status(a) == "executing"
        assert _read_status(b) == "executing"
        assert _read_status(c) == "in_review"
        assert _read_status(d) == "executing"
        assert _read_status(e) == "executing"
        assert "5 file(s) rewritten" in result.output

    def test_canonical_only_no_op(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path / "p")
        _write_issue(project, "SM-1", "queued")
        _write_session(project, "sess-1", "executing")

        result = runner.invoke(
            cli, ["migrate", "status-values", "--project-dir", str(project)]
        )
        assert result.exit_code == 0, result.output
        assert "nothing to migrate" in result.output.lower()

    def test_idempotent_on_second_run(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path / "p")
        _write_issue(project, "SM-1", "in_progress")
        _write_session(project, "sess-1", "active")

        first = runner.invoke(
            cli, ["migrate", "status-values", "--project-dir", str(project)]
        )
        assert first.exit_code == 0, first.output
        assert "2 file(s) rewritten" in first.output

        second = runner.invoke(
            cli, ["migrate", "status-values", "--project-dir", str(project)]
        )
        assert second.exit_code == 0, second.output
        assert "nothing to migrate" in second.output.lower()

    def test_missing_directories_tolerated(self, tmp_path: Path) -> None:
        # No issues/ or sessions/ directories at all — must still pass.
        project = _make_project(tmp_path / "p")
        result = runner.invoke(
            cli, ["migrate", "status-values", "--project-dir", str(project)]
        )
        assert result.exit_code == 0, result.output
        assert "nothing to migrate" in result.output.lower()

    def test_dry_run_makes_no_changes(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path / "p")
        path = _write_issue(project, "SM-1", "in_progress")
        before = path.read_text(encoding="utf-8")

        result = runner.invoke(
            cli,
            [
                "migrate",
                "status-values",
                "--project-dir",
                str(project),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "[dry-run]" in result.output
        assert path.read_text(encoding="utf-8") == before

    def test_rejects_non_project_dir(self, tmp_path: Path) -> None:
        bare = tmp_path / "bare"
        bare.mkdir()
        result = runner.invoke(
            cli, ["migrate", "status-values", "--project-dir", str(bare)]
        )
        assert result.exit_code != 0
        assert "doesn't look like a tripwire project" in result.output

    def test_unparseable_files_skipped(self, tmp_path: Path) -> None:
        """Garbage files don't crash the command — just skipped."""
        project = _make_project(tmp_path / "p")
        idir = project / "issues" / "SM-1"
        idir.mkdir(parents=True)
        (idir / "issue.yaml").write_text("no frontmatter at all", encoding="utf-8")
        # And a real one that needs rewriting
        path = _write_issue(project, "SM-2", "backlog")

        result = runner.invoke(
            cli, ["migrate", "status-values", "--project-dir", str(project)]
        )
        assert result.exit_code == 0, result.output
        assert _read_status(path) == "planned"
