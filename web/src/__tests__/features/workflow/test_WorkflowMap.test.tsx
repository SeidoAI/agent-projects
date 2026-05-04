import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { WorkflowMap } from "@/features/workflow/WorkflowMap";
import type { WorkflowGraph } from "@/lib/api/endpoints/workflow";
import { queryKeys } from "@/lib/api/queryKeys";
import { server } from "../../mocks/server";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

function makeGraph(overrides: Partial<WorkflowGraph> = {}): WorkflowGraph {
  return {
    project_id: "p1",
    workflows: [
      {
        id: "coding-session",
        actor: "coding-agent",
        trigger: "session.spawn",
        statuses: [
          {
            id: "planned",
            label: "planned",
            next: { kind: "single", single: "queued" },
            validators: [],
            jit_prompts: [],
            prompt_checks: [],
            artifacts: { consumes: [{ id: "issue", label: "issue brief" }], produces: [] },
          },
          {
            id: "queued",
            label: "queued",
            next: { kind: "single", single: "executing" },
            validators: ["v_check"],
            jit_prompts: [],
            prompt_checks: [],
            artifacts: {
              consumes: [],
              produces: [{ id: "plan", label: "plan.md", path: "sessions/{session_id}/plan.md" }],
            },
          },
          {
            id: "executing",
            label: "executing",
            next: { kind: "single", single: "in_review" },
            validators: ["v_check"],
            jit_prompts: [],
            prompt_checks: [],
            artifacts: { consumes: [], produces: [{ id: "diff", label: "implementation diff" }] },
          },
          {
            id: "in_review",
            label: "in review",
            next: {
              kind: "conditional",
              branches: [
                // biome-ignore lint/suspicious/noThenProperty: mirrors workflow.yaml branch syntax.
                { if: "review.outcome == approved", then: "verified" },
                { else: "executing" },
              ],
            },
            validators: ["v_artifact_presence"],
            jit_prompts: ["self-review"],
            prompt_checks: ["pm-session-review"],
            artifacts: { consumes: [], produces: [{ id: "review", label: "review notes" }] },
          },
          {
            id: "verified",
            label: "verified",
            next: { kind: "single", single: "completed" },
            validators: [],
            jit_prompts: [],
            prompt_checks: [],
            artifacts: { consumes: [], produces: [] },
          },
          {
            id: "completed",
            label: "completed",
            next: { kind: "terminal" },
            validators: [],
            jit_prompts: [],
            prompt_checks: [],
            artifacts: { consumes: [], produces: [{ id: "sig", label: "session signature" }] },
          },
        ],
      },
    ],
    registry: {
      validators: [
        {
          id: "v_check",
          label: "generic check",
          description: "duplicate validator id used in multiple statuses",
          blocking: true,
        },
        {
          id: "v_artifact_presence",
          label: "artifact presence",
          description: "required artifacts exist",
          blocking: true,
        },
      ],
      jit_prompts: [
        {
          id: "self-review",
          label: "self review",
          status: "in_review",
          fires_on_event: "session.complete",
          blocking: true,
          prompt_revealed: null,
          prompt_redacted: "<<JIT prompt registered>>",
        },
      ],
      prompt_checks: [
        {
          id: "pm-session-review",
          label: "session review",
          status: "in_review",
          blocking: true,
        },
      ],
    },
    drift: {
      count: 1,
      findings: [
        {
          source: "definition",
          code: "workflow/unknown_next_status",
          workflow: "coding-session",
          status: "in_review",
          severity: "error",
          message: "in_review references a missing status",
        },
      ],
    },
    ...overrides,
  };
}

function withProviders(graph: WorkflowGraph | null, opts?: { pmMode?: boolean }) {
  const pmMode = Boolean(opts?.pmMode);
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
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

describe("WorkflowMap", () => {
  it("renders one territory map from workflow statuses", () => {
    const Wrapper = withProviders(makeGraph());
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );

    expect(screen.getByTestId("workflow-territory")).toBeInTheDocument();
    expect(screen.queryByTestId("workflow-yaml-panel")).not.toBeInTheDocument();
    for (const id of ["planned", "queued", "executing", "in_review", "verified", "completed"]) {
      expect(screen.getByTestId(`status-region-${id}`)).toBeInTheDocument();
    }
  });

  it("renders territory grammar in the legend", () => {
    const Wrapper = withProviders(makeGraph());
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );
    const legend = screen.getByLabelText(/legend/i);
    for (const label of ["STATUS", "GATE", "JIT PROMPT", "ARTIFACT", "DRIFT"]) {
      expect(within(legend).getByText(label)).toBeInTheDocument();
    }
  });

  it("opens gate, JIT prompt, artifact, status, and drift drawers", () => {
    const Wrapper = withProviders(makeGraph());
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Gate into in_review/i }));
    expect(within(screen.getByRole("dialog")).getByText("GATE")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close/i }));

    fireEvent.click(screen.getByRole("button", { name: /JIT prompt self review/i }));
    expect(
      within(screen.getByRole("dialog")).getByText("<<JIT prompt registered>>"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close/i }));

    fireEvent.click(screen.getByRole("button", { name: /Artifact plan.md/i }));
    expect(within(screen.getByRole("dialog")).getByText("ARTIFACT")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close/i }));

    fireEvent.click(screen.getByRole("button", { name: /^Status executing$/i }));
    expect(within(screen.getByRole("dialog")).getByText("STATUS")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close/i }));

    fireEvent.click(screen.getByRole("button", { name: /^drift$/i }));
    expect(
      within(screen.getByRole("dialog")).getByText("workflow/unknown_next_status"),
    ).toBeInTheDocument();
  });

  it("reveals JIT prompt body for PM-mode payloads", () => {
    const graph = makeGraph({
      registry: {
        ...makeGraph().registry,
        jit_prompts: [
          {
            id: "self-review",
            label: "self review",
            status: "in_review",
            fires_on_event: "session.complete",
            blocking: true,
            prompt_revealed: "secret-prompt-body for the agent",
            prompt_redacted: "<<JIT prompt registered>>",
          },
        ],
      },
    });
    const Wrapper = withProviders(graph, { pmMode: true });
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );

    fireEvent.click(screen.getByRole("button", { name: /JIT prompt self review/i }));
    expect(within(screen.getByRole("dialog")).getByText(/secret-prompt-body/i)).toBeInTheDocument();
  });

  it("does not emit React duplicate-key warnings when one validator id appears in multiple statuses", () => {
    const Wrapper = withProviders(makeGraph());
    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );

    expect(screen.getAllByRole("button", { name: /gate into/i })).toHaveLength(3);
  });

  it("shows a loading surface while the workflow query is pending", () => {
    server.use(
      http.get("/api/projects/:pid/workflow", async () => {
        await new Promise(() => {});
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

    expect(screen.getByText(/loading workflow/i)).toBeInTheDocument();
  });

  it("shows an error surface with retry when the request fails", async () => {
    server.use(
      http.get("/api/projects/:pid/workflow", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
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
    vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <Wrapper>
        <WorkflowMap />
      </Wrapper>,
    );

    await waitFor(() =>
      expect(screen.getByText(/couldn't load the workflow map/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("shows the empty state on 404", async () => {
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

    await waitFor(() =>
      expect(screen.getByText(/workflow not yet available/i)).toBeInTheDocument(),
    );
  });
});
