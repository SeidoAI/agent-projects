---
name: superpowers-code-review
description: External-subagent contract for the technical reviewer dispatched by code-review.independent-reviews. Implementation lives outside this repo; tripwire only consumes it.
---

# superpowers-code-review

This skill is a **contract**, not an implementation. Tripwire's
`code-review` workflow dispatches an external "superpowers
code-review" subagent during the `independent-reviews` station. That
subagent's implementation does not ship in this repo. The interface
tripwire requires is documented here so consumers and future
implementations agree on the wire format.

## When tripwire dispatches this subagent

1. `pm-monitor` detects `signal.session_pr_pair_open` (see
   `MONITOR_CRITERIA.md`).
2. `pm-monitor.dispatch` routes to `code-review.received`.
3. The workflow advances to `code-review.independent-reviews`.
4. From `independent-reviews`, the PM dispatches three parallel
   reviews; this subagent is **review 2 of 3** (self-review and
   `@codex` are 1 and 3).

The dispatch is a Claude Code subagent launch with
`pm_subagent_dispatch: true` per `SUBAGENT_DELEGATION.md`. The PM
records the dispatch in `<project>/orchestration/monitor-log.yaml`.

## Input contract

The subagent receives the following payload:

| Field | Type | Description |
|---|---|---|
| `tripwire_pr_url` | string | PR against project tracking repo |
| `project_pr_url` | string | PR against code repo |
| `session_id` | string | the session under review |
| `plan_path` | string | path to `sessions/<id>/plan.md` |
| `self_review_path` | string | path or PR-URL fragment for the agent's four-lens self-review |
| `verification_checklist_path` | string | `templates/skills/verification/CHECKLIST.md` (or pinned variant) |
| `repo_paths` | list[string] | declared touched paths from `session.yaml` |
| `context` | string (optional) | freeform PM hint, e.g. "focus on the websocket layer" |

The subagent is expected to check out the project-pr branch in an
isolated worktree, read the listed inputs, and produce its review
without writing into the project tracking repo.

## Output contract

The subagent writes a single file:

```
<project>/sessions/<session-id>/reviews/superpowers.yaml
```

Schema:

```yaml
verdict: merge | relaunch
findings:
  - severity: blocking | major | minor | nit
    message: string                # one-line description
    file: string (optional)        # path inside project repo
    line: integer (optional)       # 1-indexed
    rationale: string (optional)   # 1-2 sentences if non-obvious
summary: string                    # 1-2 paragraphs, plain text
```

`verdict` is the subagent's recommendation. The PM is not bound by
it — `code-review.synthesis` is where the actual decision is made,
combining this subagent's verdict with self-review and codex.

`findings` may be empty. An empty findings list with
`verdict: merge` and a non-empty `summary` is a valid clean review.

## Out of scope for this skill

- **The detection logic itself** — what patterns the subagent looks
  for, which files it prioritises, how it weighs severity. That is
  the implementation, and it lives outside this repo.
- **Codex review** — separate, triggered by an `@codex` PR comment
  on the project-pr by the PM.
- **The PM's final synthesis** — lives in `code-review.synthesis`,
  not in the subagent. The subagent contributes one of three inputs.
- **Mutating the project repo or PR** — the subagent reads only and
  writes only to its assigned output path.

## See also

- `WORKFLOWS_CODE_REVIEW.md` — the consuming workflow.
- `SUBAGENT_DELEGATION.md` — general subagent dispatch pattern,
  scope token, and return contract.
- `MONITOR_CRITERIA.md` — `signal.session_pr_pair_open` definition.
