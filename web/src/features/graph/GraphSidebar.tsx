import { ChevronDown, ChevronRight, PanelLeftClose } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import type { ReactFlowGraph, ReactFlowNode } from "@/lib/api/endpoints/graph";
import { cn } from "@/lib/utils";

/**
 * Left rail of the Concept Graph (KUI-104, spec §3.5).
 *
 * Outline tree of concepts grouped by `type` (model / decision /
 * service / …). Issues are excluded — this rail is concepts-only;
 * the canvas handles cross-entity overview. The currently-focused
 * concept is highlighted with `aria-current="true"`.
 *
 * PM #25 round 2:
 * - Owns its own scroll (P1) — `overflow-y-auto` + `min-h-0` so the
 *   sidebar's content doesn't share scroll with the canvas.
 * - Categories are collapsible (P2), with a count chip on each
 *   header and a small color square keyed to the kind token (P2).
 *   Default state: category containing the selected node is
 *   expanded; everything else collapsed when the graph has more
 *   than 6 categories, otherwise everything starts expanded.
 */
export interface GraphSidebarProps {
  graph: ReactFlowGraph;
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** Optional — caller may omit when the sidebar is non-collapsible. */
  onCollapse?: () => void;
}

interface ConceptEntry {
  id: string;
  label: string;
  type: string;
}

/** Kind → token. Mirrors the tones used by `<Stamp>` so the
 *  sidebar/rail/canvas trio share one visual vocabulary. */
const KIND_COLOR: Record<string, string> = {
  schema: "var(--color-info)",
  service: "var(--color-info)",
  endpoint: "var(--color-gate)",
  contract: "var(--color-gate)",
  decision: "var(--color-tripwire)",
  requirement: "var(--color-rule)",
  model: "var(--color-ink)",
  custom: "var(--color-ink-2)",
};

/** Above this many distinct categories, the sidebar collapses
 *  every category except the one holding the current selection
 *  (or all if nothing is selected). Six fits one ~900px viewport
 *  before scrolling kicks in; lower thresholds get loud, higher
 *  ones lose their reason to collapse. */
export const CATEGORY_COLLAPSE_THRESHOLD = 6;

export function colorForKind(kind: string): string {
  return KIND_COLOR[kind] ?? "var(--color-ink-2)";
}

export function GraphSidebar({ graph, selectedId, onSelect, onCollapse }: GraphSidebarProps) {
  const grouped = useMemo(() => groupConcepts(graph.nodes), [graph.nodes]);

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    const collapseAll = grouped.length > CATEGORY_COLLAPSE_THRESHOLD;
    const selectedKind = selectedId
      ? grouped.find(([, list]) => list.some((e) => e.id === selectedId))?.[0]
      : undefined;
    for (const [type] of grouped) {
      initial[type] = collapseAll && type !== selectedKind;
    }
    return initial;
  });

  const toggle = (type: string) => setCollapsed((prev) => ({ ...prev, [type]: !prev[type] }));

  return (
    <aside
      data-testid="graph-sidebar"
      // Independent scroll container per PM #25 round 2 P1: the
      // `min-h-0` is what lets the grid row honour overflow-y; the
      // outer `<div>` in `ConceptGraph` uses `grid-rows-[…minmax(0,1fr)]`
      // for the same reason.
      className="flex w-60 shrink-0 flex-col gap-3 overflow-y-auto border-(--color-edge) border-r bg-(--color-paper-2) px-4 py-4"
    >
      <div className="flex items-center justify-between">
        <h3 className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
          concepts · {graph.meta.node_count}
        </h3>
        <Button variant="ghost" size="icon" onClick={onCollapse} aria-label="Collapse panel">
          <PanelLeftClose className="h-4 w-4" />
        </Button>
      </div>
      {grouped.length === 0 ? (
        <p className="font-serif text-[13px] italic text-(--color-ink-3)">no concepts yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {grouped.map(([type, entries]) => {
            const isCollapsed = collapsed[type];
            const Caret = isCollapsed ? ChevronRight : ChevronDown;
            return (
              <li key={type} className="flex flex-col gap-1">
                <button
                  type="button"
                  onClick={() => toggle(type)}
                  aria-expanded={!isCollapsed}
                  className="flex w-full items-center gap-2 rounded-(--radius-stamp) px-1 py-0.5 text-left transition-colors hover:bg-(--color-paper-3)"
                >
                  <Caret className="h-3 w-3 shrink-0 text-(--color-ink-3)" aria-hidden />
                  <span
                    aria-hidden
                    data-testid={`graph-sidebar-color-${type}`}
                    className="inline-block h-2.5 w-2.5 shrink-0 rounded-(--radius-stamp)"
                    style={{ backgroundColor: colorForKind(type) }}
                  />
                  <span className="flex-1 font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
                    {type}
                  </span>
                  <span
                    data-testid={`graph-sidebar-count-${type}`}
                    className="font-mono text-[10px] text-(--color-ink-3) tabular-nums tracking-[0.04em]"
                  >
                    {entries.length}
                  </span>
                </button>
                {isCollapsed ? null : (
                  <ul className="flex flex-col gap-0.5 pl-5">
                    {entries.map((entry) => {
                      const active = entry.id === selectedId;
                      return (
                        <li key={entry.id}>
                          <button
                            type="button"
                            onClick={() => onSelect(entry.id)}
                            aria-current={active ? "true" : undefined}
                            className={cn(
                              "block w-full truncate rounded-(--radius-stamp) px-2 py-1 text-left",
                              "font-sans text-[12px] leading-tight transition-colors",
                              active
                                ? "bg-(--color-paper-3) text-(--color-ink)"
                                : "text-(--color-ink-2) hover:bg-(--color-paper-3) hover:text-(--color-ink)",
                            )}
                          >
                            {entry.label}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}

function groupConcepts(nodes: ReactFlowNode[]): Array<[string, ConceptEntry[]]> {
  const buckets = new Map<string, ConceptEntry[]>();
  for (const n of nodes) {
    if (n.type !== "concept") continue;
    const t = String(n.data?.type ?? "concept");
    const label = String(n.data?.label ?? n.id);
    if (!buckets.has(t)) buckets.set(t, []);
    buckets.get(t)?.push({ id: n.id, label, type: t });
  }
  const out: Array<[string, ConceptEntry[]]> = [];
  for (const [t, list] of buckets) {
    list.sort((a, b) => a.label.localeCompare(b.label));
    out.push([t, list]);
  }
  out.sort((a, b) => a[0].localeCompare(b[0]));
  return out;
}
