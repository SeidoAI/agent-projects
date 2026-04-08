# ID Allocation: Dual UUID + Sequential Keys

Every entity in the system carries two identifiers:

- A canonical `uuid` (UUID4, agent-generated, never changes)
- A human-readable `id` (sequential or slug, possibly renamed on
  collision)

Both live in the frontmatter. The dual model is deliberate — see the
rationale below.

## UUIDs

**Agents generate their own UUIDs.** No CLI call needed. Use any uuid4
library or the stdlib `uuid.uuid4()` equivalent. Put the result in the
`uuid:` field at the **top** of the frontmatter.

Example: `uuid: 7c3a4b1d-9f2e-4a8c-b5d6-1e2f3a4b5c6d`

**Do NOT hand-write UUIDs.** The validator rejects non-UUID4 values.
Two agents picking the same UUID is astronomically unlikely (~2^122
collision space), so there's no coordination needed between parallel
agents.

## Sequential issue keys

Issues carry a human-readable `<PREFIX>-<N>` key (e.g. `SEI-42`).
**Allocate keys via the CLI:**

```bash
agent-project next-key --type issue
# → SEI-42
```

For a batch of N issues, use `--count N`:

```bash
agent-project next-key --type issue --count 5
# → SEI-42
# → SEI-43
# → SEI-44
# → SEI-45
# → SEI-46
```

The CLI takes a file lock on `project.yaml`, reads `next_issue_number`,
increments by `count`, writes back, releases the lock, and returns the
allocated keys on stdout. This is atomic across concurrent callers —
safe even if other agents are running in parallel.

**Do NOT**:
- Hand-pick issue keys (causes sequence drift the validator catches)
- Read `project.yaml.next_issue_number` yourself and increment it
- Reuse a key you've already used

## Session and node ids

Sessions and concept nodes use **slug ids** that you pick yourself. No
CLI call needed.

Rules:

- **Node ids** — lowercase, start with a letter, letters/digits/hyphens.
  Examples: `user-model`, `auth-token-endpoint`, `dec-003-session-tokens`.
- **Session ids** — same slug format. Examples: `wave1-agent-a`,
  `critical-prod-fix`, `auth-epic-kickoff`.
- The filename (minus `.yaml`) must exactly match the `id` field.

`next-key --type session` exists and returns a `<PREFIX>-S<N>` form,
but in v0 sessions are typically slug-based and don't use it. Most
projects will never call it.

## Conflict resolution

Key collisions are rare but possible across branches merged
independently. If two files claim the same `id` with different `uuid`s,
the validator detects it as `collision/id` and (with `--fix`) renames
one of the files to the next free key while updating references.

You don't have to handle collisions manually — the validator does it.
Just make sure you always generate a fresh `uuid` so the system can
tell entities apart.

## Why dual ID?

- **Human readability**: `[[user-model]]` and `SEI-42` are what humans
  and agents use in prose, branch names, commit messages, and PR
  titles. UUIDs are not memorable.
- **Backwards compatibility**: Linear-style keys in commit messages
  (`fix: correct typo in SEI-42`) keep working unchanged.
- **Stable identity across renames**: UUIDs make splits, merges, and
  collision-driven renames safe — lookups go through the canonical
  identity, not the human label.

## Why not skip `next-key` and self-increment?

- **Race conditions** — two concurrent agents would both read
  `next_issue_number: 42`, both write `SEI-42`, and collide.
- **Atomicity** — `next-key` is one CLI call, one file lock, one
  increment, one return. The alternative is three file operations
  (read, increment, write) you'd have to coordinate.
- **Future-proofing** — centralised allocation makes distributed
  scenarios (batch allocation, per-agent ranges) easy to add later.

## See also

- `VALIDATION.md` — the `collision/id` and `sequence/drift` checks
- `ANTI_PATTERNS.md` — the mortal sin of hand-writing UUIDs
