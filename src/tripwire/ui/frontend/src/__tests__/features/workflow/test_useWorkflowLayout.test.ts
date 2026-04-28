import { describe, expect, it } from "vitest";

import { computeWorkflowLayout, WORKFLOW_CANVAS } from "@/features/workflow/useWorkflowLayout";
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
    tripwires: [],
    connectors: { sources: [], sinks: [] },
    artifacts: [],
    ...overrides,
  };
}

describe("computeWorkflowLayout", () => {
  it("evenly spaces 6 stations between left/right gutters on the wire", () => {
    const layout = computeWorkflowLayout(buildGraph());
    expect(layout.stations).toHaveLength(6);
    const xs = layout.stations.map((s) => s.x);
    expect(xs[0]).toBeGreaterThanOrEqual(WORKFLOW_CANVAS.gutterLeft);
    expect(xs[xs.length - 1]).toBeLessThanOrEqual(
      WORKFLOW_CANVAS.width - WORKFLOW_CANVAS.gutterRight,
    );
    for (let i = 1; i < xs.length; i++) {
      expect(xs[i]).toBeGreaterThan(xs[i - 1]);
    }
    // All stations sit on the central wire.
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
    const inReviewX = layout.stations.find((s) => s.id === "in_review")!.x;
    expect(layout.validators[0].x).toBe(inReviewX);
    expect(layout.validators[1].x).toBe(inReviewX);
    // Validators sit above the wire (lower y in screen coords).
    expect(layout.validators[0].y).toBeLessThan(WORKFLOW_CANVAS.wireY);
    // Stacked: second validator further from the wire than first.
    expect(layout.validators[1].y).toBeLessThan(layout.validators[0].y);
  });

  it("stacks tripwires above their fires_on_station alongside validators", () => {
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
        tripwires: [
          {
            id: "t1",
            kind: "tripwire",
            name: "stale-context",
            fires_on_event: "session.complete",
            fires_on_station: "in_review",
          },
        ],
      }),
    );
    expect(layout.tripwires).toHaveLength(1);
    const inReviewX = layout.stations.find((s) => s.id === "in_review")!.x;
    expect(layout.tripwires[0].x).toBe(inReviewX);
    // Tripwires stacked higher than the existing validator at that station.
    expect(layout.tripwires[0].y).toBeLessThan(layout.validators[0].y);
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
    const queuedX = layout.stations.find((s) => s.id === "queued")!.x;
    expect(layout.artifacts[0].x).toBe(queuedX);
    expect(layout.artifacts[0].y).toBeGreaterThan(WORKFLOW_CANVAS.wireY);
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
    expect(layout.sources[0].x).toBeLessThan(WORKFLOW_CANVAS.gutterLeft);
    expect(layout.sources[1].x).toBe(layout.sources[0].x);
    expect(layout.sources[1].y).not.toBe(layout.sources[0].y);
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
    expect(layout.sinks[0].x).toBeGreaterThan(WORKFLOW_CANVAS.width - WORKFLOW_CANVAS.gutterRight);
  });

  it("returns empty layout collections for an empty graph", () => {
    const layout = computeWorkflowLayout(buildGraph());
    expect(layout.validators).toEqual([]);
    expect(layout.tripwires).toEqual([]);
    expect(layout.artifacts).toEqual([]);
    expect(layout.sources).toEqual([]);
    expect(layout.sinks).toEqual([]);
  });
});
