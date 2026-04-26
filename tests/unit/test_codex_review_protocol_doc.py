"""Verify the v0.7.10 §D2 ``codex-review-protocol.md`` shipped doc.

The protocol doc is the agent's review-structure prompt. It ships
under ``src/tripwire/templates/project/docs/codex-review-protocol.md``
so ``tripwire init``'s standard project-tree copy lands it at
``<project>/docs/codex-review-protocol.md`` — the path referenced
by the codex-reviewer agent's ``context.docs``.
"""

from __future__ import annotations

import yaml

from tripwire.templates import get_templates_dir

PROTOCOL_DOC_REL = "project/docs/codex-review-protocol.md"
AGENT_YAML_REL = "agent_templates/codex-reviewer.yaml"


def test_protocol_doc_ships_under_project_docs():
    """The doc must live under ``templates/project/docs/`` so the
    standard init copy puts it at ``<project>/docs/...`` — the path
    the codex-reviewer agent references."""
    path = get_templates_dir() / PROTOCOL_DOC_REL
    assert path.is_file(), f"missing protocol doc: {path}"


def test_protocol_path_matches_agent_yaml_reference():
    """Drift guard: the agent yaml's ``context.docs`` must point at the
    file we actually ship. If someone moves either side without the
    other, this catches it."""
    agent_path = get_templates_dir() / AGENT_YAML_REL
    agent_data = yaml.safe_load(agent_path.read_text(encoding="utf-8"))
    referenced = agent_data["context"]["docs"]
    # The agent yaml refers to the path AS SEEN by a project (under
    # `<project>/docs/`); the shipped template lives at
    # `templates/project/docs/`. Strip the `project/` prefix.
    template_relative_to_project = PROTOCOL_DOC_REL[len("project/") :]
    assert template_relative_to_project in referenced


def test_protocol_doc_specifies_severity_levels():
    """Per spec §3.D2: review must group issues by severity. The doc
    must enumerate the severity vocabulary so the agent's output is
    consistent across runs."""
    path = get_templates_dir() / PROTOCOL_DOC_REL
    body = path.read_text(encoding="utf-8")
    body_lower = body.lower()
    # Same vocabulary used in the workflow's inline prompt — keep
    # them in lockstep (no programmatic check, just a comment hint).
    for severity in ("blocking", "major", "minor", "nit"):
        assert severity in body_lower, (
            f"protocol doc missing severity tier: {severity!r}"
        )


def test_protocol_doc_addresses_no_diff_case():
    """Per the plan: "how to handle no-diff PRs". The doc must give the
    agent guidance on what to post when the PR has no reviewable
    content (e.g. a docs-only or empty PR)."""
    path = get_templates_dir() / PROTOCOL_DOC_REL
    body = path.read_text(encoding="utf-8").lower()
    # Either of these phrases satisfies the contract — the doc's
    # author may pick wording, but one must be present.
    assert "no diff" in body or "empty diff" in body or "no changes" in body, (
        "protocol doc must instruct the agent on the no-diff/empty-PR case"
    )


def test_protocol_doc_warns_against_nit_only_reviews():
    """Per the plan: "what NOT to nit-pick". The doc must discourage
    pure-style nit reviews so the comment is signal, not noise."""
    path = get_templates_dir() / PROTOCOL_DOC_REL
    body = path.read_text(encoding="utf-8").lower()
    assert "nit" in body  # the doc must explicitly address nits
    # And explicitly say "skip" / "avoid" / "don't" near nits — a
    # protocol that only mentions nits as a tier is incomplete.
    forbidden_phrases = ("skip", "avoid", "do not", "don't", "not worth")
    assert any(phrase in body for phrase in forbidden_phrases), (
        "protocol must steer the agent away from nit-only reviews"
    )
