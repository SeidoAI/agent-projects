"""tripwire ci install CLI."""

from pathlib import Path

import yaml
from click.testing import CliRunner

from tripwire.cli.ci import ci_cmd


def test_ci_install_writes_workflow(tmp_path_project: Path):
    project_yaml = tmp_path_project / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    data["tripwire_version"] = "0.7.0"
    project_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(ci_cmd, ["install", "--project-dir", str(tmp_path_project)])
    assert result.exit_code == 0, result.output
    wf = tmp_path_project / ".github" / "workflows" / "tripwire.yml"
    assert wf.is_file()
    text = wf.read_text(encoding="utf-8")
    assert "tripwire-pm==0.7.0" in text
    # v0.7.6 §2.E.1: bumped from @v4 (Node 20 deprecated 2026-09-16).
    assert "actions/checkout@v6" in text


def test_ci_install_falls_back_to_installed_version(tmp_path_project: Path):
    """When project has no tripwire_version, use the installed CLI version."""
    runner = CliRunner()
    result = runner.invoke(ci_cmd, ["install", "--project-dir", str(tmp_path_project)])
    assert result.exit_code == 0, result.output
    wf = tmp_path_project / ".github" / "workflows" / "tripwire.yml"
    assert wf.is_file()
    text = wf.read_text(encoding="utf-8")
    # fallback version is the installed tripwire
    from tripwire import __version__

    assert f"tripwire-pm=={__version__}" in text


def test_ci_install_refuses_overwrite(tmp_path_project: Path):
    wf_dir = tmp_path_project / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "tripwire.yml").write_text("# existing\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(ci_cmd, ["install", "--project-dir", str(tmp_path_project)])
    assert result.exit_code != 0
    assert (
        "already exists" in result.output
        or "already exists" in (result.stderr_bytes or b"").decode()
    )


def test_ci_install_force_overwrites(tmp_path_project: Path):
    wf_dir = tmp_path_project / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "tripwire.yml").write_text("# existing\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        ci_cmd,
        [
            "install",
            "--project-dir",
            str(tmp_path_project),
            "--force",
            "--version",
            "0.7.0",
        ],
    )
    assert result.exit_code == 0, result.output
    wf = wf_dir / "tripwire.yml"
    text = wf.read_text(encoding="utf-8")
    assert "tripwire-pm==0.7.0" in text
    assert "# existing" not in text


def test_ci_install_version_override_wins(tmp_path_project: Path):
    project_yaml = tmp_path_project / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    data["tripwire_version"] = "0.6.0"
    project_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        ci_cmd,
        [
            "install",
            "--project-dir",
            str(tmp_path_project),
            "--version",
            "0.99.0",
        ],
    )
    assert result.exit_code == 0, result.output
    wf = tmp_path_project / ".github" / "workflows" / "tripwire.yml"
    assert "tripwire-pm==0.99.0" in wf.read_text(encoding="utf-8")
