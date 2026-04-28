import { useMemo } from "react";
import type { ReactFlowGraph, ReactFlowNode } from "@/lib/api/endpoints/graph";
import { cn } from "@/lib/utils";

/**
 * Left rail of the Concept Graph (KUI-104, spec §3.5).
 *
 * Outline tree of concepts grouped by `type` (model / decision /
 * service / …). Issues are excluded — this rail is concepts-only;
 * the canvas handles cross-entity overview. The currently-focused
 * concept is highlighted with `aria-current="true"`.
 */
export interface GraphSidebarProps {
  graph: ReactFlowGraph;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

interface ConceptEntry {
  id: string;
  label: string;
  type: string;
}

export function GraphSidebar({ graph, selectedId, onSelect }: GraphSidebarProps) {
  const grouped = useMemo(() => groupConcepts(graph.nodes), [graph.nodes]);

  return (
    <aside
      data-testid="graph-sidebar"
      className="flex w-60 shrink-0 flex-col gap-4 border-(--color-edge) border-r bg-(--color-paper-2) px-4 py-4"
    >
      <h3 className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
        concepts · {graph.meta.node_count}
      </h3>
      {grouped.length === 0 ? (
        <p className="font-serif text-[13px] italic text-(--color-ink-3)">no concepts yet.</p>
      ) : (
        <ul className="flex flex-col gap-4">
          {grouped.map(([type, entries]) => (
            <li key={type} className="flex flex-col gap-1.5">
              <div className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
                {type}
              </div>
              <ul className="flex flex-col gap-0.5">
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
            </li>
          ))}
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
