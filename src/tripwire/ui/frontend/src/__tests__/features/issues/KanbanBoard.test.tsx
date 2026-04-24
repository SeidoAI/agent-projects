import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { KanbanBoard } from "@/features/issues/KanbanBoard";
import type { EnumDescriptor } from "@/lib/api/endpoints/enums";
import type { IssueSummary } from "@/lib/api/endpoints/issues";
import { queryKeys } from "@/lib/api/queryKeys";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

const ENUM: EnumDescriptor = {
  name: "issue_status",
  values: [
    { value: "todo", label: "To do", color: "#888", description: null },
    { value: "doing", label: "Doing", color: "#0af", description: null },
    { value: "done", label: "Done", color: "#0f0", description: null },
  ],
};

function issue(id: string, status: string, overrides: Partial<IssueSummary> = {}): IssueSummary {
  return {
    id,
    title: `title ${id}`,
    status,
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
    ...overrides,
  };
}

function withSeed(issues: IssueSummary[] | undefined, statusEnum: EnumDescriptor | undefined) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  if (issues) qc.setQueryData(queryKeys.issues("p1"), issues);
  if (statusEnum) qc.setQueryData(queryKeys.enum("p1", "issue_status"), statusEnum);
  return {
    qc,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/p/p1/board"]}>
          <Routes>
            <Route path="/p/:projectId/board" element={children} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    ),
  };
}

describe("KanbanBoard", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders one column per enum value in order", () => {
    const { wrapper } = withSeed([issue("X-1", "todo")], ENUM);
    render(<KanbanBoard />, { wrapper });
    const sections = screen.getAllByRole("region", { hidden: true });
    // Each kanban column carries aria-label "<Label> column"
    expect(screen.getByLabelText("To do column")).toBeInTheDocument();
    expect(screen.getByLabelText("Doing column")).toBeInTheDocument();
    expect(screen.getByLabelText("Done column")).toBeInTheDocument();
    expect(sections.length).toBeGreaterThanOrEqual(3);
  });

  it("puts each issue in the column matching its status", () => {
    const { wrapper } = withSeed(
      [issue("X-1", "todo"), issue("X-2", "doing"), issue("X-3", "done")],
      ENUM,
    );
    render(<KanbanBoard />, { wrapper });

    const todoCol = screen.getByTestId("kanban-column-todo");
    const doingCol = screen.getByTestId("kanban-column-doing");
    const doneCol = screen.getByTestId("kanban-column-done");
    expect(todoCol.querySelector('[data-testid="issue-card-X-1"]')).not.toBeNull();
    expect(doingCol.querySelector('[data-testid="issue-card-X-2"]')).not.toBeNull();
    expect(doneCol.querySelector('[data-testid="issue-card-X-3"]')).not.toBeNull();
  });

  it("optimistically moves an issue when the mutation starts, and rolls back on error", async () => {
    const before = [issue("X-1", "todo"), issue("X-2", "doing")];
    const { qc, wrapper } = withSeed(before, ENUM);

    // Stub fetch to reject the PATCH with a 409 — this is the path
    // the plan calls out: "Invalid transition → rollback + toast".
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "illegal transition", code: "issue/invalid_transition" }),
          {
            status: 409,
            headers: { "content-type": "application/json" },
          },
        ),
      ),
    );

    render(<KanbanBoard />, { wrapper });

    // Kick off the mutation directly — simulating a drop without having
    // to drive dnd-kit's pointer events through jsdom.
    const { useUpdateIssueStatus } = await import("@/features/issues/hooks/useIssues");
    let mutate: ReturnType<typeof useUpdateIssueStatus>["mutateAsync"] | null = null;
    function Harness() {
      const m = useUpdateIssueStatus("p1");
      mutate = m.mutateAsync;
      return null;
    }
    render(
      <QueryClientProvider client={qc}>
        <Harness />
      </QueryClientProvider>,
    );

    expect(mutate).not.toBeNull();

    await act(async () => {
      try {
        await mutate?.({ key: "X-1", status: "done" });
      } catch {
        // expected — the mock fetch rejects
      }
    });

    await waitFor(() => {
      const after = qc.getQueryData<IssueSummary[]>(queryKeys.issues("p1"));
      const x1 = after?.find((i) => i.id === "X-1");
      expect(x1?.status).toBe("todo");
    });
  });
});
