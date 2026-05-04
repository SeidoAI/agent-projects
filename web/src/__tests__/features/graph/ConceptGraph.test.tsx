import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConceptGraph } from "@/features/graph/ConceptGraph";
import type { ReactFlowGraph } from "@/lib/api/endpoints/graph";
import type { NodeDetail } from "@/lib/api/endpoints/nodes";
import { queryKeys } from "@/lib/api/queryKeys";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

vi.mock("@/lib/api/endpoints/inbox", () => ({
  useInbox: () => ({ data: [] }),
}));

const useNodeMock = vi.fn<() => { data: NodeDetail | undefined; isLoading: boolean }>(() => ({
  data: undefined,
  isLoading: false,
}));

vi.mock("@/lib/api/endpoints/nodes", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    useNode: (...args: unknown[]) => useNodeMock(...(args as [])),
  };
});

function withSeed(data: ReactFlowGraph | undefined) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  if (data) qc.setQueryData(queryKeys.graph("p1", "concept"), data);
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/p/p1/graph"]}>
        <Routes>
          <Route path="/p/:projectId/graph" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function makeGraph(): ReactFlowGraph {
  return {
    nodes: [
      {
        id: "user-model",
        type: "concept",
        position: { x: 200, y: 200 },
        data: {
          label: "User model",
          type: "model",
          status: "active",
          has_saved_layout: true,
        },
      },
      {
        id: "auth-flow",
        type: "concept",
        position: { x: 400, y: 250 },
        data: {
          label: "Auth flow",
          type: "decision",
          status: "active",
          has_saved_layout: true,
        },
      },
      {
        id: "session-svc",
        type: "concept",
        position: { x: 600, y: 200 },
        data: {
          label: "Session service",
          type: "service",
          status: "stale",
          has_saved_layout: true,
        },
      },
    ],
    edges: [
      { id: "e1", source: "user-model", target: "auth-flow", relation: "cites", data: {} },
      {
        id: "e2",
        source: "auth-flow",
        target: "session-svc",
        relation: "related",
        data: {},
      },
    ],
    meta: {
      kind: "concept",
      focus: null,
      upstream: false,
      downstream: false,
      depth: null,
      node_count: 3,
      edge_count: 2,
      orphans: [],
    },
  };
}

describe("ConceptGraph layout (PM #25 round 2)", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("viewBox covers every node's position so a tall layout isn't clipped (P1)", () => {
    // Regression: with ~200 layered-BFS nodes, positions span
    // y ≈ -2000..+2000. Previous viewBox `0 0 W H` clipped
    // negative-y content and centred the viewport in dead space.
    // After the fix, the SVG's viewBox covers the bbox of all
    // node positions (with padding), so every circle's cy falls
    // within [vbY, vbY + vbHeight].
    const tallNodes = Array.from({ length: 50 }, (_, i) => ({
      id: `n-${i}`,
      type: "concept" as const,
      position: { x: 100 + (i % 5) * 200, y: -2000 + i * 80 },
      data: { label: `Node ${i}`, type: "model", has_saved_layout: true },
    }));
    const wrapper = withSeed({
      nodes: tallNodes,
      edges: [],
      meta: {
        kind: "concept",
        focus: null,
        upstream: false,
        downstream: false,
        depth: null,
        node_count: tallNodes.length,
        edge_count: 0,
        orphans: [],
      },
    });
    const { container } = render(<ConceptGraph />, { wrapper });
    const svg = container.querySelector(
      "[data-testid='concept-graph-canvas'] svg",
    ) as SVGSVGElement | null;
    expect(svg).not.toBeNull();
    const viewBox = svg?.getAttribute("viewBox") ?? "0 0 0 0";
    const parts = viewBox.split(" ").map(Number);
    const vbX = parts[0] ?? 0;
    const vbY = parts[1] ?? 0;
    const vbW = parts[2] ?? 0;
    const vbH = parts[3] ?? 0;
    // All node circles sit inside the viewBox.
    const circles = container.querySelectorAll("[data-testid^='node-circle-']");
    expect(circles.length).toBe(tallNodes.length);
    for (const circle of Array.from(circles)) {
      const cx = Number(circle.getAttribute("cx"));
      const cy = Number(circle.getAttribute("cy"));
      expect(cx).toBeGreaterThanOrEqual(vbX - 1);
      expect(cx).toBeLessThanOrEqual(vbX + vbW + 1);
      expect(cy).toBeGreaterThanOrEqual(vbY - 1);
      expect(cy).toBeLessThanOrEqual(vbY + vbH + 1);
    }
  });

  it("scrolls sidebar and canvas independently (P1)", () => {
    // The sidebar concept tree must scroll on its own — sharing a
    // scroll container with the canvas means scrolling through
    // nodes loses the sidebar context.
    const wrapper = withSeed({
      nodes: Array.from({ length: 20 }, (_, i) => ({
        id: `concept-${i}`,
        type: "concept" as const,
        position: { x: i * 50, y: i * 50 },
        data: {
          label: `Concept ${i}`,
          type: i % 3 === 0 ? "model" : "decision",
          has_saved_layout: true,
        },
      })),
      edges: [],
      meta: {
        kind: "concept",
        focus: null,
        upstream: false,
        downstream: false,
        depth: null,
        node_count: 20,
        edge_count: 0,
        orphans: [],
      },
    });
    const { container } = render(<ConceptGraph />, { wrapper });
    const sidebar = container.querySelector("[data-testid='graph-sidebar']") as HTMLElement | null;
    const canvas = container.querySelector(
      "[data-testid='concept-graph-canvas']",
    ) as HTMLElement | null;
    expect(sidebar).not.toBeNull();
    expect(canvas).not.toBeNull();
    // Both must own their overflow — neither delegates to the
    // outer grid container. jsdom doesn't compute Tailwind utility
    // classes, so we assert on the className contract instead of
    // getComputedStyle. (The "overflow-y-auto" / "overflow-auto"
    // utilities are how the production CSS sets overflow.)
    expect(sidebar?.className ?? "").toMatch(/overflow-y-auto|overflow-auto/);
    expect(canvas?.className ?? "").toMatch(/overflow-y-auto|overflow-auto/);
    // They are NOT the same node and not nested inside a shared
    // single scroll container.
    expect(sidebar).not.toBe(canvas);
    expect(sidebar?.contains(canvas as Node)).toBe(false);
    expect(canvas?.contains(sidebar as Node)).toBe(false);
  });

  it("clicking the drift header's stale-only toggle dims non-stale nodes", () => {
    // Drift restored as a header card on the Concepts page (the
    // /drift route was retired in v0.9.7). The "show stale only"
    // toggle is the in-page drift filter — non-stale nodes get
    // data-dim="true" so the user can scan only the drift surface.
    const wrapper = withSeed({
      nodes: [
        {
          id: "fresh-1",
          type: "concept",
          position: { x: 100, y: 100 },
          data: { label: "Fresh", type: "model", status: "active", has_saved_layout: true },
        },
        {
          id: "stale-1",
          type: "concept",
          position: { x: 300, y: 100 },
          data: { label: "Stale", type: "model", status: "stale", has_saved_layout: true },
        },
      ],
      edges: [],
      meta: {
        kind: "concept",
        focus: null,
        upstream: false,
        downstream: false,
        depth: null,
        node_count: 2,
        edge_count: 0,
        orphans: [],
      },
    });
    const { container } = render(<ConceptGraph />, { wrapper });
    const fresh = () => container.querySelector("[data-testid='node-group-fresh-1']");
    const stale = () => container.querySelector("[data-testid='node-group-stale-1']");

    // Initially: stale-only is off, neither node is dim.
    expect(fresh()?.getAttribute("data-dim")).toBe("false");
    expect(stale()?.getAttribute("data-dim")).toBe("false");

    // Click the toggle in the drift header.
    const toggle = screen.getByTestId("drift-stale-only-toggle");
    expect(toggle).toHaveTextContent(/show stale only · 1/i);
    fireEvent.click(toggle);

    // Stale node still reads clearly; the fresh node dims.
    expect(stale()?.getAttribute("data-dim")).toBe("false");
    expect(fresh()?.getAttribute("data-dim")).toBe("true");
  });

  it("encodes type-driven node sizing — principles render larger than glossary nodes", () => {
    // P2 from PR review: the TYPE_SIZE_SCALE table at the top of
    // ConceptGraph.tsx had no behavioural test. A row deletion
    // (or accidental flattening of all scales to 1.0) would silently
    // regress the visual hierarchy. We pin only the ORDERING — exact
    // pixel radii are calibration knobs that should stay free to
    // tune. Today: principle/invariant 1.4× > model/decision 1.0× >
    // glossary/practice 0.85×.
    const wrapper = withSeed({
      nodes: [
        {
          id: "principle-x",
          type: "concept",
          position: { x: 100, y: 100 },
          data: { label: "P", type: "principle", has_saved_layout: true },
        },
        {
          id: "model-x",
          type: "concept",
          position: { x: 300, y: 100 },
          data: { label: "M", type: "model", has_saved_layout: true },
        },
        {
          id: "glossary-x",
          type: "concept",
          position: { x: 500, y: 100 },
          data: { label: "G", type: "glossary", has_saved_layout: true },
        },
      ],
      edges: [],
      meta: {
        kind: "concept",
        focus: null,
        upstream: false,
        downstream: false,
        depth: null,
        node_count: 3,
        edge_count: 0,
        orphans: [],
      },
    });
    const { container } = render(<ConceptGraph />, { wrapper });
    const r = (id: string) =>
      Number(
        container
          .querySelector(`[data-testid='node-circle-${id}']`)
          ?.getAttribute("r"),
      );
    const rPrinciple = r("principle-x");
    const rModel = r("model-x");
    const rGlossary = r("glossary-x");
    // Strict ordering — the table being adjusted up or down is
    // fine; flattening to a single radius is the regression we
    // want to catch.
    expect(rPrinciple).toBeGreaterThan(rModel);
    expect(rModel).toBeGreaterThan(rGlossary);
  });

  it("truncates long node labels on the canvas to keep dense layouts readable (P1)", () => {
    const longLabel = "this is an extremely long concept node label";
    const wrapper = withSeed({
      nodes: [
        {
          id: "verbose",
          type: "concept",
          position: { x: 100, y: 100 },
          data: { label: longLabel, type: "model", has_saved_layout: true },
        },
      ],
      edges: [],
      meta: {
        kind: "concept",
        focus: null,
        upstream: false,
        downstream: false,
        depth: null,
        node_count: 1,
        edge_count: 0,
        orphans: [],
      },
    });
    const { container } = render(<ConceptGraph />, { wrapper });
    const labelText = container
      .querySelector("[data-testid='node-label-verbose']")
      ?.textContent?.trim();
    expect(labelText).toBeDefined();
    // Truncated form should not contain the full label.
    expect(labelText?.length ?? 0).toBeLessThan(longLabel.length);
    expect(labelText).toMatch(/…|\.\.\./);
  });
});

describe("ConceptGraph", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("does not crash when the payload contains issue↔concept edges (PM #25 P1)", () => {
    // Regression: d3-force throws on link initialisation when an
    // edge endpoint is absent from the simulation's node set. The
    // backend's concept graph payload returns a mix of concept and
    // issue nodes; if we hand all edges to useGraphLayout while
    // only feeding it the concept subset, the issue↔concept edges
    // dangle and the simulation explodes on first load.
    const wrapper = withSeed({
      nodes: [
        {
          id: "user-model",
          type: "concept",
          position: { x: 100, y: 100 },
          data: { label: "User model", type: "model", has_saved_layout: true },
        },
        {
          id: "auth-flow",
          type: "concept",
          position: { x: 300, y: 200 },
          data: { label: "Auth flow", type: "decision" },
        },
        {
          id: "KUI-1",
          type: "issue",
          position: { x: 500, y: 100 },
          data: { label: "Login endpoint" },
        },
      ],
      edges: [
        {
          id: "e_concept",
          source: "user-model",
          target: "auth-flow",
          relation: "cites",
          data: {},
        },
        {
          // issue → concept reference edge — would dangle for
          // useGraphLayout if not filtered out at the call site.
          id: "e_issue_ref",
          source: "KUI-1",
          target: "user-model",
          relation: "references",
          data: {},
        },
      ],
      meta: {
        kind: "concept",
        focus: null,
        upstream: false,
        downstream: false,
        depth: null,
        node_count: 3,
        edge_count: 2,
        orphans: [],
      },
    });
    expect(() => render(<ConceptGraph />, { wrapper })).not.toThrow();
  });

  it("shows the empty-state when the backend returns 0 nodes", () => {
    const wrapper = withSeed({
      nodes: [],
      edges: [],
      meta: {
        kind: "concept",
        focus: null,
        upstream: false,
        downstream: false,
        depth: null,
        node_count: 0,
        edge_count: 0,
        orphans: [],
      },
    });
    render(<ConceptGraph />, { wrapper });
    expect(screen.getByText(/No concept nodes yet/)).toBeInTheDocument();
  });

  it("renders the chapter eyebrow + title from the design mockup", () => {
    const wrapper = withSeed(makeGraph());
    render(<ConceptGraph />, { wrapper });
    expect(screen.getByText(/chapter 05 · concept graph/i)).toBeInTheDocument();
    expect(screen.getByText(/What this project is made of/i)).toBeInTheDocument();
  });

  it("renders the left sidebar grouped by node type", () => {
    const wrapper = withSeed(makeGraph());
    const { container } = render(<ConceptGraph />, { wrapper });
    const sidebar = container.querySelector("[data-testid='graph-sidebar']");
    expect(sidebar).not.toBeNull();
    // The SVG canvas also renders these labels via <text> with role=button
    // groups, so scope the lookup to the sidebar HTML buttons.
    const buttons = sidebar?.querySelectorAll("button") ?? [];
    const labels = Array.from(buttons).map((b) => b.textContent ?? "");
    expect(labels).toEqual(expect.arrayContaining(["Auth flow", "Session service", "User model"]));
  });

  it("renders one SVG circle per concept node on the canvas", () => {
    const wrapper = withSeed(makeGraph());
    const { container } = render(<ConceptGraph />, { wrapper });
    const circles = container.querySelectorAll("[data-testid^='node-circle-']");
    expect(circles.length).toBe(3);
  });

  it("renders edges with the correct dasharray for relation kind", () => {
    const wrapper = withSeed(makeGraph());
    const { container } = render(<ConceptGraph />, { wrapper });
    const cites = container.querySelector("[data-edge-relation='cites']") as SVGLineElement | null;
    const related = container.querySelector(
      "[data-edge-relation='related']",
    ) as SVGLineElement | null;
    expect(cites).not.toBeNull();
    expect(related).not.toBeNull();
    expect(cites?.getAttribute("stroke-dasharray")).toBe("0");
    expect(related?.getAttribute("stroke-dasharray")).toBe("3 3");
  });

  it("treats cites and references as solid relations; related as dashed (PM #25 round 4 P2)", () => {
    // Regression: edges previously rendered solid only when
    // `relation === "cites"`, so backend `references` edges showed
    // dashed even though the legend's solid swatch is meant to
    // cover both. The mapping is now explicit: solid for cites +
    // references; dashed for everything else (related, blocked_by,
    // parent, …).
    const wrapper = withSeed({
      nodes: [
        {
          id: "a",
          type: "concept",
          position: { x: 100, y: 100 },
          data: { label: "A", type: "model", has_saved_layout: true },
        },
        {
          id: "b",
          type: "concept",
          position: { x: 200, y: 100 },
          data: { label: "B", type: "model", has_saved_layout: true },
        },
        {
          id: "c",
          type: "concept",
          position: { x: 300, y: 100 },
          data: { label: "C", type: "model", has_saved_layout: true },
        },
        {
          id: "d",
          type: "concept",
          position: { x: 400, y: 100 },
          data: { label: "D", type: "model", has_saved_layout: true },
        },
      ],
      edges: [
        { id: "e1", source: "a", target: "b", relation: "cites", data: {} },
        { id: "e2", source: "b", target: "c", relation: "references", data: {} },
        { id: "e3", source: "c", target: "d", relation: "related", data: {} },
      ],
      meta: {
        kind: "concept",
        focus: null,
        upstream: false,
        downstream: false,
        depth: null,
        node_count: 4,
        edge_count: 3,
        orphans: [],
      },
    });
    const { container } = render(<ConceptGraph />, { wrapper });
    const get = (rel: string) =>
      container.querySelector(`[data-edge-relation='${rel}']`) as SVGLineElement | null;
    expect(get("cites")?.getAttribute("stroke-dasharray")).toBe("0");
    expect(get("references")?.getAttribute("stroke-dasharray")).toBe("0");
    expect(get("related")?.getAttribute("stroke-dasharray")).toBe("3 3");
  });

  it("draws the dashed amber stroke on stale concept nodes", () => {
    const wrapper = withSeed(makeGraph());
    const { container } = render(<ConceptGraph />, { wrapper });
    const stale = container.querySelector(
      "[data-testid='node-circle-session-svc']",
    ) as SVGCircleElement | null;
    expect(stale).not.toBeNull();
    expect(stale?.getAttribute("data-stale")).toBe("true");
    expect(stale?.getAttribute("stroke-dasharray")).toBe("3 2");
  });

  it("focuses a node on click and dims non-neighbours via group opacity", () => {
    const wrapper = withSeed(makeGraph());
    const { container } = render(<ConceptGraph />, { wrapper });
    const target = container.querySelector(
      "[data-testid='node-group-auth-flow']",
    ) as SVGGElement | null;
    expect(target).not.toBeNull();
    fireEvent.click(target as Element);

    // After click: focus = auth-flow. Its 1-hop neighbours are
    // user-model + session-svc; both stay full opacity. No node is
    // dimmed because every concept is a neighbour or the focus.
    const focused = container.querySelector("[data-testid='node-group-auth-flow']");
    expect(focused?.getAttribute("data-focus")).toBe("true");
    expect(focused?.getAttribute("data-dim")).toBe("false");
  });

  it("dims non-neighbour groups when a leaf node is focused", () => {
    const graph = makeGraph();
    // Add a 4th unconnected concept so it can be dimmed.
    graph.nodes.push({
      id: "lonely",
      type: "concept",
      position: { x: 800, y: 400 },
      data: { label: "Lonely", type: "model", has_saved_layout: true },
    });
    const wrapper = withSeed(graph);
    const { container } = render(<ConceptGraph />, { wrapper });
    fireEvent.click(container.querySelector("[data-testid='node-group-user-model']") as Element);
    const lonely = container.querySelector("[data-testid='node-group-lonely']");
    expect(lonely?.getAttribute("data-dim")).toBe("true");
  });
});

describe("ConceptGraph rail", () => {
  afterEach(() => {
    cleanup();
    useNodeMock.mockReset();
    useNodeMock.mockImplementation(() => ({ data: undefined, isLoading: false }));
  });

  it("shows version + last-touched-by metadata when source provenance is set", () => {
    const detail: NodeDetail = {
      id: "user-model",
      type: "model",
      name: "User model",
      description: "User identity record",
      status: "active",
      tags: [],
      related: [],
      ref_count: 2,
      body: "## Description\n\nWhat the user model is.\n",
      is_stale: false,
      source: {
        repo: "SeidoAI/web",
        path: "src/models/user.py",
        content_hash: "sha256:abc1234567",
      },
    };
    useNodeMock.mockImplementation(() => ({ data: detail, isLoading: false }));

    const wrapper = withSeed(makeGraph());
    const { container } = render(<ConceptGraph />, { wrapper });
    fireEvent.click(container.querySelector("[data-testid='node-group-user-model']") as Element);
    // Title is rendered with double-bracket wrapper; rail shows it
    // alongside the sidebar entry — assert the rail-specific shape.
    expect(screen.getByText(/\[\[User model\]\]/)).toBeInTheDocument();
    expect(screen.getByText(/version · vabc1234/i)).toBeInTheDocument();
  });
});

describe("ConceptGraph auto-arrange button", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("flips to 'Re-layout all' (enabled) when every node has a saved layout", () => {
    // PM #25 round 5: a disabled "All nodes positioned" state
    // stranded users whose positions all came from automatic
    // seeding (not user drags). The button now flips to a
    // "Re-layout all" mode that un-pins everything for one pass.
    const wrapper = withSeed(makeGraph()); // every node in makeGraph has has_saved_layout: true
    render(<ConceptGraph />, { wrapper });
    const btn = screen.getByRole("button", { name: /re-layout every concept node/i });
    expect(btn).not.toBeDisabled();
    expect(btn.textContent ?? "").toMatch(/re-layout all/i);
  });

  it("shows the unsaved count and is enabled when unsaved nodes exist", () => {
    const wrapper = withSeed({
      nodes: [
        {
          id: "saved-1",
          type: "concept",
          position: { x: 100, y: 100 },
          data: { label: "Saved", type: "model", has_saved_layout: true },
        },
        {
          id: "unsaved-1",
          type: "concept",
          position: { x: 0, y: 0 },
          data: { label: "Unsaved A", type: "principle" },
        },
        {
          id: "unsaved-2",
          type: "concept",
          position: { x: 0, y: 0 },
          data: { label: "Unsaved B", type: "principle" },
        },
      ],
      edges: [{ id: "e1", source: "saved-1", target: "unsaved-1", relation: "related", data: {} }],
      meta: {
        kind: "concept",
        focus: null,
        upstream: false,
        downstream: false,
        depth: null,
        node_count: 3,
        edge_count: 1,
        orphans: [],
      },
    });
    render(<ConceptGraph />, { wrapper });
    const btn = screen.getByRole("button", { name: /auto-arrange unsaved nodes/i });
    expect(btn).not.toBeDisabled();
    expect(btn.textContent ?? "").toMatch(/auto-arrange \(2 unsaved\)/i);
  });

  it("clicking the button does not throw and the button stays present", () => {
    // Smoke test for the click path: bumps reseedNonce → useGraphLayout
    // re-runs → useLayoutPersistence buffers a PATCH on debounce.
    // The persistence layer is debounced and tested separately; here
    // we verify the click is safe and the UI stays responsive.
    const wrapper = withSeed({
      nodes: [
        {
          id: "anchor",
          type: "concept",
          position: { x: 200, y: 200 },
          data: { label: "Anchor", type: "model", has_saved_layout: true },
        },
        {
          id: "drifter",
          type: "concept",
          position: { x: 0, y: 0 },
          data: { label: "Drifter", type: "principle" },
        },
      ],
      edges: [{ id: "e1", source: "anchor", target: "drifter", relation: "related", data: {} }],
      meta: {
        kind: "concept",
        focus: null,
        upstream: false,
        downstream: false,
        depth: null,
        node_count: 2,
        edge_count: 1,
        orphans: [],
      },
    });
    render(<ConceptGraph />, { wrapper });
    const btn = screen.getByRole("button", { name: /auto-arrange unsaved nodes/i });
    expect(() => fireEvent.click(btn)).not.toThrow();
    // Button still visible after the click; not in an error state.
    expect(screen.getByRole("button", { name: /auto-arrange unsaved nodes/i })).toBeInTheDocument();
  });
});
