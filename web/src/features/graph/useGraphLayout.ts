import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
} from "d3-force";
import { useEffect, useMemo, useRef, useState } from "react";

import type { ReactFlowEdge, ReactFlowNode } from "@/lib/api/endpoints/graph";

export interface Vec2 {
  x: number;
  y: number;
}

export interface UseGraphLayoutInput {
  nodes: ReactFlowNode[];
  edges: ReactFlowEdge[];
  width: number;
  height: number;
}

export interface UseGraphLayoutResult {
  /** Final position per node id (saved + seeded). */
  positions: Record<string, Vec2>;
  /** Positions newly seeded this run — what the caller persists to YAML. */
  newLayouts: Record<string, Vec2>;
  /** True once the simulation has settled. */
  didSeed: boolean;
}

interface SimNode {
  id: string;
  x: number;
  y: number;
  fx?: number | null;
  fy?: number | null;
}

interface SimLink {
  source: string;
  target: string;
}

const SIM_ITERATIONS = 400;
const NODE_R = 22;
const MIN_PAD = 12;

/**
 * Hand-rolled SVG canvas position seeding for the Concept Graph (KUI-104).
 *
 * Per `[[dec-drop-xyflow-for-svg]]`, we run d3-force in-process to
 * place nodes that arrive without a `data.has_saved_layout` flag,
 * pin nodes that DO have one to their server-supplied (x, y), then
 * step the simulation to convergence and write the resting positions
 * back to YAML via {@link useLayoutPersistence}.
 *
 * Returns the per-node positions plus a `newLayouts` map of just the
 * nodes that were freshly seeded — the caller persists those and
 * leaves saved layouts alone.
 */
export function useGraphLayout({
  nodes,
  edges,
  width,
  height,
}: UseGraphLayoutInput): UseGraphLayoutResult {
  const [positions, setPositions] = useState<Record<string, Vec2>>(() => initialPositions(nodes));
  const [didSeed, setDidSeed] = useState<boolean>(false);
  const [newLayouts, setNewLayouts] = useState<Record<string, Vec2>>({});

  // Identity of the input that triggers a re-seed. Includes EVERY
  // node id (saved + unsaved), each saved node's (x, y), and the
  // edge topology — so a refresh fires whenever any of those
  // change. PM #25 round 3 P2 added the id list (caught
  // same-length / same-topology id swaps); PM #25 round 4 P2 adds
  // the coordinate component (catches the case where a refetch
  // returns the same ids/topology with different saved positions,
  // e.g. another user dragged a node).
  const seedKey = useMemo(() => {
    const allIds = nodes
      .map((n) => {
        const tag = n.data?.has_saved_layout ? "s" : "u";
        // Include saved coordinates so coord-only changes still
        // trigger a re-seed. Coordinates for unsaved nodes are
        // re-derived by the seed effect itself, so they don't
        // need to participate in the key.
        const coords = n.data?.has_saved_layout ? `@${n.position.x},${n.position.y}` : "";
        return `${n.id}:${tag}${coords}`;
      })
      .sort()
      .join(",");
    const topology = edges
      .map((e) => `${e.source}>${e.target}`)
      .sort()
      .join(",");
    return `${allIds}|${topology}|${width}|${height}`;
  }, [nodes, edges, width, height]);

  const lastSeedRef = useRef<string | null>(null);

  useEffect(() => {
    if (lastSeedRef.current === seedKey) return;
    lastSeedRef.current = seedKey;

    const unsaved = nodes.filter((n) => !n.data?.has_saved_layout);
    if (unsaved.length === 0) {
      // Every node already has a saved layout; nothing to seed.
      setPositions(initialPositions(nodes));
      setNewLayouts({});
      setDidSeed(false);
      return;
    }

    const cx = width / 2;
    const cy = height / 2;
    const r = Math.min(width, height) / 3;
    const simNodes: SimNode[] = nodes.map((n, i) => {
      const saved = Boolean(n.data?.has_saved_layout);
      if (saved) {
        return { id: n.id, x: n.position.x, y: n.position.y, fx: n.position.x, fy: n.position.y };
      }
      // Seed unsaved nodes on a deterministic ring around the centre
      // so the simulation has something to spread out.
      const a = (i / nodes.length) * Math.PI * 2;
      return {
        id: n.id,
        x: cx + Math.cos(a) * r,
        y: cy + Math.sin(a) * r,
      };
    });
    const simLinks: SimLink[] = edges.map((e) => ({ source: e.source, target: e.target }));

    const sim = forceSimulation<SimNode>(simNodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(simLinks)
          .id((n) => n.id)
          .distance(120)
          .strength(0.4),
      )
      .force("charge", forceManyBody().strength(-280))
      .force("center", forceCenter(cx, cy).strength(0.05))
      .force("x", forceX(cx).strength(0.04))
      .force("y", forceY(cy).strength(0.04))
      .force(
        "collide",
        forceCollide<SimNode>(NODE_R + MIN_PAD)
          .strength(1)
          .iterations(4),
      )
      .stop();

    for (let i = 0; i < SIM_ITERATIONS; i += 1) sim.tick();

    const next: Record<string, Vec2> = {};
    const seeded: Record<string, Vec2> = {};
    for (const n of simNodes) {
      const x = Number.isFinite(n.x) ? n.x : cx;
      const y = Number.isFinite(n.y) ? n.y : cy;
      next[n.id] = { x, y };
      const original = nodes.find((node) => node.id === n.id);
      if (!original?.data?.has_saved_layout) {
        seeded[n.id] = { x, y };
      }
    }
    setPositions(next);
    setNewLayouts(seeded);
    setDidSeed(true);
  }, [nodes, edges, width, height, seedKey]);

  return { positions, newLayouts, didSeed };
}

function initialPositions(nodes: ReactFlowNode[]): Record<string, Vec2> {
  const out: Record<string, Vec2> = {};
  for (const n of nodes) {
    out[n.id] = { x: n.position.x, y: n.position.y };
  }
  return out;
}
