"""Per-session cost computation (KUI-96 §E2).

Public surface for turning a stream-json log produced by ``claude -p``
into a :class:`CostBreakdown` of US dollars by token category. Used by
``tripwire session cost``, the ``Cost`` column in ``session list``, the
UI session detail, and (transitively, by importing the same helpers)
the in-flight runtime monitor.

Pricing comes from ``src/tripwire/data/anthropic_pricing.yaml``. The
file ships with the package and is refreshed manually — there is no
public Anthropic pricing API to poll. Match strategy is the longest
substring of ``message.model`` that appears in the ``models:`` map; if
nothing matches, the conservative ``default:`` rates apply.

Why a dedicated module: the in-flight monitor already had pricing
helpers, but they were private to ``runtimes/monitor.py`` and only
counted *cumulative* cost during a live spawn. CLI and UI need to
compute cost from a finished log on disk, with a per-category
breakdown the user can read. Hoisting the pricing primitives here
keeps a single source of truth — the monitor delegates to this
module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# ---------- Pricing -------------------------------------------------------


_PRICING_PATH = Path(__file__).parent.parent / "data" / "anthropic_pricing.yaml"


@dataclass(frozen=True)
class ModelRates:
    """USD per million tokens, by category, for a single model."""

    input: float
    output: float
    cache_read: float
    cache_write: float


_pricing_cache: dict[str, ModelRates] | None = None
_default_rates_cache: ModelRates | None = None


def load_pricing() -> tuple[dict[str, ModelRates], ModelRates]:
    """Read ``anthropic_pricing.yaml`` once and memoise.

    Returns ``(models, default_rates)``. Tests that mutate the cache
    (e.g. fixture pricing) can clear it via :func:`reset_pricing_cache`.
    """
    global _pricing_cache, _default_rates_cache
    if _pricing_cache is not None and _default_rates_cache is not None:
        return _pricing_cache, _default_rates_cache
    raw = yaml.safe_load(_PRICING_PATH.read_text(encoding="utf-8"))
    models = {
        name: ModelRates(**rates) for name, rates in (raw.get("models") or {}).items()
    }
    default = ModelRates(**raw["default"])
    _pricing_cache = models
    _default_rates_cache = default
    return models, default


def reset_pricing_cache() -> None:
    """Clear the memoised pricing tables (test seam)."""
    global _pricing_cache, _default_rates_cache
    _pricing_cache = None
    _default_rates_cache = None


def rate_for(model_name: str) -> ModelRates:
    """Pick the longest-key prefix match for ``model_name``, else default."""
    models, default = load_pricing()
    matches = [k for k in models if k in model_name]
    if not matches:
        return default
    best = max(matches, key=len)
    return models[best]


def cost_for_usage(model_name: str, usage: dict[str, Any]) -> float:
    """Compute USD cost for a single ``usage`` payload from one event."""
    rates = rate_for(model_name)
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    crd = int(usage.get("cache_read_input_tokens") or 0)
    cwr = int(usage.get("cache_creation_input_tokens") or 0)
    return (
        inp * rates.input
        + out * rates.output
        + crd * rates.cache_read
        + cwr * rates.cache_write
    ) / 1_000_000


# ---------- CostBreakdown -------------------------------------------------


@dataclass
class CostBreakdown:
    """Per-token-category cost for one session, plus total."""

    input_usd: float = 0.0
    output_usd: float = 0.0
    cache_read_usd: float = 0.0
    cache_write_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    # Each event's model is recorded so the report can flag the
    # mixed-model case (e.g. fallback-model kicked in mid-session).
    models_used: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.models_used is None:
            self.models_used = []

    @property
    def total_usd(self) -> float:
        return (
            self.input_usd
            + self.output_usd
            + self.cache_read_usd
            + self.cache_write_usd
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_usd": self.input_usd,
            "output_usd": self.output_usd,
            "cache_read_usd": self.cache_read_usd,
            "cache_write_usd": self.cache_write_usd,
            "total_usd": self.total_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "models_used": list(self.models_used),
        }


# ---------- Compute from a stream-json log --------------------------------


def _accumulate_event(
    event: dict[str, Any], breakdown: CostBreakdown, fallback_model: str
) -> None:
    """Update ``breakdown`` in place from one ``assistant`` event.

    Non-assistant events and events with no ``usage`` payload are
    silently ignored — the result event also carries usage but it is
    cumulative-style and would double-count if added.
    """
    if event.get("type") != "assistant":
        return
    message = event.get("message") or {}
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return

    model = message.get("model") or fallback_model
    rates = rate_for(model)

    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    crd = int(usage.get("cache_read_input_tokens") or 0)
    cwr = int(usage.get("cache_creation_input_tokens") or 0)

    breakdown.input_tokens += inp
    breakdown.output_tokens += out
    breakdown.cache_read_tokens += crd
    breakdown.cache_write_tokens += cwr

    breakdown.input_usd += inp * rates.input / 1_000_000
    breakdown.output_usd += out * rates.output / 1_000_000
    breakdown.cache_read_usd += crd * rates.cache_read / 1_000_000
    breakdown.cache_write_usd += cwr * rates.cache_write / 1_000_000

    if model not in breakdown.models_used:
        breakdown.models_used.append(model)


def compute_cost_from_log(
    log_path: Path,
    *,
    fallback_model: str = "claude-opus-4-7",
) -> CostBreakdown:
    """Walk a stream-json log and return its full :class:`CostBreakdown`.

    Missing files yield a zero breakdown rather than raising — the
    caller (CLI, UI service) does not want to crash on a session that
    was never spawned. Malformed JSON lines are skipped.
    """
    breakdown = CostBreakdown()
    if not log_path.is_file():
        return breakdown

    for raw in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        _accumulate_event(event, breakdown, fallback_model)

    return breakdown


def compute_session_cost(
    project_dir: Path,
    session_id: str,
    *,
    fallback_model: str = "claude-opus-4-7",
) -> CostBreakdown:
    """Resolve a session-id to its persisted log path and compute cost.

    Returns a zero breakdown if the session has no recorded
    ``runtime_state.log_path`` (never spawned, or state was cleared by
    ``tripwire session cleanup``).
    """
    from tripwire.core.session_store import load_session

    session = load_session(project_dir, session_id)
    log_path_str = session.runtime_state.log_path
    if not log_path_str:
        return CostBreakdown()
    log_path = Path(log_path_str).expanduser()
    return compute_cost_from_log(log_path, fallback_model=fallback_model)


__all__ = [
    "CostBreakdown",
    "ModelRates",
    "compute_cost_from_log",
    "compute_session_cost",
    "cost_for_usage",
    "load_pricing",
    "rate_for",
    "reset_pricing_cache",
]
