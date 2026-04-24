# Keel v0.7 — per-issue developer + verified notes (enforced)

**Status**: idea (not yet designed)
**Date**: 2026-04-17
**Depends on**: v0.6a artifact manifest + ownership model
**Source**: every PM review since the kb-pivot test has flagged
missing `issues/<KEY>/developer.md` notes. The DoD checklist asks
for them, but nothing checks they exist — pure aspirational text.

---

## 1. The problem

The default issue template carries this DoD checklist
(`src/keel/templates/issue_templates/default.yaml.j2:25-26`):

```markdown
## Definition of Done
- [ ] Implementation complete
- [ ] Tests added/updated
- [ ] Completion comment added
- [ ] issues/{{ id }}/developer.md added
- [ ] issues/{{ id }}/verified.md added
- [ ] Concept nodes created/updated for new artifacts
```

Every issue spec in every project carries the same checklist. The
PM agent generates issues that include it. Execution agents receive
issues with this DoD. **And every PR review since v0.5 has flagged
the same gap: the developer.md / verified.md files don't exist.**

Reasons:

1. **Nothing fails the build when they're missing.** The validator's
   `check_artifact_presence` looks at session-level artifacts only
   (the manifest at `templates/artifacts/manifest.yaml`). It has no
   concept of per-issue artifacts.
2. **The agent rationalises the gap.** The DoD checklist is a
   markdown checkbox in the issue body. The agent ticks it (or
   doesn't tick it) and moves on. There is no failing-first
   scaffold pattern that forces the file to be created.
3. **The role of `verified.md` is undefined.** v1 has no
   verification agent — the PM (or human) does verification. So
   `verified.md` was always going to be missing until the
   verification skill ships.

Yesterday's PR-#5 and PR-#6 reviews both ended with: "DoD: missing
developer note. (Note: keel doesn't currently validate this.)" The
gap is now well-attested across multiple sessions and agents — it
isn't a one-off agent failure. It's a missing primitive.

## 2. The fix — per-issue artifacts as a first-class concept

Extend the existing artifact model from session-scoped to
issue-scoped. The PM-managed schema, the validator, and the
templating system all gain an `issue_artifacts/` analogue to the
existing `artifacts/` directory.

### 2.1 Manifest

New file: `src/keel/templates/issue_artifacts/manifest.yaml`.

```yaml
# Issue artifact manifest — declares what every issue must produce
# during its lifecycle.
#
# Mirrors the session artifact manifest but scopes per-issue:
# files live at `issues/<KEY>/<file>` rather than
# `sessions/<id>/artifacts/<file>`.
#
# The validator enforces stage-aware requirements:
# - developer.md is required when issue.status reaches `in_review` or `done`
# - verified.md is required when issue.status reaches `done`
#
# Projects can add or override entries via `issue_artifact_overrides`
# in their project.yaml.

artifacts:
  - name: developer
    file: developer.md
    template: developer.md.j2
    produced_at: implementing
    produced_by: execution-agent
    owned_by: execution-agent
    required: true
    required_at_status: in_review

  - name: verified
    file: verified.md
    template: verified.md.j2
    produced_at: verifying
    produced_by: verification-agent
    owned_by: verification-agent
    required: true
    required_at_status: done
```

### 2.2 Schema additions

New model in `src/keel/models/manifest.py` — extend the existing
`ArtifactEntry` with an optional `required_at_status` field, OR
introduce a sibling `IssueArtifactEntry` if we don't want to mix
session and issue semantics. **Decision lean: sibling class.**
Reason: the `produced_at` phase enum is session-shaped
(planning/implementing/verifying/completion). Issues have status
(backlog/todo/in_progress/in_review/done), not phase. Mixing the
two on one model invites confusion.

```python
IssueStatus = Literal["backlog", "todo", "in_progress", "in_review", "done"]

class IssueArtifactEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    file: str
    template: str
    produced_by: AgentType
    owned_by: AgentType | None = None
    required: bool = True
    required_at_status: IssueStatus = "done"

    @model_validator(mode="after")
    def _default_owned_by_to_produced_by(self) -> IssueArtifactEntry:
        if self.owned_by is None:
            object.__setattr__(self, "owned_by", self.produced_by)
        return self


class IssueArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifacts: list[IssueArtifactEntry] = Field(default_factory=list)
```

### 2.3 Validator

New checks in `src/keel/core/validator.py`:

```python
def check_issue_artifact_presence(ctx: ValidationContext) -> list[CheckResult]:
    """Issues at or past `required_at_status` must have all required
    issue artifacts."""
    manifest = _load_issue_artifact_manifest(ctx.project_dir)
    results: list[CheckResult] = []
    for issue in ctx.issues:
        for entry in manifest.artifacts:
            if not entry.required:
                continue
            if not _status_at_or_past(issue.status, entry.required_at_status):
                continue
            artifact_path = paths.issue_dir(ctx.project_dir, issue.id) / entry.file
            if not artifact_path.exists():
                results.append(
                    CheckResult(
                        code="issue_artifact/missing",
                        severity=Severity.ERROR,
                        ...
                        message=(
                            f"Issue {issue.id!r} status is {issue.status!r} "
                            f"and must have {entry.file!r}. "
                            f"The {entry.produced_by} agent writes this "
                            f"during {entry.produced_at_status_implied}."
                        ),
                        hint=(
                            f"Run `keel issue artifact init {issue.id} "
                            f"{entry.name}` or write the file manually."
                        ),
                    )
                )
    return results
```

Status comparison helper: a strict ordering on `IssueStatus`
(`backlog < todo < in_progress < in_review < done`). The validator
treats "at or past" as ≥.

### 2.4 CLI

New CLI subcommand: `keel issue artifact init <issue-key> <name>`.

```bash
$ keel issue artifact init KUI-58 developer
Wrote issues/KUI-58/developer.md from template.

$ keel issue artifact list KUI-58
✓ developer.md (required, produced_by: execution-agent)
  verified.md (required, produced_by: verification-agent) — MISSING
```

The `init` subcommand:
1. Looks up the manifest entry.
2. Renders the template at `templates/issue_artifacts/<template>.j2`
   with `issue` and `project` in scope.
3. Writes to `issues/<KEY>/<file>`.
4. Refuses to overwrite (use `--force` to overwrite).

### 2.5 Templates

Two new templates in `src/keel/templates/issue_artifacts/`:

**`developer.md.j2`**:
```markdown
# Developer notes — {{ issue.id }}

## What I built

{# Brief — 1-3 sentences on what changed and why. The agent fills in. #}

## Key decisions

{# Any non-obvious choices: library selection, architectural splits,
   patterns that future agents need to know about. #}

## Files touched

{# Bulleted list. The PR diff captures what; this captures why. #}

## Tests added

{# Bulleted list. What scenarios you covered, what you deliberately
   didn't cover. #}

## Stop-and-ask points triggered

{# Did any execution constraints in the issue body fire? If yes,
   what did you do? If no, write "none". #}

## Followups

{# Things you noticed but didn't fix in this issue. Each one
   should be a new issue or a comment on the relevant existing
   issue. Don't leave them buried here. #}
```

**`verified.md.j2`**:
```markdown
# Verification notes — {{ issue.id }}

**Verified by**: {# pm-agent | verification-agent | human reviewer #}
**Verified at**: {# date #}
**Verdict**: {# approved | approved-with-followups | rejected #}

## Acceptance criteria

{% for criterion in issue.acceptance_criteria %}
- [ ] {{ criterion }} — {# evidence: file:line, test name, or "manual smoke" #}
{% endfor %}

## Deviations found

{# Files touched outside the issue's Repo scope, dependencies added
   beyond the spec, layout changes. Cross-reference the developer
   note's reasoning. #}

## Follow-up issues created

{# Bulleted list of new issue keys created from gaps surfaced
   during verification. #}
```

### 2.6 Integration with existing issue template

The DoD checklist in `default.yaml.j2` stays — it's still useful
as a human-readable summary — but the lines now reference the
artifact system rather than free-form paths:

```markdown
## Definition of Done
- [ ] Implementation complete
- [ ] Tests added/updated
- [ ] Completion comment added
- [ ] developer.md ({{ id }}) — see `keel issue artifact list {{ id }}`
- [ ] verified.md ({{ id }}) — see `keel issue artifact list {{ id }}`
- [ ] Concept nodes created/updated for new artifacts
```

The agent doesn't need to know the file path; it runs the CLI.

## 3. Status transitions and gating

### 3.1 What blocks an issue from going to `done`?

- `verified.md` missing → validator error (already covered).
- Status transition validator (existing) refuses `in_review → done`
  if the developer note is missing.

The two checks are belt-and-braces: the artifact-presence check
catches the steady-state gap; the transition check catches the
moment of attempt.

### 3.2 What blocks `in_progress → in_review`?

- `developer.md` missing → validator error.

### 3.3 Backwards compatibility

Existing projects have many issues already at `done` without these
artifacts. The validator should treat them as **warnings, not
errors, when `created_at < manifest_introduced_at`**. Add a
`grandfather_before` field on the manifest:

```yaml
artifacts:
  - name: developer
    ...
    grandfather_before: "2026-04-17T00:00:00Z"
```

Issues created before that timestamp downgrade missing-artifact
to a warning. Issues created after must comply. This avoids one
big migration PR.

## 4. Verifier role — what to do until v1.x

`verified.md` declares itself produced by `verification-agent`,
but v1 ships no verification agent. Until that agent lands:

- The PM acts as verifier (for now, "/pm-session-review" output
  becomes the verified.md content for each issue in the session).
- A `--produced-by` override on `keel issue artifact init` lets
  the PM (or human) write the file with a different attribution:

```bash
keel issue artifact init KUI-58 verified --produced-by pm-agent
```

The validator accepts any `produced_by` value at file-write time;
the manifest's `produced_by` is advisory (who *normally* writes
this), not enforced.

## 5. Scope summary

**v0.7 (this spec):**

Schema:
- `IssueArtifactEntry` + `IssueArtifactManifest` models
- `templates/issue_artifacts/manifest.yaml` with `developer` +
  `verified` entries
- `templates/issue_artifacts/developer.md.j2` +
  `verified.md.j2` templates

Validator:
- `check_issue_artifact_presence` — `issue_artifact/missing` error
- Status transition checks: block `in_progress → in_review`
  without developer.md, block `in_review → done` without
  verified.md
- `grandfather_before` honoured to avoid retroactive errors

CLI:
- `keel issue artifact init <key> <name> [--force] [--produced-by AGENT]`
- `keel issue artifact list <key> [--format text|json]`
- `keel issue artifact verify <key>` — runs presence check for
  one issue (useful in execution-agent loops)

Template:
- Update `default.yaml.j2` DoD lines to reference the CLI
  rather than literal paths

**v0.8+ (deferred):**
- Real verification agent that produces verified.md
- Per-issue artifact overrides in issue.yaml (analog of
  session.artifact_overrides)
- Approval gates on issue artifacts (e.g., PM must sign off on
  developer.md before transition to in_review)

## 6. Open questions

- **Should `developer.md` be required at `in_review` or `done`?**
  Lean: `in_review`. The note exists for the verifier to read; if
  it's not there at review time, the verifier has nothing to check
  against beyond the diff. Required at `done` is too late.
- **Should the manifest live in the project (`project.yaml`) or
  in keel templates?** Lean: keel templates with project-level
  overrides via `project.yaml.issue_artifact_overrides`, mirroring
  the session artifact pattern.
- **What happens when an issue is reopened from `done` to
  `in_progress`?** Lean: developer.md and verified.md persist;
  the next pass appends a `## Re-engagement YYYY-MM-DD` section
  rather than overwriting. The `init --force` flag opt-in for
  destructive overwrite.
- **Does the PM session need its own artifact for capturing the
  per-issue review?** That's effectively what the v0.7 PM monitor
  spec's `/pm-session-review` produces. We could route that output
  directly into `verified.md` for each issue covered by the
  session — closes the loop without needing a separate artifact.
  Lean: yes, wire `/pm-session-review` to write verified.md as a
  side-effect when the PM runs it.

## 7. Effort estimate

| Component | Estimate |
|---|---|
| `IssueArtifactEntry` + `IssueArtifactManifest` models | 0.5 day |
| Manifest YAML + 2 templates | 0.5 day |
| `check_issue_artifact_presence` validator | 1 day |
| Status-transition guards (2 transitions) | 1 day |
| `keel issue artifact` CLI (3 subcommands) | 1.5 days |
| `grandfather_before` plumbing + tests | 0.5 day |
| Issue template DoD update + propagation tests | 0.5 day |
| Tests (validator + CLI + e2e) | 2 days |
| **Total** | **~7.5 days** |

## 8. Testing

| Test | Verifies |
|---|---|
| `test_issue_artifact_manifest_loads` | YAML parses to model |
| `test_issue_at_in_review_missing_developer_errors` | Validator fires |
| `test_issue_at_done_missing_verified_errors` | Validator fires |
| `test_issue_at_todo_no_artifacts_required` | No false positives |
| `test_grandfather_before_downgrades_to_warning` | Backcompat |
| `test_status_transition_blocked_without_developer` | Transition guard |
| `test_status_transition_blocked_without_verified` | Transition guard |
| `test_artifact_init_writes_template` | CLI happy path |
| `test_artifact_init_refuses_overwrite` | Refuses without --force |
| `test_artifact_init_force_overwrites` | --force works |
| `test_artifact_init_produced_by_override` | PM-as-verifier path |
| `test_artifact_list_shows_missing_entries` | CLI list |
| `test_pm_session_review_writes_verified_md` | Cross-spec wiring |

## 9. Terminology alignment with issue status

### 9.1 The mismatch

Three of the four `ArtifactPhase` enum values shadow `IssueStatus`
values without saying so:

| Session phase (current) | Issue status (current) | Same concept? |
|---|---|---|
| `planning` | (no analog) | session-only |
| `implementing` | `in_progress` | yes — same activity |
| `verifying` | `in_review` | yes — same activity |
| `completion` | `done` | yes — same end-state |

Agents (and humans skimming the codebase) routinely confuse the
two. The validator's stage-aware messages say
"required during implementing" while the issue body says "ready
for review when in_progress" — same moment, two vocabularies.
The cost is small per encounter and large in aggregate.

### 9.2 Proposal — rename session phases to match issue statuses

Rename the three overlapping `ArtifactPhase` values:

```python
# before
ArtifactPhase = Literal["planning", "implementing", "verifying", "completion"]

# after
ArtifactPhase = Literal["planning", "in_progress", "in_review", "done"]
```

`planning` stays — there's no issue analog (issues skip planning;
the PM does it once per session, not per issue).

This is **not** unifying the two enums into one. They still measure
different axes (issue lifecycle vs session activity). The rename
just makes shared moments use the same word, so a reader doesn't
have to translate.

### 9.3 Migration

This is a wide-but-mechanical change. Files to update:

- `src/keel/models/manifest.py` — `ArtifactPhase` literal
- `src/keel/templates/artifacts/manifest.yaml` — every
  `produced_at` value
- `src/keel/core/validator.py` — every reference to phase names
  in messages, hints, and check logic
- `src/keel/templates/skills/**/*.md` — every skill that mentions
  the phase vocabulary (project-manager, verification, the
  *-coder skills)
- `src/keel/templates/skills/project-manager/references/SCHEMA_*.md`
  — schema docs that enumerate values
- `docs/**.md` — overarching plan, keel-plan, anywhere the
  vocabulary leaks into prose
- All session YAMLs in test fixtures + example projects
- v0.7 PM monitor spec (`2026-04-16-v07-pm-monitor.md`) — uses
  the old vocabulary in its lifecycle diagrams

For one release, accept the legacy values as aliases:

```python
def _normalise_phase(value: str) -> str:
    return _PHASE_ALIASES.get(value, value)

_PHASE_ALIASES = {
    "implementing": "in_progress",
    "verifying": "in_review",
    "completion": "done",
}
```

The model-level `Literal` only accepts the new values; the YAML
loader normalises before validation. This lets old fixtures load,
emits a deprecation warning, and keeps the enforcement strict at
the model boundary.

After v0.8 ships, drop the alias.

### 9.4 Validation — three layers

**Layer 1: schema-level (loader-time).**
The YAML loader rejects any value not in `IssueStatus ∪
{"planning"}` with `phase/unknown`. Catches typos and stale
values immediately.

**Layer 2: enum-coherence (CI-only sanity check).**
A new test asserts that `set(ArtifactPhase) - {"planning"}` is a
subset of `set(IssueStatus)`. If anyone adds a new phase, this
fails until they either (a) align it with an issue status or
(b) explicitly mark it session-only by adding it to a sanctioned
exception set:

```python
SESSION_ONLY_PHASES: frozenset[str] = frozenset({"planning"})

def test_artifact_phases_align_with_issue_status():
    overlap_required = set(ArtifactPhase) - SESSION_ONLY_PHASES
    assert overlap_required.issubset(set(IssueStatus)), (
        f"ArtifactPhase values {overlap_required - set(IssueStatus)!r} "
        f"don't match IssueStatus. Either rename them or add to "
        f"SESSION_ONLY_PHASES with justification."
    )
```

This is the "drift detection" guard. It costs nothing and prevents
the next person from re-introducing the divergence.

**Layer 3: data-coherence (validator check).**
Add a runtime check that flags state contradictions between a
session and the issues it owns:

| Session phase | Allowed issue statuses | Code |
|---|---|---|
| `planning` | `backlog`, `todo` | `coherence/issue_too_advanced` |
| `in_progress` | `todo`, `in_progress`, `in_review` | warn on `done` |
| `in_review` | `in_review`, `done` | error on `in_progress` or earlier |
| `done` | `done` | error on anything else |

The matrix encodes "if the session has moved past X, every issue
it owns should have caught up." Flag mismatches as
`coherence/issue_status_lags_session` (warning, since real-world
slippage happens — e.g., one issue genuinely got descoped) or
`coherence/issue_status_ahead_of_session` (error — that's a
genuine inconsistency).

This is the check that turns the alignment from "nice naming"
into "load-bearing constraint." Without it, the rename is
cosmetic; with it, the vocabulary actually means the same thing.

### 9.5 Effort delta

| Component | Estimate |
|---|---|
| Rename + alias plumbing | 0.5 day |
| Migrate templates, skills, docs | 1 day |
| Layer 2 enum-coherence test | 0.25 day |
| Layer 3 coherence validator + matrix | 1 day |
| Tests (loader aliases, drift guard, coherence matrix) | 0.75 day |
| **Subtotal** | **~3.5 days** |

Lands together with §1-§8 of this spec or as a precursor PR;
either order works.

### 9.6 What this doesn't try to do

- **Unify the enums into one.** Already argued against in §1's
  open-question discussion: cardinality (one session ↔ many
  issues) makes that wrong. Keep two enums; share the words.
- **Promote `planning` into `IssueStatus`.** Issues don't have a
  planning state in keel — the PM plans them into existence.
  Adding it would force every backlog issue to start `planning`,
  which is noise.
- **Rename `IssueStatus` to match phase.** The issue vocabulary
  is the more visible one (it's in every PR title, every status
  command output, every Linear-equivalent UI). Session phase is
  internal plumbing; it should yield to issue status, not the
  reverse.

## 10. Cross-references

- `2026-04-16-v07-pm-monitor.md` — `/pm-session-review` writes
  `verified.md` as a side-effect (§6 open question); also
  affected by §9 vocabulary rename
- `src/keel/models/manifest.py` — existing session ArtifactManifest;
  §9 changes the `ArtifactPhase` literal
- `src/keel/templates/artifacts/manifest.yaml` — existing
  session manifest; §9 changes every `produced_at` value
- `src/keel/templates/issue_templates/default.yaml.j2` — DoD
  checklist update
- `src/keel/core/validator.py` — `check_artifact_presence` is the
  twin of the new `check_issue_artifact_presence`
