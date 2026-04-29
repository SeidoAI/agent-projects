import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { Stamp } from "@/components/ui/stamp";
import { ApiError } from "@/lib/api/client";
import { useWorkflow } from "@/lib/api/endpoints/workflow";
import { isPmMode } from "@/lib/role";
import { ArtifactCard } from "./ArtifactCard";
import { ConnectorCurve } from "./ConnectorCurve";
import { StationCard } from "./StationCard";
import { TripwireCard } from "./TripwireCard";
import {
  computeWorkflowLayout,
  type PositionedConnector,
  type PositionedStation,
  WORKFLOW_CANVAS,
} from "./useWorkflowLayout";
import { ValidatorCard } from "./ValidatorCard";
import { WorkflowDrawer, type WorkflowSelection } from "./WorkflowDrawer";

/**
 * Workflow Map — process-definition surface at `/p/:projectId/workflow`.
 *
 * Read-only visualisation of how Tripwire orchestrates a session.
 * Sources flow in LEFT, sinks flow out RIGHT, the lifecycle wire
 * runs through the centre, validators and tripwires sit above
 * their gating station, artifacts below their producer.
 *
 * Per [[dec-critical-path-elon-method]] this is process spec, not
 * live state — there is no per-session highlighting and no
 * "active now" overlay; the dashboard is the live-state surface.
 */
export function WorkflowMap() {
  const { projectId } = useProjectShell();
  const [searchParams] = useSearchParams();
  // Detect PM-mode BEFORE the fetch so the hook can pin
  // X-Tripwire-Role on the request and the React Query cache key
  // — the backend nulls `tripwires[*].prompt_revealed` for non-PM
  // viewers, so without this the drawer never has the prompt body
  // even when ?role=pm is set.
  const pmMode = useMemo(() => isPmMode(searchParams.get("role")), [searchParams]);
  const query = useWorkflow(projectId, { pmMode });
  const { data: graph, isPending, isError, error, refetch } = query;

  const layout = useMemo(() => (graph ? computeWorkflowLayout(graph) : null), [graph]);
  const [hovered, setHovered] = useState<HoverKey | null>(null);
  const [selection, setSelection] = useState<WorkflowSelection | null>(null);

  // Distinct surfaces per query state (Codex P2):
  //  - pending  → skeleton placeholder so flaky-network users don't
  //               briefly read "no graph"
  //  - error (non-404) → error chrome with retry
  //  - empty (404 or genuine empty graph) → existing copy
  //  - success → real canvas
  // 404 still falls through to "empty" — Strand Y is additive,
  // pre-shipping clients see 404 until the endpoint lands.
  const stateBranch: React.ReactNode = (() => {
    if (layout) {
      return (
        <Canvas layout={layout} hovered={hovered} onHover={setHovered} onSelect={setSelection} />
      );
    }
    if (isPending) return <LoadingState />;
    if (isError && !is404(error)) return <ErrorState onRetry={() => void refetch()} />;
    return <EmptyState />;
  })();

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="font-sans font-semibold text-[28px] text-(--color-ink) tracking-[-0.02em] leading-tight">
          Workflow
        </h1>
        <p className="font-serif text-[14px] italic text-(--color-ink-2) leading-snug">
          how Tripwire orchestrates a session — read this once, the dashboard reads it every day.
        </p>
      </header>
      <Legend />
      {stateBranch}
      <WorkflowDrawer selection={selection} pmMode={pmMode} onClose={() => setSelection(null)} />
    </div>
  );
}

function is404(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404;
}

type HoverKey =
  | { kind: "validator"; id: string }
  | { kind: "tripwire"; id: string }
  | { kind: "artifact"; id: string }
  | { kind: "source"; id: string }
  | { kind: "sink"; id: string };

interface CanvasProps {
  layout: NonNullable<ReturnType<typeof computeWorkflowLayout>>;
  hovered: HoverKey | null;
  onHover: (k: HoverKey | null) => void;
  onSelect: (s: WorkflowSelection) => void;
}

function Canvas({ layout, hovered, onHover, onSelect }: CanvasProps) {
  const { stations, validators, tripwires, artifacts, sources, sinks, viewBox } = layout;
  const stationsById = new Map(stations.map((s) => [s.id, s] as const));
  const hl = useMemo(() => computeHighlight(hovered), [hovered]);

  return (
    <section
      // Vertical scroll: per round-3 PM follow-up the canvas is
      // not space-constrained — at high entity density the dynamic
      // viewBox grows beyond the visible viewport and the user
      // scrolls. `flex-1 min-h-0` lets the section take whatever
      // height is left after the page header + legend strip.
      className="relative flex-1 w-full min-h-0 overflow-auto rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2)"
      aria-label="Workflow map canvas"
    >
      <svg
        viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
        width={viewBox.width}
        height={viewBox.height}
        preserveAspectRatio="xMinYMin meet"
        style={{ display: "block" }}
      >
        <title>Workflow orchestration graph</title>
        <line
          x1={WORKFLOW_CANVAS.gutterLeft}
          x2={WORKFLOW_CANVAS.width - WORKFLOW_CANVAS.gutterRight}
          y1={WORKFLOW_CANVAS.wireY}
          y2={WORKFLOW_CANVAS.wireY}
          stroke="var(--color-rule)"
          strokeWidth={1.6}
          strokeLinecap="round"
        />
        {sources.map((c) => (
          <ConnectorCurve
            key={`source-${c.id}`}
            id={`source-${c.id}`}
            from={{ x: c.x, y: c.y }}
            to={attachmentPoint(c, stationsById)}
            dimmed={hl.connectorDimmed(`source-${c.id}`)}
          />
        ))}
        {sinks.map((c) => (
          <ConnectorCurve
            key={`sink-${c.id}`}
            id={`sink-${c.id}`}
            from={attachmentPoint(c, stationsById)}
            to={{ x: c.x, y: c.y }}
            dimmed={hl.connectorDimmed(`sink-${c.id}`)}
          />
        ))}
        {artifacts.map((a) => {
          const producer = stationsById.get(a.produced_by);
          const consumer = a.consumed_by ? stationsById.get(a.consumed_by) : null;
          return (
            <g key={`artifact-wires-${a.id}`}>
              {producer ? (
                <ConnectorCurve
                  id={`artifact-out-${a.id}`}
                  from={{ x: producer.x, y: producer.y + 10 }}
                  to={{ x: a.x, y: a.y - 30 }}
                  dimmed={hl.connectorDimmed(`artifact-out-${a.id}`)}
                  stroke="var(--color-info)"
                />
              ) : null}
              {consumer ? (
                <ConnectorCurve
                  id={`artifact-in-${a.id}`}
                  from={{ x: a.x, y: a.y - 30 }}
                  to={{ x: consumer.x, y: consumer.y + 10 }}
                  dimmed={hl.connectorDimmed(`artifact-in-${a.id}`)}
                  stroke="var(--color-info)"
                />
              ) : null}
            </g>
          );
        })}
        {stations.map((s) => (
          <StationCard key={`station-${s.id}`} station={s} x={s.x} y={s.y} />
        ))}
        {validators.map((v) => (
          <ValidatorCard
            key={`validator-${v.id}`}
            validator={v}
            x={v.x}
            y={v.y}
            dimmed={hl.entityDimmed(`validator-${v.id}`)}
            onClick={() => onSelect({ kind: "validator", entity: v })}
            onMouseEnter={() => onHover({ kind: "validator", id: v.id })}
            onMouseLeave={() => onHover(null)}
          />
        ))}
        {tripwires.map((t) => (
          <TripwireCard
            key={`tripwire-${t.id}`}
            tripwire={t}
            x={t.x}
            y={t.y}
            dimmed={hl.entityDimmed(`tripwire-${t.id}`)}
            onClick={() => onSelect({ kind: "tripwire", entity: t })}
            onMouseEnter={() => onHover({ kind: "tripwire", id: t.id })}
            onMouseLeave={() => onHover(null)}
          />
        ))}
        {artifacts.map((a) => (
          <ArtifactCard
            key={`artifact-${a.id}`}
            artifact={a}
            x={a.x}
            y={a.y}
            dimmed={hl.entityDimmed(`artifact-${a.id}`)}
            onClick={() => onSelect({ kind: "artifact", entity: a })}
            onMouseEnter={() => onHover({ kind: "artifact", id: a.id })}
            onMouseLeave={() => onHover(null)}
          />
        ))}
        {sources.map((c) => (
          <ConnectorEndpoint
            key={`source-end-${c.id}`}
            connector={c}
            side="left"
            dimmed={hl.entityDimmed(`source-${c.id}`)}
            onMouseEnter={() => onHover({ kind: "source", id: c.id })}
            onMouseLeave={() => onHover(null)}
          />
        ))}
        {sinks.map((c) => (
          <ConnectorEndpoint
            key={`sink-end-${c.id}`}
            connector={c}
            side="right"
            dimmed={hl.entityDimmed(`sink-${c.id}`)}
            onMouseEnter={() => onHover({ kind: "sink", id: c.id })}
            onMouseLeave={() => onHover(null)}
          />
        ))}
      </svg>
    </section>
  );
}

const ENDPOINT_W = 132;
const ENDPOINT_H = 32;

function ConnectorEndpoint({
  connector,
  side,
  dimmed,
  onMouseEnter,
  onMouseLeave,
}: {
  connector: PositionedConnector;
  side: "left" | "right";
  dimmed: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}) {
  return (
    <foreignObject
      x={side === "left" ? connector.x - ENDPOINT_W : connector.x}
      y={connector.y - ENDPOINT_H / 2}
      width={ENDPOINT_W}
      height={ENDPOINT_H}
      opacity={dimmed ? 0.25 : 1}
      style={{ transition: "opacity 120ms ease-out", overflow: "visible" }}
    >
      <div
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        // biome-ignore lint/a11y/noStaticElementInteractions: hover-only
        // visualisation; connector endpoints are NOT focusable (the
        // cards above the wire are the real click/focus targets).
        // We don't attach onFocus/onBlur because there's no
        // tabIndex and adding one would imply interactivity that
        // doesn't exist.
        role="img"
        aria-label={`${side === "left" ? "Source" : "Sink"} ${connector.name}`}
        className="flex h-full w-full items-center justify-center gap-1.5 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-2"
      >
        <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-3)">
          {side === "left" ? "src" : "sink"}
        </span>
        <span className="font-sans font-semibold text-[12px] text-(--color-ink) leading-tight">
          {connector.name}
        </span>
      </div>
    </foreignObject>
  );
}

function attachmentPoint(
  c: PositionedConnector,
  stationsById: Map<string, PositionedStation>,
): { x: number; y: number } {
  const s = c.attachStation ? stationsById.get(c.attachStation) : undefined;
  if (s) return { x: s.x, y: s.y };
  return { x: WORKFLOW_CANVAS.width / 2, y: WORKFLOW_CANVAS.wireY };
}

interface Highlight {
  /** Returns true when the connector should drop to dim opacity. */
  connectorDimmed: (id: string) => boolean;
  /** Returns true when the entity card should drop to dim opacity. */
  entityDimmed: (id: string) => boolean;
}

function computeHighlight(hovered: HoverKey | null): Highlight {
  if (!hovered) {
    return {
      connectorDimmed: () => false,
      entityDimmed: () => false,
    };
  }
  const liveEntity = `${hovered.kind}-${hovered.id}`;
  const liveConnectors = new Set<string>();
  if (hovered.kind === "artifact") {
    liveConnectors.add(`artifact-out-${hovered.id}`);
    liveConnectors.add(`artifact-in-${hovered.id}`);
  } else if (hovered.kind === "source") {
    liveConnectors.add(`source-${hovered.id}`);
  } else if (hovered.kind === "sink") {
    liveConnectors.add(`sink-${hovered.id}`);
  }
  return {
    connectorDimmed: (id) => !liveConnectors.has(id),
    entityDimmed: (id) => id !== liveEntity,
  };
}

/**
 * Legend strip — one `<Stamp>` pill chip per category, the chip
 * IS the label (no parallel "legend version" of the chip per
 * round-3 PM follow-up). The data-stamp-tone attribute on each
 * chip is what tests assert against to check we're using the
 * shared `Stamp` primitive.
 */
const LEGEND_CHIPS: {
  label: string;
  tone: React.ComponentProps<typeof Stamp>["tone"];
  copy: string;
}[] = [
  { label: "SOURCE", tone: "default", copy: "external input wired in" },
  { label: "STATION", tone: "rule", copy: "lifecycle stage on the wire" },
  { label: "SINK", tone: "default", copy: "external output wired out" },
  { label: "GATE", tone: "gate", copy: "validator blocks until rule passes" },
  { label: "TRIPWIRE", tone: "tripwire", copy: "fires on event — agent must ack" },
  { label: "ARTIFACT", tone: "info", copy: "typed document the workflow produces" },
];

function Legend() {
  return (
    <section
      aria-label="Legend"
      className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-4 py-3"
    >
      {LEGEND_CHIPS.map((c) => (
        <div key={c.label} className="flex items-center gap-2">
          <Stamp tone={c.tone}>{c.label}</Stamp>
          <span className="font-serif text-[12px] italic text-(--color-ink-3) leading-snug">
            {c.copy}
          </span>
        </div>
      ))}
    </section>
  );
}

function StateFrame({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="flex flex-1 items-center justify-center rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) py-24"
      role="status"
    >
      {children}
    </div>
  );
}

function LoadingState() {
  return (
    <StateFrame>
      <p data-loading="workflow" className="font-serif text-[14px] italic text-(--color-ink-3)">
        Loading workflow…
      </p>
    </StateFrame>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <StateFrame>
      <div className="flex flex-col items-center gap-3">
        <p className="font-serif text-[14px] italic text-(--color-rule)">
          Couldn't load the workflow graph.
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="rounded-(--radius-stamp) border border-(--color-ink) bg-(--color-paper) px-3 py-1 font-mono text-[11px] uppercase tracking-[0.06em] text-(--color-ink) hover:bg-(--color-paper-3)"
        >
          Retry
        </button>
      </div>
    </StateFrame>
  );
}

function EmptyState() {
  return (
    <StateFrame>
      <p className="font-serif text-[14px] italic text-(--color-ink-3)">
        Workflow not yet available — backend has not registered the orchestration graph.
      </p>
    </StateFrame>
  );
}
