"""Integration tests for `keel init`.

These tests exercise the CLI end-to-end via Click's `CliRunner`: they
invoke the actual command against a tmp directory and assert on the
resulting project structure, then run the validator against the result
to confirm a freshly-init'd project passes the gate cleanly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from keel.cli.main import cli
from keel.core.validator import validate_project


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _init_args(target: Path, **overrides: str) -> list[str]:
    """Return a `[init, ...]` argv that skips all prompts by default."""
    args = [
        "init",
        str(target),
        "--name",
        overrides.get("name", "test-project"),
        "--key-prefix",
        overrides.get("key_prefix", "TST"),
        "--base-branch",
        overrides.get("base_branch", "main"),
        "--non-interactive",
    ]
    if overrides.get("repos"):
        args += ["--repos", overrides["repos"]]
    if overrides.get("no_git", True):
        args.append("--no-git")
    if overrides.get("force"):
        args.append("--force")
    return args


# ============================================================================
# Core init flow
# ============================================================================


class TestInitBasics:
    def test_creates_all_expected_files(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "test-init"
        result = runner.invoke(cli, _init_args(target))
        assert result.exit_code == 0, result.output

        # Top-level files
        assert (target / "project.yaml").exists()
        assert (target / "CLAUDE.md").exists()
        assert (target / ".gitignore").exists()

        # Empty project directories with .gitkeep markers
        for rel in ("issues", "nodes", "sessions", "plans"):
            assert (target / rel).is_dir(), f"Missing directory: {rel}"
            assert (target / rel / ".gitkeep").exists(), f"Missing .gitkeep in {rel}"
        # docs/issues is no longer created by init (Phase 4 of v0.5 refactor
        # colocated issue artifacts under issues/<KEY>/ instead).
        assert not (target / "docs" / "issues").exists()

    def test_project_yaml_has_rendered_fields(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        result = runner.invoke(cli, _init_args(target, name="seido", key_prefix="SEI"))
        assert result.exit_code == 0

        raw = yaml.safe_load((target / "project.yaml").read_text())
        assert raw["name"] == "seido"
        assert raw["key_prefix"] == "SEI"
        assert raw["base_branch"] == "main"
        assert raw["next_issue_number"] == 1
        assert raw["next_session_number"] == 1
        assert "backlog" in raw["statuses"]
        assert "todo" in raw["status_transitions"]["backlog"]

    def test_claude_md_has_project_name_and_prefix(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        runner.invoke(cli, _init_args(target, name="seido", key_prefix="SEI"))
        claude = (target / "CLAUDE.md").read_text()
        assert "# seido" in claude
        assert "SEI" in claude

    def test_jinja_renders_project_name_and_key_prefix_completely(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Full Jinja render check: every templated file must substitute
        all `{{ var }}` markers, and the rendered files must NOT contain
        any leftover `{{` or `}}` from unrendered templates.
        """
        target = tmp_path / "render-test"
        result = runner.invoke(
            cli,
            _init_args(
                target,
                name="render-project",
                key_prefix="RND",
                base_branch="develop",
            ),
        )
        assert result.exit_code == 0, result.output

        # Every file at the project root that was rendered from a .j2
        # template must contain the substituted values, not the raw markers.
        claude = (target / "CLAUDE.md").read_text()
        assert "render-project" in claude
        assert "RND" in claude
        assert "develop" in claude
        # No leftover Jinja markers — these would mean a variable wasn't
        # substituted (StrictUndefined would have raised, but defence in
        # depth is cheap).
        assert "{{" not in claude
        assert "}}" not in claude

        # Same for project.yaml — it's also rendered from a .j2 template.
        project_yaml = (target / "project.yaml").read_text()
        assert "render-project" in project_yaml
        assert "RND" in project_yaml
        assert "{{" not in project_yaml
        assert "}}" not in project_yaml

    def test_gitignore_includes_runtime_state(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        runner.invoke(cli, _init_args(target))
        gi = (target / ".gitignore").read_text()
        assert ".keel.lock" in gi
        assert "graph/.index.lock" in gi

    def test_non_interactive_missing_name_uses_target_basename(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """In non-interactive mode, missing --name defaults to the target
        directory basename rather than erroring out (matches the interactive
        prompt default)."""
        target = tmp_path / "web-app"
        result = runner.invoke(
            cli,
            [
                "init",
                str(target),
                "--key-prefix",
                "TST",
                "--non-interactive",
                "--no-git",
            ],
        )
        assert result.exit_code == 0, result.output
        raw = yaml.safe_load((target / "project.yaml").read_text())
        assert raw["name"] == "web-app"

    def test_non_interactive_auto_extracts_key_prefix(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """In non-interactive mode, missing --key-prefix is auto-extracted
        from the project name rather than erroring out."""
        target = tmp_path / "p"
        result = runner.invoke(
            cli,
            [
                "init",
                str(target),
                "--name",
                "my-project-cool",
                "--non-interactive",
                "--no-git",
            ],
        )
        assert result.exit_code == 0, result.output
        raw = yaml.safe_load((target / "project.yaml").read_text())
        assert raw["key_prefix"] == "MPC"

    def test_non_interactive_extraction_failure_raises(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """When the name starts with a digit, extraction fails and the
        user must pass --key-prefix explicitly."""
        result = runner.invoke(
            cli,
            [
                "init",
                str(tmp_path / "p"),
                "--name",
                "2024-retro",
                "--non-interactive",
                "--no-git",
            ],
        )
        assert result.exit_code != 0
        assert "Could not auto-extract" in result.output
        assert "--key-prefix" in result.output

    def test_default_base_branch_is_main(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """When --base-branch is omitted, the default is 'main'."""
        target = tmp_path / "p"
        result = runner.invoke(
            cli,
            [
                "init",
                str(target),
                "--name",
                "p",
                "--key-prefix",
                "P",
                "--non-interactive",
                "--no-git",
            ],
        )
        assert result.exit_code == 0, result.output
        raw = yaml.safe_load((target / "project.yaml").read_text())
        assert raw["base_branch"] == "main"

    def test_init_copies_all_pm_slash_commands(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Every initialized project ships with the /pm-* slash commands
        at .claude/commands/."""
        target = tmp_path / "p"
        result = runner.invoke(cli, _init_args(target))
        assert result.exit_code == 0, result.output

        commands_dir = target / ".claude" / "commands"
        assert commands_dir.is_dir(), f"Missing {commands_dir}"

        expected = {
            # v0.6a retained + renamed + new:
            "pm-agenda.md",
            "pm-edit.md",
            "pm-graph.md",
            "pm-issue-close.md",
            "pm-lint.md",
            "pm-rescope.md",
            "pm-review.md",
            "pm-scope.md",
            "pm-session-check.md",
            "pm-session-create.md",
            "pm-session-launch.md",
            "pm-session-progress.md",
            "pm-status.md",
            "pm-triage.md",
            "pm-validate.md",
            # v0.6b workspace commands:
            "pm-project-create.md",
            "pm-project-sync.md",
            # Deprecated forwarders (removed in v0.7):
            "pm-close.md",
            "pm-handoff.md",
            "pm-plan.md",
            "pm-update.md",
        }
        actual = {p.name for p in commands_dir.glob("*.md")}
        assert expected == actual, (
            f"Expected {expected}, got {actual}. "
            f"Missing: {expected - actual}. Extra: {actual - expected}."
        )

    def test_invalid_key_prefix_rejected(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        # `1abc` → normalised to `1ABC`, which does not match the
        # `^[A-Z][A-Z0-9]*$` pattern (must start with a letter).
        result = runner.invoke(
            cli,
            _init_args(tmp_path / "p2", key_prefix="1abc"),
        )
        assert result.exit_code != 0
        assert "Invalid key prefix" in result.output

    def test_lowercase_key_prefix_normalised(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        # `sei` → normalised to `SEI`, which is valid.
        target = tmp_path / "p"
        result = runner.invoke(cli, _init_args(target, key_prefix="sei"))
        assert result.exit_code == 0
        raw = yaml.safe_load((target / "project.yaml").read_text())
        assert raw["key_prefix"] == "SEI"

    def test_refuses_to_overwrite_existing_project_yaml(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        first = runner.invoke(cli, _init_args(target))
        assert first.exit_code == 0

        second = runner.invoke(cli, _init_args(target))
        assert second.exit_code != 0
        assert "already exists" in second.output

    def test_force_overwrites_existing_project_yaml(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        runner.invoke(cli, _init_args(target, name="first"))
        result = runner.invoke(cli, _init_args(target, name="second", force=True))
        assert result.exit_code == 0
        raw = yaml.safe_load((target / "project.yaml").read_text())
        assert raw["name"] == "second"


# ============================================================================
# Repos flag
# ============================================================================


class TestReposFlag:
    def test_repos_flag_populates_project_yaml(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        result = runner.invoke(
            cli,
            _init_args(
                target,
                repos="SeidoAI/web-app-backend,SeidoAI/web-app-infrastructure",
            ),
        )
        assert result.exit_code == 0
        raw = yaml.safe_load((target / "project.yaml").read_text())
        assert "SeidoAI/web-app-backend" in raw["repos"]
        assert "SeidoAI/web-app-infrastructure" in raw["repos"]
        # Each entry should have a local key (null by default)
        assert raw["repos"]["SeidoAI/web-app-backend"]["local"] is None

    def test_empty_repos_leaves_mapping_empty(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        result = runner.invoke(cli, _init_args(target))
        assert result.exit_code == 0
        raw = yaml.safe_load((target / "project.yaml").read_text())
        # No repos declared → empty dict (or the rendered empty-mapping token)
        assert raw["repos"] in ({}, None)


# ============================================================================
# Git init
# ============================================================================


class TestGitInit:
    def test_no_git_flag_skips_git_init(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        result = runner.invoke(cli, _init_args(target, no_git=True))
        assert result.exit_code == 0
        assert not (target / ".git").exists()

    def test_git_init_runs_by_default(self, runner: CliRunner, tmp_path: Path) -> None:
        # Ensure git is available — skip if not.
        try:
            subprocess.run(["git", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pytest.skip("git is not installed")

        target = tmp_path / "p"
        # Drop the default --no-git from the helper by building args manually.
        args = [
            "init",
            str(target),
            "--name",
            "p",
            "--key-prefix",
            "TST",
            "--base-branch",
            "main",
            "--non-interactive",
        ]
        result = runner.invoke(cli, args)
        assert result.exit_code == 0, result.output
        assert (target / ".git").is_dir()


# ============================================================================
# The produced project validates cleanly
# ============================================================================


class TestInitThenValidate:
    def test_initd_project_passes_validate(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        result = runner.invoke(cli, _init_args(target))
        assert result.exit_code == 0

        report = validate_project(target)
        assert report.exit_code == 0, [f"{e.code}: {e.message}" for e in report.errors]
        assert report.errors == []
        assert report.warnings == []
        # Cache should have been built by the validator's side-effect.
        assert report.cache_rebuilt is True
        assert (target / "graph" / "index.yaml").exists()

    def test_initd_project_with_repos_passes_validate(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        result = runner.invoke(
            cli,
            _init_args(target, repos="SeidoAI/backend,SeidoAI/frontend"),
        )
        assert result.exit_code == 0

        report = validate_project(target)
        assert report.exit_code == 0, [f"{e.code}: {e.message}" for e in report.errors]

    def test_second_validate_is_noop_for_cache(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        runner.invoke(cli, _init_args(target))

        first = validate_project(target)
        assert first.cache_rebuilt is True
        second = validate_project(target)
        assert second.cache_rebuilt is False, "second validate should not rebuild"


# ============================================================================
# Targeting behaviour
# ============================================================================


class TestTargetPath:
    def test_init_into_current_directory(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        # Invoke with `.` as the target; use CliRunner's isolated filesystem
        # to verify the current-dir behaviour.
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            result = runner.invoke(
                cli,
                [
                    "init",
                    ".",
                    "--name",
                    "p",
                    "--key-prefix",
                    "TST",
                    "--base-branch",
                    "main",
                    "--non-interactive",
                    "--no-git",
                ],
            )
            assert result.exit_code == 0
            assert (Path(td) / "project.yaml").exists()

    def test_init_creates_missing_parent_dirs(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "deeply" / "nested" / "target"
        result = runner.invoke(cli, _init_args(target))
        assert result.exit_code == 0
        assert target.is_dir()
        assert (target / "project.yaml").exists()
