import { Handle, NodeToolbar, Position, type NodeProps } from "@xyflow/react";
import { useState } from "react";

import { ACTOR_COLOR, ACTOR_LABEL, isKnownActor, statusHex, statusTint } from "./tokens";
import {
  HEADER_H,
  TILE_FOLD,
  TILE_H,
  TILE_ICON_GAP,
  TILE_PAD_L,
  TILE_PAD_RIGHT,
  TILE_W,
  TX_H,
  TX_W,
  WORK_H,
  WORK_W,
  Y_HEADER_TOP,
  Y_WORK,
  type BoundaryNodeData,
  type BranchNodeData,
  type ChipNodeData,
  type DetourNodeData,
  type JitNodeData,
  type PortNodeData,
  type StatusNodeData,
  type TileNodeData,
  type WorkStepNodeData,
} from "./flowGraph";

const actorColor = (actor: string): string =>
  isKnownActor(actor) ? ACTOR_COLOR[actor] : "var(--color-ink)";

const actorLabel = (actor: string): string =>
  isKnownActor(actor) ? ACTOR_LABEL[actor] : actor.toUpperCase();

const hiddenHandle = {
  visibility: "hidden" as const,
  pointerEvents: "none" as const,
  width: 1,
  height: 1,
};

// ── status region (parent group) ──────────────────────────────────
export function StatusRegionNode({ data }: NodeProps) {
  const d = data as unknown as StatusNodeData;
  // Background = neutral paper with a soft status-coloured wash that fades
  // out beneath the top stripe. Status colour lives at the band's edge —
  // the 3px stripe plus a short gradient — and the body of the region is
  // plain paper, so actor-coloured nodes (PM ochre, Coding green, Code
  // indigo) inside don't clash with a full wash.
  const stripe = statusHex(d.status.id);
  const wash = statusTint(d.status.id, 0.18);
  return (
    <div
      data-testid={`workflow-region-${d.status.id}`}
      data-status={d.status.id}
      style={{
        width: d.width,
        height: d.height,
        position: "relative",
        background: `linear-gradient(to bottom, ${wash} 0px, var(--color-paper) 64px)`,
        boxSizing: "border-box",
        borderTop: `3px solid ${stripe}`,
      }}
    >
      {/* header band */}
      <div
        style={{
          position: "absolute",
          top: Y_HEADER_TOP,
          left: 18,
          right: 18,
          height: HEADER_H - 8,
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            color: "var(--color-ink-3)",
            letterSpacing: "0.18em",
          }}
        >
          {String(d.index + 1).padStart(2, "0")} · STATUS
        </div>
        <div
          style={{
            fontFamily: "var(--font-sans)",
            fontWeight: 600,
            fontSize: 26,
            color: "var(--color-ink)",
            letterSpacing: "-0.015em",
            marginTop: 6,
            lineHeight: 1.05,
          }}
        >
          {d.status.id}
        </div>
        {d.blurb && (
          <div
            style={{
              fontFamily: "var(--font-serif)",
              fontStyle: "italic",
              fontSize: 13.5,
              color: "var(--color-ink-2)",
              marginTop: 4,
            }}
          >
            {d.blurb}
          </div>
        )}
        {d.terminal && (
          <div
            style={{
              position: "absolute",
              top: 0,
              right: 0,
              width: 12,
              height: 12,
              borderRadius: "50%",
              background: "var(--color-ink)",
            }}
          />
        )}
      </div>

      {/* dashed band dividers — outputs divider uses dynamic position so
          it stays just above the (possibly stacked) outputs band. */}
      <DashedRule y={d.inputsTop - 6} />
      <DashedRule y={d.inputsBottom + 6} />
      <DashedRule y={d.outputsTop - 12} />

      {/* compass labels */}
      <BandCaption y={d.inputsTop - 22} text="NORTH · INPUTS" />
      <BandCaption y={d.outputsTop - 22} text="SOUTH · OUTPUTS" />

      {/* hidden handles for the region anchor edge target */}
      <Handle id="left" type="target" position={Position.Left} style={{ ...hiddenHandle, top: Y_WORK }} />
      <Handle id="right" type="source" position={Position.Right} style={{ ...hiddenHandle, top: Y_WORK }} />
      {/* north/south handles for cross-workflow links — sit at the
          band's vertical edges (top centre / bottom centre). Hidden but
          functional; the CrossLinkEdge renders the visible chrome. */}
      <Handle
        id="north"
        type="target"
        position={Position.Top}
        style={{ ...hiddenHandle, left: d.width / 2 }}
      />
      <Handle
        id="south"
        type="source"
        position={Position.Bottom}
        style={{ ...hiddenHandle, left: d.width / 2 }}
      />
    </div>
  );
}

function DashedRule({ y }: { y: number }) {
  return (
    <div
      style={{
        position: "absolute",
        top: y,
        left: 0,
        right: 0,
        height: 0,
        borderTop: "1px dashed var(--color-edge)",
        opacity: 0.7,
        pointerEvents: "none",
      }}
    />
  );
}

function BandCaption({ y, text }: { y: number; text: string }) {
  return (
    <div
      style={{
        position: "absolute",
        top: y,
        left: 0,
        right: 0,
        textAlign: "center",
        fontFamily: "var(--font-mono)",
        fontSize: 9,
        color: "var(--color-ink-3)",
        letterSpacing: "0.18em",
        pointerEvents: "none",
      }}
    >
      {text}
    </div>
  );
}

// Hidden handles re-used across nodes — top/bottom variants for return-edge
// routing through the south detour band (or symmetric north).
const sideHandle = (offset: number) => ({ ...hiddenHandle, top: offset });

// ── work_step ─────────────────────────────────────────────────────
export function WorkStepNode({ data, selected }: NodeProps) {
  const d = data as unknown as WorkStepNodeData;
  const w = d.workStep;
  const c = actorColor(w.actor);
  return (
    <div
      data-testid={`workflow-workstep-${d.statusId}-${w.id}`}
      style={{
        width: WORK_W,
        height: WORK_H,
        background: "var(--color-paper-2)",
        border: `1.8px solid ${c}`,
        borderRadius: 4,
        position: "relative",
        cursor: "pointer",
        boxShadow: selected ? `0 0 0 2px ${c}33` : undefined,
      }}
    >
      <NodeToolbar isVisible={selected} position={Position.Top} offset={8}>
        <ToolbarShell>
          <ToolbarLabel>WORK · {w.id}</ToolbarLabel>
          {w.skills.length > 0 && (
            <ToolbarLabel muted>
              ▸ {w.skills.length} skill{w.skills.length === 1 ? "" : "s"}
            </ToolbarLabel>
          )}
          <ToolbarButton action="zoom-to-node">Zoom</ToolbarButton>
        </ToolbarShell>
      </NodeToolbar>
      <div
        style={{
          position: "absolute",
          top: 0,
          bottom: 0,
          left: 0,
          width: 6,
          background: c,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 10,
          left: 16,
          fontFamily: "var(--font-mono)",
          fontSize: 9.5,
          color: "var(--color-ink-3)",
          letterSpacing: "0.14em",
        }}
      >
        WORK · {actorLabel(w.actor)}
      </div>
      <div
        style={{
          position: "absolute",
          top: 28,
          left: 16,
          right: 14,
          fontFamily: "var(--font-sans)",
          fontWeight: 600,
          fontSize: 18,
          color: "var(--color-ink)",
          lineHeight: 1.1,
        }}
      >
        {w.label}
      </div>
      <Handle id="left" type="target" position={Position.Left} style={sideHandle(WORK_H / 2)} />
      <Handle id="right" type="source" position={Position.Right} style={sideHandle(WORK_H / 2)} />
      {/* bottom + top handles for detour (return) routing */}
      <Handle id="bottom" type="target" position={Position.Bottom} style={hiddenHandle} />
      <Handle id="top" type="source" position={Position.Top} style={hiddenHandle} />
    </div>
  );
}

// ── chips (skill / ref) ───────────────────────────────────────────
export function ChipNode({ data }: NodeProps) {
  const d = data as unknown as ChipNodeData;
  const isSkill = d.kind === "skill";
  const stroke = isSkill ? "var(--color-info)" : "var(--color-ink-3)";
  const fg = isSkill ? "var(--color-info)" : "var(--color-ink-2)";
  return (
    <div
      data-testid={`workflow-chip-${d.statusId}-${d.kind}-${d.label}`}
      style={{
        width: "100%",
        height: "100%",
        background: "var(--color-paper)",
        border: `1px solid ${stroke}`,
        borderRadius: 3,
        fontFamily: "var(--font-mono)",
        fontSize: 11,
        color: fg,
        letterSpacing: "0.02em",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "0 8px",
        whiteSpace: "nowrap",
        boxSizing: "border-box",
      }}
    >
      {isSkill ? "▸ " : "↑ "}
      {d.label}
    </div>
  );
}

// ── output tile ───────────────────────────────────────────────────
export function TileNode({ data }: NodeProps) {
  const d = data as unknown as TileNodeData;
  const a = d.artifact;
  return (
    <div
      data-testid={`workflow-tile-${d.statusId}-${a.id}`}
      title={a.label}
      style={{
        width: TILE_W,
        height: TILE_H,
        position: "relative",
        cursor: "pointer",
      }}
    >
      <svg width={TILE_W} height={TILE_H} viewBox={`0 0 ${TILE_W} ${TILE_H}`}>
        <path
          d={`M 0 0 H ${TILE_W - TILE_FOLD} L ${TILE_W} ${TILE_FOLD - 4} V ${TILE_H} H 0 Z`}
          fill="var(--color-paper-2)"
          stroke="var(--color-ink-3)"
          strokeDasharray="3 2"
          strokeWidth={0.9}
        />
        <path
          d={`M ${TILE_W - TILE_FOLD} 0 V ${TILE_FOLD - 4} H ${TILE_W}`}
          fill="none"
          stroke="var(--color-ink-3)"
          strokeWidth={0.9}
          strokeDasharray="3 2"
        />
      </svg>
      <div
        style={{
          position: "absolute",
          top: 0,
          bottom: 0,
          left: TILE_PAD_L,
          right: TILE_FOLD + TILE_PAD_RIGHT,
          display: "flex",
          alignItems: "center",
          gap: TILE_ICON_GAP,
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          color: "var(--color-ink-2)",
          pointerEvents: "none",
        }}
      >
        <span style={{ flexShrink: 0 }}>◫</span>
        <span
          style={{
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            minWidth: 0,
          }}
        >
          {a.label}
        </span>
      </div>
    </div>
  );
}

// ── boundary transition (sits ON the wall) ────────────────────────
export function BoundaryTransitionNode({ data, selected }: NodeProps) {
  const d = data as unknown as BoundaryNodeData;
  return <TransitionBox d={d} flavor="boundary" selected={selected} />;
}

// ── detour transition (return / side / loop) ──────────────────────
export function DetourTransitionNode({ data, selected }: NodeProps) {
  const d = data as unknown as DetourNodeData;
  return <TransitionBox d={d} flavor="detour" selected={selected} />;
}

interface TransitionBoxProps {
  d: { route: BoundaryNodeData["route"]; gateCount: number };
  flavor: "boundary" | "detour";
  selected?: boolean;
}

function TransitionBox({ d, flavor, selected }: TransitionBoxProps) {
  const r = d.route;
  const c = actorColor(r.actor);
  return (
    <div
      data-testid={`workflow-transition-${r.id}`}
      data-placement={flavor}
      style={{
        width: TX_W,
        height: TX_H,
        position: "relative",
        cursor: "pointer",
        boxShadow: selected ? `0 0 0 2px ${c}33` : undefined,
      }}
    >
      <NodeToolbar isVisible={Boolean(selected)} position={Position.Top} offset={10}>
        <ToolbarShell>
          <ToolbarLabel>
            {flavor === "boundary" ? "BOUNDARY · " : "DETOUR · "}
            {r.kind}
          </ToolbarLabel>
          {r.command && <ToolbarLabel muted>▷ {r.command}</ToolbarLabel>}
          {d.gateCount > 0 && (
            <ToolbarLabel muted>×{d.gateCount} gate</ToolbarLabel>
          )}
          <ToolbarButton action="zoom-to-node">Zoom</ToolbarButton>
        </ToolbarShell>
      </NodeToolbar>
      {flavor === "boundary" && (
        <>
          {/* door-frame fragments above/below to convey wall-piercing */}
          <div
            style={{
              position: "absolute",
              left: -8,
              right: -8,
              top: -10,
              height: 4,
              background: c,
              opacity: 0.85,
            }}
          />
          <div
            style={{
              position: "absolute",
              left: -8,
              right: -8,
              bottom: -10,
              height: 4,
              background: c,
              opacity: 0.85,
            }}
          />
        </>
      )}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "var(--color-paper-2)",
          border: `${flavor === "boundary" ? 2 : 1.4}px solid ${c}`,
          borderRadius: 4,
          boxSizing: "border-box",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 0,
          bottom: 0,
          left: 0,
          width: 4,
          background: c,
        }}
      />
      {/* Eyebrow (command name) — aligned to work_step's eyebrow at
          top:10 so the two node types' visual rhythms match. */}
      {r.command && (
        <div
          style={{
            position: "absolute",
            top: 10,
            left: 12,
            fontFamily: "var(--font-mono)",
            fontSize: 9.5,
            color: "var(--color-ink-3)",
            letterSpacing: "0.14em",
          }}
        >
          ▷ {r.command}
        </div>
      )}
      {/* Main label — aligned to work_step's label at top:28 so the
          eye reads the two side-by-side without a vertical jog. */}
      <div
        style={{
          position: "absolute",
          top: 28,
          left: 12,
          right: 12,
          fontFamily: "var(--font-sans)",
          fontWeight: 600,
          fontSize: 14,
          color: "var(--color-ink)",
          letterSpacing: "-0.005em",
          lineHeight: 1.1,
        }}
      >
        {r.label}
      </div>
      <div
        style={{
          position: "absolute",
          right: 8,
          bottom: 6,
          fontFamily: "var(--font-mono)",
          fontSize: 9.5,
          fontWeight: 600,
          color: c,
          letterSpacing: "0.06em",
        }}
      >
        {actorLabel(r.actor)}
      </div>
      {d.gateCount > 0 && <GateBadge routeId={r.id} count={d.gateCount} />}
      <Handle id="left" type="target" position={Position.Left} style={{ ...hiddenHandle, top: TX_H / 2 }} />
      <Handle id="right" type="source" position={Position.Right} style={{ ...hiddenHandle, top: TX_H / 2 }} />
    </div>
  );
}

function GateBadge({ routeId, count }: { routeId: string; count: number }) {
  return (
    <div
      data-testid={`workflow-gate-badge-${routeId}`}
      style={{
        position: "absolute",
        top: 6,
        right: 8,
        height: 16,
        padding: "0 6px",
        background: "var(--color-paper-2)",
        border: "1px solid var(--color-gate)",
        borderRadius: 2,
        display: "flex",
        alignItems: "center",
        gap: 4,
        fontFamily: "var(--font-mono)",
        fontSize: 10,
        fontWeight: 600,
        color: "var(--color-gate)",
        letterSpacing: "0.04em",
        cursor: "pointer",
      }}
      role="button"
      aria-label={`Gate on route ${routeId}: ${count} checks`}
    >
      <svg width={10} height={10} viewBox="0 0 10 10">
        <rect x={1} y={4} width={8} height={5} stroke="var(--color-gate)" strokeWidth={1} fill="none" />
        <path d="M 2.5 4 V 2.5 a 2 2 0 0 1 5 0 V 4" stroke="var(--color-gate)" strokeWidth={1} fill="none" />
      </svg>
      ×{count}
    </div>
  );
}

// ── branch diamond ────────────────────────────────────────────────
export function BranchDiamondNode({ data }: NodeProps) {
  const d = data as unknown as BranchNodeData;
  const c = actorColor(d.actor);
  return (
    <div
      data-testid={`workflow-branch-${d.command}`}
      style={{ width: 180, height: 86, position: "relative" }}
    >
      <svg width={180} height={86} viewBox="0 0 180 86">
        <polygon
          points="90,2 178,43 90,84 2,43"
          fill="var(--color-paper-2)"
          stroke={c}
          strokeWidth={1.8}
        />
        <text
          x={90}
          y={38}
          textAnchor="middle"
          fontFamily="var(--font-mono)"
          fontSize={10.5}
          fill="var(--color-ink-3)"
        >
          ▷ {d.command}
        </text>
        <text
          x={90}
          y={58}
          textAnchor="middle"
          fontFamily="var(--font-sans)"
          fontWeight={600}
          fontSize={13}
          fill="var(--color-ink)"
        >
          decision
        </text>
      </svg>
      <Handle id="left" type="target" position={Position.Left} style={sideHandle(43)} />
      <Handle id="right" type="source" position={Position.Right} style={sideHandle(43)} />
      {/* bottom handle for return outcomes (south-routed) */}
      <Handle id="bottom" type="source" position={Position.Bottom} style={hiddenHandle} />
      <Handle id="top" type="source" position={Position.Top} style={hiddenHandle} />
    </div>
  );
}

// ── jit prompt flare ──────────────────────────────────────────────
export function JitPromptNode({ data }: NodeProps) {
  const d = data as unknown as JitNodeData;
  return (
    <div
      data-testid={`workflow-jit-${d.statusId}-${d.id}`}
      title={d.id}
      style={{
        width: 28,
        height: 28,
        position: "relative",
        cursor: "pointer",
      }}
    >
      <div
        style={{
          width: 28,
          height: 28,
          borderRadius: 6,
          background: "var(--color-paper)",
          border: "1.5px solid var(--color-tripwire)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "var(--font-mono)",
          fontSize: 14,
          fontWeight: 700,
          color: "var(--color-tripwire)",
        }}
      >
        !
      </div>
    </div>
  );
}

// ── port (source / sink) ──────────────────────────────────────────
export function PortNode({ data }: NodeProps) {
  const d = data as unknown as PortNodeData;
  const isSink = d.kind === "sink";
  return (
    <div
      data-testid={`workflow-port-${d.kind}-${d.label}`}
      style={{
        width: 36,
        height: 36,
        position: "relative",
      }}
    >
      {/* dot vertically centred in the bounding box so the handle (top:18)
          sits exactly on the box centre — keeps every main-flow node on the
          same Y, no edge jogs. */}
      <div
        style={{
          position: "absolute",
          top: 9,
          left: 9,
          width: 18,
          height: 18,
          borderRadius: "50%",
          background: isSink ? "var(--color-ink)" : "var(--color-paper)",
          border: "1.6px solid var(--color-ink)",
        }}
      >
        {!isSink && (
          <div
            style={{
              position: "absolute",
              top: 6,
              left: 6,
              width: 4,
              height: 4,
              borderRadius: "50%",
              background: "var(--color-ink)",
            }}
          />
        )}
      </div>
      {/* label sits BELOW the bounding box, doesn't shift the dot off-centre. */}
      <div
        style={{
          position: "absolute",
          top: 38,
          left: -50,
          width: 136,
          textAlign: "center",
          fontFamily: "var(--font-mono)",
          fontSize: 9,
          color: "var(--color-ink-2)",
          letterSpacing: "0.04em",
          whiteSpace: "nowrap",
        }}
      >
        {d.label}
      </div>
      <Handle id="left" type="target" position={Position.Left} style={{ ...hiddenHandle, top: 18 }} />
      <Handle id="right" type="source" position={Position.Right} style={{ ...hiddenHandle, top: 18 }} />
    </div>
  );
}

// ── toolbar primitives ────────────────────────────────────────────
function ToolbarShell({ children }: { children: React.ReactNode }) {
  return (
    <div
      data-testid="workflow-node-toolbar"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "4px 8px",
        background: "var(--color-paper)",
        border: "1px solid var(--color-edge)",
        borderRadius: 4,
        boxShadow: "0 4px 14px rgba(26,24,21,0.08)",
      }}
    >
      {children}
    </div>
  );
}

function ToolbarLabel({
  children,
  muted,
}: {
  children: React.ReactNode;
  muted?: boolean;
}) {
  return (
    <span
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: 9.5,
        letterSpacing: "0.06em",
        color: muted ? "var(--color-ink-3)" : "var(--color-ink-2)",
        textTransform: "uppercase",
      }}
    >
      {children}
    </span>
  );
}

function ToolbarButton({
  action,
  children,
}: {
  action: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      data-toolbar-action={action}
      style={{
        cursor: "pointer",
        padding: "2px 8px",
        border: "1px solid var(--color-ink)",
        background: "var(--color-paper)",
        fontFamily: "var(--font-mono)",
        fontSize: 9.5,
        color: "var(--color-ink)",
        letterSpacing: "0.06em",
        textTransform: "uppercase",
      }}
    >
      {children}
    </button>
  );
}

// ── cross-link endpoint dot ───────────────────────────────────────
// Small clickable circle on a status region's south (source) or north
// (target) edge. Clicking jumps the viewport to the OTHER endpoint's
// band — a one-click teleport across workflows.
export interface CrossLinkEndpointData {
  role: "source" | "target";
  otherWorkflowId: string;
  otherStatusId: string;
  label: string | null;
}
const CROSSLINK_HEX = "#0e7c8a";
export function CrossLinkEndpointNode({ data }: NodeProps) {
  const d = data as unknown as CrossLinkEndpointData;
  const [hovered, setHovered] = useState(false);
  const arrow = d.role === "source" ? "→" : "←";
  return (
    <div
      data-testid={`workflow-crosslink-endpoint-${d.role}-${d.otherWorkflowId}-${d.otherStatusId}`}
      data-crosslink-target-workflow={d.otherWorkflowId}
      data-crosslink-target-status={d.otherStatusId}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        width: 18,
        height: 18,
        borderRadius: "50%",
        background: CROSSLINK_HEX,
        border: "2px solid var(--color-paper)",
        boxShadow: "0 0 0 1px " + CROSSLINK_HEX,
        cursor: "pointer",
        // Force pointer-events on this exact element so hover always
        // fires on the visible circle, regardless of any ancestor
        // pointer-events: none cascade.
        pointerEvents: "auto",
        position: "relative",
      }}
    >
      {/* Hover popover — uses ReactFlow's NodeToolbar so it positions
          correctly relative to the node and survives the canvas
          transform. */}
      <NodeToolbar
        isVisible={hovered}
        position={d.role === "source" ? Position.Right : Position.Left}
        offset={6}
      >
        <div
          style={{
            background: "var(--color-paper)",
            border: `1px solid ${CROSSLINK_HEX}`,
            color: CROSSLINK_HEX,
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            padding: "4px 8px",
            letterSpacing: "0.04em",
            whiteSpace: "nowrap",
            boxShadow: "0 4px 12px rgba(26,24,21,0.10)",
            borderRadius: 2,
          }}
        >
          {d.label ? `${d.label} ` : ""}
          {arrow} {d.otherWorkflowId}.{d.otherStatusId}
          <span
            style={{
              color: "var(--color-ink-3)",
              marginLeft: 6,
              fontSize: 9,
            }}
          >
            click to jump
          </span>
        </div>
      </NodeToolbar>
      {/* Source dot sits on work_step.SOUTH (outgoing — line exits
          downward into the south cross-link lane). Target dot sits on
          work_step.NORTH (incoming — line drops in from the north
          cross-link lane above). Default left:50% + translate(-50%,-50%)
          centres each handle on the dot's geometric midpoint. */}
      <Handle
        id={d.role === "source" ? "south" : "north"}
        type={d.role === "source" ? "source" : "target"}
        position={d.role === "source" ? Position.Bottom : Position.Top}
        style={hiddenHandle}
      />
    </div>
  );
}

// ── band parent group (one per workflow in the unified canvas) ────
// Renders the band header ribbon (workflow id + brief description)
// floating above the band's top edge. The group itself is invisible —
// it just provides a parent container that fitView can target.
export interface BandNodeData {
  workflowId: string;
  brief: string;
  width: number;
  height: number;
}
export function BandHeaderNode({ data }: NodeProps) {
  const d = data as unknown as BandNodeData;
  return (
    <div
      data-testid={`workflow-band-${d.workflowId}`}
      data-workflow={d.workflowId}
      style={{
        width: d.width,
        height: d.height,
        position: "relative",
        pointerEvents: "none",
      }}
    >
      {/* Header ribbon — anchored above the band so it doesn't collide
          with the per-status header row inside. */}
      <div
        style={{
          position: "absolute",
          top: -64,
          left: 24,
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          letterSpacing: "0.18em",
          color: "var(--color-ink-2)",
          textTransform: "uppercase",
        }}
      >
        workflow · {d.workflowId}
      </div>
      {d.brief && (
        <div
          style={{
            position: "absolute",
            top: -42,
            left: 24,
            fontFamily: "var(--font-serif)",
            fontStyle: "italic",
            fontSize: 14,
            color: "var(--color-ink-3)",
            maxWidth: Math.min(d.width - 48, 720),
          }}
        >
          {d.brief}
        </div>
      )}
    </div>
  );
}

// ── dotted vertical divider between adjacent status regions ──────
// Sits exactly on the seam between two touching regions. Z-index is set
// in the graph builder so it renders below gates/boundary nodes but above
// the region background.
export interface DividerNodeData {
  height: number;
}
export function StatusDividerNode({ data }: NodeProps) {
  const d = data as unknown as DividerNodeData;
  return (
    <div
      data-testid="workflow-status-divider"
      aria-hidden
      style={{
        width: 1,
        height: d.height,
        borderRight: "1px dashed var(--color-edge)",
        pointerEvents: "none",
      }}
    />
  );
}

// ── invisible anchor inside a region (for branch outcome edges) ───
// 2x2 with handles explicitly at the centre so its handle Y == Y_WORK
// (avoids the half-pixel offset that 1x1 produces).
export function AnchorNode() {
  return (
    <div style={{ width: 2, height: 2, opacity: 0 }}>
      <Handle id="left" type="target" position={Position.Left} style={{ ...hiddenHandle, top: 1 }} />
      <Handle id="right" type="source" position={Position.Right} style={{ ...hiddenHandle, top: 1 }} />
    </div>
  );
}
