# Validation Gate

`keel validate` is the single most important command you run.
It's the gate you must pass after every batch of file writes before
declaring any work done.

## Error code quick reference

| Code prefix | Severity | Auto-fixable | Covers |
|---|---|---|---|
| `schema/` | error | no | YAML parsing + Pydantic validation |
| `issue/*`, `node/*`, `session/*`, `comment/*` | error | no | Per-entity load errors (parse, schema, io) |
| `uuid/missing` | error | yes (`fix_uuid`) | Entity without a `uuid` field |
| `uuid/not_v4` | error | no | UUID that isn't RFC 4122 v4 |
| `ref/dangling` | error | no | `[[ref]]` pointing to unknown node/issue |
| `ref/bidirectional_mismatch` | error | yes | Node.related missing back-edge |
| `ref/blocked_by`, `ref/session_issue`, `ref/comment_issue` | error | no | Link to unknown entity |
| `body/*` | error | no | Required headings missing from issue body |
| `enum/*` | error | no | Value outside the active enum |
| `collision/id` | error | no | Two entities share an `id` |
| `sequence/drift` | error | yes | `next_issue_number` below observed max |
| `timestamp/missing` | error | yes | Entity missing `created_at`/`updated_at` |
| `sorted/list` | fixed | yes | List fields sorted in place |
| `bidi/related` | fixed | yes | Back-reference added to related node |
| `phase/*` | error | no | Phase transition gate (artifacts, plans) |
| `quality/*` | warning | no | Output-degradation heuristics (anti-fatigue) |
| `coverage/*` | warning | no | Semantic-gap heuristics (unreferenced nodes, etc.) |
| `freshness/*` | warning | yes | Source hash vs stored hash mismatch |
| `standards/missing` | warning | no | A file references `standards.md` but it doesn't exist |
| `artifact/missing` | error | no | Completed session missing a required artifact |
| `fix/lock_timeout` | error | no | Concurrent `--fix` couldn't acquire the project lock |

## The one command

```bash
keel validate --strict
```

- `--strict` promotes warnings to errors (your normal mode)
- `--format=json` gives you a structured report you can parse

It always rebuilds `graph/index.yaml` as a side effect. No separate
`refs rebuild` needed.

## Exit codes

- **0** — clean
- **1** — warnings only (only possible without `--strict`)
- **2** — one or more errors

Your loop is: write files → validate → fix errors → validate → fix
errors → validate → exit 0 → commit.

## JSON output schema

```json
{
  "version": 1,
  "exit_code": 2,
  "summary": {
    "errors": 3,
    "warnings": 1,
    "fixed": 0,
    "cache_rebuilt": true,
    "duration_ms": 42
  },
  "errors": [
    {
      "code": "ref/dangling",
      "severity": "error",
      "file": "issues/SEI-42.yaml",
      "line": 18,
      "field": "body",
      "message": "Reference [[user-modle]] does not resolve to any node or issue.",
      "fix_hint": "Did you mean [[user-model]]? Or create a node 'user-modle' in nodes/."
    }
  ],
  "warnings": [],
  "fixed": []
}
```

Parse the `errors` array. For each error:

1. `file` tells you which file has the problem
2. `field` tells you which frontmatter field (or `body`)
3. `message` is a human-readable description
4. `fix_hint` is a suggested fix (not always present)
5. `code` is the stable error identifier

Fix the file, re-run, continue.

## Error codes you'll see often

### Schema errors
- `schema/project_missing` — `project.yaml` not found. Run `init`.
- `schema/project_invalid` — `project.yaml` doesn't parse or match the model.
- `issue/parse_error` — frontmatter+body parser failed on an issue file.
- `issue/schema_invalid` — fields don't match the Issue model (wrong
  types, missing required, extra fields).
- `node/schema_invalid`, `session/schema_invalid` — same for nodes, sessions.

### UUID and ID errors
- `uuid/missing` — entity has no `uuid` field. Add a uuid4.
- `id/format` — issue id isn't in `<PREFIX>-<N>` form.
- `id/wrong_prefix` — issue id has the wrong prefix (compare with
  `project.yaml.key_prefix`).

### Enum errors
- `enum/issue_status`, `enum/priority`, `enum/executor`, `enum/verifier`,
  `enum/node_type`, `enum/node_status`, `enum/session_status`,
  `enum/agent_state`, `enum/comment_type` — value not in the active enum.
  Check `enums/<name>.yaml`.

### Reference errors
- `ref/dangling` — `[[reference]]` doesn't resolve to a node or issue.
- `ref/blocked_by` — `blocked_by: [X]` references a non-existent issue.
- `ref/parent` — `parent: X` references a non-existent issue.
- `ref/related` — node `related: [X]` references a non-existent node.
- `ref/repo` — a repo isn't declared in `project.yaml.repos`.
- `ref/session_issue` — session `issues: [X]` references a non-existent issue.
- `ref/session_agent` — session `agent: X` has no matching file in `agents/`.
- `ref/comment_issue` — comment `issue_key: X` references a non-existent issue.

### Body structure (warnings)
- `body/missing_heading` — required Markdown section missing.
- `body/no_acceptance_checkbox` — Acceptance criteria has no `- [ ]` items.
- `body/no_stop_and_ask` — body missing "stop and ask" guidance.
- `body/no_references` — issue has zero concept node references (coherence gap).

### Bi-directional (warnings)
- `bidi/related` — node A declares `related: [B]` but B doesn't
  reciprocate. Auto-fixable.

### Status, freshness, artifacts
- `status/unreachable` — issue status not reachable from `backlog` via
  declared transitions.
- `freshness/source_missing` — active node with a source, file can't
  be fetched.
- `freshness/stale` — node's `content_hash` doesn't match the live
  content (warning).
- `artifact/missing` — completed session missing a required artifact.

### Quality consistency (warnings)
- `quality/body_degradation` — last-third of concrete issues (sorted by
  key) are >20% shorter than first-third. Indicates output quality
  degrading over the session. Run the quality calibration checkpoint.
- `quality/ref_degradation` — last-third of concrete issues have >40%
  fewer unique `[[node-id]]` references than first-third. Add refs to
  later issues.

### Phase requirements
- `phase/missing_artifact` — a phase-required artifact is missing.
- `phase/incomplete_artifact` — artifact exists but not marked
  `<!-- status: complete -->`.
- `phase/missing_session_plan` — session directory has no `plan.md`.

### Counters and timestamps
- `sequence/drift` — `next_issue_number` behind max existing key
  (warning, auto-fixable).
- `timestamp/missing` — `created_at` or `updated_at` missing (warning,
  auto-fixable from mtime).
- `timestamp/invalid` — timestamp isn't parseable as ISO datetime.

### Collisions
- `collision/id` — two files claim the same id with different uuids.

### Cache
- `cache/rebuild_failed` — the cache couldn't be rebuilt (warning).

## Auto-fix (`--fix`)

```bash
keel validate --strict --fix
```

Safely repairs:

- Missing `created_at` / `updated_at` — filled from file mtime
- Drifted `next_issue_number` — bumped past max existing key
- Missing `uuid` — uuid4 generated and added
- Bi-directional `related` mismatches — missing side added
- Sorted-list normalisation — `labels`, `related`, `tags` sorted
- Stale graph cache — rebuilt

Does NOT touch:

- Issue body content (no field invention)
- Reference targets (you decide what to reference)
- Anything that affects semantic intent

After a `--fix` pass, re-run `validate` without `--fix` to confirm
the project is clean.

## The iteration loop

```
write files
validate → N errors
fix errors based on JSON output
validate → M errors (M < N)
fix errors
validate → 0 errors
commit
```

If you find yourself stuck (same error recurring), you've probably
misread the schema. Re-read the relevant `SCHEMA_*.md` and the
matching example file.

## See also

- `SCHEMA_*.md` — the schemas the validator checks against
- `ANTI_PATTERNS.md` — common mistakes that trigger errors
- `REFERENCES.md` — `[[ref]]` resolution rules
