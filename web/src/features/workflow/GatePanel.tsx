import { useEffect, useState } from "react";

import { sourceApi } from "@/lib/api/endpoints/source";
import type {
  WorkflowRegistry,
  WorkflowRegistryEntry,
  WorkflowRoute,
} from "@/lib/api/endpoints/workflow";
import { SourceViewer } from "./SourceViewer";

export interface GateRow {
  kind: "tripwire" | "heuristic" | "prompt-check";
  id: string;
  label: string;
  blurb: string;
  source: string;
}

const sourceOf = (entry?: WorkflowRegistryEntry): string =>
  (entry?.source ?? "").trim();

export function describeGateContents(
  route: WorkflowRoute,
  registry?: WorkflowRegistry,
): GateRow[] {
  const rows: GateRow[] = [];
  const tripwireBy = new Map(
    (registry?.tripwires ?? []).map((v) => [v.id, v]),
  );
  const heuristicBy = new Map(
    (registry?.heuristics ?? []).map((h) => [h.id, h]),
  );
  const pmtBy = new Map((registry?.prompt_checks ?? []).map((p) => [p.id, p]));
  for (const id of route.controls.tripwires ?? []) {
    const entry = tripwireBy.get(id);
    rows.push({
      kind: "tripwire",
      id,
      label: id.replace(/^v_/, ""),
      blurb: entry?.description ?? entry?.label ?? "",
      source: sourceOf(entry),
    });
  }
  for (const id of route.controls.heuristics ?? []) {
    const entry = heuristicBy.get(id);
    rows.push({
      kind: "heuristic",
      id,
      label: id,
      blurb: entry?.description ?? entry?.label ?? "",
      source: sourceOf(entry),
    });
  }
  for (const id of route.controls.prompt_checks ?? []) {
    const entry = pmtBy.get(id);
    rows.push({
      kind: "prompt-check",
      id,
      label: id,
      blurb: entry?.description ?? entry?.label ?? "",
      source: sourceOf(entry),
    });
  }
  return rows;
}

export interface GatePanelProps {
  route: WorkflowRoute;
  registry?: WorkflowRegistry;
  onClose: () => void;
  // Page-pixel position (relative to the chart container) — passed by the host.
  pageX?: number;
  pageY?: number;
}

export function GatePanel({
  route,
  registry,
  onClose,
  pageX,
  pageY,
}: GatePanelProps) {
  const rows = describeGateContents(route, registry);
  const [sourcePath, setSourcePath] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (sourcePath) setSourcePath(null);
        else onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, sourcePath]);

  if (rows.length === 0) return null;

  return (
    <div
      data-testid={`workflow-gate-panel-${route.id}`}
      role="dialog"
      aria-label={`Gate checks for ${route.label}`}
      style={{
        position: "absolute",
        left: pageX ?? "50%",
        top: pageY ?? "50%",
        transform: pageX == null ? "translate(-50%, -50%)" : "translateX(-50%)",
        minWidth: 300,
        maxWidth: 360,
        background: "var(--color-paper)",
        border: "1.5px solid var(--color-gate)",
        boxShadow: "0 14px 30px rgba(26,24,21,0.12)",
        padding: "10px 12px",
        zIndex: 30,
        fontSize: 12,
        color: "var(--color-ink)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 6,
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            letterSpacing: "0.18em",
            color: "var(--color-gate)",
          }}
        >
          GATE · {rows.length} CHECKS
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close gate panel"
          style={{
            cursor: "pointer",
            border: 0,
            background: "none",
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--color-ink-3)",
          }}
        >
          ×
        </button>
      </div>
      <div
        style={{
          fontFamily: "var(--font-sans)",
          fontWeight: 600,
          fontSize: 13,
          marginBottom: 8,
        }}
      >
        on {route.label}
      </div>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 5,
          maxHeight: 280,
          overflow: "auto",
        }}
      >
        {rows.map((row, i) => (
          <div
            key={`${row.kind}-${row.id}-${i}`}
            style={{
              display: "flex",
              gap: 8,
              padding: "4px 0",
              borderTop: i === 0 ? "none" : "1px dashed var(--color-edge)",
            }}
          >
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 9,
                color:
                  row.kind === "tripwire"
                    ? "var(--color-gate)"
                    : row.kind === "heuristic"
                      ? "var(--color-warn)"
                      : "var(--color-info)",
                letterSpacing: "0.04em",
                flexShrink: 0,
                width: 28,
                textTransform: "uppercase",
              }}
            >
              {row.kind === "tripwire"
                ? "trp"
                : row.kind === "heuristic"
                  ? "hrs"
                  : "pmt"}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 10.5,
                    color: "var(--color-ink)",
                  }}
                >
                  {row.label}
                </span>
                {row.source && (
                  <button
                    type="button"
                    onClick={() => setSourcePath(row.source)}
                    style={{
                      cursor: "pointer",
                      border: "1px solid var(--color-edge)",
                      background: "var(--color-paper-2)",
                      padding: "1px 6px",
                      fontFamily: "var(--font-mono)",
                      fontSize: 9,
                      color: "var(--color-ink-2)",
                      letterSpacing: "0.04em",
                    }}
                    title={row.source}
                  >
                    src
                  </button>
                )}
              </div>
              {row.blurb && (
                <div
                  style={{
                    fontFamily: "var(--font-serif)",
                    fontStyle: "italic",
                    fontSize: 11.5,
                    color: "var(--color-ink-2)",
                    marginTop: 1,
                  }}
                >
                  {row.blurb}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
      {sourcePath && (
        <SourceViewer
          path={sourcePath}
          onClose={() => setSourcePath(null)}
          onOpenLocally={async () => {
            try {
              await sourceApi.open(sourcePath);
            } catch (err) {
              // soft-fail; the user can still copy the path
              console.error("open failed", err);
            }
          }}
        />
      )}
    </div>
  );
}
