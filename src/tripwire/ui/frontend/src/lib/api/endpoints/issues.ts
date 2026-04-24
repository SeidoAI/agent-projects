import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Reference as MarkdownReference } from "@/components/markdown/remark-tripwire-refs";
import { apiGet, apiPatch, apiPost } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

export type IssueReferenceKind = "node" | "issue" | "dangling";

export interface IssueReference {
  ref: string;
  resolves_as: IssueReferenceKind;
  is_stale: boolean;
}

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
  agent?: string;
}

export interface IssueValidationCode {
  code: string;
  count: number;
}

export interface IssueValidationReport {
  errors: number;
  warnings: number;
  info?: number;
  codes?: IssueValidationCode[];
  [key: string]: unknown;
}

export const issuesApi = {
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
