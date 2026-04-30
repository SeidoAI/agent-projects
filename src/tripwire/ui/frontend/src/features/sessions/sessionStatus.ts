/**
 * Status vocabulary for the sessions page — colour, sort priority, and
 * per-status visual treatment.
 *
 * Keys mirror `tripwire.models.enums.SessionStatus`:
 *   PLANNED, QUEUED, EXECUTING, ACTIVE, WAITING_FOR_CI,
 *   WAITING_FOR_REVIEW, WAITING_FOR_DEPLOY, RE_ENGAGED, IN_REVIEW,
 *   VERIFIED, COMPLETED.
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
  active: {
    color: "var(--color-rule)",
    label: "active",
    order: 0,
    fillOpacity: 1,
    textOnFill: "paper",
  },
  re_engaged: {
    color: "var(--color-rule)",
    label: "re-engaged",
    order: 0,
    fillOpacity: 0.9,
    textOnFill: "paper",
  },

  // Awaiting review / CI — gating, can't make progress without action.
  waiting_for_review: {
    color: "var(--color-gate)",
    label: "awaiting review",
    order: 1,
    fillOpacity: 0.85,
    textOnFill: "paper",
  },
  in_review: {
    color: "var(--color-gate)",
    label: "in review",
    order: 1,
    fillOpacity: 0.85,
    textOnFill: "paper",
  },
  waiting_for_ci: {
    color: "var(--color-gate)",
    label: "waiting CI",
    order: 1,
    fillOpacity: 0.7,
    textOnFill: "paper",
  },
  waiting_for_deploy: {
    color: "var(--color-gate)",
    label: "waiting deploy",
    order: 1,
    fillOpacity: 0.7,
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
  "active",
  "re_engaged",
  "waiting_for_review",
  "in_review",
  "waiting_for_ci",
  "waiting_for_deploy",
  "planned",
  "queued",
]);

export function isCompletedLike(status: string): boolean {
  return status === "completed" || status === "verified";
}
