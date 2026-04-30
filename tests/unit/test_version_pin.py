"""Version field + `[[id@vN]]` pin syntax (KUI-126 / A1).

Every Pydantic frontmatter model gains an integer `version` field
defaulting to 1. The reference parser accepts an optional `@vN`
suffix; bare references continue to mean "latest". A new
`extract_references_with_pins` helper returns `(id, version)` tuples
for callers that need the pin annotation.
"""

from __future__ import annotations

import pytest

from tripwire.core.graph import refs as graph_refs
from tripwire.core.graph import version_pin
from tripwire.models import (
    AgentSession,
    Comment,
    ConceptNode,
    Issue,
    ProjectConfig,
    RepoEntry,
)

# ---------------------------------------------------------------------------
# Version field — every entity defaults to 1
# ---------------------------------------------------------------------------


def test_issue_version_defaults_to_one():
    issue = Issue(
        id="TST-1",
        title="t",
        status="todo",
        priority="medium",
        executor="ai",
        verifier="required",
    )
    assert issue.version == 1


def test_issue_version_explicit():
    issue = Issue(
        id="TST-1",
        title="t",
        status="todo",
        priority="medium",
        executor="ai",
        verifier="required",
        version=4,
    )
    assert issue.version == 4


def test_concept_node_version_defaults_to_one():
    node = ConceptNode(id="user-model", type="model", name="User")
    assert node.version == 1


def test_session_version_defaults_to_one():
    session = AgentSession(id="s1", name="s1", agent="dev")
    assert session.version == 1


def test_comment_version_defaults_to_one():
    comment = Comment(
        issue_key="TST-1",
        author="agent:pm",
        type="pm_feedback",
        created_at="2026-04-30T00:00:00Z",
    )
    assert comment.version == 1


def test_project_config_version_defaults_to_one():
    cfg = ProjectConfig(
        name="t",
        key_prefix="TST",
        repos={"o/r": RepoEntry()},
        next_issue_number=1,
    )
    assert cfg.version == 1


# ---------------------------------------------------------------------------
# Pin syntax parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("user-model", ("user-model", None)),
        ("user-model@v1", ("user-model", 1)),
        ("user-model@v3", ("user-model", 3)),
        ("user-model@v42", ("user-model", 42)),
    ],
)
def test_parse_pin(text, expected):
    assert version_pin.parse_pin(text) == expected


def test_parse_pin_rejects_malformed():
    # `@v` without a number, or non-digit version, should be treated as a
    # plain id without a pin (forward-compat: callers can warn if needed).
    assert version_pin.parse_pin("user-model@vfoo") == ("user-model@vfoo", None)
    assert version_pin.parse_pin("user-model@v") == ("user-model@v", None)


# ---------------------------------------------------------------------------
# Reference extraction with pins
# ---------------------------------------------------------------------------


def test_extract_references_strips_pins_for_back_compat():
    """Bare extract_references must keep returning bare ids.

    Many callers (the validator, the cache, the UI) treat references
    as bare ids today. Adding pin syntax must not break them — the
    pinned form `[[user-model@v3]]` continues to resolve as
    `user-model` for legacy callers.
    """
    body = "See [[user-model]] and [[other-thing@v2]]."
    refs = graph_refs.extract_references(body)
    assert refs == ["user-model", "other-thing"]


def test_extract_references_with_pins():
    body = "See [[user-model]] and [[other-thing@v2]] and [[third@v10]]."
    pairs = graph_refs.extract_references_with_pins(body)
    assert pairs == [
        ("user-model", None),
        ("other-thing", 2),
        ("third", 10),
    ]


def test_extract_references_with_pins_skips_code_blocks():
    body = "Inline [[user-model@v3]].\n```\n[[ignored@v9]]\n```\nAfter [[other@v1]].\n"
    pairs = graph_refs.extract_references_with_pins(body)
    assert pairs == [
        ("user-model", 3),
        ("other", 1),
    ]
