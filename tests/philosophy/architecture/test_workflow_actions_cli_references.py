"""``docs/WORKFLOW_ACTIONS.md`` cites only real CLI commands.

Philosophy §9 sees ``WORKFLOW_ACTIONS.md`` as the canonical
enumeration of every workflow, status, transition, and CLI command:

    *"See `WORKFLOW_ACTIONS.md` for the canonical enumeration of
    every workflow, status, transition, and CLI command this
    principle produces."*

It is the reference the skill markdown points agents to. If a row in
that table cites ``tripwire session unicorn`` and no such CLI exists,
the agent following the doc hits a dead end and the "single
accountability surface" promise of §9 leaks.

This test is the WORKFLOW_ACTIONS.md sibling of
:mod:`tests/philosophy/architecture/test_skill_markdown_cli_references`.
Same matcher; same lenient prefix-walk semantics; different doc.
"""

from __future__ import annotations

import re
from pathlib import Path

import click

import tripwire

WORKFLOW_ACTIONS_DOC = (
    Path(tripwire.__file__).parent.parent.parent / "docs" / "WORKFLOW_ACTIONS.md"
)

INLINE_CODE_PATTERN = re.compile(r"`([^`\n]+)`")
FENCED_BLOCK_PATTERN = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
INVOCATION_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])tripwire[ \t]+([a-z][a-z0-9-]*(?:[ \t]+[a-z][a-z0-9-]*)*)"
)


def _build_command_tree() -> dict:
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
    cursor = tree
    matched = 0
    for tok in tokens:
        if tok not in cursor:
            break
        cursor = cursor[tok]
        matched += 1
    return matched


def _extract_code_bodies(text: str) -> list[str]:
    bodies: list[str] = []
    cleaned = text
    for match in FENCED_BLOCK_PATTERN.finditer(text):
        bodies.append(match.group(1))
    cleaned = FENCED_BLOCK_PATTERN.sub("", cleaned)
    for match in INLINE_CODE_PATTERN.finditer(cleaned):
        bodies.append(match.group(1))
    return bodies


def test_every_tripwire_mention_in_workflow_actions_doc_resolves_to_a_real_cli():
    """For each ``tripwire <subcommand>`` inside an inline code span
    or fenced block of ``docs/WORKFLOW_ACTIONS.md``, the leading
    prefix matches a registered click command.

    Skip cleanly if the doc isn't present in the layout being tested
    against (some packaging layouts don't ship docs/) — but if the
    file IS there, every citation must resolve.
    """
    if not WORKFLOW_ACTIONS_DOC.exists():
        # Not a failure — some installations don't ship docs/. The
        # in-repo run will find it; the wheel-smoke CI may not.
        return

    tree = _build_command_tree()
    text = WORKFLOW_ACTIONS_DOC.read_text(encoding="utf-8")

    violations: list[str] = []
    for body in _extract_code_bodies(text):
        for match in INVOCATION_PATTERN.finditer(body):
            tokens = match.group(1).split()
            matched = _longest_matching_prefix(tokens, tree)
            if matched == 0:
                violations.append(f"  'tripwire {' '.join(tokens)}' — no matching CLI")

    assert not violations, (
        "Philosophy §9 violation — `docs/WORKFLOW_ACTIONS.md` cites a CLI\n"
        "command that doesn't exist (or was renamed). This file is the\n"
        "canonical workflow-actions reference; stale rows mean the\n"
        "agent's documented path forward leads nowhere.\n"
        "\n"
        "Stale references:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: update the row in WORKFLOW_ACTIONS.md to the current CLI,\n"
        "or — if the CLI was deliberately removed — drop the row entirely."
    )
