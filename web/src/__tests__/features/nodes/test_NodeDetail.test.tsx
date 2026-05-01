import { cleanup, fireEvent, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { Link, Route } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NodeDetail as NodeDetailView } from "@/features/nodes/NodeDetail";
import type { NodeDetail, NodeSummary, ReverseRefsResult } from "@/lib/api/endpoints/nodes";
import type { ProjectDetail } from "@/lib/api/endpoints/project";
import { queryKeys } from "@/lib/api/queryKeys";
import { makeNodeDetail, makeNodeSummary, makeProject, makeReferrers } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { makeTestQueryClient, renderWithProviders } from "../../test-utils";

const NODE_ID = "auth-token-endpoint";

function fixtureNode(overrides: Partial<NodeDetail> = {}): NodeDetail {
  return makeNodeDetail({
    id: NODE_ID,
    type: "endpoint",
    name: "POST /auth/token",
    description: "Issue an auth token.",
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
    ...overrides,
  });
}

function fixtureProject(overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  return makeProject({
    name: "Demo",
    key_prefix: "KUI",
    repos: { "SeidoAI/tripwire": { local: "/tmp/tripwire-clone" } },
    ...overrides,
  });
}

const NODE_DETAIL_EXTRAS = <Route path="/p/:projectId/graph" element={<div>Graph stub</div>} />;

function renderNodeDetail(opts: {
  node?: NodeDetail;
  project?: ProjectDetail;
  reverseRefs?: ReverseRefsResult;
  allNodes?: NodeSummary[];
  initialPath?: string;
}) {
  const qc = makeTestQueryClient();
  if (opts.node) qc.setQueryData(queryKeys.node("p1", opts.node.id), opts.node);
  if (opts.project) qc.setQueryData(queryKeys.project("p1"), opts.project);
  if (opts.reverseRefs) {
    qc.setQueryData(queryKeys.reverseRefs("p1", opts.reverseRefs.node_id), opts.reverseRefs);
  }
  if (opts.allNodes) qc.setQueryData(queryKeys.nodes("p1"), opts.allNodes);
  return renderWithProviders(<NodeDetailView />, {
    queryClient: qc,
    initialPath: opts.initialPath ?? `/p/p1/nodes/${opts.node?.id ?? NODE_ID}`,
    routePath: "/p/:projectId/nodes/:nodeId",
    extraRoutes: NODE_DETAIL_EXTRAS,
  });
}

afterEach(() => {
  cleanup();
});

describe("NodeDetail", () => {
  it("renders the header, source panel, body, and bidirectional markers", () => {
    const allNodes: NodeSummary[] = [
      makeNodeSummary({
        id: "user-model",
        type: "model",
        name: "User model",
        related: ["auth-token-endpoint"],
        ref_count: 1,
      }),
      makeNodeSummary({ id: "only-one-way", name: "One-way node" }),
    ];
    const reverseRefs: ReverseRefsResult = {
      node_id: NODE_ID,
      referrers: [{ id: "KUI-42", kind: "issue" }],
    };

    const { container } = renderNodeDetail({
      node: fixtureNode(),
      project: fixtureProject(),
      reverseRefs,
      allNodes,
    });

    expect(container.textContent).toContain(NODE_ID);
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
    renderNodeDetail({
      node: fixtureNode({ is_stale: true }),
      project: fixtureProject(),
      reverseRefs: { node_id: NODE_ID, referrers: [] },
      allNodes: [],
    });

    expect(screen.getByRole("alert", { name: /Source drifted/ })).toBeInTheDocument();
    expect(screen.getByText(/Source has drifted/)).toBeInTheDocument();
  });

  it("paginates reverse refs at 10 per page", () => {
    const { container } = renderNodeDetail({
      node: fixtureNode(),
      project: fixtureProject(),
      reverseRefs: { node_id: NODE_ID, referrers: makeReferrers(25, "KUI") },
      allNodes: [],
    });

    expect(container.querySelectorAll("li[data-referrer-id]").length).toBe(10);
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("Page 3 of 3")).toBeInTheDocument();
    expect(container.querySelectorAll("li[data-referrer-id]").length).toBe(5);
  });

  it("uses 'Open in editor' (file://) when a local clone is registered", () => {
    renderNodeDetail({
      node: fixtureNode(),
      project: fixtureProject(),
      reverseRefs: { node_id: NODE_ID, referrers: [] },
      allNodes: [],
    });

    const link = screen.getByRole("link", { name: "Open source in editor" });
    expect(link).toHaveAttribute("href", "file:///tmp/tripwire-clone/src/api/auth.py#L45-L82");
  });

  it("falls back to the GitHub URL when no local clone is registered", () => {
    renderNodeDetail({
      node: fixtureNode(),
      project: fixtureProject({ repos: { "SeidoAI/tripwire": { local: null } } }),
      reverseRefs: { node_id: NODE_ID, referrers: [] },
      allNodes: [],
    });

    const link = screen.getByRole("link", { name: "Open source on GitHub" });
    expect(link).toHaveAttribute(
      "href",
      "https://github.com/SeidoAI/tripwire/blob/main/src/api/auth.py#L45-L82",
    );
  });

  it("resets reverse-refs pagination to page 1 when nodeId changes", () => {
    const qc = makeTestQueryClient();
    const nodeA = fixtureNode({ id: "node-a", name: "Node A" });
    const nodeB = fixtureNode({ id: "node-b", name: "Node B" });
    qc.setQueryData(queryKeys.node("p1", "node-a"), nodeA);
    qc.setQueryData(queryKeys.node("p1", "node-b"), nodeB);
    qc.setQueryData(queryKeys.project("p1"), fixtureProject());
    qc.setQueryData(queryKeys.nodes("p1"), []);
    qc.setQueryData(queryKeys.reverseRefs("p1", "node-a"), {
      node_id: "node-a",
      referrers: makeReferrers(25, "KUI"),
    });
    qc.setQueryData(queryKeys.reverseRefs("p1", "node-b"), {
      node_id: "node-b",
      referrers: makeReferrers(8, "KUI"),
    });

    const GoToB = () => (
      <Link to="/p/p1/nodes/node-b" data-testid="nav-b">
        go B
      </Link>
    );

    renderWithProviders(
      <>
        <GoToB />
        <NodeDetailView />
      </>,
      {
        queryClient: qc,
        initialPath: "/p/p1/nodes/node-a",
        routePath: "/p/:projectId/nodes/:nodeId",
        extraRoutes: NODE_DETAIL_EXTRAS,
      },
    );

    // On Node A: advance to page 3.
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("Page 3 of 3")).toBeInTheDocument();

    // Navigate to Node B. `key={nodeId}` on NodeDetailInner must remount
    // NodeReverseRefs so its local `page` state resets to 0. Node B
    // only has 1 page, so the paginator controls are absent — the
    // assertion is that no "Page 3" label lingers.
    fireEvent.click(screen.getByTestId("nav-b"));

    expect(screen.queryByText(/Page 3 of/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Next page" })).not.toBeInTheDocument();
    expect(screen.getByText("Referenced by (8)")).toBeInTheDocument();
  });

  it("renders 'not found' when the API returns 404", async () => {
    server.use(
      http.get("/api/projects/p1/nodes/missing-node", () =>
        HttpResponse.json({ detail: "Node not found", code: "node/not_found" }, { status: 404 }),
      ),
    );

    renderWithProviders(<NodeDetailView />, {
      initialPath: "/p/p1/nodes/missing-node",
      routePath: "/p/:projectId/nodes/:nodeId",
      extraRoutes: NODE_DETAIL_EXTRAS,
    });

    expect(await screen.findByText("Node not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to graph/ })).toHaveAttribute(
      "href",
      "/p/p1/graph",
    );
  });

  it("does not call the freshness endpoint on mount", () => {
    const checkSpy = vi.fn();
    server.use(
      http.get("/api/projects/p1/nodes/check", () => {
        checkSpy();
        return HttpResponse.json({});
      }),
      http.post("/api/projects/p1/nodes/check", () => {
        checkSpy();
        return HttpResponse.json({});
      }),
    );

    renderNodeDetail({
      node: fixtureNode(),
      project: fixtureProject(),
      reverseRefs: { node_id: NODE_ID, referrers: [] },
      allNodes: [],
    });

    expect(checkSpy).not.toHaveBeenCalled();
  });
});
