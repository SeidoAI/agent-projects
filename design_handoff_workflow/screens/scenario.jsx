// scenario.jsx — invented but plausible project for the screens
// Project: Marlin · Cross-border payments rails
//
// Aligned to the real tripwire data model:
//   - project.phase ∈ {scoping, scoped, executing, reviewing}, with phase_log
//   - sessions have: repos[], engagements[], orchestration overrides, artifact_overrides,
//     runtime_state {claude_session_id, langgraph_thread_id, workspace_volume}, current_state,
//     blocked_by_sessions, estimated_size, grouping_rationale, agent (= agent_def name)
//   - issues have: status (backlog/todo/in_progress/in_review/verified/done),
//     executor (ai/human/mixed), verifier (required/optional/none),
//     [[concept-node]] markdown refs, repo, base_branch, parent
//   - concept nodes use NodeType: endpoint/model/config/contract/decision/requirement/etc.,
//     status: active/planned/deprecated/stale
//   - agent_state during execution: investigating/planning/awaiting_plan_approval/implementing/...
//   - re_engagement_trigger when a session is restarted
//   - validation_completed events expose errors/warnings against concept refs
//   - artifacts have approval_gate; reviewer can approve or reject with feedback
//
// "Tripwire" is the project name, not an entity. The product's intervention surfaces are:
//     · validation errors (stale / unresolved [[concept]] refs)
//     · artifact approval rejections (PM rejects an artifact with feedback → re-engagement)
//     · PM reviews

window.SCENARIO = {
  org: { name: 'pearl', members: 14 },

  project: {
    id: 'marlin',
    name: 'Marlin',
    sub: 'cross-border payments rails',
    description:
      'real-time corridors for SGD/USD/EUR/MXN with FX hedging, idempotent payouts, ' +
      'and partner bank reconciliation. Replaces the legacy "globe" monolith.',
    phase: 'executing',
    phase_log: [
      { from: 'scoping',   to: 'scoped',    at: '2025-09-19T14:02:00Z', by: 'sasha k.' },
      { from: 'scoped',    to: 'executing', at: '2025-09-26T09:18:00Z', by: 'sasha k.' },
    ],
    repos: {
      'pearl-fi/marlin':       { local: '/Users/sasha/code/marlin',       github: 'https://github.com/pearl-fi/marlin' },
      'pearl-fi/marlin-infra': { local: '/Users/sasha/code/marlin-infra', github: 'https://github.com/pearl-fi/marlin-infra' },
    },
    pm: 'sasha k.',
    started: '2025-09-12',
  },

  // Issue status enum (real, from tripwire.models.enums.IssueStatus)
  issueStatusEnum: [
    { value: 'backlog',     label: 'backlog',     color: '#9a9285' },
    { value: 'todo',        label: 'todo',        color: '#3a342e' },
    { value: 'in_progress', label: 'in progress', color: '#c83d2e' },
    { value: 'in_review',   label: 'in review',   color: '#c8861f' },
    { value: 'verified',    label: 'verified',    color: '#436b4d' },
    { value: 'done',        label: 'done',        color: '#1a1815' },
  ],

  // Session status enum (real, abbreviated to states actually present in this scenario)
  sessionStatusEnum: [
    'planned', 'queued', 'executing', 'active',
    'waiting_for_ci', 'waiting_for_review', 'waiting_for_deploy',
    're_engaged', 'in_review', 'verified', 'completed', 'failed', 'paused', 'abandoned',
  ],

  // Lifecycle stations on the wire — derived from real session status transitions.
  // Used by the process map and the dashboard wire visualization.
  lifecycle: [
    { id: 'planned',  n: 1, label: 'planned',   desc: 'PM grouped issues into a session' },
    { id: 'queued',   n: 2, label: 'queued',    desc: 'awaiting an executor' },
    { id: 'spawned',  n: 3, label: 'spawned',   desc: 'container engaged · agent has context' },
    { id: 'executing',n: 4, label: 'executing', desc: 'agent runs · validators watch refs' },
    { id: 'review',   n: 5, label: 'in review', desc: 'artifact approval gate · PM review' },
    { id: 'verified', n: 6, label: 'verified',  desc: 'tests + verifier approve' },
    { id: 'completed',n: 7, label: 'completed', desc: 'merged · graph updated · session signed' },
  ],

  // Agents (real shape — agent_def files)
  agents: [
    { name: 'backend-coder',  description: 'edits server code · writes tests',           model: 'claude-sonnet-4' },
    { name: 'frontend-coder', description: 'edits React/TS · component-level changes',   model: 'claude-sonnet-4' },
    { name: 'pm-agent',       description: 'scopes issues · drafts plans · groups work', model: 'claude-sonnet-4' },
    { name: 'verifier',       description: 'reads developer.md · writes verified.md',    model: 'claude-sonnet-4' },
  ],

  // Concept graph nodes — using the real NodeType enum
  concepts: [
    { id: 'corridor',           label: 'corridor',           type: 'requirement', status: 'active',   refs: 18 },
    { id: 'payout-state',       label: 'payout-state',       type: 'model',       status: 'active',   refs: 16 },
    { id: 'idem-key',           label: 'idempotency-key',    type: 'contract',    status: 'active',   refs: 31 },
    { id: 'partner-bank',       label: 'partner-bank',       type: 'requirement', status: 'active',   refs: 12 },
    { id: 'fx-hedge',           label: 'fx-hedge',           type: 'requirement', status: 'active',   refs: 9  },
    { id: 'ledger',             label: 'double-entry-ledger',type: 'model',       status: 'active',   refs: 22 },
    { id: 'payout',             label: 'payout',             type: 'model',       status: 'active',   refs: 24 },
    { id: 'auth-token',         label: 'auth-token-endpoint',type: 'endpoint',    status: 'stale',    refs: 6  },
    { id: 'corridor-pricing',   label: 'corridor-pricing',   type: 'decision',    status: 'active',   refs: 14 },
    { id: 'webhook-replay',     label: 'webhook-replay',     type: 'contract',    status: 'active',   refs: 7  },
    { id: 'kyc',                label: 'kyc',                type: 'requirement', status: 'active',   refs: 11 },
    { id: 'reconciliation',     label: 'reconciliation',     type: 'model',       status: 'active',   refs: 19 },
    { id: 'on-call',            label: 'on-call-runbook',    type: 'custom',      status: 'stale',    refs: 4  },
    { id: 'sgd-corridor',       label: 'sgd-corridor',       type: 'config',      status: 'active',   refs: 8  },
    { id: 'mxn-corridor',       label: 'mxn-corridor',       type: 'config',      status: 'planned',  refs: 5  },
  ],
  conceptEdges: [
    ['corridor', 'payout'], ['payout', 'idem-key'], ['payout', 'payout-state'],
    ['payout', 'partner-bank'], ['corridor', 'fx-hedge'], ['corridor', 'corridor-pricing'],
    ['corridor', 'sgd-corridor'], ['corridor', 'mxn-corridor'], ['payout', 'ledger'],
    ['ledger', 'reconciliation'], ['payout-state', 'webhook-replay'],
    ['partner-bank', 'kyc'], ['kyc', 'auth-token'], ['payout', 'on-call'],
    ['fx-hedge', 'corridor-pricing'],
  ],

  // Issues — the unit of work. Sessions bundle issues.
  issues: [
    { id: 'MRLN-128', title: 'add SGD corridor + ABS bank routing', status: 'in_progress',
      executor: 'ai',  verifier: 'required', agent: 'backend-coder', priority: 'high',
      repo: 'pearl-fi/marlin', base_branch: 'main', parent: null,
      concepts: ['corridor', 'sgd-corridor', 'partner-bank', 'idem-key'], author: 'sasha k.' },
    { id: 'MRLN-129', title: 'wire reconciliation report → ledger backfill', status: 'in_progress',
      executor: 'ai',  verifier: 'required', agent: 'backend-coder', priority: 'high',
      repo: 'pearl-fi/marlin', base_branch: 'main', parent: null,
      concepts: ['reconciliation', 'ledger', 'payout-state'], author: 'r. martins' },
    { id: 'MRLN-126', title: 'idempotency key on POST /payouts/batch', status: 'in_review',
      executor: 'ai',  verifier: 'required', agent: 'backend-coder', priority: 'urgent',
      repo: 'pearl-fi/marlin', base_branch: 'main', parent: null,
      concepts: ['idem-key', 'payout'], author: 'sasha k.' },
    { id: 'MRLN-127', title: 'MXN corridor scaffold + STP partner stub', status: 'todo',
      executor: 'ai',  verifier: 'required', agent: 'backend-coder', priority: 'medium',
      repo: 'pearl-fi/marlin', base_branch: 'main', parent: null,
      concepts: ['corridor', 'mxn-corridor', 'partner-bank'], author: 'sasha k.' },
    { id: 'MRLN-130', title: 'on-call runbook · payout webhook replay', status: 'backlog',
      executor: 'human', verifier: 'optional', agent: null, priority: 'low',
      repo: 'pearl-fi/marlin', base_branch: 'main', parent: null,
      concepts: ['on-call', 'webhook-replay', 'payout-state'], author: 'l. okafor' },
    { id: 'MRLN-124', title: 'fx-hedge: pin corridor pricing to forward curve', status: 'verified',
      executor: 'ai',  verifier: 'required', agent: 'backend-coder', priority: 'high',
      repo: 'pearl-fi/marlin', base_branch: 'main', parent: null,
      concepts: ['fx-hedge', 'corridor-pricing', 'corridor'], author: 'r. martins' },
    { id: 'MRLN-125', title: 'partner-bank · KYC re-check on stale tokens', status: 'done',
      executor: 'ai',  verifier: 'required', agent: 'backend-coder', priority: 'medium',
      repo: 'pearl-fi/marlin', base_branch: 'main', parent: null,
      concepts: ['kyc', 'partner-bank', 'auth-token'], author: 'l. okafor' },
    { id: 'MRLN-122', title: 'ledger · double-entry posting for reversals', status: 'done',
      executor: 'ai',  verifier: 'required', agent: 'backend-coder', priority: 'high',
      repo: 'pearl-fi/marlin', base_branch: 'main', parent: null,
      concepts: ['ledger', 'payout', 'payout-state'], author: 'sasha k.' },
    { id: 'MRLN-131', title: 'datadog · payout latency dashboard', status: 'backlog',
      executor: 'mixed', verifier: 'optional', agent: null, priority: 'low',
      repo: 'pearl-fi/marlin-infra', base_branch: 'main', parent: null,
      concepts: ['payout'], author: 'a. tanaka' },
    { id: 'MRLN-132', title: 'rotate ABS partner credentials', status: 'todo',
      executor: 'human', verifier: 'none', agent: null, priority: 'urgent',
      repo: 'pearl-fi/marlin-infra', base_branch: 'main', parent: null,
      concepts: ['partner-bank', 'auth-token'], author: 'm. faure' },
  ],

  // Sessions — bundles of issues, with engagements + orchestration + runtime state.
  sessions: [
    {
      id: 'sgd-corridor', name: 'add SGD corridor + ABS routing', status: 'executing',
      current_state: 'executing', agent: 'backend-coder', author: 'sasha k.',
      issues: ['MRLN-128'], blocked_by_sessions: [], estimated_size: 'medium',
      grouping_rationale: 'single corridor add — narrow scope',
      repos: [{ repo: 'pearl-fi/marlin', base_branch: 'main', branch: 'session/sgd-corridor', pr_number: null }],
      runtime_state: { claude_session_id: 'cs_8f2a…', langgraph_thread_id: 'lg_3c1e…', workspace_volume: 'vol_42a' },
      engagements: [
        { n: 1, started: '14m ago', trigger: 'initial_launch', state: 'implementing', turns: 12 },
      ],
      cost: 0.84, lines: '+312 −44',
      agent_state: 'implementing',
    },
    {
      id: 'recon-backfill', name: 'wire reconciliation → ledger backfill', status: 're_engaged',
      current_state: 'executing', agent: 'backend-coder', author: 'r. martins',
      issues: ['MRLN-129'], blocked_by_sessions: [], estimated_size: 'large',
      grouping_rationale: 'cross-cutting recon→ledger work',
      repos: [{ repo: 'pearl-fi/marlin', base_branch: 'main', branch: 'session/recon-backfill', pr_number: null }],
      runtime_state: { claude_session_id: 'cs_b41c…', langgraph_thread_id: 'lg_9d2f…', workspace_volume: 'vol_71c' },
      engagements: [
        { n: 1, started: '2h 38m ago', trigger: 'initial_launch', state: 'implementing', turns: 12, ended: '1h 22m ago' },
        { n: 2, started: '1h 18m ago', trigger: 'plan_rejected', state: 'planning', turns: 4, ended: '1h 02m ago',
          note: 'PM rejected plan — too broad, asked to split auth changes out' },
        { n: 3, started: '38m ago', trigger: 'human_response', state: 'implementing', turns: 24,
          note: 'continued from rev plan' },
      ],
      cost: 1.92, lines: '+811 −287',
      agent_state: 'implementing',
      validation: {
        errors: [
          { ref: '[[auth-token]]', kind: 'stale_reference',
            note: 'session edits auth/session.ts but [[auth-token]] is marked stale — concept node needs refresh first' },
        ],
        warnings: [
          { ref: '[[reconciliation]]', kind: 'sha_mismatch',
            note: 'cited [[reconciliation]] sha 3a91e — current is 7c20f' },
        ],
      },
    },
    {
      id: 'idem-batch', name: 'idempotency key · POST /payouts/batch', status: 'waiting_for_review',
      current_state: 'in_review', agent: 'backend-coder', author: 'sasha k.',
      issues: ['MRLN-126'], blocked_by_sessions: [], estimated_size: 'small',
      grouping_rationale: 'single endpoint contract change',
      repos: [{ repo: 'pearl-fi/marlin', base_branch: 'main', branch: 'session/idem-batch', pr_number: 412 }],
      runtime_state: { claude_session_id: 'cs_2e9a…', langgraph_thread_id: 'lg_4b1c…', workspace_volume: 'vol_18d' },
      engagements: [
        { n: 1, started: '2h ago', trigger: 'initial_launch', state: 'done', turns: 8, ended: '1h 14m ago' },
      ],
      cost: 0.41, lines: '+94 −12',
      agent_state: 'done',
      artifacts: [
        { name: 'plan',         present: true,  required: true,  approval: { approved: true,  reviewer: 'sasha k.', at: '1h 14m ago' } },
        { name: 'developer.md', present: true,  required: true,  approval: null },
        { name: 'verified.md',  present: true,  required: true,  approval: { approved: true,  reviewer: 'verifier', at: '52m ago' } },
        { name: 'pr',           present: true,  required: true,  approval: null },
      ],
    },
    {
      id: 'mxn-corridor', name: 'MXN corridor scaffold + STP stub', status: 'queued',
      current_state: 'queued', agent: 'backend-coder', author: 'sasha k.',
      issues: ['MRLN-127'], blocked_by_sessions: ['sgd-corridor'], estimated_size: 'medium',
      grouping_rationale: 'second corridor — same shape as SGD',
      repos: [{ repo: 'pearl-fi/marlin', base_branch: 'main', branch: null, pr_number: null }],
      runtime_state: { claude_session_id: null, langgraph_thread_id: null, workspace_volume: null },
      engagements: [],
      cost: 0, lines: '—',
    },
    {
      id: 'webhook-replay', name: 'on-call runbook · webhook replay', status: 'planned',
      current_state: 'planned', agent: null, author: 'l. okafor',
      issues: ['MRLN-130'], blocked_by_sessions: [], estimated_size: 'small',
      grouping_rationale: 'doc + runbook only — human work',
      repos: [{ repo: 'pearl-fi/marlin', base_branch: 'main', branch: null, pr_number: null }],
      runtime_state: { claude_session_id: null, langgraph_thread_id: null, workspace_volume: null },
      engagements: [],
      cost: 0, lines: '—',
    },
    {
      id: 'fx-pin', name: 'fx-hedge · pin pricing to forward curve', status: 'completed',
      current_state: 'completed', agent: 'backend-coder', author: 'r. martins',
      issues: ['MRLN-124'], blocked_by_sessions: [], estimated_size: 'medium',
      grouping_rationale: 'pricing change — narrow blast radius',
      repos: [{ repo: 'pearl-fi/marlin', base_branch: 'main', branch: 'session/fx-pin', pr_number: 408 }],
      runtime_state: { claude_session_id: 'cs_77ab…', langgraph_thread_id: 'lg_29ef…', workspace_volume: null },
      engagements: [
        { n: 1, started: 'yesterday', trigger: 'initial_launch', state: 'done', turns: 16, ended: 'yesterday' },
      ],
      cost: 1.21, lines: '+428 −96',
      agent_state: 'done',
    },
    {
      id: 'kyc-recheck', name: 'partner-bank · KYC re-check', status: 'completed',
      current_state: 'completed', agent: 'backend-coder', author: 'l. okafor',
      issues: ['MRLN-125'], blocked_by_sessions: [], estimated_size: 'medium',
      grouping_rationale: 'KYC token refresh — touches 2 partners',
      repos: [{ repo: 'pearl-fi/marlin', base_branch: 'main', branch: 'session/kyc-recheck', pr_number: 401 }],
      runtime_state: { claude_session_id: 'cs_5d2c…', langgraph_thread_id: 'lg_7a4b…', workspace_volume: null },
      engagements: [
        { n: 1, started: '2d ago', trigger: 'initial_launch', state: 'done', turns: 11, ended: '2d ago' },
      ],
      cost: 0.78, lines: '+186 −44',
      agent_state: 'done',
    },
  ],

  team: [
    { handle: 'sasha k.',   role: 'pm',        initials: 'sk', color: '#c83d2e' },
    { handle: 'r. martins', role: 'eng',       initials: 'rm', color: '#2a4d7f' },
    { handle: 'l. okafor',  role: 'eng',       initials: 'lo', color: '#436b4d' },
    { handle: 'a. tanaka',  role: 'eng',       initials: 'at', color: '#c8861f' },
    { handle: 'm. faure',   role: 'staff eng', initials: 'mf', color: '#9b2c20' },
  ],

  // Detailed engagement-level turn timeline for one session (recon-backfill, current engagement)
  // Used by Session Detail + Live Monitor + Artifact Rejection screens.
  sessionTimeline: {
    sessionId: 'recon-backfill',
    engagement: 3,
    turns: [
      { n: 1,  t: '00:00', kind: 'spawn',     agent_state: 'investigating',
        summary: 'engagement 3 spawned · context: 4 files, 6 concepts, prior plan rejected by sasha k.' },
      { n: 2,  t: '00:42', kind: 'plan',      agent_state: 'planning',
        summary: 'sketched recon-report → ledger-backfill flow · narrowed scope per PM feedback' },
      { n: 3,  t: '01:18', kind: 'tool_read', agent_state: 'investigating',
        summary: 'read recon/report.ts (412 lines)', files: ['recon/report.ts'] },
      { n: 4,  t: '01:56', kind: 'edit',      agent_state: 'implementing',
        summary: 'added ReportEntry → LedgerLine mapper', files: ['recon/report.ts'], lines: '+62 −4' },
      { n: 5,  t: '02:51', kind: 'edit',      agent_state: 'implementing',
        summary: 'wrote ledger/backfill.ts skeleton', files: ['ledger/backfill.ts'], lines: '+184 −0' },
      { n: 6,  t: '04:02', kind: 'tool_run',  agent_state: 'testing',
        summary: 'pnpm test ledger — 14 pass · 0 fail' },
      { n: 7,  t: '04:48', kind: 'edit',      agent_state: 'implementing',
        summary: 'wired posting batch into backfill loop', files: ['ledger/post.ts', 'ledger/backfill.ts'], lines: '+72 −18' },
      { n: 8,  t: '06:11', kind: 'note',      agent_state: 'planning',
        summary: 'reasoning: chose forward-only walk to avoid double-post on retries' },
      { n: 9,  t: '06:55', kind: 'tool_read', agent_state: 'investigating',
        summary: 'read ledger/post.ts (288 lines)', files: ['ledger/post.ts'] },
      { n: 10, t: '08:02', kind: 'edit',      agent_state: 'implementing',
        summary: 'patched post() to accept batch context', files: ['ledger/post.ts'], lines: '+58 −24' },
      { n: 11, t: '09:14', kind: 'tool_run',  agent_state: 'testing',
        summary: 'pnpm test recon — 22 pass · 0 fail' },
      { n: 12, t: '10:36', kind: 'tool_read', agent_state: 'investigating',
        summary: 'read auth/session.ts — looking for token refresh path', files: ['auth/session.ts'] },
      { n: 13, t: '11:18', kind: 'edit',      agent_state: 'implementing',
        summary: 'tweaked refresh() to reuse session context', files: ['auth/session.ts'], lines: '+24 −8' },
      { n: 14, t: '12:02', kind: 'tool_run',  agent_state: 'testing',
        summary: 'pnpm test auth — 18 pass · 0 fail' },
      { n: 15, t: '13:11', kind: 'edit',      agent_state: 'refactoring',
        summary: 'split auth/session.ts helpers', files: ['auth/session.ts'], lines: '+38 −12' },
      { n: 16, t: '14:25', kind: 'plan',      agent_state: 'planning',
        summary: 'planning final wire-through: backfill ↔ recon' },
      { n: 17, t: '15:42', kind: 'edit',      agent_state: 'implementing',
        summary: 'added retry hook in auth/session.ts', files: ['auth/session.ts'], lines: '+22 −6' },
      { n: 18, t: '16:08', kind: 'validation_failed', agent_state: 'implementing',
        summary: 'validator: [[auth-token]] is stale — concept node has not been refreshed since deprecation 18 days ago',
        ref: '[[auth-token]]',
        note: 'session edited auth/session.ts which resolves to a stale concept; validator flagged before any artifact write' },
      { n: 19, t: '16:52', kind: 'edit',      agent_state: 'implementing',
        summary: 'returned to ledger/backfill.ts — wired final entries', files: ['ledger/backfill.ts'], lines: '+48 −12' },
      { n: 20, t: '18:14', kind: 'tool_run',  agent_state: 'testing',
        summary: 'pnpm test — 41 pass · 2 fail (recon edge cases)' },
      { n: 21, t: '19:38', kind: 'edit',      agent_state: 'debugging',
        summary: 'fixed recon edge case for partial reports', files: ['recon/report.ts'], lines: '+18 −4' },
      { n: 22, t: '20:11', kind: 'message',   agent_state: 'awaiting_plan_approval',
        summary: 'agent: posted progress + flagged auth/session.ts edits as needing PM sign-off',
        message_type: 'plan_approval' },
      { n: 23, t: '20:47', kind: 'tool_run',  agent_state: 'testing',
        summary: 'pnpm test — 43 pass · 0 fail' },
      { n: 24, t: '22:14', kind: 'edit',      agent_state: 'refactoring',
        summary: 'cleanup: removed dead branches in backfill loop', files: ['ledger/backfill.ts'], lines: '+12 −38' },
    ],
  },

  // The org-wide stream of recent validation events + artifact rejections + reviews.
  interventionStream: [
    { kind: 'validation',       severity: 'error', status: 'open',
      session: 'recon-backfill', issue: 'MRLN-129', t: '4m ago',
      title: '[[auth-token]] is stale',
      note: 'session edits resolve to a deprecated concept node' },
    { kind: 'plan_approval',    severity: 'review', status: 'open',
      session: 'recon-backfill', issue: 'MRLN-129', t: '12m ago',
      title: 'plan approval requested',
      note: 'agent flagged auth/session.ts edits — needs PM sign-off' },
    { kind: 'validation',       severity: 'warn', status: 'resolved',
      session: 'fx-pin', issue: 'MRLN-124', t: '2h ago',
      title: '[[corridor-pricing]] sha mismatch',
      note: 'cited 3a91e — current is 7c20f · agent re-read and re-cited' },
    { kind: 'artifact_rejection', severity: 'block', status: 'resolved',
      session: 'recon-backfill', issue: 'MRLN-129', t: 'yesterday',
      title: 'plan rejected · re_engagement triggered',
      note: 'PM: scope is too broad — split auth changes into a separate session' },
    { kind: 'verifier_pass',    severity: 'ok', status: 'resolved',
      session: 'idem-batch', issue: 'MRLN-126', t: '52m ago',
      title: 'verified.md approved',
      note: 'all acceptance criteria + tests pass' },
  ],
};

// ─── DERIVED / BRIDGING DATA ────────────────────────────────────────────
(function bridge(S) {
  // interventionStream: stable ids
  S.interventionStream.forEach((f, i) => { f.id = `EV-${String(20 + i).padStart(3, '0')}`; });

  // ── Process Map shapes (validators / connectors / artifacts) ─────────
  // The Process Map screen is a static reference diagram, so it has its own
  // shape that's separate from runtime data. We declare it here on the bridge
  // so the v3 scenario stays focused on real product data.
  S.validators = [
    { id: 'v_ref',    kind: 'gate',    name: 'reference resolution',   checks: 'plan cites concepts that exist + are active' },
    { id: 'v_scope',  kind: 'gate',    name: 'scope check',            checks: 'agent only opens files in the issue\'s primary paths' },
    { id: 'v_drift',  kind: 'monitor', name: 'concept drift',          checks: 'edits stay inside the issue\'s concept neighborhood' },
    { id: 'v_cost',   kind: 'monitor', name: 'cost ceiling',           checks: 'tokens + minutes vs. the session budget' },
    { id: 'v_test',   kind: 'gate',    name: 'tests pass',             checks: 'pnpm test green on changed packages' },
    { id: 'v_secret', kind: 'gate',    name: 'no secrets',             checks: 'staged diff has no API keys / tokens' },
    { id: 'v_mig',    kind: 'gate',    name: 'migration safety',       checks: 'schema changes have a reversible down step' },
  ];

  S.connectors = [
    { id: 'linear',    name: 'Linear'    },
    { id: 'github',    name: 'GitHub'    },
    { id: 'figma',     name: 'Figma'     },
    { id: 'slack',     name: 'Slack'     },
    { id: 'datadog',   name: 'Datadog'   },
    { id: 'pagerduty', name: 'PagerDuty' },
    { id: 'sentry',    name: 'Sentry'    },
  ];

  // Artifacts produced/consumed at lifecycle stages (using v3 lifecycle ids).
  S.artifacts = [
    { id: 'a_plan',    label: 'plan.md',          produced_by: 'spawned',   consumed_by: 'executing' },
    { id: 'a_diff',    label: 'staged diff',      produced_by: 'executing', consumed_by: 'review'    },
    { id: 'a_dev',     label: 'developer.md',     produced_by: 'executing', consumed_by: 'review'    },
    { id: 'a_test',    label: 'test results',     produced_by: 'executing', consumed_by: 'verified'  },
    { id: 'a_ver',     label: 'verified.md',      produced_by: 'review',    consumed_by: 'verified'  },
    { id: 'a_review',  label: 'review notes',     produced_by: 'review',    consumed_by: 'completed' },
    { id: 'a_merge',   label: 'merge commit',     produced_by: 'verified',  consumed_by: 'completed' },
  ];

  // Per-session turn lookup
  S.turnsBySession = {};
  const tl = S.sessionTimeline;
  if (tl) S.turnsBySession[tl.sessionId] = tl.turns;

  // Concept layout for the graph screen
  const cx = 500, cy = 280;
  const positions = {
    'corridor':         { x: cx,        y: cy - 140, weight: 32 },
    'payout':           { x: cx + 30,   y: cy + 30,  weight: 36 },
    'idem-key':         { x: cx + 240,  y: cy - 60,  weight: 24 },
    'partner-bank':     { x: cx + 200,  y: cy + 140, weight: 22 },
    'fx-hedge':         { x: cx - 230,  y: cy - 80,  weight: 22 },
    'ledger':           { x: cx - 70,   y: cy + 200, weight: 28 },
    'payout-state':     { x: cx + 110,  y: cy + 200, weight: 22 },
    'auth-token':       { x: cx + 360,  y: cy + 80,  weight: 16 },
    'corridor-pricing': { x: cx - 200,  y: cy + 60,  weight: 22 },
    'webhook-replay':   { x: cx + 320,  y: cy + 220, weight: 16 },
    'kyc':              { x: cx + 350,  y: cy - 80,  weight: 18 },
    'reconciliation':   { x: cx - 240,  y: cy + 200, weight: 22 },
    'on-call':          { x: cx - 80,   y: cy + 320, weight: 14 },
    'sgd-corridor':     { x: cx - 60,   y: cy - 280, weight: 16 },
    'mxn-corridor':     { x: cx + 160,  y: cy - 240, weight: 16 },
  };
  S.concepts.forEach(c => {
    const p = positions[c.id] || { x: cx, y: cy, weight: 18 };
    c.x = p.x; c.y = p.y; c.weight = p.weight;
  });
  S.conceptEdges = S.conceptEdges.map(e => Array.isArray(e) ? { a: e[0], b: e[1], kind: 'cites' } : e);

  // Live monitor data — for the live session view (mirrors v2 'agent monitoring')
  S.liveMonitor = {
    session_id: 'recon-backfill',
    engagement: 3,
    turn: 24,
    elapsed: '00:11.2',
    agent_state: 'refactoring',
    heading: 'Cleaning up dead branches in the backfill loop.',
    message:
      'Now that the recon edge cases pass, the backfill loop has two unreachable arms left over from the earlier walk-direction experiment. ' +
      'I will remove them and re-run the suite. Coverage should not drop — those branches were already untested.',
    tool: { name: 'read_file', args: '"ledger/backfill.ts"', ms: 280 },
    echo: [
      { t: '00:00.0', s: 'turn 24 opened — agent finalizing cleanup' },
      { t: '00:01.4', s: 'tool · run_tests("recon") → 43 pass · 0 fail in 1.1s' },
      { t: '00:04.2', s: 'agent_state · refactoring' },
      { t: '00:08.6', s: 'tool · read_file("ledger/backfill.ts") → 312 lines' },
    ],
    validators: [
      { name: 'tests · recon',   state: 'pass', detail: '43 / 43' },
      { name: 'tests · ledger',  state: 'pass', detail: '14 / 14' },
      { name: '[[auth-token]]',  state: 'fail', detail: 'stale concept' },
      { name: 'concept refs',    state: 'arm',  detail: 'watching' },
    ],
    open_interventions: [
      { kind: 'validation',    title: '[[auth-token]] · stale concept', sev: 'error' },
      { kind: 'plan_approval', title: 'plan approval requested',         sev: 'review' },
    ],
  };

  // Artifact rejection / intervention takeover — built around recon-backfill engagement 2 → 3.
  S.interventionDetail = {
    id: 'EV-021',
    kind: 'artifact_rejection',
    artifact: 'plan',
    session_id: 'recon-backfill',
    issue_id: 'MRLN-129',
    title: 'plan rejected · scope too broad',
    rejected_by: 'sasha k.',
    rejected_at: 'yesterday · 3:14pm',
    feedback:
      'The plan touches auth/session.ts to thread a batch context into refresh(). ' +
      'Auth is outside this issue\'s scope. Split that into MRLN-133 and ' +
      'rewrite the backfill plan to use the existing token-passing path. ' +
      'Re-engage when ready.',
    armed_rule:
      'Plans require PM approval before implementation begins, when the agent\'s declared file list extends beyond the issue\'s primary paths.',
    armed_by: 'sasha k.',
    armed_at: '23 days ago',
    plan_before:
`// excerpt — original plan (engagement 1, turn 4)

Files I will edit:
  recon/report.ts          # add ReportEntry → LedgerLine mapper
  ledger/backfill.ts       # new — walk recon entries, post to ledger
  ledger/post.ts           # extend post() to accept BatchCtx
  auth/session.ts          # thread BatchCtx through refresh()
                           # (so retries reuse the same token)

Tests: pnpm test recon, pnpm test ledger, pnpm test auth`,
    plan_after:
`// excerpt — revised plan (engagement 3, turn 2)

Files I will edit:
  recon/report.ts          # add ReportEntry → LedgerLine mapper
  ledger/backfill.ts       # new — walk recon entries, post to ledger
  ledger/post.ts           # extend post() to accept BatchCtx

Auth changes deferred to MRLN-133 per PM feedback.
Token refresh uses the existing flow — known to be safe under
retry because the partner adapter dedupes by Idempotency-Key.

Tests: pnpm test recon, pnpm test ledger`,
    failed_checks: [
      { name: 'plan · primary paths', got: 'plan declared 4 files; issue MRLN-129 declared 3' },
      { name: 'plan · concept neighborhood', got: 'plan touched [[auth-token]] (stale)' },
      { name: 'plan · approval gate', got: 'no override recorded — gate fires' },
    ],
    history: [
      { d: '2025-09-12', s: 'rule armed',                   who: 'sasha k.',  tone: '#a8a094' },
      { d: '2025-10-04', s: 'rejected · MRLN-098',          who: 'agent reverted', tone: '#c8861f' },
      { d: '2025-11-21', s: 'rejected · MRLN-114',          who: 'agent reverted', tone: '#c8861f' },
      { d: 'yesterday',  s: 'rejected · MRLN-129 (eng. 2)', who: 're-engaged eng. 3', tone: '#c8861f' },
      { d: 'now',         s: 'engagement 3 in flight',      who: 'agent · backend-coder', tone: '#436b4d' },
    ],
    notify: [
      { who: 'sasha k.',    why: 'PM on Marlin · armed this rule' },
      { who: 'r. martins',  why: 'driver of MRLN-129' },
      { who: 'm. faure',    why: 'last edited auth/session.ts · 18 days ago' },
    ],
  };
})(window.SCENARIO);
