"""Per-project concept-drift allowlist loader.

Lives at `<project_dir>/lint/concept-allowlist.yaml`. Schema:

    allowlist:
      - term: "Stripe"
        reason: "Why this isn't a node."
      - term: "JSON"
        reason: "..."

The `reason` field is required — silent suppression isn't allowed; the
operator (or a future maintainer) should be able to read each entry and
tell why it's there. Missing file means empty allowlist (the file is
opt-in).
"""

from __future__ import annotations

from pathlib import Path

import yaml


class AllowlistError(ValueError):
    """Raised when the allowlist file is malformed."""


_ALLOWLIST_REL = Path("lint") / "concept-allowlist.yaml"


def load_concept_allowlist(project_dir: Path) -> set[str]:
    """Return the lower-cased terms in the project's concept-drift allowlist.

    Missing file → empty set. Malformed entries (missing `term`, missing
    or blank `reason`, non-mapping root) raise `AllowlistError`.
    """
    path = project_dir / _ALLOWLIST_REL
    if not path.exists():
        return set()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return set()
    if not isinstance(raw, dict):
        raise AllowlistError(
            f"{path}: top level must be a mapping with an `allowlist:` key"
        )

    entries = raw.get("allowlist") or []
    if not isinstance(entries, list):
        raise AllowlistError(f"{path}: `allowlist` must be a list")

    terms: set[str] = set()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise AllowlistError(f"{path}: entry #{i + 1} must be a mapping")
        term = entry.get("term")
        reason = entry.get("reason")
        if not term or not isinstance(term, str):
            raise AllowlistError(f"{path}: entry #{i + 1} is missing required `term`")
        if not reason or not isinstance(reason, str) or not reason.strip():
            raise AllowlistError(
                f"{path}: entry #{i + 1} ({term!r}) is missing required "
                f"non-empty `reason`"
            )
        terms.add(term.strip().lower())

    return terms
