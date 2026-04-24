import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NodeDetail as NodeDetailView } from "@/features/nodes/NodeDetail";
import type {
  NodeDetail,
  NodeSummary,
  Referrer,
  ReverseRefsResult,
} from "@/lib/api/endpoints/nodes";
import type { ProjectDetail } from "@/lib/api/endpoints/project";
import { queryKeys } from "@/lib/api/queryKeys";

function baseNode(overrides: Partial<NodeDetail> = {}): NodeDetail {
  return {
    id: "auth-token-endpoint",
    type: "endpoint",
    name: "POST /auth/token",
    description: "Issue an auth token.",
    status: "active",
    tags: ["auth", "api"],
    related: ["user-model", "only-one-way"],
    ref_count: 7,
    body: "Body content here.",
    source: {
      repo: "SeidoAI/tripwire",
      path: "src/api/auth.py",
      lines: [45, 82],
      branch: "main",
      content_hash: "sha256:e3b0c4",
    },
    is_stale: false,
    ...overrides,
  };
}

function baseProject(overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    id: "p1",
    name: "Demo",
    key_prefix: "KUI",
    phase: "executing",
    repos: {
      "SeidoAI/tripwire": { local: "/tmp/tripwire-clone" },
    },
    ...overrides,
  };
}

function makeReferrers(count: number): Referrer[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `KUI-${i + 1}`,
    kind: "issue" as const,
  }));
}

function prime(opts: {
  node?: NodeDetail | undefined;
  project?: ProjectDetail;
  reverseRefs?: ReverseRefsResult;
  allNodes?: NodeSummary[];
}): { wrapper: ({ children }: { children: ReactNode }) => ReactElement } {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  if (opts.node) qc.setQueryData(queryKeys.node("p1", opts.node.id), opts.node);
  if (opts.project) qc.setQueryData(queryKeys.project("p1"), opts.project);
  if (opts.reverseRefs) {
    qc.setQueryData(queryKeys.reverseRefs("p1", opts.reverseRefs.node_id), opts.reverseRefs);
  }
  if (opts.allNodes) qc.setQueryData(queryKeys.nodes("p1"), opts.allNodes);

  const path = opts.node ? `/p/p1/nodes/${opts.node.id}` : "/p/p1/nodes/auth-token-endpoint";
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/p/:projectId/nodes/:nodeId" element={children} />
          <Route path="/p/:projectId/graph" element={<div>Graph stub</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { wrapper };
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(() => new Promise(() => {})),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("NodeDetail", () => {
  it("renders the header, source panel, body, and bidirectional markers", () => {
    const node = baseNode();
    const allNodes: NodeSummary[] = [
      {
        id: "user-model",
        type: "model",
        name: "User model",
        description: null,
        status: "active",
        tags: [],
        related: ["auth-token-endpoint"],
        ref_count: 1,
      },
      {
        id: "only-one-way",
        type: "concept",
        name: "One-way node",
        description: null,
        status: "active",
        tags: [],
        related: [],
        ref_count: 0,
      },
    ];
    const reverseRefs: ReverseRefsResult = {
      node_id: "auth-token-endpoint",
      referrers: [{ id: "KUI-42", kind: "issue" }],
    };

    const { wrapper } = prime({
      node,
      project: baseProject(),
      reverseRefs,
      allNodes,
    });
    const { container } = render(<NodeDetailView />, { wrapper });

    expect(container.textContent).toContain("auth-token-endpoint");
    expect(screen.getByText("endpoint")).toBeInTheDocument();
    expect(screen.getByText("POST /auth/token")).toBeInTheDocument();

    // Source panel
    expect(screen.getByText("SeidoAI/tripwire")).toBeInTheDocument();
    expect(screen.getByText("src/api/auth.py")).toBeInTheDocument();
    expect(screen.getByText("45–82")).toBeInTheDocument();

    // Bidirectional indicator for user-model, one-sided for only-one-way
    const bidi = container.querySelector('[data-related-id="user-model"]');
    expect(bidi?.querySelector('[data-relation="bidirectional"]')).not.toBeNull();

    const oneSided = container.querySelector('[data-related-id="only-one-way"]');
    expect(oneSided?.querySelector('[data-relation="one-sided"]')).not.toBeNull();
    expect(oneSided?.textContent).toContain("one-sided");

    // Reverse refs
    expect(screen.getByText("KUI-42")).toBeInTheDocument();
  });

  it("shows the stale banner when is_stale is true", () => {
    const { wrapper } = prime({
      node: baseNode({ is_stale: true }),
      project: baseProject(),
      reverseRefs: { node_id: "auth-token-endpoint", referrers: [] },
      allNodes: [],
    });
    render(<NodeDetailView />, { wrapper });

    expect(screen.getByRole("alert", { name: /Source drifted/ })).toBeInTheDocument();
    expect(screen.getByText(/Source has drifted/)).toBeInTheDocument();
  });

  it("paginates reverse refs at 10 per page", () => {
    const { wrapper } = prime({
      node: baseNode(),
      project: baseProject(),
      reverseRefs: {
        node_id: "auth-token-endpoint",
        referrers: makeReferrers(25),
      },
      allNodes: [],
    });
    const { container } = render(<NodeDetailView />, { wrapper });

    const rows = container.querySelectorAll("li[data-referrer-id]");
    expect(rows.length).toBe(10);
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("Page 3 of 3")).toBeInTheDocument();

    // Last page should have 5 items
    const lastPageRows = container.querySelectorAll("li[data-referrer-id]");
    expect(lastPageRows.length).toBe(5);
  });

  it("uses 'Open in editor' (file://) when a local clone is registered", () => {
    const { wrapper } = prime({
      node: baseNode(),
      project: baseProject(),
      reverseRefs: { node_id: "auth-token-endpoint", referrers: [] },
      allNodes: [],
    });
    render(<NodeDetailView />, { wrapper });

    const link = screen.getByRole("link", { name: "Open source in editor" });
    expect(link).toHaveAttribute("href", "file:///tmp/tripwire-clone/src/api/auth.py#L45-L82");
  });

  it("falls back to the GitHub URL when no local clone is registered", () => {
    const project = baseProject();
    project.repos = { "SeidoAI/tripwire": { local: null } };
    const { wrapper } = prime({
      node: baseNode(),
      project,
      reverseRefs: { node_id: "auth-token-endpoint", referrers: [] },
      allNodes: [],
    });
    render(<NodeDetailView />, { wrapper });

    const link = screen.getByRole("link", { name: "Open source on GitHub" });
    expect(link).toHaveAttribute(
      "href",
      "https://github.com/SeidoAI/tripwire/blob/main/src/api/auth.py#L45-L82",
    );
  });

  it("resets reverse-refs pagination to page 1 when nodeId changes", () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
    });
    const nodeA = baseNode({ id: "node-a", name: "Node A" });
    const nodeB = baseNode({ id: "node-b", name: "Node B" });
    qc.setQueryData(queryKeys.node("p1", "node-a"), nodeA);
    qc.setQueryData(queryKeys.node("p1", "node-b"), nodeB);
    qc.setQueryData(queryKeys.project("p1"), baseProject());
    qc.setQueryData(queryKeys.nodes("p1"), []);
    qc.setQueryData(queryKeys.reverseRefs("p1", "node-a"), {
      node_id: "node-a",
      referrers: makeReferrers(25), // 3 pages
    });
    qc.setQueryData(queryKeys.reverseRefs("p1", "node-b"), {
      node_id: "node-b",
      referrers: makeReferrers(8), // 1 page
    });

    const GoToB = () => (
      <Link to="/p/p1/nodes/node-b" data-testid="nav-b">
        go B
      </Link>
    );

    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/p/p1/nodes/node-a"]}>
          <Routes>
            <Route
              path="/p/:projectId/nodes/:nodeId"
              element={
                <>
                  <GoToB />
                  <NodeDetailView />
                </>
              }
            />
            <Route path="/p/:projectId/graph" element={<div>Graph stub</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // On Node A: advance to page 3.
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("Page 3 of 3")).toBeInTheDocument();

    // Navigate to Node B. `key={nodeId}` on NodeDetailInner must remount
    // NodeReverseRefs so its local `page` state resets to 0. Node B only
    // has 1 page, so the paginator controls are absent — the assertion is
    // that no "Page 3" label lingers.
    fireEvent.click(screen.getByTestId("nav-b"));

    expect(screen.queryByText(/Page 3 of/)).not.toBeInTheDocument();
    // 8 referrers on Node B — all fit on one page, no paginator.
    expect(screen.queryByRole("button", { name: "Next page" })).not.toBeInTheDocument();
    expect(screen.getByText("Referenced by (8)")).toBeInTheDocument();
  });

  it("renders 'not found' when the API returns 404", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Node not found", code: "node/not_found" }), {
          status: 404,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/p/p1/nodes/missing-node"]}>
          <Routes>
            <Route path="/p/:projectId/nodes/:nodeId" element={children} />
            <Route path="/p/:projectId/graph" element={<div>Graph stub</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    render(<NodeDetailView />, { wrapper });

    expect(await screen.findByText("Node not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to graph/ })).toHaveAttribute(
      "href",
      "/p/p1/graph",
    );
  });

  it("does not call the freshness endpoint on mount", () => {
    const fetchMock = vi.fn().mockImplementation(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);

    const { wrapper } = prime({
      node: baseNode(),
      project: baseProject(),
      reverseRefs: { node_id: "auth-token-endpoint", referrers: [] },
      allNodes: [],
    });
    render(<NodeDetailView />, { wrapper });

    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/nodes/check"),
      expect.anything(),
    );
  });
});
