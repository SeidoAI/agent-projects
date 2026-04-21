"""Tests for tripwire.ui.services.issue_service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tripwire.ui.services.issue_service import (
    IssueDetail,
    IssueFilters,
    IssueSummary,
    get_issue,
    list_issues,
    validate_issue,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_BODY_WITH_REFS = (
    "## Context\nSee [[user-model]] and [[missing-node]].\n"
    "Also [[ISS-2]] cross-ref.\n"
    "\n## Implements\n[[user-model]]\n"
    "\n## Repo scope\n- SeidoAI/web-app-backend\n"
    "\n## Requirements\n- thing\n"
    "\n## Execution constraints\nIf ambiguous, stop and ask.\n"
    "\n## Acceptance criteria\n- [ ] thing\n"
    "\n## Test plan\n```\nuv run pytest\n```\n"
    "\n## Dependencies\nnone\n"
    "\n## Definition of Done\n- [ ] done\n"
)


# ---------------------------------------------------------------------------
# list_issues
# ---------------------------------------------------------------------------


class TestListIssues:
    def test_empty_when_no_issues(self, tmp_path_project: Path):
        assert list_issues(tmp_path_project) == []

    def test_returns_all_by_default(self, tmp_path_project, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1")
        save_test_issue(tmp_path_project, "TST-2")

        result = list_issues(tmp_path_project)
        assert {s.id for s in result} == {"TST-1", "TST-2"}
        assert all(isinstance(s, IssueSummary) for s in result)

    def test_filter_by_status(self, tmp_path_project, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1", status="todo")
        save_test_issue(tmp_path_project, "TST-2", status="done")

        result = list_issues(tmp_path_project, IssueFilters(status="done"))
        assert [s.id for s in result] == ["TST-2"]

    def test_filter_by_executor(self, tmp_path_project, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1", executor="ai")
        save_test_issue(tmp_path_project, "TST-2", executor="human")

        result = list_issues(tmp_path_project, IssueFilters(executor="human"))
        assert [s.id for s in result] == ["TST-2"]

    def test_filter_by_label(self, tmp_path_project, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1", labels=["domain/backend"])
        save_test_issue(tmp_path_project, "TST-2", labels=["domain/frontend"])

        result = list_issues(tmp_path_project, IssueFilters(label="domain/frontend"))
        assert [s.id for s in result] == ["TST-2"]

    def test_filter_by_parent(self, tmp_path_project, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1")
        save_test_issue(tmp_path_project, "TST-2", parent="TST-1")
        save_test_issue(tmp_path_project, "TST-3")

        result = list_issues(tmp_path_project, IssueFilters(parent="TST-1"))
        assert [s.id for s in result] == ["TST-2"]

    def test_filters_combine_with_and(self, tmp_path_project, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1", status="todo", executor="ai")
        save_test_issue(tmp_path_project, "TST-2", status="todo", executor="human")

        result = list_issues(
            tmp_path_project,
            IssueFilters(status="todo", executor="ai"),
        )
        assert [s.id for s in result] == ["TST-1"]

    def test_is_epic_true_when_epic_label(self, tmp_path_project, save_test_issue):
        save_test_issue(
            tmp_path_project, "TST-1", labels=["type/epic", "domain/backend"]
        )
        save_test_issue(tmp_path_project, "TST-2")

        by_id = {s.id: s for s in list_issues(tmp_path_project)}
        assert by_id["TST-1"].is_epic is True
        assert by_id["TST-2"].is_epic is False

    def test_is_blocked_by_upstream_status(self, tmp_path_project, save_test_issue):
        # TST-1 is in progress → TST-2 blocked_by=[TST-1] is blocked
        save_test_issue(tmp_path_project, "TST-1", status="todo")
        save_test_issue(tmp_path_project, "TST-2", status="todo", blocked_by=["TST-1"])
        # TST-3 is blocked_by a done issue → not blocked
        save_test_issue(tmp_path_project, "TST-4", status="done")
        save_test_issue(tmp_path_project, "TST-3", status="todo", blocked_by=["TST-4"])

        by_id = {s.id: s for s in list_issues(tmp_path_project)}
        assert by_id["TST-2"].is_blocked is True
        assert by_id["TST-3"].is_blocked is False
        assert by_id["TST-1"].is_blocked is False  # no blockers at all

    def test_is_blocked_when_blocker_missing(self, tmp_path_project, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1", status="todo", blocked_by=["TST-99"])
        by_id = {s.id: s for s in list_issues(tmp_path_project)}
        assert by_id["TST-1"].is_blocked is True


# ---------------------------------------------------------------------------
# get_issue
# ---------------------------------------------------------------------------


class TestGetIssue:
    def test_returns_detail(self, tmp_path_project, save_test_issue, save_test_node):
        save_test_issue(tmp_path_project, "TST-1")

        detail = get_issue(tmp_path_project, "TST-1")
        assert isinstance(detail, IssueDetail)
        assert detail.id == "TST-1"
        assert "## Context" in detail.body

    def test_refs_resolve_to_node_issue_or_dangling(
        self,
        tmp_path_project,
        save_test_issue,
        save_test_node,
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-2")
        save_test_issue(tmp_path_project, "TST-1", body=_BODY_WITH_REFS)

        detail = get_issue(tmp_path_project, "TST-1")
        by_ref = {r.ref: r for r in detail.refs}

        # the body references user-model (node), ISS-2 (missing issue key),
        # and missing-node (dangling)
        assert by_ref["user-model"].resolves_as == "node"
        assert by_ref["user-model"].is_stale is False
        assert by_ref["missing-node"].resolves_as == "dangling"
        # ISS-2 doesn't match TST-2 — this is a dangling issue-like slug
        # (slug rule means node-slugs only, and ISS-2 doesn't match slug).
        # Confirm slug-only refs are honoured: "iss-2"-style would be found
        # but "ISS-2" in uppercase won't be — the reference parser only
        # matches lowercase slugs.
        assert "ISS-2" not in by_ref

    def test_refs_stale_flag_from_cache(
        self,
        tmp_path_project,
        save_test_issue,
        save_test_node,
        monkeypatch,
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-1", body=_BODY_WITH_REFS)

        # Prime the graph cache so stale_nodes contains user-model.
        from tripwire.core import graph_cache

        graph_cache.full_rebuild(tmp_path_project)
        cache = graph_cache.load_index(tmp_path_project)
        assert cache is not None
        cache.stale_nodes = ["user-model"]
        graph_cache.save_index(tmp_path_project, cache)

        detail = get_issue(tmp_path_project, "TST-1")
        by_ref = {r.ref: r for r in detail.refs}
        assert by_ref["user-model"].is_stale is True

    def test_refs_deduplicated(self, tmp_path_project, save_test_issue, save_test_node):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-1", body=_BODY_WITH_REFS)

        detail = get_issue(tmp_path_project, "TST-1")
        ids = [r.ref for r in detail.refs]
        assert ids.count("user-model") == 1

    def test_get_not_found(self, tmp_path_project):
        with pytest.raises(FileNotFoundError):
            get_issue(tmp_path_project, "TST-404")

    def test_epic_detection_in_detail(self, tmp_path_project, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1", labels=["type/epic"])
        detail = get_issue(tmp_path_project, "TST-1")
        assert detail.is_epic is True

    def test_dto_round_trips_via_json(
        self, tmp_path_project, save_test_issue, save_test_node
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-1", body=_BODY_WITH_REFS)
        detail = get_issue(tmp_path_project, "TST-1")
        encoded = json.loads(detail.model_dump_json())
        rebuilt = IssueDetail.model_validate(encoded)
        assert rebuilt == detail


# ---------------------------------------------------------------------------
# validate_issue
# ---------------------------------------------------------------------------


class TestValidateIssue:
    def test_returns_validation_report_for_clean_issue(
        self, tmp_path_project, save_test_issue, save_test_node
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-1")

        report = validate_issue(tmp_path_project, "TST-1")
        # Report is scoped to this issue's findings only.
        for finding in report.errors + report.warnings:
            if finding.file is not None:
                assert finding.file.startswith("issues/TST-1/")

    def test_scoped_to_one_issue(
        self, tmp_path_project, save_test_issue, save_test_node
    ):
        save_test_node(tmp_path_project, "user-model")
        # TST-1 has a dangling blocked_by → produces an error for TST-1
        save_test_issue(tmp_path_project, "TST-1", blocked_by=["TST-999"])
        # TST-2 is clean — should NOT show up in TST-1's report
        save_test_issue(tmp_path_project, "TST-2")

        report = validate_issue(tmp_path_project, "TST-1")
        for finding in report.errors + report.warnings:
            if finding.file is not None:
                assert not finding.file.startswith("issues/TST-2/")

    def test_missing_issue_returns_empty_report(
        self, tmp_path_project, save_test_issue, save_test_node
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-1")

        report = validate_issue(tmp_path_project, "TST-404")
        assert report.exit_code == 0
        assert report.errors == []
        assert report.warnings == []
