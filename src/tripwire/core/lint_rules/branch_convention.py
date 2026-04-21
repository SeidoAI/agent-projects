"""lint/branch_convention — handoff.yaml.branch must match the
``<type>/<slug>`` convention. Error-severity at handoff stage.

Parses the YAML frontmatter directly to avoid the Pydantic validator
raising before we can produce a structured lint finding.
"""

from __future__ import annotations

import yaml

from tripwire.core.branch_naming import is_valid_branch_name
from tripwire.core.linter import LintFinding, register_rule
from tripwire.core.paths import handoff_path


@register_rule(stage="handoff", code="lint/branch_convention", severity="error")
def _check(ctx):
    if ctx.session_id is None:
        return
    path = handoff_path(ctx.project_dir, ctx.session_id)
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return
    parts = text.split("---", 2)
    if len(parts) < 2:
        return
    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return  # malformed YAML handled by validator, not lint
    if not isinstance(frontmatter, dict):
        return
    branch = frontmatter.get("branch")
    if not isinstance(branch, str):
        return
    if not is_valid_branch_name(branch, project_dir=ctx.project_dir):
        yield LintFinding(
            code="lint/branch_convention",
            severity="error",
            message=(
                f"handoff.yaml.branch {branch!r} violates the <type>/<slug> "
                "convention (see BRANCH_NAMING.md)."
            ),
            file=f"sessions/{ctx.session_id}/handoff.yaml",
            fix_hint=(
                "Run `tripwire session derive-branch <session-id>` and use "
                "its output verbatim."
            ),
        )
