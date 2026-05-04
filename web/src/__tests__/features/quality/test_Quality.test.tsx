import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Quality } from "@/features/quality/Quality";
import { queryKeys } from "@/lib/api/queryKeys";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

interface SeedOpts {
  stats?: object | null;
  events?: object[] | null;
  initialEntry?: string;
}

function withRoute({ stats = null, events = null, initialEntry = "/p/p1/quality" }: SeedOpts = {}) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  if (stats) qc.setQueryData(queryKeys.workflowStats("p1", { top_n: 10 }), stats);
  if (events) {
    // The events panel rebuilds the query key from URL params; we
    // only seed the empty-filter shape (the default landing).
    qc.setQueryData(queryKeys.workflowEvents("p1", {}), {
      events,
      total: events.length,
    });
  }
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/p/:projectId/quality" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Quality", () => {
  afterEach(() => cleanup());

  // ===========================================================================
  // Page chrome
  // ===========================================================================
  it("renders the page heading", () => {
    const Wrapper = withRoute();
    render(<Quality />, { wrapper: Wrapper });
    expect(screen.getByRole("heading", { level: 1, name: /quality/i })).toBeInTheDocument();
  });

  it("renders both tab buttons", () => {
    const Wrapper = withRoute();
    render(<Quality />, { wrapper: Wrapper });
    expect(screen.getByTestId("tab-stats")).toBeInTheDocument();
    expect(screen.getByTestId("tab-events")).toBeInTheDocument();
  });

  it("defaults to stats tab when ?tab is absent", () => {
    const Wrapper = withRoute();
    render(<Quality />, { wrapper: Wrapper });
    expect(screen.getByTestId("tab-stats")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("tab-events")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("pq-by-kind")).toBeInTheDocument();
  });

  it("opens directly to events tab when ?tab=events", () => {
    const Wrapper = withRoute({ initialEntry: "/p/p1/quality?tab=events" });
    render(<Quality />, { wrapper: Wrapper });
    expect(screen.getByTestId("tab-events")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("event-log-list")).toBeInTheDocument();
  });

  it("clicking events tab swaps the panel content", () => {
    const Wrapper = withRoute();
    render(<Quality />, { wrapper: Wrapper });
    expect(screen.getByTestId("pq-by-kind")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("tab-events"));
    expect(screen.queryByTestId("pq-by-kind")).not.toBeInTheDocument();
    expect(screen.getByTestId("event-log-list")).toBeInTheDocument();
  });

  // ===========================================================================
  // Stats panel — preserves original ProcessQuality coverage
  // ===========================================================================
  it("renders kind histogram, instance histogram, and top rules from seeded data", () => {
    const Wrapper = withRoute({
      stats: {
        total: 7,
        by_kind: { "validator.run": 4, "jit_prompt.fired": 3 },
        by_instance: { "sess-1": 5, "sess-2": 2 },
        top_rules: [
          { id: "v_uuid_present", count: 4 },
          { id: "tw_self_review", count: 3 },
        ],
      },
    });
    render(<Quality />, { wrapper: Wrapper });
    expect(screen.getByTestId("pq-kind-validator.run")).toBeInTheDocument();
    expect(screen.getByTestId("pq-kind-jit_prompt.fired")).toBeInTheDocument();
    expect(screen.getByTestId("pq-instance-sess-1")).toBeInTheDocument();
    expect(screen.getByText("v_uuid_present")).toBeInTheDocument();
    expect(screen.getByText("tw_self_review")).toBeInTheDocument();
  });

  it("clicking a kind row drills into the events tab with that kind filter applied", () => {
    const Wrapper = withRoute({
      stats: {
        total: 4,
        by_kind: { "validator.run": 4 },
        by_instance: {},
        top_rules: [],
      },
    });
    render(<Quality />, { wrapper: Wrapper });
    const drillButton = screen.getByTestId("pq-kind-validator.run");
    fireEvent.click(drillButton);
    // Tab swaps to events
    expect(screen.getByTestId("tab-events")).toHaveAttribute("aria-pressed", "true");
    // Filter chip for the chosen kind reads as active in the events filter strip
    expect(screen.getByTestId("filter-kind-validator.run").className).toContain(
      "bg-(--color-ink)",
    );
  });

  it("clicking an instance row drills into the events tab with that instance filter applied", () => {
    const Wrapper = withRoute({
      stats: {
        total: 4,
        by_kind: {},
        by_instance: { "sess-42": 4 },
        top_rules: [],
      },
    });
    render(<Quality />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId("pq-instance-sess-42"));
    expect(screen.getByTestId("tab-events")).toHaveAttribute("aria-pressed", "true");
    expect((screen.getByTestId("filter-instance") as HTMLInputElement).value).toBe("sess-42");
  });

  it("renders empty states when there are no events", () => {
    const Wrapper = withRoute({
      stats: {
        total: 0,
        by_kind: {},
        by_instance: {},
        top_rules: [],
      },
    });
    render(<Quality />, { wrapper: Wrapper });
    expect(screen.getAllByText(/no events yet/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/no rule fires yet/i)).toBeInTheDocument();
  });

  // ===========================================================================
  // Events panel — preserves original EventLog coverage
  // ===========================================================================
  it("events tab renders one row per event from the seeded query cache", () => {
    const events = [
      {
        ts: "2026-04-30T14:00:00Z",
        workflow: "coding-session",
        instance: "sess-1",
        status: "executing",
        event: "validator.run",
        details: { id: "v_uuid_present", outcome: "pass" },
      },
      {
        ts: "2026-04-30T14:01:00Z",
        workflow: "coding-session",
        instance: "sess-1",
        status: "in_review",
        event: "transition.completed",
        details: { from_status: "executing", to_status: "in_review" },
      },
    ];
    const Wrapper = withRoute({ events, initialEntry: "/p/p1/quality?tab=events" });
    render(<Quality />, { wrapper: Wrapper });
    const rows = screen.getAllByTestId("event-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("data-event-kind", "validator.run");
    expect(rows[1]).toHaveAttribute("data-event-kind", "transition.completed");
  });

  it("events tab renders all kind filter chips", () => {
    const Wrapper = withRoute({ initialEntry: "/p/p1/quality?tab=events" });
    render(<Quality />, { wrapper: Wrapper });
    expect(screen.getByTestId("filter-kind-validator.run")).toBeInTheDocument();
    expect(screen.getByTestId("filter-kind-jit_prompt.fired")).toBeInTheDocument();
    expect(screen.getByTestId("filter-kind-prompt_check.invoked")).toBeInTheDocument();
  });

  it("clicking a kind filter chip activates it", () => {
    const Wrapper = withRoute({ initialEntry: "/p/p1/quality?tab=events" });
    render(<Quality />, { wrapper: Wrapper });
    const chip = screen.getByTestId("filter-kind-validator.run");
    fireEvent.click(chip);
    expect(chip.className).toContain("bg-(--color-ink)");
  });

  it("events tab renders an empty state when the events list is empty", () => {
    const Wrapper = withRoute({ events: [], initialEntry: "/p/p1/quality?tab=events" });
    render(<Quality />, { wrapper: Wrapper });
    expect(screen.getByText(/no events yet/i)).toBeInTheDocument();
  });

  it("events tab renders distinct rows even when the (workflow, instance, status, event, ts, details.id) tuple collides", () => {
    const collidingEvents = [
      {
        ts: "2026-04-30T14:00:00Z",
        workflow: "coding-session",
        instance: "sess-1",
        status: "executing",
        event: "validator.run",
        details: { id: "v_uuid_present", outcome: "pass" },
      },
      {
        ts: "2026-04-30T14:00:00Z",
        workflow: "coding-session",
        instance: "sess-1",
        status: "executing",
        event: "validator.run",
        details: { id: "v_uuid_present", outcome: "pass" },
      },
      {
        ts: "2026-04-30T14:00:00Z",
        workflow: "coding-session",
        instance: "sess-1",
        status: "executing",
        event: "validator.run",
        details: { id: "v_uuid_present", outcome: "pass" },
      },
    ];
    const Wrapper = withRoute({
      events: collidingEvents,
      initialEntry: "/p/p1/quality?tab=events",
    });
    render(<Quality />, { wrapper: Wrapper });
    expect(screen.getAllByTestId("event-row")).toHaveLength(3);
  });

  it("events tab clear button resets all filters but stays on the events tab", () => {
    const Wrapper = withRoute({
      initialEntry: "/p/p1/quality?tab=events&event=validator.run&instance=sess-1",
    });
    render(<Quality />, { wrapper: Wrapper });
    expect((screen.getByTestId("filter-instance") as HTMLInputElement).value).toBe("sess-1");
    fireEvent.click(screen.getByTestId("filter-clear-all"));
    expect((screen.getByTestId("filter-instance") as HTMLInputElement).value).toBe("");
    // Stayed on events tab
    expect(screen.getByTestId("tab-events")).toHaveAttribute("aria-pressed", "true");
  });
});
