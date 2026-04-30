"""End-to-end smoke test for the v0.9 entity graph substrate.

Builds a minimal project with every entity type that contributes to
the unified index (issue, concept node, session, comment), runs the
full cache rebuild via the same code path the validator uses, and
asserts cross-type traversal returns the expected ids and that pin
staleness fires when a target's contract_changed_at advances.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from click.testing import CliRunner

from tripwire.cli.graph import graph_cmd
from tripwire.core.graph.cache import full_rebuild
from tripwire.core.graph.index import UnifiedIndex
from tripwire.core.node_store import save_node
from tripwire.core.store import save_issue, save_project
from tripwire.core.validator import validate_project
from tripwire.models import (
    ConceptNode,
    Issue,
    NodeSource,
    ProjectConfig,
    RepoEntry,
)


def _seed(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    save_project(
        proj,
        ProjectConfig(
            name="t",
            key_prefix="TST",
            repos={"o/r": RepoEntry()},
            next_issue_number=1,
        ),
    )

    save_node(
        proj,
        ConceptNode(
            id="auth-system",
            type="system",
            name="Auth",
            version=1,
            source=NodeSource(
                repo="o/r",
                path="src/auth.py",
                content_hash="sha256:dead",
            ),
        ),
        update_cache=False,
    )

    for key in ("TST-1", "TST-2"):
        save_issue(
            proj,
            Issue(
                id=key,
                title=key,
                status="todo",
                priority="medium",
                executor="ai",
                verifier="required",
                blocked_by=["TST-1"] if key == "TST-2" else [],
                body=(
                    "## Context\nUses [[auth-system]].\n"
                    "## Implements\nREQ-1\n"
                    "## Repo scope\n- o/r\n"
                    "## Requirements\n- thing\n"
                    "## Execution constraints\nIf ambiguous, stop and ask.\n"
                    "## Acceptance criteria\n- [ ] thing\n"
                    "## Test plan\n```\nuv run pytest\n```\n"
                    "## Dependencies\nnone\n"
                    "## Definition of Done\n- [ ] done\n"
                ),
            ),
            update_cache=False,
        )

    sdir = proj / "sessions" / "session-foo"
    sdir.mkdir(parents=True)
    (sdir / "session.yaml").write_text(
        "---\n"
        + yaml.safe_dump(
            {
                "id": "session-foo",
                "name": "foo",
                "agent": "developer",
                "issues": ["TST-1"],
            },
            sort_keys=False,
        )
        + "---\n",
        encoding="utf-8",
    )

    cdir = proj / "issues" / "TST-1" / "comments"
    cdir.mkdir(parents=True)
    (cdir / "01-pm-feedback-2026-04-30.yaml").write_text(
        "---\n"
        + yaml.safe_dump(
            {
                "issue_key": "TST-1",
                "author": "agent:pm",
                "type": "pm_feedback",
                "created_at": datetime.now(tz=timezone.utc).isoformat(),
            },
            sort_keys=False,
        )
        + "---\nSee [[auth-system]] for context.\n",
        encoding="utf-8",
    )

    return proj


def test_cross_type_traversal_returns_session_and_comment(tmp_path: Path) -> None:
    proj = _seed(tmp_path)
    cache = full_rebuild(proj)
    idx = UnifiedIndex(project_dir=proj, cache=cache)

    # Downstream of TST-1: TST-2 (depends_on), session-foo (refs),
    # the comment under TST-1 (refs).
    downstream = set(idx.downstream("TST-1"))
    assert "TST-2" in downstream
    assert "session-foo" in downstream
    assert any(d.startswith("TST-1:") for d in downstream)

    # Downstream of auth-system: TST-1 + TST-2 (issue body refs),
    # the comment (body ref), and session-foo isn't here (it doesn't
    # reference auth-system in its body or issues list).
    downstream_node = set(idx.downstream("auth-system"))
    assert "TST-1" in downstream_node
    assert "TST-2" in downstream_node


def test_graph_query_cli_against_seeded_project(tmp_path: Path) -> None:
    proj = _seed(tmp_path)
    full_rebuild(proj)

    runner = CliRunner()
    result = runner.invoke(
        graph_cmd,
        [
            "query",
            "downstream",
            "TST-1",
            "--project-dir",
            str(proj),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    ids = set(payload["ids"])
    assert "session-foo" in ids
    assert "TST-2" in ids


def test_pin_staleness_fires_when_target_contract_advances(tmp_path: Path) -> None:
    proj = _seed(tmp_path)

    # Add an issue that pins auth-system at v1.
    save_issue(
        proj,
        Issue(
            id="TST-3",
            title="pinned",
            status="todo",
            priority="medium",
            executor="ai",
            verifier="required",
            body=(
                "## Context\nUses [[auth-system@v1]].\n"
                "## Implements\nREQ-1\n"
                "## Repo scope\n- o/r\n"
                "## Requirements\n- thing\n"
                "## Execution constraints\nIf ambiguous, stop and ask.\n"
                "## Acceptance criteria\n- [ ] thing\n"
                "## Test plan\n```\nuv run pytest\n```\n"
                "## Dependencies\nnone\n"
                "## Definition of Done\n- [ ] done\n"
            ),
        ),
        update_cache=False,
    )

    # First validate: pin is fresh, no stale_pin findings.
    initial = validate_project(proj, strict=False, fix=False)
    stale_findings = [
        f
        for f in [*initial.errors, *initial.warnings]
        if f.code == "references/stale_pin"
    ]
    assert stale_findings == []

    # Bump the auth-system node: PM marks contract change at v2.
    bumped = ConceptNode(
        id="auth-system",
        type="system",
        name="Auth",
        version=2,
        contract_changed_at=2,
        source=NodeSource(
            repo="o/r",
            path="src/auth.py",
            content_hash="sha256:dead",
        ),
    )
    save_node(proj, bumped, update_cache=False)

    after = validate_project(proj, strict=False, fix=False)
    stale = [
        f for f in [*after.errors, *after.warnings] if f.code == "references/stale_pin"
    ]
    assert len(stale) == 1
    assert "auth-system" in stale[0].message
