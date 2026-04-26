import { useMemo, useState } from "react";

import { useProjectShell } from "@/app/ProjectShell";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useConceptGraph } from "./hooks/useGraph";

// S1 strips the @xyflow/react renderer so the dep can be removed from
// package.json (per dec-drop-xyflow-for-svg). The hand-rolled SVG
// rebuild lands in S4 (KUI-104). Until then we keep the data fetch,
// empty state, and type-filter legend rendering so the chrome that
// surrounds the canvas keeps working — only the canvas itself is
// replaced with a placeholder.
export function ConceptGraph() {
  const { projectId } = useProjectShell();
  const { data, isLoading, isError } = useConceptGraph(projectId);
  const [activeTypes, setActiveTypes] = useState<Set<string> | null>(null);

  const availableTypes = useMemo(() => {
    if (!data) return [] as string[];
    const seen = new Set<string>();
    for (const n of data.nodes) seen.add(n.type);
    return Array.from(seen).sort();
  }, [data]);

  const effectiveActive = useMemo<Set<string>>(
    () => activeTypes ?? new Set(availableTypes),
    [activeTypes, availableTypes],
  );

  if (isLoading) {
    return <Skeleton className="h-full w-full" />;
  }
  if (isError) {
    return (
      <div className="p-6 text-sm text-destructive">Couldn't load the graph. Try refreshing.</div>
    );
  }
  if (!data || data.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
        No concept nodes yet. Add one under <code>nodes/</code>.
      </div>
    );
  }

  const toggleType = (t: string) => {
    setActiveTypes((prev) => {
      const base = prev ?? new Set(availableTypes);
      const next = new Set(base);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  };

  return (
    <div className="flex h-full">
      <aside className="w-48 shrink-0 border-r bg-background p-3">
        <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Node types</h3>
        <ul className="space-y-1">
          {availableTypes.map((t) => {
            const active = effectiveActive.has(t);
            return (
              <li key={t}>
                <button
                  type="button"
                  onClick={() => toggleType(t)}
                  aria-pressed={active}
                  className={cn(
                    "w-full rounded px-2 py-1 text-left text-xs capitalize transition-colors",
                    active ? "bg-accent text-accent-foreground" : "text-muted-foreground",
                  )}
                >
                  {t}
                </button>
              </li>
            );
          })}
        </ul>
        <p className="mt-4 text-[11px] text-muted-foreground">
          {data.meta.node_count} nodes · {data.meta.edge_count} edges
        </p>
      </aside>
      <div
        className="flex flex-1 items-center justify-center p-6 text-sm text-muted-foreground"
        data-testid="concept-graph-canvas"
      >
        Concept graph canvas ships in S4 (KUI-104) — hand-rolled SVG with d3-force layout.
      </div>
    </div>
  );
}
