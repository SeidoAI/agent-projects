"""``tripwire session insights`` — review/apply/reject agent node proposals.

This file declares the ``insights`` Click group AND its three
subcommands (``list``, ``apply``, ``reject``). The group is small
enough that splitting each leaf into its own module would harm
readability more than it would help — all three share one model
(:class:`tripwire.models.session.AgentSession`'s insights.yaml) and a
single store (:mod:`tripwire.core.insights_store`).
"""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd


@session_cmd.group(name="insights")
def session_insights_cmd() -> None:
    """Review and apply session-proposed concept-node insights."""


@session_insights_cmd.command("list")
@click.argument("session_id")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def session_insights_list_cmd(
    session_id: str, project_dir: Path, output_format: str
) -> None:
    """List node proposals from a session's insights.yaml."""
    from tripwire.core.insights_store import load_insights

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    insights = load_insights(resolved, session_id)

    if output_format == "json":
        click.echo(insights.model_dump_json(indent=2, exclude_none=True))
        return

    if not insights.proposals:
        click.echo("No insight proposals.")
        return

    for p in insights.proposals:
        click.echo(f"{p.kind} {p.id}")
        if p.kind == "new_node":
            click.echo(f"  name: {p.name}")
        else:
            click.echo(f"  delta: {p.delta}")
        click.echo(f"  rationale: {p.rationale}")
        click.echo("")


@session_insights_cmd.command("apply")
@click.argument("session_id")
@click.option(
    "--proposal",
    "proposal_id",
    required=True,
    help="The proposal id to apply",
)
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
def session_insights_apply_cmd(
    session_id: str, proposal_id: str, project_dir: Path
) -> None:
    """Materialise a proposal: new_node writes nodes/<id>.yaml; update_node appends delta."""
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    from tripwire.core.insights_store import load_insights, save_insights
    from tripwire.core.node_store import load_node, save_node
    from tripwire.models import ConceptNode

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    insights = load_insights(resolved, session_id)

    proposal = next((p for p in insights.proposals if p.id == proposal_id), None)
    if proposal is None:
        raise click.ClickException(f"Unknown proposal id {proposal_id!r}")

    if proposal.kind == "new_node":
        # `type` is required on new_node proposals (enforced by the model
        # validator); no hardcoded fallback here.
        node = ConceptNode(
            id=proposal.id,
            type=proposal.type,
            name=proposal.name or proposal.id,
            status="active",
            body=proposal.body or "",
            related=proposal.related,
        )
        save_node(resolved, node, update_cache=False)
        click.echo(f"Created node {proposal.id} (type={proposal.type})")
    else:
        try:
            node = load_node(resolved, proposal.id)
        except FileNotFoundError as exc:
            raise click.ClickException(
                f"Cannot apply update: node {proposal.id!r} does not exist."
            ) from exc
        stamp = _dt.now(tz=_tz.utc).strftime("%Y-%m-%d")
        new_body = (
            node.body.rstrip()
            + f"\n\n## Updated {stamp} (session {session_id})\n{proposal.delta}\n"
        )
        save_node(
            resolved,
            node.model_copy(update={"body": new_body}),
            update_cache=False,
        )
        click.echo(f"Updated node {proposal.id}")

    remaining = [p for p in insights.proposals if p.id != proposal_id]
    save_insights(
        resolved,
        session_id,
        insights.model_copy(update={"proposals": remaining}),
    )


@session_insights_cmd.command("reject")
@click.argument("session_id")
@click.option("--proposal", "proposal_id", required=True)
@click.option("--reason", default="", help="Why rejected (for audit)")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
def session_insights_reject_cmd(
    session_id: str, proposal_id: str, reason: str, project_dir: Path
) -> None:
    """Drop a proposal from insights.yaml and record it in insights.rejected.yaml."""
    from tripwire.core.insights_store import (
        load_insights,
        record_rejection,
        save_insights,
    )

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    insights = load_insights(resolved, session_id)

    proposal = next((p for p in insights.proposals if p.id == proposal_id), None)
    if proposal is None:
        raise click.ClickException(f"Unknown proposal id {proposal_id!r}")

    record_rejection(resolved, session_id, proposal_id, reason)
    remaining = [p for p in insights.proposals if p.id != proposal_id]
    save_insights(
        resolved,
        session_id,
        insights.model_copy(update={"proposals": remaining}),
    )
    click.echo(f"Rejected proposal {proposal_id}")
