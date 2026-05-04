// workflow/registry.jsx — control + JIT prompt + transition metadata
// Separate from data.jsx so the canonical workflow definitions stay clean.

// JIT prompts: standalone *nodes* placed in territory near the status
// they can fire in. Each entry says: which workflow, which status region
// it lives in, what it does.
const JIT_PROMPTS = {
  'self-review':        { label:'self-review',        blurb:'remind agent to review its own diff before submission.' },
  'phase-transition':   { label:'phase-transition',   blurb:'fire on phase change; recap context.' },
  'followups-not-filed':{ label:'followups-not-filed',blurb:'check that follow-ups were filed before completion.' },
  'stopped-to-ask':     { label:'stopped-to-ask',     blurb:'agent paused — surface the question.' },
  'write-count':        { label:'write-count',        blurb:'too many writes; suggest reflection.' },
  'cost-ceiling':       { label:'cost-ceiling',       blurb:'session approaching token budget.' },
};

// Where each JIT prompt anchors in the territory. (workflow, status)
const JIT_ANCHORS = [
  { id:'self-review',         workflow:'coding-session', status:'in_review' },
  { id:'phase-transition',    workflow:'coding-session', status:'executing' },
  { id:'followups-not-filed', workflow:'coding-session', status:'verified' },
  { id:'stopped-to-ask',      workflow:'coding-session', status:'executing' },
  { id:'write-count',         workflow:'coding-session', status:'executing' },
  { id:'cost-ceiling',        workflow:'coding-session', status:'executing' },
];

// Validator + prompt-check descriptions (terse — for the expanded gate list)
const VALIDATORS = {
  // workflow integrity
  v_workflow_well_formed:        'workflow.yaml parses & is well-formed',
  v_uuid_present:                'all entities have UUIDs',
  v_id_format:                   'IDs match expected format',
  v_enum_values:                 'enums are within allowed set',
  v_id_collisions:               'no duplicate IDs across the project',
  v_sequence_drift:              'sequence counters are contiguous',
  v_timestamps:                  'timestamps are present & ordered',
  // session→issue coherence
  v_session_issue_coherence:     'session matches its issue',
  v_issue_session_status_compatibility:'issue & session statuses agree',
  v_reference_integrity:         'cross-references resolve',
  v_bidirectional_related:       'related-pairs are bidirectional',
  v_no_stale_pins:               'pins point to live revisions',
  v_status_transitions:          'status transitions follow the lifecycle',
  // pre-spawn readiness
  v_issue_body_structure:        'issue body has the required sections',
  v_project_standards:           'project standards file is present',
  v_freshness:                   'inputs are fresh',
  v_comment_provenance:          'comments are attributed',
  v_handoff_artifact:            'handoff artifact is staged',
  v_worktree_paths_unique:       'worktree paths are unique',
  v_no_orphan_proj_branches:     'no orphan project branches',
  v_stale_concept:               'no stale concepts referenced',
  v_concept_name_prose:          'concept names appear in prose',
  v_semantic_coverage:           'concepts have semantic coverage',
  v_mega_issue:                  'issue is not too large to ship',
  v_node_ratio:                  'PM:concept ratio within bounds',
  v_done_implies_session_completed:'done issues match completed sessions',
  // execution review
  v_manifest_schema:             'manifest.yaml schema is valid',
  v_manifest_phase_ownership_consistent:'phases own non-overlapping work',
  v_artifact_presence:           'all expected artifacts present',
  v_coverage_heuristics:         'coverage heuristics within bounds',
  v_phase_requirements:          'each phase met its requirements',
  v_quality_consistency:         'quality signals are consistent',
  v_issue_artifact_presence:     'issue-level artifacts produced',
  // completion gates
  v_pm_response_covers_self_review:'pm responded to every self-review item',
  v_pm_response_followups_resolve:'follow-ups are resolved or filed',
  v_done_implies_issue_artifacts_on_main:'main has the issue artifacts',
  v_self_review_implies_pm_response:'self-review entries got pm responses',
};

const PROMPT_CHECKS = {
  'pm-session-create':   'PM creating session: scope/standards/handoff present?',
  'pm-session-queue':    'PM queueing: plan ready to spawn?',
  'pm-session-spawn':    'PM spawning: agent has all it needs?',
  'pm-session-review':   'PM reviewing: every self-review item answered?',
  'pm-session-complete': 'PM completing: artifacts on main, follow-ups filed?',
};

// Conditional skill loads: which skills are loaded *only* under conditions.
// Convention: a skill is conditional if `condition` is set; otherwise mandatory.
const CONDITIONAL_SKILLS = {
  // for coding-session execution: backend-development is conditional on scope
  'executing-to-review|backend-development':   'when scope touches backend',
  'executing-to-review|agent-messaging':       'when agent posts to chat',
  // pm review may load verification only when there is a self-review
  'review-approved|verification':              'when self-review present',
  'review-changes-requested|verification':     'when self-review present',
};

// Branch metadata — when a transition is actually a *decision*, list its
// alternative outcomes. Renderers can choose to render this as a diamond.
const BRANCHES = {
  // PM-session-review can either approve (→verified) or request changes (→executing)
  'review-approved': { branchOf:'pm-session-review', outcome:'approve' },
  'review-changes-requested': { branchOf:'pm-session-review', outcome:'request changes' },
  // pm-scoping validate can pass or fail
  'publish-scope':   { branchOf:'pm-validate', outcome:'pass' },
  'scope-gap-loop':  { branchOf:'pm-validate', outcome:'gap' },
  // pm-incremental-update validate can pass or fail
  'publish-update':  { branchOf:'pm-validate', outcome:'pass' },
  'fix-update-loop': { branchOf:'pm-validate', outcome:'fix' },
};

// Helper: given a route, build its progressive-disclosure rows
const describeGateContents = (route) => {
  const rows = [];
  (route.controls?.validators || []).forEach(v =>
    rows.push({ kind:'validator', id:v, label:v.replace(/^v_/,''), blurb: VALIDATORS[v] || '' }));
  (route.controls?.prompt_checks || []).forEach(p =>
    rows.push({ kind:'prompt-check', id:p, label:p, blurb: PROMPT_CHECKS[p] || '' }));
  return rows;
};

// Helper: is a (route, skill) load conditional?
const skillCondition = (routeId, skill) => CONDITIONAL_SKILLS[`${routeId}|${skill}`] || null;

Object.assign(window, {
  JIT_PROMPTS, JIT_ANCHORS, VALIDATORS, PROMPT_CHECKS,
  CONDITIONAL_SKILLS, BRANCHES,
  describeGateContents, skillCondition,
});
