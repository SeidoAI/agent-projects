import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProcessQuality } from "@/features/process-quality/ProcessQuality";
import { queryKeys } from "@/lib/api/queryKeys";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

function withRoute(seeded: object | null) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  if (seeded) qc.setQueryData(queryKeys.workflowStats("p1", { top_n: 10 }), seeded);
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/p/p1/process-quality"]}>
        <Routes>
          <Route path="/p/:projectId/process-quality" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ProcessQuality", () => {
  afterEach(() => cleanup());

  it("renders the page heading", () => {
    const Wrapper = withRoute(null);
    render(<ProcessQuality />, { wrapper: Wrapper });
    expect(screen.getByRole("heading", { name: /process quality/i })).toBeInTheDocument();
  });

  it("renders kind histogram, instance histogram, and top rules from seeded data", () => {
    const Wrapper = withRoute({
      total: 7,
      by_kind: { "validator.run": 4, "jit_prompt.fired": 3 },
      by_instance: { "sess-1": 5, "sess-2": 2 },
      top_rules: [
        { id: "v_uuid_present", count: 4 },
        { id: "tw_self_review", count: 3 },
      ],
    });
    render(<ProcessQuality />, { wrapper: Wrapper });
    expect(screen.getByTestId("pq-kind-validator.run")).toBeInTheDocument();
    expect(screen.getByTestId("pq-kind-jit_prompt.fired")).toBeInTheDocument();
    expect(screen.getByTestId("pq-instance-sess-1")).toBeInTheDocument();
    expect(screen.getByText("v_uuid_present")).toBeInTheDocument();
    expect(screen.getByText("tw_self_review")).toBeInTheDocument();
  });

  it("kind row links to events screen filtered to that kind", () => {
    const Wrapper = withRoute({
      total: 4,
      by_kind: { "validator.run": 4 },
      by_instance: {},
      top_rules: [],
    });
    render(<ProcessQuality />, { wrapper: Wrapper });
    const link = screen.getByTestId("pq-kind-validator.run");
    expect(link).toHaveAttribute("href", expect.stringContaining("events?event=validator.run"));
  });

  it("renders empty states when there are no events", () => {
    const Wrapper = withRoute({
      total: 0,
      by_kind: {},
      by_instance: {},
      top_rules: [],
    });
    render(<ProcessQuality />, { wrapper: Wrapper });
    expect(screen.getByText(/no events yet/i)).toBeInTheDocument();
  });
});
