# Anti-patterns

Things agents get wrong most often. Each one fails validation and
costs you an iteration. Read this once carefully — it'll save hours.

## The five mortal sins

1. **Inventing fields not in the schema.** You add `priority_score: 5`
   or `owner: alice` to an issue and the validator rejects it as
   `issue/schema_invalid`. Stick to what's in the example file.

2. **Forgetting to run `validate`** before declaring done. Every batch
   of writes must be followed by `agent-project validate --strict`.
   No exceptions. It catches 95% of errors before a human or PM
   reviewer has to.

3. **Hand-picking issue keys** instead of calling `next-key`. You
   guess the next key is `SEI-42` based on what you see, write that
   file, and then the validator catches `sequence/drift` because
   `next_issue_number` in `project.yaml` wasn't updated. Use
   `agent-project next-key --type issue`.

4. **Hand-writing UUIDs.** You put `uuid: 1234` or
   `uuid: some-placeholder` in the frontmatter. The validator rejects
   it. Use a real uuid4 — most languages have a one-liner for it.

5. **Dangling references.** You write `[[user-model]]` in an issue
   body but you haven't created `graph/nodes/user-model.yaml`. The
   validator reports `ref/dangling`. Either create the node or fix
   the reference.

## Field-level mistakes

### Writing `blocks` by hand

```yaml
# BAD
id: SEI-40
blocks: [SEI-42, SEI-45]   # don't write this

# GOOD
id: SEI-40
# leave `blocks` empty — the validator computes it from inverse blocked_by
```

`blocks` is computed by the validator from inverse `blocked_by`.
Writing it manually creates drift when other issues change.

### Invalid enum values

```yaml
# BAD
status: in-progress    # hyphen wrong, should be underscore
priority: very-high    # not in the enum

# GOOD
status: in_progress
priority: high
```

Look at `enums/<name>.yaml` (or run `agent-project enums show <name>`)
to see the exact allowed values.

### Bad timestamp format

```yaml
# BAD
created_at: "yesterday"
created_at: "2026/04/07 10:00"
created_at: "Apr 7, 2026"

# GOOD
created_at: "2026-04-07T10:00:00"
```

ISO 8601. The validator parses with `datetime.fromisoformat` — if it
can't parse, `timestamp/invalid`.

### Wrong ID format

```yaml
# BAD
id: sei-42             # lowercase prefix
id: SEI_42             # underscore instead of hyphen
id: SEI 42             # space
id: SEI-42.0           # not an integer suffix

# GOOD
id: SEI-42
```

Pattern: `^[A-Z][A-Z0-9]*-\d+$` for issues, `^[a-z][a-z0-9-]*$` for
nodes and sessions.

## Workflow mistakes

### Skipping the scaffold

Jumping straight into writing files without running
`agent-project scaffold-for-creation` first. You miss the current
enum values, the next available ID, the active orchestration pattern,
and the template paths. Running `scaffold-for-creation` once at the
top of every session is free and catches 90% of misalignment early.

### Reading only schema docs, not examples

Schema docs (`SCHEMA_*.md`) explain WHY. Example files
(`examples/*.yaml`) are canonical truth for the shape. Always read the
example for the entity type you're creating — it's the most reliable
guide.

### Writing all files before validating

You scope out a project, write 25 issues + 15 nodes + 3 sessions, THEN
run validate and get 50 errors. Better: write the first 3 files, run
validate, fix, continue. Catches schema mistakes before you repeat
them 25 times.

### Trying to use mutation CLI commands

```bash
# These don't exist in v0:
agent-project issue create --title "..."
agent-project node create --id user-model
agent-project session create --name ...
```

All mutation happens via direct file writes. If you try these, the
CLI will say "no such command" and you'll waste a tool call.

### Running `validate` without `--strict`

Without `--strict`, warnings don't block commit. For an agent loop,
always use `--strict` so warnings and errors are treated the same.
The only exception is when you've already fixed all errors and want
to see warnings as warnings (rare).

### Running `validate` without `--format=json`

Without `--format=json`, you get human-readable text that's harder to
parse programmatically. Use `--format=json` so you can loop over
errors, map them to files, and fix them without fuzzy string matching.

## Concept graph mistakes

### Creating nodes for everything

Don't create a node for every function or variable. The rule is
**referenced by 2+ issues OR crossing a repo boundary**. A helper
function used in one place is inline prose, not a node.

### Creating nodes for nothing

The opposite failure: writing issues with zero references. The
validator warns (`body/no_references`) because it's a strong coherence
gap signal. Your issue body should reference the relevant concept
nodes.

### Forgetting to rehash

You edit code that a node points at, but don't update the node's
`content_hash`. The freshness check then flags it as stale. When you
touch code at a node's source, rehash the node.

### Orphan nodes

You create a node but never reference it anywhere. `agent-project refs
check` reports it as an orphan. Either delete the node or add a
reference.

## See also

- `VALIDATION.md` — the full error catalogue
- `examples/*.yaml` — the canonical truths
- `WORKFLOWS_*.md` — the correct procedures
