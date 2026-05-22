"""v0.6a: sessions in ``queued`` state require a valid ``handoff.yaml``."""

from __future__ import annotations

from pydantic import ValidationError

from tripwire.core import paths
from tripwire.core.parser import ParseError, parse_frontmatter_body
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.models.session import AgentSession


def check_handoff_artifact(ctx: ValidationContext) -> list[CheckResult]:
    """v0.6a: sessions in ``queued`` state require a valid handoff.yaml.

    Three possible findings:
    - ``handoff_schema/required_at_queued`` — session queued but file missing.
    - ``handoff_schema/branch_format`` — handoff.yaml.branch violates
      the ``<type>/<slug>`` convention (extracted via raw YAML parse so
      malformed branches surface cleanly, not as generic schema errors).
    - ``handoff_schema/malformed`` — any other parse/schema failure.
    """
    results: list[CheckResult] = []

    for entity in ctx.sessions:
        session: AgentSession = entity.model
        if session.status != "queued":
            continue

        handoff_file_rel = f"{paths.SESSIONS_DIR}/{session.id}/{paths.HANDOFF_FILENAME}"
        handoff_file = paths.handoff_path(ctx.project_dir, session.id)
        if not handoff_file.is_file():
            results.append(
                CheckResult(
                    code="handoff_schema/required_at_queued",
                    severity="error",
                    file=handoff_file_rel,
                    message=(
                        f"Session {session.id!r} is queued but handoff.yaml "
                        "is missing — launch requires a structured handoff "
                        "artifact."
                    ),
                    fix_hint=(
                        "Run `/pm-session-queue` which creates handoff.yaml, "
                        "or write sessions/<id>/handoff.yaml manually."
                    ),
                )
            )
            continue

        # Check branch format via raw YAML parse first so malformed branch
        # strings surface as handoff_schema/branch_format (the specific code
        # callers expect), not as a generic Pydantic ValidationError.
        try:
            text = handoff_file.read_text(encoding="utf-8")
            frontmatter, _body = parse_frontmatter_body(text)
        except (ParseError, OSError) as exc:
            results.append(
                CheckResult(
                    code="handoff_schema/malformed",
                    severity="error",
                    file=handoff_file_rel,
                    message=f"handoff.yaml failed to parse: {exc}",
                )
            )
            continue

        branch = frontmatter.get("branch") if isinstance(frontmatter, dict) else None
        if isinstance(branch, str):
            from tripwire.core.branch_naming import is_valid_branch_name

            if not is_valid_branch_name(branch, project_dir=ctx.project_dir):
                results.append(
                    CheckResult(
                        code="handoff_schema/branch_format",
                        severity="error",
                        file=handoff_file_rel,
                        field="branch",
                        message=(
                            f"handoff.yaml.branch {branch!r} does not match "
                            "the <type>/<slug> convention."
                        ),
                        fix_hint=(
                            "Run `tripwire session derive-branch <session-id>` "
                            "and copy its output."
                        ),
                    )
                )
                continue

        # Pydantic validation catches any other schema problems (missing
        # required fields, bad types). The branch validator inside
        # SessionHandoff raises the same branch-format error, but this
        # function already handled that code above, so any ValidationError
        # here is structural.
        try:
            from tripwire.core.handoff_store import load_handoff

            load_handoff(ctx.project_dir, session.id)
        except ValidationError as exc:
            results.append(
                CheckResult(
                    code="handoff_schema/malformed",
                    severity="error",
                    file=handoff_file_rel,
                    message=f"handoff.yaml schema validation failed: {exc}",
                )
            )
        except ValueError as exc:
            # branch format (caught again via SessionHandoff validator) or
            # unparseable YAML.
            results.append(
                CheckResult(
                    code="handoff_schema/malformed",
                    severity="error",
                    file=handoff_file_rel,
                    message=str(exc),
                )
            )

    return results
