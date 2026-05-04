import { AlertTriangle, ShieldCheck } from "lucide-react";

import { useDriftReport } from "@/lib/api/endpoints/drift";
import { cn } from "@/lib/utils";

export interface DriftHeaderProps {
  projectId: string;
  staleCount: number;
  staleOnly: boolean;
  onToggleStaleOnly: () => void;
}

/**
 * Drift status card on the Concept Graph header — replaces the
 * retired `/drift` page per the v0.9.7 page-consolidation pass
 * (see [[principle-concept-graph-as-definition]] + the "drift is
 * a metric, not a view" rationale).
 *
 * Surfaces the unified coherence score plus the per-class
 * breakdown (stale pins, unresolved refs, stale concepts, workflow
 * drift findings) and a single affordance: "show stale only" — a
 * filter that the canvas/sidebar consumes to dim/hide non-stale
 * nodes while the user investigates.
 *
 * Score colour is a 3-band traffic light: green ≥ 90, amber 70-89,
 * red < 70. Matches the retired DriftReport's banding so operators
 * who learned the old surface read this one identically.
 */
export function DriftHeader({
  projectId,
  staleCount,
  staleOnly,
  onToggleStaleOnly,
}: DriftHeaderProps) {
  const query = useDriftReport(projectId);
  const report = query.data;
  const score = report?.score;
  const breakdown = report?.breakdown;
  const findings = report?.workflow_drift_findings ?? [];

  const tone = scoreTone(score);

  return (
    <section
      data-testid="drift-header"
      data-tone={tone}
      aria-label="Drift status"
      className={cn(
        "flex flex-wrap items-center gap-4 rounded-(--radius-stamp) border px-4 py-3",
        tone === "ok" && "border-(--color-edge) bg-(--color-paper-2)",
        tone === "warn" && "border-(--color-gate) bg-(--color-gate)/8",
        tone === "alert" && "border-(--color-rule) bg-(--color-rule)/10",
        tone === "loading" && "border-(--color-edge) bg-(--color-paper-2)",
      )}
    >
      <div
        className="flex flex-1 flex-wrap items-baseline gap-x-3 gap-y-1"
        data-testid="drift-stats-row"
      >
        <ScoreBlock tone={tone} score={score} pending={query.isPending} />
        <Separator />
        <BreakdownStat
          label="stale concepts"
          value={breakdown?.stale_concepts}
          testId="drift-stale-concepts"
        />
        <Separator />
        <BreakdownStat
          label="stale pins"
          value={breakdown?.stale_pins}
          testId="drift-stale-pins"
        />
        <Separator />
        <BreakdownStat
          label="unresolved refs"
          value={breakdown?.unresolved_refs}
          testId="drift-unresolved-refs"
        />
        <Separator />
        <BreakdownStat
          label="workflow drift"
          value={breakdown?.workflow_drift_findings}
          testId="drift-workflow"
          highlight={findings.length > 0}
        />
      </div>

      <button
        type="button"
        onClick={onToggleStaleOnly}
        aria-pressed={staleOnly}
        disabled={staleCount === 0}
        data-testid="drift-stale-only-toggle"
        className={cn(
          "rounded-(--radius-stamp) border px-3 py-1 font-mono text-[11px] uppercase tracking-[0.06em] transition-colors",
          staleOnly
            ? "border-(--color-ink) bg-(--color-ink) text-(--color-paper)"
            : "border-(--color-edge) bg-(--color-paper) text-(--color-ink-2) hover:bg-(--color-paper-3)",
          staleCount === 0 && "cursor-not-allowed opacity-50 hover:bg-(--color-paper)",
        )}
      >
        {staleCount === 0 ? "no stale nodes" : `show stale only · ${staleCount}`}
      </button>
    </section>
  );
}

function ScoreBlock({
  tone,
  score,
  pending,
}: {
  tone: Tone;
  score: number | undefined;
  pending: boolean;
}) {
  const Icon = tone === "alert" ? AlertTriangle : ShieldCheck;
  const colorClass =
    tone === "alert"
      ? "text-(--color-rule)"
      : tone === "warn"
        ? "text-(--color-gate)"
        : tone === "ok"
          ? "text-(--color-info)"
          : "text-(--color-ink-3)";

  return (
    <div className="flex items-baseline gap-2" data-testid="drift-score-block">
      <Icon
        className={cn("h-4 w-4 shrink-0 self-center", colorClass)}
        aria-hidden
      />
      <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-3)">
        coherence
      </span>
      <span
        className={cn(
          "font-sans font-semibold text-[15px] tabular-nums",
          colorClass,
        )}
        data-testid="drift-score"
      >
        {pending ? "…" : (score ?? "—")}
      </span>
    </div>
  );
}

function BreakdownStat({
  label,
  value,
  testId,
  highlight = false,
}: {
  label: string;
  value: number | undefined;
  testId: string;
  highlight?: boolean;
}) {
  const v = value ?? 0;
  return (
    <div className="flex items-baseline gap-2" data-testid={testId}>
      <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-3)">
        {label}
      </span>
      <span
        className={cn(
          "font-sans font-semibold text-[15px] tabular-nums",
          highlight && v > 0 ? "text-(--color-rule)" : "text-(--color-ink)",
        )}
      >
        {v}
      </span>
    </div>
  );
}

function Separator() {
  return (
    <span aria-hidden className="font-mono text-[14px] text-(--color-ink-3) leading-none">
      ·
    </span>
  );
}

type Tone = "ok" | "warn" | "alert" | "loading";

function scoreTone(score: number | undefined): Tone {
  if (score === undefined) return "loading";
  if (score >= 90) return "ok";
  if (score >= 70) return "warn";
  return "alert";
}
