import {
  Background,
  Controls,
  type Edge,
  MiniMap,
  type Node,
  type NodeTypes,
  ReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { Skeleton } from "@/components/ui/skeleton";
import type { ReactFlowEdge, ReactFlowNode } from "@/lib/api/endpoints/graph";
import { cn } from "@/lib/utils";
import { ConceptNode } from "./ConceptNode";
import { useConceptGraph } from "./hooks/useGraph";

const nodeTypes: NodeTypes = {
  concept: ConceptNode,
  issue: ConceptNode,
};

const RELATION_STYLES: Record<string, { stroke: string; dashArray?: string; label: string }> = {
  blocked_by: { stroke: "#ef4444", label: "blocks" },
  references: { stroke: "#6366f1", dashArray: "4 3", label: "refs" },
  related: { stroke: "#a3a3a3", dashArray: "2 4", label: "related" },
  parent: { stroke: "#22c55e", label: "parent" },
};

function mapNode(n: ReactFlowNode): Node {
  // React Flow expects `type` to key `nodeTypes`; our backend sends
  // node-category strings (e.g. "issue", "concept") that we register
  // above. Unknown types fall back to "concept" so they still render.
  const type = nodeTypes[n.type] ? n.type : "concept";
  return {
    id: n.id,
    type,
    position: n.position,
    data: n.data,
  };
}

function mapEdge(e: ReactFlowEdge): Edge {
  const style = RELATION_STYLES[e.relation] ?? { stroke: "#6b7280", label: e.relation };
  return {
    id: e.id,
    source: e.source,
    target: e.target,
    style: { stroke: style.stroke, strokeDasharray: style.dashArray },
    data: { ...e.data, relation: e.relation },
    label: style.label,
    labelStyle: { fill: style.stroke, fontSize: 10 },
    labelBgPadding: [2, 2],
    labelBgStyle: { fill: "var(--background)", opacity: 0.85 },
  };
}

export function ConceptGraph() {
  return (
    <ReactFlowProvider>
      <ConceptGraphInner />
    </ReactFlowProvider>
  );
}

function ConceptGraphInner() {
  const { projectId } = useProjectShell();
  const navigate = useNavigate();
  const { data, isLoading, isError } = useConceptGraph(projectId);
  // `null` means "user hasn't touched the filter yet — treat as all".
  // Picking a sentinel instead of a mount-time effect avoids a first-
  // paint flash of zero nodes while the effect waits to run.
  const [activeTypes, setActiveTypes] = useState<Set<string> | null>(null);

  const availableTypes = useMemo(() => {
    if (!data) return [] as string[];
    const seen = new Set<string>();
    for (const n of data.nodes) seen.add(n.type);
    return Array.from(seen).sort();
  }, [data]);

  // The effective set drives both filtering and aria-pressed so the
  // two can't disagree. Before the first toggle, it's every type;
  // after, it's exactly what the user has selected.
  const effectiveActive = useMemo<Set<string>>(
    () => activeTypes ?? new Set(availableTypes),
    [activeTypes, availableTypes],
  );

  const filteredNodes = useMemo(() => {
    if (!data) return [] as Node[];
    return data.nodes.filter((n) => effectiveActive.has(n.type)).map(mapNode);
  }, [data, effectiveActive]);

  const filteredEdges = useMemo(() => {
    if (!data) return [] as Edge[];
    // Drop any edge whose endpoints got filtered out — React Flow
    // otherwise throws a warning for each dangling edge.
    const visibleIds = new Set(filteredNodes.map((n) => n.id));
    return data.edges
      .filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target))
      .map(mapEdge);
  }, [data, filteredNodes]);

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
      // First toggle: base off the "all types" view the user actually sees.
      const base = prev ?? new Set(availableTypes);
      const next = new Set(base);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  };

  const onNodeClick = (_: unknown, node: Node) => {
    // Route back to the detail view. Issue-type nodes go to the issue
    // detail path; everything else goes to the node detail path.
    const isIssue = /^[A-Z][A-Z0-9]*-\d+$/.test(node.id);
    navigate(isIssue ? `/p/${projectId}/issues/${node.id}` : `/p/${projectId}/nodes/${node.id}`);
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
      <div className="flex-1" data-testid="concept-graph-canvas">
        <ReactFlow
          nodes={filteredNodes}
          edges={filteredEdges}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background />
          <MiniMap pannable zoomable />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}
