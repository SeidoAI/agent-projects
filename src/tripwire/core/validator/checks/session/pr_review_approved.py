"""Every session at ``verified`` or past must have a passing ``review.json``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.validator.checks._helpers import _session_at_or_past


def _load_review_json(project_dir: Path, sid: str) -> dict[str, Any] | None:
    """Read ``sessions/<sid>/review.json`` or return None if absent/garbled."""
    review_path = paths.session_dir(project_dir, sid) / "review.json"
    if not review_path.is_file():
        return None
    try:
        data = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def check_pr_review_approved(ctx: ValidationContext) -> list[CheckResult]:
    """Every session at `verified` or past must have a passing review.

    Reads ``sessions/<sid>/review.json`` and requires ``exit_code ≤ 1``.
    Missing/garbled file means review never ran.

    Code: ``session/review_not_approved``.
    """
    results: list[CheckResult] = []
    for entity in ctx.sessions:
        session = entity.model
        sid = session.id
        if not _session_at_or_past(ctx, str(session.status), "verified"):
            continue

        data = _load_review_json(ctx.project_dir, sid)
        if data is None:
            results.append(
                CheckResult(
                    code="session/review_not_approved",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/review.json",
                    message=(
                        f"Session {sid!r}: no review.json — run "
                        f"`tripwire session review {sid}` before completing."
                    ),
                    fix_hint=(
                        f"Run `tripwire session review {sid}` to produce "
                        f"review.json with a verdict and exit_code."
                    ),
                )
            )
            continue

        exit_code = data.get("exit_code")
        if not isinstance(exit_code, int):
            results.append(
                CheckResult(
                    code="session/review_not_approved",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/review.json",
                    field="exit_code",
                    message=(
                        f"Session {sid!r}: review.json missing a valid "
                        f"integer `exit_code`."
                    ),
                    fix_hint=(
                        f"Re-run `tripwire session review {sid}` to regenerate "
                        f"review.json."
                    ),
                )
            )
            continue

        if exit_code > 1:
            verdict = data.get("verdict", "?")
            results.append(
                CheckResult(
                    code="session/review_not_approved",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/review.json",
                    field="exit_code",
                    message=(
                        f"Session {sid!r}: last review reported verdict="
                        f"{verdict!r} (exit_code={exit_code}). Fix findings "
                        f"and re-review."
                    ),
                    fix_hint=(
                        "Address the review findings, then re-run "
                        f"`tripwire session review {sid}`."
                    ),
                )
            )
    return results
