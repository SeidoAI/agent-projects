import { useMemo, useState } from "react";

import type { EnumValue } from "@/lib/api/endpoints/enums";
import type { IssueSummary } from "@/lib/api/endpoints/issues";
import { layoutLayeredDag, roundedOrthogonalPath } from "@/features/sessions/layeredDag";

export interface IssuesGraphViewProps {
  issues: IssueSummary[];
  /** Status enum values, ordered as displayed in the kanban. The
   *  array index drives the DAG row tie-break (earlier = higher up)
   *  and is the source of truth for the per-status colour swatch. */
  statusValues: EnumValue[];
  /** Fired when a node is clicked; the parent opens its preview drawer. */
  onNodeClick: (issue: IssueSummary) => void;
}

const NODE_W = 200;
const NODE_H = 56;
const FALLBACK_COLOR = "var(--color-ink-3)";

/**
 * Issues × Graph quadrant of the Board 2x2 matrix. Renders an issue
 * dependency graph: nodes are issues, edges flow from blocker
 * (`blocked_by`) into the dependent. Issues without blocked-by edges
 * sit on the leftmost layer alongside other "unblocked" work.
 *
 * Reuses the `layoutLayeredDag` primitive that already powers the
 * SessionFlow surface, so the layered routing and crossing-min are
 * the same. Status colour and ordering come from the project's
 * `issue_status` enum so the visual vocabulary matches the kanban.
 */
export function IssuesGraphView({ issues, statusValues, onNodeClick }: IssuesGraphViewProps) {
  const [focusId, setFocusId] = useState<string | null>(null);

  const issuesById = useMemo(() => {
    const m = new Map<string, IssueSummary>();
    for (const i of issues) m.set(i.id, i);
    return m;
  }, [issues]);

  const statusIndex = useMemo(() => {
    const m = new Map<string, number>();
    statusValues.forEach((v, idx) => m.set(v.value, idx));
    return m;
  }, [statusValues]);

  const colorForStatus = useMemo(() => {
    const m = new Map<string, string>();
    for (const v of statusValues) m.set(v.value, v.color ?? FALLBACK_COLOR);
    return m;
  }, [statusValues]);

  const layout = useMemo(() => {
    const visibleIds = new Set(issues.map((i) => i.id));
    const rawEdges = issues.flatMap((i) =>
      i.blocked_by
        .filter((b) => visibleIds.has(b))
        .map((b) => ({ source: b, target: i.id })),
    );
    // P1 from PR review: defend against `blocked_by` cycles. The
    // layered-DAG's layer-assignment loop terminates by ids.length
    // bound, but on a cycle the layer it picks is non-deterministic
    // and the rendered ordering claims a partial order that doesn't
    // exist. Drop the back-edges of any detected cycle and warn once
    // per session so the data error surfaces.
    const edges = stripCycles(rawEdges, issues.length);
    return layoutLayeredDag(
      {
        nodes: issues.map((i) => ({ id: i.id })),
        // blocker → blocked: same edge direction as SessionFlow.
        edges,
        statusOrderOf: (id) =>
          statusIndex.get(issuesById.get(id)?.status ?? "") ?? statusValues.length,
      },
      { nodeWidth: NODE_W, nodeHeight: NODE_H, layerStride: 280 },
    );
  }, [issues, issuesById, statusIndex, statusValues.length]);

  if (issues.length === 0) {
    return (
      <p
        data-testid="issues-graph-empty"
        className="px-1 py-4 font-serif text-[12px] text-(--color-ink-3) italic"
      >
        No issues match the current filters.
      </p>
    );
  }

  return (
    <div
      data-testid="issues-graph-view"
      className="relative max-h-[640px] overflow-auto rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2)"
    >
      <svg
        role="img"
        aria-label="Issue dependency graph"
        width={Math.max(layout.width, 600)}
        height={Math.max(layout.height, 240)}
        className="block"
      >
        <title>Issue dependency graph</title>
        <defs>
          <marker
            id="issues-graph-arrow"
            viewBox="0 0 10 10"
            refX="10"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto"
            markerUnits="userSpaceOnUse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" />
          </marker>
        </defs>

        <g data-layer="edges">
          {layout.edges.map((e) => {
            const sourceIssue = issuesById.get(e.source);
            const baseColor = sourceIssue
              ? (colorForStatus.get(sourceIssue.status) ?? FALLBACK_COLOR)
              : "var(--color-edge)";
            const isOnFocus = focusId !== null && (e.source === focusId || e.target === focusId);
            const stroke = isOnFocus ? "var(--color-rule)" : baseColor;
            const opacity = focusId !== null && !isOnFocus ? 0.18 : 0.85;
            return (
              <path
                key={`${e.source}->${e.target}`}
                d={roundedOrthogonalPath(e.points, 10)}
                fill="none"
                stroke={stroke}
                strokeWidth={isOnFocus ? 3.5 : 2.5}
                strokeLinejoin="round"
                strokeLinecap="round"
                opacity={opacity}
                markerEnd="url(#issues-graph-arrow)"
              />
            );
          })}
        </g>

        <g data-layer="nodes">
          {issues.map((issue) => {
            const pos = layout.positions[issue.id];
            if (!pos) return null;
            const color = colorForStatus.get(issue.status) ?? FALLBACK_COLOR;
            const isFocus = issue.id === focusId;
            const fillOpacity = isFocus ? 1 : 0.18;
            return (
              // biome-ignore lint/a11y/useSemanticElements: SVG <g role="button"> is the standard pattern.
              <g
                key={issue.id}
                role="button"
                tabIndex={0}
                aria-label={`Open issue ${issue.id}: ${issue.title}`}
                data-testid={`issues-graph-node-${issue.id}`}
                data-focus={isFocus ? "true" : "false"}
                transform={`translate(${pos.x - NODE_W / 2}, ${pos.y - NODE_H / 2})`}
                onClick={() => {
                  setFocusId(issue.id);
                  onNodeClick(issue);
                }}
                onKeyDown={(ev) => {
                  if (ev.key === "Enter" || ev.key === " ") {
                    ev.preventDefault();
                    setFocusId(issue.id);
                    onNodeClick(issue);
                  }
                }}
                style={{ cursor: "pointer", outline: "none" }}
              >
                <rect
                  width={NODE_W}
                  height={NODE_H}
                  rx={8}
                  fill={color}
                  fillOpacity={fillOpacity}
                  stroke={color}
                  strokeWidth={isFocus ? 2.4 : 1.4}
                />
                <text
                  x={12}
                  y={20}
                  fontFamily="var(--font-mono)"
                  fontSize={10}
                  fill="var(--color-ink-3)"
                  letterSpacing={0.5}
                >
                  {issue.id}
                </text>
                <text
                  x={12}
                  y={40}
                  fontFamily="var(--font-sans)"
                  fontSize={12}
                  fontWeight={600}
                  fill="var(--color-ink)"
                >
                  {truncate(issue.title, 26)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : `${s.slice(0, n - 1)}…`;
}

/**
 * Drop edges that participate in a cycle, preserving the rest. DFS
 * with a recursion-stack set; back-edges are the offending ones. On
 * the first detected cycle we emit a single console.warn so the
 * underlying data error surfaces in dev — without crashing the
 * page or silently lying about a partial order.
 *
 * Bounded by the issue count (also passed in for an explicit
 * iteration cap belt-and-braces against a malformed adjacency).
 */
export function stripCycles(
  edges: { source: string; target: string }[],
  nodeCount: number,
): { source: string; target: string }[] {
  if (edges.length === 0) return edges;
  const adjacency = new Map<string, string[]>();
  for (const e of edges) {
    let arr = adjacency.get(e.source);
    if (!arr) {
      arr = [];
      adjacency.set(e.source, arr);
    }
    arr.push(e.target);
  }

  const visited = new Set<string>();
  const onStack = new Set<string>();
  const dropEdges = new Set<string>();
  let warned = false;
  const edgeKey = (s: string, t: string) => `${s}->${t}`;

  // Iterative DFS so we don't blow the stack on long chains.
  const dfs = (root: string) => {
    const stack: { node: string; iter: Iterator<string> }[] = [];
    const enter = (node: string) => {
      visited.add(node);
      onStack.add(node);
      stack.push({ node, iter: (adjacency.get(node) ?? [])[Symbol.iterator]() });
    };
    enter(root);
    let safety = nodeCount * (edges.length + 1);
    while (stack.length > 0 && safety-- > 0) {
      const top = stack[stack.length - 1];
      if (!top) break;
      const next = top.iter.next();
      if (next.done) {
        onStack.delete(top.node);
        stack.pop();
        continue;
      }
      const child = next.value;
      if (onStack.has(child)) {
        // Back-edge → cycle.
        dropEdges.add(edgeKey(top.node, child));
        if (!warned) {
          // eslint-disable-next-line no-console
          console.warn(
            `IssuesGraphView: blocked_by cycle detected (back-edge ${top.node} → ${child}); ` +
              "rendering remaining edges. Fix the issue YAMLs to break the cycle.",
          );
          warned = true;
        }
        continue;
      }
      if (!visited.has(child)) enter(child);
    }
  };

  for (const start of adjacency.keys()) {
    if (!visited.has(start)) dfs(start);
  }

  if (dropEdges.size === 0) return edges;
  return edges.filter((e) => !dropEdges.has(edgeKey(e.source, e.target)));
}
