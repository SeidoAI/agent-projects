"""Shared pytest fixtures."""

from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture
def tmp_path_project(tmp_path: Path) -> Path:
    """Create a minimal tripwire project with default manifest, return its path.

    Mirrors the minimum shape expected by validator and CLI: project.yaml,
    issues/, nodes/, sessions/, docs/, and a default manifest in
    templates/artifacts/manifest.yaml matching the shipping template.
    """
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    # v0.9.4: include canonical statuses + transitions so issue-status
    # validators (`status/unreachable`, `enum/issue_status`) pass without
    # each test having to seed them. Mirrors the project.yaml shape that
    # `tripwire init` writes out of the box.
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "tmp",
                "key_prefix": "TMP",
                "next_issue_number": 1,
                "next_session_number": 1,
                "statuses": [
                    "planned",
                    "queued",
                    "executing",
                    "in_review",
                    "verified",
                    "completed",
                    "abandoned",
                    "deferred",
                ],
                "status_transitions": {
                    "planned": ["queued", "abandoned"],
                    "queued": ["executing", "abandoned", "planned"],
                    "executing": ["in_review", "abandoned", "queued"],
                    "in_review": ["verified", "executing"],
                    "verified": ["completed", "in_review"],
                    "completed": [],
                    "abandoned": ["planned"],
                    "deferred": ["planned", "queued", "abandoned"],
                },
                # v0.10.0+ requires the project's own meta-repo (PT
                # repo) to appear in `repos:` — slug must end with
                # '/<project.name>' or `local` must equal the project
                # dir. Slug-suffix is the easier match here since the
                # tmp_path is unstable.
                "repos": {
                    "SeidoAI/tmp": {"local": None},
                    "SeidoAI/web-app-backend": {"local": None},
                },
            }
        )
    )
    for sub in ("issues", "nodes", "sessions", "docs", "plans"):
        (project_dir / sub).mkdir()
    # v0.13: workflow.yaml is required for execute_transition to resolve
    # routes. Provide a minimal coding-session covering all SessionStatus
    # values + the transitions the test suite exercises.
    # Reference every implemented validator on the planned-to-queued
    # route so `declared_validator_ids` returns the full catalog when
    # tests call `validate_project` without `validator_ids=`. Otherwise
    # only `v_workflow_well_formed` would run.
    _all_validators = [
        "v_artifact_presence",
        "v_bidirectional_related",
        "v_comment_provenance",
        "v_done_implies_issue_artifacts_on_main",
        "v_done_implies_session_completed",
        "v_enum_values",
        "v_freshness",
        "v_handoff_artifact",
        "v_id_collisions",
        "v_id_format",
        "v_issue_artifact_presence",
        "v_issue_body_structure",
        "v_issue_session_status_compatibility",
        "v_manifest_phase_ownership_consistent",
        "v_manifest_schema",
        "v_no_orphan_proj_branches",
        "v_no_stale_pins",
        "v_phase_requirements",
        "v_pm_response_covers_self_review",
        "v_pm_response_followups_resolve",
        "v_pr_merged_for_session",
        "v_pr_review_approved",
        "v_pr_review_code_review_skill",
        "v_pr_review_evidence",
        "v_pr_review_external_reviewer",
        "v_pr_review_threshold_findings",
        "v_project_repos_present",
        "v_project_standards",
        "v_reference_integrity",
        "v_self_review_implies_pm_response",
        "v_session_has_developer_md",
        "v_session_has_verified_md",
        "v_session_issue_coherence",
        "v_status_transitions",
        "v_timestamps",
        "v_uuid_present",
        "v_workflow_well_formed",
        "v_workspace_link",
        "v_worktree_paths_unique",
    ]
    _route_lines = []
    for f, t, kind in [
        ("planned", "queued", "forward"),
        ("queued", "executing", "forward"),
        ("executing", "in_review", "forward"),
        ("in_review", "verified", "forward"),
        ("verified", "completed", "forward"),
        ("in_review", "executing", "revert"),
        ("verified", "in_review", "revert"),
        ("executing", "paused", "side"),
        ("executing", "failed", "side"),
        ("paused", "executing", "forward"),
        ("failed", "executing", "forward"),
        ("paused", "queued", "revert"),
        ("paused", "completed", "revert"),
        ("completed", "paused", "revert"),
        ("planned", "abandoned", "side"),
        ("queued", "abandoned", "side"),
        ("executing", "abandoned", "side"),
        ("paused", "abandoned", "side"),
        ("failed", "abandoned", "side"),
        ("in_review", "abandoned", "side"),
        ("verified", "abandoned", "side"),
    ]:
        _route_lines.append(
            f"      - id: {f}-to-{t}\n"
            f"        actor: pm-agent\n"
            f"        from: {f}\n"
            f"        to: {t}\n"
            f"        kind: {kind}\n"
        )
        if kind == "revert":
            _route_lines.append(
                "        preserve_fields:\n"
                "          - runtime_state.claude_session_id\n"
                "          - runtime_state.worktrees\n"
            )
        # The in_review → verified route runs the PR-review tripwires
        # at gate time so test_transition_to_verified_blocked_by_missing_evidence
        # exercises the right surface.
        if (f, t) == ("in_review", "verified"):
            _route_lines.append(
                "        controls:\n"
                "          tripwires:\n"
                "            - v_pr_review_evidence\n"
                "            - v_pr_review_threshold_findings\n"
                "            - v_pr_review_external_reviewer\n"
                "            - v_pr_review_code_review_skill\n"
            )

    # v0.13: reference every implemented validator on a STATUS
    # (specifically the entry-only ``planned`` status) so
    # ``declared_validator_ids`` (which feeds full-project validation
    # when callers pass no ``validator_ids=``) returns the full set —
    # WITHOUT subjecting every route to the entire catalog at gate
    # time. The executor only fires the route's ``controls.tripwires``
    # when a route is declared (status-level tripwires are the
    # fallback for routeless transitions, which we don't have here).
    _status_tripwires = "\n".join(f"          - {vid}" for vid in _all_validators)
    (project_dir / "workflow.yaml").write_text(
        "workflow_schema_version: 1\n"
        "workflows:\n"
        "  coding-session:\n"
        "    actor: coding-agent\n"
        "    trigger: session.spawn\n"
        "    instance:\n"
        "      storage_path: sessions/{instance_id}/session.yaml\n"
        "      status_field: status\n"
        "      status_enum: [planned, queued, executing, in_review,\n"
        "        verified, completed, paused, failed, abandoned]\n"
        "    statuses:\n"
        "      - id: planned\n"
        "        tripwires:\n" + _status_tripwires + "\n"
        "      - id: queued\n"
        "      - id: executing\n"
        "      - id: in_review\n"
        "      - id: verified\n"
        "      - id: completed\n"
        "        terminal: true\n"
        "      - id: paused\n"
        "      - id: failed\n"
        "      - id: abandoned\n"
        "        terminal: true\n"
        "    routes:\n" + "".join(_route_lines)
    )
    templates = project_dir / "templates" / "artifacts"
    templates.mkdir(parents=True)
    # Minimal manifest — real one is tested separately. Matches v0.6a shape.
    templates.joinpath("manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "artifacts": [
                    {
                        "name": "plan",
                        "file": "plan.md",
                        "template": "plan.md.j2",
                        "produced_at": "planning",
                        "produced_by": "pm",
                        "owned_by": "pm",
                        "required": True,
                    },
                ]
            }
        )
    )
    return project_dir


@pytest.fixture
def save_test_issue():
    """Factory fixture: save a minimal valid Issue via `store.save_issue`."""

    def _factory(project_dir: Path, key: str, **kwargs: Any) -> None:
        from tripwire.core.store import save_issue
        from tripwire.models import Issue

        default_body = (
            "## Context\nWith [[user-model]] reference.\n"
            "\n## Implements\nREQ-1\n"
            "\n## Repo scope\n- SeidoAI/web-app-backend\n"
            "\n## Requirements\n- thing\n"
            "\n## Execution constraints\nIf ambiguous, stop and ask.\n"
            "\n## Acceptance criteria\n- [ ] thing\n"
            "\n## Test plan\n```\nuv run pytest\n```\n"
            "\n## Dependencies\nnone\n"
            "\n## Definition of Done\n- [ ] done\n"
        )
        fm: dict[str, Any] = {
            "id": key,
            "title": f"Test {key}",
            "status": "queued",
            "priority": "medium",
            "executor": "ai",
            "verifier": "required",
            "kind": "feat",
            "body": default_body,
        }
        fm.update(kwargs)
        save_issue(project_dir, Issue.model_validate(fm), update_cache=False)

    return _factory


@pytest.fixture
def save_test_session():
    """Factory fixture: save a minimal valid AgentSession via `session_store.save_session`."""

    def _factory(
        project_dir: Path, session_id: str, *, plan: bool = False, **kwargs: Any
    ) -> None:
        from tripwire.core import paths
        from tripwire.core.session_store import save_session
        from tripwire.models import AgentSession

        fm: dict[str, Any] = {
            "id": session_id,
            "name": "Test session",
            "agent": "backend-coder",
            "issues": [],
            "status": "planned",
            "repos": [],
        }
        fm.update(kwargs)
        save_session(project_dir, AgentSession.model_validate(fm))
        if plan:
            # Substantive plan content so the v0.7.9 strict pre-spawn
            # check (`check/plan_unfilled`) doesn't fire for tests that
            # only care about lifecycle / runtime mechanics. Tests that
            # specifically exercise the strict check should overwrite
            # plan.md with a placeholder body of their own.
            plan_path = paths.session_plan_path(project_dir, session_id)
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(
                "# Plan — test session\n\n"
                "## Goal\n"
                "Drive the lifecycle path under test end to end. This "
                "stub is long enough to clear the strict-check body "
                "floor (200 chars) so tests that don't care about plan "
                "content can ignore the v0.7.9 pre-spawn gates.\n\n"
                "## Approach\n"
                "Phase 1: read fixtures. Phase 2: invoke the CLI under "
                "test. Phase 3: assert observable side effects.\n",
                encoding="utf-8",
            )

    return _factory


@pytest.fixture
def save_test_node():
    """Factory fixture: save a minimal valid ConceptNode via `node_store.save_node`."""

    def _factory(
        project_dir: Path,
        node_id: str,
        *,
        body: str = "Description.\n",
        **kwargs: Any,
    ) -> None:
        from tripwire.core.node_store import save_node
        from tripwire.models import ConceptNode

        fm: dict[str, Any] = {
            "id": node_id,
            "type": "model",
            "name": "User",
            "status": "active",
            "body": body,
        }
        fm.update(kwargs)
        save_node(project_dir, ConceptNode.model_validate(fm), update_cache=False)

    return _factory


@pytest.fixture
def write_handoff_yaml():
    """Factory fixture: write a minimal handoff.yaml for a session."""

    def _factory(
        project_dir: Path, session_id: str, *, branch: str = "feat/test"
    ) -> None:
        from datetime import datetime, timezone
        from uuid import uuid4

        from tripwire.core.handoff_store import save_handoff
        from tripwire.models.handoff import SessionHandoff

        h = SessionHandoff(
            uuid=uuid4(),
            session_id=session_id,
            handoff_at=datetime.now(tz=timezone.utc),
            handed_off_by="pm",
            branch=branch,
        )
        save_handoff(project_dir, h)

    return _factory


@pytest.fixture
def fresh_project():
    """Factory: create a minimal tripwire project directory.

    Writes plain YAML (no frontmatter) matching ProjectConfig shape.
    Used by workspace CLI tests that need a real project on disk.
    """

    def _factory(
        proj_dir: Path, *, name: str = "test", key_prefix: str = "TST"
    ) -> Path:
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "project.yaml").write_text(
            f"name: {name}\n"
            f"key_prefix: {key_prefix}\n"
            "next_issue_number: 1\n"
            "next_session_number: 1\n",
            encoding="utf-8",
        )
        for sub in ("issues", "nodes", "sessions", "docs"):
            (proj_dir / sub).mkdir(parents=True, exist_ok=True)
        return proj_dir

    return _factory


@pytest.fixture
def fresh_workspace():
    """Factory: workspace directory with workspace.yaml + nodes/."""

    def _factory(ws_dir: Path, *, slug: str = "ws") -> Path:
        from datetime import datetime, timezone
        from uuid import uuid4

        from tripwire.core.paths import workspace_nodes_dir
        from tripwire.core.workspace_store import save_workspace
        from tripwire.models.workspace import Workspace

        ws_dir.mkdir(parents=True, exist_ok=True)
        workspace_nodes_dir(ws_dir).mkdir(parents=True, exist_ok=True)
        now = datetime.now(tz=timezone.utc)
        save_workspace(
            ws_dir,
            Workspace(
                uuid=uuid4(),
                name=slug,
                slug=slug,
                description="",
                schema_version=1,
                tripwire_version="0.6.0",
                created_at=now,
                updated_at=now,
            ),
        )
        return ws_dir

    return _factory


@pytest.fixture
def tmp_project_manifest(tmp_path: Path):
    """Factory creating a minimal project with a custom manifest for
    validator testing."""

    def _factory(artifacts: list[dict]) -> Path:
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / "project.yaml").write_text(
            "name: tmp\nkey_prefix: TMP\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        (project_dir / "issues").mkdir()
        (project_dir / "nodes").mkdir()
        (project_dir / "sessions").mkdir()
        templates = project_dir / "templates" / "artifacts"
        templates.mkdir(parents=True)
        (templates / "manifest.yaml").write_text(
            yaml.safe_dump({"artifacts": artifacts})
        )
        return project_dir

    return _factory
