# Authoring tripwires (KUI-135)

A **tripwire** is a hidden prompt registered against a lifecycle
event. The agent doesn't see it until the event fires, at which point
the CLI returns the prompt as command output and blocks the lifecycle
transition until the agent acknowledges it.

This guide is for project-team authors who want to add a tripwire on
top of the built-ins. The package ships built-in tripwires under
`tripwire._internal.tripwires.*` (the `self-review` tripwire is a
worked example); your tripwire lives in your project repo and is
registered via `project.yaml.tripwires.extra`.

## When to write a tripwire

Write a tripwire when there's a deeply-engrained workflow step the
team keeps forgetting AND that step has an objective acknowledgement
path (file produced, comment posted, command run). Tripwires are a
ceiling on agent autonomy — the prompt is invisible until the moment
of truth, and the agent can't skip it. That property is the entire
value, but it also means a noisy tripwire actively hurts.

Bad tripwire candidates:

- Style preferences ("use snake_case"). Lint rule territory.
- Anything you'd rather discuss in PR review. Code review territory.
- Anything the agent should obviously do without prompting. Just put
  it in the agent's persistent skill, not behind a tripwire.

Good tripwire candidates:

- "Run the data migration before merging" — the team forgets, and
  there's a CLI to run.
- "Confirm you've updated the changelog" — periodically forgotten,
  one-line ack via a file marker.
- "Self-review using the four lenses" — the canonical built-in.

## Anatomy

A tripwire is a Python class subclassing
`tripwire._internal.tripwires.Tripwire`. Three class attributes plus
two methods:

```python
from typing import ClassVar
from tripwire._internal.tripwires import Tripwire, TripwireContext


class ChangelogTripwire(Tripwire):
    id: ClassVar[str] = "changelog-updated"
    fires_on: ClassVar[str] = "session.complete"
    blocks: ClassVar[bool] = True

    # Optional, but recommended. The (workflow, station) pair this
    # tripwire registers at — the workflow.yaml well-formedness
    # validator uses this to make sure the workflow references a real
    # tripwire and vice versa.
    at: ClassVar[tuple[str, str]] = ("coding-session", "in_review")

    def fire(self, ctx: TripwireContext) -> str:
        return (
            "Before this session can complete, confirm you've updated "
            "CHANGELOG.md with a one-line entry naming the visible "
            "change. Edit the file, then re-run with `--ack`."
        )

    def is_acknowledged(self, ctx: TripwireContext) -> bool:
        marker = ctx.ack_path(self.id)
        return marker.is_file()
```

### `id` — the registry key

Stable, dash-separated, unique within the project. The marker file
that the CLI writes on `--ack` is named after this.

### `fires_on` — the lifecycle event

Must be one of the events the registry knows about. v0.9 ships:

- `session.complete`
- `issue.close`
- `pr.open`
- `validate.run`
- `session.resume`

### `blocks` — does the lifecycle wait?

`True` is almost always what you want. `False` means the prompt is
delivered as info, but the lifecycle event proceeds anyway. Use
`False` only for advisory tripwires (rare).

### `at` — the workflow station (optional but recommended)

If your project uses `workflow.yaml` (v0.9+), declare the
`(workflow, station)` pair the tripwire fires at. The well-formedness
validator catches typos and dead references this way.

### `fire(ctx) -> str`

Return the prompt to deliver. Use `ctx.variation_index(N)` if you
want the prompt to vary across sessions (deterministically — the
same session always sees the same variation, so re-runs aren't
disorienting). Keep the prompt short and end with a clear ack
instruction.

### `is_acknowledged(ctx) -> bool`

Return `True` once the agent has done what the prompt asked. Most
implementations check for an ack-marker file at
`ctx.ack_path(self.id)`. The CLI's `--ack` flag writes that marker
via `tripwire.core.tripwire_state.write_ack_marker`, which validates
that the ack carries either `fix_commits` (≥1 SHA) or
`declared_no_findings: true`. That substantiveness check is what
keeps the ack from becoming "click-through" behaviour.

If the ack should require something more than the marker (e.g. a
specific file in the repo), implement that check here directly. The
CLI will keep delivering the prompt until this method returns True.

## Testing your tripwire

Use `tripwire test-tripwire <id>` (KUI-136) to fire your tripwire
against a synthetic context without going through the lifecycle:

```sh
tripwire test-tripwire changelog-updated
# Prints the prompt your `fire()` would return.

tripwire test-tripwire changelog-updated --session sess-42
# Same, but with a specific session id (affects variation_index).

tripwire test-tripwire changelog-updated --ack
# Writes a substantive ack marker so subsequent fires don't block.
```

This lets you iterate on the prompt copy without spawning a real
session.

## Registering the tripwire

Add it to `project.yaml.tripwires.extra`:

```yaml
tripwires:
  enabled: true
  extra:
    - id: changelog-updated
      fires_on: session.complete
      class: my_project.tripwires.ChangelogTripwire
```

The `class` field is a dotted Python path resolvable from the project
root's `sys.path`. Alternatively, use `module:` for a project-local
file:

```yaml
    - id: changelog-updated
      fires_on: session.complete
      module: tripwires/changelog.py
```

The module-path form is resolved relative to `project_dir` and loaded
by `importlib.util.spec_from_file_location`. The loader auto-detects
the single `Tripwire` subclass in the module; ambiguity raises at
load time.

## After substantial rework — `--reset-acks` (KUI-137)

When a session reopens after PR-review feedback or plan changes, the
existing acks may no longer be substantive (they describe finished
work, not the rework). Pass `--reset-acks` to `session reopen` to
wipe the per-session ack markers so each tripwire fires fresh:

```sh
tripwire session reopen sess-42 --reason "PR comments to address" \
    --reset-acks
```

The reset emits a `session.acks_reset` event so the audit trail
shows the rework boundary.

## Common pitfalls

**Prompt copy that names itself.** Agents read the prompt as user
text. Don't say "this is your tripwire prompt"; just give the
instruction.

**Acks that the agent can short-circuit.** If `is_acknowledged`
returns True the moment a file exists, an empty file passes. Use the
substantiveness contract (`fix_commits` or `declared_no_findings`)
or check file content yourself.

**Tripwires that fire on irrelevant lifecycle events.** Pick the
narrowest event that catches the failure mode. `validate.run` fires
on every CLI invocation — only use it for things you want to check
on every run.

**Forgetting `at`.** Without it, `tripwire validate` won't catch
that your `workflow.yaml` references a tripwire that no longer
exists. Always set `at`.
