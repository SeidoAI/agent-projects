import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type EdgeProps,
} from "@xyflow/react";

import { CROSSLINK_BUS_X, Y_DEEP_RETURN, Y_WORK } from "./flowGraph";
import { ACTOR_COLOR, isKnownActor } from "./tokens";

export interface ActorEdgeData extends Record<string, unknown> {
  actor: string;
  kind: string;
  label?: string;
}

const DASH_BY_KIND: Record<string, string | undefined> = {
  return: "7 5",
  side: "10 4 2 4",
  loop: "4 4",
};

const actorStroke = (actor: string): string =>
  isKnownActor(actor) ? ACTOR_COLOR[actor] : "var(--color-ink)";

export function ActorEdge(props: EdgeProps) {
  const {
    id,
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    markerEnd,
    data,
  } = props;
  const d = (data ?? {}) as ActorEdgeData;
  const stroke = actorStroke(d.actor);
  const dash = DASH_BY_KIND[d.kind];

  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 12,
  });

  return (
    <>
      <BaseEdge
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke,
          strokeWidth: 2,
          strokeDasharray: dash,
        }}
      />
      {d.label && (
        <EdgeLabelRenderer>
          <div
            data-testid={`workflow-edge-label-${id}`}
            className="nodrag nopan"
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              padding: "2px 8px",
              background: "var(--color-paper)",
              border: `1px solid ${stroke}`,
              borderRadius: 2,
              fontFamily: "var(--font-mono)",
              fontSize: 10.5,
              color: "var(--color-ink)",
              letterSpacing: "0.04em",
              pointerEvents: "all",
              whiteSpace: "nowrap",
              zIndex: 1000,
            }}
          >
            {d.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

// ── CrossLinkEdge: connects a status in one workflow band to a status
// in another. Routes south out of the source region's bottom, traverses
// the inter-band gutter, then drops into the target band on a dedicated
// lane *above* the inputs band — so the cross-link never crosses any
// material-input chip docking on the same north edge. Distinct visual
// (dashed indigo) marks it as a cross-workflow link, not an intra-workflow
// transition.
export interface CrossLinkEdgeData extends Record<string, unknown> {
  sourceWorkflow: string;
  label?: string | null;
  /** Absolute Y of the in-band cross-link lane in the SOURCE band
   *  (Y_CROSSLINK_LANE relative to bandTop). Routing the outbound
   *  horizontal here keeps the line in clear space between inputs and
   *  work-steps. */
  sourceLaneY?: number | null;
  /** Absolute Y of the in-band cross-link lane in the TARGET band. */
  targetLaneY?: number | null;
}

// Cross-link colour — picked to stand apart from every actor hue:
//   pm-agent (var(--color-tripwire) #b8741a ochre)
//   coding-agent (var(--color-gate) #2d5a3d green)
//   code (var(--color-info) #2d3a7c indigo)
// Teal sits diagonally opposite all three on the wheel and reads as
// "this is metadata, not a route."
const CROSSLINK_HEX = "#0e7c8a";

export function CrossLinkEdge(props: EdgeProps) {
  const { id, sourceX, sourceY, targetX, targetY, markerEnd, data } = props;
  const d = (data ?? {}) as CrossLinkEdgeData;
  const stroke = CROSSLINK_HEX;
  const dash = "4 4";
  const r = 12;

  // Route every cross-link through a shared vertical bus on the far
  // left of the canvas (CROSSLINK_BUS_X). Horizontal segments live in
  // the IN-BAND cross-link lane of each band — between the inputs band
  // and the work line, an empty stripe at every region's top. So the
  // line:
  //   1) exits the source dot UPWARD (north of the work_step)
  //   2) rises into the source band's in-band lane
  //   3) runs west to the bus
  //   4) up/down the bus to the target band's in-band lane
  //   5) east across the target band to under the target dot
  //   6) drops down into the target dot
  // Nothing crosses inputs, outputs, work-steps, or the band edges.
  const busX = CROSSLINK_BUS_X;
  const FALLBACK_OFFSET = 170;
  const sourceTurnY =
    typeof d.sourceLaneY === "number"
      ? d.sourceLaneY
      : sourceY - FALLBACK_OFFSET;
  const targetTurnY =
    typeof d.targetLaneY === "number"
      ? d.targetLaneY
      : targetY - FALLBACK_OFFSET;

  // Source dot is on the work_step's NORTH, lane is ABOVE it
  // (smaller Y), so the source approach goes UP — we stop r below
  // sourceTurnY (= sourceTurnY + r) before arcing west.
  // Target dot is also on the work_step's NORTH, target lane is
  // ABOVE it, so the final segment drops DOWN (lane → dot) — same
  // sign as before.
  const sourceApproachY =
    sourceY > sourceTurnY ? sourceTurnY + r : sourceTurnY - r;
  const path = [
    `M ${sourceX} ${sourceY}`,
    `L ${sourceX} ${sourceApproachY}`,
    `Q ${sourceX} ${sourceTurnY}, ${sourceX - r} ${sourceTurnY}`,
    `L ${busX + r} ${sourceTurnY}`,
    `Q ${busX} ${sourceTurnY}, ${busX} ${sourceTurnY + (targetTurnY > sourceTurnY ? r : -r)}`,
    `L ${busX} ${targetTurnY - (targetTurnY > sourceTurnY ? r : -r)}`,
    `Q ${busX} ${targetTurnY}, ${busX + r} ${targetTurnY}`,
    `L ${targetX - r} ${targetTurnY}`,
    `Q ${targetX} ${targetTurnY}, ${targetX} ${targetTurnY + r}`,
    `L ${targetX} ${targetY}`,
  ].join(" ");

  // Two labels per edge — one near each end — so the user reads the
  // link's purpose while looking AT the source dot OR the target dot,
  // not from the middle of the bus where it'd be off-screen.
  //
  // Labels are RIGHT-ANCHORED at a fixed inboard distance from the
  // dot's X (translate -100% on X). This makes the label's right edge
  // sit at exactly DOT_CLEARANCE px from the dot regardless of the
  // label text length — long labels grow leftwards into open canvas,
  // never crowding the dot.
  const DOT_CLEARANCE = 56;
  const sourceLabelRightX = sourceX - DOT_CLEARANCE;
  const targetLabelRightX = targetX - DOT_CLEARANCE;
  const labelText = d.label ?? d.sourceWorkflow;
  // Translucent paper background so the dashed line shows through the
  // label rather than being masked by a solid halo. Label text + border
  // remain at full opacity for legibility.
  // Solid paper background so the dashed line is fully masked behind
  // the label (label sits OVER the line) and text reads at full
  // contrast. The original "translucent" interpretation was wrong —
  // user wants the label to occlude the line, not blend with it.
  const labelStyle: React.CSSProperties = {
    position: "absolute",
    padding: "3px 10px",
    background: "var(--color-paper)",
    border: `1px dashed ${stroke}`,
    borderRadius: 2,
    fontFamily: "var(--font-mono)",
    fontSize: 10.5,
    color: stroke,
    letterSpacing: "0.04em",
    pointerEvents: "all",
    whiteSpace: "nowrap",
    zIndex: 1000,
  };

  return (
    <>
      <BaseEdge
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke,
          strokeWidth: 1.5,
          strokeDasharray: dash,
          fill: "none",
        }}
      />
      <EdgeLabelRenderer>
        <div
          data-testid={`workflow-crosslink-label-${id}-source`}
          className="nodrag nopan"
          style={{
            ...labelStyle,
            transform: `translate(-100%, -50%) translate(${sourceLabelRightX}px, ${sourceTurnY}px)`,
          }}
        >
          ↗ {labelText}
        </div>
        <div
          data-testid={`workflow-crosslink-label-${id}-target`}
          className="nodrag nopan"
          style={{
            ...labelStyle,
            transform: `translate(-100%, -50%) translate(${targetLabelRightX}px, ${targetTurnY}px)`,
          }}
        >
          ↘ {labelText}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

// ── ReturnEdge: a south-routed step path used for backwards (return)
// outcomes from a branch diamond. Path goes:
//   source → straight down to Y_DEEP_RETURN → west across to target X
//   → straight up into target. Label sits on the deep horizontal segment,
// well below any forward arrows.
export function ReturnEdge(props: EdgeProps) {
  const { id, sourceX, sourceY, targetX, targetY, markerEnd, data } = props;
  const d = (data ?? {}) as ActorEdgeData;
  const stroke = actorStroke(d.actor);
  const dash = "7 5";
  // Y_DEEP_RETURN is a band-RELATIVE constant. In the unified canvas,
  // sourceY is absolute (band offset baked in), so deriving `deep` from
  // the constant directly puts the U-turn at band 0's depth — making
  // returns in lower bands shoot up to the top of the canvas. Compute
  // deep from sourceY's offset within its band so the U-turn lands in
  // the same per-band lane regardless of which band we're in.
  const deep = sourceY + (Y_DEEP_RETURN - Y_WORK);

  // step path with rounded corners
  const r = 18;
  const path = [
    `M ${sourceX} ${sourceY}`,
    `L ${sourceX} ${deep - r}`,
    `Q ${sourceX} ${deep}, ${sourceX - r} ${deep}`,
    `L ${targetX + r} ${deep}`,
    `Q ${targetX} ${deep}, ${targetX} ${deep - r}`,
    `L ${targetX} ${targetY}`,
  ].join(" ");

  const labelX = (sourceX + targetX) / 2;
  const labelY = deep;

  return (
    <>
      <BaseEdge
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke,
          strokeWidth: 2,
          strokeDasharray: dash,
          fill: "none",
        }}
      />
      {d.label && (
        <EdgeLabelRenderer>
          <div
            data-testid={`workflow-edge-label-${id}`}
            className="nodrag nopan"
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              padding: "3px 10px",
              background: "var(--color-paper)",
              border: `1.2px solid ${stroke}`,
              borderRadius: 2,
              fontFamily: "var(--font-mono)",
              fontSize: 10.5,
              color: "var(--color-ink)",
              letterSpacing: "0.04em",
              pointerEvents: "all",
              whiteSpace: "nowrap",
              // High zIndex so the label sits OVER the dashed return
              // line — same readability rule as cross-link labels. No
              // halo/box-shadow; the solid paper background masks the
              // line directly behind the label.
              zIndex: 1000,
            }}
          >
            {d.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
