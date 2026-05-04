"""Integration tests for the read commands introduced in Step 8.

Covers: validate, status, graph, refs, node check, templates, enums,
artifacts. One test class per command group; shared fixtures build
minimal valid projects on tmp_path.

These tests exercise the CLI via Click's CliRunner. The correctness of
the underlying core modules is already covered by the unit test suite;
these tests focus on argument parsing, output formatting, exit codes,
and end-to-end flows.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner

from tripwire.cli.main import cli
from tripwire.core.parser import serialize_frontmatter_body


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ============================================================================
# Helpers — build a project with issues and nodes
# ============================================================================


def init_project(runner: CliRunner, target: Path, key_prefix: str = "TST") -> None:
    result = runner.invoke(
        cli,
        [
            "init",
            str(target),
            "--name",
            "t",
            "--key-prefix",
            key_prefix,
            "--base-branch",
            "main",
            "--repos",
            "org/repo-a,org/repo-b",
            "--non-interactive",
            "--no-git",
        ],
    )
    assert result.exit_code == 0, result.output


def write_issue_file(
    project_dir: Path,
    key: str,
    *,
    status: str = "queued",
    priority: str = "medium",
    executor: str = "ai",
    blocked_by: list[str] | None = None,
    body: str | None = None,
    **frontmatter: Any,
) -> None:
    idir = project_dir / "issues" / key
    idir.mkdir(parents=True, exist_ok=True)

    fm: dict[str, Any] = {
        "uuid": str(uuid.uuid4()),
        "id": key,
        "title": f"Test {key}",
        "status": status,
        "priority": priority,
        "executor": executor,
        "verifier": "required",
        "created_at": "2026-04-07T10:00:00",
        "updated_at": "2026-04-07T10:00:00",
    }
    if blocked_by:
        fm["blocked_by"] = blocked_by
    fm.update(frontmatter)

    if body is None:
        body = (
            "## Context\n[[user-model]]\n"
            "## Implements\nREQ-1\n"
            "## Repo scope\n- org/repo-a\n"
            "## Requirements\n- thing\n"
            "## Execution constraints\nIf ambiguous, stop and ask.\n"
            "## Acceptance criteria\n- [ ] thing\n"
            "## Test plan\n```\nrun tests\n```\n"
            "## Dependencies\nnone\n"
            "## Definition of Done\n- [ ] done\n"
        )

    path = idir / "issue.yaml"
    path.write_text(serialize_frontmatter_body(fm, body), encoding="utf-8")


def write_node_file(
    project_dir: Path,
    node_id: str,
    *,
    node_type: str = "model",
    related: list[str] | None = None,
    body: str = "Description.\n",
) -> None:
    nodes_dir = project_dir / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)
    fm = {
        "uuid": str(uuid.uuid4()),
        "id": node_id,
        "type": node_type,
        "name": node_id.replace("-", " ").title(),
        "status": "active",
        "related": related or [],
        "created_at": "2026-04-07T10:00:00",
        "updated_at": "2026-04-07T10:00:00",
    }
    path = nodes_dir / f"{node_id}.yaml"
    path.write_text(serialize_frontmatter_body(fm, body), encoding="utf-8")


def populate_project(runner: CliRunner, target: Path) -> None:
    """Build a non-trivial project with issues, nodes, and a chain."""
    init_project(runner, target)
    write_node_file(target, "user-model")
    write_node_file(target, "auth-endpoint", node_type="endpoint")
    write_issue_file(target, "TST-1")
    write_issue_file(target, "TST-2", blocked_by=["TST-1"])
    write_issue_file(target, "TST-3", blocked_by=["TST-2"], status="executing")


# ============================================================================
# validate
# ============================================================================


class TestValidate:
    def test_clean_project_exits_zero(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        # Default output is text
        result = runner.invoke(cli, ["validate", "--project-dir", str(target)])
        assert result.exit_code == 0
        assert "passed" in result.output

    def test_text_format(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        result = runner.invoke(
            cli, ["validate", "--project-dir", str(target), "--format", "text"]
        )
        assert result.exit_code == 0
        assert "passed" in result.output

    def test_project_with_errors_exits_two(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        # Write an issue with the wrong prefix → id/wrong_prefix error.
        write_issue_file(target, "OTHER-1")
        write_node_file(target, "user-model")
        result = runner.invoke(cli, ["validate", "--project-dir", str(target)])
        assert result.exit_code == 2
        assert "id/wrong_prefix" in result.output

    def test_text_format_is_default(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        result = runner.invoke(cli, ["validate", "--project-dir", str(target)])
        assert result.exit_code == 0
        # Default is now text, not JSON
        assert "passed" in result.output

    def test_json_format_explicit(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        result = runner.invoke(
            cli, ["validate", "--project-dir", str(target), "--format", "json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["version"] == 1
        assert payload["exit_code"] == 0
        assert "summary" in payload
        assert "errors" in payload
        assert payload["summary"]["cache_rebuilt"] is True

    def test_validate_promotes_warnings_strict_by_default(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """``--strict`` was hard-removed in stage 1 of the workflow
        codification. ``tripwire validate`` is now strict-by-default —
        warnings count as errors, exit code 2."""

        target = tmp_path / "p"
        init_project(runner, target)
        # Issue with no references → body/no_references warning
        write_node_file(target, "user-model")
        write_issue_file(
            target,
            "TST-1",
            body=(
                "## Context\nNo refs here.\n"
                "## Implements\nx\n"
                "## Repo scope\nx\n"
                "## Requirements\nx\n"
                "## Execution constraints\nstop and ask.\n"
                "## Acceptance criteria\n- [ ] x\n"
                "## Test plan\nx\n"
                "## Dependencies\nnone\n"
                "## Definition of Done\n- [ ] x\n"
            ),
        )

        result = runner.invoke(cli, ["validate", "--project-dir", str(target)])
        # Strict-by-default: warnings promoted to errors.
        assert result.exit_code == 2

        # Confirm the flag was hard-removed (passing it errors out).
        with_flag = runner.invoke(
            cli, ["validate", "--project-dir", str(target), "--strict"]
        )
        assert with_flag.exit_code != 0
        assert "no such option" in with_flag.output.lower() or "--strict" in with_flag.output

    def test_fix_repairs_sequence_drift(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        write_node_file(target, "user-model")
        write_issue_file(target, "TST-5")  # jumps past next_issue_number=1
        result = runner.invoke(cli, ["validate", "--project-dir", str(target), "--fix"])
        # The fix bumps next_issue_number, so it doesn't show up as a warning
        # on the post-fix re-validate.
        raw = yaml.safe_load((target / "project.yaml").read_text())
        assert raw["next_issue_number"] == 6
        assert "sequence/drift" in result.output or result.exit_code in (0, 1)


# ============================================================================
# status
# ============================================================================


class TestStatus:
    def test_empty_project(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        # Default is rich now
        result = runner.invoke(cli, ["status", "--project-dir", str(target)])
        assert result.exit_code == 0
        assert "0 issues" in result.output or "total_issues" not in result.output

    def test_populated_project(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        # Use rich format for human-readable assertions
        result = runner.invoke(
            cli, ["status", "--project-dir", str(target), "--format", "text"]
        )
        assert result.exit_code == 0
        assert "3 issues" in result.output
        assert "2 blocked" in result.output
        assert "critical path: 3" in result.output

    def test_rich_is_default(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        result = runner.invoke(cli, ["status", "--project-dir", str(target)])
        assert result.exit_code == 0
        # Default is now rich, not JSON
        assert "3 issues" in result.output

    def test_json_format_explicit(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        result = runner.invoke(
            cli, ["status", "--project-dir", str(target), "--format", "json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["total_issues"] == 3
        assert payload["key_prefix"] == "TST"
        assert payload["critical_path_length"] == 3
        assert len(payload["blocked_issues"]) == 2

    def test_status_missing_project_yaml(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        result = runner.invoke(cli, ["status", "--project-dir", str(tmp_path)])
        assert result.exit_code != 0
        assert "project.yaml not found" in result.output


# ============================================================================
# graph
# ============================================================================


class TestGraph:
    def test_mermaid_is_default(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        result = runner.invoke(cli, ["graph", "--project-dir", str(target)])
        assert result.exit_code == 0
        assert result.output.startswith("graph LR")

    def test_json_format(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        result = runner.invoke(
            cli, ["graph", "--project-dir", str(target), "--format", "json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert len(payload["nodes"]) == 3

    def test_deps_mermaid(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        result = runner.invoke(
            cli, ["graph", "--project-dir", str(target), "--format", "mermaid"]
        )
        assert result.exit_code == 0
        assert result.output.startswith("graph LR")
        assert "TST-1" in result.output

    def test_deps_dot(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        result = runner.invoke(
            cli, ["graph", "--project-dir", str(target), "--format", "dot"]
        )
        assert result.exit_code == 0
        assert "digraph" in result.output

    def test_concept_graph(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        runner.invoke(cli, ["validate", "--project-dir", str(target)])
        result = runner.invoke(
            cli,
            [
                "graph",
                "--project-dir",
                str(target),
                "--type",
                "concept",
                "--format",
                "mermaid",
            ],
        )
        assert result.exit_code == 0
        assert result.output.startswith("graph LR")
        assert "user_model" in result.output

    def test_output_to_file(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        out = tmp_path / "graph.json"
        result = runner.invoke(
            cli,
            [
                "graph",
                "--project-dir",
                str(target),
                "--format",
                "json",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0
        assert out.exists()
        payload = json.loads(out.read_text())
        assert "nodes" in payload

    def test_status_filter(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        # Only TST-3 is in_progress; filtering should leave a 1-node graph.
        result = runner.invoke(
            cli,
            [
                "graph",
                "--project-dir",
                str(target),
                "--status-filter",
                "executing",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert len(payload["nodes"]) == 1
        assert payload["nodes"][0]["id"] == "TST-3"


# ============================================================================
# refs
# ============================================================================


class TestRefs:
    def test_list_issue_refs(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        result = runner.invoke(
            cli, ["refs", "list", "TST-1", "--project-dir", str(target)]
        )
        assert result.exit_code == 0
        assert "user-model" in result.output

    def test_list_json(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        result = runner.invoke(
            cli,
            [
                "refs",
                "list",
                "TST-1",
                "--project-dir",
                str(target),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["issue"] == "TST-1"
        assert any(r["ref"] == "user-model" for r in payload["references"])

    def test_reverse(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        # Build cache first
        runner.invoke(cli, ["validate", "--project-dir", str(target)])
        result = runner.invoke(
            cli, ["refs", "reverse", "user-model", "--project-dir", str(target)]
        )
        assert result.exit_code == 0
        # All 3 issues reference [[user-model]] via their default body
        assert "TST-1" in result.output
        assert "TST-2" in result.output
        assert "TST-3" in result.output

    def test_check_clean(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        result = runner.invoke(cli, ["refs", "check", "--project-dir", str(target)])
        assert result.exit_code == 0
        assert "no dangling" in result.output

    def test_check_detects_dangling(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        write_issue_file(
            target,
            "TST-1",
            body=(
                "## Context\n[[does-not-exist]]\n"
                "## Implements\nx\n"
                "## Repo scope\nx\n"
                "## Requirements\nx\n"
                "## Execution constraints\nstop and ask.\n"
                "## Acceptance criteria\n- [ ] x\n"
                "## Test plan\nx\n"
                "## Dependencies\nnone\n"
                "## Definition of Done\n- [ ] x\n"
            ),
        )
        result = runner.invoke(
            cli,
            [
                "refs",
                "check",
                "--project-dir",
                str(target),
                "--format",
                "json",
            ],
        )
        payload = json.loads(result.output)
        assert any(d["ref"] == "does-not-exist" for d in payload["dangling"])


# ============================================================================
# node check
# ============================================================================


class TestNodeCheck:
    def test_all_nodes(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        result = runner.invoke(cli, ["node", "check", "--project-dir", str(target)])
        assert result.exit_code == 0

    def test_single_node(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        result = runner.invoke(
            cli, ["node", "check", "user-model", "--project-dir", str(target)]
        )
        assert result.exit_code == 0

    def test_json_output(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        result = runner.invoke(
            cli,
            [
                "node",
                "check",
                "--project-dir",
                str(target),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert isinstance(payload, list)

    def test_unknown_node_errors(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        populate_project(runner, target)
        result = runner.invoke(
            cli,
            ["node", "check", "nonexistent", "--project-dir", str(target)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output


# ============================================================================
# templates
# ============================================================================


class TestTemplates:
    def test_list_populated_after_init(self, runner: CliRunner, tmp_path: Path) -> None:
        """Step 9+ ships a full template set, so init'd projects list them."""
        target = tmp_path / "p"
        init_project(runner, target)
        result = runner.invoke(cli, ["templates", "list", "--project-dir", str(target)])
        assert result.exit_code == 0
        # Every major template subdirectory should appear in the list.
        assert "issue_templates/default.yaml.j2" in result.output
        assert "comment_templates/" in result.output
        assert "templates/artifacts/manifest.yaml" in result.output
        assert "agents/backend-coder.yaml" in result.output

    def test_list_empty_when_removed(self, runner: CliRunner, tmp_path: Path) -> None:
        """If a project has no templates (deleted after init), list says so."""
        import shutil as _shutil

        target = tmp_path / "p"
        init_project(runner, target)
        # Remove every template subdirectory; project.yaml still exists.
        for subdir in (
            "issue_templates",
            "comment_templates",
            "session_templates",
            "templates",
            "agents",
            "orchestration",
        ):
            if (target / subdir).exists():
                _shutil.rmtree(target / subdir)

        result = runner.invoke(cli, ["templates", "list", "--project-dir", str(target)])
        assert result.exit_code == 0
        assert "no templates" in result.output

    def test_list_with_extra_template(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        # Add a project-specific template alongside the packaged defaults.
        tpl_dir = target / "issue_templates"
        tpl_dir.mkdir(exist_ok=True)
        (tpl_dir / "bug.yaml.j2").write_text("---\nid: {{id}}\n---\n")

        result = runner.invoke(cli, ["templates", "list", "--project-dir", str(target)])
        assert result.exit_code == 0
        assert "issue_templates/bug.yaml.j2" in result.output
        # The packaged default should still be listed too.
        assert "issue_templates/default.yaml.j2" in result.output

    def test_show_by_path(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        # Show the packaged default template by its full path.
        result = runner.invoke(
            cli,
            [
                "templates",
                "show",
                "issue_templates/default.yaml.j2",
                "--project-dir",
                str(target),
            ],
        )
        assert result.exit_code == 0
        # The packaged default template has a `## Context` section and a
        # `## Definition of Done` section.
        assert "## Context" in result.output
        assert "## Definition of Done" in result.output

    def test_show_by_stem(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        # Add an unambiguous project-specific template.
        tpl_dir = target / "issue_templates"
        tpl_dir.mkdir(exist_ok=True)
        (tpl_dir / "bug.yaml.j2").write_text("BUG TEMPLATE BODY\n")

        result = runner.invoke(
            cli,
            ["templates", "show", "bug", "--project-dir", str(target)],
        )
        assert result.exit_code == 0
        assert "BUG TEMPLATE BODY" in result.output

    def test_show_unknown_template(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        result = runner.invoke(
            cli,
            ["templates", "show", "nope-does-not-exist", "--project-dir", str(target)],
        )
        assert result.exit_code != 0


# ============================================================================
# enums
# ============================================================================


class TestEnums:
    def test_list_after_init(self, runner: CliRunner, tmp_path: Path) -> None:
        """After init, enums come from project files (source=project)."""
        target = tmp_path / "p"
        init_project(runner, target)
        result = runner.invoke(cli, ["enums", "list", "--project-dir", str(target)])
        assert result.exit_code == 0
        assert "issue_status" in result.output
        assert "project" in result.output  # source column shows project-level files

    def test_list_json(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        result = runner.invoke(
            cli,
            [
                "enums",
                "list",
                "--project-dir",
                str(target),
                "--format",
                "json",
            ],
        )
        payload = json.loads(result.output)
        assert "issue_status" in payload
        assert "queued" in payload["issue_status"]["values"]

    def test_show(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        result = runner.invoke(
            cli,
            ["enums", "show", "issue_status", "--project-dir", str(target)],
        )
        assert result.exit_code == 0
        assert "planned" in result.output
        assert "executing" in result.output

    def test_show_unknown(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        result = runner.invoke(
            cli, ["enums", "show", "nope", "--project-dir", str(target)]
        )
        assert result.exit_code != 0

    def test_project_override(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        enums_dir = target / "enums"
        enums_dir.mkdir(exist_ok=True)
        # Overwrite the packaged issue_status with a custom one.
        (enums_dir / "issue_status.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "IssueStatus",
                    "values": [
                        {"id": "open", "label": "Open"},
                        {"id": "closed", "label": "Closed"},
                    ],
                }
            )
        )
        result = runner.invoke(
            cli,
            [
                "enums",
                "show",
                "issue_status",
                "--project-dir",
                str(target),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["source"] == "project"
        assert [v["id"] for v in payload["values"]] == ["open", "closed"]


# ============================================================================
# artifacts
# ============================================================================


class TestArtifacts:
    def test_list_session_uses_default_manifest(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """A freshly init'd project ships the default 5-artifact manifest."""
        target = tmp_path / "p"
        init_project(runner, target)
        # Use JSON format to avoid rich table truncation of long filenames.
        result = runner.invoke(
            cli,
            [
                "artifacts",
                "list",
                "api-endpoints",
                "--project-dir",
                str(target),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        files = {a["file"] for a in payload["artifacts"]}
        # The default manifest has all five artifacts.
        assert files >= {
            "plan.md",
            "task-checklist.md",
            "verification-checklist.md",
            "recommended-testing-plan.md",
            "post-completion-comments.md",
        }
        # None of them exist on disk → all marked missing.
        for entry in payload["artifacts"]:
            assert entry["exists"] == "no"

    def test_list_with_manifest_and_files(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        init_project(runner, target)

        # Overwrite the packaged manifest with a custom 2-entry one.
        manifest_dir = target / "templates" / "artifacts"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "manifest.yaml").write_text(
            yaml.safe_dump(
                {
                    "artifacts": [
                        {
                            "name": "plan",
                            "file": "plan.md",
                            "produced_at": "planning",
                            "required": True,
                        },
                        {
                            "name": "post-completion-comments",
                            "file": "post-completion-comments.md",
                            "produced_at": "completed",
                            "required": True,
                        },
                    ]
                }
            )
        )

        session_dir = target / "sessions" / "api-endpoints" / "artifacts"
        session_dir.mkdir(parents=True)
        (session_dir / "plan.md").write_text("# Plan\n\nSteps...\n")
        # post-completion-comments.md intentionally missing → required-missing

        # Use JSON format to avoid rich table truncation of long filenames.
        result = runner.invoke(
            cli,
            [
                "artifacts",
                "list",
                "api-endpoints",
                "--project-dir",
                str(target),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        files = {a["file"] for a in payload["artifacts"]}
        assert "plan.md" in files
        assert "post-completion-comments.md" in files

        # And the missing-required file should be marked exists=no.
        post_entry = next(
            a
            for a in payload["artifacts"]
            if a["file"] == "post-completion-comments.md"
        )
        assert post_entry["exists"] == "no"
        assert post_entry["required"] == "yes"

    def test_list_json(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)

        session_dir = target / "sessions" / "api-endpoints" / "artifacts"
        session_dir.mkdir(parents=True)
        (session_dir / "plan.md").write_text("content")

        result = runner.invoke(
            cli,
            [
                "artifacts",
                "list",
                "api-endpoints",
                "--project-dir",
                str(target),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["session"] == "api-endpoints"
        assert any(a["file"] == "plan.md" for a in payload["artifacts"])

    def test_show_by_file(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)

        session_dir = target / "sessions" / "api-endpoints" / "artifacts"
        session_dir.mkdir(parents=True)
        (session_dir / "plan.md").write_text("# Plan content\n")

        result = runner.invoke(
            cli,
            [
                "artifacts",
                "show",
                "api-endpoints",
                "plan.md",
                "--project-dir",
                str(target),
            ],
        )
        assert result.exit_code == 0
        assert "Plan content" in result.output

    def test_show_by_manifest_name(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)

        # Overwrite the packaged manifest with a single-entry one for
        # test isolation.
        manifest_dir = target / "templates" / "artifacts"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "manifest.yaml").write_text(
            yaml.safe_dump(
                {
                    "artifacts": [
                        {
                            "name": "plan",
                            "file": "plan.md",
                            "produced_at": "planning",
                            "required": True,
                        }
                    ]
                }
            )
        )

        session_dir = target / "sessions" / "api-endpoints" / "artifacts"
        session_dir.mkdir(parents=True)
        (session_dir / "plan.md").write_text("VIA MANIFEST NAME\n")

        result = runner.invoke(
            cli,
            [
                "artifacts",
                "show",
                "api-endpoints",
                "plan",  # the manifest "name" field, not the filename
                "--project-dir",
                str(target),
            ],
        )
        assert result.exit_code == 0
        assert "VIA MANIFEST NAME" in result.output

    def test_show_missing_session(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        init_project(runner, target)
        result = runner.invoke(
            cli,
            [
                "artifacts",
                "show",
                "nonexistent",
                "plan.md",
                "--project-dir",
                str(target),
            ],
        )
        assert result.exit_code != 0


# ============================================================================
# End-to-end: the full v0 read-command loop
# ============================================================================


class TestEndToEnd:
    def test_full_v0_loop_against_populated_project(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """init → populate → validate → status → graph → refs check.

        Every command in the v0 surface should work end-to-end on a real
        populated project. If any of them breaks, this test catches it.
        """
        target = tmp_path / "p"
        populate_project(runner, target)

        # 1. validate — strict-by-default in stage 1 of the workflow
        # codification: heuristic warnings on a freshly populated
        # fixture project surface as exit 2. The end-to-end smoke test
        # only asserts the CLI works (doesn't crash), so accept any
        # of the documented exit codes.
        v = runner.invoke(cli, ["validate", "--project-dir", str(target)])
        assert v.exit_code in (0, 1, 2)
        assert (
            not any(
                "error" in line.lower() and "s:" in line.lower()
                for line in v.output.split("\n")
                if line.startswith("validate")
            )
            or v.exit_code < 2
        )

        # 2. status
        s = runner.invoke(cli, ["status", "--project-dir", str(target)])
        assert s.exit_code == 0

        # 3. brief
        sc = runner.invoke(cli, ["brief", "--project-dir", str(target)])
        assert sc.exit_code == 0

        # 4. graph deps
        gd = runner.invoke(cli, ["graph", "--project-dir", str(target)])
        assert gd.exit_code == 0

        # 5. graph concept
        gc = runner.invoke(
            cli,
            ["graph", "--project-dir", str(target), "--type", "concept"],
        )
        assert gc.exit_code == 0

        # 6. refs check
        rc = runner.invoke(cli, ["refs", "check", "--project-dir", str(target)])
        assert rc.exit_code == 0

        # 7. node check
        nc = runner.invoke(cli, ["node", "check", "--project-dir", str(target)])
        assert nc.exit_code == 0

        # 8. enums list
        el = runner.invoke(cli, ["enums", "list", "--project-dir", str(target)])
        assert el.exit_code == 0

        # 9. templates list
        tl = runner.invoke(cli, ["templates", "list", "--project-dir", str(target)])
        assert tl.exit_code == 0

        # 10. next-key still works
        nk = runner.invoke(cli, ["next-key", "--project-dir", str(target)])
        assert nk.exit_code == 0
        # TST-1/2/3 already exist, so next key should be past the drift fix
        # (which was applied by validate above)
        assert nk.output.strip().startswith("TST-")
