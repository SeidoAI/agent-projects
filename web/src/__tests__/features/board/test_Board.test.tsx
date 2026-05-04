import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Board } from "@/features/board/Board";
import type { IssueSummary } from "@/lib/api/endpoints/issues";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { queryKeys } from "@/lib/api/queryKeys";

afterEach(() => cleanup());

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

function makeSession(overrides: Partial<SessionSummary>): SessionSummary {
  return {
    id: "x",
    name: "session",
    agent: "frontend-coder",
    status: "executing",
    issues: [],
    estimated_size: null,
    blocked_by_sessions: [],
    repos: [],
    current_state: null,
    re_engagement_count: 0,
    task_progress: { done: 0, total: 0 },
    cost_usd: 0,
    ...overrides,
  };
}

function makeIssue(overrides: Partial<IssueSummary>): IssueSummary {
  return {
    id: "K-1",
    title: "issue",
    status: "backlog",
    priority: "medium",
    executor: "ai",
    verifier: "required",
    kind: null,
    agent: null,
    labels: [],
    parent: null,
    repo: null,
    blocked_by: [],
    is_blocked: false,
    is_epic: false,
    created_at: "2026-04-20T12:00:00Z",
    updated_at: "2026-04-20T12:00:00Z",
    ...overrides,
  };
}

function makeQc(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
}

function renderBoard({
  qc,
  initialPath = "/p/p1/board",
}: {
  qc: QueryClient;
  initialPath?: string;
}) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/p/:projectId/board" element={children} />
            <Route path="*" element={<div data-testid="elsewhere" />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }
  return { qc, ...render(<Board />, { wrapper: Wrapper }) };
}

describe("Board", () => {
  it("defaults to sessions view, renders a card per loaded session", async () => {
    const qc = makeQc();
    qc.setQueryData(queryKeys.sessions("p1"), [
      makeSession({ id: "v08-board", status: "executing" }),
      makeSession({ id: "v08-foundations", status: "completed" }),
      makeSession({ id: "v08-recovery", status: "failed" }),
    ]);
    qc.setQueryData(queryKeys.issues("p1"), []);
    qc.setQueryData(queryKeys.enum("p1", "issue_status"), { name: "x", values: [] });
    qc.setQueryData(queryKeys.inboxFiltered("p1", { bucket: "blocked" }), []);

    renderBoard({ qc });

    await waitFor(() => {
      expect(screen.getByText("v08-board")).toBeInTheDocument();
    });
    // Off-track column appears because we have a `failed` session.
    expect(screen.getByRole("region", { name: /off-track/i })).toBeInTheDocument();
    // The completed column renders too — drag-targets always exist
    // for the in-flow stages.
    expect(screen.getByRole("region", { name: /completed/i })).toBeInTheDocument();
  });

  it("hydrates view + filter state from URL", async () => {
    const qc = makeQc();
    qc.setQueryData(queryKeys.sessions("p1"), []);
    qc.setQueryData(queryKeys.issues("p1"), [makeIssue({ id: "B-1", title: "First issue" })]);
    qc.setQueryData(queryKeys.enum("p1", "issue_status"), {
      name: "issue_status",
      values: [
        { value: "backlog", label: "Backlog", color: null, description: null },
        { value: "done", label: "Done", color: null, description: null },
      ],
    });
    qc.setQueryData(queryKeys.inboxFiltered("p1", { bucket: "blocked" }), []);

    renderBoard({ qc, initialPath: "/p/p1/board?view=issues" });

    await waitFor(() => {
      expect(screen.getByText("First issue")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /^issues/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("opens the entity preview drawer when a card is clicked", async () => {
    const qc = makeQc();
    qc.setQueryData(queryKeys.sessions("p1"), [makeSession({ id: "abc", name: "Demo session" })]);
    qc.setQueryData(queryKeys.issues("p1"), []);
    qc.setQueryData(queryKeys.enum("p1", "issue_status"), { name: "x", values: [] });
    qc.setQueryData(queryKeys.inboxFiltered("p1", { bucket: "blocked" }), []);

    renderBoard({ qc });

    await waitFor(() => {
      expect(screen.getByText("Demo session")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("abc"));
    // The entity drawer renders the title (visible heading) + an
    // "open full →" link to the full session detail screen.
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Demo session" })).toBeInTheDocument();
    });
    const openFull = screen.getByRole("link", { name: /open full/i });
    expect(openFull).toHaveAttribute("href", "/p/p1/sessions/abc");
  });

  // ===========================================================================
  // 2x2 matrix: view ∈ {sessions, issues} × mode ∈ {board, graph}
  // ===========================================================================
  describe("mode toggle", () => {
    it("renders both ModeToggle buttons defaulting to board", async () => {
      const qc = makeQc();
      qc.setQueryData(queryKeys.sessions("p1"), []);
      qc.setQueryData(queryKeys.issues("p1"), []);
      qc.setQueryData(queryKeys.enum("p1", "issue_status"), { name: "x", values: [] });
      qc.setQueryData(queryKeys.inboxFiltered("p1", { bucket: "blocked" }), []);

      renderBoard({ qc });

      expect(screen.getByTestId("board-mode-board")).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByTestId("board-mode-graph")).toHaveAttribute("aria-pressed", "false");
    });

    it("renders SessionsGraphView when (view=sessions, mode=graph)", async () => {
      const qc = makeQc();
      qc.setQueryData(queryKeys.sessions("p1"), [
        makeSession({ id: "alpha", name: "Alpha", status: "executing" }),
      ]);
      qc.setQueryData(queryKeys.issues("p1"), []);
      qc.setQueryData(queryKeys.enum("p1", "issue_status"), { name: "x", values: [] });
      qc.setQueryData(queryKeys.inboxFiltered("p1", { bucket: "blocked" }), []);

      renderBoard({ qc, initialPath: "/p/p1/board?mode=graph" });

      expect(screen.getByTestId("sessions-graph-view")).toBeInTheDocument();
      // SessionFlow renders an SVG <g> per session with this testid.
      expect(screen.getByTestId("session-flow-node-alpha")).toBeInTheDocument();
    });

    it("renders IssuesGraphView when (view=issues, mode=graph)", async () => {
      const qc = makeQc();
      qc.setQueryData(queryKeys.sessions("p1"), []);
      qc.setQueryData(queryKeys.issues("p1"), [
        makeIssue({ id: "K-1", title: "Root issue" }),
        makeIssue({ id: "K-2", title: "Blocked by K-1", blocked_by: ["K-1"] }),
      ]);
      qc.setQueryData(queryKeys.enum("p1", "issue_status"), {
        name: "issue_status",
        values: [
          { value: "backlog", label: "Backlog", color: "#888", description: null },
          { value: "done", label: "Done", color: "#0a0", description: null },
        ],
      });
      qc.setQueryData(queryKeys.inboxFiltered("p1", { bucket: "blocked" }), []);

      renderBoard({ qc, initialPath: "/p/p1/board?view=issues&mode=graph" });

      expect(screen.getByTestId("issues-graph-view")).toBeInTheDocument();
      expect(screen.getByTestId("issues-graph-node-K-1")).toBeInTheDocument();
      expect(screen.getByTestId("issues-graph-node-K-2")).toBeInTheDocument();
    });

    it("clicking the graph button while on issues view persists mode=graph in the URL", async () => {
      const qc = makeQc();
      qc.setQueryData(queryKeys.sessions("p1"), []);
      qc.setQueryData(queryKeys.issues("p1"), []);
      qc.setQueryData(queryKeys.enum("p1", "issue_status"), { name: "x", values: [] });
      qc.setQueryData(queryKeys.inboxFiltered("p1", { bucket: "blocked" }), []);

      renderBoard({ qc, initialPath: "/p/p1/board?view=issues" });

      // Default mode is board on landing
      expect(screen.getByTestId("board-mode-board")).toHaveAttribute("aria-pressed", "true");
      fireEvent.click(screen.getByTestId("board-mode-graph"));
      expect(screen.getByTestId("board-mode-graph")).toHaveAttribute("aria-pressed", "true");
      // The graph quadrant for issues took over.
      expect(screen.getByTestId("issues-graph-empty")).toBeInTheDocument();
    });

    it("clicking an issue node in graph mode opens the entity drawer", async () => {
      const qc = makeQc();
      qc.setQueryData(queryKeys.sessions("p1"), []);
      qc.setQueryData(queryKeys.issues("p1"), [
        makeIssue({ id: "K-9", title: "Drawer me" }),
      ]);
      qc.setQueryData(queryKeys.enum("p1", "issue_status"), {
        name: "issue_status",
        values: [{ value: "backlog", label: "Backlog", color: null, description: null }],
      });
      qc.setQueryData(queryKeys.inboxFiltered("p1", { bucket: "blocked" }), []);

      renderBoard({ qc, initialPath: "/p/p1/board?view=issues&mode=graph" });

      fireEvent.click(screen.getByTestId("issues-graph-node-K-9"));
      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Drawer me" })).toBeInTheDocument();
      });
    });
  });
});
