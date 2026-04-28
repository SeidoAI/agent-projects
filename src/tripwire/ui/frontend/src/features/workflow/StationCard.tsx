import { sessionStageColor } from "@/components/ui/session-stage-row";
import type { WorkflowStation } from "@/lib/api/endpoints/workflow";

const STATION_R = 14;
const LABEL_GAP = 18;

/**
 * Pure SVG station mark on the lifecycle wire — a filled circle in
 * the canonical session-stage colour with the station label and
 * ordinal stamped underneath. The fill comes from
 * [[session-stage-mapping]] so this map and the dashboard's
 * `SessionStageRow` share one visual vocabulary.
 *
 * The component does not handle interactivity — stations are read-
 * only on the workflow map (the workflow is the spec, not live state).
 */
export interface StationCardProps {
  station: WorkflowStation;
  x: number;
  y: number;
}

export function StationCard({ station, x, y }: StationCardProps) {
  const fill = sessionStageColor(station.id);
  return (
    <g>
      <circle
        cx={x}
        cy={y}
        r={STATION_R}
        fill={fill}
        stroke="var(--color-ink)"
        strokeWidth={1.4}
      />
      <text
        x={x}
        y={y - STATION_R - LABEL_GAP}
        textAnchor="middle"
        fontFamily="Bricolage Grotesque, var(--font-sans)"
        fontSize={13}
        fontWeight={600}
        fill="var(--color-ink)"
      >
        {station.label}
      </text>
      <text
        x={x}
        y={y + STATION_R + LABEL_GAP}
        textAnchor="middle"
        fontFamily="Geist Mono, var(--font-mono)"
        fontSize={10}
        fill="var(--color-ink-3)"
        letterSpacing="0.06em"
      >
        {String(station.n).padStart(2, "0")}
      </text>
    </g>
  );
}
