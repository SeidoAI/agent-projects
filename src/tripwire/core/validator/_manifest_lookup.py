"""Shared manifest-lookup helpers for artifact-shaped validator rules.

Every rule that fires on a manifest-declared artifact (presence, coverage,
follow-up resolution, evidence content, etc.) consults the same metadata:
the entry's ``produced_at`` (when does it become required?) and
``owned_by`` (which actor authors and is therefore the addressee of any
fix-hint?). This module centralises both lookups so individual checks
read the manifest as authority rather than hand-rolling phase gates.

v0.11.1 introduced this pattern via a private ``_pm_response_produced_at``
helper in ``coherence.py``. v0.12 generalises it and adds the actor-prefix
companion.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from tripwire.models.manifest import ArtifactEntry

if TYPE_CHECKING:
    from tripwire.core.validator._types import ValidationContext


def artifact_entry(ctx: ValidationContext, name: str) -> ArtifactEntry | None:
    """Look up a manifest entry by ``name``.

    Returns the full ``ArtifactEntry`` (with ``file``, ``produced_at``,
    ``produced_by``, ``owned_by``, ``required``, ``approval_gate``) or
    ``None`` if the manifest is missing, fails to load, or doesn't
    declare an entry with that name.

    Callers should treat ``None`` as "skip this check entirely" — same
    fallback ``check_artifact_presence`` already uses for a missing
    manifest. Rules that declare their work against an artifact whose
    entry isn't in the project's manifest are deliberately silent rather
    than firing on a phantom assumption.
    """
    from tripwire.core.validator.checks._helpers import _load_manifest

    manifest, _ = _load_manifest(ctx)
    if manifest is None:
        return None
    return next((e for e in manifest.artifacts if e.name == name), None)


_ARTIFACT_PHASE_TO_SESSION_STATUS: dict[str, str] = {
    "planning": "queued",
}
"""Maps artifact_phase enum values to the session_status threshold at
which a `produced_at: <phase>` artifact must exist.

The artifact manifest's ``produced_at`` field uses the
``artifact_phase`` enum (planning / executing / in_review / verified /
completed). The session lifecycle uses the ``session_status`` enum
(planned / queued / executing / in_review / verified / completed +
side states). Three of the four lifecycle phases share the same name
in both enums (executing, in_review, verified, completed) and need no
translation. Only ``planning`` is asymmetric — it's the project-level
work the PM does before queueing the session, so the corresponding
session status is ``queued`` (the artifact must exist by the time the
session is queued for the agent).
"""


def phase_to_session_status(phase: str) -> str:
    """Translate an artifact_phase value to its session_status threshold.

    Used by checks that gate on `entry.produced_at` against
    `session.status`. Pass the manifest's `produced_at` value through
    this before calling `status_at_or_past(..., enum_name="session_status")`.

    Returns the input unchanged for phases that exist in both enums.
    """
    return _ARTIFACT_PHASE_TO_SESSION_STATUS.get(phase, phase)


def find_artifact_on_disk(session_dir: Path, file: str) -> Path | None:
    """Locate a session artifact by filename, checking both layouts.

    Real-world tripwire projects write artifacts to two different
    locations depending on age and authoring path:

    - ``sessions/<sid>/<file>`` — the layout most agents and most
      coherence checks expect (e.g. self-review.md, pm-response.yaml).
    - ``sessions/<sid>/artifacts/<file>`` — the layout
      `paths.session_artifacts_dir()` constructs and some UI services
      use.

    To avoid false-positive `artifact/missing` errors for files that
    exist in the "wrong" location, we check both. Returns the first
    location that contains the file, or ``None`` if neither does.
    """
    direct = session_dir / file
    if direct.is_file():
        return direct
    nested = session_dir / "artifacts" / file
    if nested.is_file():
        return nested
    return None


def actor_prefix(entry: ArtifactEntry | None) -> str:
    """Return the fix-hint prefix that identifies the actor responsible
    for an artifact-shaped rule's finding.

    Reads ``entry.owned_by`` and maps it to a self-identifying prefix:

    - ``pm`` → ``"PM action — "``
    - any agent type (``execution-agent``, ``verification-agent``,
      ``planning-agent``, ``backend-coder``, ``frontend-coder``, etc.)
      → ``"Agent action — "``
    - explicit ``"either"`` or unknown values → ``"Either action — "``
    - ``None`` (no entry to consult, or rule isn't artifact-shaped)
      → empty string (no prefix; cross-entity invariants don't carry
      a single addressee).

    Hint copy is read out of context (logs, screenshots, copy-paste).
    A self-identifying prefix lets a future reader know who's expected
    to act without needing the surrounding rule definition.
    """
    if entry is None:
        return ""
    owned_by = (entry.owned_by or "").strip().lower()
    if owned_by == "pm":
        return "PM action — "
    if owned_by == "either":
        return "Either action — "
    if owned_by == "" or owned_by == "unknown":
        return "Either action — "
    return "Agent action — "
