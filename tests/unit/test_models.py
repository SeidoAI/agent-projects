"""Unit tests for the Pydantic data models.

Cover:
- Default field generation (UUIDs)
- Required vs optional fields
- ID format validation (Issue, ConceptNode)
- Round-trip serialisation (model_validate -> model_dump preserves data)
- Multi-repo session schema (RepoBinding)
- Graph edge alias handling (from/to vs from_id/to_id)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest

from keel.models import (
    AgentSession,
    ArtifactSpec,
    Comment,
    ConceptNode,
    EngagementEntry,
    GraphEdge,
    Issue,
    NodeSource,
    ProjectConfig,
    RepoBinding,
    RepoEntry,
    SessionOrchestration,
)


class TestIssue:
    def test_uuid_auto_generated(self) -> None:
        issue = Issue(
            id="SEI-1",
            title="Test",
            status="todo",
            priority="medium",
            executor="ai",
            verifier="required",
        )
        assert isinstance(issue.uuid, UUID)
        # uuid4 has version 4
        assert issue.uuid.version == 4

    def test_two_issues_get_different_uuids(self) -> None:
        a = Issue(
            id="SEI-1",
            title="A",
            status="todo",
            priority="low",
            executor="ai",
            verifier="none",
        )
        b = Issue(
            id="SEI-2",
            title="B",
            status="todo",
            priority="low",
            executor="ai",
            verifier="none",
        )
        assert a.uuid != b.uuid

    def test_id_format_validation_accepts_valid(self) -> None:
        for valid in ["SEI-1", "PKB-42", "X-9999", "ABC-1"]:
            Issue(
                id=valid,
                title="t",
                status="todo",
                priority="low",
                executor="ai",
                verifier="none",
            )

    def test_id_format_validation_rejects_invalid(self) -> None:
        for invalid in ["sei-1", "SEI", "SEI-", "-1", "SEI 1", "SEI-1.0"]:
            with pytest.raises(ValueError):
                Issue(
                    id=invalid,
                    title="t",
                    status="todo",
                    priority="low",
                    executor="ai",
                    verifier="none",
                )

    def test_round_trip_with_body(self) -> None:
        issue = Issue(
            id="SEI-42",
            title="Round-trip",
            status="in_progress",
            priority="high",
            executor="ai",
            verifier="required",
            labels=["domain/backend"],
            blocked_by=["SEI-40"],
            docs=["docs/spec.md"],
            created_at=datetime(2026, 4, 7, 10, 0, 0),
            body="## Context\nSome context with [[ref]].\n",
        )
        dumped = issue.model_dump(mode="json")
        restored = Issue.model_validate(dumped)
        assert restored.uuid == issue.uuid
        assert restored.id == issue.id
        assert restored.body == issue.body
        assert restored.labels == issue.labels
        assert restored.blocked_by == issue.blocked_by
        assert restored.docs == issue.docs

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValueError):
            Issue(
                id="SEI-1",
                title="t",
                status="todo",
                priority="low",
                executor="ai",
                verifier="none",
                made_up_field="oops",
            )


class TestConceptNode:
    def test_uuid_auto_generated(self) -> None:
        node = ConceptNode(id="user-model", type="model", name="User")
        assert isinstance(node.uuid, UUID)

    def test_id_must_be_lowercase_slug(self) -> None:
        for valid in ["user-model", "auth-token-endpoint", "tf-api-url", "x"]:
            ConceptNode(id=valid, type="model", name="t")
        for invalid in ["UserModel", "user_model", "User-Model", "-foo", "1foo-bar"]:
            with pytest.raises(ValueError):
                ConceptNode(id=invalid, type="model", name="t")

    def test_default_status_is_active(self) -> None:
        node = ConceptNode(id="user-model", type="model", name="User")
        assert node.status == "active"

    def test_node_with_source(self) -> None:
        node = ConceptNode(
            id="auth-endpoint",
            type="endpoint",
            name="POST /auth",
            source=NodeSource(
                repo="SeidoAI/web-app-backend",
                path="src/api/auth.py",
                lines=(45, 82),
                branch="test",
                content_hash="sha256:abc",
            ),
        )
        assert node.source is not None
        assert node.source.lines == (45, 82)

    def test_round_trip_preserves_source(self) -> None:
        node = ConceptNode(
            id="auth-endpoint",
            type="endpoint",
            name="POST /auth",
            source=NodeSource(
                repo="SeidoAI/web-app-backend",
                path="src/api/auth.py",
                lines=(45, 82),
            ),
            related=["user-model"],
            tags=["auth"],
        )
        dumped = node.model_dump(mode="json")
        restored = ConceptNode.model_validate(dumped)
        assert restored.source == node.source
        assert restored.related == node.related


class TestComment:
    def test_minimal_comment(self) -> None:
        c = Comment(
            issue_key="SEI-1",
            author="claude",
            type="status_change",
            created_at=datetime(2026, 4, 7),
            body="started work",
        )
        assert isinstance(c.uuid, UUID)
        assert c.body == "started work"

    def test_round_trip(self) -> None:
        c = Comment(
            issue_key="SEI-1",
            author="claude",
            type="status_change",
            created_at=datetime(2026, 4, 7),
            body="x",
        )
        dumped = c.model_dump(mode="json")
        restored = Comment.model_validate(dumped)
        assert restored.uuid == c.uuid


class TestRepoBinding:
    def test_minimal(self) -> None:
        b = RepoBinding(repo="SeidoAI/web-app-backend", base_branch="test")
        assert b.branch is None
        assert b.pr_number is None

    def test_with_branch_and_pr(self) -> None:
        b = RepoBinding(
            repo="SeidoAI/web-app-backend",
            base_branch="test",
            branch="claude/SEI-42",
            pr_number=42,
        )
        assert b.pr_number == 42


class TestAgentSession:
    def test_minimal_session(self) -> None:
        s = AgentSession(
            id="wave1-agent-a",
            name="Auth + User Model",
            agent="backend-coder",
        )
        assert isinstance(s.uuid, UUID)
        assert s.status == "planned"
        assert s.repos == []
        assert s.engagements == []

    def test_multi_repo_session(self) -> None:
        s = AgentSession(
            id="wave1-agent-a",
            name="x",
            agent="backend-coder",
            issues=["SEI-40", "SEI-42"],
            repos=[
                RepoBinding(
                    repo="SeidoAI/web-app-backend",
                    base_branch="test",
                    branch="claude/SEI-40",
                    pr_number=42,
                ),
                RepoBinding(
                    repo="SeidoAI/web-app-infrastructure",
                    base_branch="test",
                ),
            ],
            current_state="implementing",
        )
        assert len(s.repos) == 2
        assert s.repos[0].pr_number == 42
        assert s.repos[1].branch is None
        assert s.current_state == "implementing"

    def test_session_orchestration_override(self) -> None:
        s = AgentSession(
            id="critical-fix",
            name="x",
            agent="backend-coder",
            orchestration=SessionOrchestration(
                pattern="default",
                overrides={"plan_approval_required": True},
            ),
        )
        assert s.orchestration is not None
        assert s.orchestration.overrides["plan_approval_required"] is True

    def test_artifact_overrides(self) -> None:
        s = AgentSession(
            id="x",
            name="x",
            agent="x",
            artifact_overrides=[
                ArtifactSpec(
                    name="architecture-diff",
                    file="architecture-diff.md",
                    template="architecture-diff.md.j2",
                    produced_at="completion",
                    required=True,
                )
            ],
        )
        assert len(s.artifact_overrides) == 1
        assert s.artifact_overrides[0].name == "architecture-diff"

    def test_engagement_history_round_trip(self) -> None:
        s = AgentSession(
            id="x",
            name="x",
            agent="x",
            engagements=[
                EngagementEntry(
                    started_at=datetime(2026, 4, 7, 10),
                    trigger="initial_launch",
                    ended_at=datetime(2026, 4, 7, 12),
                    outcome="pr_opened",
                ),
                EngagementEntry(
                    started_at=datetime(2026, 4, 7, 14),
                    trigger="ci_failure",
                    context="lint failure",
                ),
            ],
        )
        dumped = s.model_dump(mode="json")
        restored = AgentSession.model_validate(dumped)
        assert len(restored.engagements) == 2
        assert restored.engagements[1].context == "lint failure"


class TestProjectConfig:
    def test_minimal_project(self) -> None:
        p = ProjectConfig(name="test", key_prefix="TST")
        assert p.next_issue_number == 1
        assert p.next_session_number == 1
        assert p.base_branch == "test"

    def test_with_repos(self) -> None:
        p = ProjectConfig(
            name="seido",
            key_prefix="SEI",
            repos={
                "SeidoAI/web-app-backend": RepoEntry(local="~/Code/seido/web-app"),
                "SeidoAI/web-app-frontend": RepoEntry(),
            },
        )
        assert len(p.repos) == 2
        assert p.repos["SeidoAI/web-app-backend"].local == "~/Code/seido/web-app"
        assert p.repos["SeidoAI/web-app-frontend"].local is None

    def test_status_transitions(self) -> None:
        p = ProjectConfig(
            name="x",
            key_prefix="X",
            statuses=["backlog", "todo", "done"],
            status_transitions={
                "backlog": ["todo"],
                "todo": ["done"],
                "done": [],
            },
        )
        assert p.status_transitions["todo"] == ["done"]


class TestGraphEdge:
    def test_alias_population_from(self) -> None:
        # Edges in the YAML cache use `from`/`to` (Python keywords).
        e = GraphEdge.model_validate(
            {"from": "SEI-1", "to": "user-model", "type": "references"}
        )
        assert e.from_id == "SEI-1"
        assert e.to_id == "user-model"

    def test_alias_population_field_name(self) -> None:
        e = GraphEdge(from_id="SEI-1", to_id="SEI-2", type="blocked_by")
        assert e.from_id == "SEI-1"
        assert e.to_id == "SEI-2"

    def test_dump_by_alias(self) -> None:
        e = GraphEdge(from_id="SEI-1", to_id="user-model", type="references")
        dumped = e.model_dump(by_alias=True)
        assert "from" in dumped
        assert "to" in dumped
        assert dumped["from"] == "SEI-1"
