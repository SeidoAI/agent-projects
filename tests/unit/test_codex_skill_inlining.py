"""Codex sessions inline skill content into the kickoff prompt.

Codex has no ``.claude/skills/SKILL.md`` discovery mechanism; without
inlining, the agent has no idea what its declared skill is. The
helper :func:`tripwire.runtimes.prep.inline_skills_for_codex` reads
each named skill's ``SKILL.md`` and concatenates them under a single
``## Skills`` header so the prompt-renderer can prepend the block to
``{plan}``.
"""

from __future__ import annotations

from tripwire.runtimes.prep import inline_skills_for_codex


def test_inline_returns_empty_string_for_no_skills():
    assert inline_skills_for_codex([]) == ""


def test_inline_concatenates_each_skill_under_header():
    out = inline_skills_for_codex(["backend-development"])
    assert "## Skills" in out
    # Sentinel content from the actual shipped skill — kept stable
    # by using a substring that exists in the SKILL.md frontmatter.
    assert "name: backend-development" in out
    assert "Backend Development" in out


def test_inline_concatenates_multiple_skills_in_order():
    out = inline_skills_for_codex(["backend-development", "agent-messaging"])
    assert "## Skills" in out
    assert "name: backend-development" in out
    assert "name: agent-messaging" in out
    # Order preserved
    assert out.index("name: backend-development") < out.index("name: agent-messaging")


def test_inline_skips_unknown_skills_silently():
    """copy_skills validates skill existence; this helper is downstream
    of that — passing 'real-skill, fake-skill' yields the real one's
    content and silently drops the fake. Re-validating here would make
    the helper non-idempotent across re-prep cycles."""
    out = inline_skills_for_codex(["backend-development", "definitely-not-real-skill"])
    assert "name: backend-development" in out
    # Fake one didn't crash and didn't show up
    assert "definitely-not-real-skill" not in out
