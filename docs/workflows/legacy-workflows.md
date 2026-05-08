# Legacy workflow declarations (documentation only, v0.13)

These workflows shipped in `workflow.yaml.j2` through v0.12 as
documentation of the surrounding PM/review/ops process. None of them
have an executor — they were never wired to drive `session.status`
mutations or fire side-effects, and keeping them in the live template
created a drift hazard (someone trusting the spec to drive behavior it
doesn't drive).

In v0.13 the live template carries only `coding-session`, the workflow
the executor actually runs. The blocks below are reference material
preserved verbatim from v0.12, except the duplicate
`concept-freshness` block from lines 1417–1479 of v0.12 — that was a
merge artifact, not a second workflow.

If you want to materialise any of these into an executable workflow,
the path is: register a `WORKFLOW_ID` in the executor module, add the
appropriate side-effect handlers in `core/workflow/side_effects.py`,
and wire the routes with `side_effects:` arrays.

```yaml
workflows:

  pm-scoping:
    actor: pm-agent
    trigger: command.pm-scope
    statuses:
      - id: intake
        next: draft
        work_steps:
          - id: capture
            actor: pm-agent
            label: capture intent
            skills: [project-manager]
      - id: draft
        next: validate
        # Heuristics fire-once on draft outputs: mega-issue (split too
        # large), prose-without-node (concept names mentioned without a
        # structured ref), semantic-coverage (AC under-references
        # nodes), quality-consistency (drift from calibrated baseline).
        heuristics:
          - v_mega_issue
          - v_concept_name_prose
          - v_semantic_coverage
          - v_quality_consistency
        work_steps:
          - id: draft
            actor: pm-agent
            label: draft scoped issues
            skills: [project-manager]
      - id: validate
        next:
          - if: gaps.present == true
            then: draft
          - else: publish
        # Hard gates on the scoped artifacts before the loop can exit;
        # the slash-command invocation is itself recorded as a
        # prompt_check so the gate can audit "was pm-validate run."
        # (v_workflow_well_formed is auto-prepended by the registry.)
        tripwires:
          - v_uuid_present
          - v_id_format
          - v_id_collisions
          - v_reference_integrity
        heuristics:
          - v_sequence_drift
        prompt_checks: [pm-validate]
        work_steps:
          - id: validate
            actor: code
            label: validate scope
            skills: [project-manager]
      - id: publish
        terminal: true
        # Phase requirements (gap-analysis.md + compliance.md present
        # AND complete) is the scoping → scoped phase boundary tripwire.
        # The done-implies-completed gate keeps publish from advancing
        # an issue whose dependent session is not yet finished.
        tripwires:
          - v_phase_requirements
          - v_done_implies_session_completed
        prompt_checks: [pm-scope]
        cross_links:
          - workflow: pm-triage
            status: intake
            label: scoped issues enter triage
            kind: triggers
        work_steps:
          - id: publish
            actor: pm-agent
            label: publish scoped issues
            skills: [project-manager]
    routes:
      - id: scope-intake
        actor: pm-agent
        command: pm-scope
        trigger: command.pm-scope
        from: source:intent
        to: intake
        kind: forward
        label: intake intent
        skills: [project-manager]
      - id: draft-scope
        actor: pm-agent
        command: pm-scope
        trigger: scoping.draft
        from: intake
        to: draft
        kind: forward
        label: draft artifacts
        skills: [project-manager]
      - id: validate-scope
        actor: code
        command: pm-validate
        trigger: command.pm-validate
        from: draft
        to: validate
        kind: forward
        label: validate scope
        skills: [project-manager]
      - id: scope-gap-loop
        actor: pm-agent
        command: pm-rescope
        trigger: gaps.present == true
        from: validate
        to: draft
        kind: return
        label: close gaps
        skills: [project-manager]
      - id: publish-scope
        actor: pm-agent
        command: pm-scope
        trigger: gaps.present == false
        from: validate
        to: publish
        kind: forward
        label: publish
        emits:
          artifacts:
            - id: scoped-issues
              label: scoped issues and sessions

  pm-triage:
    actor: pm-agent
    trigger: command.pm-triage
    statuses:
      - id: intake
        next: classify
        work_steps:
          - id: receive
            actor: pm-agent
            label: receive inbox item
            skills: [project-manager, agent-messaging]
      - id: classify
        next: act
        # Mega-item flag at classify-time so the PM can split before
        # acting on a too-large incoming inbox row.
        heuristics:
          - v_mega_issue
        work_steps:
          - id: classify
            actor: pm-agent
            label: classify item
            skills: [project-manager]
      - id: act
        next: close
        # Action references must resolve before the triage hops out to
        # a coding-session; pm-edit is the recorded slash command.
        tripwires:
          - v_reference_integrity
        prompt_checks: [pm-edit]
        cross_links:
          - workflow: coding-session
            status: planned
            label: triages into session
            kind: triggers
        work_steps:
          - id: act
            actor: pm-agent
            label: act on classification
            skills: [project-manager]
      - id: close
        terminal: true
        tripwires:
          - v_done_implies_session_completed
        work_steps:
          - id: close
            actor: pm-agent
            label: close triage record
            skills: [project-manager]
    routes:
      - id: triage-intake
        actor: pm-agent
        command: pm-triage
        trigger: command.pm-triage
        from: source:inbox
        to: intake
        kind: forward
        label: intake
        skills: [project-manager, agent-messaging]
      - id: classify-item
        actor: pm-agent
        command: pm-triage
        trigger: triage.classify
        from: intake
        to: classify
        kind: forward
        label: classify
        skills: [project-manager]
      - id: act-on-item
        actor: pm-agent
        command: pm-edit
        trigger: triage.action
        from: classify
        to: act
        kind: forward
        label: act
        skills: [project-manager]
      - id: close-triage
        actor: pm-agent
        command: pm-triage
        trigger: triage.close
        from: act
        to: close
        kind: forward
        label: close

  pm-incremental-update:
    actor: pm-agent
    trigger: command.pm-edit
    statuses:
      - id: inspect
        next: edit
        work_steps:
          - id: inspect
            actor: pm-agent
            label: inspect change request
            skills: [project-manager]
      - id: edit
        next: validate
        # Edit-time heuristics: prose-without-node, quality-drift.
        heuristics:
          - v_concept_name_prose
          - v_quality_consistency
        work_steps:
          - id: edit
            actor: pm-agent
            label: apply edits
            skills: [project-manager]
      - id: validate
        next:
          - if: validation.clean == true
            then: publish
          - else: edit
        tripwires:
          - v_uuid_present
          - v_id_format
          - v_reference_integrity
        prompt_checks: [pm-validate]
        work_steps:
          - id: validate
            actor: code
            label: validate edits
            skills: [project-manager]
      - id: publish
        terminal: true
        tripwires:
          - v_phase_requirements
          - v_done_implies_session_completed
        prompt_checks: [pm-issue-close]
        cross_links:
          - workflow: coding-session
            status: planned
            label: incremental update spawns session
            kind: triggers
          - workflow: issue-closure
            status: closing
            label: pm-issue-close path
            kind: triggers
        work_steps:
          - id: publish
            actor: pm-agent
            label: publish update
            skills: [project-manager]
    routes:
      - id: inspect-update
        actor: pm-agent
        command: pm-edit
        trigger: command.pm-edit
        from: source:change-request
        to: inspect
        kind: forward
        label: inspect
        skills: [project-manager]
      - id: apply-update
        actor: pm-agent
        command: pm-edit
        trigger: update.apply
        from: inspect
        to: edit
        kind: forward
        label: edit
        skills: [project-manager]
      - id: validate-update
        actor: code
        command: pm-validate
        trigger: command.pm-validate
        from: edit
        to: validate
        kind: forward
        label: validate
      - id: fix-update-loop
        actor: pm-agent
        command: pm-edit
        trigger: validation.clean == false
        from: validate
        to: edit
        kind: return
        label: fix
        skills: [project-manager]
      - id: publish-update
        actor: pm-agent
        command: pm-issue-close
        trigger: validation.clean == true
        from: validate
        to: publish
        kind: forward
        label: publish
        skills: [project-manager]

  project-maintenance:
    actor: pm-agent
    trigger: command.pm-status
    statuses:
      - id: inspect
        next: report
        # Sweep heuristics: stale concepts, off-band node ratio, drift
        # from calibrated quality. Markers keep the sweep idempotent
        # across runs; condition_hash drift re-fires.
        heuristics:
          - v_stale_concept
          - v_node_ratio
          - v_quality_consistency
        work_steps:
          - id: inspect
            actor: pm-agent
            label: inspect project state
            skills: [project-manager]
      - id: report
        terminal: true
        prompt_checks: [pm-agenda]
        cross_links:
          - workflow: pm-triage
            status: intake
            label: maintenance findings enter triage
            kind: triggers
        work_steps:
          - id: report
            actor: pm-agent
            label: emit findings
            skills: [project-manager]
    routes:
      - id: status-report
        actor: pm-agent
        command: pm-status
        trigger: command.pm-status
        from: source:project
        to: inspect
        kind: forward
        label: status
        skills: [project-manager]
      - id: agenda-report
        actor: pm-agent
        command: pm-agenda
        trigger: command.pm-agenda
        from: inspect
        to: report
        kind: forward
        label: agenda
        skills: [project-manager]
      - id: graph-report
        actor: pm-agent
        command: pm-graph
        trigger: command.pm-graph
        from: inspect
        to: report
        kind: side
        label: graph
        skills: [project-manager]
      - id: validate-report
        actor: code
        command: pm-validate
        trigger: command.pm-validate
        from: inspect
        to: report
        kind: side
        label: validate
      - id: sync-project
        actor: code
        command: pm-project-sync
        trigger: command.pm-project-sync
        from: inspect
        to: report
        kind: side
        label: sync

  # pm-monitor — overseer loop. Scans project state, classifies signals,
  # and dispatches actions or subagents per the cross_link contract. The
  # signal vocabulary, thresholds, and dispatch targets are codified in
  # `references/MONITOR_CRITERIA.md`. Threshold values live in
  # `project.yaml.monitor:` so iteration doesn't require code edits.
  pm-monitor:
    actor: pm-agent
    trigger: command.pm-monitor
    statuses:
      - id: scan
        next: classify
        tripwires:
          - v_workflow_well_formed
        work_steps:
          - id: gather-session-state
            actor: pm-agent
            label: gather session state
            skills: [project-manager]
          - id: gather-pr-state
            actor: pm-agent
            label: gather PR state
            skills: []
          - id: gather-inbox-state
            actor: pm-agent
            label: gather inbox state
            skills: [agent-messaging]
          - id: gather-message-queue
            actor: pm-agent
            label: gather message queue
            skills: []
      - id: classify
        next: dispatch
        heuristics:
          - v_stale_concept
        work_steps:
          - id: classify-each-signal
            actor: pm-agent
            label: classify signals
            skills: [project-manager]
      - id: dispatch
        next: idle
        cross_links:
          - workflow: coding-session
            status: queued
            label: launch session
            kind: triggers
            pm_subagent_dispatch: true
          - workflow: coding-session
            status: executing
            label: relaunch crashed session
            kind: triggers
            pm_subagent_dispatch: true
          - workflow: pm-triage
            status: intake
            label: triage new inbound
            kind: triggers
            pm_subagent_dispatch: true
          - workflow: pm-incremental-update
            status: inspect
            label: handle agent question
            kind: triggers
            pm_subagent_dispatch: true
          - workflow: code-review
            status: received
            label: launch review on PR pair
            kind: triggers
            pm_subagent_dispatch: true
          - workflow: inbox-handling
            status: pending
            label: escalate to user
            kind: triggers
          - workflow: concept-freshness
            status: detected
            label: stale-node count high
            kind: triggers
        work_steps:
          - id: spawn-action
            actor: pm-agent
            label: dispatch matched signals
            skills: [project-manager]
      - id: idle
        next: scan
        work_steps:
          - id: wait-or-tick
            actor: pm-agent
            label: wait for next tick
            skills: [project-manager]
      - id: stopped
        terminal: true
        # Sink for shutdown / kill. Reached only when the operator
        # halts the monitor — not via any normal route. Required by the
        # well-formedness check; pm-monitor's working loop is
        # `scan → classify → dispatch → idle → scan`.
    routes:
      - id: monitor-tick
        actor: pm-agent
        command: pm-monitor
        trigger: command.pm-monitor
        from: idle
        to: scan
        kind: forward
        label: tick
        skills: [project-manager]
      - id: scan-to-classify
        actor: pm-agent
        trigger: scan.complete
        from: scan
        to: classify
        kind: forward
        label: classify signals
        skills: [project-manager]
      - id: dispatch-launch-session
        actor: pm-agent
        from: classify
        to: dispatch
        trigger: signal.session_unblocked == true
        signals: [signal.session_unblocked]
        kind: forward
        label: launch unblocked session
        skills: [project-manager]
      - id: dispatch-relaunch
        actor: pm-agent
        from: classify
        to: dispatch
        trigger: signal.session_crashed == true
        signals:
          - signal.session_crashed
          - signal.session_paused_question
        kind: forward
        label: relaunch crashed or stuck
        skills: [project-manager]
      - id: dispatch-review
        actor: pm-agent
        from: classify
        to: dispatch
        trigger: signal.session_pr_pair_open == true
        signals: [signal.session_pr_pair_open]
        kind: forward
        label: launch code-review
        skills: [project-manager]
      - id: dispatch-triage
        actor: pm-agent
        from: classify
        to: dispatch
        trigger: signal.inbox_inbound_new == true
        signals:
          - signal.inbox_inbound_new
          - signal.comment_question
        kind: forward
        label: dispatch triage
        skills: [project-manager]
      - id: dispatch-idle
        actor: pm-agent
        from: classify
        to: idle
        trigger: signal.nothing_to_do == true
        signals: [signal.nothing_to_do]
        kind: side
        label: nothing to do
        skills: [project-manager]
      - id: dispatch-to-idle
        actor: pm-agent
        trigger: dispatch.complete
        from: dispatch
        to: idle
        kind: forward
        label: return to idle
        skills: [project-manager]

  # code-review — multi-reviewer cycle. Cross-cutting workflow that
  # takes a coding-session's PR pair through gate-check, three
  # independent reviews (self/superpowers/codex), synthesis, and
  # either merge+node-reconcile or relaunch.
  code-review:
    actor: pm-agent
    trigger: signal.session_pr_pair_open
    statuses:
      - id: received
        next: gate-check
        tripwires:
          - v_freshness
        work_steps:
          - id: confirm-pr-pair
            actor: pm-agent
            label: confirm tripwire-pr + project-pr live
            skills: [project-manager]
      - id: gate-check
        next: independent-reviews
        tripwires:
          - v_artifact_presence
          - v_handoff_artifact
          - v_phase_requirements
        work_steps:
          - id: run-validate-on-branch
            actor: pm-agent
            label: validate on branch
            skills: [project-manager, verification]
          - id: walk-verification-checklist
            actor: pm-agent
            label: walk verification checklist
            skills: []
          - id: write-verified-md
            actor: pm-agent
            label: write verified.md
            skills: []
      - id: independent-reviews
        next: synthesis
        work_steps:
          - id: read-self-review
            actor: pm-agent
            label: read self-review.md
            skills: [project-manager]
          - id: launch-superpowers-subagent
            actor: pm-agent
            label: launch superpowers code-review subagent
            skills: []
          - id: comment-codex-trigger
            actor: pm-agent
            label: comment @codex on project-pr
            skills: []
          - id: collect-review-outputs
            actor: pm-agent
            label: collect three review outputs
            skills: []
      - id: synthesis
        next:
          - if: review.verdict == merge
            then: node-reconcile
          - else: relaunch
        jit_prompts:
          - self-review
        work_steps:
          - id: synthesize-findings
            actor: pm-agent
            label: synthesize three reviews
            skills: [project-manager]
          - id: decide-verdict
            actor: pm-agent
            label: decide merge or relaunch
            skills: []
      - id: node-reconcile
        next: merge
        cross_links:
          - workflow: concept-freshness
            status: detected
            label: trigger node refresh
            kind: triggers
        work_steps:
          - id: identify-touched-nodes
            actor: pm-agent
            label: identify touched nodes
            skills: [project-manager]
          - id: identify-missing-nodes
            actor: pm-agent
            label: identify missing nodes
            skills: []
          - id: update-or-create-nodes
            actor: pm-agent
            label: update or create nodes
            skills: []
          - id: rehash-source-nodes
            actor: pm-agent
            label: rehash source nodes
            skills: []
      - id: merge
        terminal: true
        tripwires:
          - v_done_implies_issue_artifacts_on_main
        work_steps:
          - id: merge-tripwire-pr
            actor: pm-agent
            label: merge tripwire-pr
            skills: [project-manager]
          - id: merge-project-pr
            actor: pm-agent
            label: merge project-pr
            skills: []
          - id: emit-merge-event
            actor: pm-agent
            label: emit merge event
            skills: []
      - id: relaunch
        terminal: true
        cross_links:
          - workflow: coding-session
            status: executing
            label: relaunch agent with findings
            kind: triggers
            pm_subagent_dispatch: true
        work_steps:
          - id: write-pm-followup-artifact
            actor: pm-agent
            label: write PM followup artifact
            skills: [project-manager]
          - id: session-reopen-and-resume
            actor: pm-agent
            label: reopen session and resume coding agent
            skills: []
    routes:
      - id: pr-pair-received
        actor: pm-agent
        trigger: signal.session_pr_pair_open == true
        signals: [signal.session_pr_pair_open]
        from: source:session.in_review
        to: received
        kind: forward
        label: receive PR pair
        skills: [project-manager]
      - id: pass-gate
        actor: pm-agent
        trigger: received.confirmed
        from: received
        to: gate-check
        kind: forward
        label: gate-check
        skills: [project-manager]
      - id: enter-reviews
        actor: pm-agent
        trigger: gate-check.passed
        from: gate-check
        to: independent-reviews
        kind: forward
        label: launch reviewers
        skills: [project-manager]
      - id: enter-synthesis
        actor: pm-agent
        trigger: reviews.collected
        from: independent-reviews
        to: synthesis
        kind: forward
        label: synthesize
        skills: [project-manager]
      - id: route-to-merge
        actor: pm-agent
        command: pm-session-review
        trigger: review.verdict == merge
        from: synthesis
        to: node-reconcile
        kind: forward
        label: route to merge
        controls:
          prompt_checks: [pm-session-review]
        skills: [project-manager]
      - id: route-to-relaunch
        actor: pm-agent
        command: pm-session-review
        trigger: review.verdict == relaunch
        from: synthesis
        to: relaunch
        kind: return
        label: route to relaunch
        controls:
          prompt_checks: [pm-session-review]
        skills: [project-manager]
      - id: do-merge
        actor: pm-agent
        trigger: node-reconcile.complete
        from: node-reconcile
        to: merge
        kind: forward
        label: merge PRs
        skills: [project-manager]

  inbox-handling:
    actor: pm-agent
    trigger: signal.inbox_inbound_new
    statuses:
      - id: pending
        next: triaged
        heuristics:
          - v_concept_name_prose
        work_steps:
          - id: receive-row
            actor: pm-agent
            label: receive inbox row
            skills: [project-manager, agent-messaging]
      - id: triaged
        next: resolved
        tripwires:
          - v_reference_integrity
        prompt_checks: [pm-edit]
        work_steps:
          - id: classify-row
            actor: pm-agent
            label: classify and decide action
            skills: [project-manager]
      - id: resolved
        terminal: true
        work_steps:
          - id: close-row
            actor: pm-agent
            label: close inbox row
            skills: [project-manager]
    routes:
      - id: inbox-receive
        actor: pm-agent
        trigger: signal.inbox_inbound_new == true
        signals: [signal.inbox_inbound_new, signal.comment_question]
        from: source:inbox
        to: pending
        kind: forward
        label: receive
        skills: [project-manager]
      - id: inbox-triage
        actor: pm-agent
        command: pm-edit
        trigger: command.pm-edit
        from: pending
        to: triaged
        kind: forward
        label: triage
        skills: [project-manager]
      - id: inbox-resolve
        actor: pm-agent
        trigger: triage.action_taken
        from: triaged
        to: resolved
        kind: forward
        label: resolve
        skills: [project-manager]

  pr-lifecycle:
    actor: pm-agent
    trigger: pr.opened
    statuses:
      - id: draft
        next: ready
        work_steps:
          - id: open-draft
            actor: coding-agent
            label: open draft PR
            skills: [backend-development]
      - id: ready
        next: reviewing
        tripwires:
          - v_freshness
          - v_handoff_artifact
          - v_comment_provenance
        work_steps:
          - id: mark-ready
            actor: coding-agent
            label: mark ready for review
            skills: [agent-messaging]
      - id: reviewing
        next:
          - if: review.outcome == approved
            then: approved
          - else: rejected
        cross_links:
          - workflow: code-review
            status: received
            label: review consumes PR pair
            kind: triggered_by
        work_steps:
          - id: under-review
            actor: pm-agent
            label: PR under review
            skills: [project-manager]
      - id: approved
        next: merged
        tripwires:
          - v_done_implies_issue_artifacts_on_main
        work_steps:
          - id: hold-approved
            actor: pm-agent
            label: ready to merge
            skills: [project-manager]
      - id: merged
        terminal: true
        work_steps:
          - id: emit-merge
            actor: pm-agent
            label: emit pr.merged event
            skills: [project-manager]
      - id: rejected
        terminal: true
        cross_links:
          - workflow: coding-session
            status: executing
            label: rejection re-enters execution
            kind: triggers
        work_steps:
          - id: hold-rejected
            actor: pm-agent
            label: rejected — relaunch session
            skills: [project-manager]
    routes:
      - id: pr-open
        actor: coding-agent
        trigger: pr.opened
        from: source:branch
        to: draft
        kind: forward
        label: open PR
        skills: [backend-development]
      - id: pr-ready
        actor: coding-agent
        trigger: pr.ready_for_review
        from: draft
        to: ready
        kind: forward
        label: mark ready
        skills: [backend-development]
      - id: pr-enter-review
        actor: pm-agent
        trigger: review.requested
        from: ready
        to: reviewing
        kind: forward
        label: enter review
        skills: [project-manager]
      - id: pr-approve
        actor: pm-agent
        trigger: review.outcome == approved
        from: reviewing
        to: approved
        kind: forward
        label: approve
        skills: [project-manager]
      - id: pr-reject
        actor: pm-agent
        trigger: review.outcome == changes_requested
        from: reviewing
        to: rejected
        kind: return
        label: reject
        skills: [project-manager]
      - id: pr-merge
        actor: pm-agent
        trigger: pr.merge
        from: approved
        to: merged
        kind: forward
        label: merge
        skills: [project-manager]

  phase-advancement:
    actor: pm-agent
    trigger: command.pm-phase
    statuses:
      - id: scoping
        next: scoped
        work_steps:
          - id: in-scoping
            actor: pm-agent
            label: scoping phase work
            skills: [project-manager]
      - id: scoped
        next: executing
        tripwires:
          - v_phase_requirements
        work_steps:
          - id: in-scoped
            actor: pm-agent
            label: scoped — ready to execute
            skills: [project-manager]
      - id: executing
        next: reviewing
        work_steps:
          - id: in-executing
            actor: pm-agent
            label: executing phase work
            skills: [project-manager]
      - id: reviewing
        terminal: true
        tripwires:
          - v_done_implies_issue_artifacts_on_main
        work_steps:
          - id: in-reviewing
            actor: pm-agent
            label: reviewing phase work
            skills: [project-manager]
    routes:
      - id: advance-to-scoped
        actor: pm-agent
        command: pm-phase
        trigger: command.pm-phase
        from: scoping
        to: scoped
        kind: forward
        label: advance to scoped
        skills: [project-manager]
      - id: advance-to-executing
        actor: pm-agent
        command: pm-phase
        trigger: command.pm-phase
        from: scoped
        to: executing
        kind: forward
        label: advance to executing
        skills: [project-manager]
      - id: advance-to-reviewing
        actor: pm-agent
        command: pm-phase
        trigger: command.pm-phase
        from: executing
        to: reviewing
        kind: forward
        label: advance to reviewing
        skills: [project-manager]

  issue-closure:
    actor: pm-agent
    trigger: command.pm-issue-close
    statuses:
      - id: closing
        next: closed
        tripwires:
          - v_done_implies_issue_artifacts_on_main
          - v_done_implies_session_completed
          - v_issue_artifact_presence
        prompt_checks: [pm-issue-close]
        work_steps:
          - id: close-checks
            actor: pm-agent
            label: run close-time checks
            skills: [project-manager]
      - id: closed
        terminal: true
        work_steps:
          - id: emit-closure
            actor: pm-agent
            label: emit closure event
            skills: [project-manager]
    routes:
      - id: issue-close
        actor: pm-agent
        command: pm-issue-close
        trigger: command.pm-issue-close
        from: source:issue
        to: closing
        kind: forward
        label: begin close
        skills: [project-manager]
      - id: issue-finalize
        actor: pm-agent
        trigger: close.checks_passed
        from: closing
        to: closed
        kind: forward
        label: finalize
        skills: [project-manager]

```
