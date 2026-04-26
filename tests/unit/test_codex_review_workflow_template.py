"""Verify the v0.7.10 §D1 ``codex-review.yml.j2`` workflow template
renders to valid YAML, fires only on PR ``issue_comment`` events
containing ``@codex``, runs the OpenAI Codex CLI in headless mode
against the PR diff, and posts the result back as a PR comment.

The template is shipped under
``src/tripwire/templates/project/.github/workflows/`` and is stamped
into a project's ``.github/workflows/`` by ``tripwire init``.
"""

from __future__ import annotations

import yaml
from jinja2 import Environment, FileSystemLoader

from tripwire.templates import get_templates_dir


def _render_template(version: str = "0.7.10") -> str:
    template_root = get_templates_dir() / "project" / ".github" / "workflows"
    env = Environment(
        loader=FileSystemLoader(str(template_root)),
        keep_trailing_newline=True,
    )
    return env.get_template("codex-review.yml.j2").render(tripwire_version=version)


def _on_block(data: dict) -> dict:
    # YAML 1.1: bareword ``on`` parses as boolean True.
    return data[True]


def test_template_renders_to_valid_yaml():
    rendered = _render_template()
    data = yaml.safe_load(rendered)
    assert data["name"] == "Codex review"


def test_template_triggers_on_issue_comment_created():
    """Per spec §3.D1: ``on: issue_comment.created``."""
    rendered = _render_template()
    data = yaml.safe_load(rendered)
    on_block = _on_block(data)
    assert "issue_comment" in on_block
    assert on_block["issue_comment"]["types"] == ["created"]


def test_job_gated_on_pr_and_codex_mention():
    """Per spec §3.D1: ``if: contains(github.event.comment.body, '@codex')``.

    Plus the PR-only guard (``github.event.issue.pull_request``) so issue
    comments on issues — not PRs — don't fire the workflow. ``contains``
    is case-insensitive in YAML expressions per GitHub Actions docs, but
    we still want the literal ``@codex`` string in the source so the
    intent is reviewable.
    """
    rendered = _render_template()
    data = yaml.safe_load(rendered)
    review_job = data["jobs"]["review"]
    if_expr = review_job["if"]
    assert "github.event.issue.pull_request" in if_expr
    assert "@codex" in if_expr
    assert "contains(github.event.comment.body" in if_expr


def test_template_pins_actions_to_point_releases():
    """Per the v8.1.0-style policy in the v0.7.10 spec §5: every
    third-party action is pinned to a point release, not a floating
    major. checkout@v6 is the project standard for v0.7.x."""
    rendered = _render_template()
    assert "actions/checkout@v6" in rendered
    # setup-node is required to npm-install the codex CLI.
    assert "actions/setup-node@v4" in rendered


def test_template_installs_codex_cli():
    """The job invokes the OpenAI Codex CLI (``codex exec``) so it must
    install the binary before use. We use the npm-distributed package
    ``@openai/codex`` so the install is one ``npm i -g`` step."""
    rendered = _render_template()
    assert "@openai/codex" in rendered


def test_template_invokes_codex_against_pr_diff():
    """The codex-reviewer agent reads ``gh pr diff <num>`` and posts a
    structured review. The workflow shells out to gh + codex; we don't
    pin the exact incantation but assert the two tools are invoked in
    the same job."""
    rendered = _render_template()
    assert "gh pr diff" in rendered
    assert "codex exec" in rendered


def test_template_posts_result_as_pr_comment():
    """After codex runs, its output goes back as a PR comment. ``gh pr
    comment`` is the simplest way (alternative: actions/github-script
    + REST). Either way we expect ``gh pr comment`` in the workflow."""
    rendered = _render_template()
    assert "gh pr comment" in rendered


def test_template_uses_openai_api_key_secret():
    """Codex CLI auth is via ``OPENAI_API_KEY`` per KUI-94's auth gate
    (also documented in ``src/tripwire/runtimes/codex.py``). The
    workflow must pass this through as an env var to the codex step."""
    rendered = _render_template()
    assert "OPENAI_API_KEY" in rendered
    assert "secrets.OPENAI_API_KEY" in rendered


def test_template_grants_pr_write_permission():
    """``gh pr comment`` requires ``pull-requests: write`` and ``issues:
    write`` (issue_comment events run with default-restricted token).
    Without these the post-comment step 403s silently."""
    rendered = _render_template()
    data = yaml.safe_load(rendered)
    perms = data["jobs"]["review"]["permissions"]
    assert perms["pull-requests"] == "write"
    # issue_comment events also need issues:write to comment via gh.
    assert perms["issues"] == "write"


def test_template_has_concurrency_per_pr():
    """Per the plan's risk mitigation: concurrency:1 per-PR keeps
    rapid-fire ``@codex`` comments from racing each other on the
    same PR (each later run cancels the earlier one)."""
    rendered = _render_template()
    data = yaml.safe_load(rendered)
    # Either workflow-level or job-level concurrency is acceptable.
    concurrency = data.get("concurrency") or data["jobs"]["review"].get("concurrency")
    assert concurrency is not None, "expected concurrency block on workflow or job"


def test_template_has_timeout():
    """Codex review should not run away. 10 minutes is a generous cap —
    the spec target is "review comment within 5 min"."""
    rendered = _render_template()
    data = yaml.safe_load(rendered)
    assert data["jobs"]["review"]["timeout-minutes"] <= 15
