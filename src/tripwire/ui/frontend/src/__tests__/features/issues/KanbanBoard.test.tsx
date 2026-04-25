import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { type ReactNode, useEffect } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  type UpdateStatusVariables,
  useUpdateIssueStatus,
} from "@/features/issues/hooks/useIssues";
import { KanbanBoard } from "@/features/issues/KanbanBoard";
import type { EnumDescriptor } from "@/lib/api/endpoints/enums";
import type { IssueFilterParams, IssueSummary } from "@/lib/api/endpoints/issues";
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
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
}

function withClient(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/p/p1/board"]}>
        <Routes>
          <Route path="/p/:projectId/board" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

/**
 * A tiny sibling that exposes the mutation to the test — rendered
 * inside the SAME QueryClientProvider as the board so the optimistic
 * write + rollback show up in the board's render tree. The previous
 * version of this test rendered the harness in a separate tree, which
 * meant the "did the UI actually roll back?" question went untested:
 * the cache read looked fine even when the board's subscription was
 * wired wrong.
 */
function MutationHarness({
  onReady,
}: {
  onReady: (mutate: (v: UpdateStatusVariables) => Promise<IssueSummary>) => void;
}) {
  const m = useUpdateIssueStatus("p1");
  useEffect(() => {
    onReady(m.mutateAsync);
  }, [m.mutateAsync, onReady]);
  return null;
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
    const qc = makeClient();
    qc.setQueryData(queryKeys.issues("p1"), [issue("X-1", "todo")]);
    qc.setQueryData(queryKeys.enum("p1", "issue_status"), ENUM);
    render(<KanbanBoard />, { wrapper: withClient(qc) });
    expect(screen.getByLabelText("To do column")).toBeInTheDocument();
    expect(screen.getByLabelText("Doing column")).toBeInTheDocument();
    expect(screen.getByLabelText("Done column")).toBeInTheDocument();
  });

  it("puts each issue in the column matching its status", () => {
    const qc = makeClient();
    qc.setQueryData(queryKeys.issues("p1"), [
      issue("X-1", "todo"),
      issue("X-2", "doing"),
      issue("X-3", "done"),
    ]);
    qc.setQueryData(queryKeys.enum("p1", "issue_status"), ENUM);
    render(<KanbanBoard />, { wrapper: withClient(qc) });

    expect(
      within(screen.getByTestId("kanban-column-todo")).getByTestId("issue-card-X-1"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("kanban-column-doing")).getByTestId("issue-card-X-2"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("kanban-column-done")).getByTestId("issue-card-X-3"),
    ).toBeInTheDocument();
  });

  it("rolls the card back to its original column when the server rejects the move", async () => {
    // Stubbed fetch: GET returns the seeded list so `invalidateQueries`
    // after the failed PATCH reconverges to consistent state; PATCH
    // rejects with the 409 the plan calls out as "invalid transition".
    const persisted = [issue("X-1", "todo"), issue("X-2", "doing")];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
        const method = (init?.method ?? "GET").toUpperCase();
        if (method === "PATCH") {
          return Promise.resolve(
            new Response(
              JSON.stringify({ detail: "illegal transition", code: "issue/invalid_transition" }),
              { status: 409, headers: { "content-type": "application/json" } },
            ),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify(persisted), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      }),
    );

    const qc = makeClient();
    qc.setQueryData(queryKeys.issues("p1"), persisted);
    qc.setQueryData(queryKeys.enum("p1", "issue_status"), ENUM);

    let mutate: ((v: UpdateStatusVariables) => Promise<IssueSummary>) | null = null;
    render(
      <>
        <KanbanBoard />
        <MutationHarness
          onReady={(m) => {
            mutate = m;
          }}
        />
      </>,
      { wrapper: withClient(qc) },
    );

    // Before the move, X-1 is in "todo".
    expect(
      within(screen.getByTestId("kanban-column-todo")).getByTestId("issue-card-X-1"),
    ).toBeInTheDocument();

    await waitFor(() => expect(mutate).not.toBeNull());

    await act(async () => {
      try {
        await mutate?.({ key: "X-1", status: "done" });
      } catch {
        // expected — mocked PATCH rejects
      }
    });

    // After the failure, the board's rendered output must show X-1
    // back in "todo" — the rollback is meaningful only if the UI
    // re-renders with the restored data.
    await waitFor(() => {
      expect(
        within(screen.getByTestId("kanban-column-todo")).getByTestId("issue-card-X-1"),
      ).toBeInTheDocument();
    });
    expect(
      within(screen.getByTestId("kanban-column-done")).queryByTestId("issue-card-X-1"),
    ).toBeNull();
  });

  it("rolls back filtered cache entries as well as the unfiltered list", async () => {
    // When the dashboard deep-links the board with `?status=todo`,
    // the TanStack entry is `issuesFiltered(pid, { status: 'todo' })`.
    // The mutation must touch both keys or the filtered view stays
    // stale after a rejected move.
    // Same dispatch pattern as the other rollback test — GET returns
    // the pre-move state so the invalidate-triggered refetch doesn't
    // flip the query into an error.
    const filters: IssueFilterParams = { status: "todo" };
    const originalList = [issue("X-1", "todo"), issue("X-2", "doing")];
    const originalFiltered = [issue("X-1", "todo")];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        const method = (init?.method ?? "GET").toUpperCase();
        if (method === "PATCH") {
          return Promise.resolve(
            new Response(
              JSON.stringify({ detail: "illegal transition", code: "issue/invalid_transition" }),
              { status: 409, headers: { "content-type": "application/json" } },
            ),
          );
        }
        const body = url.includes("status=todo") ? originalFiltered : originalList;
        return Promise.resolve(
          new Response(JSON.stringify(body), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      }),
    );

    const qc = makeClient();
    qc.setQueryData(queryKeys.issues("p1"), originalList);
    qc.setQueryData(queryKeys.issuesFiltered("p1", filters), originalFiltered);

    let mutate: ((v: UpdateStatusVariables) => Promise<IssueSummary>) | null = null;
    render(
      <QueryClientProvider client={qc}>
        <MutationHarness
          onReady={(m) => {
            mutate = m;
          }}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(mutate).not.toBeNull());

    await act(async () => {
      try {
        await mutate?.({ key: "X-1", status: "done" });
      } catch {
        // expected
      }
    });

    // Both cache entries must have been rolled back. The prefix cancel
    // + per-entry snapshot/restore means `data-X-1.status === "todo"`
    // in both caches after the failure.
    await waitFor(() => {
      const list = qc.getQueryData<IssueSummary[]>(queryKeys.issues("p1"));
      const filtered = qc.getQueryData<IssueSummary[]>(queryKeys.issuesFiltered("p1", filters));
      expect(list?.find((i) => i.id === "X-1")?.status).toBe("todo");
      expect(filtered?.find((i) => i.id === "X-1")?.status).toBe("todo");
    });
  });
});
