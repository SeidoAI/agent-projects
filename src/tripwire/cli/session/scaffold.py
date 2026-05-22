"""``tripwire session scaffold`` — render session planning artifacts."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session


@session_cmd.command("scaffold")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing files instead of skipping them.",
)
@click.option(
    "--artifact",
    "artifact_name",
    default=None,
    help=(
        "Scaffold a specific artifact by file name "
        "(e.g. `verification-checklist.md`). Default: every planning-"
        "phase, PM-owned, required artifact from the manifest."
    ),
)
@click.option(
    "--no-handoff",
    is_flag=True,
    default=False,
    help=(
        "Skip writing handoff.yaml. Default behaviour: write handoff.yaml "
        "with a derived branch name if the file does not yet exist."
    ),
)
def session_scaffold_cmd(
    session_id: str,
    project_dir: Path,
    force: bool,
    artifact_name: str | None,
    no_handoff: bool,
) -> None:
    """Render session planning artifacts from their Jinja templates.

    Before this command existed, PMs copy-pasted
    ``verification-checklist.md`` from other sessions because there
    was no scaffolder. Readiness checks that artifact at queue time,
    so the missing step was a recurring onboarding papercut.

    Default: render every manifest entry where
    ``produced_at=="planning"``, ``owned_by=="pm"``, and
    ``required=True``. Pass ``--artifact <file>`` to scaffold a
    single entry. ``--force`` overwrites existing files.
    """
    from tripwire.core.manifest_loader import load_artifact_manifest

    resolved, session = _resolve_and_load_session(project_dir, session_id)

    manifest, _findings = load_artifact_manifest(resolved)
    if manifest is None:
        raise click.ClickException(
            "No artifact manifest found at templates/artifacts/manifest.yaml"
        )

    if artifact_name:
        targets = [e for e in manifest.artifacts if e.file == artifact_name]
        if not targets:
            raise click.ClickException(
                f"artifact '{artifact_name}' not declared in manifest"
            )
    else:
        targets = [
            e
            for e in manifest.artifacts
            if e.produced_at == "planning" and e.owned_by == "pm" and e.required
        ]
        if not targets:
            click.echo("No planning-phase PM-owned required artifacts to scaffold.")
            return

    # Jinja loader pointed at the project's artifacts/templates dir.
    # init copies the packaged templates here at project-create time,
    # so scaffold respects whatever the user has customised locally.
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    from tripwire.core import paths as _paths

    templates_root = resolved / "templates" / "artifacts"
    env = Environment(
        loader=FileSystemLoader(str(templates_root)),
        autoescape=select_autoescape(disabled_extensions=("j2", "md")),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    session_root = _paths.session_dir(resolved, session_id)
    artifacts_dest_dir = _paths.session_artifacts_dir(resolved, session_id)
    session_root.mkdir(parents=True, exist_ok=True)
    artifacts_dest_dir.mkdir(parents=True, exist_ok=True)

    context = {
        "session": session,
        "session_id": session_id,
        "session_name": session.name,
        "agent": session.agent,
        "issues": session.issues,
    }

    wrote = 0
    for entry in targets:
        dest = artifacts_dest_dir / entry.file
        if dest.exists() and not force:
            click.echo(f"  Skipping {entry.file} — exists (use --force to overwrite)")
            continue
        try:
            tpl = env.get_template(entry.template)
        except Exception as exc:
            raise click.ClickException(
                f"template {entry.template!r} not found under {templates_root}: {exc}"
            ) from exc
        rendered = tpl.render(**context)
        dest.write_text(rendered, encoding="utf-8")
        click.echo(f"  Wrote {_paths.SESSION_ARTIFACTS_SUBDIR}/{entry.file}")
        wrote += 1

    if wrote == 0 and not artifact_name:
        click.echo("  (nothing scaffolded — all targets already existed)")

    # Handoff.yaml — session state, not an artifact (lives outside the
    # manifest), but conceptually a planning-phase PM-owned file. PMs
    # should not have to hand-craft it; derive the branch from the
    # session's primary issue kind and write it here unless suppressed.
    if not no_handoff and not artifact_name:
        _scaffold_handoff(resolved, session, force)


def _scaffold_handoff(project_dir: Path, session, force: bool) -> None:
    """Write sessions/<id>/handoff.yaml with a derived branch name.

    Skips silently if the file already exists and `force` is False.
    Logs a warning (without failing) if branch derivation fails — the
    PM can still hand-write the file as a fallback.
    """
    import uuid as _uuid
    from datetime import datetime, timezone

    from tripwire.core.branch_naming import BranchNameError, derive_branch_name
    from tripwire.core.handoff_store import handoff_path, save_handoff
    from tripwire.core.store import load_issue
    from tripwire.models.handoff import SessionHandoff

    dest = handoff_path(project_dir, session.id)
    if dest.exists() and not force:
        click.echo("  Skipping handoff.yaml — exists (use --force to overwrite)")
        return

    # Pick the first issue's kind as the branch type. Fallback to "feat"
    # if no issues are bound or the first issue's kind isn't a valid
    # branch type for this project.
    primary_kind = "feat"
    if session.issues:
        try:
            first_issue = load_issue(project_dir, session.issues[0])
            if first_issue.kind:
                primary_kind = first_issue.kind
        except (FileNotFoundError, AttributeError):
            pass

    try:
        branch = derive_branch_name(session.id, primary_kind, project_dir=project_dir)
    except BranchNameError as exc:
        click.echo(f"  Skipping handoff.yaml — could not derive branch: {exc}")
        return

    handoff = SessionHandoff(
        uuid=_uuid.uuid4(),
        session_id=session.id,
        handoff_at=datetime.now(tz=timezone.utc),
        handed_off_by="pm",
        branch=branch,
    )
    save_handoff(project_dir, handoff)
    click.echo(f"  Wrote handoff.yaml (branch: {branch})")
