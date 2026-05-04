import { describe, expect, it } from "vitest";

import { Y_WORK, buildFlow } from "@/features/workflow/flowGraph";
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
      work_steps: [],
    },
    {
      id: "queued",
      next: { kind: "single", single: "executing" },
      validators: [],
      jit_prompts: [],
      prompt_checks: [],
      artifacts: { produces: [{ id: "plan", label: "plan.md" }], consumes: [] },
      work_steps: [],
    },
    {
      id: "executing",
      next: { kind: "single", single: "in_review" },
      validators: [],
      jit_prompts: ["self-review", "cost-ceiling"],
      prompt_checks: [],
      artifacts: { produces: [{ id: "diff", label: "diff" }], consumes: [] },
      work_steps: [
        { id: "implement", actor: "coding-agent", label: "implement", skills: ["backend-development"] },
      ],
    },
    {
      id: "in_review",
      next: { kind: "single", single: "verified" },
      validators: [],
      jit_prompts: [],
      prompt_checks: [],
      artifacts: { produces: [], consumes: [] },
      work_steps: [],
    },
    {
      id: "verified",
      next: { kind: "terminal" },
      validators: [],
      jit_prompts: [],
      prompt_checks: [],
      artifacts: { produces: [], consumes: [] },
      work_steps: [],
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
      controls: { validators: ["v_uuid_present"], jit_prompts: [], prompt_checks: [] },
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

describe("buildFlow", () => {
  it("emits one status node per workflow status, ordered west→east, touching", () => {
    const flow = buildFlow(fixture);
    const statuses = flow.nodes.filter((n) => n.type === "status");
    expect(statuses).toHaveLength(5);
    expect(statuses.map((n) => n.id)).toEqual([
      "status:planned",
      "status:queued",
      "status:executing",
      "status:in_review",
      "status:verified",
    ]);
    for (let i = 0; i < statuses.length - 1; i++) {
      const a = statuses[i]!;
      const b = statuses[i + 1]!;
      const aRight = a.position.x + (a.style?.width as number);
      expect(b.position.x).toBe(aRight);
    }
  });

  it("emits a work_step node parented to its status region", () => {
    const flow = buildFlow(fixture);
    const ws = flow.nodes.find((n) => n.id === "work:executing:implement");
    expect(ws).toBeDefined();
    expect(ws?.parentId).toBe("status:executing");
    expect(ws?.type).toBe("workStep");
  });

  it("emits chips in the inputs band for skills and ref artifacts (deduped per region)", () => {
    const flow = buildFlow(fixture);
    // Skills are deduped by name within a region — id no longer carries
    // the work_step that loaded the skill (that's data on the chip).
    const skill = flow.nodes.find(
      (n) => n.id === "chip:executing:skill:backend-development",
    );
    expect(skill).toBeDefined();
    expect(skill?.parentId).toBe("status:executing");
    expect(skill?.position.y).toBeLessThan(Y_WORK);
  });

  it("emits an output tile for each produces artifact", () => {
    const flow = buildFlow(fixture);
    const tile = flow.nodes.find((n) => n.id === "tile:executing:diff");
    expect(tile).toBeDefined();
    expect(tile?.parentId).toBe("status:executing");
    expect(tile?.position.y).toBeGreaterThan(Y_WORK);
  });

  it("emits boundary transitions on the wall between adjacent regions", () => {
    const flow = buildFlow(fixture);
    const tx = flow.nodes.find((n) => n.id === "tx:queued-to-executing");
    expect(tx?.type).toBe("boundary");
    const queued = flow.nodes.find((n) => n.id === "status:queued")!;
    const expectedWallX = queued.position.x + (queued.style?.width as number);
    // tx position.x is the upper-left of the box; its centre should sit on the wall
    const txCenter = tx!.position.x + (tx!.style?.width as number) / 2;
    expect(txCenter).toBe(expectedWallX);
  });

  it("emits a branch diamond in diamond mode and an outcome edge per route", () => {
    const flow = buildFlow(fixture, { gateMode: "diamond" });
    const diamond = flow.nodes.find((n) => n.id === "branch:pm-session-review");
    expect(diamond?.type).toBe("branch");
    const outcomes = flow.edges.filter((e) => e.source === "branch:pm-session-review");
    expect(
      outcomes.map((e) => (e.data as { label?: string } | undefined)?.label),
    ).toEqual(expect.arrayContaining(["approve", "request changes"]));
  });

  it("emits source / sink ports", () => {
    const flow = buildFlow(fixture);
    const source = flow.nodes.find((n) => n.id === "port:source:issue");
    const sink = flow.nodes.find((n) => n.id === "port:sink:main");
    expect(source?.type).toBe("port");
    expect(sink?.type).toBe("port");
  });

  it("renders JIT flares parented to the executing status", () => {
    const flow = buildFlow(fixture);
    const flares = flow.nodes.filter((n) => n.type === "jit");
    expect(flares).toHaveLength(2);
    expect(flares.every((n) => n.parentId === "status:executing")).toBe(true);
  });
});
