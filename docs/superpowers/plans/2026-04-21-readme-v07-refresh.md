# README refresh — v0.7 alignment + structural cleanup

## Context

The README was last materially updated around v0.2. Post-v0.7.0:

- **Stale facts**: "v0.2. 502 tests pass." — actual: v0.7.0, 1282 tests. "14-check validation gate" — actual: 23 check functions in `validator.py`. "33 reference files", "13 canonical examples", "12 slash commands", "10 slash commands" — all unverified/wrong.
- **Stale slash-command table**: lists the four deprecated forwarders (`/pm-handoff`, `/pm-close`, `/pm-update`, `/pm-plan`) and is missing all 13 current v0.7 commands (`/pm-session-{queue,spawn,check,agenda,monitor,review,complete,create,progress}`, `/pm-issue-{close,artifact}`, `/pm-project-{create,sync}`).
- **Stale project layout**: shows v0.5-era `issues/MP-*.yaml` (flat) and `graph/nodes/*.yaml` (nested). Actual v0.7: `issues/<KEY>/{issue.yaml, developer.md, verified.md, comments/}/` + `nodes/*.yaml` at the top level + `sessions/<id>/{handoff.yaml, insights.yaml, review.json}`.
- **Missing v0.7 story**: the 6-stage `IssueStatus` flow, per-issue artifacts gated by status, agent-proposed node insights, session monitor/review/complete commands, canonical YAML spawn config, Layer-3 coherence validator — none appear.
- **Structural duplication**: "Design principles" (5 principles) at the top AND "How it works — Four principles" lower — same ideas, different words.
- **Bloat**: "What we learned building this" is 95 lines of behavioural-psychology editorial. Valuable content but it's a blog post, not a README section.
- **Non-working roadmap**: the orchestration YAML example references `events.on_session_complete` — not implemented in v0.7.
- **Broken hero**: the new brand kit landed at `f1b196a` replaced the old `img/tripwire_full_*.svg` and `img/tripwire_mark_*.svg` files. The hero picture tag still points at the old paths and currently renders as broken images on GitHub.
- **Empty PyPI long-description**: `pyproject.toml` already has `readme = README.md` (commit `a301bea`), so the next release will carry the README. Image refs need to be absolute GitHub-raw URLs for the hero to render on the PyPI page.

The distribution name is `tripwire-pm` while the CLI + import are `tripwire`; users land confused about this. One-line note needed.

## Goals

1. **Accurate**: every count, version, command, path matches what v0.7.0 actually ships.
2. **Scannable**: ≤300 lines. One 10-second pitch, one 60-second overview, 2–3 deep dives behind `<details>`.
3. **v0.7-aware**: surface the feature set that actually differentiates v0.7 (lifecycle, artifacts, insights, coherence).
4. **Cross-platform rendering**: renders cleanly on both GitHub and the PyPI project page.

## Non-goals

- Rewriting the design-principles prose (the 5-principle block shipped in v0.7b Phase 8 is canonical — keep).
- Changing the product framing. The current tagline and pitch are right.
- Writing new marketing copy from scratch. This is a structural + factual refresh, not a rebrand.

## Target structure

```
1.  Hero (logo, badges, tagline)          ~14 lines
2.  Pitch paragraph + nav                  ~8 lines
3.  Quickstart                             ~28 lines   refreshed
4.  What you get                           ~12 lines   refreshed
5.  Principles (keep the 5)               ~48 lines   unchanged
6.  How it works                           ~16 lines   rewritten (was dup of principles)
7.  v0.7 lifecycle flow (NEW)              ~20 lines   net-new
8.  Commands                               ~22 lines   refreshed
9.  Slash commands                         ~30 lines   rewritten
10. Project layout                         ~30 lines   rewritten
11. <details> Demo                         ~25 lines   refreshed CLI samples
12. <details> Under the hood               ~30 lines   shortened
13. <details> Worked example               ~14 lines   refreshed
14. Status                                 ~6 lines    refreshed
15. Docs                                   ~6 lines    refreshed
16. License                                ~3 lines    unchanged
```

Total target: **~280 lines** (down from 426).

## Critical files

- `README.md` — the refresh target
- `docs/superpowers/plans/V0.8-RAW.MD` — already flags this refresh as item #10
- `img/README.md` — brand-kit docs (reference for which hero asset to pick)
- `img/stacked-trans.svg` or `img/mark-light.svg` — candidate hero assets
- `src/tripwire/templates/commands/pm-*.md` — authoritative slash-command list (27 files; 23 active + 4 deprecated forwarders)
- `src/tripwire/core/validator.py` — authoritative check count (23 `def check_` functions)
- `pyproject.toml` — version is the authoritative version string

## Plan

### Phase 1: Fix the broken hero (blocking — images render as broken on GitHub right now)

- [ ] Pick the canonical hero asset from the v1 kit (`img/stacked-trans.svg` is the most likely match for a 520px hero; `img/stacked-light.svg` + `img/stacked-dark.svg` for light/dark pair).
- [ ] Rewrite the `<picture>` block with the new paths, using **absolute GitHub raw URLs** (`https://raw.githubusercontent.com/SeidoAI/tripwire/main/img/...`) so the PyPI page renders the image.
- [ ] Commit as its own commit. This is a 1-commit fix that unbreaks the rendered README; the rest of the refresh can land separately.

### Phase 2: Refresh the factual content

Edits only, no structural change yet.

- [ ] **Tagline / pitch**: unchanged (keep "A git-native project tracker where the PM, coders, and verifier are AI agents").
- [ ] **Quickstart**:
  - Keep: `pip install tripwire-pm` + `tripwire init my-project` + `cd my-project` + `claude`
  - **Add 1-line note**: "_(Distribution name is `tripwire-pm` because PyPI prohibits `tripwire`; the CLI and `import tripwire` are unchanged.)_"
  - Keep minimal install section with the quoted `"tripwire-pm[projects]"` form.
- [ ] **What you get**: refresh the bullets.
  - Keep: "One repo, everything inside", "Dual ID system", "Content-hashed concept graph", "One-shot context brief".
  - Replace "14-check validation gate" → "23-check validation gate" (or just "validation gate as a blocking command — schema, references, coherence, freshness").
  - Replace "Customisable session artifacts" → "Per-issue + per-session artifacts, enforced by status gate" (covers v0.7's developer.md / verified.md enforcement).
  - Replace "Progressive-disclosure PM skill" → "Shipped PM skill with 20 reference files and 14 canonical examples. The agent reads the example, not the schema doc."
  - **Add** "Session lifecycle commands: queue → spawn → monitor → review → complete." (new v0.7).
  - **Add** "Agent insights capture: sessions propose concept-node additions/updates; PM reviews at complete time." (new v0.7).
- [ ] **Status section**:
  - "v0.2. 502 tests pass." → "**v0.7.0.** 1282 tests pass. 23-check validation gate. 23 `/pm-*` slash commands."
  - Drop the "Not in v0" paragraph — most of that shipped.
- [ ] **Docs section**: already points at `docs/tripwire-*.md` post-v0.7a. Verify links resolve.
- [ ] **Demo block**: keep the structure; refresh CLI outputs to show current shape of `validate` report (includes `cache_rebuilt`, `duration_ms`, `findings` with `code`/`severity`) and current `status` output (adds insights/artifacts counts once implemented, otherwise leave).

### Phase 3: Rewrite the slash-command table

Source of truth: `src/tripwire/templates/commands/pm-*.md`.

- [ ] Generate the table from the 23 active commands (drop the 4 deprecated forwarders).
- [ ] Group into sections matching the skill's organisation: **Scoping**, **Triage & edit**, **Sessions**, **Issues**, **Project**, **Interpretive**.
- [ ] Each row: command, argument hint, one-line "what it does" from the command's frontmatter `description`.

Example target:

```
### Scoping
| Command | Args | What it does |
|---|---|---|
| `/pm-scope` | `<intent>` | Scope a new project from intent + planning docs |
| `/pm-rescope` | `<intent>` | Expand an existing project with new scope |

### Sessions
| `/pm-session-create` | `<session-id>` | Create a session YAML + plan skeleton |
| `/pm-session-queue` | `<session-id>` | Verify readiness; transition planned → queued |
| `/pm-session-spawn` | `<session-id>` | Create worktree + launch claude -p |
| `/pm-session-monitor` | `[session-ids...]` | Self-paced runtime observation |
| `/pm-session-review` | `<session-id>` | Review PR vs issue specs; writes verified.md |
| `/pm-session-complete` | `<session-id>` | Close-out gates + transition to done |
...
```

### Phase 4: Rewrite the project-layout block

Current layout is v0.5-era. Rewrite to match v0.7:

```
my-project/
├── project.yaml                 # name, key_prefix, statuses, enum pointers, spawn_defaults
├── .tripwire/                   # project overrides (v0.7: commands/, spawn/)
├── enums/*.yaml                 # issue_status, session_status, etc. (override shipped)
├── issues/<KEY>/
│   ├── issue.yaml               # frontmatter + body
│   ├── developer.md             # written at in_review
│   ├── verified.md              # written at verified
│   └── comments/                # one file per PM comment
├── nodes/*.yaml                 # concept graph
├── sessions/<id>/
│   ├── session.yaml
│   ├── handoff.yaml             # PM → execution agent record
│   ├── plan.md                  # produced at planning
│   ├── task-checklist.md        # produced at in_progress
│   ├── verification-checklist.md# produced at planning
│   ├── recommended-testing-plan.md
│   ├── post-completion-comments.md
│   ├── review.json              # written by tripwire session review
│   ├── insights.yaml            # optional: agent-proposed node additions
│   └── artifacts/               # overflow session artifacts
├── graph/index.yaml             # derived cache (rebuildable)
├── templates/                   # project-local Jinja templates
└── .claude/
    ├── commands/pm-*.md         # slash commands (23 shipped)
    └── skills/project-manager/  # reference docs + examples
```

### Phase 5: Add "v0.7 lifecycle flow" section

Short (~20 lines). Explains how the pieces connect:

1. **Plan** — PM scopes; writes `plan.md`, `verification-checklist.md`.
2. **Queue → Spawn** — PM queues; `tripwire session spawn` creates a worktree + launches `claude -p` with the resolved spawn config.
3. **Execute** — Agent writes code, runs tests, opens PR. Writes `developer.md` + `task-checklist.md`.
4. **Monitor** — `/pm-session-monitor` loops: cost, turn, latest tool, PR status.
5. **Review** — `/pm-session-review` checks PR vs acceptance criteria; writes `verified.md` + `review.json`.
6. **Complete** — `/pm-session-complete` gates on merged PR + artifacts + review exit-code; closes issues; cleans worktree; PM reviews insights.

Cite: `docs/specs/2026-04-20-v07-unified.md` for full detail.

### Phase 6: Rewrite "How it works"

Was duplicate of principles. Now: one paragraph per mechanism.

- **The concept graph.** (current content — keep)
- **The validator is the gate.** (current content — keep)
- **Sessions are knowledge-producing events.** (new — mention artifacts + insights)
- **The project repo ships its own instruction set.** (current content — keep, but shorten)

Drop "Four principles" numbering — these are mechanisms, not principles.

### Phase 7: Move the 95-line "What we learned" section

- [ ] Create `docs/learnings.md` with the full "What we learned building this" content.
- [ ] Replace the README details block with a single-paragraph summary + link:

  > **What we learned building this.** Running a real PM agent against an 8,000-line planning corpus surfaced seven recurring failure modes — missing self-checks, workflow steps that weren't load-bearing, agent output degrading over session length, and more. See [`docs/learnings.md`](docs/learnings.md).

### Phase 8: Drop the orchestration example

`events.on_session_complete` isn't implemented in v0.7. Delete the YAML block in the "Under the hood" details section; keep the rest (dual IDs, graph cache, auto-fix subset, PM skill).

### Phase 9: Refresh the "Under the hood" block

- [ ] Update "PM skill ships ... 17 reference docs and 13 canonical example files" → **20 and 14** (actual counts from `ls src/tripwire/templates/skills/project-manager/{references,examples}/`).
- [ ] Shorten the content-hashing example — the current block is 15 lines including a multi-line YAML; keep the idea, drop one layer of elaboration.

### Phase 10: Post-refresh verification

- [ ] `grep -rn 'Keel\|keel' README.md` — zero (except in historical filename refs under `docs/specs/2026-04-15-*` if referenced).
- [ ] Every slash command in the README table appears as a file under `src/tripwire/templates/commands/`.
- [ ] Project-layout block matches what `tripwire init` actually produces (spot-check against a fresh `tripwire init /tmp/readme-test`).
- [ ] Version / test-count / check-count / skill-ref-count numbers match live counts.
- [ ] README length ≤ 300 lines.
- [ ] `wc -l README.md` and compare to target 280.
- [ ] All image URLs absolute and resolvable.
- [ ] `gh pr view` the resulting PR and confirm GitHub renders the hero.
- [ ] Build a wheel locally (`uv build`) and inspect `dist/tripwire_pm-*.whl` METADATA → README body + hero HTML present.
- [ ] Optional: upload to TestPyPI to confirm PyPI-side render before the next real release.

## Release coupling

The README refresh + the pyproject `readme` field + the PyPI long-description take effect together on the next published version. Realistic path:

- **Option A**: ship the README refresh as-is on `main`. It renders on GitHub immediately. PyPI gets it on the next release.
- **Option B**: cut `v0.7.1` right after the README refresh merges. It's a metadata + docs bump only; no behaviour change. Lets PyPI page reflect reality quickly.

Recommend **B** (fast follow-up). One-commit version bump + tag.

## Out of scope

- Rewriting the 5-principle block. The v0.7b canonical version stays.
- Marketing copy / SEO tuning. This is structural + factual.
- Translated versions / non-English READMEs.
- Badge inflation (PyPI downloads, CI status, coverage). Optional; can add later.
