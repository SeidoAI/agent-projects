import { describe, expect, it } from "vitest";

import {
  computeWorkflowLayout,
  WORKFLOW_CANVAS,
  WORKFLOW_CARD_DIMS,
} from "@/features/workflow/useWorkflowLayout";
import type { WorkflowGraph } from "@/lib/api/endpoints/workflow";

const STATIONS: WorkflowGraph["lifecycle"]["stations"] = [
  { id: "planned", n: 1, label: "planned", desc: "" },
  { id: "queued", n: 2, label: "queued", desc: "" },
  { id: "executing", n: 3, label: "executing", desc: "" },
  { id: "in_review", n: 4, label: "in review", desc: "" },
  { id: "verified", n: 5, label: "verified", desc: "" },
  { id: "completed", n: 6, label: "completed", desc: "" },
];

function buildGraph(overrides: Partial<WorkflowGraph> = {}): WorkflowGraph {
  return {
    project_id: "p1",
    lifecycle: { stations: STATIONS },
    validators: [],
    jit_prompts: [],
    connectors: { sources: [], sinks: [] },
    artifacts: [],
    ...overrides,
  };
}

function must<T>(v: T | undefined, msg: string): T {
  if (v === undefined) throw new Error(msg);
  return v;
}

describe("computeWorkflowLayout", () => {
  it("evenly spaces 6 stations between left/right gutters on the wire", () => {
    const layout = computeWorkflowLayout(buildGraph());
    expect(layout.stations).toHaveLength(6);
    const xs = layout.stations.map((s) => s.x);
    const first = must(xs[0], "first station x missing");
    const last = must(xs[xs.length - 1], "last station x missing");
    expect(first).toBeGreaterThanOrEqual(WORKFLOW_CANVAS.gutterLeft);
    expect(last).toBeLessThanOrEqual(WORKFLOW_CANVAS.width - WORKFLOW_CANVAS.gutterRight);
    for (let i = 1; i < xs.length; i++) {
      const cur = must(xs[i], `xs[${i}] missing`);
      const prev = must(xs[i - 1], `xs[${i - 1}] missing`);
      expect(cur).toBeGreaterThan(prev);
    }
    for (const s of layout.stations) {
      expect(s.y).toBe(WORKFLOW_CANVAS.wireY);
    }
  });

  it("stacks validators above their fires_on_station with the gate row", () => {
    const layout = computeWorkflowLayout(
      buildGraph({
        validators: [
          {
            id: "v1",
            kind: "gate",
            name: "self-review",
            fires_on_station: "in_review",
            checks: "self-review.md exists",
            blocks: true,
          },
          {
            id: "v2",
            kind: "gate",
            name: "tests-green",
            fires_on_station: "in_review",
          },
        ],
      }),
    );
    expect(layout.validators).toHaveLength(2);
    const inReviewStation = must(
      layout.stations.find((s) => s.id === "in_review"),
      "in_review station missing",
    );
    const v0 = must(layout.validators[0], "validators[0]");
    const v1 = must(layout.validators[1], "validators[1]");
    expect(v0.x).toBe(inReviewStation.x);
    expect(v1.x).toBe(inReviewStation.x);
    expect(v0.y).toBeLessThan(WORKFLOW_CANVAS.wireY);
    expect(v1.y).toBeLessThan(v0.y);
  });

  it("stacks JIT prompts above their fires_on_station alongside validators", () => {
    const layout = computeWorkflowLayout(
      buildGraph({
        validators: [
          {
            id: "v1",
            kind: "gate",
            name: "self-review",
            fires_on_station: "in_review",
          },
        ],
        jit_prompts: [
          {
            id: "t1",
            kind: "jit_prompt",
            name: "stale-context",
            fires_on_event: "session.complete",
            fires_on_station: "in_review",
          },
        ],
      }),
    );
    expect(layout.jit_prompts).toHaveLength(1);
    const inReviewStation = must(
      layout.stations.find((s) => s.id === "in_review"),
      "in_review station missing",
    );
    const t0 = must(layout.jit_prompts[0], "jit_prompts[0]");
    const v0 = must(layout.validators[0], "validators[0]");
    expect(t0.x).toBe(inReviewStation.x);
    expect(t0.y).toBeLessThan(v0.y);
  });

  it("places artifacts below the wire under their producer station", () => {
    const layout = computeWorkflowLayout(
      buildGraph({
        artifacts: [
          { id: "a_plan", label: "plan.md", produced_by: "queued", consumed_by: "executing" },
        ],
      }),
    );
    expect(layout.artifacts).toHaveLength(1);
    const queuedStation = must(
      layout.stations.find((s) => s.id === "queued"),
      "queued station missing",
    );
    const a0 = must(layout.artifacts[0], "artifacts[0]");
    expect(a0.x).toBe(queuedStation.x);
    expect(a0.y).toBeGreaterThan(WORKFLOW_CANVAS.wireY);
  });

  it("places sources stacked vertically on the LEFT gutter", () => {
    const layout = computeWorkflowLayout(
      buildGraph({
        connectors: {
          sources: [
            { id: "linear", name: "Linear", wired_to_station: "planned", data: "issues" },
            { id: "github", name: "GitHub", wired_to_station: "planned" },
          ],
          sinks: [],
        },
      }),
    );
    expect(layout.sources).toHaveLength(2);
    const s0 = must(layout.sources[0], "sources[0]");
    const s1 = must(layout.sources[1], "sources[1]");
    expect(s0.x).toBeLessThan(WORKFLOW_CANVAS.gutterLeft);
    expect(s1.x).toBe(s0.x);
    expect(s1.y).not.toBe(s0.y);
  });

  it("places sinks stacked vertically on the RIGHT gutter", () => {
    const layout = computeWorkflowLayout(
      buildGraph({
        connectors: {
          sources: [],
          sinks: [{ id: "github_pr", name: "PR open", wired_from_station: "in_review" }],
        },
      }),
    );
    expect(layout.sinks).toHaveLength(1);
    const sink0 = must(layout.sinks[0], "sinks[0]");
    expect(sink0.x).toBeGreaterThan(WORKFLOW_CANVAS.width - WORKFLOW_CANVAS.gutterRight);
  });

  it("returns empty layout collections for an empty graph", () => {
    const layout = computeWorkflowLayout(buildGraph());
    expect(layout.validators).toEqual([]);
    expect(layout.jit_prompts).toEqual([]);
    expect(layout.artifacts).toEqual([]);
    expect(layout.sources).toEqual([]);
    expect(layout.sinks).toEqual([]);
  });

  it("returns a viewBox that expands to fit deep validator + JIT prompt stacks", () => {
    // 4 validators + 3 JIT prompts at the same station produce a stack
    // that pushes the top-most card y above the default 0 origin.
    // The viewBox must grow upward (negative y) so cards render
    // inside it; without this the top of the stack is clipped.
    const layout = computeWorkflowLayout(
      buildGraph({
        validators: Array.from({ length: 4 }, (_, i) => ({
          id: `v${i + 1}`,
          kind: "gate" as const,
          name: `validator-${i + 1}`,
          fires_on_station: "in_review",
        })),
        jit_prompts: Array.from({ length: 3 }, (_, i) => ({
          id: `t${i + 1}`,
          kind: "jit_prompt" as const,
          name: `jit-prompt-${i + 1}`,
          fires_on_station: "in_review",
        })),
      }),
    );
    const allTops = [
      ...layout.validators.map((v) => v.y - WORKFLOW_CARD_DIMS.validator.h / 2),
      ...layout.jit_prompts.map((t) => t.y - WORKFLOW_CARD_DIMS.jitPrompt.h / 2),
    ];
    const minTop = Math.min(...allTops);
    expect(minTop).toBeLessThan(0);
    expect(layout.viewBox.y).toBeLessThanOrEqual(minTop);
    expect(layout.viewBox.height).toBeGreaterThan(WORKFLOW_CANVAS.height);
  });

  it("produces non-overlapping bounding boxes for a dense same-station stack", () => {
    // Per round-3 PM follow-up: 4 validators + 3 JIT prompts at one
    // station must not overlap. Each card's bbox is centred on
    // (x, y) with the canonical width/height; assert no two
    // bounding boxes intersect.
    const layout = computeWorkflowLayout(
      buildGraph({
        validators: Array.from({ length: 4 }, (_, i) => ({
          id: `v${i + 1}`,
          kind: "gate" as const,
          name: `validator-${i + 1}`,
          fires_on_station: "in_review",
        })),
        jit_prompts: Array.from({ length: 3 }, (_, i) => ({
          id: `t${i + 1}`,
          kind: "jit_prompt" as const,
          name: `jit-prompt-${i + 1}`,
          fires_on_station: "in_review",
        })),
      }),
    );
    interface Bbox {
      id: string;
      x: number;
      y: number;
      w: number;
      h: number;
    }
    const boxes: Bbox[] = [
      ...layout.validators.map((v) => ({
        id: v.id,
        x: v.x - WORKFLOW_CARD_DIMS.validator.w / 2,
        y: v.y - WORKFLOW_CARD_DIMS.validator.h / 2,
        w: WORKFLOW_CARD_DIMS.validator.w,
        h: WORKFLOW_CARD_DIMS.validator.h,
      })),
      ...layout.jit_prompts.map((t) => ({
        id: t.id,
        x: t.x - WORKFLOW_CARD_DIMS.jitPrompt.w / 2,
        y: t.y - WORKFLOW_CARD_DIMS.jitPrompt.h / 2,
        w: WORKFLOW_CARD_DIMS.jitPrompt.w,
        h: WORKFLOW_CARD_DIMS.jitPrompt.h,
      })),
    ];
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i];
        const b = boxes[j];
        if (!a || !b) continue;
        const overlaps = a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
        expect(overlaps, `${a.id} overlaps ${b.id}`).toBe(false);
      }
    }
  });
});
