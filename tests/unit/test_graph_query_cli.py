"""tripwire graph query — cross-type traversal CLI (KUI-133 / A8).

The unified-index facade powers a new `query upstream/downstream`
subcommand under `tripwire graph`. It reads the graph cache and
returns IDs of nodes connected through the canonical edge kinds.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from tripwire.cli.graph import graph_cmd
from tripwire.core.graph.cache import full_rebuild
from tripwire.core.store import save_issue, save_project
from tripwire.models import Issue, ProjectConfig, RepoEntry


def _seed(tmp_path: Path) -> None:
    save_project(
        tmp_path,
        ProjectConfig(
            name="t",
            key_prefix="TST",
            repos={"SeidoAI/test-repo": RepoEntry()},
            next_issue_number=1,
        ),
    )
    for key in ("TST-1", "TST-2"):
        issue = Issue(
            id=key,
            title=key,
            status="todo",
            priority="medium",
            executor="ai",
            verifier="required",
            blocked_by=["TST-1"] if key == "TST-2" else [],
        )
        save_issue(tmp_path, issue, update_cache=False)
    # Session that works on TST-1
    sdir = tmp_path / "sessions" / "session-foo"
    sdir.mkdir(parents=True)
    front = yaml.safe_dump(
        {"id": "session-foo", "name": "foo", "agent": "dev", "issues": ["TST-1"]},
        sort_keys=False,
    )
    (sdir / "session.yaml").write_text(f"---\n{front}---\n", encoding="utf-8")
    full_rebuild(tmp_path)


def test_query_downstream_returns_session_and_issue(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        graph_cmd,
        [
            "query",
            "downstream",
            "TST-1",
            "--project-dir",
            str(tmp_path),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    # Downstream of TST-1: TST-2 (depends_on), session-foo (refs).
    ids = set(payload["ids"])
    assert "TST-2" in ids
    assert "session-foo" in ids


def test_query_upstream_returns_blocker(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        graph_cmd,
        [
            "query",
            "upstream",
            "TST-2",
            "--project-dir",
            str(tmp_path),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    # TST-2 depends_on TST-1, so upstream of TST-2 includes TST-1.
    assert "TST-1" in set(payload["ids"])


def test_query_kind_filter(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    # Filter to refs only — TST-2's upstream via depends_on (TST-1) should
    # disappear when we restrict to refs.
    result = runner.invoke(
        graph_cmd,
        [
            "query",
            "upstream",
            "TST-2",
            "--project-dir",
            str(tmp_path),
            "--kind",
            "refs",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "TST-1" not in set(payload["ids"])


def test_render_subcommand_still_renders(tmp_path: Path) -> None:
    """Backwards compat: existing rendering moved to `graph render`."""
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        graph_cmd,
        [
            "render",
            "--project-dir",
            str(tmp_path),
            "--type",
            "deps",
            "--format",
            "mermaid",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "graph LR" in result.output


def test_bare_graph_invocation_still_renders(tmp_path: Path) -> None:
    """Backwards compat: `tripwire graph` (no subcommand) keeps rendering.

    Q2 in the plan says either a default subcommand or a literal
    `render` subcommand is acceptable; this asserts the default path
    keeps the existing call-site shape working.
    """
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        graph_cmd,
        [
            "--project-dir",
            str(tmp_path),
            "--type",
            "deps",
            "--format",
            "mermaid",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "graph LR" in result.output
