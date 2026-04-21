"""Extract `[[node-id]]` references from Markdown bodies.

Edges in the concept graph are emergent: an issue body that says
`[[user-model]]` creates an edge from the issue to the `user-model` node
without any separate edge file. This module pulls those references out of
prose and returns them as a list.

Code blocks are explicitly skipped — `[[foo]]` inside a fenced code block
is not a reference (it's literal code or example output).
"""

from __future__ import annotations

import re

# A reference is `[[id]]` where id is a lowercase slug. The strict slug
# rule means random `[[words like this]]` in prose are NOT picked up — only
# things that look like real node ids.
REFERENCE_PATTERN = re.compile(r"\[\[([a-z][a-z0-9-]*)\]\]")

# Lines that toggle a fenced code block. We use a permissive opening rule:
# any line whose stripped form starts with three backticks (or three tildes)
# enters a code block; the same toggles it off.
FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")


def extract_references(body: str) -> list[str]:
    """Return all `[[node-id]]` references found in `body`, in order.

    Duplicates are preserved (an issue that mentions `[[user-model]]` twice
    yields it twice). Use `dict.fromkeys()` or `set()` at the call site if
    you want unique references.

    Lines inside fenced code blocks are ignored.
    """
    refs: list[str] = []
    in_fence = False

    for line in body.splitlines():
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        refs.extend(REFERENCE_PATTERN.findall(line))

    return refs


def replace_references(
    body: str,
    resolver: callable,  # type: ignore[valid-type]
) -> str:
    """Replace every `[[node-id]]` in `body` with `resolver(node_id)`.

    The resolver is called with the bare node id (no brackets) and should
    return the replacement string. Lines inside fenced code blocks are left
    untouched.

    Useful for the UI to render references as links, or for the validator's
    `--fix` to rewrite collided ids in place.
    """
    out_lines: list[str] = []
    in_fence = False

    for line in body.splitlines(keepends=True):
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue
        out_lines.append(REFERENCE_PATTERN.sub(lambda m: resolver(m.group(1)), line))

    return "".join(out_lines)
