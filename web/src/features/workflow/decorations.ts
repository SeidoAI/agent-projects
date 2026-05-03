// Frontend-side decoration tables that the API does not expose.
// Lifted from design_handoff_workflow/workflow/registry.jsx.

export type BranchOutcome = { branchOf: string; outcome: string };

// When two routes share a logical command and produce different outcomes,
// the layout renders them as a single diamond with labelled outgoing edges.
export const BRANCHES: Record<string, BranchOutcome> = {
  "review-approved": { branchOf: "pm-session-review", outcome: "approve" },
  "review-changes-requested": { branchOf: "pm-session-review", outcome: "request changes" },
  "publish-scope": { branchOf: "pm-validate", outcome: "pass" },
  "scope-gap-loop": { branchOf: "pm-validate", outcome: "gap" },
  "publish-update": { branchOf: "pm-validate", outcome: "pass" },
  "fix-update-loop": { branchOf: "pm-validate", outcome: "fix" },
};

// Skill loads marked as conditional rather than mandatory. The skill
// ribbon underlines these with a dotted line and a trailing "?".
export const CONDITIONAL_SKILLS: Record<string, string> = {
  "executing-to-review|backend-development": "when scope touches backend",
  "executing-to-review|agent-messaging": "when agent posts to chat",
  "review-approved|verification": "when self-review present",
  "review-changes-requested|verification": "when self-review present",
};

export const skillCondition = (routeId: string, skill: string): string | null =>
  CONDITIONAL_SKILLS[`${routeId}|${skill}`] ?? null;
