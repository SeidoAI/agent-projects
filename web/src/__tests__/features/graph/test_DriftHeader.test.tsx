import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DriftHeader } from "@/features/graph/DriftHeader";
import type { DriftReport } from "@/lib/api/endpoints/drift";
import { queryKeys } from "@/lib/api/queryKeys";

afterEach(() => cleanup());

function withSeed(report: DriftReport | null) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  if (report) qc.setQueryData(queryKeys.drift("p1"), report);
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const ALL_OK: DriftReport = {
  score: 100,
  breakdown: {
    stale_pins: 0,
    unresolved_refs: 0,
    stale_concepts: 0,
    workflow_drift_findings: 0,
  },
  workflow_drift_findings: [],
};

describe("DriftHeader", () => {
  it("renders coherence score from the seeded report", () => {
    const wrapper = withSeed({
      ...ALL_OK,
      score: 87,
    });
    render(
      <DriftHeader
        projectId="p1"
        staleCount={0}
        staleOnly={false}
        onToggleStaleOnly={() => {}}
      />,
      { wrapper },
    );
    expect(screen.getByTestId("drift-score")).toHaveTextContent("87");
  });

  it("renders the per-class breakdown numbers", () => {
    const wrapper = withSeed({
      score: 73,
      breakdown: {
        stale_pins: 4,
        unresolved_refs: 2,
        stale_concepts: 11,
        workflow_drift_findings: 1,
      },
      workflow_drift_findings: [
        {
          code: "missing_required_check",
          workflow: "wf",
          instance: "sess-1",
          status: "executing",
          severity: "warning",
          message: "demo",
        },
      ],
    });
    render(
      <DriftHeader
        projectId="p1"
        staleCount={11}
        staleOnly={false}
        onToggleStaleOnly={() => {}}
      />,
      { wrapper },
    );
    expect(screen.getByTestId("drift-stale-pins")).toHaveTextContent("4");
    expect(screen.getByTestId("drift-unresolved-refs")).toHaveTextContent("2");
    expect(screen.getByTestId("drift-stale-concepts")).toHaveTextContent("11");
    expect(screen.getByTestId("drift-workflow")).toHaveTextContent("1");
  });

  it("uses the green (ok) tone when score >= 90", () => {
    const wrapper = withSeed({ ...ALL_OK, score: 95 });
    render(
      <DriftHeader
        projectId="p1"
        staleCount={0}
        staleOnly={false}
        onToggleStaleOnly={() => {}}
      />,
      { wrapper },
    );
    expect(screen.getByTestId("drift-header")).toHaveAttribute("data-tone", "ok");
  });

  it("uses the amber (warn) tone when score is between 70 and 89", () => {
    const wrapper = withSeed({ ...ALL_OK, score: 80 });
    render(
      <DriftHeader
        projectId="p1"
        staleCount={3}
        staleOnly={false}
        onToggleStaleOnly={() => {}}
      />,
      { wrapper },
    );
    expect(screen.getByTestId("drift-header")).toHaveAttribute("data-tone", "warn");
  });

  it("uses the red (alert) tone when score is below 70", () => {
    const wrapper = withSeed({ ...ALL_OK, score: 42 });
    render(
      <DriftHeader
        projectId="p1"
        staleCount={20}
        staleOnly={false}
        onToggleStaleOnly={() => {}}
      />,
      { wrapper },
    );
    expect(screen.getByTestId("drift-header")).toHaveAttribute("data-tone", "alert");
  });

  it("renders a placeholder while the drift query is loading", () => {
    const wrapper = withSeed(null);
    render(
      <DriftHeader
        projectId="p1"
        staleCount={0}
        staleOnly={false}
        onToggleStaleOnly={() => {}}
      />,
      { wrapper },
    );
    expect(screen.getByTestId("drift-score")).toHaveTextContent("…");
    expect(screen.getByTestId("drift-header")).toHaveAttribute("data-tone", "loading");
  });

  it("disables the stale-only toggle when there are no stale nodes", () => {
    const wrapper = withSeed(ALL_OK);
    render(
      <DriftHeader
        projectId="p1"
        staleCount={0}
        staleOnly={false}
        onToggleStaleOnly={() => {}}
      />,
      { wrapper },
    );
    const btn = screen.getByTestId("drift-stale-only-toggle");
    expect(btn).toBeDisabled();
    expect(btn).toHaveTextContent(/no stale nodes/i);
  });

  it("shows the stale count and fires the toggle when there are stale nodes", () => {
    const onToggle = vi.fn();
    const wrapper = withSeed({ ...ALL_OK, score: 78 });
    render(
      <DriftHeader
        projectId="p1"
        staleCount={7}
        staleOnly={false}
        onToggleStaleOnly={onToggle}
      />,
      { wrapper },
    );
    const btn = screen.getByTestId("drift-stale-only-toggle");
    expect(btn).not.toBeDisabled();
    expect(btn).toHaveTextContent(/show stale only · 7/i);
    fireEvent.click(btn);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("reflects the staleOnly prop with aria-pressed=true when active", () => {
    const wrapper = withSeed({ ...ALL_OK, score: 78 });
    render(
      <DriftHeader
        projectId="p1"
        staleCount={5}
        staleOnly={true}
        onToggleStaleOnly={() => {}}
      />,
      { wrapper },
    );
    expect(screen.getByTestId("drift-stale-only-toggle")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
