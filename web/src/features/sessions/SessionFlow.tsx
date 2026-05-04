import { useEffect, useLayoutEffect, useMemo, useRef } from "react";

import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { layoutLayeredDag, roundedOrthogonalPath } from "./layeredDag";
import { colorForStatus, isCompletedLike, statusOrder, statusStyle } from "./sessionStatus";

interface SessionFlowProps {
  sessions: SessionSummary[];
  focusId: string | null;
  onSelect: (id: string) => void;
  /** When true, completed/verified sessions are kept regardless of distance from live work. */
  showAllCompleted: boolean;
}

const NODE_W = 168;
const NODE_H = 48;

/**
 * Hide completed/verified sessions that are >1 hop from any live session.
 * Keep every live session, plus completed/verified sessions that are
 * immediate neighbours (blocker or dependant) of one.
 */
function cullFarCompleted(sessions: SessionSummary[]): SessionSummary[] {
  const successors = new Map<string, string[]>();
  for (const s of sessions) {
    for (const b of s.blocked_by_sessions) {
      let arr = successors.get(b);
      if (!arr) {
        arr = [];
        successors.set(b, arr);
      }
      arr.push(s.id);
    }
  }
  const keep = new Set<string>();
  for (const s of sessions) {
    if (isCompletedLike(s.status)) continue;
    keep.add(s.id);
    for (const b of s.blocked_by_sessions) keep.add(b);
    for (const d of successors.get(s.id) ?? []) keep.add(d);
  }
  return sessions.filter((s) => keep.has(s.id));
}

export function SessionFlow({ sessions, focusId, onSelect, showAllCompleted }: SessionFlowProps) {
  const visible = useMemo(
    () => (showAllCompleted ? sessions : cullFarCompleted(sessions)),
    [sessions, showAllCompleted],
  );

  const sessionStatusById = useMemo(() => {
    const m = new Map<string, string>();
    for (const s of visible) m.set(s.id, s.status);
    return m;
  }, [visible]);

  const layout = useMemo(() => {
    return layoutLayeredDag(
      {
        nodes: visible.map((s) => ({ id: s.id })),
        // blocker → blocked: source must finish before target.
        edges: visible.flatMap((s) =>
          s.blocked_by_sessions
            .filter((b) => sessionStatusById.has(b))
            .map((b) => ({ source: b, target: s.id })),
        ),
        statusOrderOf: (id) => statusOrder(sessionStatusById.get(id) ?? "completed"),
      },
      { nodeWidth: NODE_W, nodeHeight: NODE_H },
    );
  }, [visible, sessionStatusById]);

  const containerRef = useRef<HTMLDivElement | null>(null);

  // Centre on the first executing session on first render only.
  const initialCenterApplied = useRef(false);
  useLayoutEffect(() => {
    if (initialCenterApplied.current) return;
    const el = containerRef.current;
    if (!el || visible.length === 0) return;
    const target =
      visible.find((s) => s.id === focusId) ??
      visible.find((s) => statusOrder(s.status) === 0) ??
      visible[0];
    if (!target) return;
    const pos = layout.positions[target.id];
    if (!pos) return;
    el.scrollTo({
      left: pos.x - el.clientWidth / 2,
      top: pos.y - el.clientHeight / 2,
      behavior: "auto",
    });
    initialCenterApplied.current = true;
  }, [layout, visible, focusId]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !focusId) return;
    if (!initialCenterApplied.current) return;
    const pos = layout.positions[focusId];
    if (!pos) return;
    el.scrollTo({
      left: pos.x - el.clientWidth / 2,
      top: pos.y - el.clientHeight / 2,
      behavior: "smooth",
    });
  }, [focusId, layout]);

  if (visible.length === 0) return null;

  return (
    <div
      ref={containerRef}
      data-testid="session-flow"
      className="relative max-h-[480px] overflow-auto rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2)"
    >
      <svg
        role="img"
        aria-label="Session dependency flow"
        width={Math.max(layout.width, 600)}
        height={Math.max(layout.height, 240)}
        className="block"
      >
        <title>Session dependency flow</title>
        <defs>
          {/* Single arrowhead — fill="context-stroke" inherits the path's
              own stroke colour (SVG2; supported in all current browsers).
              That way the arrow tints itself per status without needing
              a marker per colour. */}
          <marker
            id="session-flow-arrow"
            viewBox="0 0 10 10"
            refX="10"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto"
            markerUnits="userSpaceOnUse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" />
          </marker>
        </defs>

        {/* Edges first so the chips paint over their stubs. */}
        <g data-layer="edges">
          {layout.edges.map((e) => {
            const sourceSession = visible.find((s) => s.id === e.source);
            const baseColor = sourceSession
              ? colorForStatus(sourceSession.status)
              : "var(--color-edge)";
            const isOnFocus = focusId !== null && (e.source === focusId || e.target === focusId);
            const stroke = isOnFocus ? "var(--color-rule)" : baseColor;
            const opacity = focusId !== null && !isOnFocus ? 0.18 : 0.85;
            return (
              <path
                key={`${e.source}->${e.target}`}
                d={roundedOrthogonalPath(e.points, 10)}
                fill="none"
                stroke={stroke}
                strokeWidth={isOnFocus ? 3.5 : 2.5}
                strokeLinejoin="round"
                strokeLinecap="round"
                opacity={opacity}
                markerEnd="url(#session-flow-arrow)"
              />
            );
          })}
        </g>

        <g data-layer="nodes">
          {visible.map((s) => {
            const pos = layout.positions[s.id];
            if (!pos) return null;
            const style = statusStyle(s.status);
            const color = style.color;
            const isFocus = s.id === focusId;
            const fillOpacity = isFocus ? 1 : style.fillOpacity;
            const textColor =
              style.textOnFill === "paper" ? "var(--color-paper)" : "var(--color-ink)";
            const subTextColor =
              style.textOnFill === "paper" ? "var(--color-paper)" : "var(--color-ink-2)";
            return (
              // biome-ignore lint/a11y/useSemanticElements: SVG <g role="button"> is the standard pattern.
              <g
                key={s.id}
                role="button"
                tabIndex={0}
                aria-label={`Focus session ${s.name}`}
                data-testid={`session-flow-node-${s.id}`}
                data-focus={isFocus ? "true" : "false"}
                transform={`translate(${pos.x - NODE_W / 2}, ${pos.y - NODE_H / 2})`}
                onClick={() => onSelect(s.id)}
                onKeyDown={(ev) => {
                  if (ev.key === "Enter" || ev.key === " ") {
                    ev.preventDefault();
                    onSelect(s.id);
                  }
                }}
                style={{ cursor: "pointer", outline: "none" }}
              >
                <rect
                  width={NODE_W}
                  height={NODE_H}
                  rx={8}
                  fill={color}
                  fillOpacity={fillOpacity}
                  stroke={color}
                  strokeWidth={isFocus ? 2.4 : 1.4}
                />
                <text
                  x={12}
                  y={19}
                  fontFamily="var(--font-sans)"
                  fontSize={12}
                  fontWeight={600}
                  fill={textColor}
                  fillOpacity={s.status === "completed" && !isFocus ? 0.6 : 1}
                >
                  {truncate(s.name, 22)}
                </text>
                <text
                  x={12}
                  y={35}
                  fontFamily="var(--font-mono)"
                  fontSize={9}
                  fill={subTextColor}
                  fillOpacity={0.85}
                  letterSpacing={0.5}
                >
                  {style.label.toUpperCase()}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : `${s.slice(0, n - 1)}…`;
}
