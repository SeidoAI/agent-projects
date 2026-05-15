"""Unit tests for `core/status.py` (status transition reachability).

v0.13.1 (B8): the helpers now take a workflow-derived adjacency map
``{from_status: [to_status, ...]}`` rather than a ``ProjectConfig``.
The caller builds the map via :func:`build_issue_transitions`, which
reads ``workflow.yaml``'s ``issue-closure`` workflow.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import ClassVar

from tripwire.core.status import (
    build_issue_transitions,
    is_status_reachable,
    is_transition_allowed,
    reachable_statuses,
)


class TestIsTransitionAllowed:
    def test_allowed(self) -> None:
        t = {"queued": ["executing"], "executing": ["done"]}
        assert is_transition_allowed(t, "queued", "executing")

    def test_disallowed(self) -> None:
        t = {"queued": ["executing"], "executing": ["done"]}
        assert not is_transition_allowed(t, "queued", "done")

    def test_self_transition_always_allowed(self) -> None:
        t = {"queued": ["executing"]}
        assert is_transition_allowed(t, "queued", "queued")

    def test_unknown_source(self) -> None:
        t = {"queued": ["executing"]}
        assert not is_transition_allowed(t, "qa", "done")


class TestReachableStatuses:
    def test_full_seido_default_flow(self) -> None:
        t = {
            "planned": ["queued", "abandoned"],
            "queued": ["executing", "planned", "abandoned"],
            "executing": ["in_review", "queued", "abandoned"],
            "in_review": ["verified", "executing"],
            "verified": ["done", "in_review"],
            "done": [],
            "abandoned": ["planned"],
        }
        reachable = reachable_statuses(t)
        # Every declared status should be reachable from backlog
        assert reachable == set(t.keys())

    def test_isolated_status_not_reachable(self) -> None:
        t = {
            "planned": ["queued"],
            "queued": ["done"],
            "done": [],
            "orphan": [],
        }
        reachable = reachable_statuses(t)
        assert "orphan" not in reachable
        assert "done" in reachable

    def test_no_transitions_returns_declared_statuses(self) -> None:
        # With no workflow routes the helper falls back to "every
        # declared status is trivially reachable" — preserves the
        # pre-v0.13.1 escape hatch for projects without an
        # issue-closure workflow yet.
        reachable = reachable_statuses({}, declared_statuses=["a", "b", "c"])
        assert reachable == {"a", "b", "c"}


class TestIsStatusReachable:
    def test_reachable(self) -> None:
        t = {"planned": ["queued"], "queued": ["done"], "done": []}
        assert is_status_reachable(t, "done")

    def test_unreachable(self) -> None:
        t = {"planned": ["queued"], "queued": ["done"], "done": [], "orphan": []}
        assert not is_status_reachable(t, "orphan")


class TestShippedTemplateCanonicalLifecycle:
    """The shipped `workflow.yaml.j2` issue-closure block must reach
    every status the project enum declares from the `planned` start
    state — otherwise the structure validator's
    ``check_status_transitions`` raises `status/unreachable` for any
    issue not in `planned`.

    Regression for v0.13.1 (B8): the original consolidation shipped a
    2-status (closing/closed) workflow that broke reachability for the
    8-status flow projects actually use.
    """

    CANONICAL_STATUSES: ClassVar[set[str]] = {
        "planned",
        "queued",
        "executing",
        "in_review",
        "verified",
        "completed",
        "abandoned",
        "deferred",
    }

    def test_shipped_template_reaches_all_canonical_statuses(
        self, tmp_path: Path
    ) -> None:
        # Plant the shipped template verbatim into a temp project dir,
        # then exercise the same reachability pipeline the validator uses.
        template = Path("src/tripwire/templates/workflow.yaml.j2").read_text(
            encoding="utf-8"
        )
        (tmp_path / "workflow.yaml").write_text(template, encoding="utf-8")
        t = build_issue_transitions(tmp_path)
        reachable = reachable_statuses(
            t, declared_statuses=sorted(self.CANONICAL_STATUSES)
        )
        assert self.CANONICAL_STATUSES <= reachable, sorted(
            self.CANONICAL_STATUSES - reachable
        )


class TestBuildIssueTransitions:
    def test_returns_empty_when_no_workflow_file(self, tmp_path: Path) -> None:
        # No workflow.yaml on disk → empty map; reachability falls back
        # to "trivially reachable".
        assert build_issue_transitions(tmp_path) == {}

    def test_collapses_issue_closure_routes_to_adjacency(self, tmp_path: Path) -> None:
        (tmp_path / "workflow.yaml").write_text(
            dedent(
                """\
                workflow_schema_version: 1
                workflows:
                  issue-closure:
                    actor: pm-agent
                    trigger: command.pm-issue-close
                    instance:
                      storage_path: instances/issues/{instance_id}/issue.yaml
                      status_field: status
                      status_enum: [planned, queued, completed]
                    statuses:
                      - id: closing
                      - id: closed
                        terminal: true
                    routes:
                      - id: r1
                        actor: pm-agent
                        from: planned
                        to: queued
                        kind: forward
                      - id: r2
                        actor: pm-agent
                        from: queued
                        to: completed
                        kind: forward
                      - id: r-boundary
                        actor: pm-agent
                        from: source:issue
                        to: closing
                        kind: forward
                """
            ),
            encoding="utf-8",
        )
        t = build_issue_transitions(tmp_path)
        # Status-to-status edges flatten cleanly; boundary-port routes
        # (source:/sink:) are skipped.
        assert t["planned"] == ["queued"]
        assert t["queued"] == ["completed"]
        assert "source:issue" not in t
        # The instance.status_enum values appear as keys (even if no
        # outbound edges yet) so reachability sees them at all.
        assert "completed" in t
