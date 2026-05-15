"""The inbox HTTP surface has no POST-create endpoint.

Philosophy §6 ("The PM agent as attention curator") names the rule:

    *"The route layer has no POST-create endpoint — the PM agent's
    authoring surface is the filesystem, matching the existing
    'agents create entities by writing files' rule for issues,
    sessions, and nodes."*

The motivation is the §6 thesis: curated channels stay valuable
because someone whose name is on the signal cares it's worth reading.
A POST-create endpoint opens authoring to any client that can hit
the route — UI, scripts, CI, third-party tools — and the curation
collapses one over-eager writer at a time.

The two legal mutations are:

  - ``POST /{entry_id}/resolve`` — mark an existing entry resolved.
    The entry's content is unchanged; this is the post-attention flip.
  - (none for create) — entries are authored by the PM agent writing
    ``inbox/<id>.md`` to the filesystem via its Write tool.

This test parses the inbox route module's source and asserts no
POST route exists that creates a new entry (i.e. matches an
authoring path shape rather than ``/{entry_id}/{action}``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import tripwire

INBOX_ROUTE_FILE = Path(tripwire.__file__).parent / "ui" / "routes" / "inbox.py"

# The single legal POST shape: an action on an existing entry. Any
# POST that doesn't match this shape is a create-or-update primitive
# and a §6 regression.
LEGAL_POST_PATH_SUFFIXES = {"/{entry_id}/resolve"}


def _route_path_from_decorator(decorator: ast.expr) -> tuple[str, str] | None:
    """Return ``(method, path)`` for an ``@router.post("/foo")`` /
    ``@router.get("/bar")`` decorator, or None for anything else."""
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute):
        return None
    if not (
        isinstance(decorator.func.value, ast.Name)
        and decorator.func.value.id == "router"
    ):
        return None
    method = decorator.func.attr  # "get" | "post" | "delete" | ...
    if not decorator.args:
        return None
    first = decorator.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return method, first.value
    return None


def test_inbox_router_exposes_no_post_create_endpoint():
    """Parse ``ui/routes/inbox.py``; the only POST route is the
    resolve flip on an existing entry id.

    A failure here means someone added a creation surface (e.g.
    ``POST /``, ``POST /create``, ``POST /entries``) to the inbox.
    §6 forbids this — the PM agent's authoring surface is the
    filesystem, and the route layer reads + flips resolved state
    only.
    """
    tree = ast.parse(INBOX_ROUTE_FILE.read_text(encoding="utf-8"))

    post_paths: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                parsed = _route_path_from_decorator(decorator)
                if parsed is None:
                    continue
                method, path = parsed
                if method == "post":
                    post_paths.append(path)

    illegal = [p for p in post_paths if p not in LEGAL_POST_PATH_SUFFIXES]
    assert not illegal, (
        "Philosophy §6 violation — inbox route exposes a non-resolve POST\n"
        "endpoint. The route layer has NO POST-create surface; the PM\n"
        "agent authors inbox entries by writing to the filesystem.\n"
        "\n"
        f"Illegal POST routes: {illegal}\n"
        f"Legal POSTs: {sorted(LEGAL_POST_PATH_SUFFIXES)}\n"
        "\n"
        "Fix: delete the new POST route. If the human needs a UI affordance\n"
        "to author an inbox entry, route through the PM agent (e.g. open\n"
        "the agent in a dialog that prompts it to write the entry)."
    )

    # Sanity: assert resolve is still there. If it disappears, the
    # rest of the test passes trivially — surface the absence loudly.
    assert "/{entry_id}/resolve" in post_paths, (
        "inbox router no longer exposes POST /{entry_id}/resolve. The\n"
        "philosophy doc still describes resolve as a legal route — "
        "either restore it or update §6 to reflect the new shape."
    )
