import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConceptGraph } from "@/features/graph/ConceptGraph";
import type { ReactFlowGraph } from "@/lib/api/endpoints/graph";
import { queryKeys } from "@/lib/api/queryKeys";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

// React Flow relies on ResizeObserver at mount. jsdom doesn't ship one,
// so every test suite that mounts ReactFlow has to supply a stub. We
// also stub `DOMRect` measurements via getBoundingClientRect below.
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverMock);
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

describe("ConceptGraph", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
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

  it("renders the type-filter legend with one entry per unique node type", () => {
    const wrapper = withSeed({
      nodes: [
        {
          id: "user-model",
          type: "concept",
          position: { x: 0, y: 0 },
          data: { label: "User model", node_type: "decision" },
        },
        {
          id: "auth-flow",
          type: "concept",
          position: { x: 100, y: 0 },
          data: { label: "Auth flow", node_type: "decision" },
        },
        {
          id: "KUI-1",
          type: "issue",
          position: { x: 200, y: 0 },
          data: { label: "Login endpoint" },
        },
      ],
      edges: [
        {
          id: "e1",
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
        edge_count: 1,
        orphans: [],
      },
    });
    render(<ConceptGraph />, { wrapper });
    // Two distinct React Flow types: "concept" and "issue"
    expect(screen.getByRole("button", { name: "concept" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "issue" })).toBeInTheDocument();
    expect(screen.getByText(/3 nodes · 1 edges/)).toBeInTheDocument();
  });
});
