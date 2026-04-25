"""Tests for the README CD workflow template.

The template stamps `<project>/.github/workflows/readme.yml` at init.
We assert all three loop guardrails are present in the rendered output
and that the template renders cleanly with the init context.
"""

from __future__ import annotations

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from tripwire.templates import get_templates_dir

WORKFLOW_RELPATH = "project/.github/workflows/readme.yml.j2"


def _render_workflow(tripwire_version: str = "0.7.8") -> str:
    """Render the workflow template the same way `tripwire init` does."""
    env = Environment(
        loader=FileSystemLoader(str(get_templates_dir())),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    template = env.get_template(WORKFLOW_RELPATH)
    return template.render(tripwire_version=tripwire_version)


def test_template_renders_without_strict_undefined_errors() -> None:
    """StrictUndefined surfaces typos as render errors. If this passes,
    every variable referenced by the template is in the init context."""
    out = _render_workflow()
    assert out  # non-empty


def test_workflow_parses_as_yaml() -> None:
    parsed = yaml.safe_load(_render_workflow())
    # `on:` is a Python boolean key when parsed by PyYAML 1.1, but PyYAML
    # 5+ treats it as a string. Accept either to keep the test stable.
    assert "jobs" in parsed
    assert "regenerate" in parsed["jobs"]


def test_guardrail_1_skip_self_triggered_runs() -> None:
    """First guardrail: the job-level `if:` skips runs whose head commit
    we made (commit message starts with `docs(readme):`)."""
    out = _render_workflow()
    assert "!startsWith(github.event.head_commit.message, 'docs(readme):')" in out


def test_guardrail_2_skip_ci_in_commit_body() -> None:
    """Second guardrail: `[skip ci]` in the bot's commit message means
    any workflow without its own filter still won't fire on our commit."""
    out = _render_workflow()
    assert "[skip ci]" in out


def test_guardrail_3_git_diff_quiet_short_circuits_push() -> None:
    """Third guardrail: when the rendered README is identical to the file
    on disk, `git diff --quiet` exits 0 and the step bails before commit."""
    out = _render_workflow()
    assert "git diff --quiet README.md" in out
    # Make sure it's actually used as a guard, not just mentioned.
    assert "exit 0" in out


def test_branch_protection_fallback_pat() -> None:
    """`README_BOT_PAT || GITHUB_TOKEN` lets users opt into PAT auth
    when their main branch protection requires it."""
    out = _render_workflow()
    assert "secrets.README_BOT_PAT || secrets.GITHUB_TOKEN" in out


def test_pinned_tripwire_version_in_install_step() -> None:
    """The workflow installs the same tripwire version the project was
    init'd with, so renders are reproducible after an upgrade."""
    out = _render_workflow(tripwire_version="0.7.9")
    assert "tripwire-pm>=0.7.9" in out


def test_bot_identity_set_before_commit() -> None:
    out = _render_workflow()
    assert "tripwire-bot" in out
    assert "tripwire-bot@users.noreply.github.com" in out


def test_triggers_only_on_push_to_main() -> None:
    out = _render_workflow()
    parsed = yaml.safe_load(out)
    # PyYAML may parse `on` as True; access by both possible keys.
    on_block = parsed.get("on") or parsed.get(True)
    assert on_block is not None, "workflow has no `on:` trigger block"
    assert on_block.get("push", {}).get("branches") == ["main"]
    # Crucially, NOT triggered on pull_request — those run against PR HEAD,
    # not the post-merge state, so the README would lag the actual project.
    assert "pull_request" not in on_block
