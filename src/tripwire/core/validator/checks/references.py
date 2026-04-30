"""Reference integrity: link resolution + bidirectional consistency."""

from __future__ import annotations

from pathlib import Path

import yaml

from tripwire.core import paths
from tripwire.core.reference_parser import extract_references
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.models.comment import Comment
from tripwire.models.issue import Issue
from tripwire.models.node import ConceptNode
from tripwire.models.session import AgentSession


def check_reference_integrity(ctx: ValidationContext) -> list[CheckResult]:
    """All `[[node-id]]`, `blocked_by`, `parent`, `related`, `repo`, `agent` refs resolve."""
    results: list[CheckResult] = []
    issue_ids = {e.model.id for e in ctx.issues}
    node_ids = {e.model.id for e in ctx.nodes}
    repo_slugs = set(ctx.project_config.repos.keys()) if ctx.project_config else set()
    agent_ids = _discover_agent_ids(ctx.project_dir)

    for entity in ctx.issues:
        issue: Issue = entity.model

        # [[node-id]] in body
        for ref in extract_references(issue.body):
            if ref not in node_ids and ref not in issue_ids:
                results.append(
                    CheckResult(
                        code="ref/dangling",
                        severity="error",
                        file=entity.rel_path,
                        field="body",
                        message=f"Reference [[{ref}]] does not resolve to any node or issue.",
                        fix_hint=(
                            f"Create {paths.NODES_DIR}/{ref}.yaml or fix the "
                            f"reference. Existing nodes: {sorted(node_ids)[:5]}..."
                            if node_ids
                            else f"Create {paths.NODES_DIR}/{ref}.yaml or fix the reference."
                        ),
                    )
                )

        # blocked_by
        for blocker in issue.blocked_by:
            if blocker not in issue_ids:
                results.append(
                    CheckResult(
                        code="ref/blocked_by",
                        severity="error",
                        file=entity.rel_path,
                        field="blocked_by",
                        message=f"blocked_by references unknown issue {blocker!r}.",
                    )
                )

        # parent
        if issue.parent is not None and issue.parent not in issue_ids:
            results.append(
                CheckResult(
                    code="ref/parent",
                    severity="error",
                    file=entity.rel_path,
                    field="parent",
                    message=f"parent references unknown issue {issue.parent!r}.",
                )
            )

        # repo
        if issue.repo and repo_slugs and issue.repo not in repo_slugs:
            results.append(
                CheckResult(
                    code="ref/repo",
                    severity="error",
                    file=entity.rel_path,
                    field="repo",
                    message=(
                        f"repo {issue.repo!r} not declared in project.yaml.repos."
                    ),
                    fix_hint=f"Add {issue.repo!r} to project.yaml under `repos:`.",
                )
            )

    for entity in ctx.nodes:
        node: ConceptNode = entity.model
        for related_id in node.related:
            if related_id not in node_ids:
                results.append(
                    CheckResult(
                        code="ref/related",
                        severity="error",
                        file=entity.rel_path,
                        field="related",
                        message=f"related references unknown node {related_id!r}.",
                    )
                )
        if (
            node.source
            and node.source.repo
            and repo_slugs
            and node.source.repo not in repo_slugs
        ):
            results.append(
                CheckResult(
                    code="ref/repo",
                    severity="error",
                    file=entity.rel_path,
                    field="source.repo",
                    message=(
                        f"source.repo {node.source.repo!r} not declared in project.yaml.repos."
                    ),
                )
            )
        for ref in extract_references(node.body):
            if ref not in node_ids and ref not in issue_ids:
                results.append(
                    CheckResult(
                        code="ref/dangling",
                        severity="error",
                        file=entity.rel_path,
                        field="body",
                        message=f"Reference [[{ref}]] does not resolve.",
                    )
                )

    for entity in ctx.sessions:
        session: AgentSession = entity.model
        for issue_key in session.issues:
            if issue_key not in issue_ids:
                results.append(
                    CheckResult(
                        code="ref/session_issue",
                        severity="error",
                        file=entity.rel_path,
                        field="issues",
                        message=f"session.issues references unknown issue {issue_key!r}.",
                    )
                )
        if agent_ids and session.agent not in agent_ids:
            results.append(
                CheckResult(
                    code="ref/session_agent",
                    severity="error",
                    file=entity.rel_path,
                    field="agent",
                    message=(
                        f"session.agent {session.agent!r} has no matching definition in agents/."
                    ),
                )
            )
        for binding in session.repos:
            if repo_slugs and binding.repo not in repo_slugs:
                results.append(
                    CheckResult(
                        code="ref/repo",
                        severity="error",
                        file=entity.rel_path,
                        field="repos",
                        message=(
                            f"session.repos[].repo {binding.repo!r} not declared in project.yaml.repos."
                        ),
                    )
                )

    for entity in ctx.comments:
        comment: Comment = entity.model
        if comment.issue_key not in issue_ids:
            results.append(
                CheckResult(
                    code="ref/comment_issue",
                    severity="error",
                    file=entity.rel_path,
                    field="issue_key",
                    message=f"Comment.issue_key references unknown issue {comment.issue_key!r}.",
                )
            )

    return results


def _discover_agent_ids(project_dir: Path) -> set[str]:
    """Read `<project>/agents/*.yaml` and return the set of declared agent ids."""
    agents_dir = project_dir / paths.AGENTS_DIR
    if not agents_dir.is_dir():
        return set()
    ids: set[str] = set()
    for path in sorted(agents_dir.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if isinstance(raw, dict) and "id" in raw:
            ids.add(str(raw["id"]))
        else:
            ids.add(path.stem)
    return ids


def check_bidirectional_related(ctx: ValidationContext) -> list[CheckResult]:
    """For every node A.related: [B], node B.related must contain A."""
    results: list[CheckResult] = []
    by_id = {e.model.id: e for e in ctx.nodes}
    for entity in ctx.nodes:
        node: ConceptNode = entity.model
        for related_id in node.related:
            other = by_id.get(related_id)
            if other is None:
                continue  # caught by ref integrity
            if node.id not in other.model.related:
                results.append(
                    CheckResult(
                        code="bidi/related",
                        severity="warning",
                        file=entity.rel_path,
                        field="related",
                        message=(
                            f"Node {node.id!r} declares related {related_id!r}, "
                            f"but {related_id!r} does not declare {node.id!r} in its related list."
                        ),
                        fix_hint="Run with --fix to add the missing back-reference.",
                    )
                )
    return results
