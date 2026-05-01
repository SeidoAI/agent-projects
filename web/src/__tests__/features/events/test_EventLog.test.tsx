import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EventLog } from "@/features/events/EventLog";
import { queryKeys } from "@/lib/api/queryKeys";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

function withRoute(initialEntry = "/p/p1/events") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/p/:projectId/events" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function withSeededRoute(events: object[], initialEntry = "/p/p1/events") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  // Seed every filter combination the component might try — the
  // hook rebuilds the queryKey from URL params, so we only seed the
  // empty-filter shape here.
  qc.setQueryData(queryKeys.workflowEvents("p1", {}), {
    events,
    total: events.length,
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/p/:projectId/events" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("EventLog", () => {
  afterEach(() => cleanup());

  it("renders the page header with title", () => {
    const Wrapper = withRoute();
    render(<EventLog />, { wrapper: Wrapper });
    expect(screen.getByRole("heading", { name: /events/i })).toBeInTheDocument();
  });

  it("renders one row per event from the seeded query cache", () => {
    const events = [
      {
        ts: "2026-04-30T14:00:00Z",
        workflow: "coding-session",
        instance: "sess-1",
        station: "executing",
        event: "validator.run",
        details: { id: "v_uuid_present", outcome: "pass" },
      },
      {
        ts: "2026-04-30T14:01:00Z",
        workflow: "coding-session",
        instance: "sess-1",
        station: "in_review",
        event: "transition.completed",
        details: { from_station: "executing", to_station: "in_review" },
      },
    ];
    const Wrapper = withSeededRoute(events);
    render(<EventLog />, { wrapper: Wrapper });
    const rows = screen.getAllByTestId("event-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("data-event-kind", "validator.run");
    expect(rows[1]).toHaveAttribute("data-event-kind", "transition.completed");
  });

  it("renders all kind filter chips", () => {
    const Wrapper = withRoute();
    render(<EventLog />, { wrapper: Wrapper });
    expect(screen.getByTestId("filter-kind-validator.run")).toBeInTheDocument();
    expect(screen.getByTestId("filter-kind-jit_prompt.fired")).toBeInTheDocument();
    expect(screen.getByTestId("filter-kind-prompt_check.invoked")).toBeInTheDocument();
  });

  it("clicking a kind filter chip persists in the URL", () => {
    const Wrapper = withRoute();
    render(<EventLog />, { wrapper: Wrapper });
    const chip = screen.getByTestId("filter-kind-validator.run");
    fireEvent.click(chip);
    // After click the URL params include `event=validator.run` —
    // we re-render with that and confirm the chip is active.
    // Reading the URL inside MemoryRouter requires inspecting the
    // chip's class; a chip is "active" when the inverse style is
    // applied, surfaced via the className we set in chipClass().
    expect(chip.className).toContain("bg-(--color-ink)");
  });

  it("renders an empty state when the events list is empty", () => {
    const Wrapper = withSeededRoute([]);
    render(<EventLog />, { wrapper: Wrapper });
    expect(screen.getByText(/no events yet/i)).toBeInTheDocument();
  });

  it("renders distinct rows even when (workflow, instance, station, event, ts, details.id) collide", () => {
    // Codex P1: events log emits at second granularity, so a dense
    // burst of identical-tuple rows must still produce unique React
    // keys + clickable rows. The synthId fallback adds an
    // occurrence-count suffix `|#N` so each row gets its own key.
    const collidingEvents = [
      {
        ts: "2026-04-30T14:00:00Z",
        workflow: "coding-session",
        instance: "sess-1",
        station: "executing",
        event: "validator.run",
        details: { id: "v_uuid_present", outcome: "pass" },
      },
      {
        ts: "2026-04-30T14:00:00Z",
        workflow: "coding-session",
        instance: "sess-1",
        station: "executing",
        event: "validator.run",
        details: { id: "v_uuid_present", outcome: "pass" },
      },
      {
        ts: "2026-04-30T14:00:00Z",
        workflow: "coding-session",
        instance: "sess-1",
        station: "executing",
        event: "validator.run",
        details: { id: "v_uuid_present", outcome: "pass" },
      },
    ];
    const Wrapper = withSeededRoute(collidingEvents);
    render(<EventLog />, { wrapper: Wrapper });
    const rows = screen.getAllByTestId("event-row");
    // Three rows render even though their underlying tuples are
    // identical — keys disambiguate via the per-render counter.
    expect(rows).toHaveLength(3);
  });
});
