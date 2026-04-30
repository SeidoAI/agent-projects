"""KUI-148 (D6) — node_ratio lint.

Warn when the ratio (concept nodes ÷ active issues) falls outside the
band configured for the project's ``metadata.kind``. The default band
is intentionally wide (0.10 .. 5.0) so a passing project doesn't see
this warning at all; libraries / frameworks have a tighter band that
expects more nodes per issue.

The lint silences itself when a project has fewer than 5 active
issues — small projects produce too noisy a ratio.
"""

from pathlib import Path

import yaml

from tripwire.core.validator import load_context
from tripwire.core.validator.lint import node_ratio


def _set_kind(project_dir: Path, kind: str) -> None:
    cfg = yaml.safe_load((project_dir / "project.yaml").read_text())
    cfg.setdefault("metadata", {})["kind"] = kind
    (project_dir / "project.yaml").write_text(yaml.safe_dump(cfg))


def test_too_few_nodes_warns(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    # 10 active issues, 0 nodes → ratio 0 < 0.10 (default min) → warn.
    for n in range(10):
        save_test_issue(tmp_path_project, key=f"TMP-{n + 1}", status="in_progress")
    ctx = load_context(tmp_path_project)
    results = node_ratio.check(ctx)
    assert any(r.code == "node_ratio/below_band" for r in results)


def test_too_many_nodes_warns(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    # 5 active issues, 26 nodes → ratio 5.2 > 5.0 (default max) → warn.
    for n in range(5):
        save_test_issue(tmp_path_project, key=f"TMP-{n + 1}", status="in_progress")
    for n in range(26):
        save_test_node(tmp_path_project, node_id=f"node-{n}")
    ctx = load_context(tmp_path_project)
    results = node_ratio.check(ctx)
    assert any(r.code == "node_ratio/above_band" for r in results)


def test_in_band_no_warning(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    # 5 active issues, 5 nodes → ratio 1.0 — inside default band.
    for n in range(5):
        save_test_issue(tmp_path_project, key=f"TMP-{n + 1}", status="in_progress")
    for n in range(5):
        save_test_node(tmp_path_project, node_id=f"node-{n}")
    ctx = load_context(tmp_path_project)
    assert node_ratio.check(ctx) == []


def test_small_project_silent(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    """Fewer than 5 active issues — lint stays silent (avoids noise)."""
    save_test_issue(tmp_path_project, key="TMP-1", status="in_progress")
    ctx = load_context(tmp_path_project)
    assert node_ratio.check(ctx) == []


def test_library_kind_uses_tighter_band(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    """For kind=library the band is 0.5..10.0 — 0.4 ratio fires."""
    _set_kind(tmp_path_project, "library")
    for n in range(10):
        save_test_issue(tmp_path_project, key=f"TMP-{n + 1}", status="in_progress")
    for n in range(4):
        save_test_node(tmp_path_project, node_id=f"node-{n}")
    ctx = load_context(tmp_path_project)
    results = node_ratio.check(ctx)
    assert any(r.code == "node_ratio/below_band" for r in results)
