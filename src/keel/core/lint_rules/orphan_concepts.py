"""lint/issue_body_orphan_concepts — warn when an issue body mentions a
capitalised proper-noun term that isn't covered by any concept node.

This is a heuristic, not a structural check. It tries to catch scoping
shortcuts where the PM agent wrote about "our auth system" or "Stripe"
without creating (or linking) a node for that concept.

False positives are expected (common nouns capitalized at sentence
start, technology names used once in passing). The signal is still
useful — it forces the agent to justify each orphan or create a node.
"""

from __future__ import annotations

import re

from keel.core.linter import LintFinding, register_rule
from keel.core.node_store import list_nodes
from keel.core.store import list_issues

# Multi-word Title-Case proper nouns: "Auth System", "Stripe", "OAuth Token"
_PROPER_NOUN = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\b")

# Common English words that capitalise at sentence start. Avoids noise.
_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "but",
    "by",
    "do",
    "for",
    "from",
    "has",
    "have",
    "i",
    "if",
    "in",
    "is",
    "it",
    "its",
    "not",
    "of",
    "on",
    "or",
    "so",
    "that",
    "the",
    "this",
    "to",
    "use",
    "we",
    "was",
    "were",
    "will",
    "with",
    "you",
    "your",
}


@register_rule(
    stage="scoping",
    code="lint/issue_body_orphan_concepts",
    severity="warning",
)
def _check(ctx):
    node_names: set[str] = set()
    for n in list_nodes(ctx.project_dir):
        node_names.add(n.name.lower())
        node_names.add(n.id.lower())

    for issue in list_issues(ctx.project_dir):
        body = f"{issue.title or ''} {issue.body or ''}"
        mentions = {m.lower() for m in _PROPER_NOUN.findall(body)}
        orphans = {m for m in mentions if m not in node_names}
        orphans -= _STOPWORDS
        for orphan in sorted(orphans):
            yield LintFinding(
                code="lint/issue_body_orphan_concepts",
                severity="warning",
                message=(
                    f"issue {issue.id} mentions {orphan!r} which isn't "
                    "covered by any concept node."
                ),
                file=f"issues/{issue.id}/issue.yaml",
                fix_hint=(
                    f"Add a node for {orphan!r}, alias it in an existing "
                    "node, or ignore if it's a common term."
                ),
            )
