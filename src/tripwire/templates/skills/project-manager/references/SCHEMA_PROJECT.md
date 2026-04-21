# Schema: project.yaml

The root config file for a tripwire repo. Defines the project's
name, key prefix, repo registry, status flow, enum defaults, and
counters. Read it early in any workflow — everything else references it.

## Fields

```yaml
name: seido-mvp                    # free-form human-readable project name
key_prefix: SEI                    # issue key prefix, must match ^[A-Z][A-Z0-9]*$
description: Seido MVP management  # optional
base_branch: test                  # default branch issues target
environments: [test, prod]         # free list of environment names

# Repo registry — GitHub slug → optional local clone path
repos:
  SeidoAI/web-app-backend:
    local: ~/Code/seido/web-app
  SeidoAI/web-app-frontend:
    local: null                    # null means "fetch via gh api"

# Issue lifecycle states (matches enums/issue_status.yaml)
statuses: [backlog, todo, in_progress, ...]

# Directed graph of allowed status transitions. Every issue's status
# must be reachable from `backlog` via these transitions.
status_transitions:
  backlog: [todo, canceled]
  todo: [in_progress, backlog, canceled]
  ...

# Label categories — project-specific taxonomies on top of the standard fields
label_categories:
  executor: [ai, human, mixed]
  verifier: [required, optional, none]
  domain: []                       # empty means "any label in this category is allowed"
  agent: []

# Concept graph settings
graph:
  node_types: [endpoint, model, config, ...]
  auto_index: true

# Orchestration defaults (project-wide; sessions can override)
orchestration:
  default_pattern: default         # references orchestration/default.yaml
  plan_approval_required: false
  auto_merge_on_pass: false

# Sequential key counters — DO NOT hand-edit. Use `tripwire next-key`.
next_issue_number: 1
next_session_number: 1

created_at: "2026-04-07T10:00:00"
```

## When to update

- **Adding a new repo to the project** — add it under `repos:`
- **Adding a new status** — add it to `statuses` AND `status_transitions`
  (both lists must agree)
- **Changing the default orchestration pattern** — update
  `orchestration.default_pattern` to a different pattern name
- **Flipping `plan_approval_required`** or `auto_merge_on_pass` — update
  under `orchestration:`

## When NOT to update

- **`next_issue_number` / `next_session_number`** — use
  `tripwire next-key`. Hand-editing these causes sequence drift
  that the validator catches but is a waste of an iteration.
- **Removing statuses that issues are currently in** — you'll create
  unreachable-status errors.

## See also

- `examples/issue-fully-formed.yaml` for how issues reference project fields
- `ID_ALLOCATION.md` for the counter discipline
- `CONCEPT_GRAPH.md` for the `graph:` settings
