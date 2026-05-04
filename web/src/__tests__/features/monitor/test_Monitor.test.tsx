import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Monitor } from "@/features/monitor/Monitor";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { queryKeys } from "@/lib/api/queryKeys";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

afterEach(() => cleanup());

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

interface SeedOpts {
  sessions?: SessionSummary[];
  events?: { ts: string; workflow: string; instance: string; status: string; event: string; details: object }[];
}

function withRoute({ sessions = [], events = [] }: SeedOpts) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  qc.setQueryData(queryKeys.sessions("p1"), sessions);
  qc.setQueryData(queryKeys.workflowEvents("p1", {}), {
    events,
    total: events.length,
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/p/p1/monitor"]}>
        <Routes>
          <Route path="/p/:projectId/monitor" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Monitor", () => {
  // ===========================================================================
  // Page chrome
  // ===========================================================================
  it("renders the page heading + summary strip", () => {
    const Wrapper = withRoute({});
    render(<Monitor />, { wrapper: Wrapper });
    expect(screen.getByRole("heading", { level: 1, name: /monitor/i })).toBeInTheDocument();
    expect(screen.getByTestId("monitor-summary")).toBeInTheDocument();
    expect(screen.getByTestId("monitor-stat-active")).toHaveTextContent("0");
    expect(screen.getByTestId("monitor-stat-total")).toHaveTextContent("0");
    expect(screen.getByTestId("monitor-stat-tripwires")).toHaveTextContent("0");
  });

  // ===========================================================================
  // Empty states
  // ===========================================================================
  it("renders the no-sessions empty state when zero sessions exist", () => {
    const Wrapper = withRoute({});
    render(<Monitor />, { wrapper: Wrapper });
    expect(screen.getByTestId("monitor-empty")).toBeInTheDocument();
    expect(screen.getByText(/no sessions exist yet/i)).toBeInTheDocument();
  });

  it("renders the all-idle empty state when sessions exist but none are live", () => {
    const Wrapper = withRoute({
      sessions: [
        makeSession({ id: "old-1", status: "completed" }),
        makeSession({ id: "old-2", status: "verified" }),
      ],
    });
    render(<Monitor />, { wrapper: Wrapper });
    expect(screen.getByTestId("monitor-empty")).toBeInTheDocument();
    expect(screen.getByText(/2 sessions on file/i)).toBeInTheDocument();
  });

  // ===========================================================================
  // Active session cards
  // ===========================================================================
  it("renders one card per active session and skips idle sessions", () => {
    const Wrapper = withRoute({
      sessions: [
        makeSession({ id: "live-1", name: "Live one", status: "executing" }),
        makeSession({ id: "live-2", name: "Live two", status: "in_review" }),
        makeSession({ id: "done", name: "Finished", status: "completed" }),
      ],
    });
    render(<Monitor />, { wrapper: Wrapper });
    expect(screen.getByTestId("monitor-session-live-1")).toBeInTheDocument();
    expect(screen.getByTestId("monitor-session-live-2")).toBeInTheDocument();
    expect(screen.queryByTestId("monitor-session-done")).not.toBeInTheDocument();
    expect(screen.getByTestId("monitor-stat-active")).toHaveTextContent("2");
    expect(screen.getByTestId("monitor-stat-total")).toHaveTextContent("3");
  });

  it("renders status, agent, and progress bar for each card", () => {
    const Wrapper = withRoute({
      sessions: [
        makeSession({
          id: "alpha",
          name: "Alpha",
          status: "executing",
          agent: "backend-coder",
          task_progress: { done: 3, total: 5 },
        }),
      ],
    });
    render(<Monitor />, { wrapper: Wrapper });
    const card = screen.getByTestId("monitor-session-alpha");
    expect(within(card).getByText(/backend-coder/)).toBeInTheDocument();
    expect(within(card).getByText("3 / 5")).toBeInTheDocument();
    expect(within(card).getByTestId("monitor-progress-bar")).toHaveStyle({ width: "60%" });
    expect(within(card).getByTestId("monitor-session-alpha-status")).toHaveTextContent(/executing/);
  });

  it("renders linked PR badges when the session has repo bindings", () => {
    const Wrapper = withRoute({
      sessions: [
        makeSession({
          id: "alpha",
          status: "executing",
          repos: [
            { repo: "acme/web", base_branch: "main", branch: "feat/a", pr_number: 42 },
            { repo: "acme/api", base_branch: "main", branch: "feat/a", pr_number: 7 },
          ],
        }),
      ],
    });
    render(<Monitor />, { wrapper: Wrapper });
    const card = screen.getByTestId("monitor-session-alpha");
    expect(within(card).getByText("acme/web#42")).toBeInTheDocument();
    expect(within(card).getByText("acme/api#7")).toBeInTheDocument();
  });

  it("renders the no-PRs hint when the session has no PR bindings", () => {
    const Wrapper = withRoute({
      sessions: [
        makeSession({
          id: "alpha",
          status: "executing",
          repos: [
            // Branch but no PR yet — common state for sessions that
            // just spawned and haven't pushed.
            { repo: "acme/web", base_branch: "main", branch: "feat/a", pr_number: null },
          ],
        }),
      ],
    });
    render(<Monitor />, { wrapper: Wrapper });
    const card = screen.getByTestId("monitor-session-alpha");
    expect(within(card).getByTestId("monitor-prs-none")).toBeInTheDocument();
  });

  // ===========================================================================
  // Tripwire correlation
  // ===========================================================================
  it("counts only jit_prompt.fired events per session, ignoring other event kinds", () => {
    const Wrapper = withRoute({
      sessions: [
        makeSession({ id: "alpha", status: "executing" }),
        makeSession({ id: "beta", status: "executing" }),
      ],
      events: [
        {
          ts: "2026-04-30T14:00:00Z",
          workflow: "wf",
          instance: "alpha",
          status: "executing",
          event: "jit_prompt.fired",
          details: { id: "tw_self_review" },
        },
        {
          ts: "2026-04-30T14:01:00Z",
          workflow: "wf",
          instance: "alpha",
          status: "executing",
          event: "jit_prompt.fired",
          details: { id: "tw_write_count" },
        },
        {
          // Validator runs are not tripwires — should be ignored.
          ts: "2026-04-30T14:02:00Z",
          workflow: "wf",
          instance: "alpha",
          status: "executing",
          event: "validator.run",
          details: { id: "v_uuid_present", outcome: "pass" },
        },
        {
          ts: "2026-04-30T14:03:00Z",
          workflow: "wf",
          instance: "beta",
          status: "executing",
          event: "jit_prompt.fired",
          details: { id: "tw_phase_transition" },
        },
      ],
    });
    render(<Monitor />, { wrapper: Wrapper });
    expect(screen.getByTestId("monitor-session-alpha")).toHaveAttribute("data-fires", "2");
    expect(screen.getByTestId("monitor-session-beta")).toHaveAttribute("data-fires", "1");
    expect(screen.getByTestId("monitor-stat-tripwires")).toHaveTextContent("3");
  });

  it("renders the tripwire badge with last-fire timestamp when fires exist", () => {
    const Wrapper = withRoute({
      sessions: [makeSession({ id: "alpha", status: "executing" })],
      events: [
        {
          ts: "2026-04-30T14:00:00Z",
          workflow: "wf",
          instance: "alpha",
          status: "executing",
          event: "jit_prompt.fired",
          details: { id: "tw_self_review" },
        },
        {
          ts: "2026-04-30T14:30:00Z",
          workflow: "wf",
          instance: "alpha",
          status: "executing",
          event: "jit_prompt.fired",
          details: { id: "tw_write_count" },
        },
      ],
    });
    render(<Monitor />, { wrapper: Wrapper });
    const card = screen.getByTestId("monitor-session-alpha");
    expect(within(card).getByTestId("monitor-tripwires")).toHaveTextContent(/2.*tripwires/);
    // Newest fire wins for the "last" timestamp display.
    expect(within(card).getByTestId("monitor-tripwires-last")).toHaveTextContent("14:30:00");
  });

  it("renders the no-tripwires placeholder for sessions with zero fires", () => {
    const Wrapper = withRoute({
      sessions: [makeSession({ id: "clean", status: "executing" })],
    });
    render(<Monitor />, { wrapper: Wrapper });
    const card = screen.getByTestId("monitor-session-clean");
    expect(within(card).getByTestId("monitor-tripwires-none")).toBeInTheDocument();
  });

  // ===========================================================================
  // Cross-cutting
  // ===========================================================================
  it("session id is a deep-link to the session detail page", () => {
    const Wrapper = withRoute({
      sessions: [makeSession({ id: "alpha", name: "Alpha", status: "executing" })],
    });
    render(<Monitor />, { wrapper: Wrapper });
    const link = screen.getByRole("link", { name: "alpha" });
    expect(link).toHaveAttribute("href", "/p/p1/sessions/alpha");
  });
});
