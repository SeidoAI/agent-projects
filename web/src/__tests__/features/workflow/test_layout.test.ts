import { describe, expect, it } from "vitest";

import {
  TX_W,
  layoutWorkflow,
  orthogonal,
  pathFromPoints,
} from "@/features/workflow/layout";
import type { WorkflowDefinition } from "@/lib/api/endpoints/workflow";

const fixture: WorkflowDefinition = {
  id: "coding-session",
  actor: "coding-agent",
  trigger: "session.spawn",
  brief_description: "one session: plan, execute, review, ship.",
  statuses: [
    {
      id: "planned",
      next: { kind: "single", single: "queued" },
      validators: [],
      jit_prompts: [],
      prompt_checks: [],
      artifacts: { produces: [], consumes: [] },
    },
    {
      id: "queued",
      next: { kind: "single", single: "executing" },
      validators: [],
      jit_prompts: [],
      prompt_checks: [],
      artifacts: { produces: [{ id: "plan", label: "plan.md" }], consumes: [] },
    },
    {
      id: "executing",
      next: { kind: "single", single: "in_review" },
      validators: [],
      jit_prompts: ["self-review", "cost-ceiling"],
      prompt_checks: [],
      artifacts: { produces: [{ id: "diff", label: "diff" }], consumes: [] },
    },
    {
      id: "in_review",
      next: { kind: "single", single: "verified" },
      validators: [],
      jit_prompts: [],
      prompt_checks: [],
      artifacts: { produces: [], consumes: [] },
    },
    {
      id: "verified",
      next: { kind: "terminal" },
      validators: [],
      jit_prompts: [],
      prompt_checks: [],
      artifacts: { produces: [], consumes: [] },
    },
  ],
  routes: [
    {
      id: "session-create",
      workflow_id: "coding-session",
      actor: "pm-agent",
      from: "source:issue",
      to: "planned",
      kind: "forward",
      label: "create session",
      controls: { validators: [], jit_prompts: [], prompt_checks: [] },
      skills: [],
      emits: { artifacts: [], events: [], comments: [], status_changes: [] },
    },
    {
      id: "queued-to-executing",
      workflow_id: "coding-session",
      actor: "pm-agent",
      from: "queued",
      to: "executing",
      kind: "forward",
      label: "spawn coding agent",
      controls: { validators: [], jit_prompts: [], prompt_checks: [] },
      skills: [],
      emits: { artifacts: [], events: [], comments: [], status_changes: [] },
    },
    {
      id: "review-approved",
      workflow_id: "coding-session",
      actor: "pm-agent",
      from: "in_review",
      to: "verified",
      kind: "forward",
      label: "approve review",
      controls: { validators: [], jit_prompts: [], prompt_checks: [] },
      skills: [],
      emits: { artifacts: [], events: [], comments: [], status_changes: [] },
    },
    {
      id: "review-changes-requested",
      workflow_id: "coding-session",
      actor: "pm-agent",
      from: "in_review",
      to: "executing",
      kind: "return",
      label: "request changes",
      controls: { validators: [], jit_prompts: [], prompt_checks: [] },
      skills: [],
      emits: { artifacts: [], events: [], comments: [], status_changes: [] },
    },
    {
      id: "verified-to-merged",
      workflow_id: "coding-session",
      actor: "code",
      from: "verified",
      to: "sink:main",
      kind: "terminal",
      label: "merge to main",
      controls: { validators: [], jit_prompts: [], prompt_checks: [] },
      skills: [],
      emits: { artifacts: [], events: [], comments: [], status_changes: [] },
    },
  ],
};

describe("layoutWorkflow", () => {
  it("places one region per status, equal width, ordered west→east", () => {
    const layout = layoutWorkflow(fixture);
    expect(layout.regions).toHaveLength(5);
    expect(layout.regions[0]!.id).toBe("planned");
    expect(layout.regions[4]!.id).toBe("verified");
    expect(layout.regions[4]!.terminal).toBe(true);
    const widths = new Set(layout.regions.map((r) => r.w));
    expect(widths.size).toBe(1);
    expect(layout.regions[1]!.x).toBeGreaterThan(layout.regions[0]!.x);
  });

  it("allocates lane Y by route kind", () => {
    const layout = layoutWorkflow(fixture);
    const get = (id: string) =>
      layout.transitions.find(
        (t) => t.kind === "transition" && t.id === `t-${id}`,
      );
    const forward = get("queued-to-executing");
    const ret = get("review-changes-requested");
    expect(forward?.cy).toBe(layout.mainY);
    expect(ret?.cy).toBe(layout.southY);
  });

  it("derives JIT anchors from status.jit_prompts and stacks vertically", () => {
    const layout = layoutWorkflow(fixture);
    expect(layout.jits).toHaveLength(2);
    expect(layout.jits.map((j) => j.label)).toEqual(["self-review", "cost-ceiling"]);
    const first = layout.jits[0]!;
    const second = layout.jits[1]!;
    expect(first.status).toBe("executing");
    expect(second.y).toBeGreaterThan(first.y);
    expect(first.y).toBeGreaterThanOrEqual(layout.proofTop);
  });

  it("emits source / sink ports at the chart edges", () => {
    const layout = layoutWorkflow(fixture);
    const source = layout.ports.find((p) => p.kind === "source");
    const sink = layout.ports.find((p) => p.kind === "sink");
    expect(source?.label).toBe("issue");
    expect(sink?.label).toBe("main");
    const firstRegion = layout.regions[0]!;
    const lastRegion = layout.regions[layout.regions.length - 1]!;
    expect(source?.x).toBeLessThan(firstRegion.x);
    expect(sink?.x).toBeGreaterThan(lastRegion.x + lastRegion.w);
  });

  it("collapses branched routes into a diamond when gateMode='diamond'", () => {
    const layout = layoutWorkflow(fixture, { gateMode: "diamond" });
    const diamond = layout.transitions.find((t) => t.kind === "branch");
    expect(diamond?.id).toBe("branch-pm-session-review");
    expect(diamond?.command).toBe("pm-session-review");
    const outcomeEdges = layout.edges.filter((e) => e.outcomeLabel);
    expect(new Set(outcomeEdges.map((e) => e.outcomeLabel))).toEqual(
      new Set(["approve", "request changes"]),
    );
  });

  it("emits no diamond in 'lock' mode (branches render as separate transitions)", () => {
    const layout = layoutWorkflow(fixture, { gateMode: "lock" });
    expect(layout.transitions.find((t) => t.kind === "branch")).toBeUndefined();
    const transitionIds = layout.transitions
      .filter((t) => t.kind === "transition")
      .map((t) => t.id);
    expect(transitionIds).toContain("t-review-approved");
    expect(transitionIds).toContain("t-review-changes-requested");
  });

  it("computes proof shelf below main line and artifact row at region bottom", () => {
    const layout = layoutWorkflow(fixture);
    const firstRegion = layout.regions[0]!;
    expect(layout.proofTop).toBeGreaterThan(layout.mainY);
    expect(layout.artifactRowY).toBeGreaterThan(layout.proofTop);
    expect(layout.artifactRowY).toBeLessThan(firstRegion.y + firstRegion.h);
  });

  it("transition box width matches TX_W constant", () => {
    const layout = layoutWorkflow(fixture);
    const tx = layout.transitions.find((t) => t.kind === "transition");
    expect(tx?.w).toBe(TX_W);
  });
});

describe("orthogonal", () => {
  it("returns a 2-point line for collinear horizontal endpoints", () => {
    const pts = orthogonal({ x: 0, y: 50 }, { x: 100, y: 50 });
    expect(pts).toHaveLength(2);
  });

  it("inserts midpoint waypoints when endpoints differ in Y", () => {
    const pts = orthogonal({ x: 0, y: 50 }, { x: 200, y: 100 });
    expect(pts).toHaveLength(4);
    expect(pts[1]!.x).toBe(100);
    expect(pts[1]!.y).toBe(50);
  });

  it("uses an explicit detour Y when supplied", () => {
    const pts = orthogonal({ x: 0, y: 50 }, { x: 200, y: 50 }, { detour: 200 });
    expect(pts).toHaveLength(4);
    expect(pts[1]!.y).toBe(200);
    expect(pts[2]!.y).toBe(200);
  });
});

describe("pathFromPoints", () => {
  it("returns empty for fewer than 2 points", () => {
    expect(pathFromPoints([])).toBe("");
  });

  it("emits M/L for a single segment", () => {
    expect(pathFromPoints([{ x: 0, y: 0 }, { x: 10, y: 0 }])).toBe("M 0 0 L 10 0");
  });

  it("emits Q-curve corners between segments", () => {
    const d = pathFromPoints([
      { x: 0, y: 0 },
      { x: 50, y: 0 },
      { x: 50, y: 100 },
    ]);
    expect(d).toContain("Q 50 0");
  });
});
