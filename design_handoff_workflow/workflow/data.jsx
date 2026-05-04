// workflow/data.jsx — canonical workflow definitions (all 6 workflows from workflow.yaml.j2)
// Plus registry metadata for controls and skills. The map renderers consume this.

const ACTOR_COLOR = {
  'pm-agent':     '#8a5a16',
  'coding-agent': '#176b50',
  'code':         '#315f7c',
};
const ACTOR_LABEL = {
  'pm-agent':     'PM',
  'coding-agent': 'CODING',
  'code':         'CODE',
};

// Status descriptions. Kept short — territory labels, not prose.
const STATUS_BLURBS = {
  // coding-session
  planned:   'intent shaped',
  queued:    'plan committed',
  executing: 'agent working',
  in_review: 'pm reviewing',
  verified:  'review approved',
  completed: 'session signed',
  // pm-session-management
  inspect:   'check readiness',
  create:    'draft session',
  queue:     'commit to queue',
  spawn:     'launch agent',
  monitor:   'observe runtime',
  review:    'review work',
  complete:  'finalize',
  // pm-scoping
  intake:    'capture intent',
  draft:     'draft scope',
  validate:  'validate',
  publish:   'publish scope',
  // pm-triage
  classify:  'classify item',
  act:       'take action',
  close:     'close ticket',
  // pm-incremental-update
  edit:      'apply edit',
  // project-maintenance
  report:    'report status',
};

const WORKFLOWS = [
  // ─── 01 coding-session ────────────────────────────────────────────
  {
    id: 'coding-session',
    family: 'coding',
    actor: 'coding-agent',
    trigger: 'session.spawn',
    label: 'coding-session',
    blurb: 'one session: plan, execute, review, ship.',
    statuses: [
      { id:'planned',   blurb:STATUS_BLURBS.planned,   artifacts:{consumes:[{id:'issue-brief',label:'issue brief'}], produces:[]} },
      { id:'queued',    blurb:STATUS_BLURBS.queued,    artifacts:{consumes:[], produces:[{id:'plan',label:'plan.md'}]} },
      { id:'executing', blurb:STATUS_BLURBS.executing, artifacts:{consumes:[{id:'plan',label:'plan.md'}], produces:[{id:'diff',label:'implementation diff'}]} },
      { id:'in_review', blurb:STATUS_BLURBS.in_review, artifacts:{consumes:[{id:'diff',label:'implementation diff'}], produces:[{id:'review-notes',label:'review notes'}]} },
      { id:'verified',  blurb:STATUS_BLURBS.verified,  artifacts:{consumes:[{id:'review-notes',label:'review notes'}], produces:[]} },
      { id:'completed', blurb:STATUS_BLURBS.completed, terminal:true, artifacts:{consumes:[], produces:[{id:'session-signature',label:'session signature'}]} },
    ],
    routes: [
      { id:'session-create', actor:'pm-agent', command:'pm-session-create', from:'source:issue', to:'planned', kind:'forward', label:'create session',
        controls:{prompt_checks:['pm-session-create'], validators:['v_workflow_well_formed','v_uuid_present','v_id_format','v_enum_values','v_id_collisions','v_sequence_drift','v_timestamps'], jit_prompts:[]},
        skills:['project-manager'], emits:{artifacts:[{id:'session-yaml',label:'session.yaml'}],events:[]} },
      { id:'planned-to-queued', actor:'pm-agent', command:'pm-session-queue', from:'planned', to:'queued', kind:'forward', label:'queue session',
        controls:{prompt_checks:['pm-session-queue'], validators:['v_session_issue_coherence','v_issue_session_status_compatibility','v_reference_integrity','v_bidirectional_related','v_no_stale_pins','v_status_transitions'], jit_prompts:[]},
        skills:['project-manager'], emits:{artifacts:[{id:'plan',label:'plan.md'}]} },
      { id:'queued-to-executing', actor:'pm-agent', command:'pm-session-spawn', from:'queued', to:'executing', kind:'forward', label:'spawn coding agent',
        controls:{prompt_checks:['pm-session-spawn'], validators:['v_issue_body_structure','v_project_standards','v_freshness','v_comment_provenance','v_handoff_artifact','v_worktree_paths_unique','v_no_orphan_proj_branches','v_stale_concept','v_concept_name_prose','v_semantic_coverage','v_mega_issue','v_node_ratio','v_done_implies_session_completed'], jit_prompts:[]},
        skills:['project-manager','backend-development','agent-messaging'], emits:{events:['session.spawn']} },
      { id:'executing-to-review', actor:'coding-agent', from:'executing', to:'in_review', kind:'forward', label:'submit for review', command:null,
        controls:{prompt_checks:[], validators:['v_manifest_schema','v_manifest_phase_ownership_consistent','v_artifact_presence','v_coverage_heuristics','v_phase_requirements','v_quality_consistency','v_issue_artifact_presence'], jit_prompts:[]},
        skills:['backend-development','agent-messaging'], emits:{artifacts:[{id:'diff',label:'implementation diff'}]} },
      { id:'review-approved', actor:'pm-agent', command:'pm-session-review', from:'in_review', to:'verified', kind:'forward', label:'approve review',
        controls:{prompt_checks:['pm-session-review'], validators:[], jit_prompts:[]}, skills:['project-manager','verification'],
        emits:{artifacts:[{id:'review-notes',label:'review notes'}]} },
      { id:'review-changes-requested', actor:'pm-agent', command:'pm-session-review', from:'in_review', to:'executing', kind:'return', label:'request changes',
        controls:{prompt_checks:[], validators:[], jit_prompts:[]}, skills:['project-manager','verification','backend-development'],
        emits:{comments:['changes-requested']} },
      { id:'verified-to-completed', actor:'pm-agent', command:'pm-session-complete', from:'verified', to:'completed', kind:'forward', label:'complete session',
        controls:{prompt_checks:['pm-session-complete'], validators:['v_pm_response_covers_self_review','v_pm_response_followups_resolve','v_done_implies_issue_artifacts_on_main','v_self_review_implies_pm_response'], jit_prompts:['self-review','phase-transition','followups-not-filed','stopped-to-ask','write-count','cost-ceiling']},
        skills:['project-manager','verification'], emits:{artifacts:[{id:'session-signature',label:'session signature'}]} },
      { id:'completed-to-merged', actor:'code', from:'completed', to:'sink:main', kind:'terminal', label:'merge to main',
        controls:{prompt_checks:[], validators:[], jit_prompts:[]}, skills:[], emits:{events:['pr.merged']} },
    ],
  },
  // ─── 02 pm-session-management ──────────────────────────────────────
  {
    id: 'pm-session-management', family:'pm', actor:'pm-agent', trigger:'command.pm-session-create',
    label:'session-management', blurb:"PM's lifecycle for handling sessions.",
    statuses: [
      { id:'inspect', blurb:STATUS_BLURBS.inspect },
      { id:'create',  blurb:STATUS_BLURBS.create },
      { id:'queue',   blurb:STATUS_BLURBS.queue },
      { id:'spawn',   blurb:STATUS_BLURBS.spawn },
      { id:'monitor', blurb:STATUS_BLURBS.monitor },
      { id:'review',  blurb:STATUS_BLURBS.review },
      { id:'complete',blurb:STATUS_BLURBS.complete, terminal:true },
    ],
    routes: [
      { id:'inspect-readiness', actor:'pm-agent', command:'pm-session-check', from:'source:session-request', to:'inspect', kind:'forward', label:'inspect readiness', skills:['project-manager'] },
      { id:'create-session',    actor:'pm-agent', command:'pm-session-create', from:'inspect', to:'create',  kind:'forward', label:'create',  skills:['project-manager'] },
      { id:'queue-session',     actor:'pm-agent', command:'pm-session-queue',  from:'create',  to:'queue',   kind:'forward', label:'queue',   skills:['project-manager'] },
      { id:'spawn-session',     actor:'pm-agent', command:'pm-session-spawn',  from:'queue',   to:'spawn',   kind:'forward', label:'spawn',   skills:['project-manager','backend-development'] },
      { id:'monitor-session',   actor:'pm-agent', command:'pm-session-monitor',from:'spawn',   to:'monitor', kind:'forward', label:'monitor', skills:['project-manager'] },
      { id:'review-session',    actor:'pm-agent', command:'pm-session-review', from:'monitor', to:'review',  kind:'forward', label:'review',  skills:['project-manager','verification'] },
      { id:'review-rework-loop',actor:'pm-agent', command:'pm-session-review', from:'review',  to:'monitor', kind:'return',  label:'rework',  skills:['project-manager','verification'] },
      { id:'complete-session',  actor:'pm-agent', command:'pm-session-complete',from:'review', to:'complete',kind:'forward', label:'complete',skills:['project-manager','verification'] },
    ],
  },
  // ─── 03 pm-scoping ─────────────────────────────────────────────────
  {
    id:'pm-scoping', family:'pm', actor:'pm-agent', trigger:'command.pm-scope',
    label:'scoping', blurb:'turn intent into scoped work.',
    statuses: [
      { id:'intake',   blurb:STATUS_BLURBS.intake },
      { id:'draft',    blurb:STATUS_BLURBS.draft },
      { id:'validate', blurb:STATUS_BLURBS.validate },
      { id:'publish',  blurb:STATUS_BLURBS.publish, terminal:true },
    ],
    routes: [
      { id:'scope-intake', actor:'pm-agent', command:'pm-scope', from:'source:intent', to:'intake', kind:'forward', label:'intake intent', skills:['project-manager'] },
      { id:'draft-scope',  actor:'pm-agent', command:'pm-scope', from:'intake', to:'draft', kind:'forward', label:'draft artifacts', skills:['project-manager'] },
      { id:'validate-scope', actor:'code', command:'pm-validate', from:'draft', to:'validate', kind:'forward', label:'validate scope', skills:['project-manager'] },
      { id:'scope-gap-loop', actor:'pm-agent', command:'pm-rescope', from:'validate', to:'draft', kind:'return', label:'close gaps', skills:['project-manager'] },
      { id:'publish-scope', actor:'pm-agent', command:'pm-scope', from:'validate', to:'publish', kind:'forward', label:'publish',
        emits:{artifacts:[{id:'scoped-issues',label:'scoped issues'}]} },
    ],
  },
  // ─── 04 pm-triage ──────────────────────────────────────────────────
  {
    id:'pm-triage', family:'pm', actor:'pm-agent', trigger:'command.pm-triage',
    label:'triage', blurb:'inbox in, action out.',
    statuses: [
      { id:'intake',   blurb:STATUS_BLURBS.intake },
      { id:'classify', blurb:STATUS_BLURBS.classify },
      { id:'act',      blurb:STATUS_BLURBS.act },
      { id:'close',    blurb:STATUS_BLURBS.close, terminal:true },
    ],
    routes: [
      { id:'triage-intake',  actor:'pm-agent', command:'pm-triage', from:'source:inbox', to:'intake', kind:'forward', label:'intake', skills:['project-manager','agent-messaging'] },
      { id:'classify-item',  actor:'pm-agent', command:'pm-triage', from:'intake', to:'classify', kind:'forward', label:'classify', skills:['project-manager'] },
      { id:'act-on-item',    actor:'pm-agent', command:'pm-edit',   from:'classify', to:'act', kind:'forward', label:'act', skills:['project-manager'] },
      { id:'close-triage',   actor:'pm-agent', command:'pm-triage', from:'act', to:'close', kind:'forward', label:'close', skills:[] },
    ],
  },
  // ─── 05 pm-incremental-update ──────────────────────────────────────
  {
    id:'pm-incremental-update', family:'pm', actor:'pm-agent', trigger:'command.pm-edit',
    label:'incremental-update', blurb:'small edits, validated, then published.',
    statuses: [
      { id:'inspect',  blurb:STATUS_BLURBS.inspect },
      { id:'edit',     blurb:STATUS_BLURBS.edit },
      { id:'validate', blurb:STATUS_BLURBS.validate },
      { id:'publish',  blurb:STATUS_BLURBS.publish, terminal:true },
    ],
    routes: [
      { id:'inspect-update', actor:'pm-agent', command:'pm-edit', from:'source:change-request', to:'inspect', kind:'forward', label:'inspect', skills:['project-manager'] },
      { id:'apply-update',   actor:'pm-agent', command:'pm-edit', from:'inspect', to:'edit', kind:'forward', label:'edit', skills:['project-manager'] },
      { id:'validate-update',actor:'code',     command:'pm-validate', from:'edit', to:'validate', kind:'forward', label:'validate' },
      { id:'fix-update-loop',actor:'pm-agent', command:'pm-edit', from:'validate', to:'edit', kind:'return', label:'fix', skills:['project-manager'] },
      { id:'publish-update', actor:'pm-agent', command:'pm-issue-close', from:'validate', to:'publish', kind:'forward', label:'publish', skills:['project-manager'] },
    ],
  },
  // ─── 06 project-maintenance ────────────────────────────────────────
  {
    id:'project-maintenance', family:'maintenance', actor:'pm-agent', trigger:'command.pm-status',
    label:'maintenance', blurb:'periodic project sweep.',
    statuses: [
      { id:'inspect', blurb:STATUS_BLURBS.inspect },
      { id:'report',  blurb:STATUS_BLURBS.report, terminal:true },
    ],
    routes: [
      { id:'status-report',  actor:'pm-agent', command:'pm-status',  from:'source:project', to:'inspect', kind:'forward', label:'status', skills:['project-manager'] },
      { id:'agenda-report',  actor:'pm-agent', command:'pm-agenda',  from:'inspect', to:'report', kind:'forward', label:'agenda', skills:['project-manager'] },
      { id:'graph-report',   actor:'pm-agent', command:'pm-graph',   from:'inspect', to:'report', kind:'side',    label:'graph',  skills:['project-manager'] },
      { id:'validate-report',actor:'code',     command:'pm-validate',from:'inspect', to:'report', kind:'side',    label:'validate' },
      { id:'sync-project',   actor:'code',     command:'pm-project-sync', from:'inspect', to:'report', kind:'side', label:'sync' },
    ],
  },
];

// Normalize controls/emits with defaults
WORKFLOWS.forEach(wf => {
  wf.routes.forEach(r => {
    r.controls = r.controls || { validators:[], prompt_checks:[], jit_prompts:[] };
    r.controls.validators    = r.controls.validators || [];
    r.controls.prompt_checks = r.controls.prompt_checks || [];
    r.controls.jit_prompts   = r.controls.jit_prompts || [];
    r.skills = r.skills || [];
    r.emits  = r.emits  || {};
    r.emits.artifacts = r.emits.artifacts || [];
    r.emits.events    = r.emits.events    || [];
    r.emits.comments  = r.emits.comments  || [];
  });
  wf.statuses.forEach(s => {
    s.artifacts = s.artifacts || { produces:[], consumes:[] };
  });
});

// Skill descriptions
const SKILLS = {
  'project-manager':     { label:'project-manager',     blurb:'PM expertise: triage, scoping, review.' },
  'backend-development': { label:'backend-development', blurb:'how to write & ship backend code.' },
  'agent-messaging':     { label:'agent-messaging',     blurb:'how to communicate runtime status.' },
  'verification':        { label:'verification',        blurb:'how to verify work meets spec.' },
};

// Static drift for the demo (definition-only).
const DRIFT = [];

Object.assign(window, {
  WORKFLOWS, ACTOR_COLOR, ACTOR_LABEL, SKILLS, DRIFT, STATUS_BLURBS,
});
