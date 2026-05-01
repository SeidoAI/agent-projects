import { useQuery } from "@tanstack/react-query";

import { pmRoleHeaders } from "@/lib/role";
import { ApiError, apiGet } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

/**
 * Typed client for `/api/workflow` (Strand Y).
 *
 * The endpoint may not be live yet at S1-merge; consumers should treat
 * `data === undefined` as "no graph available, render empty
 * placeholders" and the typed shape is the contract once Strand Y
 * lands. See spec §2.1 for the response payload.
 */
export interface WorkflowStation {
  id: string;
  n: number;
  label: string;
  desc: string;
}

export interface WorkflowValidator {
  id: string;
  kind: "gate" | "jit_prompt";
  name: string;
  checks?: string;
  fires_on_station: string;
  fires_on_event?: string;
  blocks?: boolean;
  prompt_revealed?: string | null;
  prompt_redacted?: string | null;
  wired_to?: string[];
}

export interface WorkflowConnector {
  id: string;
  name: string;
  data?: string;
  wired_to_station?: string;
  wired_from_station?: string;
}

export interface WorkflowArtifact {
  id: string;
  label: string;
  produced_by: string;
  consumed_by: string | null;
}

/**
 * KUI-125 — workflow.yaml-derived definition for the Workflow Map.
 *
 * One entry per declared workflow (`coding-session`, `pm-review`,
 * future workflows). Stations carry the typed `next:` shape (single
 * id / conditional branches / terminal) so the UI can render the
 * full directed-cyclic graph the v0.9 substrate exposes.
 */
export type WorkflowYamlNext =
  | { kind: "single"; single: string }
  | { kind: "conditional"; branches: WorkflowYamlBranch[] }
  | { kind: "terminal" };

export type WorkflowYamlBranch = { if: string; then: string } | { else: string };

export interface WorkflowYamlStation {
  id: string;
  next: WorkflowYamlNext;
  validators: string[];
  jit_prompts: string[];
  prompt_checks: string[];
}

export interface WorkflowYamlDefinition {
  id: string;
  actor: string;
  trigger: string;
  stations: WorkflowYamlStation[];
}

export interface WorkflowGraph {
  project_id: string;
  lifecycle: { stations: WorkflowStation[] };
  validators: WorkflowValidator[];
  jit_prompts: WorkflowValidator[];
  connectors: { sources: WorkflowConnector[]; sinks: WorkflowConnector[] };
  artifacts: WorkflowArtifact[];
  /** v0.9 — workflow.yaml-derived workflow definitions (KUI-125). */
  workflows?: WorkflowYamlDefinition[];
}

export const workflowApi = {
  /**
   * GET the orchestration graph for a project.
   *
   * `pmMode` toggles the `X-Tripwire-Role: pm` header so the
   * server fills `jit_prompts[*].prompt_revealed` with the
   * unredacted body (otherwise it returns `null`). The role gate
   * is a semantic separation, not auth — see `role_gate.py`.
   */
  get: (pid: string, opts?: { pmMode?: boolean }) =>
    apiGet<WorkflowGraph>(`/api/projects/${encodeURIComponent(pid)}/workflow`, {
      headers: pmRoleHeaders(Boolean(opts?.pmMode)),
    }),
};

/** Polling floor for the workflow query.
 *
 * The workflow graph is built from registries at request time —
 * a Python-side validator/JIT prompt registration changes the
 * payload but doesn't fire any of the existing `file_changed`
 * entity types. Polling at 30s is the cheap floor that keeps
 * the AC#3 "auto-updates when backend registers a new entity"
 * promise honest even without a matching WS event; the WS
 * dispatcher in `eventHandlers.ts` invalidates the workflow key
 * on any `file_changed` for the fast path on top.
 *
 * Exported for tests so the hook contract is asserted explicitly
 * (a future PR shouldn't be able to silently drop polling without
 * the test failing).
 */
export const WORKFLOW_REFETCH_MS = 30_000;

export function useWorkflow(pid: string, opts?: { pmMode?: boolean }) {
  const pmMode = Boolean(opts?.pmMode);
  return useQuery<WorkflowGraph>({
    // PM-mode payload differs from default (JIT prompt
    // bodies revealed); cache them under separate keys so toggling
    // role doesn't return a stale redacted graph.
    queryKey: [...queryKeys.workflow(pid), { pmMode }] as const,
    queryFn: () => workflowApi.get(pid, { pmMode }),
    staleTime: staleTime.default,
    refetchInterval: WORKFLOW_REFETCH_MS,
    // The endpoint is additive — until Strand Y ships, the backend
    // returns 404. Don't retry on a clean 404; surface as undefined to
    // the consumer so the Dashboard renders the empty wire shape.
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 2;
    },
  });
}
