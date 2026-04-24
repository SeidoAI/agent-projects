# Tripwire v0.8 — bi-directional active concept graph + version pins

**Status**: spec (ready for plan)
**Date**: 2026-04-24
**Depends on**: v0.7.3 (CLAUDE.md concept-context breadcrumbs land in v0.7.3 and get upgraded here)
**Related**: `2026-04-21-v08-tripwires-as-primitive.md` (independent v0.8 feature; both can land in the same release)
**Source**: brainstorm 2026-04-23 — turning the concept graph from a passive registry into the project's coherence enforcement layer.

---

## 1. The problem

The current concept graph is uni-directional and passive.

- **Uni-directional**: docs / issues / sessions / nodes reference other nodes via `[[id]]`. The references flow one way. Nothing ever asks "node X just changed; what depends on it?"
- **Passive**: a node has a `source.content_hash` that detects when the source file changes. Beyond that one signal, the graph stores relationships but does not enforce coherence between them.

The downstream symptom we hit in the testing-backend trial (2026-04-23): the session plan was written against an earlier reality. By the time it ran, ~5,000 lines of test code had landed bundled with their feature PRs, making most of the plan's "create X" steps obsolete. The agent discovered this, scoped down, shipped 4 files — but burned 14m 51s and $4.74 of budget on the discovery. The graph already knew (the relevant `[[issue-service]]` etc. nodes had been refreshed); nothing surfaced "this plan references nodes whose underlying code has substantively shipped since the plan was written."

Generalised: **the graph holds the truth, but nothing checks references against the truth at the moment they matter (plan launch, PR merge, doc edit).**

## 2. The solution

Three coupled changes:

1. **Add an integer `version` field to every node.** Bumped by deliberate `tripwire node bump` only when the contractual surface changes (not on every body edit).
2. **Every reference includes its acknowledged version.** `[[file-watcher@v3]]` in markdown, `file-watcher@v3` in YAML lists. A bare `[[id]]` is treated as "never acknowledged" — flagged loudly.
3. **Strict-mode validation by default.** When a node bumps from v3 → v4, every referrer pinned at v3 is automatically stale and CI fails until each is either re-pinned (acknowledged as still-applicable) or rewritten (referrer updates its content to match the new node).

Together they convert the graph from passive registry into active enforcement layer. Every `[[ref]]` becomes a *signed receipt*: "I read this node at version N and judged it still applies to me." Drift becomes detectable, attributable, and fix-trackable.

## 3. Schema

### 3.1 Node frontmatter

Add `version: <int>` to node YAML frontmatter. Monotonic. Starts at 1.

```yaml
---
uuid: 909119a3-...
id: file-watcher
version: 3
type: contract
name: '`FileWatcher` — file-system change emitter'
source:
  path: src/tripwire/core/file_watcher.py
  content_hash: sha256:abc...
related:
  - websocket-hub@v2
  - issue-service@v1
---

## Body

(node body content here)
```

### 3.2 Reference syntax

| Context | Bare (legacy) | Pinned (v0.8) |
|---|---|---|
| Markdown body | `[[file-watcher]]` | `[[file-watcher@v3]]` |
| YAML list (`related`, `blocked_by`, etc.) | `file-watcher` | `file-watcher@v3` |

The parser splits on `@` to extract `(node-id, version)`. Same parser used everywhere a reference appears.

### 3.3 Migration

One-time sweep at v0.8 launch:

```bash
tripwire node migrate-pin-all
```

For every existing bare reference across `issues/`, `nodes/`, `sessions/`, `docs/`, auto-pin to the current version of the referenced node. Commits as `migrate(node-pins): auto-pin all references to current versions`. After this commit, bare references in committed files are rare (only newly-introduced ones, which the validator will catch).

## 4. Bump semantics — when version changes

Bump is **deliberate**. Trivial body edits (typo, formatting, expanded explanation) **do not** bump version. Only changes to the **contractual surface** — the part other things depend on — bump.

The discipline is enforced by:

- `tripwire node bump <id> --reason "..."` is the only way to increment.
- Validator check `node/version_uncommitted`: if the body has changed since the last bump-commit and no bump has happened, fails in `--strict` mode. Forces the bumper to either acknowledge the change is contractual (and bump) or revert (and re-edit without changing semantics).
- `bump` interactively asks "is this a contract change?" with examples; `--no-confirm` for the agent path.

Version source-of-truth: the `version:` integer in the node's YAML frontmatter, in the working tree at HEAD.

## 5. CLI commands

All commands default to **markdown output** (per the agent-as-primary-consumer principle established in v0.7.3). `--format=json` opt-in only for machine pipelines.

### 5.1 Read / query

#### `tripwire node referrers <id> [--distance N] [--include-stale-only]`

Default `N=1` (direct referrers). Output is per-kind grouped:

```markdown
# `file-watcher` v3 — referrers

## Issues (2)
- **KUI-44** — pinned `@v2` — ⚠ stale (1 version behind)
- **KUI-51** — pinned `@v3` — ✓ current

## Sessions (1)
- **backend-realtime** — pinned `@v3` — ✓ current

## Other nodes (1)
- **websocket-hub** — pinned `@v1` — ⚠ stale (2 versions behind)

## Docs (1)
- `docs/tripwire-ui.md` — no pin — ⚠ unacknowledged

## Plans (1)
- `sessions/frontend-views-detail/plan.md` — pinned `@v3` — ✓ current

**Summary:** 3 referrers stale (1 issue, 1 node, 1 doc), 3 current.
```

`--include-stale-only` filters to just the rows requiring action.

#### `tripwire node neighborhood <id> [--distance N]`

Both directions (referrers + dependencies) as one local graph render. Default `N=1`. Useful for "what concept area does this live in."

#### `tripwire node history <id>`

Version log: each bump as a row.

```markdown
# `file-watcher` — version history

| Version | Bumped at | Bumped by | Commit | Reason |
|---|---|---|---|---|
| v3 | 2026-04-22 | s-wheels | `9f88d87` | "added prune-on-send-failure" |
| v2 | 2026-04-18 | s-wheels | `bc2727b` | "renamed `dispatch` → `emit`" |
| v1 | 2026-04-15 | pm-agent | `init`     | initial node |
```

#### `tripwire node diff <id> [--from <v|cur-N>] [--to <v|cur>] [--at-pin <file:line>]`

Diff between two versions of a node body. Defaults: `--from cur-1 --to cur` (last bump's diff). Functionally:

1. Walk `git log --follow nodes/<id>.yaml` for commits whose message matches the deterministic format `node-bump(<id>): vN → vM — <reason>`. The `vM` commit anchors that version.
2. `git diff <commit_vN>:nodes/<id>.yaml <commit_vM>:nodes/<id>.yaml`, filtered to body section (skip housekeeping fields like `updated_at`).

`--at-pin <file:line>` resolves the pinned version at that location and diffs against current — for an agent walking through ack decisions.

#### `tripwire node hot [--limit N]`

Sorted by referrer count. Helps spot over-broad nodes that should be split.

#### `tripwire node orphan`

Zero-referrer nodes. Candidates for deletion or "this concept never caught on."

### 5.2 Mutate / propagate

#### `tripwire node bump <id> --reason "..." [--no-confirm]`

Increments the node's `version` field. Commits with the deterministic message format `node-bump(<id>): vN → vM — <reason>`. Triggers the alert wave (every referrer pinned at vN is now stale).

Without `--no-confirm`, prompts: *"You're bumping `<id>` from v3 → v4. Is this a contract change? Examples: …"*. Soft guardrail against bump-on-typo.

#### `tripwire node ack <id> --in <file:line>`

Edits the file in place to bump `[[id@v(N-1)]]` → `[[id@vN]]`. The atomic unit of "I looked, it still applies." Markdown and YAML both supported (parser splits on `@` either way).

#### `tripwire node ack-bulk <id> --pattern <glob> --reason "..." [--dry-run]`

Same but across many files. `--dry-run` previews which files would be touched without writing. Required for the trivial-bump case where every referrer is already implicitly fine ("I bumped because we tightened wording, no contractual change").

#### `tripwire node propagate <id> [--interactive]`

For each stale referrer of `<id>`:
1. Show the diff of what changed in the node body (from `tripwire node diff <id> --at-pin <referrer-loc>`).
2. Ask y/n/edit per location.
3. y → ack and continue. n → leave stale, log as deferred. e → open editor at the referrer location.

Interactive by default; `--non-interactive` for the agent path that just wants the diffs and decision points emitted as a checklist.

### 5.3 PR-level

#### `tripwire pr blast-radius <pr>`

For the diff in `<pr>`:

```markdown
# PR #42 blast radius

## Nodes touched by source changes (3)
- `file-watcher` (`src/tripwire/core/file_watcher.py` modified) — current v3, will need bump if surface changed
- `websocket-hub` (`src/tripwire/core/ws_hub.py` modified) — current v1, will need bump
- `issue-service` (`src/tripwire/ui/services/issue_service.py` modified) — current v2

## Pinned referrers requiring acknowledgment after merge (8)

### If `file-watcher` bumps to v4:
- `issues/KUI-44/issue.yaml` (pinned `@v2` already stale)
- `issues/KUI-51/issue.yaml` (pinned `@v3`)
- `nodes/websocket-hub.yaml` (pinned `@v3`)
- `sessions/frontend-views-detail/plan.md` (pinned `@v3`)

### If `websocket-hub` bumps to v2:
- `issues/KUI-44/issue.yaml` (pinned `@v1`)
- `nodes/file-watcher.yaml` (pinned `@v1`)

### If `issue-service` bumps to v3:
- `issues/KUI-24/issue.yaml` (pinned `@v2`)
- `sessions/backend-mutation-services/plan.md` (pinned `@v2`)

**Suggested PR comment:** "This PR will require ≤8 acknowledgments after merge if all 3 candidate nodes bump."
```

CI posts this as a PR comment automatically on PR open + on every push.

#### `tripwire pr ack-status <pr>`

After the PR merges and node bumps land, walks the post-merge debt: are all required acknowledgments resolved? Drives a "stale references remaining from #42" board.

### 5.4 Project health

#### `tripwire drift report`

One command, one number for "how coherent is this project right now":

```markdown
# Drift report — tripwire-ui-init

## Summary
- **Coherence score: 87%** (304 of 348 references current)
- 44 stale references across 3 nodes
- 7 nodes never freshened in > 30 days
- 2 orphan nodes

## Stale concentrations
- `file-watcher` v3 → 18 stale (highest pressure; bump landed 2 days ago)
- `issue-service` v2 → 14 stale
- `validation-runner` v4 → 12 stale

## Never-freshened (> 30 days)
- `tailwind-theme` — last source-check 2026-03-10
- `frontend-routing-contract` — last source-check 2026-03-12
- ...

## Orphans
- `legacy-keel-bridge` (0 referrers) — candidate for deletion
- `experimental-streaming` (0 referrers)
```

The number to track week-over-week. If active enforcement is doing its job, coherence stays > 90%.

## 6. Validation tripwires

All default-on for PM in `--strict` mode. Block merges.

| Code | When it fires | Severity |
|---|---|---|
| `node/stale_reference` | Referrer's pinned version is older than node's current version | error |
| `node/missing_pin` | Bare `[[id]]` reference (no version) | error |
| `node/cycle` | Cyclic dependencies between nodes | error |
| `node/never_freshened` | Node's source `content_hash` not re-verified in N days (project-configurable, default 30) | warning |
| `node/over_broad` | Node has > M referrers AND body > K lines (project-configurable, defaults M=20, K=200) | warning |
| `node/version_uncommitted` | Node body diff vs body at last bump-commit ≠ none AND no new bump-commit | error |

Strict-mode is the default for PMs because the alternative is the drift the project exists to prevent. The cost of strictness is the friction of acknowledging changes; the cost of looseness is silent decay. Net positive on strict.

## 7. Process integrations

### 7.1 CLAUDE.md prep (extends v0.7.3)

v0.7.3 ships a "Concept context" section in the prep-rendered CLAUDE.md that lists every `[[ref]]` found in `plan.md` with the project-tracking worktree path.

v0.8 upgrades it to use version pins:

```markdown
## Concept context for this session

The plan references these nodes — read them at start, confirm versions still match:

- `[[file-watcher@v3]]` — `/Users/.../project-tripwire-ui-init/nodes/file-watcher.yaml` (current: v3 ✓)
- `[[websocket-hub@v1]]` — `/Users/.../project-tripwire-ui-init/nodes/websocket-hub.yaml` (current: v2 ⚠ STALE — plan may be obsolete in this area; stop and ask if you find drift)
- `[[issue-service@v2]]` — `/Users/.../project-tripwire-ui-init/nodes/issue-service.yaml` (current: v2 ✓)
```

The agent is told upfront which parts of the plan reference current concepts and which reference stale ones. Stop-and-ask is wired specifically to the stale signals.

### 7.2 `tripwire validate-plan <id>` (extends v0.7.3)

v0.7.3 ships the basic command (file-existence checks). v0.8 extends it:

- For each `[[id@vN]]` in the plan body, check the node's current version. If `@vN < current`, mark the plan section stale.
- For each "Step N: create `<file>`" step, check `<file>` doesn't already exist (carryover).
- For each "modify `<file>`" step, check `<file>` exists AND its content_hash anchors don't conflict with described-pre-state in the plan (carryover, harder).

Output: per-section coherence rating with specific deltas.

### 7.3 Auto-transition via agent messaging

Punted to the agent-messaging layer (separate v0.8 thread). When a PR is opened, the agent emits a message; the orchestrator transitions the session `executing` → `in_review` on receipt. Avoids inference; uses explicit signal.

## 8. Output format conventions

**Default: markdown.** Agents read markdown all day; visual cues like `⚠ stale` and `✓ current` parse cognitively without a JSON deserialize step. Output is composable into PR comments, issue bodies, plan updates without a re-format step.

**Opt-in: `--format=json`** for genuine machine pipelines (`jq` chains, scripting, automated dashboards). Specifically NOT the default for any read command.

This reverses the v0.2 plan's "JSON-default" direction, which was tried and failed (agents ignored the JSON and went for the text alternative anyway). v0.7.3 sweeps the README messaging that propagated this; v0.8 doctrine is explicit: **agents are primary consumers; agents prefer markdown.**

## 9. Edge cases / open design choices

### 9.1 Bump on uncommitted changes to referrers

**Decision: bump succeeds even when stale referrers exist; strict-mode validation surfaces them downstream.** Atomic propagation is impossible at scale; making bump itself block until every referrer is acknowledged would make the tool unusable for non-trivial graphs. The reporting + per-referrer acknowledgment commands give the mechanism; the policy choice (block PRs on stale refs vs warn-only) belongs to the project, not the tool. PMs default to strict; loose mode exists for migration windows.

### 9.2 YAML field for nested data — pin format for non-string refs

For YAML lists of strings (`related: [file-watcher@v3]`), the `@vN` suffix works directly. For YAML where refs are nested under additional keys (`blocked_by: - {issue: KUI-44, reason: "..."}`) the pin still goes on the bare ref string (`{issue: KUI-44@v3, reason: "..."}`). One parser, one format, no per-context special-casing.

### 9.3 ack-bulk ergonomics matter for strict-default to be tolerable

If a contract-equivalent bump requires walking 30 stale referrers one-by-one, strict mode becomes punishing. `tripwire node ack-bulk` with `--pattern` + `--reason` + `--dry-run` keeps friction proportional to actual review work. **Building this is non-optional, not nice-to-have**, given strict default.

### 9.4 bump-commit message format is part of the contract

`node-bump(<id>): vN → vM — <reason>` is what `node history` and `node diff` parse. Changing this format breaks history reconstruction. Recommend: lock format in a test, change only with deliberate migration.

### 9.5 What about content_hash / source freshness?

Existing `source.content_hash` mechanism stays. It detects "the source file changed without anyone re-reading the node body to check it's still accurate." That's a different question from "the node body itself drifted from what referrers were pinned to." Both are needed. Both fire independent validators (`node/never_freshened` for source-vs-body drift; `node/stale_reference` for body-vs-pin drift).

### 9.6 What stops `version` from drifting from reality (e.g. someone manually edits frontmatter)?

The `node/version_uncommitted` validator. It compares the body at HEAD to the body at the most recent `node-bump(...)` commit. If they differ and no new bump exists, error. Catches: hand-incremented version without commit, edited body without bump, etc.

## 10. Out of scope (deliberately)

- **Semantic version classification** (semver-style major/minor/patch). Single integer is enough; we're not exposing the contract as a public API.
- **Automatic bump suggestion** (LLM looks at body diff and proposes "this is a contract change"). Could be a future enhancement; not for v0.8.
- **Cross-project graph** (referencing nodes in other tripwire projects). Same single-project scope as today.
- **Time-based version expiry** ("version expires after 90 days regardless of source"). Source-staleness already covered by `never_freshened`; over-engineering otherwise.

## 11. Implementation order

Within the v0.8 release, ship in this order so each step has consumers:

1. **Schema additions + parser** (the version field, `@vN` syntax, migration sweep). Nothing breaks; bare refs continue to work, just emit the warning.
2. **`tripwire node bump` + history infra** (deterministic commit format, parseable from `git log`). No CLI consumers yet beyond the bump itself.
3. **Read commands**: `referrers`, `neighborhood`, `history`, `diff`, `hot`, `orphan`. Project becomes inspectable.
4. **Validators**: `stale_reference`, `missing_pin`, `cycle`, `never_freshened`, `over_broad`, `version_uncommitted`. Drift becomes visible.
5. **Mutation commands**: `ack`, `ack-bulk`, `propagate`. The fix-it side of the validators.
6. **PR-level**: `pr blast-radius` (CI integration), `pr ack-status`. The merge-time discipline.
7. **`drift report`**. The single number to track.
8. **CLAUDE.md prep upgrade + `validate-plan` extension**. Pulls v0.7.3's breadcrumbs into version awareness.

Steps 1–4 are the "minimum viable active graph"; 5–8 round out the surface.

## 12. Verification

After implementation, the testing-backend regression should not be possible:

- The failing trial: plan written → 5,000 LOC of tests landed since → agent burns 14 minutes discovering this.
- After v0.8: plan references `[[issue-service@v1]]` etc.; `tripwire validate-plan testing-backend` at queue time sees `issue-service` is now v2 (because the test PRs bumped it); flags the plan as stale before spawn; PM updates plan first; agent launches with current truth.

Net cost of running the failing trial: 14m + $4.74. Net cost with v0.8: 30 seconds of `validate-plan`, plan PR, 30 seconds of `validate-plan` re-run. Recovers ≥ 28x on the first occurrence; many times more across many sessions.
