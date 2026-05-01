"""Tests for `tripwire validate-plan <session-id>` (v0.7.3 item D).

Pre-spawn coherence gate. Catches obsolete plans before the agent
burns budget discovering them. Four checks: plan/missing,
plan/unresolved_ref, plan/create_target_exists,
plan/modify_target_missing.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.validate_plan import validate_plan_cmd


def _write_plan(project_dir: Path, session_id: str, body: str) -> None:
    artifacts_dir = project_dir / "sessions" / session_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "plan.md").write_text(body, encoding="utf-8")


class TestValidatePlanCli:
    def test_missing_plan_yields_error(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s-missing", status="planned")
        runner = CliRunner()
        result = runner.invoke(
            validate_plan_cmd,
            ["s-missing", "--project-dir", str(tmp_path_project)],
        )
        # plan.md was never written.
        assert result.exit_code == 2
        assert "plan/missing" in result.output

    def test_clean_plan_passes(
        self,
        tmp_path_project,
        save_test_session,
        save_test_node,
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_session(tmp_path_project, "s-clean", status="planned")
        _write_plan(
            tmp_path_project,
            "s-clean",
            "# Plan\n\nReferences `[[user-model]]`.\n",
        )

        runner = CliRunner()
        result = runner.invoke(
            validate_plan_cmd,
            ["s-clean", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        assert "no issues found" in result.output.lower()

    def test_unresolved_ref_yields_error(self, tmp_path_project, save_test_session):
        # No node saved — ref will dangle.
        save_test_session(tmp_path_project, "s-ref", status="planned")
        _write_plan(
            tmp_path_project,
            "s-ref",
            "# Plan\n\nUses `[[no-such-node]]` here.\n",
        )

        runner = CliRunner()
        result = runner.invoke(
            validate_plan_cmd,
            ["s-ref", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 2
        assert "plan/unresolved_ref" in result.output
        assert "no-such-node" in result.output

    def test_create_target_exists_yields_warning(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        # Set up a fake "code clone" that contains a file the plan
        # tries to create. project.yaml's repos[].local points at it.
        clone = tmp_path_project / "fake-clone"
        existing_file = clone / "src" / "thing.py"
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("# already shipped\n")

        # Register the repo with a local clone path.
        project_yaml = tmp_path_project / "project.yaml"
        original = project_yaml.read_text()
        project_yaml.write_text(
            original + f"\nrepos:\n  SeidoAI/fake:\n    local: {clone}\n"
        )

        save_test_issue(tmp_path_project, "T-1", kind="feat")
        save_test_session(
            tmp_path_project,
            "s-create",
            status="planned",
            issues=["T-1"],
            repos=[{"repo": "SeidoAI/fake", "base_branch": "main"}],
        )
        _write_plan(
            tmp_path_project,
            "s-create",
            "# Plan\n\n"
            "### Step 1: Create the thing\n"
            "- **Files:** `src/thing.py`\n"
            "- **Change:** Implement the new thing.\n",
        )

        runner = CliRunner()
        result = runner.invoke(
            validate_plan_cmd,
            ["s-create", "--project-dir", str(tmp_path_project)],
        )
        # Warnings → exit 1.
        assert result.exit_code == 1, result.output
        assert "plan/create_target_exists" in result.output
        assert "src/thing.py" in result.output

    def test_modify_target_missing_yields_warning(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        # Code clone exists but the path the plan tries to modify
        # does not exist within it.
        clone = tmp_path_project / "fake-clone"
        clone.mkdir(parents=True, exist_ok=True)

        project_yaml = tmp_path_project / "project.yaml"
        original = project_yaml.read_text()
        project_yaml.write_text(
            original + f"\nrepos:\n  SeidoAI/fake:\n    local: {clone}\n"
        )

        save_test_issue(tmp_path_project, "T-1", kind="feat")
        save_test_session(
            tmp_path_project,
            "s-modify",
            status="planned",
            issues=["T-1"],
            repos=[{"repo": "SeidoAI/fake", "base_branch": "main"}],
        )
        _write_plan(
            tmp_path_project,
            "s-modify",
            "# Plan\n\n"
            "### Step 1: Update the helper\n"
            "- **Files:** `src/missing_helper.py`\n"
            "- **Change:** Modify the helper to support X.\n",
        )

        runner = CliRunner()
        result = runner.invoke(
            validate_plan_cmd,
            ["s-modify", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 1, result.output
        assert "plan/modify_target_missing" in result.output

    def test_prefix_set_resolves_sub_tree_path(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        """When `path_prefix` is set on a repo binding, plan paths
        resolve relative to `<clone>/<path_prefix>` as well as the
        clone root. Frontend plans can say `src/app/router.tsx`
        instead of the full monorepo path."""
        clone = tmp_path_project / "fake-clone"
        existing_file = clone / "web" / "src" / "app" / "router.tsx"
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("// router\n")

        project_yaml = tmp_path_project / "project.yaml"
        original = project_yaml.read_text()
        project_yaml.write_text(
            original + f"\nrepos:\n  SeidoAI/fake:\n    local: {clone}\n"
        )

        save_test_issue(tmp_path_project, "T-1", kind="feat")
        save_test_session(
            tmp_path_project,
            "s-prefix",
            status="planned",
            issues=["T-1"],
            repos=[
                {
                    "repo": "SeidoAI/fake",
                    "base_branch": "main",
                    "path_prefix": "web",
                }
            ],
        )
        _write_plan(
            tmp_path_project,
            "s-prefix",
            "# Plan\n\n"
            "### Step 1: Update the router\n"
            "- **Files:** `src/app/router.tsx`\n"
            "- **Change:** Modify the router to support X.\n",
        )

        runner = CliRunner()
        result = runner.invoke(
            validate_plan_cmd,
            ["s-prefix", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        assert "plan/modify_target_missing" not in result.output

    def test_prefix_unset_produces_modify_target_missing_warning(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        """Regression guard for the prefix feature: same fixture as
        the prefix-set case, but without `path_prefix`, the existing
        file is invisible to the resolver and we get the warning.
        Proves the prefix is doing the work — not some unrelated
        resolver fix that made the first test pass."""
        clone = tmp_path_project / "fake-clone"
        existing_file = (
            clone
            / "src"
            / "tripwire"
            / "ui"
            / "frontend"
            / "src"
            / "app"
            / "router.tsx"
        )
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("// router\n")

        project_yaml = tmp_path_project / "project.yaml"
        original = project_yaml.read_text()
        project_yaml.write_text(
            original + f"\nrepos:\n  SeidoAI/fake:\n    local: {clone}\n"
        )

        save_test_issue(tmp_path_project, "T-1", kind="feat")
        save_test_session(
            tmp_path_project,
            "s-no-prefix",
            status="planned",
            issues=["T-1"],
            repos=[{"repo": "SeidoAI/fake", "base_branch": "main"}],
        )
        _write_plan(
            tmp_path_project,
            "s-no-prefix",
            "# Plan\n\n"
            "### Step 1: Update the router\n"
            "- **Files:** `src/app/router.tsx`\n"
            "- **Change:** Modify the router to support X.\n",
        )

        runner = CliRunner()
        result = runner.invoke(
            validate_plan_cmd,
            ["s-no-prefix", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 1, result.output
        assert "plan/modify_target_missing" in result.output
        assert "src/app/router.tsx" in result.output

    def test_json_format_returns_structured(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s-json", status="planned")
        _write_plan(
            tmp_path_project,
            "s-json",
            "# Plan\n\nUses `[[ghost-node]]`.\n",
        )

        runner = CliRunner()
        result = runner.invoke(
            validate_plan_cmd,
            [
                "s-json",
                "--project-dir",
                str(tmp_path_project),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 2
        # Content-assertion — actual JSON structure carries the codes.
        import json as _json

        payload = _json.loads(result.output)
        assert payload["session_id"] == "s-json"
        codes = [r["code"] for r in payload["errors"]]
        assert "plan/unresolved_ref" in codes
