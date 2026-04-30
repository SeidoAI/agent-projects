"""tripwire node check --update — refresh content_hash + optional bump.

KUI-130 / A5. The `--update` flag has been pointed at by validator
fix-hints for several releases; v0.9 finally implements it. The flow:

1. ``tripwire node check --update <node>`` rewrites
   ``source.content_hash`` to match current content.
2. ``tripwire node check --update --bump-contract <node>`` additionally
   bumps ``version`` by 1 and sets ``contract_changed_at`` to the new
   version. PM uses this to mark a contract-change bump that
   invalidates pinned consumers.
3. Without ``--update``, the command is read-only (existing
   behaviour).
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.node import node_cmd
from tripwire.core.node_store import load_node, save_node
from tripwire.core.store import save_project
from tripwire.models import ConceptNode, NodeSource, ProjectConfig, RepoEntry


def _make_project_with_local_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    src = repo_dir / "src" / "auth.py"
    src.parent.mkdir(parents=True)
    src.write_text("def login(): pass\n", encoding="utf-8")

    proj = tmp_path / "proj"
    proj.mkdir()
    save_project(
        proj,
        ProjectConfig(
            name="t",
            key_prefix="TST",
            repos={"o/r": RepoEntry(local=str(repo_dir))},
            next_issue_number=1,
        ),
    )
    return proj, src


def _save_node_with_stale_hash(proj: Path) -> None:
    node = ConceptNode(
        id="auth-system",
        type="system",
        name="Auth",
        version=1,
        source=NodeSource(
            repo="o/r",
            path="src/auth.py",
            content_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        ),
    )
    save_node(proj, node, update_cache=False)


def test_update_refreshes_content_hash(tmp_path: Path) -> None:
    proj, _src = _make_project_with_local_repo(tmp_path)
    _save_node_with_stale_hash(proj)

    runner = CliRunner()
    result = runner.invoke(
        node_cmd,
        ["check", "auth-system", "--update", "--project-dir", str(proj)],
    )
    assert result.exit_code == 0, result.output

    refreshed = load_node(proj, "auth-system")
    assert refreshed.source is not None
    # Hash should no longer be the all-zero stub; should match the
    # actual file's sha256.
    assert refreshed.source.content_hash != (
        "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    )
    assert refreshed.source.content_hash.startswith("sha256:")
    # version unchanged when --bump-contract not passed
    assert refreshed.version == 1
    assert refreshed.contract_changed_at is None


def test_update_with_bump_contract_increments_version(tmp_path: Path) -> None:
    proj, _src = _make_project_with_local_repo(tmp_path)
    _save_node_with_stale_hash(proj)

    runner = CliRunner()
    result = runner.invoke(
        node_cmd,
        [
            "check",
            "auth-system",
            "--update",
            "--bump-contract",
            "--project-dir",
            str(proj),
        ],
    )
    assert result.exit_code == 0, result.output

    refreshed = load_node(proj, "auth-system")
    assert refreshed.version == 2
    assert refreshed.contract_changed_at == 2


def test_update_without_node_id_is_rejected(tmp_path: Path) -> None:
    """Mutation against every node at once is too dangerous to default to.

    `tripwire node check --update` without a node id should error out
    rather than silently rehashing every node in the project.
    """
    proj, _src = _make_project_with_local_repo(tmp_path)
    _save_node_with_stale_hash(proj)
    runner = CliRunner()
    result = runner.invoke(
        node_cmd,
        ["check", "--update", "--project-dir", str(proj)],
    )
    assert result.exit_code != 0
    assert "node" in result.output.lower()


def test_no_update_flag_is_read_only(tmp_path: Path) -> None:
    proj, _src = _make_project_with_local_repo(tmp_path)
    _save_node_with_stale_hash(proj)
    before = (proj / "nodes" / "auth-system.yaml").read_text(encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        node_cmd,
        ["check", "auth-system", "--project-dir", str(proj)],
    )
    # Read-only check — should not raise.
    assert result.exit_code == 0, result.output

    after = (proj / "nodes" / "auth-system.yaml").read_text(encoding="utf-8")
    assert before == after


def test_bump_contract_requires_update(tmp_path: Path) -> None:
    proj, _src = _make_project_with_local_repo(tmp_path)
    _save_node_with_stale_hash(proj)
    runner = CliRunner()
    result = runner.invoke(
        node_cmd,
        [
            "check",
            "auth-system",
            "--bump-contract",
            "--project-dir",
            str(proj),
        ],
    )
    assert result.exit_code != 0
    assert "update" in result.output.lower()
