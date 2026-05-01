import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowMap } from "@/features/workflow/WorkflowMap";
import type { WorkflowGraph } from "@/lib/api/endpoints/workflow";
import { queryKeys } from "@/lib/api/queryKeys";
import { server } from "../../mocks/server";

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
    jit_prompts: [
      {
        id: "t1",
        kind: "jit_prompt",
        name: "stale-context",
        fires_on_station: "in_review",
        fires_on_event: "session.complete",
        prompt_revealed: null,
        prompt_redacted: "<<JIT prompt registered>>",
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

function withProviders(graph: WorkflowGraph | null, opts?: { pmMode?: boolean }) {
  const pmMode = Boolean(opts?.pmMode);
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  // Mirror the cache-key shape used by `useWorkflow` — without the
  // pmMode suffix the hook misses cache and falls back to MSW's
  // stub handler, which returns an empty graph.
  if (graph) qc.setQueryData([...queryKeys.workflow("p1"), { pmMode }], graph);
  const initialEntry = pmMode ? "/p/p1/workflow?role=pm" : "/p/p1/workflow";
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/p/:projectId/workflow" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(cleanup);

describe("WorkflowMap", () => {
  it("renders the legend as 6 pill chips using the Stamp primitive (no parallel chip variant)", () => {
    const Wrapper = withProviders(makeGraph());
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );
    const legend = screen.getByLabelText(/legend/i);
    // Each chip carries `data-tone` written by `Stamp` itself —
    // asserts the legend uses the canonical Stamp primitive rather
    // than a hand-rolled "legend version" of the chip.
    const chips = legend.querySelectorAll("[data-tone]");
    expect(chips.length).toBe(6);
    // Validator vs JIT prompt distinction is the cognitive teaching
    // surface — both chips + their explanatory copy must be present.
    expect(within(legend).getByText("GATE")).toBeTruthy();
    expect(within(legend).getByText("JIT PROMPT")).toBeTruthy();
    expect(within(legend).getByText(/blocks/i)).toBeTruthy();
    expect(within(legend).getByText(/agent must ack/i)).toBeTruthy();
    // All 6 categories represented.
    for (const label of ["SOURCE", "STATION", "SINK", "GATE", "JIT PROMPT", "ARTIFACT"]) {
      expect(within(legend).getByText(label)).toBeTruthy();
    }
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

  it("opens the JIT prompt drawer with the redacted placeholder for non-PM viewers", () => {
    const Wrapper = withProviders(makeGraph());
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );
    const jitPromptButton = screen.getByLabelText(/JIT prompt stale-context/);
    fireEvent.click(jitPromptButton);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("<<JIT prompt registered>>")).toBeTruthy();
  });

  it("reveals the prompt body for ?role=pm viewers (PM-mode payload reaches the drawer)", () => {
    // Seed the PM-mode cache key with a graph whose JIT prompt has
    // `prompt_revealed` populated (mirroring what the server returns
    // when the `X-Tripwire-Role: pm` header arrives). The drawer
    // should render that body, not the placeholder.
    const graph = makeGraph({
      jit_prompts: [
        {
          id: "t1",
          kind: "jit_prompt",
          name: "stale-context",
          fires_on_station: "in_review",
          fires_on_event: "session.complete",
          prompt_revealed: "secret-prompt-body for the agent",
          prompt_redacted: "<<JIT prompt registered>>",
        },
      ],
    });
    const Wrapper = withProviders(graph, { pmMode: true });
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );
    fireEvent.click(screen.getByLabelText(/JIT prompt stale-context/));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/secret-prompt-body for the agent/i)).toBeTruthy();
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

  it("shows a Loading… surface while the workflow query is pending", () => {
    // Hold the response open so the query never settles; assert
    // pending state renders 'Loading workflow…' (not the empty-state
    // copy, which would mislead users on slow networks).
    server.use(
      http.get("/api/projects/:pid/workflow", async () => {
        await new Promise(() => {
          /* never resolve */
        });
        return HttpResponse.json({});
      }),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const Wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/p/p1/workflow"]}>
          <Routes>
            <Route path="/p/:projectId/workflow" element={children} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );
    expect(screen.getByText(/loading workflow/i)).toBeTruthy();
    expect(screen.queryByText(/backend has not registered the orchestration graph/i)).toBeNull();
  });

  it("shows an Error surface with a Retry button when the request fails (non-404)", async () => {
    server.use(
      http.get("/api/projects/:pid/workflow", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    // Disable React Query's own retry shaping for this test so the
    // 500 settles into the error state quickly. The hook's
    // production retry policy is exercised separately.
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, retryDelay: 0 } },
    });
    const Wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/p/p1/workflow"]}>
          <Routes>
            <Route path="/p/:projectId/workflow" element={children} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    // The 500 surfaces as a console.error from React Query; the
    // global setup converts unexpected console output into test
    // failures, so silence it for this scenario only.
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );
    await waitFor(
      () => {
        expect(screen.getByText(/Couldn't load the workflow graph/i)).toBeTruthy();
      },
      { timeout: 8000 },
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
  });

  it("shows the empty-state copy on 404 (Strand Y not yet shipped)", async () => {
    server.use(
      http.get("/api/projects/:pid/workflow", () =>
        HttpResponse.json({ detail: "not found" }, { status: 404 }),
      ),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const Wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/p/p1/workflow"]}>
          <Routes>
            <Route path="/p/:projectId/workflow" element={children} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );
    await waitFor(() => {
      expect(screen.getByText(/backend has not registered the orchestration graph/i)).toBeTruthy();
    });
  });
});
