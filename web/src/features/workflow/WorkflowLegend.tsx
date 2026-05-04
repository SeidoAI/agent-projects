import { ACTOR_COLOR, ACTOR_ORDER } from "./tokens";

export function WorkflowLegend() {
  return (
    <div
      data-testid="workflow-legend"
      style={{
        display: "flex",
        gap: 14,
        alignItems: "center",
        flexWrap: "wrap",
        marginTop: 8,
        fontFamily: "var(--font-mono)",
        fontSize: 10,
        color: "var(--color-ink-2)",
        padding: "8px 12px",
        background: "var(--color-paper-2)",
        border: "1px solid var(--color-edge)",
      }}
    >
      <Eyebrow>actors</Eyebrow>
      {ACTOR_ORDER.map((actor) => (
        <span
          key={actor}
          style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
        >
          <span
            style={{ width: 18, height: 3, background: ACTOR_COLOR[actor] }}
          />
          {actor}
        </span>
      ))}
      <span style={{ flex: 1 }} />
      <Eyebrow>route</Eyebrow>
      <RouteSwatch dash={null} label="forward" />
      <RouteSwatch dash="7 5" label="return" />
      <RouteSwatch dash="10 4 2 4" label="side" />
      <CrossLinkSwatch />
      <Eyebrow>markers</Eyebrow>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <svg width={14} height={14} aria-hidden>
          <rect
            x={2}
            y={6}
            width={10}
            height={6}
            stroke="var(--color-gate)"
            strokeWidth={1.4}
            fill="none"
          />
          <path
            d="M4 6 V4 a3 3 0 0 1 6 0 V6"
            stroke="var(--color-gate)"
            strokeWidth={1.4}
            fill="none"
          />
        </svg>
        gate cluster
      </span>
      <span
        data-testid="workflow-legend-heuristic"
        style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
      >
        <svg width={14} height={14} aria-hidden>
          <rect
            x={2}
            y={2}
            width={10}
            height={10}
            rx={3}
            stroke="var(--color-warn)"
            strokeWidth={1.4}
            fill="none"
          />
          <text
            x={7}
            y={10}
            textAnchor="middle"
            fontSize={9}
            fontWeight={700}
            fill="var(--color-warn)"
          >
            ~
          </text>
        </svg>
        heuristic
      </span>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <svg width={14} height={14} aria-hidden>
          <rect
            x={2}
            y={2}
            width={10}
            height={10}
            rx={3}
            stroke="var(--color-tripwire)"
            strokeWidth={1.4}
            fill="none"
          />
          <text
            x={7}
            y={10}
            textAnchor="middle"
            fontSize={9}
            fontWeight={700}
            fill="var(--color-tripwire)"
          >
            !
          </text>
        </svg>
        jit prompt
      </span>
    </div>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: 10,
        letterSpacing: "0.18em",
        textTransform: "uppercase",
        color: "var(--color-ink-3)",
      }}
    >
      {children}
    </span>
  );
}

function RouteSwatch({ dash, label }: { dash: string | null; label: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <svg width={36} height={10} aria-hidden>
        <path
          d="M2 5 L34 5"
          stroke="var(--color-ink)"
          strokeWidth={2}
          strokeDasharray={dash ?? undefined}
        />
      </svg>
      {label}
    </span>
  );
}

const CROSSLINK_SWATCH_HEX = "#0e7c8a";
function CrossLinkSwatch() {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <svg width={42} height={12} aria-hidden>
        {/* small teal dot at the start (matches the on-canvas endpoint
            circle), then a dashed teal line to indicate the cross-link
            edge connecting two workflows. */}
        <circle
          cx={4}
          cy={6}
          r={3.5}
          fill={CROSSLINK_SWATCH_HEX}
          stroke={CROSSLINK_SWATCH_HEX}
          strokeWidth={1}
        />
        <path
          d="M9 6 L40 6"
          stroke={CROSSLINK_SWATCH_HEX}
          strokeWidth={1.5}
          strokeDasharray="4 4"
        />
      </svg>
      cross-workflow
    </span>
  );
}
