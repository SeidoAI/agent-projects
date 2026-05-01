import { cn } from "@/lib/utils";

/**
 * The recurring red rule + stamped circles primitive (per spec §3.1 C0.4).
 *
 * Used as a header strip on the Dashboard, threaded through Board column
 * headers (S2), as the spine of the Workflow Map (S5), and as a mini
 * progress indicator on Session Detail (S3).
 *
 * Only the Dashboard variant lands in S1 — counts above stations and an
 * optional `currentIndex` highlight for context-sensitive consumers.
 */
export interface LifecycleStation {
  id: string;
  label: string;
}

export interface LifecycleWireProps {
  stations: LifecycleStation[];
  /** 0-based index of the active station; rendered with aria-current="step". */
  currentIndex?: number;
  /** Map of station-id → integer count rendered as a small badge above the dot. */
  counts?: Record<string, number>;
  /**
   * Map of station-id → array of session ids at that station. When
   * provided, each station renders a vertical stack of small dots
   * above its circle (one dot per session, capped to MAX_VISIBLE_DOTS
   * with a "+N" overflow). Visualises load per stage at a glance.
   */
  sessionIdsByStation?: Record<string, string[]>;
  /**
   * Controlled selection. When set, the matching station's circle
   * is highlighted (filled rule-red) so the rest of the page can
   * filter / scope to it.
   */
  selectedStation?: string | null;
  /**
   * Click handler. Fires with the clicked station id. Parents
   * typically toggle: `prev === id ? null : id`.
   */
  onStationClick?: (stationId: string) => void;
  /** Override the default 80px tall strip; useful for the mini variant. */
  height?: number;
  className?: string;
}

const PADDING_X = 20;
const VIEWBOX_W = 1000;
const MAX_VISIBLE_DOTS = 5;
// SVG band y-coords. The wire line runs at WIRE_Y; dots stack above
// it from DOT_BAND_BOTTOM upward; the SVG is sized tall enough to fit
// the dot column.
const SVG_H = 96;
const WIRE_Y = 70;
const DOT_R = 3;
const DOT_GAP = 3;

export function LifecycleWire({
  stations,
  currentIndex,
  counts,
  sessionIdsByStation,
  selectedStation,
  onStationClick,
  height = 80,
  className,
}: LifecycleWireProps) {
  const n = stations.length;
  // Stations are evenly spaced between PADDING_X and VIEWBOX_W - PADDING_X.
  // For a single station we fall back to centring it; the `Math.max(n-1, 1)`
  // avoids dividing by zero on a 1-station wire.
  const innerW = VIEWBOX_W - PADDING_X * 2;
  const stepX = innerW / Math.max(n - 1, 1);
  const interactive = Boolean(onStationClick);

  return (
    <div
      className={cn(
        "relative w-full",
        // The component renders against the cream paper-2 surface by default.
        className,
      )}
      style={{ height }}
    >
      <svg
        viewBox={`0 0 ${VIEWBOX_W} ${SVG_H}`}
        width="100%"
        height={height}
        preserveAspectRatio="none"
        className="block"
        aria-hidden
        role="presentation"
      >
        <title>Lifecycle wire</title>
        <line
          x1={PADDING_X}
          y1={WIRE_Y}
          x2={VIEWBOX_W - PADDING_X}
          y2={WIRE_Y}
          stroke="var(--color-rule)"
          strokeWidth={1.6}
          strokeLinecap="round"
        />
        {stations.map((s, i) => {
          const x = PADDING_X + i * stepX;
          const isSelected = selectedStation === s.id;
          // Stacked dots above the wire — one per session, capped at
          // MAX_VISIBLE_DOTS. The base of the stack sits a few pixels
          // above the station circle so it doesn't crowd the wire.
          const ids = sessionIdsByStation?.[s.id] ?? [];
          const visible = Math.min(ids.length, MAX_VISIBLE_DOTS);
          const overflow = ids.length - visible;
          const dotBaseY = WIRE_Y - 14; // a notch above the wire
          return (
            <g key={s.id}>
              {/* Stacked session dots above the wire — keyed by the
                  actual session id so React doesn't reorder dots when
                  the underlying list changes. Slice cap is in
                  MAX_VISIBLE_DOTS, the rest surface as "+N" overflow
                  text below. */}
              {ids.slice(0, visible).map((sid, di) => (
                <circle
                  key={sid}
                  cx={x}
                  cy={dotBaseY - di * (DOT_R * 2 + DOT_GAP)}
                  r={DOT_R}
                  fill={isSelected ? "var(--color-rule)" : "var(--color-ink-2)"}
                  opacity={isSelected ? 1 : 0.7}
                />
              ))}
              {/* Station circle on the wire — filled rule-red when selected. */}
              <circle
                cx={x}
                cy={WIRE_Y}
                r={9}
                fill={isSelected ? "var(--color-rule)" : "var(--color-paper)"}
                stroke="var(--color-ink)"
                strokeWidth={1.4}
              />
              <circle
                cx={x}
                cy={WIRE_Y}
                r={3.5}
                fill={isSelected ? "var(--color-paper)" : "var(--color-rule)"}
              />
              {/* Overflow text below the dot stack ("+3" if 8 sessions). */}
              {overflow > 0 ? (
                <text
                  x={x}
                  y={dotBaseY - visible * (DOT_R * 2 + DOT_GAP) + 1}
                  fontFamily="Geist Mono, monospace"
                  fontSize={8}
                  fill="var(--color-ink-3)"
                  textAnchor="middle"
                >
                  +{overflow}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>

      <div className="absolute inset-0 grid" style={{ gridTemplateColumns: `repeat(${n}, 1fr)` }}>
        {stations.map((s, i) => {
          const isActive = currentIndex === i;
          const isSelected = selectedStation === s.id;
          const c = counts?.[s.id];
          const Cell = interactive ? "button" : "div";
          const cellClass = cn(
            "flex flex-col items-center justify-end pb-1",
            interactive && "cursor-pointer transition-colors",
            interactive &&
              (isSelected
                ? "text-(--color-ink) font-semibold"
                : "text-(--color-ink-2) hover:text-(--color-ink)"),
          );
          return (
            <Cell
              key={s.id}
              type={interactive ? "button" : undefined}
              onClick={interactive ? () => onStationClick?.(s.id) : undefined}
              aria-pressed={interactive ? isSelected : undefined}
              aria-current={isActive ? "step" : undefined}
              aria-label={interactive ? `Filter to ${s.label} (${c ?? 0})` : undefined}
              className={cellClass}
            >
              <div
                className={cn(
                  "font-sans text-[12px] leading-tight",
                  isActive || isSelected
                    ? "text-(--color-ink) font-semibold"
                    : "text-(--color-ink-2)",
                )}
              >
                {s.label}
              </div>
              {c !== undefined && c >= 0 ? (
                <div className="mt-0.5 font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
                  {String(i + 1).padStart(2, "0")} · {c}
                </div>
              ) : null}
            </Cell>
          );
        })}
      </div>
    </div>
  );
}
