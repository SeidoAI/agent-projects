import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { Stamp } from "@/components/ui/stamp";
import { sessionStageColor } from "@/components/ui/session-stage-row";
import { useWorkflow } from "@/lib/api/endpoints/workflow";
import { ArtifactCard } from "./ArtifactCard";
import { ConnectorCurve } from "./ConnectorCurve";
import { StationCard } from "./StationCard";
import { TripwireCard } from "./TripwireCard";
import {
  WORKFLOW_CANVAS,
  computeWorkflowLayout,
  type PositionedConnector,
  type PositionedStation,
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
  const { data: graph } = useWorkflow(projectId);
  const [searchParams] = useSearchParams();
  const pmMode = useMemo(() => isPmMode(searchParams.get("role")), [searchParams]);

  const layout = useMemo(() => (graph ? computeWorkflowLayout(graph) : null), [graph]);
  const [hovered, setHovered] = useState<HoverKey | null>(null);
  const [selection, setSelection] = useState<WorkflowSelection | null>(null);

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="font-sans font-semibold text-[28px] text-(--color-ink) tracking-[-0.02em] leading-tight">
          Workflow
        </h1>
        <p className="font-serif text-[14px] italic text-(--color-ink-2) leading-snug">
          how Tripwire orchestrates a session — read this once, the dashboard reads it
          every day.
        </p>
      </header>
      <Legend />
      {layout ? (
        <Canvas
          layout={layout}
          hovered={hovered}
          onHover={setHovered}
          onSelect={setSelection}
        />
      ) : (
        <EmptyState />
      )}
      <WorkflowDrawer
        selection={selection}
        pmMode={pmMode}
        onClose={() => setSelection(null)}
      />
    </div>
  );
}

type HoverKey =
  | { kind: "station"; id: string }
  | { kind: "validator"; id: string; station: string }
  | { kind: "tripwire"; id: string; station: string }
  | { kind: "artifact"; id: string; producer: string; consumer: string | null }
  | { kind: "source"; id: string; station: string | undefined }
  | { kind: "sink"; id: string; station: string | undefined };

interface CanvasProps {
  layout: NonNullable<ReturnType<typeof computeWorkflowLayout>>;
  hovered: HoverKey | null;
  onHover: (k: HoverKey | null) => void;
  onSelect: (s: WorkflowSelection) => void;
}

function Canvas({ layout, hovered, onHover, onSelect }: CanvasProps) {
  const { stations, validators, tripwires, artifacts, sources, sinks } = layout;
  const stationXById = new Map(stations.map((s) => [s.id, s] as const));

  // Hover-highlight: collect the set of (entity id, connector id)
  // that should stay opaque while the user hovers an item. Anything
  // outside that set drops to ~25% opacity.
  const hl = useMemo(() => computeHighlight(hovered), [hovered]);

  return (
    <div
      className="relative w-full overflow-auto rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2)"
      role="region"
      aria-label="Workflow map canvas"
    >
      <svg
        viewBox={`0 0 ${WORKFLOW_CANVAS.width} ${WORKFLOW_CANVAS.height}`}
        width="100%"
        preserveAspectRatio="xMidYMid meet"
        style={{ minHeight: 600 }}
      >
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
            to={attachmentPoint(c, stationXById)}
            dimmed={!hl.connectors.has(`source-${c.id}`)}
          />
        ))}
        {sinks.map((c) => (
          <ConnectorCurve
            key={`sink-${c.id}`}
            id={`sink-${c.id}`}
            from={attachmentPoint(c, stationXById)}
            to={{ x: c.x, y: c.y }}
            dimmed={!hl.connectors.has(`sink-${c.id}`)}
          />
        ))}
        {artifacts.map((a) => {
          const producer = stationXById.get(a.produced_by);
          const consumer = a.consumed_by ? stationXById.get(a.consumed_by) : null;
          return (
            <g key={`artifact-wires-${a.id}`}>
              {producer ? (
                <ConnectorCurve
                  id={`artifact-out-${a.id}`}
                  from={{ x: producer.x, y: producer.y + 14 }}
                  to={{ x: a.x, y: a.y - 30 }}
                  dimmed={!hl.connectors.has(`artifact-out-${a.id}`)}
                  stroke="var(--color-info)"
                />
              ) : null}
              {consumer ? (
                <ConnectorCurve
                  id={`artifact-in-${a.id}`}
                  from={{ x: a.x, y: a.y - 30 }}
                  to={{ x: consumer.x, y: consumer.y + 14 }}
                  dimmed={!hl.connectors.has(`artifact-in-${a.id}`)}
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
          <g
            key={`validator-${v.id}`}
            onMouseEnter={() =>
              onHover({ kind: "validator", id: v.id, station: v.fires_on_station })
            }
            onMouseLeave={() => onHover(null)}
          >
            <ValidatorCard
              validator={v}
              x={v.x}
              y={v.y}
              dimmed={hl.dimmedEntities.has(`validator-${v.id}`)}
              onClick={() => onSelect({ kind: "validator", entity: v })}
            />
          </g>
        ))}
        {tripwires.map((t) => (
          <g
            key={`tripwire-${t.id}`}
            onMouseEnter={() =>
              onHover({ kind: "tripwire", id: t.id, station: t.fires_on_station })
            }
            onMouseLeave={() => onHover(null)}
          >
            <TripwireCard
              tripwire={t}
              x={t.x}
              y={t.y}
              dimmed={hl.dimmedEntities.has(`tripwire-${t.id}`)}
              onClick={() => onSelect({ kind: "tripwire", entity: t })}
            />
          </g>
        ))}
        {artifacts.map((a) => (
          <g
            key={`artifact-${a.id}`}
            onMouseEnter={() =>
              onHover({
                kind: "artifact",
                id: a.id,
                producer: a.produced_by,
                consumer: a.consumed_by,
              })
            }
            onMouseLeave={() => onHover(null)}
          >
            <ArtifactCard
              artifact={a}
              x={a.x}
              y={a.y}
              dimmed={hl.dimmedEntities.has(`artifact-${a.id}`)}
              onClick={() => onSelect({ kind: "artifact", entity: a })}
            />
          </g>
        ))}
        {sources.map((c) => (
          <ConnectorEndpoint
            key={`source-end-${c.id}`}
            connector={c}
            side="left"
            dimmed={hl.dimmedEntities.has(`source-${c.id}`)}
            onMouseEnter={() => onHover({ kind: "source", id: c.id, station: c.attachStation })}
            onMouseLeave={() => onHover(null)}
          />
        ))}
        {sinks.map((c) => (
          <ConnectorEndpoint
            key={`sink-end-${c.id}`}
            connector={c}
            side="right"
            dimmed={hl.dimmedEntities.has(`sink-${c.id}`)}
            onMouseEnter={() => onHover({ kind: "sink", id: c.id, station: c.attachStation })}
            onMouseLeave={() => onHover(null)}
          />
        ))}
      </svg>
    </div>
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
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div
        className="flex h-full w-full items-center justify-center gap-1.5 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-2"
        aria-label={`${side === "left" ? "Source" : "Sink"} ${connector.name}`}
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
  stationXById: Map<string, PositionedStation>,
): { x: number; y: number } {
  if (c.attachStation && stationXById.has(c.attachStation)) {
    const s = stationXById.get(c.attachStation)!;
    return { x: s.x, y: s.y };
  }
  return { x: WORKFLOW_CANVAS.width / 2, y: WORKFLOW_CANVAS.wireY };
}

interface Highlight {
  /** Connector ids that should stay opaque (defaults to "all opaque"
   *  when nothing is hovered — captured here as a sentinel). */
  connectors: Set<string> & { _all?: true };
  /** Entity keys that should DROP to 25% (the inverse — "everything
   *  not touching the hovered entity"). When nothing is hovered the
   *  set is empty, so nothing dims. */
  dimmedEntities: Set<string>;
}

function computeHighlight(hovered: HoverKey | null): Highlight {
  if (!hovered) {
    const all = new Set<string>() as Highlight["connectors"];
    all._all = true;
    return {
      connectors: new Proxy(all, {
        get(target, prop) {
          if (prop === "has") return () => true;
          // biome-ignore lint/suspicious/noExplicitAny: proxy-through
          return (target as any)[prop];
        },
      }) as Highlight["connectors"],
      dimmedEntities: new Set(),
    };
  }
  const liveConnectors = new Set<string>();
  const liveEntities = new Set<string>();
  switch (hovered.kind) {
    case "station": {
      // Station hover keeps all connectors touching this station opaque.
      liveEntities.add(`station-${hovered.id}`);
      break;
    }
    case "validator": {
      liveEntities.add(`validator-${hovered.id}`);
      break;
    }
    case "tripwire": {
      liveEntities.add(`tripwire-${hovered.id}`);
      break;
    }
    case "artifact": {
      liveEntities.add(`artifact-${hovered.id}`);
      liveConnectors.add(`artifact-out-${hovered.id}`);
      liveConnectors.add(`artifact-in-${hovered.id}`);
      break;
    }
    case "source": {
      liveEntities.add(`source-${hovered.id}`);
      liveConnectors.add(`source-${hovered.id}`);
      break;
    }
    case "sink": {
      liveEntities.add(`sink-${hovered.id}`);
      liveConnectors.add(`sink-${hovered.id}`);
      break;
    }
  }
  // The dimmedEntities set is "everything that exists but isn't in
  // liveEntities" — but since we only know live entities here, we
  // flip the logic at render time: each card asks
  // dimmedEntities.has(its-key), defaulting to false. So we leave
  // the set empty and instead build it from a closure over the
  // hovered key.
  return {
    connectors: liveConnectors as Highlight["connectors"],
    dimmedEntities: new Proxy(new Set<string>(), {
      get(_, prop) {
        if (prop === "has")
          return (key: string) => liveEntities.size > 0 && !liveEntities.has(key);
        // biome-ignore lint/suspicious/noExplicitAny: proxy-through
        return (Set.prototype as any)[prop as string];
      },
    }),
  };
}

function Legend() {
  return (
    <div
      aria-label="Legend"
      className="flex flex-wrap items-stretch gap-4 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-4 py-3"
    >
      <LegendItem
        swatch={
          <span
            aria-hidden
            className="h-3 w-3 rounded-full"
            style={{ background: sessionStageColor("executing") }}
          />
        }
        label="station"
        copy="lifecycle stage on the wire"
      />
      <LegendItem
        swatch={
          <span
            aria-hidden
            className="h-3 w-8 rounded-full border border-(--color-edge)"
            style={{ background: "var(--color-paper)" }}
          />
        }
        label="source"
        copy="external input wired in"
      />
      <LegendItem
        swatch={
          <span
            aria-hidden
            className="h-3 w-8 rounded-full border border-(--color-edge)"
            style={{ background: "var(--color-paper)" }}
          />
        }
        label="sink"
        copy="external output wired out"
      />
      <LegendItem
        swatch={<Stamp tone="gate">GATE</Stamp>}
        label="validator"
        copy="blocks until rule passes"
      />
      <LegendItem
        swatch={<Stamp tone="tripwire">TRIPWIRE</Stamp>}
        label="tripwire"
        copy="fires on event; agent must ack"
      />
      <LegendItem
        swatch={<Stamp tone="info">ARTIFACT</Stamp>}
        label="artifact"
        copy="typed document the workflow produces"
      />
    </div>
  );
}

function LegendItem({
  swatch,
  label,
  copy,
}: {
  swatch: React.ReactNode;
  label: string;
  copy: string;
}) {
  return (
    <div className="flex min-w-[160px] flex-1 items-center gap-2.5">
      <div className="flex h-6 w-12 items-center justify-center">{swatch}</div>
      <div className="flex flex-col gap-0.5">
        <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-(--color-ink-2)">
          {label}
        </span>
        <span className="font-serif text-[12px] italic text-(--color-ink-3) leading-snug">
          {copy}
        </span>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-1 items-center justify-center rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) py-24">
      <p className="font-serif text-[14px] italic text-(--color-ink-3)">
        Workflow not yet available — backend has not registered the orchestration graph.
      </p>
    </div>
  );
}

/**
 * PM-mode detection: `?role=pm` URL flag (dev convenience) OR the
 * `tripwire-role` localStorage key set to `pm`. Mirrors spec §4.13.
 */
function isPmMode(roleParam: string | null): boolean {
  if (roleParam === "pm") return true;
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem("tripwire-role") === "pm";
  } catch {
    return false;
  }
}
