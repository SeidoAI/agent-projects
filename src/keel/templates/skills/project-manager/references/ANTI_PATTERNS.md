# Anti-patterns

Things agents get wrong most often. Each one fails validation and
costs you an iteration. Read this once carefully — it'll save hours.

This is the detailed reference for the "five mortal sins" summary in
`SKILL.md`. Read that first for the short list, then come here for the
bad/good examples and the reasoning behind each rule.

## The five mortal sins

1. **Inventing fields not in the schema.** You add `priority_score: 5`
   or `owner: alice` to an issue and the validator rejects it as
   `issue/schema_invalid`. Stick to what's in the example file.

2. **Forgetting to run `validate`** before declaring done. Every batch
   of writes must be followed by `keel validate --strict`.
   No exceptions. It catches 95% of errors before a human or PM
   reviewer has to.

3. **Hand-picking issue keys** instead of calling `next-key`. You
   guess the next key is `SEI-42` based on what you see, write that
   file, and then the validator catches `sequence/drift` because
   `next_issue_number` in `project.yaml` wasn't updated. Use
   `keel next-key --type issue`.

4. **Hand-writing UUIDs.** You put `uuid: 1234` or
   `uuid: some-placeholder` in the frontmatter. The validator rejects
   it. Use a real uuid4 — most languages have a one-liner for it.

5. **Dangling references.** You write `[[user-model]]` in an issue
   body but you haven't created `nodes/user-model.yaml`. The
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

Look at `enums/<name>.yaml` (or run `keel enums show <name>`)
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
`keel brief` first. You miss the current
enum values, the next available ID, the active orchestration pattern,
and the template paths. Running `brief` once at the
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
keel issue create --title "..."
keel node create --id user-model
keel session create --name ...
```

All mutation happens via direct file writes. If you try these, the
CLI will say "no such command" and you'll waste a tool call.

### Running `validate` without `--strict`

Without `--strict`, warnings don't block commit. For an agent loop,
always use `--strict` so warnings and errors are treated the same.
The only exception is when you've already fixed all errors and want
to see warnings as warnings (rare).

### Parsing validate output with inline scripts

Do not write Python one-liners to parse validate JSON output. Use
the built-in format options instead:
- `--format summary` for error-code counts
- `--format compact` for one line per error
- `--count` for just the error count
- `--format text` (default) for human-readable output

### Delegating file writing to subagents

Do not use subagents to write issues, nodes, sessions, or plans. You
must write every file yourself so that you can meaningfully review
your own output in the gap analysis step. A PM agent that delegates
writing has "high structural confidence, low semantic confidence" —
it knows validation passed but can't describe what any given file
contains.

### Quality degradation over time (the fatigue pattern)

Agent output degrades measurably over long writing sessions. In a
60-issue scoping run, the first 20 concrete issues averaged 2,470
characters and 4.0 node references; the last 20 averaged 1,883
characters and 1.5 references — a 24% drop in depth and 63% drop
in cross-referencing.

This mimics human cognitive fatigue from training data. The agent
isn't tired, but it produces progressively thinner output as if it
were.

The quality calibration checkpoint in the scoping workflow counters
this: after every 20 concrete issues, reread the first 3 and last 3,
rewrite the last 3 if they're thinner. The validator also detects
this pattern (`quality/body_degradation`, `quality/ref_degradation`)
and will flag it.

### Surface-level gap analysis

Mapping phases to issue ranges ("P1a → KBP-17–20 | Covered") is a
table of contents, not a gap analysis. Each row must map one specific
deliverable (one endpoint, one migration step, one UI component) to
one specific issue. If you find yourself writing "KBP-X through
KBP-Y," you are not doing the analysis.

## Concept graph mistakes

### Creating nodes for everything

Don't create a node for every function or variable. But **when in
doubt, create the node.** The cost of a node is 30 seconds. The
cost of a missing node is undetected drift. For a coherence tool,
recall matters more than precision.

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

You create a node but never reference it anywhere. `keel refs
check` reports it as an orphan. Either delete the node or add a
reference.

## See also

- `VALIDATION.md` — the full error catalogue
- `examples/*.yaml` — the canonical truths
- `WORKFLOWS_*.md` — the correct procedures
