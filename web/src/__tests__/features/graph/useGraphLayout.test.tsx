import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { __test__, useGraphLayout } from "@/features/graph/useGraphLayout";
import type { ReactFlowEdge, ReactFlowNode } from "@/lib/api/endpoints/graph";

function node(id: string, x = 0, y = 0, hasSaved = false): ReactFlowNode {
  return {
    id,
    type: "concept",
    position: { x, y },
    data: hasSaved ? { has_saved_layout: true } : {},
  };
}

function edge(source: string, target: string): ReactFlowEdge {
  return { id: `${source}-${target}`, source, target, relation: "related", data: {} };
}

describe("useGraphLayout", () => {
  it("returns the supplied position verbatim when every node has a saved layout", () => {
    const nodes = [node("a", 100, 200, true), node("b", -50, 75, true)];
    const edges = [edge("a", "b")];
    const { result } = renderHook(() => useGraphLayout({ nodes, edges, width: 1000, height: 600 }));
    expect(result.current.positions.a).toEqual({ x: 100, y: 200 });
    expect(result.current.positions.b).toEqual({ x: -50, y: 75 });
    expect(result.current.didSeed).toBe(false);
  });

  it("seeds positions for nodes without a saved layout", async () => {
    const nodes = [node("a"), node("b"), node("c")];
    const edges = [edge("a", "b"), edge("b", "c")];
    const { result } = renderHook(() => useGraphLayout({ nodes, edges, width: 1000, height: 600 }));
    await waitFor(() => {
      expect(result.current.didSeed).toBe(true);
    });
    // Every node has a finite position after seeding.
    for (const id of ["a", "b", "c"]) {
      const p = result.current.positions[id];
      expect(p).toBeDefined();
      if (!p) continue;
      expect(Number.isFinite(p.x)).toBe(true);
      expect(Number.isFinite(p.y)).toBe(true);
    }
    // d3-force places connected nodes at distinct points.
    const a = result.current.positions.a;
    const b = result.current.positions.b;
    expect(a).toBeDefined();
    expect(b).toBeDefined();
    if (a && b) {
      expect(a.x !== b.x || a.y !== b.y).toBe(true);
    }
  });

  it("uses saved positions and seeds only the unsaved ones", async () => {
    const nodes = [node("a", 50, 50, true), node("b"), node("c")];
    const edges = [edge("a", "b"), edge("b", "c")];
    const { result } = renderHook(() => useGraphLayout({ nodes, edges, width: 1000, height: 600 }));
    await waitFor(() => {
      expect(result.current.didSeed).toBe(true);
    });
    expect(result.current.positions.a).toEqual({ x: 50, y: 50 });
    expect(result.current.positions.b).toBeDefined();
    expect(result.current.positions.c).toBeDefined();
  });

  it("emits seeded positions via newLayouts so the caller can persist", async () => {
    const nodes = [node("a"), node("b")];
    const edges = [edge("a", "b")];
    const { result } = renderHook(() => useGraphLayout({ nodes, edges, width: 800, height: 400 }));
    await waitFor(() => {
      expect(result.current.didSeed).toBe(true);
    });
    expect(Object.keys(result.current.newLayouts).sort()).toEqual(["a", "b"]);
  });

  it("refreshes positions when saved coordinates change for the same node ids (PM #25 round 4 P2)", () => {
    // Regression: seedKey identity-aware fix in round 3 used node
    // ids but omitted coordinates. If the backend returns the same
    // node ids + topology with NEW saved positions (e.g. another
    // user dragged the node, or a cleanup repositioned things),
    // `lastSeedRef` short-circuited and `positions` kept the old
    // coordinates. Including a coordinate hash in seedKey makes
    // the effect re-run on coordinate changes.
    const before = [node("alpha", 100, 100, true), node("beta", 200, 200, true)];
    const after = [node("alpha", 500, 500, true), node("beta", 200, 200, true)];
    const { result, rerender } = renderHook(
      ({ nodes }: { nodes: ReactFlowNode[] }) =>
        useGraphLayout({ nodes, edges: [], width: 1000, height: 600 }),
      { initialProps: { nodes: before } },
    );
    expect(result.current.positions.alpha).toEqual({ x: 100, y: 100 });

    rerender({ nodes: after });
    expect(result.current.positions.alpha).toEqual({ x: 500, y: 500 });
    expect(result.current.positions.beta).toEqual({ x: 200, y: 200 });
  });

  it("seeds unsaved nodes near a related saved neighbour, not on the central ring", () => {
    // Regression for the bulk-import "everything piles in the centre"
    // symptom. Old seeding placed every unsaved node on a single ring
    // around the canvas centre; with many siblings of one saved node,
    // d3-force couldn't unbunch them because the saved node was
    // pinned. Smart placement seeds unsaved nodes adjacent to a
    // placed neighbour so the simulation starts from a sensible
    // configuration. We assert on the SEED (deterministic) — the
    // d3-force pass after is refinement and exercised by other tests.
    const SAVED = node("anchor", 300, 300, true);
    const SIBLINGS = Array.from({ length: 6 }, (_, i) => node(`sib-${i}`));
    const seeds = __test__.seedSimNodes(
      [SAVED, ...SIBLINGS],
      SIBLINGS.map((n) => edge("anchor", n.id)),
      2000,
      1200,
    );
    const seedById: Record<string, (typeof seeds)[number]> = Object.fromEntries(
      seeds.map((s) => [s.id, s]),
    );
    // Anchor stays pinned at its saved position.
    expect(seedById.anchor?.fx).toBe(300);
    expect(seedById.anchor?.fy).toBe(300);
    // Every sibling seeded within ~250px of the anchor — well inside
    // the "near a related neighbour" guarantee.
    for (const sib of SIBLINGS) {
      const s = seedById[sib.id];
      expect(s).toBeDefined();
      if (!s) continue;
      const dx = s.x - 300;
      const dy = s.y - 300;
      expect(Math.sqrt(dx * dx + dy * dy)).toBeLessThan(250);
    }
    // Siblings don't pile on a single point.
    const points = new Set(
      SIBLINGS.map((n) => {
        const s = seedById[n.id];
        return s ? `${s.x.toFixed(1)},${s.y.toFixed(1)}` : "";
      }),
    );
    expect(points.size).toBe(SIBLINGS.length);
  });

  it("falls back to outer ring for orphan nodes (no path to any placed neighbour)", () => {
    // Two disconnected components: A is fully unsaved (no anchor),
    // B is the same. Every node is an orphan, so all should land on
    // the outer ring spread out — none piled at the centre.
    const orphans = Array.from({ length: 8 }, (_, i) => node(`o-${i}`));
    const seeds = __test__.seedSimNodes(orphans, [], 2000, 1200);
    const seedById: Record<string, (typeof seeds)[number]> = Object.fromEntries(
      seeds.map((s) => [s.id, s]),
    );
    const cx = 1000;
    const cy = 600;
    const expectedRadius = Math.min(2000, 1200) / 2; // 600
    for (const o of orphans) {
      const s = seedById[o.id];
      expect(s).toBeDefined();
      if (!s) continue;
      const dx = s.x - cx;
      const dy = s.y - cy;
      const dist = Math.sqrt(dx * dx + dy * dy);
      // Should be on the outer ring, NOT bunched at centre.
      expect(dist).toBeGreaterThan(expectedRadius * 0.95);
      expect(dist).toBeLessThan(expectedRadius * 1.05);
    }
  });

  it("re-seeds when reseedNonce changes (Auto-arrange button)", async () => {
    const nodes = [node("a", 100, 100, true), node("b"), node("c")];
    const edges = [edge("a", "b"), edge("a", "c")];
    let nonce = 0;
    const { result, rerender } = renderHook(
      ({ reseedNonce }: { reseedNonce: number }) =>
        useGraphLayout({ nodes, edges, width: 1000, height: 600, reseedNonce }),
      { initialProps: { reseedNonce: nonce } },
    );
    await waitFor(() => {
      expect(result.current.didSeed).toBe(true);
    });
    // Capture the current newLayouts payload so we can assert the
    // reseed produced one.
    const beforeKeys = Object.keys(result.current.newLayouts).sort();
    expect(beforeKeys).toEqual(["b", "c"]);

    nonce += 1;
    rerender({ reseedNonce: nonce });
    await waitFor(() => {
      // After reseed, didSeed should still be true and newLayouts
      // should still contain entries for both unsaved nodes.
      expect(Object.keys(result.current.newLayouts).sort()).toEqual(["b", "c"]);
    });
  });

  it("refreshes positions when saved-node ids swap with same length + topology (PM #25 round 3 P2)", () => {
    // Regression: seedKey was built from `nodes.length`, the
    // unsaved-id list, and edge topology. Two all-saved fixtures
    // with the same length + (empty) topology and different ids
    // produced identical seedKey → effect short-circuited →
    // positions stayed pointing at the OLD ids and the NEW nodes
    // had no entry in `positions`. Including all node ids in the
    // seedKey identity restores the refresh.
    const fixtureA = [node("alpha", 10, 20, true), node("beta", 30, 40, true)];
    const fixtureB = [node("gamma", 50, 60, true), node("delta", 70, 80, true)];
    const { result, rerender } = renderHook(
      ({ nodes }: { nodes: ReactFlowNode[] }) =>
        useGraphLayout({ nodes, edges: [], width: 1000, height: 600 }),
      { initialProps: { nodes: fixtureA } },
    );
    expect(result.current.positions.alpha).toEqual({ x: 10, y: 20 });
    expect(result.current.positions.beta).toEqual({ x: 30, y: 40 });

    // Same length, same (empty) topology, different ids.
    rerender({ nodes: fixtureB });
    expect(result.current.positions.gamma).toEqual({ x: 50, y: 60 });
    expect(result.current.positions.delta).toEqual({ x: 70, y: 80 });
    // Old ids no longer in positions.
    expect(result.current.positions.alpha).toBeUndefined();
    expect(result.current.positions.beta).toBeUndefined();
  });
});
