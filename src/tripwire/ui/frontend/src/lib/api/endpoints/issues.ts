import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Reference as MarkdownReference } from "@/components/markdown/remark-tripwire-refs";
import { apiGet, apiPatch, apiPost } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

export type IssueReferenceKind = "node" | "issue" | "session" | "dangling";

export interface IssueReference {
  ref: string;
  resolves_as: IssueReferenceKind;
  is_stale: boolean;
}

// Aliases for code paths using the shorter names from PR #21 (`Reference`, `ReferenceKind`).
export type ReferenceKind = IssueReferenceKind;
export type Reference = IssueReference;

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
  created_at: string | null;
  updated_at: string | null;
}

export interface IssueDetail extends IssueSummary {
  body: string;
  refs: IssueReference[];
}

export interface IssuePatchBody {
  status?: string;
  priority?: string;
  labels?: string[];
  agent?: string | null;
}

// Alias for code paths using PR #21's shorter name.
export type IssuePatch = IssuePatchBody;

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

export interface ValidationFinding {
  code: string;
  severity: "error" | "warning" | "fixed" | "info";
  message: string;
  file?: string | null;
  line?: number | null;
  [key: string]: unknown;
}

export interface ValidationSummary {
  errors: number;
  warnings: number;
  fixed: number;
  cache_rebuilt?: boolean;
  duration_ms?: number;
}

export type ValidationCategoryCounts = {
  errors: number;
  warnings: number;
  fixed: number;
};

export interface IssueValidationReport {
  version: number;
  exit_code: number;
  summary: ValidationSummary;
  categories: Record<string, ValidationCategoryCounts>;
  errors: ValidationFinding[];
  warnings: ValidationFinding[];
  fixed: ValidationFinding[];
}

export const issuesApi = {
  list: (pid: string, filters?: IssueFilterParams) =>
    apiGet<IssueSummary[]>(
      `/api/projects/${encodeURIComponent(pid)}/issues${buildQuery(filters)}`,
    ),
  get: (pid: string, key: string) =>
    apiGet<IssueDetail>(
      `/api/projects/${encodeURIComponent(pid)}/issues/${encodeURIComponent(key)}`,
    ),
  patch: (pid: string, key: string, body: IssuePatchBody) =>
    apiPatch<IssueDetail>(
      `/api/projects/${encodeURIComponent(pid)}/issues/${encodeURIComponent(key)}`,
      body,
    ),
  validate: (pid: string, key: string) =>
    apiPost<IssueValidationReport>(
      `/api/projects/${encodeURIComponent(pid)}/issues/${encodeURIComponent(key)}/validate`,
    ),
};

export function useIssue(pid: string, key: string) {
  return useQuery({
    queryKey: queryKeys.issue(pid, key),
    queryFn: () => issuesApi.get(pid, key),
    staleTime: staleTime.default,
  });
}

export function useIssuePatch(pid: string, key: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: IssuePatchBody) => issuesApi.patch(pid, key, body),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.issue(pid, key), data);
      qc.invalidateQueries({ queryKey: queryKeys.issues(pid) });
    },
  });
}

export function useIssueValidate(pid: string, key: string) {
  return useMutation({
    mutationFn: () => issuesApi.validate(pid, key),
  });
}

/** Convert the API's `{ref, resolves_as, is_stale}` into MarkdownBody's
 * `{token, resolves_as, is_stale}` shape. */
export function toMarkdownRefs(refs: IssueReference[] | undefined): MarkdownReference[] {
  if (!refs) return [];
  return refs.map((r) => ({
    token: r.ref,
    resolves_as: r.resolves_as,
    is_stale: r.is_stale,
  }));
}
