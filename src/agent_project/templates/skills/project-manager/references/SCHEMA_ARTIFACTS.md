# Schema: Session Artifacts

Session artifacts are the structured outputs a coding agent produces
during a session. They live at `sessions/<id>/artifacts/<file>` and
their shape is declared in `templates/artifacts/manifest.yaml`.

## The manifest

`templates/artifacts/manifest.yaml` declares every artifact every
session must produce. The default ships five:

```yaml
artifacts:
  - name: plan
    file: plan.md
    template: plan.md.j2
    produced_at: planning
    required: true
    approval_gate: false

  - name: task-checklist
    file: task-checklist.md
    template: task-checklist.md.j2
    produced_at: planning
    required: true
    approval_gate: false

  - name: verification-checklist
    file: verification-checklist.md
    template: verification-checklist.md.j2
    produced_at: planning
    required: true
    approval_gate: false

  - name: recommended-testing-plan
    file: recommended-testing-plan.md
    template: recommended-testing-plan.md.j2
    produced_at: completion
    required: true
    approval_gate: false

  - name: post-completion-comments
    file: post-completion-comments.md
    template: post-completion-comments.md.j2
    produced_at: completion
    required: true
    approval_gate: false
```

## Fields

- `name` — short identifier used when referring to the artifact (e.g.
  in `agent-project artifacts show wave1-a plan`).
- `file` — the actual filename under `sessions/<id>/artifacts/`.
- `template` — the Jinja template in `templates/artifacts/` the agent
  renders from.
- `produced_at` — when in the session lifecycle the artifact is written
  (`planning` or `completion`, or a project-defined phase).
- `required` — if `true`, the validator errors if this artifact is
  missing for a `completed` session.
- `approval_gate` — if `true`, after writing this artifact the agent
  must stop and wait for a human to approve via a blocking message.
  (The orchestration runtime implements the actual gate; v0's validator
  just checks presence.)

## The five default artifacts

1. **`plan.md`** — the agent's implementation plan, written during the
   planning phase. Equivalent to Claude Code's internal plan output but
   committed to git. Set `approval_gate: true` to require human
   approval before the agent writes any code.

2. **`task-checklist.md`** — a living markdown table the agent updates
   as work progresses. Columns: task, status (`pending`, `in_progress`,
   `done`, `blocked`, `skipped`), comments. Humans can glance at it to
   see where the agent is.

3. **`verification-checklist.md`** — generated at planning time, ticked
   off at the end. The final gate the agent walks through before
   declaring the session done.

4. **`recommended-testing-plan.md`** — written at completion. Tells the
   human reviewer what to test manually or in higher environments,
   beyond what CI covers.

5. **`post-completion-comments.md`** — reflective notes at the very end.
   Decisions made, things deferred, surprises, follow-up suggestions.
   The PM agent uses this for triage.

## Project customisation

Projects can:

- Add new artifacts by editing `templates/artifacts/manifest.yaml` and
  adding a corresponding `<name>.md.j2` template under
  `templates/artifacts/`.
- Remove artifacts by setting `required: false` or deleting the entry.
- Flip approval gates via `approval_gate: true/false`.
- Reshape templates by editing the `.j2` files — agents render them at
  runtime.

## Per-session overrides

Sessions can override the project manifest via
`session.artifact_overrides`:

```yaml
artifact_overrides:
  - name: architecture-diff
    file: architecture-diff.md
    produced_at: completion
    required: true
```

This adds a session-specific artifact on top of the project defaults,
or can override an existing entry.

## See also

- `examples/artifacts/plan.md` — worked example of a full plan
- `examples/artifacts/task-checklist.md` — worked example with a mid-session state
- `examples/artifacts/verification-checklist.md` — worked example at completion
- `templates/artifacts/*.j2` — the runtime templates agents render from
