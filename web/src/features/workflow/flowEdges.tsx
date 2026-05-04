import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type EdgeProps,
} from "@xyflow/react";

import { Y_DEEP_RETURN } from "./flowGraph";
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
              fontSize: 10,
              color: "var(--color-ink)",
              letterSpacing: "0.04em",
              pointerEvents: "all",
              whiteSpace: "nowrap",
              zIndex: 50,
              boxShadow: "0 0 0 3px var(--color-paper)",
            }}
          >
            {d.label}
          </div>
        </EdgeLabelRenderer>
      )}
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
  const deep = Y_DEEP_RETURN;

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
              fontSize: 10,
              color: "var(--color-ink)",
              letterSpacing: "0.04em",
              pointerEvents: "all",
              whiteSpace: "nowrap",
              zIndex: 60,
              boxShadow: "0 0 0 4px var(--color-paper)",
            }}
          >
            {d.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
