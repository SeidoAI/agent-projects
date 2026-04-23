"""Tests for `tripwire init` repo-local prompts (I2).

v0.7.2 init collected slug lists but never prompted for each slug's
`local:` clone path — every `tripwire session spawn` on a fresh
project failed with "No local clone for X". I2 adds a prompt loop
after slug collection that defaults to a sibling directory when one
matches the repo basename.
"""

from __future__ import annotations

import pytest
import yaml
from click.testing import CliRunner

from tripwire.cli.init import (
    _guess_local_for_slug,
    _prompt_for_repo_locals,
    init_cmd,
)


class TestGuessLocalForSlug:
    def test_finds_sibling_matching_basename(self, tmp_path):
        clone = tmp_path / "web-app"
        (clone / ".git").mkdir(parents=True)
        project = tmp_path / "project"
        project.mkdir()

        result = _guess_local_for_slug("SeidoAI/web-app", project)

        assert result == str(clone)

    def test_returns_none_when_no_sibling(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        assert _guess_local_for_slug("SeidoAI/web-app", project) is None

    def test_ignores_non_git_directory(self, tmp_path):
        """A directory with the right name but no .git isn't a clone."""
        (tmp_path / "web-app").mkdir()
        project = tmp_path / "project"
        project.mkdir()
        assert _guess_local_for_slug("SeidoAI/web-app", project) is None

    def test_looks_at_grandparent_too(self, tmp_path):
        """Common monorepo layout: cwd is workspaces/project, clone is
        workspaces/../code — grandparent scan finds it."""
        clone = tmp_path / "code"
        (clone / ".git").mkdir(parents=True)
        deep = tmp_path / "workspaces" / "project"
        deep.mkdir(parents=True)
        assert _guess_local_for_slug("SeidoAI/code", deep) == str(clone)


class TestPromptForRepoLocals:
    def test_prompts_per_slug_and_returns_dict(self, tmp_path, monkeypatch):
        """Sequential prompts; each answer lands in the returned dict keyed by slug."""
        answers = iter(["/home/alice/first", "/home/alice/second"])
        monkeypatch.setattr("click.prompt", lambda *_a, **_k: next(answers))

        result = _prompt_for_repo_locals(["SeidoAI/first", "SeidoAI/second"], tmp_path)

        assert result == {
            "SeidoAI/first": "/home/alice/first",
            "SeidoAI/second": "/home/alice/second",
        }

    def test_empty_answer_records_none(self, tmp_path, monkeypatch):
        """Blank answer means "skip for now", recorded as None."""
        monkeypatch.setattr("click.prompt", lambda *_a, **_k: "  ")
        result = _prompt_for_repo_locals(["SeidoAI/x"], tmp_path)
        assert result == {"SeidoAI/x": None}

    def test_default_is_sibling_guess_when_available(self, tmp_path, monkeypatch):
        clone = tmp_path / "web-app"
        (clone / ".git").mkdir(parents=True)
        project = tmp_path / "project"
        project.mkdir()

        seen_defaults: list[str] = []

        def _prompt(_msg: str, default: str = "", **_kw) -> str:
            seen_defaults.append(default)
            return default

        monkeypatch.setattr("click.prompt", _prompt)

        result = _prompt_for_repo_locals(["SeidoAI/web-app"], project)

        assert seen_defaults == [str(clone)]
        assert result == {"SeidoAI/web-app": str(clone)}


class TestInitCmdIntegration:
    """End-to-end: run `tripwire init` via CliRunner and inspect the
    project.yaml it wrote. Content assertions, not "exit 0"."""

    def test_init_writes_local_paths_for_each_repo(self, tmp_path):
        runner = CliRunner()
        # Enter-separated answers for: name, key-prefix, base-branch
        # (default main), repos, then one local per slug. After "no git".
        user_input = (
            "smoke\n"  # project name
            "SMK\n"  # key prefix (accepts default-from-name or types)
            "main\n"  # base branch
            "SeidoAI/alpha,SeidoAI/beta\n"  # repo slugs
            "/local/alpha\n"  # local for alpha
            "/local/beta\n"  # local for beta
        )
        result = runner.invoke(
            init_cmd,
            [str(tmp_path / "proj"), "--no-git"],
            input=user_input,
        )

        assert result.exit_code == 0, result.output
        written = yaml.safe_load((tmp_path / "proj" / "project.yaml").read_text())
        assert written["repos"] == {
            "SeidoAI/alpha": {"local": "/local/alpha"},
            "SeidoAI/beta": {"local": "/local/beta"},
        }

    def test_non_interactive_writes_null_locals(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            init_cmd,
            [
                str(tmp_path / "proj"),
                "--non-interactive",
                "--name",
                "smoke",
                "--key-prefix",
                "SMK",
                "--base-branch",
                "main",
                "--repos",
                "SeidoAI/x",
                "--no-git",
            ],
        )
        assert result.exit_code == 0, result.output
        written = yaml.safe_load((tmp_path / "proj" / "project.yaml").read_text())
        assert written["repos"] == {"SeidoAI/x": {"local": None}}

    @pytest.mark.parametrize("blank_answer", ["", "  ", "\t"])
    def test_blank_local_answer_yields_null(self, tmp_path, blank_answer):
        """Hitting enter on the local prompt (no sibling guess) records null."""
        runner = CliRunner()
        user_input = (
            "smoke\n"
            "SMK\n"
            "main\n"
            "SeidoAI/x\n"
            f"{blank_answer}\n"  # blank local → null
        )
        result = runner.invoke(
            init_cmd,
            [str(tmp_path / "proj"), "--no-git"],
            input=user_input,
        )
        assert result.exit_code == 0, result.output
        written = yaml.safe_load((tmp_path / "proj" / "project.yaml").read_text())
        assert written["repos"] == {"SeidoAI/x": {"local": None}}
