import { AlertTriangle } from "lucide-react";
import type { MouseEvent } from "react";

import { cn } from "@/lib/utils";

/** The off-track stage id is special-cased in the row: when its
 *  bucket has any sessions, the card flips into an alert state
 *  (red border, alert icon) regardless of selection. */
export const OFF_TRACK_STAGE_ID = "off_track";

/**
 * Canonical 7-stage session lifecycle used for the dashboard row.
 *
 * The backend `session_status` enum carries 14 values (executing,
 * active, waiting_for_ci, etc.) — too many to ground the dashboard's
 * "where does my attention go?" frame. The 7 canonical stages here
 * collapse the richer enum into the strategic view; the `matches`
 * predicate handles the mapping.
 *
 * The 7th stage `off_track` (failed/paused/abandoned) sits at the
 * right end of the row — sessions that fell out of the happy path
 * are exactly what a PM needs to see, so the row surfaces them
 * directly (in addition to being escalated via the attention queue).
 */
export interface SessionStage {
  id: string;
  label: string;
  color: string;
  matches: (status: string) => boolean;
}

export const SESSION_STAGES: SessionStage[] = [
  {
    id: "planned",
    label: "planned",
    color: "#9a9285",
    matches: (s) => s === "planned",
  },
  {
    id: "queued",
    label: "queued",
    color: "#7a7368",
    matches: (s) => s === "queued",
  },
  {
    id: "executing",
    label: "executing",
    color: "#c83d2e",
    matches: (s) =>
      s === "executing" ||
      s === "active" ||
      s === "waiting_for_ci" ||
      s === "waiting_for_review" ||
      s === "waiting_for_deploy",
  },
  {
    id: "in_review",
    label: "review",
    color: "#2d3a7c",
    matches: (s) => s === "in_review" || s === "re_engaged",
  },
  {
    id: "verified",
    label: "verified",
    color: "#2d5a3d",
    matches: (s) => s === "verified",
  },
  {
    id: "completed",
    label: "completed",
    color: "#5a4d3a",
    matches: (s) => s === "completed",
  },
  {
    id: "off_track",
    label: "off-track",
    color: "#b8741a",
    matches: (s) => s === "failed" || s === "paused" || s === "abandoned",
  },
];

export const UNASSIGNED_STAGE_ID = "unassigned";
const UNASSIGNED_COLOR = "#a89d8c";

/** Lookup helper: returns the canonical stage id for any session
 *  status. Returns `null` only for null/undefined or genuinely
 *  unknown states — every documented backend status now maps to one
 *  of the 7 stages (including off-track). */
export function sessionStageId(status: string | null | undefined): string | null {
  if (!status) return null;
  for (const s of SESSION_STAGES) {
    if (s.matches(status)) return s.id;
  }
  return null;
}

/** Lookup helper: returns the stage color for any session status, or
 *  the off-track color for unmapped states (defensive default). Used
 *  by the right-column session pill so its color matches the top
 *  row's card stripe. */
export function sessionStageColor(status: string | null | undefined): string {
  const id = sessionStageId(status);
  if (!id) return "#b8741a";
  const stage = SESSION_STAGES.find((s) => s.id === id);
  return stage?.color ?? "#b8741a";
}

export interface StageBucket {
  sessionCount: number;
  issueCount: number;
}

export interface SessionStageRowProps {
  /** Per-stage counts. Keys = stage id (or `unassigned`). */
  buckets: Record<string, StageBucket>;
  /** Currently-selected stage ids. Empty = no filter. */
  selected: Set<string>;
  /** Click handler. Receives the stage id and the modifier-key state
   *  (cmd on mac, ctrl elsewhere) so the parent can implement
   *  add-to-selection vs replace-selection semantics. */
  onStageClick: (stageId: string, additive: boolean) => void;
  className?: string;
}

/**
 * Top-of-dashboard row of stage filter cards.
 *
 * Layout: 7 cards in a flexbox row — `(unassigned)` on the left, then
 * the 6 canonical lifecycle stages. Each card shows `N sess · M iss`
 * and a coloured stripe matching the stage. Cards are buttons:
 *
 * - plain click: toggle (replace selection with this single stage,
 *   or clear if it was the only-selected one)
 * - cmd/ctrl + click: additive (add or remove from selection)
 *
 * Selection state lives in the parent (ProjectDashboard). Default in
 * the parent is `{executing, in_review}` — the "what's live" view.
 */
export function SessionStageRow({
  buckets,
  selected,
  onStageClick,
  className,
}: SessionStageRowProps) {
  const cards: { id: string; label: string; color: string; isUnassigned: boolean }[] = [
    {
      id: UNASSIGNED_STAGE_ID,
      label: "unassigned",
      color: UNASSIGNED_COLOR,
      isUnassigned: true,
    },
    ...SESSION_STAGES.map((s) => ({
      id: s.id,
      label: s.label,
      color: s.color,
      isUnassigned: false,
    })),
  ];

  return (
    <div className={cn("flex flex-wrap gap-2.5", className)}>
      {cards.map((c) => {
        const bucket = buckets[c.id] ?? { sessionCount: 0, issueCount: 0 };
        const isSelected = selected.has(c.id);
        const isAlert = c.id === OFF_TRACK_STAGE_ID && bucket.sessionCount > 0;
        const handleClick = (ev: MouseEvent<HTMLButtonElement>) => {
          const additive = ev.metaKey || ev.ctrlKey;
          onStageClick(c.id, additive);
        };
        // Alert state overrides the usual selected/hover treatment:
        // red border + tinted background + alert icon. The card
        // also reads in the same red regardless of selection so the
        // PM can't miss it.
        const cardClass = cn(
          "flex min-w-[120px] flex-1 flex-col items-start gap-2 rounded-(--radius-stamp) border px-3 py-2.5 text-left transition-colors",
          isAlert
            ? "border-(--color-rule) bg-(--color-rule)/10 ring-1 ring-(--color-rule)/40"
            : isSelected
              ? "border-(--color-ink) bg-(--color-paper) shadow-[0_0_0_1px_var(--color-ink)]"
              : "border-(--color-edge) bg-(--color-paper) hover:border-(--color-ink-3)",
        );
        return (
          <button
            key={c.id}
            type="button"
            onClick={handleClick}
            aria-pressed={isSelected}
            aria-label={`Filter to ${c.label} (${bucket.sessionCount} sessions, ${bucket.issueCount} issues)${isAlert ? " — alert" : ""}`}
            className={cardClass}
          >
            <div className="flex w-full items-center justify-between">
              {isAlert ? (
                <AlertTriangle
                  className="h-3.5 w-3.5 text-(--color-rule)"
                  strokeWidth={2.4}
                  aria-hidden
                />
              ) : (
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  aria-hidden
                  style={{ background: c.color }}
                />
              )}
              <span
                className={cn(
                  "font-sans font-semibold text-[20px] tabular-nums leading-none tracking-[-0.02em]",
                  isAlert ? "text-(--color-rule)" : "text-(--color-ink)",
                )}
              >
                {c.isUnassigned ? bucket.issueCount : bucket.sessionCount}
              </span>
            </div>
            <div
              className={cn(
                "font-mono text-[10px] uppercase tracking-[0.06em]",
                isAlert ? "font-semibold text-(--color-rule)" : "text-(--color-ink-3)",
              )}
            >
              {c.label}
            </div>
            {!c.isUnassigned ? (
              <div
                className={cn(
                  "font-mono text-[10px] tracking-[0.04em]",
                  isAlert ? "text-(--color-rule)" : "text-(--color-ink-3)",
                )}
              >
                {bucket.sessionCount} sess · {bucket.issueCount} iss
              </div>
            ) : (
              <div className="font-mono text-[10px] text-(--color-ink-3) tracking-[0.04em]">
                no session
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
