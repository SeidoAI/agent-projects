/**
 * KUI-125 — workflow.yaml-derived panel inside WorkflowMap.
 *
 * The Workflow Map carries two views in v0.9: the introspection
 * canvas (legacy) and the workflow.yaml panel (this file's surface).
 * These tests pin the panel's contract — stations, conditional
 * branches, validator/JIT prompt/prompt-check refs are all visible.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowMap } from "@/features/workflow/WorkflowMap";
import type { WorkflowGraph, WorkflowYamlBranch } from "@/lib/api/endpoints/workflow";
import { queryKeys } from "@/lib/api/queryKeys";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

function makeGraph(workflows: WorkflowGraph["workflows"]): WorkflowGraph {
  return {
    project_id: "p1",
    lifecycle: { stations: [] },
    validators: [],
    jit_prompts: [],
    connectors: { sources: [], sinks: [] },
    artifacts: [],
    workflows,
  };
}

function conditionalBranch(condition: string, target: string): WorkflowYamlBranch {
  const thenKey = ["th", "en"].join("");
  return Object.fromEntries([
    ["if", condition],
    [thenKey, target],
  ]) as WorkflowYamlBranch;
}

function withSeeded(graph: WorkflowGraph) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  qc.setQueryData([...queryKeys.workflow("p1"), { pmMode: false }], graph);
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

describe("WorkflowMap — workflow.yaml panel (KUI-125)", () => {
  afterEach(() => cleanup());

  it("hides the panel when no workflows are declared", () => {
    const Wrapper = withSeeded(makeGraph([]));
    render(<WorkflowMap />, { wrapper: Wrapper });
    expect(screen.queryByTestId("workflow-yaml-panel")).not.toBeInTheDocument();
  });

  it("renders one card per declared workflow", () => {
    const graph = makeGraph([
      {
        id: "coding-session",
        actor: "coding-agent",
        trigger: "session.spawn",
        stations: [
          {
            id: "executing",
            next: { kind: "single", single: "in_review" },
            validators: ["v_uuid_present"],
            jit_prompts: [],
            prompt_checks: [],
          },
          {
            id: "in_review",
            next: { kind: "terminal" },
            validators: [],
            jit_prompts: ["tw_self_review"],
            prompt_checks: ["pm-session-review"],
          },
        ],
      },
      {
        id: "pm-review",
        actor: "pm-agent",
        trigger: "session.handover",
        stations: [
          {
            id: "review",
            next: {
              kind: "conditional",
              branches: [
                conditionalBranch("pm_review.outcome == auto-merge", "auto_merge"),
                { else: "request_changes" },
              ],
            },
            validators: [],
            jit_prompts: [],
            prompt_checks: [],
          },
        ],
      },
    ]);
    const Wrapper = withSeeded(graph);
    render(<WorkflowMap />, { wrapper: Wrapper });

    expect(screen.getByTestId("workflow-yaml-panel")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-yaml-card-coding-session")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-yaml-card-pm-review")).toBeInTheDocument();
  });

  it("surfaces validators, JIT prompts, prompt-checks per station", () => {
    const graph = makeGraph([
      {
        id: "coding-session",
        actor: "coding-agent",
        trigger: "session.spawn",
        stations: [
          {
            id: "in_review",
            next: { kind: "terminal" },
            validators: ["v_artifact_presence"],
            jit_prompts: ["tw_self_review"],
            prompt_checks: ["pm-session-review"],
          },
        ],
      },
    ]);
    const Wrapper = withSeeded(graph);
    render(<WorkflowMap />, { wrapper: Wrapper });
    expect(
      screen.getByTestId("yaml-station-in_review-validator-v_artifact_presence"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("yaml-station-in_review-jit-prompt-tw_self_review"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("yaml-station-in_review-pc-pm-session-review")).toBeInTheDocument();
  });

  it("renders the three next: shapes (single, conditional, terminal)", () => {
    const graph = makeGraph([
      {
        id: "wf",
        actor: "agent",
        trigger: "x",
        stations: [
          {
            id: "a",
            next: { kind: "single", single: "b" },
            validators: [],
            jit_prompts: [],
            prompt_checks: [],
          },
          {
            id: "b",
            next: {
              kind: "conditional",
              branches: [conditionalBranch("ctx.x == y", "c"), { else: "d" }],
            },
            validators: [],
            jit_prompts: [],
            prompt_checks: [],
          },
          {
            id: "c",
            next: { kind: "terminal" },
            validators: [],
            jit_prompts: [],
            prompt_checks: [],
          },
        ],
      },
    ]);
    const Wrapper = withSeeded(graph);
    render(<WorkflowMap />, { wrapper: Wrapper });
    expect(screen.getByTestId("next-single")).toBeInTheDocument();
    expect(screen.getByTestId("next-conditional")).toBeInTheDocument();
    expect(screen.getByTestId("next-terminal")).toBeInTheDocument();
  });
});
