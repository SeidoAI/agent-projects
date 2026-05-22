"""``project.yaml.repos`` must declare the project's own meta-repo (PT repo)."""

from __future__ import annotations

from pathlib import Path

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext


def check_project_repos_present(ctx: ValidationContext) -> list[CheckResult]:
    """``project.yaml.repos`` must declare the project's own meta-repo
    (the "PT repo") as at least one entry (v0.10.0+).

    The dashboard distinguishes the PT repo (slug ending in
    ``/<project.name>`` OR with ``local`` matching the project dir)
    from generic code-output repos. Without a PT-repo entry the
    "project repo · …" affordance can't render. Mirror the JS predicate
    in ``web/src/features/dashboard/ProjectDashboard.tsx::isPtRepo``
    so the two surfaces agree.

    Validate-time check (not schema-time) — projects that load but
    lack a PT repo surface as a structured finding instead of
    crashing the whole validator with a Pydantic exception.
    """
    config = ctx.project_config
    if config is None:
        return []
    project_dir = ctx.project_dir.resolve()
    name = config.name
    repos = config.repos or {}

    for slug, entry in repos.items():
        # Match by local-path equality (entry.local == project.dir)
        # OR by slug suffix (slug.endswith('/' + name)). Either is
        # enough, mirroring the dashboard's `isPtRepo` predicate.
        local = entry.local if entry is not None else None
        if local is not None:
            try:
                if Path(local).expanduser().resolve() == project_dir:
                    return []
            except OSError:
                # An unresolvable path doesn't match — fall through
                # to the slug-suffix test. A separate check could
                # surface the dangling path; out of scope here.
                pass
        if slug.endswith("/" + name):
            return []

    return [
        CheckResult(
            code="project/repos_required",
            severity="error",
            file=paths.PROJECT_CONFIG,
            field="repos",
            message=(
                f"project.yaml.repos has no entry for the project's own "
                f"repo (slug ending in /{name}, or local matching the "
                "project dir); the v0.10.0 dashboard can't render the "
                "'project repo' affordance without it."
            ),
            fix_hint=(
                "Add an entry to project.yaml.repos that identifies the "
                "project's own meta-repo:\n"
                f"  repos:\n"
                f"    SeidoAI/project-{name}:\n"
                f"      local: <project-dir>"
            ),
        )
    ]
