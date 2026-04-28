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
    const { result } = renderHook(() =>
      useGraphLayout({ nodes, edges, width: 1000, height: 600 }),
    );
    expect(result.current.positions["a"]).toEqual({ x: 100, y: 200 });
    expect(result.current.positions["b"]).toEqual({ x: -50, y: 75 });
    expect(result.current.didSeed).toBe(false);
  });

  it("seeds positions for nodes without a saved layout", async () => {
    const nodes = [node("a"), node("b"), node("c")];
    const edges = [edge("a", "b"), edge("b", "c")];
    const { result } = renderHook(() =>
      useGraphLayout({ nodes, edges, width: 1000, height: 600 }),
    );
    await waitFor(() => {
      expect(result.current.didSeed).toBe(true);
    });
    // Every node has a finite position after seeding.
    for (const id of ["a", "b", "c"]) {
      const p = result.current.positions[id];
      expect(p).toBeDefined();
      expect(Number.isFinite(p.x)).toBe(true);
      expect(Number.isFinite(p.y)).toBe(true);
    }
    // d3-force places connected nodes at distinct points.
    const a = result.current.positions["a"];
    const b = result.current.positions["b"];
    expect(a.x !== b.x || a.y !== b.y).toBe(true);
  });

  it("uses saved positions and seeds only the unsaved ones", async () => {
    const nodes = [node("a", 50, 50, true), node("b"), node("c")];
    const edges = [edge("a", "b"), edge("b", "c")];
    const { result } = renderHook(() =>
      useGraphLayout({ nodes, edges, width: 1000, height: 600 }),
    );
    await waitFor(() => {
      expect(result.current.didSeed).toBe(true);
    });
    expect(result.current.positions["a"]).toEqual({ x: 50, y: 50 });
    expect(result.current.positions["b"]).toBeDefined();
    expect(result.current.positions["c"]).toBeDefined();
  });

  it("emits seeded positions via newLayouts so the caller can persist", async () => {
    const nodes = [node("a"), node("b")];
    const edges = [edge("a", "b")];
    const { result } = renderHook(() =>
      useGraphLayout({ nodes, edges, width: 800, height: 400 }),
    );
    await waitFor(() => {
      expect(result.current.didSeed).toBe(true);
    });
    expect(Object.keys(result.current.newLayouts).sort()).toEqual(["a", "b"]);
  });
});
