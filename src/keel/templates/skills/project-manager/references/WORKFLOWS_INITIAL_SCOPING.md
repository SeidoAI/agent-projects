# Workflow: Initial Scoping

The workflow for transforming raw planning documents into a fully scoped
project — the project-kb-pivot case. You have a directory of markdown
planning docs and need to emit a coherent set of issues, concept nodes,
and sessions that pass validate.

## Precondition

You are in a freshly-init'd `keel` directory. `keel init` creates an
empty `./planning/` subdirectory by default — drop any raw planning
markdown files in there before invoking scoping. Scoping also works
from user intent alone if `./planning/` is empty or missing.

## Procedure

### 1. Front-load context
```bash
keel brief
```
Read the output. Note the `next issue key`, active enums, artifact
manifest, orchestration pattern, template paths, and skill example paths.

### 2. Read the planning docs
Read every `.md` file under `./planning/` in full — you cannot scope
what you haven't read. If `./planning/` is empty or missing, use the
user's intent (passed via `$ARGUMENTS` to `/pm-scope`) as your sole
source and proceed.

### 3. Read the canonical examples
Before writing any file, read at least:
- `examples/issue-fully-formed.yaml`
- `examples/issue-with-references.yaml`
- `examples/node-endpoint.yaml`
- `examples/node-decision.yaml`
- `examples/session-multi-repo.yaml`

The example files are the canonical truth. If your output doesn't look
like them, you're doing it wrong.

### 4. Plan the breakdown
Do NOT start writing files yet. Sketch out (in memory, or in a scratch
note you don't commit):

- **Epics** — the 1-5 top-level themes the planning docs describe.
  These become parent issues (`parent: null`).
- **Issues** — one per concrete unit of work. Each has a parent epic
  (unless it IS an epic), a target repo, and an executor.
- **Concept nodes** — anything referenced by ≥2 issues or crossing a
  repo boundary. Endpoints, models, configs, decisions, contracts. See
  `CONCEPT_GRAPH.md` for the "named bookmark" rule.
- **Sessions** — logical groupings of issues for one agent run. A session
  typically contains 1-5 related issues and spans one wave.

### 5. Allocate IDs
For each new issue you plan to create, call:
```bash
keel next-key --type issue
```
Collect the allocated keys. Do this ONCE per issue — don't hand-pick.

Nodes and sessions use slug ids that you choose (lowercase, letter-first,
hyphenated). Session ids are typically `wave<N>-agent-<x>` or a
descriptive slug like `critical-prod-fix`.

For each entity (issue, node, session, comment), generate a `uuid4`
yourself — don't call any CLI for it.

### 6. Write the files

Write in dependency order so early files can be referenced by later ones:

1. **Concept nodes first** → `graph/nodes/<id>.yaml`. Placeholder `status: planned` nodes for things that don't exist in code yet.
2. **Epic issues** → `issues/<KEY>.yaml`. These are the parents.
3. **Concrete issues** → `issues/<KEY>.yaml`. Reference the epics as `parent`, reference concept nodes via `[[node-id]]` in the body.
4. **Sessions** → `sessions/<id>.yaml`. Reference the issue keys you just created.

Copy the schema from the closest example file. Fill in the real values.
Do not invent fields; do not skip required fields.

### 7. Validate, iterate, validate
```bash
keel validate --strict --format=json
```
Parse the JSON. For each error, map it to a file and fix it. Re-run.
Repeat until `exit_code == 0`.

Common issues on first pass:
- Dangling `[[refs]]` (you referenced something you didn't create)
- Wrong status (you used a status value not in `enums/issue_status.yaml`)
- Missing body section (your issue body doesn't have all required headings)
- Sequence drift (you allocated keys out of order — run `validate --fix`)

### 8. Confirm the shape
```bash
keel status
keel graph --type concept --format=mermaid
keel refs check
```
Sanity-check the dashboard: are the counts what you expected? Does the
concept graph show the structure you intended? Are there orphan nodes?

### 9. Commit
Per `COMMIT_CONVENTIONS.md`. One commit for the whole initial scoping,
branch named something like `pm/initial-scoping`.

## Anti-patterns to avoid

- Writing files before reading any examples.
- Reading schema references but not example files (schema references
  explain *why*; examples are the canonical truth).
- Hand-picking issue keys without `next-key`.
- Referencing nodes that don't exist yet (or worse: inventing node ids
  inline and never creating the node files).
- Skipping the validation gate because "the files look right".

## See also

- `WORKFLOWS_INCREMENTAL_UPDATE.md` for small surgical edits later.
- `CONCEPT_GRAPH.md` for the when-to-create-a-node rule.
- `VALIDATION.md` for interpreting validator errors.
- `ANTI_PATTERNS.md` for the full list of things to avoid.
