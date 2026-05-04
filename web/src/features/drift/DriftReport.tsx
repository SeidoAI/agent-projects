import { useMemo, useState } from "react";

import { useProjectShell } from "@/app/ProjectShell";
import { Stamp, type StampTone } from "@/components/ui/stamp";
import {
  type DriftBreakdown,
  useDriftReport,
  type WorkflowDriftFinding,
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

const CLASS_STAMP_TONES: Record<keyof DriftBreakdown, StampTone> = {
  stale_pins: "tripwire",
  unresolved_refs: "rule",
  stale_concepts: "info",
  workflow_drift_findings: "gate",
};

export function DriftReport() {
  const { projectId } = useProjectShell();
  const query = useDriftReport(projectId);
  const [activeClass, setActiveClass] = useState<ClassFilter>(null);

  if (query.isLoading) {
    return (
      <div className="p-6 font-serif text-[13px] italic text-(--color-ink-3)">
        Loading drift report…
      </div>
    );
  }
  if (query.isError || !query.data) {
    return (
      <div className="p-6 font-serif text-[13px] italic text-(--color-rule)">
        Failed to load drift report.
      </div>
    );
  }

  const { score, breakdown, workflow_drift_findings: findings } = query.data;

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="font-sans font-semibold text-[28px] text-(--color-ink) tracking-[-0.02em] leading-tight">
          Drift report
        </h1>
        <p className="font-serif text-[14px] italic text-(--color-ink-2) leading-snug">
          coherence score across references, concept freshness, and workflow drift findings.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_1fr]">
        <ScoreCard score={score} />
        <BreakdownPanel breakdown={breakdown} activeClass={activeClass} onSelect={setActiveClass} />
      </div>

      <DrillDownPanel
        findings={findings}
        activeClass={activeClass}
        onClear={() => setActiveClass(null)}
      />
    </div>
  );
}

function ScoreCard({ score }: { score: number }) {
  return (
    <section
      data-testid="drift-score"
      aria-label="Coherence score"
      className="flex min-h-[156px] flex-col justify-between rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) p-4"
    >
      <div className="flex items-center justify-between">
        <h2 className="font-sans font-semibold text-[14px] uppercase tracking-[0.04em] text-(--color-ink-2)">
          coherence
        </h2>
        <Stamp tone={scoreTone(score)}>{scoreBand(score)}</Stamp>
      </div>
      <div>
        <div className="font-sans font-semibold text-[64px] leading-none tracking-[-0.03em] text-(--color-ink) tabular-nums">
          {score}
        </div>
        <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-3)">
          out of 100
        </div>
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
  const rows = (Object.keys(CLASS_LABELS) as Array<keyof DriftBreakdown>).map((key) => ({
    key,
    label: CLASS_LABELS[key],
    count: breakdown[key] ?? 0,
  }));
  return (
    <section
      data-testid="drift-breakdown"
      className="flex min-h-[156px] flex-col gap-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) p-4"
    >
      <h2 className="font-sans font-semibold text-[14px] uppercase tracking-[0.04em] text-(--color-ink-2)">
        Breakdown
      </h2>
      <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {rows.map((row) => {
          const selected = activeClass === row.key;
          const drillable = row.key === "workflow_drift_findings" && row.count > 0;
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
                  "flex min-h-[44px] w-full items-center gap-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-3 py-2 text-left",
                  drillable ? "hover:bg-(--color-paper-3)" : "cursor-default opacity-80",
                  selected && "bg-(--color-paper-3) ring-1 ring-(--color-ink-3)",
                )}
              >
                <Stamp tone={CLASS_STAMP_TONES[row.key]}>
                  {row.key === "workflow_drift_findings" ? "workflow" : "signal"}
                </Stamp>
                <span className="min-w-0 truncate font-sans text-[13px] text-(--color-ink-2)">
                  {row.label}
                </span>
                <span className="ml-auto font-mono text-[12px] tabular-nums text-(--color-ink)">
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
        className="flex flex-col gap-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) p-4"
      >
        <h2 className="font-sans font-semibold text-[14px] uppercase tracking-[0.04em] text-(--color-ink-2)">
          Workflow drift findings
        </h2>
        <p className="font-serif text-[13px] italic text-(--color-ink-3)">
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
      className="flex min-h-0 flex-col gap-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) p-4"
    >
      <header className="flex items-center justify-between gap-3">
        <h2 className="font-sans font-semibold text-[14px] uppercase tracking-[0.04em] text-(--color-ink-2)">
          Workflow drift findings ({filtered.length})
        </h2>
        {activeClass !== null && (
          <button
            type="button"
            onClick={onClear}
            className="rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-2 py-1 font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-2) hover:bg-(--color-paper-3)"
          >
            clear filter
          </button>
        )}
      </header>
      <ul className="flex flex-col gap-2 text-xs">
        {filtered.map((finding) => (
          <li
            key={findingKey(finding)}
            className="rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-3 py-2"
          >
            <div className="flex flex-wrap items-center gap-2 font-mono">
              <Stamp tone="rule">{finding.code}</Stamp>
              <span className="text-[11px] text-(--color-ink-2)">
                {finding.workflow}:{finding.instance}
              </span>
              <span className="text-[11px] text-(--color-ink-3)">{finding.status ?? "-"}</span>
              <Stamp tone={finding.severity === "error" ? "tripwire" : "info"}>
                {finding.severity}
              </Stamp>
            </div>
            <p className="mt-2 font-sans text-[13px] leading-snug text-(--color-ink-2)">
              {finding.message}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function scoreBand(score: number): string {
  if (score >= 80) return "healthy";
  if (score >= 50) return "watch";
  return "drift";
}

function scoreTone(score: number): StampTone {
  if (score >= 80) return "gate";
  if (score >= 50) return "tripwire";
  return "rule";
}

function findingKey(finding: WorkflowDriftFinding): string {
  return [
    finding.code,
    finding.workflow,
    finding.instance,
    finding.status ?? "-",
    finding.severity,
    finding.message,
  ].join("|");
}
