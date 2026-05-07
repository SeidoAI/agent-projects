# Anti-patterns

Detailed reference for the "five mortal sins" in `SKILL.md`. Read that
first for the short list, then this for examples.

## The five mortal sins (with examples)

1. **Inventing fields.** Adding `priority_score: 5` or `owner: alice`
   triggers `issue/schema_invalid`. Stick to the example file.
2. **Skipping `validate`** after a batch of writes. It catches 95% of
   errors before a reviewer sees them.
3. **Hand-picking issue keys** instead of `tripwire next-key
   --type issue`. Drift in `next_issue_number` → `sequence/drift`.
4. **Hand-writing UUIDs** like `uuid: 1234`. Use a real uuid4.
5. **Dangling references.** `[[user-model]]` in a body without
   `nodes/user-model.yaml` → `ref/dangling`.

## Field-level mistakes

**Writing `blocks` by hand.** It's computed from inverse `blocked_by`.
Manual entries drift. Leave it empty.

**Invalid enum values.** `status: in-progress` (should be underscore),
`priority: very-high` (not in enum). Run `tripwire enums show <name>`
or read `templates/enums/<name>.yaml`.

**Bad timestamp format.** ISO 8601 only:
`created_at: "2026-04-07T10:00:00"`. Validator uses
`datetime.fromisoformat`.

**Wrong ID format.** Issues match `^[A-Z][A-Z0-9]*-\d+$`
(`SEI-42` ✓, `sei-42` / `SEI_42` / `SEI 42` / `SEI-42.0` ✗). Nodes &
sessions match `^[a-z][a-z0-9-]*$`.

## Workflow mistakes

- **Skipping `tripwire brief`** at session start. Missing it costs
  you the active enums, next ID, orchestration pattern, and template
  paths.
- **Reading only schemas, not examples.** Schemas explain WHY;
  `examples/*.yaml` is canonical for shape. Always read the example.
- **Validating only at the end.** Batch of 3-5 files, then validate.
  Schema mistakes compound otherwise.
- **Trying mutation CLIs.** `tripwire issue create` etc. don't exist;
  all mutation is direct file writes.
- **Parsing validate output with inline Python.** Use `--format
  summary`, `--format compact`, or `--count`.
- **Delegating writes to subagents.** You lose the ability to
  meaningfully gap-analyse your own work — high structural
  confidence, low semantic confidence.
- **Quality fatigue.** Output measurably thins over a long run. See
  the calibration checkpoint in `WORKFLOWS_INITIAL_SCOPING.md` §6.
  Validator codes: `quality/body_degradation`, `quality/ref_degradation`.
- **Surface-level gap analysis.** Mapping ranges ("KBP-17–20 |
  Covered") is a TOC. Each row maps one deliverable to one issue.

## Concept graph mistakes

- **Node spam.** Don't node every function. But **when in doubt,
  create the node** — recall matters more than precision.
- **Zero refs in an issue.** `body/no_references` warns. Reference
  the relevant nodes.
- **Forgetting to rehash.** Edit code at a node's source → update
  `content_hash`. Otherwise `freshness/stale`.
- **Orphan nodes.** Created but never referenced. Delete or reference.

## See also

- `VALIDATION.md` — full error catalogue
- `examples/*.yaml` — canonical shapes
- `WORKFLOWS_*.md` — procedures
