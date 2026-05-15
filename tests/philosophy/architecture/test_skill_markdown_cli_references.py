"""Skill markdown's ``tripwire <cmd>`` mentions name real CLIs.

Philosophy §9 fourth principle:

    *"CLI codifies repetitive procedure. Layer 1 wraps individual
    external operations ... Layer 2 chains common combos. Layer 3
    (skill markdown) selects, sequences, and recovers from failure."*

Skill markdown is Layer 3 — its job is to tell the agent *which*
Layer 1/2 CLI to invoke. If a skill says "run ``tripwire session
normalise-branch``" but that command doesn't exist (or was renamed),
the agent reads instructions that lead nowhere. The §9 promise that
"three orthogonal extension points" stay coherent dies one stale doc
at a time.

This test walks every ``.md`` file under ``templates/skills/`` and,
for each ``tripwire <subcommand>...`` mention, asserts the prefix
matches a registered click command in
:mod:`tripwire.cli.main`.

The test is **lenient** on the matching shape: it greedily walks the
click command tree and accepts the longest prefix that matches.
``tripwire validate --strict --format=json`` matches ``validate`` and
the flags are ignored. ``tripwire transition <wf> <id> <target>``
matches ``transition``. False negatives (real CLI invocations the
parser doesn't recognise) would surface as failures here — that's the
test's job. False positives (prose like "Tripwire is a framework that
runs validate") are filtered by requiring the lowercase literal
``tripwire `` with a following lowercase-token-shape word.
"""

from __future__ import annotations

import re
from pathlib import Path

import click

import tripwire

SKILLS_ROOT = Path(tripwire.__file__).parent / "templates" / "skills"

# Markdown distinguishes prose from code at the syntactic level. A
# "real" CLI invocation in skill markdown is either:
#
#   1. inside an inline code span:  `tripwire validate --strict`
#   2. inside a fenced code block:  ```bash
#                                   tripwire validate
#                                   ```
#
# Prose like "the tripwire version" should never match. We extract
# both shapes and run the same matcher on their bodies.

# Inline code spans: `...` (single-backtick) — capture the body.
# Avoids matching `` ``code with backtick`` `` (rare); good enough.
INLINE_CODE_PATTERN = re.compile(r"`([^`\n]+)`")

# Fenced code blocks: ```lang\n...\n``` — capture the body, language-
# agnostic. We don't filter by language because skill markdown is
# inconsistent about labelling shell blocks.
FENCED_BLOCK_PATTERN = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)

# Within a code body, find the `tripwire <subcommand>...` shape and
# capture the subcommand sequence (lowercase tokens, hyphen-separated).
# Use `[ \t]+` rather than `\s+` so the pattern stays on one line — a
# `tripwire` literal at the end of one line followed by an unrelated
# identifier on the next line is not an invocation, it's adjacency.
INVOCATION_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])tripwire[ \t]+([a-z][a-z0-9-]*(?:[ \t]+[a-z][a-z0-9-]*)*)"
)


def _build_command_tree() -> dict:
    """Walk the click hierarchy and return a nested dict of subcommand
    names → child dict (empty dict on leaves)."""
    from tripwire.cli.main import cli

    def walk(group: click.Group) -> dict:
        out: dict[str, dict] = {}
        for name, cmd in group.commands.items():
            if isinstance(cmd, click.Group):
                out[name] = walk(cmd)
            else:
                out[name] = {}
        return out

    return walk(cli)


def _longest_matching_prefix(tokens: list[str], tree: dict) -> int:
    """Return the index up to which ``tokens`` form a valid CLI path
    through ``tree``. 0 means no token matched at all.
    """
    cursor = tree
    matched = 0
    for tok in tokens:
        if tok not in cursor:
            break
        cursor = cursor[tok]
        matched += 1
    return matched


def _extract_code_bodies(text: str) -> list[str]:
    """Return the bodies of every fenced code block and inline code
    span in *text*. Anything outside these spans is prose and the
    test deliberately ignores it.

    Order: fenced first, then inline. Bodies are not de-duplicated —
    one repeated invocation produces multiple matches downstream, which
    is fine (a real failure surfaces every offending location).
    """
    bodies: list[str] = []
    # Pull fenced blocks out, then strip them from the text so the
    # inline-code pass doesn't double-count nested-looking content.
    cleaned = text
    for match in FENCED_BLOCK_PATTERN.finditer(text):
        bodies.append(match.group(1))
    cleaned = FENCED_BLOCK_PATTERN.sub("", cleaned)
    for match in INLINE_CODE_PATTERN.finditer(cleaned):
        bodies.append(match.group(1))
    return bodies


def test_every_tripwire_mention_in_skill_markdown_resolves_to_a_real_cli():
    """For each ``tripwire <subcommand>`` mention in
    ``templates/skills/**/*.md``, the leading prefix matches a
    registered click command.

    A failure here means a skill markdown file tells the agent to
    run a CLI that doesn't exist. That's a §9 contract break:
    Layer 3 (skill) is supposed to wrap Layer 1/2 CLIs faithfully.
    """
    tree = _build_command_tree()

    md_files = sorted(SKILLS_ROOT.rglob("*.md"))
    assert md_files, (
        f"no .md files found under {SKILLS_ROOT} — the templates/skills/ "
        f"tree may have moved. Update SKILLS_ROOT."
    )

    violations: list[str] = []
    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        for body in _extract_code_bodies(text):
            for match in INVOCATION_PATTERN.finditer(body):
                tokens = match.group(1).split()
                matched = _longest_matching_prefix(tokens, tree)
                if matched == 0:
                    rel = md_path.relative_to(SKILLS_ROOT.parent.parent)
                    violations.append(
                        f"  {rel}: 'tripwire {' '.join(tokens)}' — no matching CLI"
                    )

    assert not violations, (
        "Philosophy §9 violation — skill markdown references CLIs that\n"
        "don't exist (or have been renamed). Layer 3 (skill) must wrap\n"
        "Layer 1/2 CLIs that actually resolve; otherwise the agent reads\n"
        "instructions leading to a dead end.\n"
        "\n"
        "Stale references:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix options:\n"
        "  1. Update the skill markdown to the current CLI name.\n"
        "  2. Add the missing CLI command (rare — it's usually a doc\n"
        "     update, not a missing implementation).\n"
        "  3. If the reference is intentional prose (not an invocation),\n"
        "     reword so it doesn't match the `tripwire <subcommand>`\n"
        "     shape (e.g. 'the tripwire framework' rather than\n"
        "     'tripwire validate is...')."
    )
