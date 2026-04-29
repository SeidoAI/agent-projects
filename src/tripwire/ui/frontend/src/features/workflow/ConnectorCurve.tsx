/**
 * Single SVG path connecting two layout points with a horizontally-
 * biased cubic Bézier. Used everywhere the workflow map needs a
 * wire: source → station, station → sink, station → artifact,
 * artifact → consumer station.
 *
 * The control points pull out horizontally so the curve enters and
 * leaves each endpoint roughly tangent to the page x-axis — keeps
 * dense layouts legible without a graph library.
 */
export interface Point {
  x: number;
  y: number;
}

export interface ConnectorCurveProps {
  id: string;
  from: Point;
  to: Point;
  /** When true the path drops to ~25% opacity (hover-highlight). */
  dimmed: boolean;
  /** Override the default stroke colour (defaults to the rule red). */
  stroke?: string;
}

export function ConnectorCurve({ id, from, to, dimmed, stroke }: ConnectorCurveProps) {
  const dx = Math.max(40, Math.abs(to.x - from.x) / 2);
  const c1x = from.x + (to.x >= from.x ? dx : -dx);
  const c2x = to.x - (to.x >= from.x ? dx : -dx);
  const d = `M${from.x},${from.y} C${c1x},${from.y} ${c2x},${to.y} ${to.x},${to.y}`;
  return (
    <path
      d={d}
      data-connector-id={id}
      fill="none"
      stroke={stroke ?? "var(--color-rule)"}
      strokeWidth={1.4}
      strokeLinecap="round"
      opacity={dimmed ? 0.25 : 1}
      style={{ transition: "opacity 120ms ease-out" }}
    />
  );
}
