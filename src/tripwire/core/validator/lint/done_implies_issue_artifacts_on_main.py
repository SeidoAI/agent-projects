"""Issues at ``status: done`` must have their required artifacts on origin/main.

The correctness contract for issues. Every required file listed in
``project.yaml.artifact_manifest.issue_required`` (defaults to
``developer.md`` and ``verified.md``) must be present on the merged-
main snapshot of the project tracking repo (``origin/main``); "on
main" is the only state that counts.

Online-first. We don't ``git fetch`` from inside validate (would hit
the network on every run). If ``origin/main`` is unreadable (no remote,
no fetch yet, repo isn't a git checkout), emit a single
``done_implies_artifacts/main_unavailable`` warning and skip the
per-issue checks — the operator can re-run after a fetch.

The session half of this rule (which gated on the deleted
``legacy_completed`` status and checked the pre-v0.8 flat artifact
layout) was removed in KUI-158. The modern session check is
``check_artifact_presence`` in ``validator/__init__.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tripwire.core.git_helpers import MainTreeUnavailable, list_paths_on_main
from tripwire.core.store import PROJECT_CONFIG_FILENAME

if TYPE_CHECKING:
    from tripwire.core.validator import CheckResult, ValidationContext


def check(ctx: ValidationContext) -> list[CheckResult]:
    from tripwire.core.validator import CheckResult

    if ctx.project_config is None:
        return []

    done_issues = [e for e in ctx.issues if e.model.status == "completed"]
    if not done_issues:
        return []

    try:
        on_main = list_paths_on_main(ctx.project_dir)
    except MainTreeUnavailable as exc:
        return [
            CheckResult(
                code="done_implies_artifacts/main_unavailable",
                severity="warning",
                file=PROJECT_CONFIG_FILENAME,
                message=(
                    f"Cannot read origin/main; `done` ⇒ artifact rule "
                    f"unverified ({exc})."
                ),
                fix_hint=(
                    "Run `git fetch origin` in the project tracking repo, "
                    "then re-run validate. Network-isolated environments "
                    "can ignore this warning."
                ),
            )
        ]

    manifest = ctx.project_config.artifact_manifest
    results: list[CheckResult] = []

    for entity in done_issues:
        issue = entity.model
        for fname in manifest.issue_required:
            rel = f"issues/{issue.id}/{fname}"
            if rel in on_main:
                continue
            results.append(
                CheckResult(
                    code="done_implies_artifacts/missing_on_main",
                    severity="error",
                    file=entity.rel_path,
                    message=(
                        f"Issue {issue.id!r} is `done` but required artifact "
                        f"{fname!r} is missing on origin/main."
                    ),
                    fix_hint=(
                        f"Write {rel} on a feature branch and merge it to "
                        f"origin/main. The on-main check looks at the merged "
                        f"snapshot — local working-tree files don't count."
                    ),
                )
            )

    return results
