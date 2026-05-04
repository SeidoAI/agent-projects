export type QueryKey = readonly unknown[];

export interface IssueFilters {
  status?: string;
  priority?: string;
  executor?: string;
  label?: string;
}

export const queryKeys = {
  // Projects
  projects: () => ["projects"] as const,
  project: (id: string) => ["projects", id] as const,

  // Issues
  issues: (pid: string) => ["issues", pid] as const,
  issuesFiltered: (pid: string, filters: IssueFilters) => ["issues", pid, filters] as const,
  issue: (pid: string, key: string) => ["issues", pid, key] as const,

  // Nodes
  nodes: (pid: string) => ["nodes", pid] as const,
  node: (pid: string, nid: string) => ["nodes", pid, nid] as const,
  reverseRefs: (pid: string, nid: string) => ["nodes", pid, nid, "reverseRefs"] as const,

  // Graphs
  graph: (pid: string, type: "deps" | "concept") => ["graph", pid, type] as const,

  // Inbox (PM-agent attention queue)
  inbox: (pid: string) => ["inbox", pid] as const,
  inboxFiltered: (pid: string, filters: { bucket?: string; resolved?: boolean }) =>
    ["inbox", pid, filters] as const,
  inboxItem: (pid: string, id: string) => ["inbox", pid, id] as const,

  // Sessions
  sessions: (pid: string) => ["sessions", pid] as const,
  session: (pid: string, sid: string) => ["sessions", pid, sid] as const,
  sessionArtifacts: (pid: string, sid: string) => ["sessions", pid, sid, "artifacts"] as const,
  artifact: (pid: string, sid: string, name: string) =>
    ["sessions", pid, sid, "artifacts", name] as const,

  // Manifest + enums + orchestration
  artifactManifest: (pid: string) => ["projects", pid, "artifact-manifest"] as const,
  enum: (pid: string, name: string) => ["projects", pid, "enums", name] as const,
  orchestration: (pid: string) => ["projects", pid, "orchestration"] as const,
  validationStatus: (pid: string) => ["projects", pid, "validation-status"] as const,

  // Strand Y (v0.8) — workflow graph + process events.
  workflow: (pid: string) => ["projects", pid, "workflow"] as const,
  events: (pid: string, params: object) => ["projects", pid, "events", params] as const,

  // v0.9 — workflow events log (KUI-155, KUI-156). Distinct from
  // `events` above (v0.8 emitter); reads the v0.9 events log.
  workflowEvents: (pid: string, params: object) =>
    ["projects", pid, "workflow-events", params] as const,
  workflowStats: (pid: string, params: object) =>
    ["projects", pid, "workflow-stats", params] as const,

  // Drift report — surfaces on the Concept Graph header card
  // (the standalone /drift page was retired in v0.9.7).
  drift: (pid: string) => ["projects", pid, "drift"] as const,

  // v2 (declared but unused in v1 — placeholder to avoid churn later)
  containers: () => ["containers"] as const,
  messages: (sid: string) => ["messages", sid] as const,
  unreadMessages: () => ["messages", "unread"] as const,
  githubPrs: (repo: string) => ["github", "prs", repo] as const,
};

export const staleTime = {
  default: 30_000,
  enum: 5 * 60_000,
  orchestration: 5 * 60_000,
  container: 5_000,
  github: 60_000,
  message: 0,
} as const;

export function isPrefix(key: QueryKey, prefix: QueryKey): boolean {
  if (prefix.length > key.length) return false;
  for (let i = 0; i < prefix.length; i++) {
    if (key[i] !== prefix[i]) return false;
  }
  return true;
}
