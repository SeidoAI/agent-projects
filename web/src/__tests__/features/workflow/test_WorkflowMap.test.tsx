import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { WorkflowMap } from "@/features/workflow/WorkflowMap";
import type {
  WorkflowGraph,
  WorkflowRoute,
  WorkflowStatus,
} from "@/lib/api/endpoints/workflow";
import { server } from "../../mocks/server";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

function status(
  id: string,
  overrides: Partial<WorkflowStatus> = {},
): WorkflowStatus {
  return {
    id,
    next: { kind: "single", single: "next" },
    validators: [],
    jit_prompts: [],
    prompt_checks: [],
    artifacts: { produces: [], consumes: [] },
    ...overrides,
  };
}

function route(overrides: Partial<WorkflowRoute>): WorkflowRoute {
  return {
    id: "r-x",
    workflow_id: "coding-session",
    actor: "pm-agent",
    from: "planned",
    to: "queued",
    kind: "forward",
    label: "go",
    controls: { validators: [], jit_prompts: [], prompt_checks: [] },
    skills: [],
    emits: { artifacts: [], events: [], comments: [], status_changes: [] },
    ...overrides,
  };
}

function makeGraph(overrides: Partial<WorkflowGraph> = {}): WorkflowGraph {
  return {
    project_id: "p1",
    workflows: [
      {
        id: "coding-session",
        actor: "coding-agent",
        trigger: "session.spawn",
        brief_description: "one session: plan, execute, review, ship.",
        statuses: [
          status("planned", { next: { kind: "single", single: "queued" } }),
          status("queued", { next: { kind: "single", single: "executing" } }),
          status("executing", {
            next: { kind: "single", single: "in_review" },
            jit_prompts: ["self-review"],
          }),
          status("in_review", { next: { kind: "single", single: "verified" } }),
          status("verified", { next: { kind: "terminal" } }),
        ],
        routes: [
          route({
            id: "queued-to-executing",
            command: "pm-session-spawn",
            from: "queued",
            to: "executing",
            label: "spawn coding agent",
            controls: {
              validators: ["v_uuid_present"],
              jit_prompts: [],
              prompt_checks: ["pm-session-spawn"],
            },
            skills: ["project-manager"],
          }),
          route({
            id: "executing-to-review",
            actor: "coding-agent",
            from: "executing",
            to: "in_review",
            label: "submit for review",
          }),
          route({
            id: "review-approved",
            command: "pm-session-review",
            from: "in_review",
            to: "verified",
            label: "approve",
          }),
          route({
            id: "review-changes-requested",
            command: "pm-session-review",
            from: "in_review",
            to: "executing",
            kind: "return",
            label: "request changes",
          }),
        ],
      },
      {
        id: "pm-scoping",
        actor: "pm-agent",
        trigger: "command.pm-scope",
        brief_description: "turn intent into scoped work.",
        statuses: [
          status("intake", { next: { kind: "single", single: "draft" } }),
          status("draft", { next: { kind: "terminal" } }),
        ],
        routes: [
          route({
            id: "scope-intake",
            from: "intake",
            to: "draft",
            label: "draft",
          }),
        ],
      },
    ],
    registry: {
      validators: [
        {
          id: "v_uuid_present",
          label: "v_uuid_present",
          description: "all entities have UUIDs",
        },
      ],
      prompt_checks: [
        {
          id: "pm-session-spawn",
          label: "pm-session-spawn",
          description: "PM spawning: agent has all it needs?",
        },
      ],
      jit_prompts: [
        {
          id: "self-review",
          label: "self-review",
          description: "remind agent to review own diff",
          fires_on_event: "session.complete",
          prompt_redacted: "<<self-review>>",
        },
      ],
      commands: [],
      skills: [],
    },
    drift: { count: 0, findings: [] },
    ...overrides,
  };
}

function mountAt(
  initialEntry: string,
  body: () => ReactElement = () => <WorkflowMap />,
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/p/:projectId/workflow" element={body()} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("WorkflowMap (V1 territory map)", () => {
  it("renders the navigator grouped by actor and the active workflow", async () => {
    server.use(
      http.get("/api/projects/:pid/workflow", () => HttpResponse.json(makeGraph())),
    );
    mountAt("/p/p1/workflow");

    const nav = await screen.findByTestId("workflow-navigator");
    expect(nav).toHaveTextContent(/ACTOR · CODING-AGENT/i);
    expect(nav).toHaveTextContent(/ACTOR · PM-AGENT/i);
    expect(screen.getByTestId("workflow-nav-tile-coding-session")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-nav-tile-pm-scoping")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-flowchart")).toHaveAttribute(
      "data-workflow",
      "coding-session",
    );
  });

  it("renders the brief-description below the navigator", async () => {
    server.use(
      http.get("/api/projects/:pid/workflow", () => HttpResponse.json(makeGraph())),
    );
    mountAt("/p/p1/workflow");
    expect(
      await screen.findByText("one session: plan, execute, review, ship."),
    ).toBeInTheDocument();
  });

  it("opens the inline gate panel when the gate badge is clicked", async () => {
    server.use(
      http.get("/api/projects/:pid/workflow", () => HttpResponse.json(makeGraph())),
    );
    mountAt("/p/p1/workflow");

    const badge = await screen.findByTestId("workflow-gate-badge-queued-to-executing");
    fireEvent.click(badge);

    const panel = await screen.findByTestId(
      "workflow-gate-panel-queued-to-executing",
    );
    expect(panel).toHaveTextContent("GATE · 2 CHECKS");
    expect(panel).toHaveTextContent("uuid_present");
    expect(panel).toHaveTextContent("pm-session-spawn");
  });

  it("does not render a gate badge when the route has no controls", async () => {
    server.use(
      http.get("/api/projects/:pid/workflow", () => HttpResponse.json(makeGraph())),
    );
    mountAt("/p/p1/workflow");

    await screen.findByTestId("workflow-flowchart");
    expect(
      screen.queryByTestId("workflow-gate-badge-executing-to-review"),
    ).not.toBeInTheDocument();
  });

  it("switches the active workflow when a navigator tile is clicked", async () => {
    server.use(
      http.get("/api/projects/:pid/workflow", () => HttpResponse.json(makeGraph())),
    );
    mountAt("/p/p1/workflow");

    fireEvent.click(await screen.findByTestId("workflow-nav-tile-pm-scoping"));

    await waitFor(() =>
      expect(screen.getByTestId("workflow-flowchart")).toHaveAttribute(
        "data-workflow",
        "pm-scoping",
      ),
    );
  });

  it("respects ?wf=<id> in the URL on initial render", async () => {
    server.use(
      http.get("/api/projects/:pid/workflow", () => HttpResponse.json(makeGraph())),
    );
    mountAt("/p/p1/workflow?wf=pm-scoping");
    const chart = await screen.findByTestId("workflow-flowchart");
    expect(chart).toHaveAttribute("data-workflow", "pm-scoping");
  });

  it("shows the loading state while pending", async () => {
    server.use(
      http.get(
        "/api/projects/:pid/workflow",
        async () =>
          new Promise<Response>(() => {
            /* never resolves */
          }),
      ),
    );
    mountAt("/p/p1/workflow");
    expect(await screen.findByText(/loading workflow/i)).toBeInTheDocument();
  });

  it("shows the empty state when no workflows are returned", async () => {
    server.use(
      http.get("/api/projects/:pid/workflow", () =>
        HttpResponse.json(makeGraph({ workflows: [] })),
      ),
    );
    mountAt("/p/p1/workflow");
    expect(await screen.findByText(/not yet available/i)).toBeInTheDocument();
  });

  it("opens the drawer when a status region is clicked", async () => {
    server.use(
      http.get("/api/projects/:pid/workflow", () => HttpResponse.json(makeGraph())),
    );
    mountAt("/p/p1/workflow");

    const region = await screen.findByTestId("workflow-region-executing");
    fireEvent.click(region);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
});
