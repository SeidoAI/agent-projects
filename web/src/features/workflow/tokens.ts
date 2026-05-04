// Workflow-page tokens. Aliases over the redesign palette declared in
// web/src/styles/app.css — no new colours introduced.

export type WorkflowActor = "pm-agent" | "coding-agent" | "code";

export const ACTOR_ORDER: readonly WorkflowActor[] = [
  "pm-agent",
  "coding-agent",
  "code",
] as const;

// CSS-var strings for SVG stroke/fill and inline styles.
export const ACTOR_COLOR: Record<WorkflowActor, string> = {
  "pm-agent": "var(--color-tripwire)",
  "coding-agent": "var(--color-gate)",
  code: "var(--color-info)",
};

// Short uppercase stamps shown bottom-right of transition nodes.
export const ACTOR_LABEL: Record<WorkflowActor, string> = {
  "pm-agent": "PM",
  "coding-agent": "CODING",
  code: "CODE",
};

// Family-style human label for the navigator column heading.
export const ACTOR_HEADING: Record<WorkflowActor, string> = {
  "pm-agent": "PM-AGENT",
  "coding-agent": "CODING-AGENT",
  code: "CODE",
};

export const isKnownActor = (actor: string): actor is WorkflowActor =>
  actor === "pm-agent" || actor === "coding-agent" || actor === "code";

// Status palette — single source of truth: web/src/components/ui/session-stage-row.tsx
// (SESSION_STAGES). Replicating the hexes here so the workflow chart's
// region tints exactly match the dashboard's stage indicator dots, without
// importing the dashboard module (which would pull in unrelated UI deps).
const STATUS_HEX: Record<string, string> = {
  planned: "#b8b0a0",
  queued: "#b07a2c",
  executing: "#c83d2e",
  in_review: "#2d3a7c",
  verified: "#2d5a3d",
  completed: "#5a4d3a",
  // soft fallbacks for non-canonical statuses (other workflows)
  intake: "#b8b0a0",
  classify: "#b07a2c",
  act: "#c83d2e",
  close: "#5a4d3a",
  draft: "#b8b0a0",
  validate: "#2d3a7c",
  publish: "#2d5a3d",
  inspect: "#b8b0a0",
  create: "#b07a2c",
  queue: "#b07a2c",
  spawn: "#c83d2e",
  monitor: "#c83d2e",
  review: "#2d3a7c",
  complete: "#5a4d3a",
  edit: "#c83d2e",
  report: "#5a4d3a",
};

export const statusHex = (statusId: string): string =>
  STATUS_HEX[statusId] ?? "#b8b0a0";

/** Convert #rrggbb → rgba(r,g,b,a). Used for low-opacity region tints. */
export const statusTint = (statusId: string, alpha: number): string => {
  const hex = statusHex(statusId);
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!m) return `rgba(184, 176, 160, ${alpha})`;
  const r = Number.parseInt(m[1]!, 16);
  const g = Number.parseInt(m[2]!, 16);
  const b = Number.parseInt(m[3]!, 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};
