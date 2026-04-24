import { apiGet, apiPatch } from "../client";

export type ReferenceKind = "issue" | "node" | "session";

export interface Reference {
  ref: string;
  resolves_as: ReferenceKind;
  is_stale: boolean;
}

/** Mirrors `IssueSummary` from `tripwire.ui.services.issue_service`. */
export interface IssueSummary {
  id: string;
  title: string;
  status: string;
  priority: string;
  executor: string;
  verifier: string;
  kind: string | null;
  agent: string | null;
  labels: string[];
  parent: string | null;
  repo: string | null;
  blocked_by: string[];
  is_blocked: boolean;
  is_epic: boolean;
}

export interface IssueDetail extends IssueSummary {
  body: string;
  refs: Reference[];
}

export interface IssuePatch {
  status?: string;
  priority?: string;
  labels?: string[];
  agent?: string | null;
}

export interface IssueFilterParams {
  status?: string;
  executor?: string;
  label?: string;
  parent?: string;
}

function buildQuery(filters?: IssueFilterParams): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.executor) params.set("executor", filters.executor);
  if (filters.label) params.set("label", filters.label);
  if (filters.parent) params.set("parent", filters.parent);
  const s = params.toString();
  return s ? `?${s}` : "";
}

export const issuesApi = {
  list: (pid: string, filters?: IssueFilterParams) =>
    apiGet<IssueSummary[]>(`/api/projects/${encodeURIComponent(pid)}/issues${buildQuery(filters)}`),

  get: (pid: string, key: string) =>
    apiGet<IssueDetail>(
      `/api/projects/${encodeURIComponent(pid)}/issues/${encodeURIComponent(key)}`,
    ),

  patch: (pid: string, key: string, patch: IssuePatch) =>
    apiPatch<IssueDetail>(
      `/api/projects/${encodeURIComponent(pid)}/issues/${encodeURIComponent(key)}`,
      patch,
    ),
};
