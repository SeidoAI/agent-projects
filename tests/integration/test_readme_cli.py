"""Integration tests for `tripwire readme generate`."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from tripwire.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project(tmp_path_project: Path) -> Path:
    """Alias for clarity: this is the project root with project.yaml."""
    return tmp_path_project


# ============================================================================
# Generate path
# ============================================================================


class TestGenerate:
    def test_writes_readme_to_default_location(
        self, runner: CliRunner, project: Path
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "readme",
                "generate",
                "--project-dir",
                str(project),
                "--merges-limit",
                "0",
            ],
        )
        assert result.exit_code == 0, result.output
        readme = project / "README.md"
        assert readme.is_file()
        content = readme.read_text(encoding="utf-8")
        assert content.startswith("<!-- tripwire-readme-auto -->")
        assert "## Session graph" in content

    def test_writes_to_custom_output_path(
        self, runner: CliRunner, project: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "out" / "MY_README.md"
        result = runner.invoke(
            cli,
            [
                "readme",
                "generate",
                "--project-dir",
                str(project),
                "--output",
                str(out),
                "--merges-limit",
                "0",
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.is_file()
        # Default README.md should NOT have been written when --output points
        # elsewhere.
        assert not (project / "README.md").exists()

    def test_section_order_matches_spec(self, runner: CliRunner, project: Path) -> None:
        result = runner.invoke(
            cli,
            [
                "readme",
                "generate",
                "--project-dir",
                str(project),
                "--merges-limit",
                "0",
            ],
        )
        assert result.exit_code == 0, result.output
        content = (project / "README.md").read_text(encoding="utf-8")
        # Importance hierarchy must hold even after future template edits.
        section_order = [
            "## At a glance",
            "## Session graph",
            "## Active sessions",
            "## Recent merges",
            "## Critical path",
            "## Roadmap",
            "## Workspace",
            "<summary><b>Issues</b>",
            "<summary><b>All sessions</b>",
            "## Links",
        ]
        last = -1
        for marker in section_order:
            idx = content.find(marker)
            assert idx > last, f"{marker!r} missing or out of order"
            last = idx


# ============================================================================
# --check semantics
# ============================================================================


class TestCheck:
    def test_check_exits_0_when_in_sync(self, runner: CliRunner, project: Path) -> None:
        # Generate first, then immediately --check: must be in sync.
        gen = runner.invoke(
            cli,
            [
                "readme",
                "generate",
                "--project-dir",
                str(project),
                "--merges-limit",
                "0",
            ],
        )
        assert gen.exit_code == 0, gen.output

        check = runner.invoke(
            cli,
            [
                "readme",
                "generate",
                "--project-dir",
                str(project),
                "--check",
                "--merges-limit",
                "0",
            ],
        )
        assert check.exit_code == 0, check.output
        assert "in sync" in check.output

    def test_check_exits_1_when_out_of_sync(
        self, runner: CliRunner, project: Path
    ) -> None:
        # No README.md → out of sync.
        result = runner.invoke(
            cli,
            [
                "readme",
                "generate",
                "--project-dir",
                str(project),
                "--check",
                "--merges-limit",
                "0",
            ],
        )
        assert result.exit_code == 1
        # Stderr is captured into result.output for CliRunner by default
        # depending on mix_stderr; we check stdout+stderr together.
        combined = (result.output or "") + (result.stderr or "")
        assert "out of sync" in combined

    def test_check_exits_1_when_content_diverges(
        self, runner: CliRunner, project: Path
    ) -> None:
        gen = runner.invoke(
            cli,
            [
                "readme",
                "generate",
                "--project-dir",
                str(project),
                "--merges-limit",
                "0",
            ],
        )
        assert gen.exit_code == 0
        # Mutate the generated README to force divergence.
        readme = project / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8") + "\nLOCAL EDIT\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            cli,
            [
                "readme",
                "generate",
                "--project-dir",
                str(project),
                "--check",
                "--merges-limit",
                "0",
            ],
        )
        assert result.exit_code == 1


# ============================================================================
# Custom template
# ============================================================================


class TestCustomTemplate:
    def test_explicit_template_overrides_default(
        self, runner: CliRunner, project: Path, tmp_path: Path
    ) -> None:
        custom = tmp_path / "custom.md.j2"
        custom.write_text(
            "<!-- tripwire-readme-auto -->\n"
            "Project: {{ project_name }}\nSessions: {{ total_sessions }}\n"
        )
        result = runner.invoke(
            cli,
            [
                "readme",
                "generate",
                "--project-dir",
                str(project),
                "--template",
                str(custom),
                "--merges-limit",
                "0",
            ],
        )
        assert result.exit_code == 0, result.output
        content = (project / "README.md").read_text(encoding="utf-8")
        assert "Project: tmp" in content
        assert "Sessions: 0" in content

    def test_project_dot_tripwire_template_overrides_packaged(
        self, runner: CliRunner, project: Path
    ) -> None:
        override_dir = project / ".tripwire"
        override_dir.mkdir()
        (override_dir / "readme.md.j2").write_text(
            "<!-- tripwire-readme-auto -->\nFROM-PROJECT-OVERRIDE: {{ project_name }}\n"
        )
        result = runner.invoke(
            cli,
            [
                "readme",
                "generate",
                "--project-dir",
                str(project),
                "--merges-limit",
                "0",
            ],
        )
        assert result.exit_code == 0, result.output
        content = (project / "README.md").read_text(encoding="utf-8")
        assert "FROM-PROJECT-OVERRIDE: tmp" in content


# ============================================================================
# Recent merges fallback
# ============================================================================


class TestRecentMerges:
    def test_merges_limit_zero_omits_section_content(
        self, runner: CliRunner, project: Path
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "readme",
                "generate",
                "--project-dir",
                str(project),
                "--merges-limit",
                "0",
            ],
        )
        assert result.exit_code == 0, result.output
        content = (project / "README.md").read_text(encoding="utf-8")
        # The section header is always present; with no merges fetched
        # the body falls back to the placeholder text.
        assert "## Recent merges" in content
        assert "No recent merges" in content
