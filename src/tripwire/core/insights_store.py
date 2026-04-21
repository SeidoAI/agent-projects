"""Read/write sessions/<id>/insights.yaml and insights.rejected.yaml.

The execution agent writes `insights.yaml` with proposed node additions
or updates. The PM's complete-session workflow applies or rejects each
proposal; rejections are recorded in `insights.rejected.yaml` so the
decision trail survives even after the applied proposal is removed.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tripwire.core import paths
from tripwire.models.insights import InsightsFile


def insights_path(project_dir: Path, session_id: str) -> Path:
    return paths.session_dir(project_dir, session_id) / "insights.yaml"


def rejected_path(project_dir: Path, session_id: str) -> Path:
    return paths.session_dir(project_dir, session_id) / "insights.rejected.yaml"


def load_insights(project_dir: Path, session_id: str) -> InsightsFile:
    """Load `insights.yaml`; missing file → empty `InsightsFile()`."""
    p = insights_path(project_dir, session_id)
    if not p.is_file():
        return InsightsFile()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return InsightsFile.model_validate(data)


def save_insights(project_dir: Path, session_id: str, file: InsightsFile) -> None:
    """Write `insights.yaml`. Parent directory is created if missing."""
    p = insights_path(project_dir, session_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = file.model_dump(exclude_none=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def record_rejection(
    project_dir: Path, session_id: str, proposal_id: str, reason: str
) -> None:
    """Append a rejection entry to `insights.rejected.yaml`."""
    p = rejected_path(project_dir, session_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if p.is_file():
        existing = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    entries = existing.get("rejected") or []
    entries.append({"id": proposal_id, "reason": reason})
    existing["rejected"] = entries
    p.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")
