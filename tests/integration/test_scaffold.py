"""Integration tests for `tripwire scaffold-for-creation`.

Verifies both output formats against:
- A freshly-init'd v0 project (minimal state, no optional templates)
- A project with a hand-written artifact manifest, orchestration pattern,
  and skill examples
- Missing project.yaml (clean error)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from tripwire.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _init_project(runner: CliRunner, target: Path, **overrides: str) -> None:
    args = [
        "init",
        str(target),
        "--name",
        overrides.get("name", "test"),
        "--key-prefix",
        overrides.get("key_prefix", "TST"),
        "--base-branch",
        overrides.get("base_branch", "main"),
        "--non-interactive",
        "--no-git",
    ]
    if overrides.get("repos"):
        args += ["--repos", overrides["repos"]]
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, result.output


# ============================================================================
# Text format
# ============================================================================


class TestScaffoldText:
    def test_section_headers_present(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        assert result.exit_code == 0, result.output

        for section in (
            "PROJECT:",
            "Base branch:",
            "NEXT IDS:",
            "ACTIVE ENUMS",
            "ACTIVE ARTIFACT MANIFEST",
            "ACTIVE ORCHESTRATION PATTERN",
            "TEMPLATES",
            "SKILL EXAMPLES",
            "VALIDATION GATE",
            "ID ALLOCATION",
        ):
            assert section in result.output, f"Missing section: {section!r}"

    def test_shows_project_name_and_prefix(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target, name="my-project", key_prefix="MP")

        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        assert "PROJECT: my-project (MP)" in result.output
        assert "next issue key: MP-1" in result.output

    def test_shows_repos_with_local_indicator(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target, repos="SeidoAI/backend,SeidoAI/frontend")

        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        assert "SeidoAI/backend" in result.output
        assert "SeidoAI/frontend" in result.output
        assert "(no local clone)" in result.output

    def test_shows_all_packaged_enums(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        for enum_name in (
            "issue_status",
            "priority",
            "executor",
            "verifier",
            "node_type",
            "node_status",
            "session_status",
            "message_type",
            "agent_state",
            "comment_type",
            "re_engagement_trigger",
        ):
            assert enum_name in result.output, f"Missing enum: {enum_name}"

    def test_issue_status_values_visible(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)
        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        # A few representative values
        assert "backlog" in result.output
        assert "in_progress" in result.output
        assert "done" in result.output

    def test_init_project_has_shipped_templates(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """A freshly-init'd project ships the full Step 9 template set:
        artifact manifest, orchestration pattern, issue templates, etc.
        The scaffold output should show all of them populated."""
        target = tmp_path / "p"
        _init_project(runner, target)

        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        # All Step 9 and Step 10 content present → no "missing" placeholders.
        assert "(no manifest.yaml present" not in result.output
        assert "(pattern file missing" not in result.output
        assert "(no templates shipped yet" not in result.output
        assert "(no skill examples shipped yet" not in result.output
        # Manifest entries visible
        assert "plan.md (planning, required)" in result.output
        assert "task-checklist.md (in_progress, required)" in result.output
        # Template file paths visible
        assert "issue_templates/default.yaml.j2" in result.output
        # Step 10 skill examples visible
        assert "examples/issue-fully-formed.yaml" in result.output
        assert "examples/node-endpoint.yaml" in result.output

    def test_degraded_project_shows_missing_sections(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """If a project has its templates removed, the scaffold output falls
        back to the descriptive 'missing' placeholders."""
        import shutil as _shutil

        target = tmp_path / "p"
        _init_project(runner, target)
        # Remove the shipped templates that scaffold looks for.
        for sub in (
            "templates",
            "orchestration",
            "issue_templates",
            "comment_templates",
            "session_templates",
        ):
            p = target / sub
            if p.exists():
                _shutil.rmtree(p)

        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        assert "(no manifest.yaml present" in result.output
        assert "(pattern file missing" in result.output
        assert "(no templates shipped yet" in result.output

    def test_validation_gate_instructions_present(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)
        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        assert "tripwire validate --strict" in result.output

    def test_id_allocation_instructions_present(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)
        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        assert "tripwire next-key --type issue" in result.output
        assert "uuid4" in result.output
        assert "Do NOT hand-write UUIDs" in result.output


# ============================================================================
# JSON format
# ============================================================================


class TestScaffoldJson:
    def test_json_is_parseable(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        result = runner.invoke(
            cli,
            [
                "scaffold-for-creation",
                "--project-dir",
                str(target),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["project_name"] == "test"
        assert data["key_prefix"] == "TST"
        assert data["base_branch"] == "main"

    def test_json_has_all_top_level_keys(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        result = runner.invoke(
            cli,
            [
                "scaffold-for-creation",
                "--project-dir",
                str(target),
                "--format",
                "json",
            ],
        )
        data = json.loads(result.output)
        expected_keys = {
            "project_name",
            "key_prefix",
            "description",
            "base_branch",
            "repos",
            "next_issue_key",
            "next_session_key",
            "next_node_id",
            "enums",
            "artifact_manifest",
            "orchestration",
            "templates",
            "skill_examples",
            "validation_gate",
            "id_allocation",
        }
        assert set(data.keys()) >= expected_keys

    def test_json_enums_have_lists(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        result = runner.invoke(
            cli,
            [
                "scaffold-for-creation",
                "--project-dir",
                str(target),
                "--format",
                "json",
            ],
        )
        data = json.loads(result.output)
        assert "issue_status" in data["enums"]
        assert isinstance(data["enums"]["issue_status"], list)
        assert "todo" in data["enums"]["issue_status"]

    def test_json_next_issue_key_uses_prefix(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target, key_prefix="PKB")

        result = runner.invoke(
            cli,
            [
                "scaffold-for-creation",
                "--project-dir",
                str(target),
                "--format",
                "json",
            ],
        )
        data = json.loads(result.output)
        assert data["next_issue_key"] == "PKB-1"

    def test_json_artifact_manifest_populated_after_init(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Step 9 ships the default manifest — it's present after init."""
        target = tmp_path / "p"
        _init_project(runner, target)
        result = runner.invoke(
            cli,
            [
                "scaffold-for-creation",
                "--project-dir",
                str(target),
                "--format",
                "json",
            ],
        )
        data = json.loads(result.output)
        assert data["artifact_manifest"]["exists"] is True
        # Default manifest has 5 artifacts
        files = {a["file"] for a in data["artifact_manifest"]["artifacts"]}
        assert "plan.md" in files
        assert "post-completion-comments.md" in files
        assert len(data["artifact_manifest"]["artifacts"]) == 5


# ============================================================================
# With a richer project (hand-written manifest, orchestration, skill examples)
# ============================================================================


class TestScaffoldRicherProject:
    def test_artifact_manifest_detected(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        # Overwrite the default manifest with a custom two-entry one that
        # has an approval_gate, to test gate rendering.
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
                            "approval_gate": True,
                        },
                        {
                            "name": "task-checklist",
                            "file": "task-checklist.md",
                            "produced_at": "planning",
                            "required": True,
                        },
                    ]
                }
            )
        )

        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        assert "plan.md (planning, required) [approval_gate]" in result.output
        assert "task-checklist.md (planning, required)" in result.output

    def test_orchestration_pattern_file_detected(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        orch_dir = target / "orchestration"
        orch_dir.mkdir(exist_ok=True)
        (orch_dir / "default.yaml").write_text("name: default\nevents: {}\n")

        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        assert "(pattern file missing" not in result.output

    def test_templates_listed(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)
        # Step 9 already ships `issue_templates/default.yaml.j2`.

        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        assert "issue_templates/default.yaml.j2" in result.output

    def test_skill_examples_listed(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)
        # Step 10 already ships the full set of skill examples.

        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        assert "issue-fully-formed.yaml" in result.output
        assert "node-endpoint.yaml" in result.output


# ============================================================================
# Error handling
# ============================================================================


class TestScaffoldErrors:
    def test_missing_project_yaml_clean_error(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(tmp_path)]
        )
        assert result.exit_code != 0
        assert "project.yaml not found" in result.output

    def test_invalid_format_rejected(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(
            cli,
            [
                "scaffold-for-creation",
                "--project-dir",
                str(tmp_path),
                "--format",
                "xml",
            ],
        )
        assert result.exit_code != 0


# ============================================================================
# After a next-key allocation, the scaffold reflects the new next_issue_number
# ============================================================================


class TestScaffoldReflectsState:
    def test_next_issue_key_advances_with_counter(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        # Manually bump next_issue_number (next-key CLI comes in Step 7)
        raw = yaml.safe_load((target / "project.yaml").read_text())
        raw["next_issue_number"] = 42
        (target / "project.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))

        result = runner.invoke(
            cli, ["scaffold-for-creation", "--project-dir", str(target)]
        )
        assert "next issue key: TST-42" in result.output
