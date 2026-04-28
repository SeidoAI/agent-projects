import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useGraphLayout } from "@/features/graph/useGraphLayout";
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
