"""Per-issue artifact presence gated on the issue artifact manifest."""

from __future__ import annotations

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext


def check_issue_artifact_presence(ctx: ValidationContext) -> list[CheckResult]:
    """Every issue at status ≥ required_at_status must have its artifact file.

    Loads the issue artifact manifest (shipped + project overrides), then for
    each issue checks whether the required files exist once the issue has
    reached the status gate.
    """
    from tripwire.core.issue_artifact_store import (
        load_issue_artifact_manifest,
        status_at_or_past,
    )

    results: list[CheckResult] = []
    try:
        manifest = load_issue_artifact_manifest(ctx.project_dir)
    except FileNotFoundError:
        # Manifest template missing from the installed package — not fatal.
        return results
    except Exception as exc:
        results.append(
            CheckResult(
                code="issue_artifact_manifest/invalid",
                severity="error",
                file="templates/issue_artifacts/manifest.yaml",
                message=f"Failed to load issue artifact manifest: {exc}",
            )
        )
        return results

    for entity in ctx.issues:
        issue = entity.model
        for entry in manifest.artifacts:
            if not entry.required:
                continue
            if not status_at_or_past(
                issue.status, entry.required_at_status, ctx.project_dir
            ):
                continue
            artifact_path = paths.issue_docs_dir(ctx.project_dir, issue.id) / entry.file
            rel_path = (
                f"{paths.ISSUES_DIR}/{issue.id}/{paths.ISSUE_DOCS_SUBDIR}/{entry.file}"
            )
            if artifact_path.is_file():
                continue
            results.append(
                CheckResult(
                    code="issue_artifact/missing",
                    severity="error",
                    file=rel_path,
                    message=(
                        f"Issue {issue.id!r} ({issue.status}) has reached "
                        f"{entry.required_at_status!r} but is missing "
                        f"required artifact {entry.file!r}."
                    ),
                    fix_hint=(f"Write {rel_path} from {entry.template}."),
                )
            )
    return results
