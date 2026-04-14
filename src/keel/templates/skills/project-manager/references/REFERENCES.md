# `[[node-id]]` References

References are how entities connect in the concept graph without
storing edges as separate files. Every reference is implicit — derived
from the data.

## Syntax

A reference is `[[<id>]]` where `<id>` is a lowercase, letter-first,
hyphenated slug that matches a concept node id or an issue key.

- ✓ `[[user-model]]`
- ✓ `[[auth-token-endpoint]]`
- ✓ `[[dec-003-session-tokens]]`
- ✗ `[[UserModel]]` — uppercase not allowed
- ✗ `[[user_model]]` — underscores not allowed
- ✗ `[[1foo]]` — must start with a letter

The reference parser uses the regex `\[\[([a-z][a-z0-9-]*)\]\]`. Same
slug rule as `ConceptNode.id` validation.

## Where references go

References work in any Markdown body:

- Issue bodies (`issues/<KEY>/issue.yaml`)
- Node bodies (`nodes/<id>.yaml`)
- Comment bodies (`issues/<KEY>/comments/*.yaml`)
- Session artifact markdown (`sessions/<id>/artifacts/*.md`)

The validator extracts them from every body during validation.

## Fenced code blocks are skipped

References inside fenced code blocks (`` ``` `` or `~~~`) are NOT
parsed — they're treated as literal text. This means you can write
example commands or output without worrying about triggering false
positives:

````markdown
Run `keel refs list SEI-42` to see the references:

```
user-model     resolves    ok
[[fake-ref]]   in code     (not parsed)
```
````

## Bi-directional `related` on nodes

The `related` field on a concept node is bi-directional. If node A's
`related` contains B, node B's `related` must contain A:

```yaml
# nodes/node-a.yaml
id: node-a
related: [node-b]

# nodes/node-b.yaml
id: node-b
related: [node-a]  # required — B must point back
```

The validator warns on asymmetry (`bidi/related`) and `--fix` auto-adds
the missing side. You can just write both sides yourself — it's
clearer and avoids surprises.

## `blocked_by` is canonical, `blocks` is computed

On issues, `blocked_by` is the authoritative field. `blocks` is
**computed** by the validator from the inverse of `blocked_by` across
all issues:

```yaml
# issues/SEI-42.yaml
id: SEI-42
blocked_by: [SEI-40]    # canonical
blocks: []              # do NOT write — validator computes this

# issues/SEI-40.yaml
id: SEI-40
blocked_by: []
blocks: [SEI-42]        # derived from SEI-42.blocked_by
```

**Don't write `blocks` by hand.** The validator and graph cache manage
it. If you're confused about what blocks what, look at the cache:

```bash
cat graph/index.yaml | grep -A 3 "SEI-40"
```

## Dangling references

A dangling reference points at an entity that doesn't exist. The
validator reports it as `ref/dangling`. Common causes:

- **Typo**: `[[user-modle]]` instead of `[[user-model]]`. Fix the typo.
- **Forgot to create the node**: the node exists in your plan but you
  never wrote the `nodes/<id>.yaml` file. Create it.
- **Wrong slug**: you referenced `[[user-model]]` but the file is
  `user_model.yaml`. Rename the file or the reference.
- **Reference in an example you copied**: the example had `[[user-model]]`
  but you haven't created a `user-model` node in your project. Either
  create one or edit the reference out.

## Reference commands

- `keel refs list <issue-key>` — every reference in one issue
- `keel refs reverse <node-id>` — every entity that references a node
- `keel refs check` — full scan (dangling, orphan, stale)

## See also

- `CONCEPT_GRAPH.md` — when to create a node vs inline prose
- `SCHEMA_NODES.md` — node file schema
- `VALIDATION.md` — `ref/dangling`, `bidi/related`, `ref/blocked_by` codes
