import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowMap } from "@/features/workflow/WorkflowMap";
import type { WorkflowGraph } from "@/lib/api/endpoints/workflow";
import { queryKeys } from "@/lib/api/queryKeys";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

const STATIONS: WorkflowGraph["lifecycle"]["stations"] = [
  { id: "planned", n: 1, label: "planned", desc: "" },
  { id: "queued", n: 2, label: "queued", desc: "" },
  { id: "executing", n: 3, label: "executing", desc: "" },
  { id: "in_review", n: 4, label: "in review", desc: "" },
  { id: "verified", n: 5, label: "verified", desc: "" },
  { id: "completed", n: 6, label: "completed", desc: "" },
];

function makeGraph(overrides: Partial<WorkflowGraph> = {}): WorkflowGraph {
  return {
    project_id: "p1",
    lifecycle: { stations: STATIONS },
    validators: [
      {
        id: "v1",
        kind: "gate",
        name: "self-review",
        fires_on_station: "in_review",
        checks: "self-review.md exists",
        blocks: true,
      },
    ],
    tripwires: [
      {
        id: "t1",
        kind: "tripwire",
        name: "stale-context",
        fires_on_station: "in_review",
        fires_on_event: "session.complete",
        prompt_revealed: null,
        prompt_redacted: "<<tripwire registered>>",
      },
    ],
    connectors: {
      sources: [{ id: "linear", name: "Linear", wired_to_station: "planned", data: "issues" }],
      sinks: [{ id: "github_pr", name: "PR open", wired_from_station: "in_review" }],
    },
    artifacts: [
      { id: "a_plan", label: "plan.md", produced_by: "queued", consumed_by: "executing" },
    ],
    ...overrides,
  };
}

function withProviders(graph: WorkflowGraph | null) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  if (graph) qc.setQueryData(queryKeys.workflow("p1"), graph);
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/p/p1/workflow"]}>
        <Routes>
          <Route path="/p/:projectId/workflow" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(cleanup);

describe("WorkflowMap", () => {
  it("renders the legend strip explaining validator vs tripwire", () => {
    const Wrapper = withProviders(makeGraph());
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );
    const legend = screen.getByLabelText(/legend/i);
    // Each of the legend swatches has identifying copy.
    expect(within(legend).getByText(/^source$/i)).toBeTruthy();
    expect(within(legend).getByText(/^station$/i)).toBeTruthy();
    expect(within(legend).getByText(/^sink$/i)).toBeTruthy();
    expect(within(legend).getAllByText(/^artifact$/i).length).toBeGreaterThan(0);
    // Validator vs tripwire distinction must be explicit in the legend.
    expect(within(legend).getByText(/blocks/i)).toBeTruthy();
    expect(within(legend).getByText(/agent must ack/i)).toBeTruthy();
  });

  it("renders all 6 stations from the API graph", () => {
    const Wrapper = withProviders(makeGraph());
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );
    for (const s of STATIONS) {
      expect(screen.getAllByText(s.label).length).toBeGreaterThan(0);
    }
  });

  it("opens the validator drawer on click and shows the GATE stamp", () => {
    const Wrapper = withProviders(makeGraph());
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );
    const validatorButton = screen.getByLabelText(/Validator self-review/);
    fireEvent.click(validatorButton);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("GATE")).toBeTruthy();
    expect(within(dialog).getByText(/self-review\.md exists/i)).toBeTruthy();
  });

  it("opens the tripwire drawer with the redacted placeholder for non-PM viewers", () => {
    const Wrapper = withProviders(makeGraph());
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );
    const tripwireButton = screen.getByLabelText(/Tripwire stale-context/);
    fireEvent.click(tripwireButton);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("<<tripwire registered>>")).toBeTruthy();
  });

  it("auto-renders new validators added to the API without code changes", () => {
    const graph = makeGraph({
      validators: [
        {
          id: "v1",
          kind: "gate",
          name: "self-review",
          fires_on_station: "in_review",
          checks: "self-review.md exists",
        },
        {
          id: "v2",
          kind: "gate",
          name: "tests-green",
          fires_on_station: "in_review",
          checks: "CI green",
        },
      ],
    });
    const Wrapper = withProviders(graph);
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );
    expect(screen.getByLabelText(/Validator self-review/)).toBeTruthy();
    expect(screen.getByLabelText(/Validator tests-green/)).toBeTruthy();
  });

  it("renders an empty-state placeholder when the API returns no graph", () => {
    const Wrapper = withProviders(null);
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );
    expect(screen.getByText(/backend has not registered the orchestration graph/i)).toBeTruthy();
  });
});
