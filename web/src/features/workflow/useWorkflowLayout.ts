import { useMemo } from "react";

import type {
  WorkflowArtifact,
  WorkflowConnector,
  WorkflowGraph,
  WorkflowStation,
  WorkflowValidator,
} from "@/lib/api/endpoints/workflow";

/**
 * Canvas geometry for the workflow map.
 *
 * Stations evenly spaced on a horizontal wire at `wireY`; sources
 * stacked in the LEFT gutter; sinks in the RIGHT gutter;
 * validators + JIT prompts above the wire above their
 * `fires_on_station`; artifacts below the wire under `produced_by`.
 *
 * Layout is deterministic by entity-kind and by position in the
 * input array — keeps the rendered output stable when the API
 * registers a new entity (the diff is "one row added," not "the
 * whole graph relays out").
 *
 * The canvas is NOT space-constrained: viewBox bounds are computed
 * dynamically by `computeWorkflowLayout` from actual content so
 * tall validator stacks don't clip and the container scrolls.
 */
export const WORKFLOW_CANVAS = {
  width: 1380,
  /** Default minimum SVG height. Real height is `viewBox.height`
   *  computed dynamically from content; this is the fall-back when
   *  every entity fits inside the canonical band. */
  height: 820,
  wireY: 420,
  gutterLeft: 200,
  gutterRight: 200,
  validatorRowHeight: 96,
  validatorRowGap: 60,
  jitPromptRowGap: 40,
  artifactRowGap: 60,
  artifactRowHeight: 86,
  connectorRowGap: 70,
  connectorRowOffset: 40,
  /** Padding added around the bounding box of all entities when
   *  computing the viewBox so cards never touch the canvas edge. */
  paddingY: 40,
} as const;

/** Card / endpoint dimensions. Kept here so the layout maths can
 *  compute bounding boxes for overlap detection — the cards
 *  themselves render at these dimensions. */
export const WORKFLOW_CARD_DIMS = {
  validator: { w: 168, h: 84 },
  jitPrompt: { w: 184, h: 84 },
  artifact: { w: 156, h: 60 },
  endpoint: { w: 132, h: 32 },
} as const;

export interface PositionedStation extends WorkflowStation {
  x: number;
  y: number;
}

export interface PositionedValidator extends WorkflowValidator {
  x: number;
  y: number;
  /** 0-based stack index above the wire at this station. */
  stackIndex: number;
}

export interface PositionedArtifact extends WorkflowArtifact {
  x: number;
  y: number;
}

export interface PositionedConnector extends WorkflowConnector {
  x: number;
  y: number;
  /** Station-id this connector lands on (sources) or leaves from (sinks). */
  attachStation: string | undefined;
}

export interface WorkflowLayout {
  stations: PositionedStation[];
  validators: PositionedValidator[];
  jit_prompts: PositionedValidator[];
  artifacts: PositionedArtifact[];
  sources: PositionedConnector[];
  sinks: PositionedConnector[];
  /** Dynamic SVG viewBox covering every positioned entity plus
   *  `paddingY`. The container scrolls when the viewBox height
   *  exceeds the visible viewport. */
  viewBox: { x: number; y: number; width: number; height: number };
}

/**
 * Pure layout computation. The hook wrapper memoises against the
 * graph identity; callers usually pass the TanStack Query cached
 * object directly so re-renders that don't change the data don't
 * re-lay-out.
 */
export function computeWorkflowLayout(graph: WorkflowGraph): WorkflowLayout {
  const stations = layoutStations(graph.lifecycle.stations);
  const stationXById = new Map(stations.map((s) => [s.id, s.x] as const));

  const validatorStackByStation = new Map<string, number>();
  const validators: PositionedValidator[] = graph.validators.map((v) => {
    const idx = validatorStackByStation.get(v.fires_on_station) ?? 0;
    validatorStackByStation.set(v.fires_on_station, idx + 1);
    const x = stationXById.get(v.fires_on_station) ?? WORKFLOW_CANVAS.width / 2;
    const y =
      WORKFLOW_CANVAS.wireY -
      WORKFLOW_CANVAS.validatorRowGap -
      idx * WORKFLOW_CANVAS.validatorRowHeight;
    return { ...v, x, y, stackIndex: idx };
  });

  // JIT prompts stack above the validator stack at each station, so a
  // station with 2 validators + 1 JIT prompt renders [p1, v2, v1] from
  // top down. The visual band is "above the wire," and JIT prompts
  // sit higher to reinforce the cognitive ordering: gates first
  // (closer to the wire they gate), prompts further out (loud,
  // attention-getting).
  const jit_prompts: PositionedValidator[] = graph.jit_prompts.map((t) => {
    const validatorCount = validatorStackByStation.get(t.fires_on_station) ?? 0;
    const promptOffset = validatorStackByStation.get(`__jp__${t.fires_on_station}`) ?? 0;
    validatorStackByStation.set(`__jp__${t.fires_on_station}`, promptOffset + 1);
    const x = stationXById.get(t.fires_on_station) ?? WORKFLOW_CANVAS.width / 2;
    const y =
      WORKFLOW_CANVAS.wireY -
      WORKFLOW_CANVAS.validatorRowGap -
      validatorCount * WORKFLOW_CANVAS.validatorRowHeight -
      WORKFLOW_CANVAS.jitPromptRowGap -
      promptOffset * WORKFLOW_CANVAS.validatorRowHeight;
    return { ...t, x, y, stackIndex: validatorCount + promptOffset };
  });

  const artifactStackByStation = new Map<string, number>();
  const artifacts: PositionedArtifact[] = graph.artifacts.map((a) => {
    const idx = artifactStackByStation.get(a.produced_by) ?? 0;
    artifactStackByStation.set(a.produced_by, idx + 1);
    const x = stationXById.get(a.produced_by) ?? WORKFLOW_CANVAS.width / 2;
    const y =
      WORKFLOW_CANVAS.wireY +
      WORKFLOW_CANVAS.artifactRowGap +
      idx * WORKFLOW_CANVAS.artifactRowHeight;
    return { ...a, x, y };
  });

  const sources: PositionedConnector[] = graph.connectors.sources.map((c, i) => ({
    ...c,
    attachStation: c.wired_to_station,
    x: WORKFLOW_CANVAS.gutterLeft - WORKFLOW_CANVAS.connectorRowOffset,
    y:
      WORKFLOW_CANVAS.wireY -
      ((graph.connectors.sources.length - 1) / 2) * WORKFLOW_CANVAS.connectorRowGap +
      i * WORKFLOW_CANVAS.connectorRowGap,
  }));

  const sinks: PositionedConnector[] = graph.connectors.sinks.map((c, i) => ({
    ...c,
    attachStation: c.wired_from_station,
    x: WORKFLOW_CANVAS.width - WORKFLOW_CANVAS.gutterRight + WORKFLOW_CANVAS.connectorRowOffset,
    y:
      WORKFLOW_CANVAS.wireY -
      ((graph.connectors.sinks.length - 1) / 2) * WORKFLOW_CANVAS.connectorRowGap +
      i * WORKFLOW_CANVAS.connectorRowGap,
  }));

  const viewBox = computeViewBox({ validators, jit_prompts, artifacts, sources, sinks });
  return { stations, validators, jit_prompts, artifacts, sources, sinks, viewBox };
}

/** Compute the dynamic SVG viewBox so every entity (plus
 *  `paddingY`) is inside it. Validator stacks 4+ deep at one
 *  station push card y values negative; this expands the viewBox
 *  upward to keep them visible instead of clipping. */
function computeViewBox(layout: {
  validators: PositionedValidator[];
  jit_prompts: PositionedValidator[];
  artifacts: PositionedArtifact[];
  sources: PositionedConnector[];
  sinks: PositionedConnector[];
}): { x: number; y: number; width: number; height: number } {
  let minY: number = 0;
  let maxY: number = WORKFLOW_CANVAS.height;
  for (const v of layout.validators) {
    minY = Math.min(minY, v.y - WORKFLOW_CARD_DIMS.validator.h / 2);
    maxY = Math.max(maxY, v.y + WORKFLOW_CARD_DIMS.validator.h / 2);
  }
  for (const t of layout.jit_prompts) {
    minY = Math.min(minY, t.y - WORKFLOW_CARD_DIMS.jitPrompt.h / 2);
    maxY = Math.max(maxY, t.y + WORKFLOW_CARD_DIMS.jitPrompt.h / 2);
  }
  for (const a of layout.artifacts) {
    maxY = Math.max(maxY, a.y + WORKFLOW_CARD_DIMS.artifact.h / 2);
  }
  for (const c of [...layout.sources, ...layout.sinks]) {
    minY = Math.min(minY, c.y - WORKFLOW_CARD_DIMS.endpoint.h / 2);
    maxY = Math.max(maxY, c.y + WORKFLOW_CARD_DIMS.endpoint.h / 2);
  }
  const top = minY - WORKFLOW_CANVAS.paddingY;
  const bottom = maxY + WORKFLOW_CANVAS.paddingY;
  return { x: 0, y: top, width: WORKFLOW_CANVAS.width, height: bottom - top };
}

function layoutStations(stations: WorkflowStation[]): PositionedStation[] {
  if (stations.length === 0) return [];
  const innerW = WORKFLOW_CANVAS.width - WORKFLOW_CANVAS.gutterLeft - WORKFLOW_CANVAS.gutterRight;
  const stepX = innerW / Math.max(stations.length - 1, 1);
  return stations.map((s, i) => ({
    ...s,
    x: WORKFLOW_CANVAS.gutterLeft + i * stepX,
    y: WORKFLOW_CANVAS.wireY,
  }));
}

export function useWorkflowLayout(graph: WorkflowGraph | undefined): WorkflowLayout | undefined {
  return useMemo(() => (graph ? computeWorkflowLayout(graph) : undefined), [graph]);
}
