# Workspace sync — agent mediation guide

This doc explains how to handle a merge brief produced by
`keel workspace pull`. It is referenced by the `/pm-project-sync`
slash command.

## When this applies

A merge brief is created when `keel workspace pull` encounters a
non-trivial 3-way conflict on a workspace-origin node. Trivial cases
(fast-forward, non-overlapping field changes) are auto-applied; only
genuinely overlapping edits reach you.

## Brief structure

File: `.keel/merge-briefs/<node-id>.yaml`

```yaml
node_id: auth-system
merge_type: pull
base_sha: a3f2b1c                  # workspace commit at last pull
generated_at: 2026-04-15T14:30:00Z
base_version: {...}                # node at base_sha
ours_version: {...}                # project's current copy
theirs_version: {...}              # workspace HEAD
field_diffs:
  - field: description
    base: "..."
    ours: "..."
    theirs: "..."
    status: conflict
auto_merged_fields:
  - related_to                      # applied already in the draft node
hints:
  - "field `description`: both sides modified the text..."
```

A draft-merged node file is also written to `nodes/<node-id>.yaml`.
It contains the auto-merged fields already applied plus your `ours`
values as starting points for conflicting fields. Edit this file to
produce the final resolved node.

## Field diff statuses

| status | meaning | action |
|---|---|---|
| `ours_only` | Only we changed this field | Already taken; leave as-is |
| `theirs_only` | Only upstream changed this field | Already taken; leave as-is |
| `conflict` | Both sides changed it differently | Reason and resolve |
| `structural` | Both sides changed it to the same new value | Already consistent |

Only `conflict` entries need your intelligence.

## Resolution strategies

### Text fields (`description`, `definition`)

- **Both extended with compatible content**: combine. Example — base
  said "Auth service"; ours said "Auth service, handles sessions";
  theirs said "Auth service supporting OAuth". Resolve: "Auth service
  supporting OAuth, handles sessions."
- **Contradictory meanings**: pick the one matching project purpose.
  Note the deviation in the description if it is meaningful.
- **Upstream generic + local specific**: usually keep upstream's
  general definition and append a project-specific clarifier.

### List fields (`related`, `tags`, `aliases`)

- Non-overlapping additions — union (`[a, b]` + `[a, c]` → `[a, b, c]`).
- Removed upstream but still relevant locally — keep the local item
  and consider forking if the project truly needs the old shape.

### Typed fields (`type`, enum values)

- Genuinely different types are a signal that this might be two
  distinct concepts. Consider forking and creating a new node rather
  than reconciling.

## Finalizing

After editing `nodes/<node-id>.yaml` to the resolved form:

```bash
keel workspace merge-resolve <node-id>
```

Validates the node schema, bumps `workspace_sha` to the current
workspace HEAD, and deletes the brief. If validation fails, the
brief is preserved — fix the node and retry.

## When to fork instead of merge

- Your project needs a genuinely different version of this concept.
- Upstream has evolved in a direction that doesn't fit your use case.
- You want to stop receiving updates for this node entirely.

Fork via `keel workspace fork <node-id>`. The node's `scope` flips to
`local`; sync skips it in both directions. The `workspace_sha` is
preserved for audit but no longer checked.

## When to abandon a pull

If a pull produced briefs you don't want to resolve right now:

```bash
rm .keel/merge-briefs/<node-id>.yaml
```

Then revert `nodes/<node-id>.yaml` to its pre-pull state (`git
checkout`). The project's `workspace_sha` for that node stays at the
pre-pull value. The next pull will surface the same conflict again.
