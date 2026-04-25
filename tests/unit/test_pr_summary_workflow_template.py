"""Verify the packaged ``pr-summary.yml.j2`` workflow template renders to
valid YAML, stamps the configured tripwire version, escapes GitHub
Actions ``${{ ... }}`` expressions through Jinja's raw blocks, and gets
copied into freshly-init'd projects.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner
from jinja2 import Environment, FileSystemLoader

from tripwire.cli.main import cli
from tripwire.templates import get_templates_dir


def _render_template(version: str) -> str:
    template_root = get_templates_dir() / "project" / ".github" / "workflows"
    env = Environment(
        loader=FileSystemLoader(str(template_root)),
        keep_trailing_newline=True,
    )
    return env.get_template("pr-summary.yml.j2").render(tripwire_version=version)


def test_template_renders_to_valid_yaml():
    rendered = _render_template("0.7.7")
    data = yaml.safe_load(rendered)
    assert data["name"] == "PR summary"
    # YAML 1.1 turns the bareword ``on`` into the boolean True.
    assert "pull_request" in data[True]
    assert data["jobs"]["summary"]["runs-on"] == "ubuntu-latest"


def test_template_stamps_tripwire_version():
    rendered = _render_template("0.7.7")
    assert "tripwire-pm>=0.7.7" in rendered


def test_template_preserves_github_actions_expressions():
    """``${{ github.base_ref }}`` and friends must survive Jinja rendering."""
    rendered = _render_template("0.7.7")
    assert "${{ github.base_ref }}" in rendered
    assert "${{ github.event.pull_request.number }}" in rendered


def test_template_pins_third_party_actions_to_specific_versions():
    rendered = _render_template("0.7.7")
    assert "actions/checkout@v6" in rendered
    assert "astral-sh/setup-uv@v8.1.0" in rendered
    assert "peter-evans/create-or-update-comment@v4" in rendered


def test_template_includes_marker_discriminator():
    rendered = _render_template("0.7.7")
    assert "<!-- tripwire-pr-summary -->" in rendered


def test_template_requests_pull_request_write_permission():
    rendered = _render_template("0.7.7")
    data = yaml.safe_load(rendered)
    assert data["permissions"]["pull-requests"] == "write"


def test_template_uses_full_clone_for_base_ref_resolution():
    """``fetch-depth: 0`` is required so the base SHA is resolvable."""
    rendered = _render_template("0.7.7")
    data = yaml.safe_load(rendered)
    checkout_step = next(
        s
        for s in data["jobs"]["summary"]["steps"]
        if s.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout_step["with"]["fetch-depth"] == 0


def test_init_stamps_workflow_into_project(tmp_path: Path):
    runner = CliRunner()
    target = tmp_path / "stamped"
    result = runner.invoke(
        cli,
        [
            "init",
            str(target),
            "--name",
            "stamp-test",
            "--key-prefix",
            "ST",
            "--base-branch",
            "main",
            "--non-interactive",
            "--no-git",
        ],
    )
    assert result.exit_code == 0, result.output
    wf = target / ".github" / "workflows" / "pr-summary.yml"
    assert wf.is_file(), "pr-summary.yml was not stamped into the project"
    data = yaml.safe_load(wf.read_text(encoding="utf-8"))
    assert data["name"] == "PR summary"
