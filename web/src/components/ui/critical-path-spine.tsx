import type { CriticalPathResult } from "@/features/dashboard/hooks/useCriticalPath";
import { cn } from "@/lib/utils";

import { sessionStageColor } from "./session-stage-row";

/**
 * Horizontal spine of the longest in-flight dependency chain.
 *
 * Renders one chip per session, joined by `→` arrows. Each chip is
 * a button — clicking it (or the unlock badge above) sets the
 * blocker filter on the right-column sessions list, scoping it to
 * "this session + everything it directly blocks." The chain head
 * — the session whose unblocking moves the most downstream work
 * — gets a leading `▶` cursor mark.
 *
 * Three rendered states (decided in the parent based on
 * `CriticalPathResult`):
 *   - chain.length ≥ 2: render the chain
 *   - chain.length === 1 with inFlightCount > 1: "no chain — N
 *     independent sessions running"
 *   - inFlightCount === 0: "no in-flight sessions"
 */
export interface CriticalPathSpineProps {
  result: CriticalPathResult;
  /** Currently selected blocker (matches a chain session.id), or
   *  null when the blocker filter isn't active. */
  selectedBlocker: string | null;
  /** Click handler — fires with the clicked session's id. The
   *  parent typically toggles: prev === id ? null : id. */
  onSelectBlocker: (id: string) => void;
  className?: string;
}

export function CriticalPathSpine({
  result,
  selectedBlocker,
  onSelectBlocker,
  className,
}: CriticalPathSpineProps) {
  const { chain, fanout, tied, inFlightCount } = result;

  // Empty / no-chain states collapse the card chrome entirely —
  // it's an absence of news, not a section worth framing. Centred
  // serif italic + a small rule-red mark borrowed from the logo
  // language signals "tripwire ran, nothing to surface."
  if (chain.length < 2) {
    const message =
      inFlightCount === 0
        ? "No in-flight sessions"
        : `No critical path — ${inFlightCount} independent session${inFlightCount === 1 ? "" : "s"}`;
    return (
      <div className={cn("flex flex-col items-center gap-2 py-4", className)}>
        <span className="font-serif text-[14px] italic text-(--color-ink-3)">{message}</span>
        <TripwireMark />
      </div>
    );
  }

  return (
    <SpineFrame
      className={className}
      subtitle={`${chain.length} sessions deep · ${fanout} downstream${tied ? " · ties exist" : ""}`}
    >
      <ol className="flex flex-wrap items-end gap-x-2 gap-y-3 pt-14">
        {chain.map((session, idx) => {
          const color = sessionStageColor(session.status);
          const isHead = idx === 0;
          const isSelected = selectedBlocker === session.id;
          const directUnlocks = result.directUnlocks[session.id] ?? 0;
          const onClick = () => onSelectBlocker(session.id);
          return (
            <li key={session.id} className="flex items-end gap-2">
              {idx > 0 ? (
                <span aria-hidden className="pb-1.5 font-mono text-[12px] text-(--color-ink-3)">
                  →
                </span>
              ) : null}
              <div className="relative flex flex-col items-stretch">
                {directUnlocks > 0 ? (
                  <DirectUnlockBranch count={directUnlocks} onClick={onClick} />
                ) : null}
                <button
                  type="button"
                  onClick={onClick}
                  aria-pressed={isSelected}
                  aria-label={`Filter to sessions blocked by ${session.id}`}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-(--radius-stamp) border bg-(--color-paper) px-2 py-1 transition-colors",
                    isSelected
                      ? "border-(--color-rule) bg-(--color-rule)/10"
                      : isHead
                        ? "border-(--color-ink) hover:border-(--color-ink-3)"
                        : "border-(--color-edge) hover:border-(--color-ink-3)",
                  )}
                >
                  {isHead ? (
                    <span
                      aria-hidden
                      className="font-mono text-[10px] text-(--color-rule)"
                      title="critical-path head"
                    >
                      ▶
                    </span>
                  ) : null}
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    aria-hidden
                    style={{ background: color }}
                  />
                  <span className="font-mono text-[11px] text-(--color-ink)">{session.id}</span>
                </button>
              </div>
            </li>
          );
        })}
      </ol>
    </SpineFrame>
  );
}

/** Origin dot + quarter-arc + arrow + numbered circle above each
 *  chain chip, signalling "unblocking this also frees N parallel
 *  sessions the chain doesn't already show." The arc rises
 *  vertically from the chip's top-centre then sweeps horizontal-
 *  right, terminating in an arrow into the red circle.
 *
 *  Geometry (SVG viewBox 70×30, anchored bottom-left at chip top-
 *  centre — no x-translate):
 *    - Origin (0, 30) = chip's top-centre
 *    - Quadratic bezier with control at (0, 8) forces a vertical
 *      tangent at start and horizontal tangent at end (22, 8)
 *    - Arrow head triangle at (22..28, 8) pointing right
 *    - Filled red circle (r=14) at (44, 8) with white count
 */
function DirectUnlockBranch({ count, onClick }: { count: number; onClick: () => void }) {
  return (
    <>
      {/* Red origin dot sitting on the chip's top-centre border. */}
      <span
        aria-hidden
        className="-top-[3px] -translate-x-1/2 absolute left-1/2 h-1.5 w-1.5 rounded-full bg-(--color-rule)"
      />
      <button
        type="button"
        onClick={onClick}
        aria-label={`Filter to sessions directly unlocked (${count}) — click to filter`}
        className="absolute bottom-full left-1/2 block cursor-pointer border-0 bg-transparent p-0"
      >
        <svg
          width="70"
          height="48"
          viewBox="0 0 70 48"
          overflow="visible"
          aria-hidden
          role="presentation"
          className="block"
        >
          <title>directly unlocks {count}</title>
          {/* Quadratic bezier with control at (0, 16) gives a long
            vertical rise from y=48 → y≈16, then bends to horizontal
            terminating at (22, 16). Taller than the previous arc so
            the circle sits clearly above the chip rather than
            hugging it. */}
          <path
            d="M 0 48 Q 0 16 22 16"
            stroke="var(--color-rule)"
            strokeWidth="1.4"
            fill="none"
            strokeLinecap="round"
          />
          {/* Arrow tip lands at x=30, which is the circle's outer
            edge (cx=44 minus r=14) — tip touches the circle. */}
          <polygon points="22,11 22,21 30,16" fill="var(--color-rule)" />
          <circle
            cx="44"
            cy="16"
            r="14"
            fill="var(--color-rule)"
            stroke="var(--color-ink)"
            strokeWidth="1.4"
          />
          <text
            x="44"
            y="19.5"
            textAnchor="middle"
            fontFamily="Geist Mono, monospace"
            fontSize="11"
            fontWeight="700"
            fill="var(--color-paper)"
          >
            {count}
          </text>
        </svg>
      </button>
    </>
  );
}

/** A tiny rule-red horizontal line with a centred dot — the logo's
 *  "tripwire" motif (a wire with a stamp). Used to underline the
 *  no-critical-path empty state so the absence still feels intentional. */
function TripwireMark() {
  return (
    <svg
      width="400"
      height="10"
      viewBox="0 0 400 10"
      aria-hidden
      className="block"
      role="presentation"
    >
      <title>tripwire mark</title>
      <line
        x1="4"
        y1="5"
        x2="396"
        y2="5"
        stroke="var(--color-rule)"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <circle
        cx="200"
        cy="5"
        r="3"
        fill="var(--color-paper)"
        stroke="var(--color-rule)"
        strokeWidth="1.4"
      />
      <circle cx="200" cy="5" r="1" fill="var(--color-rule)" />
    </svg>
  );
}

function SpineFrame({
  children,
  subtitle,
  className,
}: {
  children: React.ReactNode;
  subtitle?: string;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) px-6 py-4",
        className,
      )}
    >
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h3 className="m-0 font-sans font-semibold text-[16px] text-(--color-ink) tracking-[-0.01em]">
          Critical path
        </h3>
        {subtitle ? (
          <span className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
            {subtitle}
          </span>
        ) : null}
      </div>
      {children}
    </section>
  );
}
