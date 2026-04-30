# v0.9 — Tripwire authoring loop

**2026-04-30**

This is the design spec for the v0.9 B-series — the project-team
authoring loop for tripwires built on top of the v0.8 primitive
(`docs/specs/2026-04-21-v08-tripwires-as-primitive.md`). It covers
three pieces:

- **B1 (KUI-135)** — the authoring guide at
  `docs/skill-references/AUTHORING_TRIPWIRES.md`.
- **B2 (KUI-136)** — the `tripwire test-tripwire` PM CLI.
- **B3 (KUI-137)** — the `tripwire session reopen --reset-acks` flag.

## Why a separate authoring loop

The v0.8 primitive shipped with one canonical tripwire (`self-review`)
hand-wired by tripwire's own maintainers. The team behaviour change we
want — project teams writing their own tripwires for the workflow
failure modes they keep hitting — needs three things v0.8 didn't
provide:

1. **Documentation that says how.** A spec is not a guide. The
   project team is not expected to read the primitive spec end-to-end
   before writing their first tripwire.
2. **A way to test the prompt without a session.** Iterating on
   prompt copy by spawning a session and waiting for the lifecycle
   event to fire is too slow and expensive; project authors will give
   up.
3. **A way to recover from acks that have gone stale.** When a PR
   round-trips after PM review, the agent's existing acks still satisfy
   the registry — but they describe the wrong work. The reopen path
   needs an explicit "wipe and re-engage" mode.

## B1 — Authoring guide

The guide lives outside the spec at
`docs/skill-references/AUTHORING_TRIPWIRES.md`. It targets a project-
team author who knows Python and has read the project's CLAUDE.md but
hasn't read the tripwire primitive spec.

Coverage:

- When to write a tripwire (good vs. bad candidates).
- The `Tripwire` subclass anatomy (id, fires_on, blocks, at, fire,
  is_acknowledged).
- Testing via `tripwire test-tripwire`.
- Registration via `project.yaml.tripwires.extra`.
- Common pitfalls.

The guide is referenced from the project-manager skill's tripwire
authoring page (a future cycle's responsibility — out of scope here).

## B2 — `tripwire test-tripwire <id>` CLI

The PM-only CLI fires the named tripwire against a synthetic
`TripwireContext` and prints the prompt that `fire()` would return.

```
tripwire test-tripwire <id> [--session <sid>] [--ack] [--project-dir <path>]
```

Behaviour:

- Loads the registry via the existing
  `tripwire._internal.tripwires.loader.load_registry`. The registry
  loader handles built-ins AND project-local extras, so the same path
  validates the author's `project.yaml.tripwires.extra` registration.
- Resolves the tripwire by `id`. Unknown ids exit non-zero with the
  list of known ids.
- Builds a `TripwireContext` with the supplied `--session` (or a
  CLI sentinel like `<test>` when omitted) and the project's slug.
  This drives `variation_index` so the prompt the author sees is
  what an agent in that session would see.
- Prints the prompt verbatim. No firings event is emitted — this is
  not a lifecycle event.
- With `--ack`, writes the standard ack marker via
  `tripwire.core.tripwire_state.write_ack_marker`. Useful for
  authoring tests that need to verify the ack path works.

Role gating mirrors `tripwire tripwires list`: the role marker
(`TRIPWIRE_ROLE=pm` env or `~/.tripwire/role` file) is required.
Executors don't run this command.

Why a CLI rather than a unit-test recipe? Tripwire authors are
typically project-team engineers, not framework maintainers — they
think in CLI commands, not Python unit tests. The CLI is the
authoring surface; the underlying `Tripwire` class is the
implementation surface.

## B3 — `tripwire session reopen --reset-acks`

Existing `session reopen` flips a completed session back to `paused`,
appends a `## PM follow-up` stub to plan.md, and audit-logs the
reopen. The acks the agent wrote during the previous engagement
still satisfy the registry — that's the bug.

Add a `--reset-acks` flag that:

1. Deletes every file under `<project_dir>/.tripwire/acks/` matching
   the suffix `-<session-id>.json`. (Marker filenames are
   `<tripwire-id>-<session-id>.json` per the v0.8 spec.)
2. Emits a single `session.acks_reset` event under
   `<project_dir>/.tripwire/events/session_acks_reset/` recording the
   session id, the count of markers deleted, the reason text, and
   the timestamp.
3. Surfaces the count in the user-facing CLI output ("Reset N
   tripwire ack(s).").

The flag is opt-in. The default `session reopen` keeps current
behaviour because the legitimate "reopen for a tiny touch-up" case
shouldn't redo the entire tripwire dance.

## Out of scope (for these three issues)

- New tripwire types (workflow-deviation tripwires KUI-138-142 are
  separate work in `v09-entity-graph-consumers`).
- The PM PR review station that consumes self-review.md (KUI-150-152
  in `v09-workflow-consumers-ui`).
- Auto-rewriting `project.yaml.tripwires.extra` from the CLI —
  `tripwire init`-time tripwire scaffolding is a v1.0 idea.

## Acceptance summary

- Authoring guide exists and covers the path from "team is
  forgetting X" to "tripwire registered and tested".
- `tripwire test-tripwire <id>` returns the prompt for a known id
  and exits non-zero with the registry listing for an unknown id.
- `tripwire session reopen <sid> --reset-acks` deletes the per-
  session ack markers and emits a `session.acks_reset` event.
