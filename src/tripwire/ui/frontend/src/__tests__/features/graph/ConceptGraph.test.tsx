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

const useNodeMock = vi.fn<() => { data: NodeDetail | undefined; isLoading: boolean }>(
  () => ({ data: undefined, isLoading: false }),
);

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

describe("ConceptGraph", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
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
