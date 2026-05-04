import { useQuery } from "@tanstack/react-query";

import { pmRoleHeaders } from "@/lib/role";
import { ApiError, apiGet } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

export type WorkflowNext =
  | { kind: "single"; single: string }
  | { kind: "conditional"; branches: WorkflowBranch[] }
  | { kind: "terminal" };

export type WorkflowBranch = { if: string; then: string } | { else: string };

export interface WorkflowArtifactRef {
  id: string;
  label: string;
  path?: string;
}

export interface WorkflowStatusArtifacts {
  produces: WorkflowArtifactRef[];
  consumes: WorkflowArtifactRef[];
}

export interface WorkflowWorkStep {
  id: string;
  actor: string;
  label: string;
  skills: string[];
}

export interface WorkflowCrossLink {
  workflow: string;
  status: string;
  label?: string | null;
  kind: "triggers" | "triggered_by";
  pm_subagent_dispatch?: boolean;
}

export interface WorkflowStatus {
  id: string;
  label?: string;
  description?: string;
  next: WorkflowNext;
  tripwires: string[];
  heuristics: string[];
  jit_prompts: string[];
  prompt_checks: string[];
  artifacts: WorkflowStatusArtifacts;
  work_steps: WorkflowWorkStep[];
  cross_links?: WorkflowCrossLink[];
}

export interface WorkflowRouteControls {
  tripwires: string[];
  heuristics: string[];
  jit_prompts: string[];
  prompt_checks: string[];
}

export interface WorkflowRouteEmits {
  artifacts: WorkflowArtifactRef[];
  events: string[];
  comments: string[];
  status_changes: string[];
}

export interface WorkflowRoute {
  id: string;
  workflow_id: string;
  actor: "pm-agent" | "coding-agent" | "code" | string;
  from: string;
  to: string;
  kind: "forward" | "return" | "loop" | "side" | "terminal" | string;
  label: string;
  trigger?: string | null;
  command?: string | null;
  controls: WorkflowRouteControls;
  signals: string[];
  skills: string[];
  emits: WorkflowRouteEmits;
}

export interface WorkflowDefinition {
  id: string;
  actor: string;
  trigger: string;
  brief_description?: string | null;
  statuses: WorkflowStatus[];
  routes: WorkflowRoute[];
}

export interface WorkflowRegistryEntry {
  id: string;
  label: string;
  description?: string;
  blocking?: boolean;
  workflow?: string;
  status?: string;
  route?: string;
  source?: string;
  fires_on_event?: string;
  prompt_revealed?: string | null;
  prompt_redacted?: string | null;
}

export interface WorkflowRegistry {
  tripwires: WorkflowRegistryEntry[];
  heuristics: WorkflowRegistryEntry[];
  jit_prompts: WorkflowRegistryEntry[];
  prompt_checks: WorkflowRegistryEntry[];
  commands: WorkflowRegistryEntry[];
  skills: WorkflowRegistryEntry[];
}

export interface WorkflowDriftFinding {
  source?: "definition" | "runtime" | string;
  code: string;
  workflow: string | null;
  instance?: string;
  status: string | null;
  severity: "error" | "warning";
  message: string;
}

export interface WorkflowDriftSummary {
  count: number;
  findings: WorkflowDriftFinding[];
}

export interface WorkflowGraph {
  project_id: string;
  workflows: WorkflowDefinition[];
  registry: WorkflowRegistry;
  drift: WorkflowDriftSummary;
}

export const workflowApi = {
  get: (pid: string, opts?: { pmMode?: boolean }) =>
    apiGet<WorkflowGraph>(`/api/projects/${encodeURIComponent(pid)}/workflow`, {
      headers: pmRoleHeaders(Boolean(opts?.pmMode)),
    }),
};

export const WORKFLOW_REFETCH_MS = 30_000;

export function useWorkflow(pid: string, opts?: { pmMode?: boolean }) {
  const pmMode = Boolean(opts?.pmMode);
  return useQuery<WorkflowGraph>({
    queryKey: [...queryKeys.workflow(pid), { pmMode }] as const,
    queryFn: () => workflowApi.get(pid, { pmMode }),
    staleTime: staleTime.default,
    refetchInterval: WORKFLOW_REFETCH_MS,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 2;
    },
  });
}
