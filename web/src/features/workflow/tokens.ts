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
