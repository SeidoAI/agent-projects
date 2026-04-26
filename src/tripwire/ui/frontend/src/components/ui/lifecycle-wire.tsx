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
  /** Override the default 80px tall strip; useful for the mini variant. */
  height?: number;
  className?: string;
}

const PADDING_X = 20;
const VIEWBOX_W = 1000;

export function LifecycleWire({
  stations,
  currentIndex,
  counts,
  height = 80,
  className,
}: LifecycleWireProps) {
  const n = stations.length;
  // Stations are evenly spaced between PADDING_X and VIEWBOX_W - PADDING_X.
  // For a single station we fall back to centring it; the `Math.max(n-1, 1)`
  // avoids dividing by zero on a 1-station wire.
  const innerW = VIEWBOX_W - PADDING_X * 2;
  const stepX = innerW / Math.max(n - 1, 1);
  const cy = 32;

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
        viewBox={`0 0 ${VIEWBOX_W} 64`}
        width="100%"
        height={height}
        preserveAspectRatio="none"
        className="block"
        aria-hidden
      >
        <line
          x1={PADDING_X}
          y1={cy}
          x2={VIEWBOX_W - PADDING_X}
          y2={cy}
          stroke="var(--color-rule)"
          strokeWidth={1.6}
          strokeLinecap="round"
        />
        {stations.map((s, i) => {
          const x = PADDING_X + i * stepX;
          return (
            <g key={s.id}>
              <circle
                cx={x}
                cy={cy}
                r={9}
                fill="var(--color-paper)"
                stroke="var(--color-ink)"
                strokeWidth={1.4}
              />
              <circle cx={x} cy={cy} r={3.5} fill="var(--color-rule)" />
            </g>
          );
        })}
      </svg>

      <div
        className="absolute inset-0 grid"
        style={{ gridTemplateColumns: `repeat(${n}, 1fr)` }}
      >
        {stations.map((s, i) => {
          const isActive = currentIndex === i;
          const c = counts?.[s.id];
          return (
            <div
              key={s.id}
              aria-current={isActive ? "step" : undefined}
              className="flex flex-col items-center justify-end pb-1"
            >
              {c && c > 0 ? (
                <span className="-translate-y-2 absolute mb-12 inline-flex h-5 min-w-5 items-center justify-center rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) px-1 font-mono text-[10px] text-(--color-ink) leading-none">
                  {c}
                </span>
              ) : null}
              <div
                className={cn(
                  "font-sans text-[12px] leading-tight",
                  isActive
                    ? "text-(--color-ink) font-semibold"
                    : "text-(--color-ink-2)",
                )}
              >
                {s.label}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
