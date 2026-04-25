"""v0.7.9 §A9 — pm-response follow-ups must reference existing issues.

For every session's local ``pm-response.md``, parse the frontmatter
``items:`` list and verify each ``follow_up: KUI-XX`` resolves to an
issue the validator knows about. Catches the "PM cited a follow-up
ticket but never created it" state.

Reads from local disk (not origin/main) — the rule operates on the
project's working tree, since dangling references should be caught
before they reach main.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tripwire.core.parser import ParseError, parse_frontmatter_body

if TYPE_CHECKING:
    from tripwire.core.validator import CheckResult, ValidationContext


def check(ctx: ValidationContext) -> list[CheckResult]:
    from tripwire.core.validator import CheckResult

    if not ctx.sessions:
        return []

    known_issue_ids = {entity.model.id for entity in ctx.issues}
    results: list[CheckResult] = []

    for entity in ctx.sessions:
        sid = entity.model.id
        rel = f"sessions/{sid}/pm-response.md"
        path = ctx.project_dir / "sessions" / sid / "pm-response.md"
        if not path.exists():
            continue

        try:
            frontmatter, _body = parse_frontmatter_body(
                path.read_text(encoding="utf-8")
            )
        except ParseError as exc:
            results.append(
                CheckResult(
                    code="pm_response_followups_resolve/parse_error",
                    severity="warning",
                    file=rel,
                    message=(f"Could not parse {rel!r} as frontmatter+body: {exc}"),
                    fix_hint=(
                        "Ensure the file starts with `---` and contains "
                        "valid YAML frontmatter."
                    ),
                )
            )
            continue

        items = frontmatter.get("items") or []
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue
            ref = item.get("follow_up")
            if not ref:
                continue
            if ref in known_issue_ids:
                continue
            results.append(
                CheckResult(
                    code="pm_response_followups_resolve/dangling_reference",
                    severity="error",
                    file=rel,
                    message=(
                        f"pm-response item references follow_up: {ref!r} "
                        f"but no such issue exists in this project."
                    ),
                    fix_hint=(
                        f"Either create issue {ref}, or remove/update the "
                        f"follow_up field on that item."
                    ),
                )
            )

    return results
