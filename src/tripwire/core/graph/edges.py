"""Per-edge-kind directionality semantics (KUI-134 / A9).

Every canonical edge kind in the v0.9 unified entity graph has either
a bidirectional rule (`refs`) or a named inverse that the unified
facade surfaces at read time. The inverse is never stored on disk —
we keep the same convention as the existing `blocked_by` ↔ `blocks`
pair, where `blocks` is computed from the inverse of `blocked_by` and
re-emitted as a derived field.

Inverse names per kind:

| Kind                 | Inverse           | Bidirectional? |
| -------------------- | ----------------- | -------------- |
| ``refs``             | ``refs``          | yes            |
| ``depends_on``       | ``blocks``        | no             |
| ``implements``       | ``implemented-by``| no             |
| ``produced-by``      | ``produces``      | no             |
| ``supersedes``       | ``superseded-by`` | no             |
| ``addressed-by``     | ``addresses``     | no             |
| ``tripwire-fired-on``| ``fired-tripwires``| no            |

Unknown kinds pass through unchanged (forward-compat).
"""

from __future__ import annotations

from tripwire.models.graph import EdgeKind

# Forward (canonical name) → inverse (display name). Bidirectional
# kinds use their own name as the inverse.
_INVERSE: dict[str, str] = {
    EdgeKind.REFS.value: EdgeKind.REFS.value,
    EdgeKind.DEPENDS_ON.value: "blocks",
    EdgeKind.IMPLEMENTS.value: "implemented-by",
    EdgeKind.PRODUCED_BY.value: "produces",
    EdgeKind.SUPERSEDES.value: "superseded-by",
    EdgeKind.ADDRESSED_BY.value: "addresses",
    EdgeKind.TRIPWIRE_FIRED_ON.value: "fired-tripwires",
}

# inverse → forward, computed from _INVERSE so the round-trip
# `inverse_kind(inverse_kind(x))` is idempotent for every kind.
_FORWARD: dict[str, str] = {v: k for k, v in _INVERSE.items()}

_BIDIRECTIONAL: frozenset[str] = frozenset({EdgeKind.REFS.value})


def inverse_kind(kind: str) -> str:
    """Return the inverse-direction name for a canonical edge kind.

    For bidirectional kinds (``refs``), returns the same kind back.
    For unknown kinds, returns the input unchanged (forward-compat:
    a stale agent that ships a new kind doesn't poison every read).
    """
    if kind in _INVERSE:
        return _INVERSE[kind]
    if kind in _FORWARD:
        # Already an inverse — round-tripping returns the canonical form.
        return _FORWARD[kind]
    return kind


def is_bidirectional(kind: str) -> bool:
    """True if `kind` is a bidirectional edge (currently only ``refs``)."""
    return kind in _BIDIRECTIONAL


def canonical_for_inverse(inverse_name: str) -> str:
    """Return the forward canonical kind whose inverse matches `inverse_name`.

    Used by the unified-index facade to translate "give me everything
    that blocks X" into "give me every depends_on edge into X".
    Unknown names pass through unchanged.
    """
    return _FORWARD.get(inverse_name, inverse_name)


__all__ = [
    "canonical_for_inverse",
    "inverse_kind",
    "is_bidirectional",
]
