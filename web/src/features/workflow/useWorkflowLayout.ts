import { useMemo } from "react";

import type {
  WorkflowArtifactRef,
  WorkflowDefinition,
  WorkflowDriftFinding,
  WorkflowGraph,
  WorkflowRegistryEntry,
  WorkflowStatus,
} from "@/lib/api/endpoints/workflow";

export type TransitionKind = "forward" | "return" | "terminal" | "side";

export interface GateCluster {
  id: string;
  statusId: string;
  validators: WorkflowRegistryEntry[];
  promptChecks: WorkflowRegistryEntry[];
  blocking: boolean;
}

export interface JitPromptMarker {
  id: string;
  statusId: string;
  prompt: WorkflowRegistryEntry;
}

export interface ArtifactMarker {
  id: string;
  statusId: string;
  direction: "produces" | "consumes";
  artifact: WorkflowArtifactRef;
}

export interface TransitionRoute {
  id: string;
  from: string;
  to: string | null;
  kind: TransitionKind;
  label: string;
}

export interface TerritoryStatus {
  status: WorkflowStatus;
  index: number;
  complexity: number;
  width: number;
  incoming: number;
  outgoing: number;
  gate: GateCluster | null;
  jitPrompts: JitPromptMarker[];
  artifacts: ArtifactMarker[];
  drift: WorkflowDriftFinding[];
}

export interface WorkflowTerritory {
  workflow: WorkflowDefinition;
  statuses: TerritoryStatus[];
  transitions: TransitionRoute[];
  drift: WorkflowDriftFinding[];
}

const MIN_STATUS_WIDTH = 220;
const MAX_STATUS_WIDTH = 390;
const COMPLEXITY_STEP = 22;

export function buildWorkflowTerritory(
  graph: WorkflowGraph,
  workflowId?: string,
): WorkflowTerritory | null {
  const workflows = graph.workflows ?? [];
  const workflow =
    (workflowId ? workflows.find((wf) => wf.id === workflowId) : workflows[0]) ?? null;
  if (!workflow) return null;

  const registry = graph.registry ?? { validators: [], jit_prompts: [], prompt_checks: [] };
  const driftFindings = graph.drift?.findings ?? [];
  const statuses = workflow.statuses ?? [];
  const validatorsById = byId(registry.validators ?? []);
  const promptsById = byId(registry.jit_prompts ?? []);
  const promptChecksById = byId(registry.prompt_checks ?? []);
  const statusIndex = new Map(statuses.map((status, index) => [status.id, index]));
  const transitions = buildTransitions(workflow, statusIndex);
  const incoming = countBy(transitions.map((route) => route.to).filter(Boolean) as string[]);
  const outgoing = countBy(transitions.map((route) => route.from));
  const driftByStatus = groupDrift(driftFindings, workflow.id);

  const territoryStatuses = statuses.map((status, index) => {
    const next = status.next ?? ({ kind: "terminal" } as const);
    const validatorIds = status.validators ?? [];
    const promptCheckIds = status.prompt_checks ?? [];
    const jitPromptIds = status.jit_prompts ?? [];
    const artifactRefs = status.artifacts ?? { produces: [], consumes: [] };
    const gate = buildGateCluster(status, validatorsById, promptChecksById);
    const jitPrompts = jitPromptIds.map((id) => ({
      id: `${status.id}:jit:${id}`,
      statusId: status.id,
      prompt: entryForStatus(promptsById, id, status.id),
    }));
    const artifacts = [
      ...(artifactRefs.produces ?? []).map((artifact) => ({
        id: `${status.id}:produces:${artifact.id}`,
        statusId: status.id,
        direction: "produces" as const,
        artifact,
      })),
      ...(artifactRefs.consumes ?? []).map((artifact) => ({
        id: `${status.id}:consumes:${artifact.id}`,
        statusId: status.id,
        direction: "consumes" as const,
        artifact,
      })),
    ];
    const branchPressure = next.kind === "conditional" ? next.branches.length : 0;
    const complexity =
      validatorIds.length +
      promptCheckIds.length +
      jitPromptIds.length +
      artifacts.length +
      branchPressure +
      (incoming.get(status.id) ?? 0) +
      (outgoing.get(status.id) ?? 0);

    return {
      status,
      index,
      complexity,
      width: clamp(
        MIN_STATUS_WIDTH + complexity * COMPLEXITY_STEP,
        MIN_STATUS_WIDTH,
        MAX_STATUS_WIDTH,
      ),
      incoming: incoming.get(status.id) ?? 0,
      outgoing: outgoing.get(status.id) ?? 0,
      gate,
      jitPrompts,
      artifacts,
      drift: driftByStatus.get(status.id) ?? [],
    };
  });

  return { workflow, statuses: territoryStatuses, transitions, drift: driftFindings };
}

function buildGateCluster(
  status: WorkflowStatus,
  validatorsById: Map<string, WorkflowRegistryEntry>,
  promptChecksById: Map<string, WorkflowRegistryEntry>,
): GateCluster | null {
  const validators = (status.validators ?? []).map((id) =>
    entryForStatus(validatorsById, id, status.id),
  );
  const promptChecks = (status.prompt_checks ?? []).map((id) =>
    entryForStatus(promptChecksById, id, status.id),
  );
  if (validators.length === 0 && promptChecks.length === 0) return null;
  return {
    id: `${status.id}:gate`,
    statusId: status.id,
    validators,
    promptChecks,
    blocking: [...validators, ...promptChecks].some((entry) => entry.blocking !== false),
  };
}

function buildTransitions(
  workflow: WorkflowDefinition,
  statusIndex: Map<string, number>,
): TransitionRoute[] {
  const routes: TransitionRoute[] = [];
  for (const status of workflow.statuses ?? []) {
    const next = status.next ?? ({ kind: "terminal" } as const);
    if (next.kind === "terminal") {
      routes.push({
        id: `${status.id}:terminal`,
        from: status.id,
        to: null,
        kind: "terminal",
        label: "terminal",
      });
      continue;
    }
    if (next.kind === "single") {
      routes.push({
        id: `${status.id}:to:${next.single}`,
        from: status.id,
        to: next.single,
        kind: classifyRoute(status.id, next.single, statusIndex),
        label: next.single,
      });
      continue;
    }
    for (const branch of next.branches) {
      const target = "else" in branch ? branch.else : branch.then;
      const condition = "else" in branch ? "else" : branch.if;
      routes.push({
        id: `${status.id}:branch:${condition}:${target}`,
        from: status.id,
        to: target,
        kind: classifyRoute(status.id, target, statusIndex),
        label: condition,
      });
    }
  }
  return routes;
}

function classifyRoute(from: string, to: string, statusIndex: Map<string, number>): TransitionKind {
  const fromIndex = statusIndex.get(from);
  const toIndex = statusIndex.get(to);
  if (fromIndex === undefined || toIndex === undefined) return "side";
  if (toIndex > fromIndex) return "forward";
  if (toIndex < fromIndex) return "return";
  return "side";
}

function byId(entries: WorkflowRegistryEntry[]): Map<string, WorkflowRegistryEntry> {
  return new Map(entries.map((entry) => [entry.id, entry]));
}

function entryForStatus(
  entries: Map<string, WorkflowRegistryEntry>,
  id: string,
  statusId: string,
): WorkflowRegistryEntry {
  return { ...(entries.get(id) ?? fallbackEntry(id)), status: statusId };
}

function fallbackEntry(id: string): WorkflowRegistryEntry {
  return { id, label: id };
}

function countBy(values: string[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  return counts;
}

function groupDrift(
  findings: WorkflowDriftFinding[],
  workflowId: string,
): Map<string, WorkflowDriftFinding[]> {
  const grouped = new Map<string, WorkflowDriftFinding[]>();
  for (const finding of findings) {
    if (finding.workflow !== workflowId || !finding.status) continue;
    const bucket = grouped.get(finding.status) ?? [];
    bucket.push(finding);
    grouped.set(finding.status, bucket);
  }
  return grouped;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function useWorkflowTerritory(
  graph: WorkflowGraph | undefined,
  workflowId?: string,
): WorkflowTerritory | null {
  return useMemo(
    () => (graph ? buildWorkflowTerritory(graph, workflowId) : null),
    [graph, workflowId],
  );
}
