/**
 * Typed fixture builders mirroring the API contract from
 * `src/lib/api/endpoints/*`. Each builder accepts an optional
 * `overrides` object so tests can express "the standard X, except
 * status=blocked".
 *
 * Use these for both MSW handler responses and `qc.setQueryData`
 * cache priming — they are the single source of truth for fixture
 * shape across the test suite.
 */
import type { ArtifactManifest, ArtifactSpec, ArtifactStatus } from "@/lib/api/endpoints/artifacts";
import type { EnumDescriptor } from "@/lib/api/endpoints/enums";
import type { ReactFlowGraph } from "@/lib/api/endpoints/graph";
import type { IssueDetail, IssueSummary } from "@/lib/api/endpoints/issues";
import type {
  NodeDetail,
  NodeSummary,
  Referrer,
  ReverseRefsResult,
} from "@/lib/api/endpoints/nodes";
import type { ProjectDetail } from "@/lib/api/endpoints/project";
import type { RepoBinding, SessionDetail, SessionSummary } from "@/lib/api/endpoints/sessions";

export const FIXTURE_PROJECT_ID = "p1";

export function makeProject(overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    id: FIXTURE_PROJECT_ID,
    name: "Demo project",
    key_prefix: "DEMO",
    phase: "executing",
    dir: "/tmp/demo",
    repos: { "SeidoAI/tripwire": { local: null, github: null } },
    status_transitions: {
      todo: ["in_progress"],
      in_progress: ["in_review", "blocked"],
      in_review: ["done", "in_progress"],
      blocked: ["in_progress"],
      done: [],
    },
    ...overrides,
  };
}

export function makeIssueSummary(overrides: Partial<IssueSummary> = {}): IssueSummary {
  return {
    id: "DEMO-1",
    title: "Sample issue",
    status: "todo",
    priority: "medium",
    executor: "ai",
    verifier: "required",
    kind: null,
    agent: null,
    labels: [],
    parent: null,
    repo: null,
    blocked_by: [],
    is_blocked: false,
    is_epic: false,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

export function makeIssueDetail(overrides: Partial<IssueDetail> = {}): IssueDetail {
  return {
    ...makeIssueSummary(),
    body: "",
    refs: [],
    ...overrides,
  };
}

export function makeIssueStatusEnum(): EnumDescriptor {
  return {
    name: "issue_status",
    values: [
      { value: "todo", label: "To do", color: "#888", description: null },
      { value: "doing", label: "Doing", color: "#0af", description: null },
      { value: "done", label: "Done", color: "#0f0", description: null },
    ],
  };
}

export function makeSessionSummary(overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    id: "sess-a",
    name: "Session A",
    agent: "frontend-coder",
    status: "active",
    issues: [],
    estimated_size: null,
    blocked_by_sessions: [],
    repos: [],
    current_state: null,
    re_engagement_count: 0,
    task_progress: { done: 0, total: 0 },
    ...overrides,
  };
}

export function makeSessionDetail(overrides: Partial<SessionDetail> = {}): SessionDetail {
  return {
    ...makeSessionSummary(),
    plan_md: "# Plan\n",
    key_files: [],
    docs: [],
    grouping_rationale: null,
    engagements: [],
    artifact_status: {},
    ...overrides,
  };
}

export function makeNodeSummary(overrides: Partial<NodeSummary> = {}): NodeSummary {
  return {
    id: "demo-node",
    type: "concept",
    name: "Demo node",
    description: null,
    status: "active",
    tags: [],
    related: [],
    ref_count: 0,
    ...overrides,
  };
}

export function makeNodeDetail(overrides: Partial<NodeDetail> = {}): NodeDetail {
  return {
    ...makeNodeSummary(),
    body: "",
    source: null,
    is_stale: false,
    ...overrides,
  };
}

export function makeReverseRefs(overrides: Partial<ReverseRefsResult> = {}): ReverseRefsResult {
  return {
    node_id: "demo-node",
    referrers: [],
    ...overrides,
  };
}

/** Build N referrers — handy for paginator tests. */
export function makeReferrers(count: number, prefix = "DEMO"): Referrer[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `${prefix}-${i + 1}`,
    kind: "issue" as const,
  }));
}

export function makeRepoBinding(overrides: Partial<RepoBinding> = {}): RepoBinding {
  return {
    repo: "SeidoAI/tripwire",
    base_branch: "main",
    branch: null,
    pr_number: null,
    ...overrides,
  };
}

export function makeArtifactSpec(overrides: Partial<ArtifactSpec> = {}): ArtifactSpec {
  return {
    name: "plan",
    file: "plan.md",
    template: "plan",
    produced_at: "planning",
    produced_by: "pm",
    owned_by: null,
    required: true,
    approval_gate: false,
    ...overrides,
  };
}

/** Wrap an `ArtifactSpec` in an `ArtifactStatus` with sensible
 *  present-or-not defaults (size + mtime when present, both null
 *  otherwise). */
export function makeArtifactStatus(
  spec: ArtifactSpec,
  present: boolean,
  overrides: Partial<ArtifactStatus> = {},
): ArtifactStatus {
  return {
    spec,
    present,
    size_bytes: present ? 120 : null,
    last_modified: present ? "2026-04-24T00:00:00Z" : null,
    approval: null,
    ...overrides,
  };
}

export function makeEmptyGraph(): ReactFlowGraph {
  return {
    nodes: [],
    edges: [],
    meta: {
      kind: "concept",
      focus: null,
      upstream: false,
      downstream: false,
      depth: null,
      node_count: 0,
      edge_count: 0,
      orphans: [],
    },
  };
}

export function makeArtifactManifest(): ArtifactManifest {
  return { artifacts: [] };
}

export function makeArtifactStatuses(): ArtifactStatus[] {
  return [];
}
