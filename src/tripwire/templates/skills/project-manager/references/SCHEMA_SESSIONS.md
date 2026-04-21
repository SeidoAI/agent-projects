# Schema: Agent Sessions

Sessions live at `sessions/<id>/session.yaml`. A session is the
persistence anchor for one logical agent invocation that may span many
container restarts (re-engagements). The canonical examples are
`examples/session-single-issue.yaml` and
`examples/session-multi-repo.yaml` — both show the YAML content, which
lives inside the session's directory.

## Directory layout

Each session is a directory containing:

```
sessions/<id>/
├── session.yaml       # the session definition (this schema)
├── plan.md            # the implementation plan (required before
│                      # phase `executing`)
├── artifacts/         # session artifacts produced during execution
│   ├── plan.md
│   ├── task-checklist.md
│   └── verification-checklist.md
└── comments/          # session-level messages (optional)
```

The directory name must match the session's `id` field.

## Frontmatter fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `uuid` | UUID4 | yes | Agent-generated canonical identity. |
| `id` | string | yes | Slug (e.g. `auth-endpoint`). Matches the session directory name. |
| `name` | string | yes | Human-readable session name. |
| `agent` | string | yes | Agent definition id; must match a file in `agents/`. |
| `issues` | list[string] | no | Issue keys this session works on. |
| `repos` | list[RepoBinding] | no | Multi-repo: every repo the session can branch and PR in. |
| `docs` | list[string] or null | no | Session-level extra docs. |
| `estimated_size` | string | no | Free-form (e.g. `small`, `medium`, `large`). |
| `blocked_by_sessions` | list[string] | no | Other session ids that must complete first. |
| `key_files` | list[string] | no | Files the session is expected to touch. |
| `grouping_rationale` | string | no | Why these issues are grouped. |
| `status` | string | yes | Must be in `enums/session_status.yaml`. Default `planned`. |
| `current_state` | string or null | no | Latest `AgentState` from a status message. |
| `orchestration` | SessionOrchestration or null | no | Per-session orchestration override. |
| `artifact_overrides` | list[ArtifactSpec] | no | Per-session artifact overrides. |
| `runtime_state` | RuntimeState | no | Session-wide handles (Claude session id, etc.). |
| `engagements` | list[EngagementEntry] | no | Append-only log of every container start. |
| `created_at` | ISO datetime | no | |
| `updated_at` | ISO datetime | no | |
| `created_by` | string | no | |

## RepoBinding

Each entry under `repos:` is a binding to one repo:

```yaml
repos:
  - repo: SeidoAI/web-app-backend    # GitHub slug (required)
    base_branch: test                # required
    branch: claude/SEI-42-auth       # null until the agent pushes
    pr_number: 42                    # null until the PR is opened
```

**All repos in a session are equal.** There is no primary. The agent
treats them symmetrically, can branch in any, and can open PRs against
any. The session tracks one branch and one PR per repo.

## RuntimeState

Session-wide runtime handles persisted across container restarts:

```yaml
runtime_state:
  claude_session_id: "sess_abc123"    # for `claude --resume`
  langgraph_thread_id: null           # for LangGraph checkpoint resume
  workspace_volume: "vol-api-endpoints-core"  # Docker volume name
```

Per-repo branch and PR number live in the `RepoBinding` entries above
— not in `runtime_state`.

## EngagementEntry

Every container start appends one entry:

```yaml
engagements:
  - started_at: "2026-04-07T14:00:00"
    trigger: initial_launch
    ended_at: "2026-04-07T16:30:00"
    outcome: pr_opened
  - started_at: "2026-04-07T17:15:00"
    trigger: ci_failure
    context: "Lint failure in src/api/auth.py:45 — ruff E302"
    ended_at: "2026-04-07T17:25:00"
    outcome: fix_pushed
```

Append-only — never rewrite past entries.

## SessionOrchestration (optional override)

Default: use `project.yaml.orchestration`. To override per session:

```yaml
orchestration:
  pattern: strict                    # use a different named pattern, OR
  overrides:                         # override individual fields
    plan_approval_required: true
    auto_merge_on_pass: false
```

Session-level fields win over project-level fields. No deeper merging —
straight field-level override.

## File path

`<project>/sessions/<id>/session.yaml`. The directory name must match
the session's `id` field. See "Directory layout" above for the full
structure.

## `handoff.yaml` (v0.6a+)

Written by the PM agent at session launch via `/pm-session-launch`.
Lives at `sessions/<id>/handoff.yaml`. **Required when the session
is in `queued` state** (validator rule `handoff_schema/required_at_queued`).

### Fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `uuid` | UUID | yes | Unique per handoff record |
| `session_id` | string | yes | Matches the session's `id` |
| `handoff_at` | datetime | yes | ISO 8601 UTC |
| `handed_off_by` | enum | yes | One of `pm`, `execution-agent`, `verification-agent` |
| `branch` | string | yes | `<type>/<slug>` per `BRANCH_NAMING.md` |
| `open_questions` | list[string] | no | Things the PM couldn't resolve during scoping |
| `context_to_preserve` | list[string] | no | Decisions made at handoff the next agent needs |
| `last_verification_passed_at` | datetime | no | For iterative handoffs |
| `workspace_context` | object | no | Optional; populated if project has a workspace pointer (v0.6b) |

### Example

```yaml
---
uuid: 8b7c6d5e-4f3a-2b1c-9d8e-7f6a5b4c3d2e
session_id: session-auth-42-setup
handoff_at: 2026-04-15T14:30:00Z
handed_off_by: pm
branch: feat/auth-42-setup
open_questions:
  - "Should retries be exponential or fixed?"
context_to_preserve:
  - "Bucket naming uses {{env}}-{{service}} convention (decided 2026-04-14)"
last_verification_passed_at: null
---
```

### Who writes what

- `/pm-session-create` writes the initial version with `branch` filled
  in from `tripwire session derive-branch` output.
- `/pm-session-launch` validates readiness and confirms; it does not
  rewrite the handoff record.
- Execution agents read `handoff.yaml` first thing on start.

## See also

- `examples/session-single-issue.yaml`
- `examples/session-multi-repo.yaml`
- `CONCEPT_GRAPH.md` if the session touches concept nodes
- `BRANCH_NAMING.md` for the per-session branch convention
