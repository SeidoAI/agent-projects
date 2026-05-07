# Validation Gate

`tripwire validate` is the gate you must pass after every batch of
writes before declaring work done.

## Error code reference

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
| `manifest_schema/produced_by_valid` | error | no | v0.6a — `produced_by` isn't a known agent type |
| `manifest_schema/owned_by_valid` | error | no | v0.6a — `owned_by` isn't a known agent type |
| `manifest_schema/phase_ownership_consistent` | warning | no | v0.6a — PM owns an artifact produced at implementing/verifying |
| `handoff_schema/required_at_queued` | error | no | v0.6a — session in `queued` but `handoff.yaml` missing |
| `handoff_schema/branch_format` | error | no | v0.6a — `handoff.yaml.branch` violates `<type>/<slug>` convention |
| `handoff_schema/malformed` | error | no | v0.6a — `handoff.yaml` failed to parse or validate |
| `spawn/not_queued` | error | no | v0.6c — session status isn't `queued` (or `failed`/`paused` without `--resume`) |
| `spawn/worktree_path_exists` | error | no | v0.6c — worktree dir exists without `--resume` |
| `spawn/worktree_missing` | error | no | v0.6c — `--resume` but worktree no longer on disk |
| `spawn/branch_checked_out` | error | no | v0.6c — branch already checked out in another worktree |
| `spawn/claude_not_on_path` | error | no | v0.6c — `which claude` empty |
| `spawn/repo_not_cloned` | error | no | v0.6c — session repo has no local clone |
| `pause/not_executing` | error | no | v0.6c — session isn't executing |
| `pause/process_not_found` | warning | no | v0.6c — PID doesn't exist (process already dead) |
| `abandon/already_terminal` | error | no | v0.6c — session is `completed` or `abandoned` |
| `cleanup/worktree_dirty` | warning | no | v0.6c — uncommitted changes without `--force` |
| `agenda/cycle_detected` | error | no | v0.6c — circular dependency in `blocked_by_sessions` |
| `agenda/orphan_blocker` | warning | no | v0.6c — blocker references nonexistent session |

## Running it

```bash
tripwire validate                # default text output
tripwire validate --format json  # structured; parse the errors[]
```

Warnings (heuristics) surface in output by default. (Stage 2's
`--heuristics-as-tripwires` will fail on heuristic hits — currently a
no-op.) Validate always rebuilds `nodes/tripwire-graph-index.yaml` as a side effect.

**Exit codes:** 0 = clean · 1 = warnings only (reserved for stage 2) ·
2 = errors. Loop: write → validate → fix → validate → 0 → commit.

## JSON output

```json
{
  "version": 1,
  "exit_code": 2,
  "summary": {"errors": 3, "warnings": 1, "fixed": 0, "cache_rebuilt": true, "duration_ms": 42},
  "errors": [
    {
      "code": "ref/dangling",
      "severity": "error",
      "file": "issues/SEI-42.yaml",
      "line": 18,
      "field": "body",
      "message": "Reference [[user-modle]] does not resolve.",
      "fix_hint": "Did you mean [[user-model]]?"
    }
  ],
  "warnings": [], "fixed": []
}
```

Per error: `file` + `field` locate it; `message` describes; `fix_hint`
suggests (when available); `code` is stable.

## Frequent error codes

The table above is exhaustive; this section only adds notes for codes
that need them.

- `enum/*` — value not in the active enum. Check
  `templates/enums/<name>.yaml` for the allowed set.
- `ref/dangling` — `[[ref]]` doesn't resolve to a node or issue.
  `fix_hint` may suggest a typo correction.
- `body/no_references` — issue has zero `[[node-id]]` references; usually
  a real coherence gap, not a typo.
- `status/unreachable` — status is not reachable from `backlog` via
  declared transitions in `project.yaml`.
- `freshness/stale` — node `content_hash` doesn't match live content.
  Warning. Auto-fixable when the node is the source-of-truth.
- `quality/body_degradation` / `quality/ref_degradation` — last-third
  of concrete issues are >20% shorter or have >40% fewer node refs
  than first-third. Run the quality-calibration checkpoint
  (WORKFLOWS_INITIAL_SCOPING.md §6).
- `phase/missing_artifact`, `phase/incomplete_artifact`,
  `phase/missing_session_plan` — phase gates didn't pass; can't
  advance until artifacts are present and marked
  `<!-- status: complete -->`.

## Auto-fix (`--fix`)

```bash
tripwire validate --fix
```

Repairs:

- Missing `created_at` / `updated_at` (from file mtime)
- Drifted `next_issue_number` (bumped past max key)
- Missing `uuid` (uuid4 generated)
- `bidi/related` mismatches (back-edge added)
- `sorted/list` normalisation (`labels`, `related`, `tags`)
- Stale graph cache (rebuilt)

Does NOT touch issue body content, reference targets, or anything
semantic. Re-run without `--fix` to confirm clean.

If the same error recurs after fixing, you misread the schema. Re-read
the matching `SCHEMA_*.md` and example file.

## `tripwire lint` — heuristic checks (v0.6a+)

Distinct from `tripwire validate`. Validate is mechanical (schema/refs);
lint is heuristic (did someone actually do the work at each stage).

```bash
tripwire lint scoping              # project-level scoping checks
tripwire lint handoff <session-id> # handoff-readiness checks
tripwire lint session <session-id> # in-flight session health checks
```

Exit codes: 0 (info-only), 1 (warning present), 2 (error present).

| Rule | Stage | Severity |
|---|---|---|
| `lint/gap_analysis_row_density` | scoping | warning |
| `lint/concept_drift` | scoping | warning |
| `lint/unpushed_promotion_candidates` | scoping | info (warning when workspace linked — v0.6b) |
| `lint/branch_convention` | handoff | error |
| `lint/session_stale` | session | warning |

See `BRANCH_NAMING.md` for the branch-convention rule.

## See also

- `SCHEMA_*.md` — the schemas the validator checks against
- `ANTI_PATTERNS.md` — common mistakes that trigger errors
- `REFERENCES.md` — `[[ref]]` resolution rules
- `BRANCH_NAMING.md` — per-session branch convention (v0.6a+)
