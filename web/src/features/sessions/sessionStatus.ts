/**
 * Status vocabulary for the sessions page — colour, sort priority, and
 * per-status visual treatment.
 *
 * Keys mirror `tripwire.models.enums.SessionStatus`:
 *   PLANNED, QUEUED, EXECUTING, IN_REVIEW, VERIFIED, COMPLETED,
 *   PAUSED, FAILED, ABANDONED.
 *
 * Hierarchy reflects PM attention: what's *running now* tops the list,
 * then what's *waiting on review*, then what's *ready next*, then *held*,
 * then *done*. Drives both section-divider order and the within-layer
 * DAG row tie-break.
 */

export interface StatusStyle {
  color: string;
  label: string;
  /** Lower = higher up. */
  order: number;
  /** Opacity of the node's coloured fill in the flow. */
  fillOpacity: number;
  /** Text colour against the fill. */
  textOnFill: "paper" | "ink";
}

const STATUS_STYLES: Record<string, StatusStyle> = {
  // Live work — top of the list, full saturation, white labels.
  executing: {
    color: "var(--color-rule)",
    label: "executing",
    order: 0,
    fillOpacity: 1,
    textOnFill: "paper",
  },

  // Awaiting review — gating, can't make progress without action.
  in_review: {
    color: "var(--color-gate)",
    label: "in review",
    order: 1,
    fillOpacity: 0.85,
    textOnFill: "paper",
  },

  // Up next — actionable.
  planned: {
    color: "var(--color-info)",
    label: "planned",
    order: 2,
    fillOpacity: 0.6,
    textOnFill: "ink",
  },
  queued: {
    color: "var(--color-info)",
    label: "queued",
    order: 2,
    fillOpacity: 0.6,
    textOnFill: "ink",
  },

  // Verified before final-completion — close to done but not yet.
  verified: {
    color: "var(--color-ink-2)",
    label: "verified",
    order: 3,
    fillOpacity: 0.35,
    textOnFill: "ink",
  },

  // Done — quiet; only kept in the flow when adjacent to live work.
  completed: {
    color: "var(--color-ink-2)",
    label: "completed",
    order: 4,
    fillOpacity: 0.18,
    textOnFill: "ink",
  },

  // Off-track — paused/failed/abandoned. Displayed but de-prioritised.
  paused: {
    color: "var(--color-ink-3)",
    label: "paused",
    order: 5,
    fillOpacity: 0.3,
    textOnFill: "ink",
  },
  failed: {
    color: "var(--color-rule)",
    label: "failed",
    order: 5,
    fillOpacity: 0.3,
    textOnFill: "paper",
  },
  abandoned: {
    color: "var(--color-ink-3)",
    label: "abandoned",
    order: 5,
    fillOpacity: 0.18,
    textOnFill: "ink",
  },
};

const FALLBACK: StatusStyle = {
  color: "var(--color-ink-3)",
  label: "other",
  order: 99,
  fillOpacity: 0.3,
  textOnFill: "ink",
};

export function statusStyle(status: string): StatusStyle {
  return STATUS_STYLES[status] ?? { ...FALLBACK, label: status };
}

export function colorForStatus(status: string): string {
  return statusStyle(status).color;
}

export function statusOrder(status: string): number {
  return statusStyle(status).order;
}

/** Statuses treated as "live/active work" for the flow's culling rule. */
export const LIVE_STATUSES = new Set([
  "executing",
  "in_review",
  "planned",
  "queued",
]);

export function isCompletedLike(status: string): boolean {
  return status === "completed" || status === "verified";
}
