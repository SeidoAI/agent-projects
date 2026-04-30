"""Strict staleness validation for `[[id@vN]]` pins (KUI-127 / A2).

The validator emits `references/stale_pin` when a pinned reference's
target has had a PM-marked contract change since the pin was set.

v0.9 ships the PM-marked path only: the entity carries a
`contract_changed_at` field naming the most recent version where a
contract change happened. A pin to any version strictly below that
value is stale. The LLM-classifier path is deferred to v1.0 (TW1-6).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tripwire.core.validator._types import LoadedEntity, ValidationContext
from tripwire.core.validator.checks.references import check_no_stale_pins
from tripwire.models import ConceptNode, Issue


def _make_entity(model, body: str) -> LoadedEntity:
    return LoadedEntity(
        rel_path="issues/TST-1/issue.yaml",
        raw_frontmatter=model.model_dump(mode="python"),
        body=body,
        model=model,
    )


def _ctx(*, issues=None, nodes=None) -> ValidationContext:
    return ValidationContext(
        project_dir=Path("/tmp/proj"),
        project_config=None,
        issues=list(issues or []),
        nodes=list(nodes or []),
        sessions=[],
        comments=[],
        issue_load_errors=[],
        session_load_errors=[],
        comment_load_errors=[],
    )


class TestStalePinValidator:
    def _build_target_node(
        self,
        *,
        version: int,
        contract_changed_at: int | None = None,
    ) -> ConceptNode:
        return ConceptNode(
            id="user-model",
            type="model",
            name="User",
            version=version,
            contract_changed_at=contract_changed_at,
        )

    def _build_issue_with_pin(self, pin_version: int) -> Issue:
        return Issue(
            id="TST-1",
            title="t",
            status="todo",
            priority="medium",
            executor="ai",
            verifier="required",
            body=f"See [[user-model@v{pin_version}]] for details.\n",
        )

    def test_stale_pin_emits_error_when_contract_change_after_pin(self):
        target = self._build_target_node(version=3, contract_changed_at=2)
        issue = self._build_issue_with_pin(pin_version=1)

        ctx = _ctx(
            issues=[_make_entity(issue, issue.body)],
            nodes=[
                LoadedEntity(
                    rel_path="nodes/user-model.yaml",
                    raw_frontmatter=target.model_dump(mode="python"),
                    body="",
                    model=target,
                )
            ],
        )
        results = check_no_stale_pins(ctx)
        stale = [r for r in results if r.code == "references/stale_pin"]
        assert len(stale) == 1
        assert stale[0].severity == "error"
        # Fix-hint should point at A5 / `node check --update`.
        assert "node check" in (stale[0].fix_hint or "")

    def test_pin_at_or_above_contract_change_is_not_stale(self):
        target = self._build_target_node(version=3, contract_changed_at=2)
        issue = self._build_issue_with_pin(pin_version=2)

        ctx = _ctx(
            issues=[_make_entity(issue, issue.body)],
            nodes=[
                LoadedEntity(
                    rel_path="nodes/user-model.yaml",
                    raw_frontmatter=target.model_dump(mode="python"),
                    body="",
                    model=target,
                )
            ],
        )
        results = check_no_stale_pins(ctx)
        stale = [r for r in results if r.code == "references/stale_pin"]
        assert stale == []

    def test_no_contract_change_marker_no_stale_emission(self):
        """Without a PM mark, version drift alone does not trip staleness."""
        target = self._build_target_node(version=5, contract_changed_at=None)
        issue = self._build_issue_with_pin(pin_version=1)

        ctx = _ctx(
            issues=[_make_entity(issue, issue.body)],
            nodes=[
                LoadedEntity(
                    rel_path="nodes/user-model.yaml",
                    raw_frontmatter=target.model_dump(mode="python"),
                    body="",
                    model=target,
                )
            ],
        )
        results = check_no_stale_pins(ctx)
        stale = [r for r in results if r.code == "references/stale_pin"]
        assert stale == []

    def test_bare_reference_never_stale(self):
        """`[[id]]` (no pin) is "latest" and never stale."""
        target = self._build_target_node(version=5, contract_changed_at=4)
        issue = Issue(
            id="TST-1",
            title="t",
            status="todo",
            priority="medium",
            executor="ai",
            verifier="required",
            body="See [[user-model]] for details.\n",
        )
        ctx = _ctx(
            issues=[_make_entity(issue, issue.body)],
            nodes=[
                LoadedEntity(
                    rel_path="nodes/user-model.yaml",
                    raw_frontmatter=target.model_dump(mode="python"),
                    body="",
                    model=target,
                )
            ],
        )
        results = check_no_stale_pins(ctx)
        stale = [r for r in results if r.code == "references/stale_pin"]
        assert stale == []
