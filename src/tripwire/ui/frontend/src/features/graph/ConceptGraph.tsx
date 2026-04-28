import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { useProjectShell } from "@/app/ProjectShell";
import { Skeleton } from "@/components/ui/skeleton";
import type { ReactFlowNode } from "@/lib/api/endpoints/graph";
import { type InboxItem, useInbox } from "@/lib/api/endpoints/inbox";
import { cn } from "@/lib/utils";
import { GraphLegend } from "./GraphLegend";
import { GraphRail } from "./GraphRail";
import { GraphSidebar } from "./GraphSidebar";
import { useConceptGraph } from "./hooks/useGraph";
import { useGraphLayout } from "./useGraphLayout";
import { useLayoutPersistence } from "./useLayoutPersistence";

const DEFAULT_CANVAS = { width: 1000, height: 600 };
const NODE_RADIUS = 22;
const NODE_RADIUS_SMALL = 16;

/**
 * Concept Graph screen (KUI-104, spec §3.5 + amendments).
 *
 * Replaces the placeholder canvas left over from KUI-101. Hand-rolled
 * SVG per `[[dec-drop-xyflow-for-svg]]`: ledger-grid background,
 * `<line>` edges (solid for cites / dashed for related), `<circle>`
 * nodes with stale-amber dashed stroke + cross-link badge for inbox
 * referrers, and a `[[concept]]` rail mirroring the
 * EntityPreviewDrawer chrome.
 *
 * Positions come from `useGraphLayout`: nodes with a server-side
 * `data.has_saved_layout` are pinned to their stored `(x, y)`; the
 * rest are seeded by d3-force and PATCHed back to YAML via
 * `useLayoutPersistence` so reloads don't re-shuffle.
 */
export function ConceptGraph() {
  const { projectId } = useProjectShell();
  const { data, isLoading, isError } = useConceptGraph(projectId);
  const { data: inbox } = useInbox(projectId);
  const persistence = useLayoutPersistence(projectId);
  const [focus, setFocus] = useState<string | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState(DEFAULT_CANVAS);

  // Track canvas size so the d3-force seeding centres in the
  // visible area instead of the default 1000×600 viewBox.
  useLayoutEffect(() => {
    const el = canvasRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) {
        setSize({ width: Math.round(width), height: Math.round(height) });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const concepts = useMemo<ReactFlowNode[]>(
    () => (data?.nodes ?? []).filter((n) => n.type === "concept"),
    [data?.nodes],
  );

  const layout = useGraphLayout({
    nodes: concepts,
    edges: data?.edges ?? [],
    width: size.width,
    height: size.height,
  });

  // Persist any newly-seeded positions back to YAML so the next
  // reload reads them and skips d3-force entirely.
  useEffect(() => {
    const seeded = layout.newLayouts;
    if (Object.keys(seeded).length === 0) return;
    persistence.persist(seeded);
  }, [layout.newLayouts, persistence]);

  const inboxByNode = useMemo(() => indexInboxByNode(inbox ?? []), [inbox]);
  const neighbours = useMemo(() => {
    if (!focus || !data) return new Set<string>();
    const out = new Set<string>();
    for (const e of data.edges) {
      if (e.source === focus) out.add(e.target);
      else if (e.target === focus) out.add(e.source);
    }
    return out;
  }, [focus, data]);

  if (isLoading) {
    return <Skeleton className="h-full w-full" />;
  }
  if (isError) {
    return (
      <div className="p-6 font-serif text-[14px] italic text-(--color-ink-3)">
        Couldn't load the graph. Try refreshing.
      </div>
    );
  }
  if (!data || data.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6 font-serif text-[14px] italic text-(--color-ink-3)">
        No concept nodes yet. Add one under <code className="font-mono">nodes/</code>.
      </div>
    );
  }

  const focusedNode = focus ? (concepts.find((n) => n.id === focus) ?? null) : null;
  const incidentEdges =
    focusedNode && data
      ? data.edges.filter((e) => e.source === focusedNode.id || e.target === focusedNode.id)
      : [];

  return (
    <div className="grid h-full grid-rows-[auto_1fr] grid-cols-[240px_1fr_320px] bg-(--color-paper) text-(--color-ink)">
      <header className="col-span-3 border-(--color-edge) border-b px-7 py-4">
        <div className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
          chapter 05 · concept graph
        </div>
        <h1 className="mt-1 font-sans font-semibold text-[30px] text-(--color-ink) leading-[1.1] tracking-[-0.02em]">
          What this project is made of.
        </h1>
        <p className="mt-1 font-serif text-[14.5px] italic text-(--color-ink-2)">
          Every concept the team has named, who cites it, and how fresh it is.
        </p>
      </header>

      <GraphSidebar graph={data} selectedId={focus} onSelect={setFocus} />

      <section
        ref={canvasRef}
        data-testid="concept-graph-canvas"
        className="relative overflow-hidden bg-(--color-paper-2)"
      >
        <svg
          role="img"
          aria-label="Concept graph canvas"
          className="absolute inset-0 h-full w-full"
          viewBox={`0 0 ${size.width} ${size.height}`}
          preserveAspectRatio="xMidYMid meet"
        >
          <title>Concept graph canvas</title>
          <defs>
            <pattern id="concept-graph-ledger" width={40} height={40} patternUnits="userSpaceOnUse">
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke="var(--color-paper-3)"
                strokeWidth={0.5}
              />
            </pattern>
          </defs>
          <rect width={size.width} height={size.height} fill="url(#concept-graph-ledger)" />

          {/* edges */}
          {data.edges.map((edge) => {
            const a = layout.positions[edge.source];
            const b = layout.positions[edge.target];
            if (!a || !b) return null;
            const isFocused = focus !== null && (edge.source === focus || edge.target === focus);
            const dashed = edge.relation !== "cites";
            return (
              <line
                key={edge.id}
                data-edge-relation={edge.relation}
                data-edge-focused={isFocused ? "true" : "false"}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={isFocused ? "var(--color-rule)" : "var(--color-edge)"}
                strokeWidth={isFocused ? 1.4 : 0.7}
                strokeDasharray={dashed ? "3 3" : "0"}
                opacity={focus !== null && !isFocused ? 0.3 : 0.85}
              />
            );
          })}

          {/* nodes */}
          {concepts.map((node) => {
            const pos = layout.positions[node.id];
            if (!pos) return null;
            const isFocus = node.id === focus;
            const isNeighbour = neighbours.has(node.id);
            const dim = focus !== null && !isFocus && !isNeighbour;
            const stale = node.data?.status === "stale";
            const r = NODE_RADIUS;
            const inboxCount = inboxByNode.get(node.id)?.length ?? 0;
            return (
              // biome-ignore lint/a11y/useSemanticElements: HTML <button> isn't a valid SVG child; role="button" on a <g> is the standard pattern for interactive SVG groups
              <g
                key={node.id}
                role="button"
                tabIndex={0}
                aria-label={`Focus ${String(node.data?.label ?? node.id)}`}
                data-testid={`node-group-${node.id}`}
                data-focus={isFocus ? "true" : "false"}
                data-dim={dim ? "true" : "false"}
                opacity={dim ? 0.35 : 1}
                style={{ cursor: "pointer", transition: "opacity 200ms ease" }}
                onClick={() => setFocus(node.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setFocus(node.id);
                  }
                }}
              >
                <circle
                  data-testid={`node-circle-${node.id}`}
                  data-stale={stale ? "true" : "false"}
                  cx={pos.x}
                  cy={pos.y}
                  r={r}
                  fill={isFocus ? "var(--color-ink)" : "var(--color-paper-2)"}
                  stroke={stale ? "#c8861f" : "var(--color-ink)"}
                  strokeWidth={isFocus ? 2.2 : stale ? 1.6 : 1.1}
                  strokeDasharray={stale ? "3 2" : "0"}
                />
                {isFocus ? (
                  <circle
                    cx={pos.x}
                    cy={pos.y}
                    r={r + 6}
                    fill="none"
                    stroke="var(--color-rule)"
                    strokeWidth={1}
                    strokeDasharray="3 3"
                  />
                ) : null}
                <text
                  x={pos.x}
                  y={pos.y + r + 12}
                  textAnchor="middle"
                  fontFamily="var(--font-sans)"
                  fontSize={11}
                  fontWeight={500}
                  fill={isFocus ? "var(--color-ink)" : "var(--color-ink-2)"}
                >
                  {String(node.data?.label ?? node.id)}
                </text>
                <text
                  x={pos.x}
                  y={pos.y + r + 24}
                  textAnchor="middle"
                  fontFamily="var(--font-mono)"
                  fontSize={8.5}
                  fill="var(--color-ink-3)"
                  letterSpacing={0.5}
                >
                  {String(node.data?.type ?? "concept")}
                </text>
                {inboxCount > 0 ? (
                  <g
                    data-testid={`inbox-badge-${node.id}`}
                    aria-label={`${inboxCount} inbox entries reference this concept`}
                  >
                    <circle
                      cx={pos.x + r - 4}
                      cy={pos.y - r + 4}
                      r={NODE_RADIUS_SMALL / 2}
                      fill="var(--color-rule)"
                      stroke="var(--color-paper-2)"
                      strokeWidth={1.4}
                    />
                    <text
                      x={pos.x + r - 4}
                      y={pos.y - r + 7}
                      textAnchor="middle"
                      fontFamily="var(--font-mono)"
                      fontSize={9}
                      fontWeight={600}
                      fill="var(--color-paper)"
                    >
                      {inboxCount > 9 ? "9+" : String(inboxCount)}
                    </text>
                  </g>
                ) : null}
              </g>
            );
          })}
        </svg>

        <GraphLegend />

        <div
          className={cn(
            "pointer-events-none absolute top-3 right-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) px-2 py-1",
            "font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]",
          )}
        >
          {data.meta.node_count} nodes · {data.meta.edge_count} edges
        </div>
      </section>

      <GraphRail
        projectId={projectId}
        node={focusedNode}
        incident={incidentEdges}
        allNodes={concepts}
        referencingInbox={focus ? (inboxByNode.get(focus) ?? []) : []}
        onSelectNeighbour={setFocus}
      />
    </div>
  );
}

function indexInboxByNode(items: InboxItem[]): Map<string, InboxItem[]> {
  const out = new Map<string, InboxItem[]>();
  for (const entry of items) {
    if (entry.resolved) continue;
    for (const ref of entry.references) {
      if ("node" in ref) {
        const list = out.get(ref.node) ?? [];
        list.push(entry);
        out.set(ref.node, list);
      }
    }
  }
  for (const list of out.values()) {
    list.sort((a, b) => b.created_at.localeCompare(a.created_at));
  }
  return out;
}
