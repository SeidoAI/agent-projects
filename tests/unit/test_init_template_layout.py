"""v0.10.0 regression: `tripwire init` writes consolidated layout under templates/.

Before v0.10.0, init scattered template/config dirs (`agents/`,
`comment_templates/`, `enums/`, `issue_templates/`,
`session_templates/`, `orchestration/`) as siblings at the project
root. v0.10.0 nests them all under one `templates/` parent so the root
keeps only operational state directories (`issues/`, `nodes/`,
`sessions/`, `inbox/`, `events/`, `graph/`, `plans/`, `templates/`).

This file asserts the new layout shape end-to-end via the actual
`tripwire init` command. Pre-v0.10.0 projects continue to work via
the dual-read resolver in `core/paths.py`; that path is exercised by
existing route + service tests that hand-build the legacy layout.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.main import cli


def test_init_writes_consolidated_templates_layout(tmp_path: Path):
    """Every templated dir lands under `templates/`, none at the project root."""
    runner = CliRunner()
    project = tmp_path / "fresh"
    result = runner.invoke(
        cli,
        [
            "init",
            "--non-interactive",
            "--no-git",
            "--no-remote",
            "--name",
            "fresh",
            "--key-prefix",
            "FRS",
            str(project),
        ],
    )
    assert result.exit_code == 0, result.output

    # Canonical: every template/config dir under templates/.
    expected_under_templates = {
        "agents",
        "artifacts",
        "comments",
        "enums",
        "issues",
        "orchestration",
        "sessions",
    }
    templates_root = project / "templates"
    assert templates_root.is_dir(), "templates/ must exist after init"
    found = {d.name for d in templates_root.iterdir() if d.is_dir()}
    assert expected_under_templates.issubset(found), (
        f"missing templates/ subdirs: {expected_under_templates - found}"
    )

    # Anti-spec: legacy flat-layout siblings must NOT exist post-init.
    legacy_siblings = (
        "agent_templates",
        "comment_templates",
        "enums",
        "issue_templates",
        "session_templates",
        "orchestration",
    )
    for legacy in legacy_siblings:
        assert not (project / legacy).is_dir(), (
            f"legacy {legacy}/ must not exist at project root after v0.10.0 init"
        )

    # Operational state dirs still at the root (unchanged by v0.10.0).
    for state in ("issues", "nodes", "sessions", "plans"):
        assert (project / state).is_dir(), f"state dir {state}/ missing"


def test_init_does_not_create_graph_directory(tmp_path: Path):
    """v0.10.0 collapses the graph cache from `graph/index.yaml` into
    `nodes/tripwire-graph-index.yaml`. A fresh project must not ship a
    standalone `graph/` directory.
    """
    runner = CliRunner()
    project = tmp_path / "fresh"
    result = runner.invoke(
        cli,
        [
            "init",
            "--non-interactive",
            "--no-git",
            "--no-remote",
            "--name",
            "fresh",
            "--key-prefix",
            "FRS",
            str(project),
        ],
    )
    assert result.exit_code == 0, result.output
    assert not (project / "graph").exists(), "graph/ must not exist post-init"


def test_init_populates_templates_agents_with_yaml_files(tmp_path: Path):
    """Sanity: at least one packaged agent YAML lands under templates/agents/."""
    runner = CliRunner()
    project = tmp_path / "fresh"
    result = runner.invoke(
        cli,
        [
            "init",
            "--non-interactive",
            "--no-git",
            "--no-remote",
            "--name",
            "fresh",
            "--key-prefix",
            "FRS",
            str(project),
        ],
    )
    assert result.exit_code == 0, result.output

    agents_dir = project / "templates" / "agents"
    yamls = list(agents_dir.glob("*.yaml"))
    assert yamls, "templates/agents/ must contain agent YAMLs after init"
    # Each agent yaml has its id at the top — sanity-check one file.
    sample = yamls[0].read_text(encoding="utf-8")
    assert "id:" in sample
