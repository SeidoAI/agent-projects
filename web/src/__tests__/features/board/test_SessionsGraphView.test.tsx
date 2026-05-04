import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionsGraphView } from "@/features/board/SessionsGraphView";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";

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

function Wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

describe("SessionsGraphView", () => {
  it("renders an empty-state message when no sessions are passed", () => {
    render(
      <Wrapper>
        <SessionsGraphView sessions={[]} onNodeClick={() => {}} />
      </Wrapper>,
    );
    expect(screen.getByText(/no sessions match/i)).toBeInTheDocument();
  });

  it("renders the underlying SessionFlow with one node per session", () => {
    const sessions = [
      makeSession({ id: "alpha", name: "Alpha", status: "executing" }),
      makeSession({ id: "beta", name: "Beta", status: "completed" }),
    ];
    render(
      <Wrapper>
        <SessionsGraphView sessions={sessions} onNodeClick={() => {}} />
      </Wrapper>,
    );
    expect(screen.getByTestId("sessions-graph-view")).toBeInTheDocument();
    expect(screen.getByTestId("session-flow-node-alpha")).toBeInTheDocument();
    // Far-completed sessions are culled by default unless they're a
    // direct neighbour of live work — without an edge to alpha,
    // beta is removed by `cullFarCompleted`.
    expect(screen.queryByTestId("session-flow-node-beta")).not.toBeInTheDocument();
  });

  it("show-all-completed toggle un-culls completed sessions", () => {
    const sessions = [
      makeSession({ id: "alpha", name: "Alpha", status: "executing" }),
      makeSession({ id: "beta", name: "Beta", status: "completed" }),
    ];
    render(
      <Wrapper>
        <SessionsGraphView sessions={sessions} onNodeClick={() => {}} />
      </Wrapper>,
    );
    expect(screen.queryByTestId("session-flow-node-beta")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("sessions-graph-show-all-completed"));
    expect(screen.getByTestId("session-flow-node-beta")).toBeInTheDocument();
  });

  it("invokes onNodeClick with the session matching the clicked node id", () => {
    const onNodeClick = vi.fn();
    const sessions = [makeSession({ id: "alpha", name: "Alpha", status: "executing" })];
    render(
      <Wrapper>
        <SessionsGraphView sessions={sessions} onNodeClick={onNodeClick} />
      </Wrapper>,
    );
    fireEvent.click(screen.getByTestId("session-flow-node-alpha"));
    expect(onNodeClick).toHaveBeenCalledTimes(1);
    expect(onNodeClick).toHaveBeenCalledWith(expect.objectContaining({ id: "alpha" }));
  });
});
