"""Unit tests for `core/validator.py` (the validation gate).

Tests every check in the catalogue and every auto-fix path. Uses helper
fixtures that build minimal valid projects on tmp_path so each test can
focus on the specific failure mode it's exercising.
"""

from __future__ import annotations

import uuid as _uuid
from pathlib import Path
from typing import Any

import pytest
import yaml

from keel.core.parser import serialize_frontmatter_body
from keel.core.validator import (
    ValidationReport,
    validate_project,
)

# ============================================================================
# Fixtures and helpers
# ============================================================================


def write_project_yaml(project_dir: Path, **overrides: Any) -> None:
    """Write a minimal valid project.yaml with sensible defaults."""
    config: dict[str, Any] = {
        "name": "test",
        "key_prefix": "TST",
        "base_branch": "main",
        "statuses": [
            "backlog",
            "todo",
            "in_progress",
            "verifying",
            "reviewing",
            "testing",
            "ready",
            "updating",
            "done",
            "canceled",
        ],
        "status_transitions": {
            "backlog": ["todo", "canceled"],
            "todo": ["in_progress", "backlog", "canceled"],
            "in_progress": ["verifying", "todo", "canceled"],
            "verifying": ["reviewing", "in_progress"],
            "reviewing": ["testing", "in_progress"],
            "testing": ["ready", "reviewing"],
            "ready": ["updating"],
            "updating": ["done"],
            "done": [],
            "canceled": ["backlog"],
        },
        "next_issue_number": 1,
        "next_session_number": 1,
        "repos": {
            "SeidoAI/web-app-backend": {"local": None},
            "SeidoAI/web-app-infrastructure": {"local": None},
        },
    }
    config.update(overrides)
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )


def write_issue(
    project_dir: Path,
    key: str,
    *,
    body: str | None = None,
    **frontmatter_overrides: Any,
) -> Path:
    """Write a syntactically valid issue with all required body sections."""
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(exist_ok=True)

    fm: dict[str, Any] = {
        "uuid": str(_uuid.uuid4()),
        "id": key,
        "title": f"Test {key}",
        "status": "todo",
        "priority": "medium",
        "executor": "ai",
        "verifier": "required",
        "created_at": "2026-04-07T10:00:00",
        "updated_at": "2026-04-07T10:00:00",
    }
    fm.update(frontmatter_overrides)

    if body is None:
        body = (
            "## Context\nWith [[user-model]] reference.\n"
            "\n## Implements\nREQ-1\n"
            "\n## Repo scope\n- SeidoAI/web-app-backend\n"
            "\n## Requirements\n- thing\n"
            "\n## Execution constraints\nIf ambiguous, stop and ask.\n"
            "\n## Acceptance criteria\n- [ ] thing\n"
            "\n## Test plan\n```\nuv run pytest\n```\n"
            "\n## Dependencies\nnone\n"
            "\n## Definition of Done\n- [ ] done\n"
        )
    text = serialize_frontmatter_body(fm, body)
    path = issues_dir / f"{key}.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def write_node(
    project_dir: Path,
    node_id: str,
    *,
    body: str = "Description.\n",
    **frontmatter_overrides: Any,
) -> Path:
    nodes_dir = project_dir / "graph" / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)
    fm: dict[str, Any] = {
        "uuid": str(_uuid.uuid4()),
        "id": node_id,
        "type": "model",
        "name": "User",
        "status": "active",
        "created_at": "2026-04-07T10:00:00",
        "updated_at": "2026-04-07T10:00:00",
    }
    fm.update(frontmatter_overrides)
    text = serialize_frontmatter_body(fm, body)
    path = nodes_dir / f"{node_id}.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def write_session(
    project_dir: Path,
    session_id: str,
    **frontmatter_overrides: Any,
) -> Path:
    sessions_dir = project_dir / "sessions"
    sessions_dir.mkdir(exist_ok=True)
    fm: dict[str, Any] = {
        "uuid": str(_uuid.uuid4()),
        "id": session_id,
        "name": "Test session",
        "agent": "backend-coder",
        "issues": [],
        "status": "planned",
        "repos": [],
    }
    fm.update(frontmatter_overrides)
    text = serialize_frontmatter_body(fm, "")
    path = sessions_dir / f"{session_id}.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    write_project_yaml(tmp_path)
    return tmp_path


@pytest.fixture
def project_with_one_node(tmp_path: Path) -> Path:
    write_project_yaml(tmp_path)
    write_node(tmp_path, "user-model")
    return tmp_path


@pytest.fixture
def project_with_one_issue_one_node(tmp_path: Path) -> Path:
    write_project_yaml(tmp_path)
    write_node(tmp_path, "user-model")
    write_issue(tmp_path, "TST-1")
    return tmp_path


def codes(report: ValidationReport, severity: str = "error") -> list[str]:
    """Helper: extract the codes for a given severity from a report."""
    items = (
        report.errors
        if severity == "error"
        else report.warnings
        if severity == "warning"
        else report.fixed
    )
    return [r.code for r in items]


# ============================================================================
# Bootstrap & loading
# ============================================================================


class TestLoading:
    def test_missing_project_yaml(self, tmp_path: Path) -> None:
        report = validate_project(tmp_path)
        assert report.exit_code == 2
        assert "schema/project_missing" in codes(report)

    def test_invalid_project_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "project.yaml").write_text("not: a: valid: mapping:\n")
        report = validate_project(tmp_path)
        assert report.exit_code == 2
        assert any(c.startswith("schema/project") for c in codes(report))

    def test_unparseable_issue(self, empty_project: Path) -> None:
        (empty_project / "issues").mkdir()
        (empty_project / "issues" / "TST-1.yaml").write_text("no frontmatter at all")
        report = validate_project(empty_project)
        assert "issue/parse_error" in codes(report)

    def test_schema_invalid_issue(self, empty_project: Path) -> None:
        (empty_project / "issues").mkdir()
        # Missing required fields like title, status, etc.
        (empty_project / "issues" / "TST-1.yaml").write_text(
            "---\nuuid: 7c3a4b1d-9f2e-4a8c-b5d6-1e2f3a4b5c6d\nid: TST-1\n---\nbody\n"
        )
        report = validate_project(empty_project)
        assert "issue/schema_invalid" in codes(report)

    def test_clean_project_passes(self, project_with_one_issue_one_node: Path) -> None:
        report = validate_project(project_with_one_issue_one_node)
        # May have warnings but no errors.
        assert report.exit_code in (0, 1)
        assert report.errors == []


# ============================================================================
# Schema / UUID / ID format
# ============================================================================


class TestUuidPresence:
    def test_missing_uuid_is_error(self, empty_project: Path) -> None:
        # Hand-write an issue without uuid (bypassing the helper).
        (empty_project / "issues").mkdir()
        text = serialize_frontmatter_body(
            {
                "id": "TST-1",
                "title": "x",
                "status": "todo",
                "priority": "medium",
                "executor": "ai",
                "verifier": "required",
            },
            "## Context\n[[user-model]]\n\n## Implements\nx\n\n## Repo scope\nx\n\n## Requirements\nx\n\n## Execution constraints\nstop and ask.\n\n## Acceptance criteria\n- [ ] x\n\n## Test plan\nx\n\n## Dependencies\nnone\n\n## Definition of Done\n- [ ] done\n",
        )
        (empty_project / "issues" / "TST-1.yaml").write_text(text)
        report = validate_project(empty_project)
        assert "uuid/missing" in codes(report)


class TestIdFormat:
    def test_wrong_prefix_is_error(self, empty_project: Path) -> None:
        write_issue(empty_project, "OTHER-1")
        report = validate_project(empty_project)
        assert "id/wrong_prefix" in codes(report)


# ============================================================================
# Enum values
# ============================================================================


class TestEnumValues:
    def test_invalid_issue_status(self, empty_project: Path) -> None:
        write_issue(empty_project, "TST-1", status="bogus_status")
        report = validate_project(empty_project)
        assert "enum/issue_status" in codes(report)

    def test_invalid_priority(self, empty_project: Path) -> None:
        write_issue(empty_project, "TST-1", priority="ultra_high")
        report = validate_project(empty_project)
        assert "enum/priority" in codes(report)

    def test_valid_status_passes(self, empty_project: Path) -> None:
        write_issue(empty_project, "TST-1", status="in_progress")
        report = validate_project(empty_project)
        assert "enum/issue_status" not in codes(report)

    def test_invalid_node_type(self, empty_project: Path) -> None:
        write_node(empty_project, "x", type="bogus_type")
        report = validate_project(empty_project)
        assert "enum/node_type" in codes(report)

    def test_invalid_session_status(self, empty_project: Path) -> None:
        write_session(empty_project, "wave1", status="bogus_status")
        report = validate_project(empty_project)
        assert "enum/session_status" in codes(report)


# ============================================================================
# Reference integrity
# ============================================================================


class TestReferenceIntegrity:
    def test_dangling_reference_error(self, empty_project: Path) -> None:
        body = (
            "## Context\nuses [[nonexistent-node]]\n\n"
            "## Implements\nx\n\n## Repo scope\nx\n\n## Requirements\nx\n\n"
            "## Execution constraints\nstop and ask.\n\n"
            "## Acceptance criteria\n- [ ] x\n\n## Test plan\nx\n\n"
            "## Dependencies\nnone\n\n## Definition of Done\n- [ ] x\n"
        )
        write_issue(empty_project, "TST-1", body=body)
        report = validate_project(empty_project)
        assert "ref/dangling" in codes(report)

    def test_blocked_by_unknown_issue(self, empty_project: Path) -> None:
        write_node(empty_project, "user-model")
        write_issue(empty_project, "TST-1", blocked_by=["TST-99"])
        report = validate_project(empty_project)
        assert "ref/blocked_by" in codes(report)

    def test_parent_unknown_issue(self, empty_project: Path) -> None:
        write_node(empty_project, "user-model")
        write_issue(empty_project, "TST-1", parent="TST-99")
        report = validate_project(empty_project)
        assert "ref/parent" in codes(report)

    def test_undeclared_repo(self, empty_project: Path) -> None:
        write_node(empty_project, "user-model")
        write_issue(empty_project, "TST-1", repo="other/repo")
        report = validate_project(empty_project)
        assert "ref/repo" in codes(report)

    def test_node_related_unknown(self, empty_project: Path) -> None:
        write_node(empty_project, "node-a", related=["nonexistent"])
        report = validate_project(empty_project)
        assert "ref/related" in codes(report)

    def test_session_unknown_issue(self, empty_project: Path) -> None:
        write_session(empty_project, "wave1", issues=["TST-99"])
        report = validate_project(empty_project)
        assert "ref/session_issue" in codes(report)


# ============================================================================
# Bi-directional related
# ============================================================================


class TestBidirectionalRelated:
    def test_one_sided_related_warns(self, empty_project: Path) -> None:
        write_node(empty_project, "node-a", related=["node-b"])
        write_node(empty_project, "node-b")  # missing back-reference
        report = validate_project(empty_project)
        assert "bidi/related" in codes(report, "warning")

    def test_symmetric_related_clean(self, empty_project: Path) -> None:
        write_node(empty_project, "node-a", related=["node-b"])
        write_node(empty_project, "node-b", related=["node-a"])
        report = validate_project(empty_project)
        assert "bidi/related" not in codes(report, "warning")


# ============================================================================
# Issue body structure
# ============================================================================


class TestIssueBodyStructure:
    def test_missing_heading_warns(self, empty_project: Path) -> None:
        write_node(empty_project, "user-model")
        write_issue(
            empty_project,
            "TST-1",
            body="## Context\n[[user-model]]\nstop and ask\n## Acceptance criteria\n- [ ] x\n",
        )
        report = validate_project(empty_project)
        assert "body/missing_heading" in codes(report, "warning")

    def test_no_acceptance_checkbox_warns(self, empty_project: Path) -> None:
        write_node(empty_project, "user-model")
        body = (
            "## Context\n[[user-model]]\n\n## Implements\nx\n\n## Repo scope\nx\n\n"
            "## Requirements\nx\n\n## Execution constraints\nstop and ask.\n\n"
            "## Acceptance criteria\nNo checkboxes here.\n\n## Test plan\nx\n\n"
            "## Dependencies\nnone\n\n## Definition of Done\n- [ ] x\n"
        )
        write_issue(empty_project, "TST-1", body=body)
        report = validate_project(empty_project)
        assert "body/no_acceptance_checkbox" in codes(report, "warning")

    def test_no_stop_and_ask_warns(self, empty_project: Path) -> None:
        write_node(empty_project, "user-model")
        body = (
            "## Context\n[[user-model]]\n\n## Implements\nx\n\n## Repo scope\nx\n\n"
            "## Requirements\nx\n\n## Execution constraints\nproceed.\n\n"
            "## Acceptance criteria\n- [ ] x\n\n## Test plan\nx\n\n"
            "## Dependencies\nnone\n\n## Definition of Done\n- [ ] x\n"
        )
        write_issue(empty_project, "TST-1", body=body)
        report = validate_project(empty_project)
        assert "body/no_stop_and_ask" in codes(report, "warning")

    def test_no_references_warns(self, empty_project: Path) -> None:
        body = (
            "## Context\nNo refs.\n\n## Implements\nx\n\n## Repo scope\nx\n\n"
            "## Requirements\nx\n\n## Execution constraints\nstop and ask.\n\n"
            "## Acceptance criteria\n- [ ] x\n\n## Test plan\nx\n\n"
            "## Dependencies\nnone\n\n## Definition of Done\n- [ ] x\n"
        )
        write_issue(empty_project, "TST-1", body=body)
        report = validate_project(empty_project)
        assert "body/no_references" in codes(report, "warning")


# ============================================================================
# Status transitions
# ============================================================================


class TestStatusTransitions:
    def test_unreachable_status(self, tmp_path: Path) -> None:
        # Build a project where `done` exists but isn't reachable from backlog.
        write_project_yaml(
            tmp_path,
            statuses=["backlog", "todo", "done", "orphan"],
            status_transitions={
                "backlog": ["todo"],
                "todo": ["done"],
                "done": [],
                "orphan": [],
            },
        )
        write_node(tmp_path, "user-model")
        write_issue(tmp_path, "TST-1", status="orphan")
        report = validate_project(tmp_path)
        assert "status/unreachable" in codes(report)


# ============================================================================
# ID collisions
# ============================================================================


class TestIdCollisions:
    def test_two_issues_same_id(self, empty_project: Path) -> None:
        # Write two issue files claiming the same id but with different uuids.
        write_node(empty_project, "user-model")
        write_issue(empty_project, "TST-1")
        # Now overwrite with a second file at a different location? Issues
        # are stored by filename = id, so we can't have two on disk. Instead
        # we simulate by modifying the existing file's uuid then writing a
        # second file with the same id and a different filename.
        # Easiest: write a second file `TST-1-dup.yaml` with id TST-1.
        (empty_project / "issues" / "TST-1-dup.yaml").write_text(
            (empty_project / "issues" / "TST-1.yaml")
            .read_text()
            .replace(
                str(_uuid.UUID("00000000-0000-0000-0000-000000000000")),
                str(_uuid.uuid4()),
            )
        )
        # The two files have different uuids (the dup got a uuid replacement
        # via re-load + we mutate). But our replace above won't trigger since
        # the uuid in TST-1.yaml is real, not the placeholder. Do it directly:
        original = (empty_project / "issues" / "TST-1.yaml").read_text()
        # Force a different uuid in the dup
        new_uuid = str(_uuid.uuid4())
        # Replace the line `uuid: <something>` with `uuid: <new>`
        lines = original.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("uuid:"):
                lines[i] = f"uuid: {new_uuid}"
                break
        (empty_project / "issues" / "TST-1-dup.yaml").write_text(
            "\n".join(lines) + "\n"
        )

        report = validate_project(empty_project)
        assert "collision/id" in codes(report)


# ============================================================================
# Sequence drift
# ============================================================================


class TestSequenceDrift:
    def test_drifted_counter_warns(self, empty_project: Path) -> None:
        write_node(empty_project, "user-model")
        # Project has next_issue_number=1 but we write an issue with key TST-5
        write_issue(empty_project, "TST-5")
        report = validate_project(empty_project)
        assert "sequence/drift" in codes(report, "warning")


# ============================================================================
# Timestamps
# ============================================================================


class TestTimestamps:
    def test_missing_timestamps_warn(self, empty_project: Path) -> None:
        write_node(empty_project, "user-model")
        write_issue(empty_project, "TST-1", created_at=None, updated_at=None)
        report = validate_project(empty_project)
        warning_codes = codes(report, "warning")
        assert "timestamp/missing" in warning_codes


# ============================================================================
# Comment provenance
# ============================================================================


class TestCommentProvenance:
    def test_invalid_comment_type_caught(self, empty_project: Path) -> None:
        write_node(empty_project, "user-model")
        write_issue(empty_project, "TST-1")
        comment_dir = empty_project / "docs" / "issues" / "TST-1" / "comments"
        comment_dir.mkdir(parents=True)
        text = serialize_frontmatter_body(
            {
                "uuid": str(_uuid.uuid4()),
                "issue_key": "TST-1",
                "author": "claude",
                "type": "bogus_type",
                "created_at": "2026-04-07T10:00:00",
            },
            "body",
        )
        (comment_dir / "001-test.yaml").write_text(text)
        report = validate_project(empty_project)
        assert "enum/comment_type" in codes(report)


# ============================================================================
# Project standards
# ============================================================================


class TestProjectStandards:
    def test_referenced_but_missing_warns(self, empty_project: Path) -> None:
        write_node(empty_project, "user-model")
        body = (
            "## Context\n[[user-model]]\n\n## Implements\nx\n\n## Repo scope\nx\n\n"
            "## Requirements\nSee standards.md.\n\n"
            "## Execution constraints\nstop and ask.\n\n"
            "## Acceptance criteria\n- [ ] x\n\n## Test plan\nx\n\n"
            "## Dependencies\nnone\n\n## Definition of Done\n- [ ] x\n"
        )
        write_issue(empty_project, "TST-1", body=body)
        report = validate_project(empty_project)
        assert "standards/missing" in codes(report, "warning")


# ============================================================================
# Auto-fix
# ============================================================================


class TestAutoFix:
    def test_fix_missing_uuid(self, empty_project: Path) -> None:
        # Hand-write an issue without uuid.
        (empty_project / "issues").mkdir()
        body = (
            "## Context\n[[user-model]]\n\n## Implements\nx\n\n## Repo scope\nx\n\n"
            "## Requirements\nx\n\n## Execution constraints\nstop and ask.\n\n"
            "## Acceptance criteria\n- [ ] x\n\n## Test plan\nx\n\n"
            "## Dependencies\nnone\n\n## Definition of Done\n- [ ] x\n"
        )
        text = serialize_frontmatter_body(
            {
                "id": "TST-1",
                "title": "x",
                "status": "todo",
                "priority": "medium",
                "executor": "ai",
                "verifier": "required",
                "created_at": "2026-04-07T10:00:00",
                "updated_at": "2026-04-07T10:00:00",
            },
            body,
        )
        (empty_project / "issues" / "TST-1.yaml").write_text(text)
        write_node(empty_project, "user-model")

        report = validate_project(empty_project, fix=True)
        # Fix recorded
        assert "uuid/missing" in [f.code for f in report.fixed]
        # File now has a uuid
        new_text = (empty_project / "issues" / "TST-1.yaml").read_text()
        assert new_text.startswith("---\nuuid:")

    def test_fix_sequence_drift(self, empty_project: Path) -> None:
        write_node(empty_project, "user-model")
        write_issue(empty_project, "TST-5")
        report = validate_project(empty_project, fix=True)
        assert "sequence/drift" in [f.code for f in report.fixed]
        # project.yaml updated
        raw = yaml.safe_load((empty_project / "project.yaml").read_text())
        assert raw["next_issue_number"] == 6

    def test_fix_missing_timestamps(self, empty_project: Path) -> None:
        write_node(empty_project, "user-model")
        write_issue(empty_project, "TST-1", created_at=None, updated_at=None)
        report = validate_project(empty_project, fix=True)
        assert "timestamp/missing" in [f.code for f in report.fixed]

    def test_fix_bidirectional_related(self, empty_project: Path) -> None:
        write_node(empty_project, "node-a", related=["node-b"])
        write_node(empty_project, "node-b")
        report = validate_project(empty_project, fix=True)
        assert "bidi/related" in [f.code for f in report.fixed]
        # node-b's file should now contain node-a in its related list.
        b_text = (empty_project / "graph" / "nodes" / "node-b.yaml").read_text()
        assert "node-a" in b_text

    def test_fix_sorted_lists(self, empty_project: Path) -> None:
        write_node(
            empty_project,
            "user-model",
            tags=["zebra", "alpha", "monkey"],
        )
        report = validate_project(empty_project, fix=True)
        sorted_codes = [f.code for f in report.fixed if f.code == "sorted/list"]
        assert len(sorted_codes) >= 1
        text = (empty_project / "graph" / "nodes" / "user-model.yaml").read_text()
        # alpha should come before monkey before zebra in the sorted list
        a = text.find("alpha")
        m = text.find("monkey")
        z = text.find("zebra")
        assert 0 < a < m < z


# ============================================================================
# Strict mode and exit codes
# ============================================================================


class TestStrictMode:
    def test_strict_promotes_warnings(
        self, project_with_one_issue_one_node: Path
    ) -> None:
        # Add a freshness warning by writing a node with a stale source path.
        # Easiest: write a body with no references → triggers
        # `body/no_references` warning.
        body = (
            "## Context\nNo refs.\n\n## Implements\nx\n\n## Repo scope\nx\n\n"
            "## Requirements\nx\n\n## Execution constraints\nstop and ask.\n\n"
            "## Acceptance criteria\n- [ ] x\n\n## Test plan\nx\n\n"
            "## Dependencies\nnone\n\n## Definition of Done\n- [ ] x\n"
        )
        # Overwrite the issue with no-references body
        write_issue(project_with_one_issue_one_node, "TST-1", body=body)

        normal = validate_project(project_with_one_issue_one_node, strict=False)
        strict = validate_project(project_with_one_issue_one_node, strict=True)
        assert normal.exit_code == 1  # warnings only
        assert strict.exit_code == 2  # warnings promoted
        assert any(e.code == "body/no_references" for e in strict.errors)


class TestJsonOutput:
    def test_json_shape(self, empty_project: Path) -> None:
        report = validate_project(empty_project)
        out = report.to_json()
        assert out["version"] == 1
        assert "exit_code" in out
        assert "summary" in out
        assert "errors" in out["summary"]
        assert "warnings" in out["summary"]
        assert "fixed" in out["summary"]
        assert "cache_rebuilt" in out["summary"]
        assert "duration_ms" in out["summary"]
        assert isinstance(out["errors"], list)
        assert isinstance(out["warnings"], list)
        assert isinstance(out["fixed"], list)

    def test_error_entry_shape(self, empty_project: Path) -> None:
        write_issue(empty_project, "OTHER-1")  # wrong prefix
        report = validate_project(empty_project)
        out = report.to_json()
        assert any(e["code"] == "id/wrong_prefix" for e in out["errors"])
        # Error entries have severity, message, file, field
        for e in out["errors"]:
            assert "code" in e
            assert "severity" in e
            assert "message" in e

    def test_json_has_categories(self, empty_project: Path) -> None:
        write_issue(empty_project, "OTHER-1")  # triggers id/wrong_prefix
        report = validate_project(empty_project)
        out = report.to_json()
        assert "categories" in out
        cats = out["categories"]
        assert isinstance(cats, dict)
        # id/wrong_prefix should produce an "id" category
        assert "id" in cats
        assert cats["id"]["errors"] >= 1
        # every category has the three keys
        for _cat, counts in cats.items():
            assert set(counts.keys()) == {"errors", "warnings", "fixed"}
            assert all(isinstance(v, int) for v in counts.values())


class TestCategorySummary:
    """Tests for the category_summary property on ValidationReport."""

    def test_empty_report_has_no_categories(self) -> None:
        report = ValidationReport()
        assert report.category_summary == {}

    def test_single_error_counted(self) -> None:
        from keel.core.validator import CheckResult

        report = ValidationReport(
            errors=[CheckResult(code="ref/dangling", severity="error", message="x")]
        )
        cats = report.category_summary
        assert "ref" in cats
        assert cats["ref"]["errors"] == 1
        assert cats["ref"]["warnings"] == 0
        assert cats["ref"]["fixed"] == 0

    def test_mixed_severities_and_categories(self) -> None:
        from keel.core.validator import CheckResult

        report = ValidationReport(
            errors=[
                CheckResult(code="ref/dangling", severity="error", message="a"),
                CheckResult(code="ref/parent", severity="error", message="b"),
                CheckResult(code="schema/invalid", severity="error", message="c"),
            ],
            warnings=[
                CheckResult(code="ref/related", severity="warning", message="d"),
                CheckResult(code="freshness/stale", severity="warning", message="e"),
            ],
            fixed=[
                CheckResult(code="timestamp/missing", severity="fixed", message="f"),
            ],
        )
        cats = report.category_summary
        assert cats["ref"] == {"errors": 2, "warnings": 1, "fixed": 0}
        assert cats["schema"] == {"errors": 1, "warnings": 0, "fixed": 0}
        assert cats["freshness"] == {"errors": 0, "warnings": 1, "fixed": 0}
        assert cats["timestamp"] == {"errors": 0, "warnings": 0, "fixed": 1}


class TestUuidV4Validation:
    """Tests for the uuid/not_v4 check (v0.2)."""

    def test_real_uuid4_passes(self, empty_project: Path) -> None:
        import uuid
        write_issue(empty_project, "TST-1", uuid=str(uuid.uuid4()))
        report = validate_project(empty_project)
        assert not any(e.code == "uuid/not_v4" for e in report.errors)

    def test_hand_crafted_uuid_fails(self, empty_project: Path) -> None:
        # Version nibble is '1' (not '4') and variant is '0' (not 8-b)
        write_issue(empty_project, "TST-1", uuid="10a1b2c3-d4e5-1f6a-0b8c-9d0e1f2a3b4c")
        report = validate_project(empty_project)
        assert any(e.code == "uuid/not_v4" for e in report.errors)

    def test_uuid_with_correct_version_but_wrong_variant(self, empty_project: Path) -> None:
        # Version nibble is '4' but variant is '0' (should be 8/9/a/b)
        write_issue(empty_project, "TST-1", uuid="10a1b2c3-d4e5-4f6a-0b8c-9d0e1f2a3b4c")
        report = validate_project(empty_project)
        assert any(e.code == "uuid/not_v4" for e in report.errors)


class TestCoverageWarnings:
    """Tests for coverage heuristic warnings (v0.2)."""

    def test_issue_with_no_node_refs_warns(self, empty_project: Path) -> None:
        write_issue(
            empty_project, "TST-1",
            body="## Context\nNo concept references here.\n"
        )
        report = validate_project(empty_project)
        assert any(
            w.code == "coverage/no_nodes_referenced" for w in report.warnings
        )

    def test_issue_with_node_ref_no_warning(self, empty_project: Path) -> None:
        write_node(empty_project, "user-model")
        write_issue(
            empty_project, "TST-1",
            body="## Context\nUses [[user-model]] for lookups.\n"
        )
        report = validate_project(empty_project)
        assert not any(
            w.code == "coverage/no_nodes_referenced" for w in report.warnings
        )
