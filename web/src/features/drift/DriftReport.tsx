import { useMemo, useState } from "react";

import { useProjectShell } from "@/app/ProjectShell";
import {
  type DriftBreakdown,
  type WorkflowDriftFinding,
  useDriftReport,
} from "@/lib/api/endpoints/drift";
import { cn } from "@/lib/utils";

/**
 * Drift Report — single screen at `/p/:projectId/drift` (KUI-157).
 *
 * Renders the unified coherence score (large numeric), a per-class
 * breakdown of drift signals, and a drill-down list of active workflow
 * drift findings. The drill-down is filterable by drift class via
 * clickable breakdown rows.
 *
 * Score colouring follows the same palette used elsewhere: green
 * ≥80, amber 50-79, red <50. The page is dark-mode aware via the
 * existing Tailwind colour tokens.
 *
 * This screen surfaces the headline metric and the workflow findings
 * that drove it. Future work:
 * week-over-week sparkline (deferred — needs a historical snapshot
 * substrate that v0.9 doesn't ship).
 */
type ClassFilter = keyof DriftBreakdown | null;

const CLASS_LABELS: Record<keyof DriftBreakdown, string> = {
  stale_pins: "Stale pins",
  unresolved_refs: "Unresolved references",
  stale_concepts: "Stale concepts",
  workflow_drift_findings: "Workflow drift findings",
};

export function DriftReport() {
  const { projectId } = useProjectShell();
  const query = useDriftReport(projectId);
  const [activeClass, setActiveClass] = useState<ClassFilter>(null);

  if (query.isLoading) {
    return (
      <div className="p-6 text-sm text-zinc-500 dark:text-zinc-400">
        Loading drift report…
      </div>
    );
  }
  if (query.isError || !query.data) {
    return (
      <div className="p-6 text-sm text-red-600 dark:text-red-400">
        Failed to load drift report.
      </div>
    );
  }

  const { score, breakdown, workflow_drift_findings: findings } = query.data;
  const scoreColor = scoreColorClass(score);

  return (
    <div className="flex flex-col gap-6 p-6">
      <header className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Drift Report
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Single coherence score; higher is healthier.
          </p>
        </div>
      </header>

      <div className="flex flex-col gap-4 md:flex-row md:items-stretch">
        <ScoreCard score={score} colorClass={scoreColor} />
        <BreakdownPanel
          breakdown={breakdown}
          activeClass={activeClass}
          onSelect={setActiveClass}
        />
      </div>

      <DrillDownPanel
        findings={findings}
        activeClass={activeClass}
        onClear={() => setActiveClass(null)}
      />
    </div>
  );
}

function ScoreCard({
  score,
  colorClass,
}: {
  score: number;
  colorClass: string;
}) {
  return (
    <section
      data-testid="drift-score"
      className="flex flex-col items-center justify-center rounded-md border border-zinc-200 bg-white px-8 py-6 dark:border-zinc-800 dark:bg-zinc-900 md:w-64"
    >
      <div className={cn("text-6xl font-bold tabular-nums", colorClass)}>
        {score}
      </div>
      <div className="mt-1 text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        coherence / 100
      </div>
    </section>
  );
}

function BreakdownPanel({
  breakdown,
  activeClass,
  onSelect,
}: {
  breakdown: DriftBreakdown;
  activeClass: ClassFilter;
  onSelect: (cls: ClassFilter) => void;
}) {
  const rows = (Object.keys(CLASS_LABELS) as Array<keyof DriftBreakdown>).map(
    (key) => ({
      key,
      label: CLASS_LABELS[key],
      count: breakdown[key] ?? 0,
    }),
  );
  return (
    <section
      data-testid="drift-breakdown"
      className="flex-1 rounded-md border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
    >
      <h2 className="mb-3 text-sm font-medium text-zinc-700 dark:text-zinc-300">
        Breakdown
      </h2>
      <ul className="flex flex-col gap-1">
        {rows.map((row) => {
          const selected = activeClass === row.key;
          const drillable =
            row.key === "workflow_drift_findings" && row.count > 0;
          return (
            <li key={row.key}>
              <button
                type="button"
                onClick={() => {
                  if (!drillable) return;
                  onSelect(selected ? null : row.key);
                }}
                disabled={!drillable}
                aria-pressed={selected}
                className={cn(
                  "flex w-full items-center justify-between rounded px-2 py-1 text-sm",
                  drillable
                    ? "hover:bg-zinc-100 dark:hover:bg-zinc-800"
                    : "cursor-default opacity-80",
                  selected &&
                    "bg-zinc-100 ring-1 ring-zinc-300 dark:bg-zinc-800 dark:ring-zinc-700",
                )}
              >
                <span className="text-zinc-700 dark:text-zinc-300">
                  {row.label}
                </span>
                <span className="font-mono tabular-nums text-zinc-900 dark:text-zinc-100">
                  {row.count}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function DrillDownPanel({
  findings,
  activeClass,
  onClear,
}: {
  findings: WorkflowDriftFinding[];
  activeClass: ClassFilter;
  onClear: () => void;
}) {
  const filtered = useMemo(() => {
    if (activeClass === null) return findings;
    if (activeClass !== "workflow_drift_findings") return [];
    return findings;
  }, [findings, activeClass]);

  if (filtered.length === 0) {
    return (
      <section
        data-testid="drift-drill-down"
        className="rounded-md border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
      >
        <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Workflow drift findings
        </h2>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {activeClass === null
            ? "No active workflow drift findings."
            : "Drill-down for this class isn't surfaced on this screen."}
        </p>
      </section>
    );
  }

  return (
    <section
      data-testid="drift-drill-down"
      className="rounded-md border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
    >
      <header className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Workflow drift findings ({filtered.length})
        </h2>
        {activeClass !== null && (
          <button
            type="button"
            onClick={onClear}
            className="text-xs text-zinc-500 underline hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            clear filter
          </button>
        )}
      </header>
      <ul className="flex flex-col gap-2 text-xs">
        {filtered.map((finding, idx) => (
          <li
            key={`${finding.code}-${finding.instance}-${finding.station ?? "none"}-${idx}`}
            className="border-b border-zinc-100 py-2 last:border-b-0 dark:border-zinc-800"
          >
            <div className="flex flex-wrap items-center gap-2 font-mono">
              <span className="font-medium text-zinc-900 dark:text-zinc-100">
                {finding.code}
              </span>
              <span className="text-zinc-500 dark:text-zinc-400">
                {finding.workflow}:{finding.instance}
              </span>
              <span className="text-zinc-500 dark:text-zinc-400">
                {finding.station ?? "-"}
              </span>
              <span className="uppercase text-zinc-500 dark:text-zinc-400">
                {finding.severity}
              </span>
            </div>
            <p className="mt-1 text-zinc-700 dark:text-zinc-300">
              {finding.message}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function scoreColorClass(score: number): string {
  if (score >= 80) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 50) return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}
