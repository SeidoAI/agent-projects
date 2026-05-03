import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from "d3-force";
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
  /**
   * Bump to force a re-seed of unsaved nodes (used by the
   * "Auto-arrange" toolbar action). Any change in this number
   * invalidates the cached `seedKey` and re-runs the simulation.
   */
  reseedNonce?: number;
  /**
   * "unsaved" (default) — pin every saved-position node and only
   * seed/refine the unsaved ones. Normal load behaviour.
   *
   * "all" — un-pin every node, seed from current positions, and
   * let the simulation re-distribute everything. The caller
   * persists ALL post-simulation positions, not just unsaved ones.
   * Used by the "Re-layout all" mode of the Auto-arrange button
   * when there are no unsaved nodes.
   */
  reseedMode?: "unsaved" | "all";
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

const SIM_ITERATIONS = 600;
const NODE_R = 22;
const MIN_PAD = 12;

// d3-force tuning. PM #25 round 5: the original config (centre 0.05
// + forceX 0.04 + forceY 0.04 = 0.13 of centripetal pull, link
// distance 120, repulsion -280) bunched ~30 of 153 nodes inside a
// 200×200 px square at the centre and pushed weakly-connected
// outliers to >2.5σ distances. Removing forceX/Y (forceCenter
// already does what they did, twice over), raising repulsion to -500,
// and pushing link distance to 180 gives connected clusters room to
// breathe without drifting orphans further. SIM_ITERATIONS bumped
// 400 → 600 to absorb the larger search space.
const FORCE_CENTER_STRENGTH = 0.08;
const FORCE_LINK_DISTANCE = 180;
const FORCE_LINK_STRENGTH = 0.4;
const FORCE_CHARGE_STRENGTH = -500;

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
  reseedNonce = 0,
  reseedMode = "unsaved",
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
    return `${allIds}|${topology}|${width}|${height}|${reseedNonce}`;
  }, [nodes, edges, width, height, reseedNonce]);

  const lastSeedRef = useRef<string | null>(null);

  useEffect(() => {
    if (lastSeedRef.current === seedKey) return;
    lastSeedRef.current = seedKey;

    const unsaved = nodes.filter((n) => !n.data?.has_saved_layout);
    // In "unsaved" mode (default) we have nothing to do when every
    // node is already pinned. In "all" mode the user has explicitly
    // asked for a re-layout, so we run regardless.
    if (unsaved.length === 0 && reseedMode !== "all") {
      setPositions(initialPositions(nodes));
      setNewLayouts({});
      setDidSeed(false);
      return;
    }

    const cx = width / 2;
    const cy = height / 2;
    const simNodes: SimNode[] = seedSimNodes(nodes, edges, cx, cy, width, height, reseedMode);
    const simLinks: SimLink[] = edges.map((e) => ({ source: e.source, target: e.target }));

    const sim = forceSimulation<SimNode>(simNodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(simLinks)
          .id((n) => n.id)
          .distance(FORCE_LINK_DISTANCE)
          .strength(FORCE_LINK_STRENGTH),
      )
      .force("charge", forceManyBody().strength(FORCE_CHARGE_STRENGTH))
      .force("center", forceCenter(cx, cy).strength(FORCE_CENTER_STRENGTH))
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
      // In "all" mode the caller wants every post-simulation position
      // persisted (the user explicitly re-layouted, so we treat all
      // nodes as freshly seeded). Otherwise only nodes that lacked a
      // saved layout count as seeded.
      if (reseedMode === "all" || !original?.data?.has_saved_layout) {
        seeded[n.id] = { x, y };
      }
    }
    setPositions(next);
    setNewLayouts(seeded);
    setDidSeed(true);
  }, [nodes, edges, width, height, seedKey, reseedMode]);

  return { positions, newLayouts, didSeed };
}

// Exported for unit testing — the seed step is the deterministic
// part of layout. The d3-force pass after it is refinement; the
// quality of the seed is what we verify.
export const __test__ = {
  seedSimNodes: (
    nodes: ReactFlowNode[],
    edges: ReactFlowEdge[],
    width: number,
    height: number,
    mode: "unsaved" | "all" = "unsaved",
  ) => seedSimNodes(nodes, edges, width / 2, height / 2, width, height, mode),
};

function initialPositions(nodes: ReactFlowNode[]): Record<string, Vec2> {
  const out: Record<string, Vec2> = {};
  for (const n of nodes) {
    out[n.id] = { x: n.position.x, y: n.position.y };
  }
  return out;
}

// Eight unit vectors for the spiral-search offset pattern, ordered to
// reduce visual clustering when many siblings share one neighbour.
const OFFSET_DIRS: ReadonlyArray<readonly [number, number]> = [
  [1, 0],
  [0, 1],
  [-1, 0],
  [0, -1],
  [0.7071, 0.7071],
  [-0.7071, 0.7071],
  [-0.7071, -0.7071],
  [0.7071, -0.7071],
];

const NEIGHBOUR_BASE_OFFSET = NODE_R * 5; // ~110px from neighbour centre
const NEIGHBOUR_RING_STEP = NODE_R * 3; // expand by ~66px per ring on collision

/**
 * Seed positions for d3-force.
 *
 * Default mode (`"unsaved"`): saved nodes get pinned (`fx`, `fy`) to
 * their server position; unsaved nodes are placed near a connected
 * neighbour whose position is already known (saved or already-placed),
 * falling back to an outer ring for orphans whose neighbours aren't
 * placed.
 *
 * "all" mode: nothing is pinned. Saved positions are still used as
 * starting positions (so the simulation moves smoothly from the
 * current state) but every node is free to move. The caller persists
 * every post-simulation position. Used by the "Re-layout all" mode of
 * the Auto-arrange button.
 */
function seedSimNodes(
  nodes: ReactFlowNode[],
  edges: ReactFlowEdge[],
  cx: number,
  cy: number,
  width: number,
  height: number,
  mode: "unsaved" | "all" = "unsaved",
): SimNode[] {
  const adjacency = new Map<string, string[]>();
  for (const e of edges) {
    if (!adjacency.has(e.source)) adjacency.set(e.source, []);
    if (!adjacency.has(e.target)) adjacency.set(e.target, []);
    adjacency.get(e.source)!.push(e.target);
    adjacency.get(e.target)!.push(e.source);
  }

  const placed = new Map<string, Vec2>();
  const out: SimNode[] = [];

  // Pass 1 — record every saved node's position. In "unsaved" mode
  // we also pin (`fx`, `fy`); in "all" mode we just seed from the
  // current position so the simulation can move it.
  for (const n of nodes) {
    if (n.data?.has_saved_layout) {
      const pos = { x: n.position.x, y: n.position.y };
      placed.set(n.id, pos);
      const sim: SimNode = { id: n.id, x: pos.x, y: pos.y };
      if (mode === "unsaved") {
        sim.fx = pos.x;
        sim.fy = pos.y;
      }
      out.push(sim);
    }
  }

  // Pass 2 — place unsaved nodes near a placed neighbour where possible.
  // Multiple passes converge unsaved → unsaved chains (a node's
  // neighbour might itself be unsaved-but-just-placed in this run).
  const unsaved = nodes.filter((n) => !n.data?.has_saved_layout);
  const unplacedFallback: ReactFlowNode[] = [];
  let madeProgress = true;
  let remaining = unsaved.slice();
  while (madeProgress && remaining.length > 0) {
    madeProgress = false;
    const next: ReactFlowNode[] = [];
    for (const n of remaining) {
      const neighbours = adjacency.get(n.id) ?? [];
      const anchor = neighbours
        .map((id) => placed.get(id))
        .find((p): p is Vec2 => p !== undefined);
      if (!anchor) {
        next.push(n);
        continue;
      }
      const pos = pickNeighbourOffset(anchor, placed);
      placed.set(n.id, pos);
      out.push({ id: n.id, x: pos.x, y: pos.y });
      madeProgress = true;
    }
    remaining = next;
  }

  // Pass 3 — orphans (no path to any placed node). Spread on an outer
  // ring so the simulation can fan them out without bunching at the
  // centre. Skip every other slot for breathing room.
  unplacedFallback.push(...remaining);
  const orphanRadius = Math.min(width, height) / 2;
  const slots = Math.max(unplacedFallback.length * 2, 8);
  unplacedFallback.forEach((n, i) => {
    const a = ((i * 2) / slots) * Math.PI * 2;
    const x = cx + Math.cos(a) * orphanRadius;
    const y = cy + Math.sin(a) * orphanRadius;
    placed.set(n.id, { x, y });
    out.push({ id: n.id, x, y });
  });

  return out;
}

function pickNeighbourOffset(anchor: Vec2, placed: Map<string, Vec2>): Vec2 {
  const minDist = NODE_R + MIN_PAD;
  for (let ring = 0; ring < 6; ring += 1) {
    const radius = NEIGHBOUR_BASE_OFFSET + ring * NEIGHBOUR_RING_STEP;
    for (const [dx, dy] of OFFSET_DIRS) {
      const candidate = { x: anchor.x + dx * radius, y: anchor.y + dy * radius };
      let collides = false;
      for (const p of placed.values()) {
        const ddx = candidate.x - p.x;
        const ddy = candidate.y - p.y;
        if (ddx * ddx + ddy * ddy < minDist * minDist) {
          collides = true;
          break;
        }
      }
      if (!collides) return candidate;
    }
  }
  // Last-resort fallback: stack along +x; d3-force will untangle.
  return { x: anchor.x + NEIGHBOUR_BASE_OFFSET * 6, y: anchor.y };
}
