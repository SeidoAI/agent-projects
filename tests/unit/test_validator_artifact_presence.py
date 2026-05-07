"""Tests for `check_artifact_presence`.

v0.11.1: the rule consults each manifest entry's `produced_at` and skips
sessions whose `status` has not yet reached that threshold. Mirrors how
`check_issue_artifact_presence` already gates issue artifacts.
"""

from __future__ import annotations

from pathlib import Path

from tests.unit.test_validator import (  # type: ignore[import-not-found]
    write_project_yaml,
    write_session,
)
from tripwire.core.validator import validate_project


def _write_minimal_manifest(project_dir: Path) -> None:
    """Write a minimal artifact manifest requiring `developer.md`."""
    manifest_dir = project_dir / "templates" / "artifacts"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.yaml").write_text(
        "artifacts:\n"
        "  - name: developer\n"
        "    file: developer.md\n"
        "    template: developer.md.j2\n"
        "    required: true\n"
        "    produced_at: completed\n"
        "    produced_by: execution-agent\n"
        "    owned_by: execution-agent\n",
        encoding="utf-8",
    )


def test_completed_session_missing_artifact_flagged(tmp_path: Path) -> None:
    """Session at completed without required artifact → artifact/missing."""
    write_project_yaml(tmp_path)
    _write_minimal_manifest(tmp_path)
    write_session(tmp_path, "done-sess", status="completed")

    report = validate_project(tmp_path, strict=True, fix=False)

    artifact_errors = [r for r in report.errors if r.code == "artifact/missing"]
    assert artifact_errors, (
        f"expected artifact/missing error, got "
        f"{[(r.code, r.message) for r in report.errors]}"
    )


def test_non_terminal_session_skips_artifact_check(tmp_path: Path) -> None:
    """Session at executing → artifact-presence rule skips it (not yet terminal)."""
    write_project_yaml(tmp_path)
    _write_minimal_manifest(tmp_path)
    write_session(tmp_path, "live-sess", status="executing")

    report = validate_project(tmp_path, strict=True, fix=False)

    artifact_errors = [r for r in report.errors if r.code == "artifact/missing"]
    assert artifact_errors == [], (
        f"executing session should not be artifact-checked, got {artifact_errors}"
    )


def _write_two_artifact_manifest(project_dir: Path) -> None:
    """Manifest declaring `early.md` at in_review and `late.md` at completed.

    Used to verify per-artifact `produced_at` gating: a session at in_review
    should be checked against the early entry but not the late one.
    """
    manifest_dir = project_dir / "templates" / "artifacts"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.yaml").write_text(
        "artifacts:\n"
        "  - name: early\n"
        "    file: early.md\n"
        "    template: early.md.j2\n"
        "    required: true\n"
        "    produced_at: in_review\n"
        "    produced_by: execution-agent\n"
        "    owned_by: execution-agent\n"
        "  - name: late\n"
        "    file: late.md\n"
        "    template: late.md.j2\n"
        "    required: true\n"
        "    produced_at: completed\n"
        "    produced_by: pm\n"
        "    owned_by: pm\n",
        encoding="utf-8",
    )


def test_in_review_session_flags_early_artifact_only(tmp_path: Path) -> None:
    """Session at in_review missing both artifacts → only the early one fires."""
    write_project_yaml(tmp_path)
    _write_two_artifact_manifest(tmp_path)
    write_session(tmp_path, "rev-sess", status="in_review")

    report = validate_project(tmp_path, strict=True, fix=False)

    missing = {r.message for r in report.errors if r.code == "artifact/missing"}
    # Exactly one artifact/missing — for early.md (produced_at: in_review).
    assert len(missing) == 1, (
        f"expected exactly one artifact/missing for early.md, got {missing}"
    )
    msg = missing.pop()
    assert "early.md" in msg
    assert "in_review" in msg
    assert "late.md" not in msg


def test_completed_session_flags_both_artifacts(tmp_path: Path) -> None:
    """Session at completed missing both → both produce artifact/missing."""
    write_project_yaml(tmp_path)
    _write_two_artifact_manifest(tmp_path)
    write_session(tmp_path, "done-sess", status="completed")

    report = validate_project(tmp_path, strict=True, fix=False)

    missing_files = {
        r.message.split("'")[-2] if "'" in r.message else r.message
        for r in report.errors
        if r.code == "artifact/missing"
    }
    # Both early.md and late.md should fire.
    assert any("early.md" in m for m in missing_files), missing_files
    assert any("late.md" in m for m in missing_files), missing_files
