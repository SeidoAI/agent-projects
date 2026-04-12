"""Unit tests for the PM skill example files.

Each example file under `templates/skills/project-manager/examples/`
must be schema-valid — an agent copying one as a starting point should
produce a file that the validator's schema checks pass.

These tests use model_validate directly (not the full validator) because
the examples reference realistic code paths like `src/api/auth.py` that
don't exist in a test environment, and the live freshness check would
fail without a local clone. The goal here is schema correctness, not
live network validation — the full validator is exercised by the
integration tests in `tests/integration/test_init.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from keel.core.parser import parse_frontmatter_body
from keel.models.comment import Comment
from keel.models.issue import Issue
from keel.models.node import ConceptNode
from keel.models.session import AgentSession
from keel.templates import get_templates_dir

EXAMPLES_DIR = get_templates_dir() / "skills" / "project-manager" / "examples"


def _all_example_files(prefix: str) -> list[Path]:
    """Return example files whose filename starts with the given prefix."""
    return sorted(EXAMPLES_DIR.glob(f"{prefix}*.yaml"))


# ============================================================================
# Issue examples
# ============================================================================


@pytest.mark.parametrize(
    "example_path",
    _all_example_files("issue-"),
    ids=lambda p: p.name,
)
def test_issue_example_schema_valid(example_path: Path) -> None:
    text = example_path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter_body(text)
    # Pydantic validates the schema; raises if anything is wrong.
    issue = Issue.model_validate({**frontmatter, "body": body})
    assert issue.uuid is not None
    assert issue.id.startswith("SEI-")  # examples all use SEI prefix


def test_issue_examples_have_required_body_sections() -> None:
    """Every issue example must contain the required Markdown headings."""
    required_headings = (
        "## Context",
        "## Implements",
        "## Repo scope",
        "## Requirements",
        "## Execution constraints",
        "## Acceptance criteria",
        "## Test plan",
        "## Dependencies",
        "## Definition of Done",
    )
    for path in _all_example_files("issue-"):
        if "epic" in path.name:
            continue  # Epic issues have a different structure
        body = path.read_text(encoding="utf-8")
        for heading in required_headings:
            assert heading in body, f"{path.name} missing required heading {heading!r}"


def test_epic_issue_example_has_basic_sections() -> None:
    """Epic issues need Context and Acceptance criteria but not the full set."""
    for path in _all_example_files("issue-epic"):
        body = path.read_text(encoding="utf-8")
        assert "## Context" in body, f"{path.name} missing ## Context"
        assert "## Acceptance criteria" in body, f"{path.name} missing ## Acceptance criteria"


def test_issue_examples_have_stop_and_ask_guidance() -> None:
    for path in _all_example_files("issue-"):
        if "epic" in path.name:
            continue  # Epics don't have execution constraints
        body = path.read_text(encoding="utf-8").lower()
        assert "stop and ask" in body or "stop, ask" in body, (
            f"{path.name} missing 'stop and ask' guidance"
        )


def test_issue_examples_have_at_least_one_acceptance_checkbox() -> None:
    for path in _all_example_files("issue-"):
        body = path.read_text(encoding="utf-8")
        # Find the Acceptance criteria section and check for `- [ ]` or `- [x]`
        section = body.split("## Acceptance criteria", 1)[-1]
        next_heading = section.find("\n## ")
        if next_heading != -1:
            section = section[:next_heading]
        assert "- [ ]" in section or "- [x]" in section, (
            f"{path.name} Acceptance criteria has no checkbox items"
        )


# ============================================================================
# Node examples
# ============================================================================


@pytest.mark.parametrize(
    "example_path",
    _all_example_files("node-"),
    ids=lambda p: p.name,
)
def test_node_example_schema_valid(example_path: Path) -> None:
    text = example_path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter_body(text)
    node = ConceptNode.model_validate({**frontmatter, "body": body})
    assert node.uuid is not None
    # Example filename is `node-<type>.yaml`; the id is a meaningful slug,
    # not the bare type.
    assert node.id  # non-empty


def test_all_node_types_covered() -> None:
    """The node examples should cover every node type in the spec."""
    expected_types = {"endpoint", "model", "decision", "config", "contract"}
    found_types: set[str] = set()
    for path in _all_example_files("node-"):
        text = path.read_text(encoding="utf-8")
        frontmatter, _body = parse_frontmatter_body(text)
        found_types.add(frontmatter["type"])
    assert expected_types <= found_types, (
        f"Missing node type examples: {expected_types - found_types}"
    )


# ============================================================================
# Session examples
# ============================================================================


@pytest.mark.parametrize(
    "example_path",
    _all_example_files("session-"),
    ids=lambda p: p.name,
)
def test_session_example_schema_valid(example_path: Path) -> None:
    text = example_path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter_body(text)
    session = AgentSession.model_validate({**frontmatter, "body": body})
    assert session.uuid is not None


def test_multi_repo_session_has_multiple_repos() -> None:
    path = EXAMPLES_DIR / "session-multi-repo.yaml"
    text = path.read_text(encoding="utf-8")
    frontmatter, _body = parse_frontmatter_body(text)
    session = AgentSession.model_validate({**frontmatter, "body": _body})
    assert len(session.repos) >= 2


# ============================================================================
# Comment example
# ============================================================================


def test_comment_example_schema_valid() -> None:
    path = EXAMPLES_DIR / "comment-status-change.yaml"
    text = path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter_body(text)
    comment = Comment.model_validate({**frontmatter, "body": body})
    assert comment.type == "status_change"


# ============================================================================
# Orchestration example
# ============================================================================


def test_orchestration_example_is_valid_yaml() -> None:
    path = EXAMPLES_DIR / "orchestration-default.yaml"
    text = path.read_text(encoding="utf-8")
    # Orchestration YAML isn't a Pydantic model in v0 — just verify it
    # parses as a mapping with `name` and `events`.
    raw = yaml.safe_load(text)
    assert isinstance(raw, dict)
    assert raw["name"] == "default"
    assert "events" in raw
    assert isinstance(raw["events"], dict)


# ============================================================================
# Artifact examples
# ============================================================================


def test_artifact_examples_present() -> None:
    """The `examples/artifacts/` subfolder ships three artifact examples."""
    artifacts_dir = EXAMPLES_DIR / "artifacts"
    assert artifacts_dir.is_dir()
    expected = {"plan.md", "task-checklist.md", "verification-checklist.md"}
    found = {p.name for p in artifacts_dir.glob("*.md")}
    assert expected <= found


def test_artifact_plan_has_expected_sections() -> None:
    path = EXAMPLES_DIR / "artifacts" / "plan.md"
    content = path.read_text(encoding="utf-8")
    # A well-formed plan has Context, Steps, and Verification
    assert "## Context" in content
    assert "## Steps" in content
    assert "## Verification" in content


# ============================================================================
# SKILL.md
# ============================================================================


def test_skill_md_exists() -> None:
    skill_md = EXAMPLES_DIR.parent / "SKILL.md"
    assert skill_md.is_file()


def test_skill_md_has_frontmatter() -> None:
    skill_md = EXAMPLES_DIR.parent / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    assert content.startswith("---")
    # Skills need `name` and `description` in frontmatter
    assert "name: project-manager" in content
    assert "description:" in content


# ============================================================================
# Reference docs
# ============================================================================


def test_all_reference_docs_present() -> None:
    """Every reference doc from the plan must be shipped."""
    references_dir = EXAMPLES_DIR.parent / "references"
    expected = {
        "WORKFLOWS_INITIAL_SCOPING.md",
        "WORKFLOWS_INCREMENTAL_UPDATE.md",
        "WORKFLOWS_TRIAGE.md",
        "WORKFLOWS_REVIEW.md",
        "SCHEMA_PROJECT.md",
        "SCHEMA_ISSUES.md",
        "SCHEMA_NODES.md",
        "SCHEMA_SESSIONS.md",
        "SCHEMA_COMMENTS.md",
        "SCHEMA_ARTIFACTS.md",
        "CONCEPT_GRAPH.md",
        "ID_ALLOCATION.md",
        "VALIDATION.md",
        "REFERENCES.md",
        "COMMIT_CONVENTIONS.md",
        "ANTI_PATTERNS.md",
        "POLICIES.md",
    }
    found = {p.name for p in references_dir.glob("*.md")}
    missing = expected - found
    assert not missing, f"Missing reference docs: {missing}"


# ============================================================================
# Step 11: Other default skills
# ============================================================================


SKILLS_DIR = get_templates_dir() / "skills"


@pytest.mark.parametrize(
    "skill_name",
    ["agent-messaging", "backend-development", "verification"],
)
def test_default_skill_has_skill_md_with_frontmatter(skill_name: str) -> None:
    skill_md = SKILLS_DIR / skill_name / "SKILL.md"
    assert skill_md.is_file(), f"{skill_name}/SKILL.md missing"
    content = skill_md.read_text(encoding="utf-8")
    assert content.startswith("---"), f"{skill_name} missing frontmatter"
    assert f"name: {skill_name}" in content
    assert "description:" in content


def test_agent_messaging_skill_references_present() -> None:
    refs_dir = SKILLS_DIR / "agent-messaging" / "references"
    expected = {"MESSAGE_TYPES.md", "EXAMPLES.md", "ANTI_PATTERNS.md"}
    found = {p.name for p in refs_dir.glob("*.md")}
    assert expected <= found


def test_backend_development_skill_references_present() -> None:
    refs_dir = SKILLS_DIR / "backend-development" / "references"
    expected = {"TDD.md", "COMMIT_PATTERN.md", "DEPENDENCIES.md"}
    found = {p.name for p in refs_dir.glob("*.md")}
    assert expected <= found


def test_verification_skill_references_present() -> None:
    refs_dir = SKILLS_DIR / "verification" / "references"
    expected = {"REWARD_HACKING.md", "SECURITY_CHECKLIST.md"}
    found = {p.name for p in refs_dir.glob("*.md")}
    assert expected <= found


def test_agent_messaging_covers_every_message_type() -> None:
    """The agent-messaging SKILL.md must mention every message type."""
    skill = (SKILLS_DIR / "agent-messaging" / "SKILL.md").read_text(encoding="utf-8")
    for msg_type in (
        "status",
        "plan_approval",
        "question",
        "stuck",
        "escalation",
        "handover",
        "progress",
        "fyi",
    ):
        assert f"`{msg_type}`" in skill, (
            f"agent-messaging SKILL.md missing type: {msg_type}"
        )


def test_verification_skill_is_read_only() -> None:
    """The verification skill MUST emphasise it cannot push code."""
    skill = (SKILLS_DIR / "verification" / "SKILL.md").read_text(encoding="utf-8")
    assert "cannot push" in skill.lower() or "read-only" in skill.lower()


def test_backend_development_skill_mentions_validation_gate() -> None:
    """The backend skill must point at `keel validate` as the gate."""
    skill = (SKILLS_DIR / "backend-development" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "keel validate" in skill
