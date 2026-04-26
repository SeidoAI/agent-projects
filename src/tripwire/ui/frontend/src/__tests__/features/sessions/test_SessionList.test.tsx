import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionList } from "@/features/sessions/SessionList";
import { queryKeys } from "@/lib/api/queryKeys";
import { makeSessionSummary } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { makeTestQueryClient, renderWithProviders } from "../../test-utils";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

afterEach(() => {
  cleanup();
});

describe("SessionList", () => {
  it("renders a card per session with name, agent, and task progress", () => {
    const qc = makeTestQueryClient();
    qc.setQueryData(queryKeys.sessions("p1"), [
      makeSessionSummary({
        id: "a",
        name: "Session A",
        agent: "backend-coder",
        issues: ["KUI-1", "KUI-2"],
        estimated_size: "M",
        task_progress: { done: 2, total: 5 },
      }),
      makeSessionSummary({
        id: "b",
        name: "Session B",
        agent: "backend-coder",
        status: "planned",
        issues: ["KUI-3"],
        task_progress: { done: 0, total: 0 },
      }),
    ]);
    renderWithProviders(<SessionList />, { queryClient: qc });

    expect(screen.getByText("Session A")).toBeInTheDocument();
    expect(screen.getByText("Session B")).toBeInTheDocument();
    expect(screen.getAllByText(/backend-coder/).length).toBeGreaterThan(0);
    expect(screen.getByText("2/5")).toBeInTheDocument();
    expect(screen.getAllByTestId("task-progress-empty").length).toBeGreaterThan(0);
  });

  it("forwards the chosen status to the backend as ?status=<value>", async () => {
    // Capture the URL the refetch hits — confirming the
    // status filter selector actually pushes the value through
    // the query key, not just bumping local state.
    const requested: string[] = [];
    server.use(
      http.get("/api/projects/p1/sessions", ({ request }) => {
        requested.push(request.url);
        return HttpResponse.json([]);
      }),
    );

    const qc = makeTestQueryClient();
    qc.setQueryData(queryKeys.sessions("p1"), [
      makeSessionSummary({ id: "a", status: "active" }),
      makeSessionSummary({ id: "b", status: "planned", name: "Planned one" }),
    ]);
    renderWithProviders(<SessionList />, { queryClient: qc });

    fireEvent.change(screen.getByLabelText("Filter sessions by status"), {
      target: { value: "active" },
    });

    await waitFor(() => expect(requested.length).toBeGreaterThan(0));
    expect(requested.some((u) => new URL(u).searchParams.get("status") === "active")).toBe(true);
  });

  it("hides blocked 'planned' sessions when Only actionable is on", () => {
    const qc = makeTestQueryClient();
    qc.setQueryData(queryKeys.sessions("p1"), [
      makeSessionSummary({
        id: "blocked",
        name: "Blocked",
        status: "planned",
        blocked_by_sessions: ["upstream"],
      }),
      makeSessionSummary({
        id: "upstream",
        name: "Upstream",
        status: "active",
        blocked_by_sessions: [],
      }),
    ]);
    renderWithProviders(<SessionList />, { queryClient: qc });

    expect(screen.getByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText("Upstream")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Only actionable/));

    expect(screen.queryByText("Blocked")).not.toBeInTheDocument();
    expect(screen.getByText("Upstream")).toBeInTheDocument();
  });

  it("renders the empty state when there are no sessions", () => {
    const qc = makeTestQueryClient();
    qc.setQueryData(queryKeys.sessions("p1"), []);
    renderWithProviders(<SessionList />, { queryClient: qc });

    expect(screen.getByText(/No sessions yet. The PM agent creates sessions/)).toBeInTheDocument();
  });
});
