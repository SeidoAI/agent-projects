"""Aggregate routing telemetry rows by (provider, model, effort, task_kind).

Produces ``$/merged-PR`` per route plus sample size + total cost. Manual
interpretation today; auto-tuning the routing table is a future task.
Routes with zero merged sessions report ``cost_per_merged_pr`` as
``None`` rather than infinity so JSON output stays consumable.

The CLI wrapper at ``cli/session.py:session_analyze_routing_cmd`` calls
:func:`aggregate_routes` then either dumps JSON or hands the payload to
:func:`render_routing_table` for Rich-formatted output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.table import Table


@dataclass
class _RouteAgg:
    provider: str
    model: str
    effort: str
    task_kind: str | None
    n: int = 0
    merged: int = 0
    total_cost_usd: float = 0.0
    total_duration_min: int = 0
    re_engages: int = 0
    ci_failures: int = 0


def aggregate_routes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bucket telemetry rows by route key and compute per-route metrics.

    Returns a list of route dicts sorted by ``cost_per_merged_pr``
    (``None`` values last). Each row includes provider/model/effort/
    task_kind, sample counts, total + per-merged cost, average duration,
    and totals for re-engages and CI failures.
    """
    agg: dict[tuple, _RouteAgg] = {}
    for r in rows:
        key = (
            r.get("provider", "claude"),
            r.get("model", "opus"),
            r.get("effort", "xhigh"),
            r.get("task_kind"),
        )
        if key not in agg:
            agg[key] = _RouteAgg(
                provider=key[0], model=key[1], effort=key[2], task_kind=key[3]
            )
        bucket = agg[key]
        bucket.n += 1
        if r.get("merged"):
            bucket.merged += 1
        bucket.total_cost_usd += float(r.get("cost_usd") or 0.0)
        bucket.total_duration_min += int(r.get("duration_min") or 0)
        bucket.re_engages += int(r.get("re_engages") or 0)
        bucket.ci_failures += int(r.get("ci_failures") or 0)

    routes_payload: list[dict[str, Any]] = []
    for bucket in agg.values():
        cost_per_merged = (
            bucket.total_cost_usd / bucket.merged if bucket.merged else None
        )
        routes_payload.append(
            {
                "provider": bucket.provider,
                "model": bucket.model,
                "effort": bucket.effort,
                "task_kind": bucket.task_kind,
                "n": bucket.n,
                "merged": bucket.merged,
                "total_cost_usd": round(bucket.total_cost_usd, 4),
                "cost_per_merged_pr": (
                    round(cost_per_merged, 4) if cost_per_merged is not None else None
                ),
                "avg_duration_min": (
                    round(bucket.total_duration_min / bucket.n, 1) if bucket.n else 0.0
                ),
                "total_re_engages": bucket.re_engages,
                "total_ci_failures": bucket.ci_failures,
            }
        )

    routes_payload.sort(
        key=lambda x: (x["cost_per_merged_pr"] is None, x["cost_per_merged_pr"] or 0)
    )
    return routes_payload


def render_routing_table(
    routes_payload: list[dict[str, Any]], console: Console
) -> None:
    """Render aggregated routes as a Rich table on *console*.

    Empty payload prints a "no telemetry yet" line and returns.
    """
    if not routes_payload:
        console.print("No routing telemetry yet. Run a session through to completion.")
        return

    table = Table(title="Routing analysis", show_header=True)
    table.add_column("provider")
    table.add_column("model")
    table.add_column("effort")
    table.add_column("task_kind")
    table.add_column("n", justify="right")
    table.add_column("merged", justify="right")
    table.add_column("$/merged", justify="right")
    table.add_column("avg dur", justify="right")
    table.add_column("re-eng", justify="right")
    for r in routes_payload:
        table.add_row(
            r["provider"],
            r["model"],
            r["effort"],
            r["task_kind"] or "—",
            str(r["n"]),
            str(r["merged"]),
            (
                f"${r['cost_per_merged_pr']:.2f}"
                if r["cost_per_merged_pr"] is not None
                else "—"
            ),
            f"{r['avg_duration_min']:.1f}m",
            str(r["total_re_engages"]),
        )
    console.print(table)
