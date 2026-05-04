import { describe, expect, it } from "vitest";

import { buildWorkflowTerritory } from "@/features/workflow/useWorkflowLayout";
import type { WorkflowGraph, WorkflowStatus } from "@/lib/api/endpoints/workflow";

function buildGraph(overrides: Partial<WorkflowGraph> = {}): WorkflowGraph {
  return {
    project_id: "p1",
    workflows: [
      {
        id: "coding-session",
        actor: "coding-agent",
        trigger: "session.spawn",
        statuses: [
          {
            id: "queued",
            next: { kind: "single", single: "executing" },
            validators: [],
            jit_prompts: [],
            prompt_checks: [],
            artifacts: { consumes: [], produces: [{ id: "plan", label: "plan.md" }] },
          },
          {
            id: "executing",
            next: {
              kind: "conditional",
              branches: [
                // biome-ignore lint/suspicious/noThenProperty: mirrors workflow.yaml branch syntax.
                { if: "review.outcome == approved", then: "in_review" },
                { else: "queued" },
              ],
            },
            validators: ["v_check", "v_check"],
            jit_prompts: ["self-review"],
            prompt_checks: ["pm-session-review"],
            artifacts: { consumes: [], produces: [{ id: "diff", label: "diff" }] },
          },
          {
            id: "in_review",
            next: { kind: "terminal" },
            validators: [],
            jit_prompts: [],
            prompt_checks: [],
            artifacts: { consumes: [], produces: [] },
          },
        ],
      },
    ],
    registry: {
      validators: [{ id: "v_check", label: "check", blocking: true }],
      jit_prompts: [{ id: "self-review", label: "self review", blocking: true }],
      prompt_checks: [{ id: "pm-session-review", label: "session review", blocking: true }],
    },
    drift: {
      count: 1,
      findings: [
        {
          source: "definition",
          code: "workflow/unknown_next_status",
          workflow: "coding-session",
          status: "executing",
          severity: "error",
          message: "bad route",
        },
      ],
    },
    ...overrides,
  };
}

describe("buildWorkflowTerritory", () => {
  it("uses statuses as the top-level territory units", () => {
    const territory = buildWorkflowTerritory(buildGraph());

    expect(territory?.statuses.map((region) => region.status.id)).toEqual([
      "queued",
      "executing",
      "in_review",
    ]);
  });

  it("groups validators and prompt checks into one gate cluster per status", () => {
    const territory = buildWorkflowTerritory(buildGraph());
    const executing = territory?.statuses.find((region) => region.status.id === "executing");

    expect(executing?.gate?.validators).toHaveLength(2);
    expect(executing?.gate?.promptChecks).toHaveLength(1);
    expect(executing?.gate?.id).toBe("executing:gate");
  });

  it("keeps JIT prompts as intervention markers, not gate members", () => {
    const territory = buildWorkflowTerritory(buildGraph());
    const executing = territory?.statuses.find((region) => region.status.id === "executing");

    expect(executing?.jitPrompts).toHaveLength(1);
    expect(executing?.gate?.validators.map((entry) => entry.id)).not.toContain("self-review");
  });

  it("derives artifacts from status declarations", () => {
    const territory = buildWorkflowTerritory(buildGraph());
    const queued = territory?.statuses.find((region) => region.status.id === "queued");

    expect(queued?.artifacts).toEqual([
      {
        id: "queued:produces:plan",
        statusId: "queued",
        direction: "produces",
        artifact: { id: "plan", label: "plan.md" },
      },
    ]);
  });

  it("classifies forward, return, and terminal routes", () => {
    const territory = buildWorkflowTerritory(buildGraph());

    expect(territory?.transitions.map((route) => [route.from, route.to, route.kind])).toEqual([
      ["queued", "executing", "forward"],
      ["executing", "in_review", "forward"],
      ["executing", "queued", "return"],
      ["in_review", null, "terminal"],
    ]);
  });

  it("uses static complexity to widen more detailed statuses within bounds", () => {
    const territory = buildWorkflowTerritory(buildGraph());
    const queued = territory?.statuses.find((region) => region.status.id === "queued");
    const executing = territory?.statuses.find((region) => region.status.id === "executing");

    expect(executing?.complexity).toBeGreaterThan(queued?.complexity ?? 0);
    expect(executing?.width).toBeGreaterThan(queued?.width ?? 0);
    expect(executing?.width).toBeLessThanOrEqual(390);
  });

  it("attaches drift findings to their status region", () => {
    const territory = buildWorkflowTerritory(buildGraph());
    const executing = territory?.statuses.find((region) => region.status.id === "executing");

    expect(executing?.drift).toHaveLength(1);
    expect(executing?.drift[0]?.code).toBe("workflow/unknown_next_status");
  });

  it("does not crash when a runtime payload is missing registry or drift", () => {
    const { registry: _registry, drift: _drift, ...graph } = buildGraph();

    const territory = buildWorkflowTerritory(graph as WorkflowGraph);
    const executing = territory?.statuses.find((region) => region.status.id === "executing");

    expect(executing?.gate?.validators.map((entry) => entry.id)).toEqual(["v_check", "v_check"]);
    expect(executing?.jitPrompts[0]?.prompt.id).toBe("self-review");
    expect(territory?.drift).toEqual([]);
  });

  it("does not crash when a status omits optional collection fields", () => {
    const graph = buildGraph();
    const workflow = graph.workflows[0];
    if (!workflow) throw new Error("missing workflow fixture");
    const executing = workflow.statuses[1] as Partial<WorkflowStatus>;
    delete executing.validators;
    delete executing.prompt_checks;
    delete executing.jit_prompts;
    delete executing.artifacts;

    const territory = buildWorkflowTerritory(graph);
    const region = territory?.statuses.find((item) => item.status.id === "executing");

    expect(region?.gate).toBeNull();
    expect(region?.jitPrompts).toEqual([]);
    expect(region?.artifacts).toEqual([]);
  });
});
