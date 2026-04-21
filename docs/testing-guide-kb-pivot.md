# Testing guide: Keel v0.1 on kb-pivot

A step-by-step guide for manually testing every v0.1 feature using
the kb-pivot project as the real-world test case. Run every command
yourself, verify every output, and note anything that feels wrong.

**Time estimate:** 45-90 minutes for the full flow.

**What you're testing:** 15 features integrated from 8 adjacent
tools (Org-mode, Fossil, superpowers, TDD, dbt, Obsidian, Linear,
Terraform). The features span CLI commands, PM skill updates, slash
commands, and template quality.

---

## Prerequisites

### 1. Install Keel into your path

From the agent-projects repo:

```bash
cd ~/Code/seido/projects/agent-projects
uv tool install --force --editable .
```

Verify:

```bash
tripwire --version
# → keel, version 0.1.0

tripwire --help
# Should list: agenda, brief, completion, enums, graph, init, next-key,
#   node, plan, refresh, refs, scaffold, status, templates, validate, view
```

If `uv tool install` doesn't work, use `uv run keel` for every
command below (prepend `uv run` and run from the agent-projects dir).

### 2. Verify kb-pivot state

```bash
cd ~/Code/seido/projects/project-kb-pivot
ls raw_planning/
# Should show ~10 .md files: agent-spec.md, api-spec.md, architecture.md, etc.
```

Make sure there's no existing `project.yaml` — if there is, this
project was already initialized with Keel. You may want to `git stash`
or start from a clean state.

---

## Phase 1: Preview what init would create (F15)

Before committing to init, preview the structure.

```bash
tripwire plan --name kb-pivot --format text
```

**What to check:**
- [ ] Shows ~91 files across 5 directories
- [ ] Directories include: `issues/`, `graph/nodes/`, `sessions/`,
  `docs/issues/`, `planning/`
- [ ] Files include: `project.yaml` (jinja), enums, skills, commands,
  examples, orchestration
- [ ] File sizes are non-zero for jinja-rendered files

Now try JSON format (this is what `/pm-plan` would consume):

```bash
tripwire plan --name kb-pivot --format json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d[\"total_files\"]} files, {d[\"total_dirs\"]} dirs')"
```

**Feature tested:** F15 (`tripwire plan` preview).

---

## Phase 2: Initialize the project

```bash
cd ~/Code/seido/projects/project-kb-pivot
tripwire init . --name kb-pivot --key-prefix KBP --no-git
```

`--no-git` because the repo already has git. If init complains
about existing files, add `--force`.

**What to check:**
- [ ] `project.yaml` created with `name: kb-pivot`, `key_prefix: KBP`,
  `base_branch: main`
- [ ] `enums/` directory populated with `issue_status.yaml`,
  `priority.yaml`, etc.
- [ ] `.claude/skills/project-manager/SKILL.md` exists
- [ ] `.claude/commands/` has 12 `pm-*.md` files
- [ ] `planning/` directory exists (your `raw_planning/` is separate —
  you can symlink or copy relevant docs into `planning/` later, or
  just point the PM agent at `raw_planning/` directly)

Verify the project is valid:

```bash
tripwire validate --strict --format=json
```

**Expected:** exit 0 (a fresh project with no issues should pass).

---

## Phase 3: Front-load context (F14 — workflow enum)

```bash
tripwire brief
```

**What to check:**
- [ ] Output starts with `PROJECT: kb-pivot (KBP)`
- [ ] `ISSUE WORKFLOW:` line shows the full status flow:
  `backlog → todo → in_progress → verifying → reviewing → testing → ready → updating → done → canceled`
- [ ] `ACTIVE ENUMS` section lists all enum names with values
- [ ] `NEXT IDS` section shows `next issue key: KBP-1`

**Feature tested:** F14 (default workflow enum surfaced prominently).

---

## Phase 4: Scope the project with the PM agent

This is the main test. Open Claude Code in the kb-pivot directory:

```bash
claude
```

Then invoke the scoping slash command:

```
/pm-scope Transform kb-pivot from single-purpose BO tool to multi-KB platform. Planning docs in ./raw_planning/.
```

**What to observe during execution:**

### F5 — Bite-sized plan template
- [ ] The agent creates a session plan (under `sessions/`) that uses
  the step-by-step format: Steps with **Files**, **Change**, **Code**,
  **Verify**, **Est** fields
- [ ] The plan has a `## Context` section and a `## Verification` section
  (not the old "Goal" / "Approach" format)

### F8 — Failing-first scaffold
- [ ] After creating initial issues/nodes, the agent runs
  `tripwire validate --strict --format=json`
- [ ] Validation FAILS initially (by design) — look for `ref/dangling`
  errors from `[[__PLACEHOLDER__]]` refs or unfilled fields
- [ ] The agent iterates: fix errors → re-validate → fix → re-validate
  until green
- [ ] The agent explicitly mentions the "red-green" pattern

### F7 — Red-flag tables
- [ ] If the agent reads SKILL.md or a WORKFLOWS file, it encounters
  the red-flag tables. You may not see this directly, but if the agent
  says something like "I should not skip validate" or "I need to check
  refs reverse before modifying," the tables are working.

### F6 — Delegation model
- [ ] The agent creates issues and plans but does NOT try to write
  implementation code
- [ ] The agent describes its output as "for delegation to an execution
  agent"
- [ ] Look for the agent staying in PM mode throughout

### F11 — Named validator categories
When the agent runs validate, check the output:
- [ ] Text output groups errors by category: `[ref]`, `[schema]`,
  `[freshness]`, etc.
- [ ] JSON output has a `categories` object with per-category counts

### F12 — Backlinks
- [ ] At some point the agent runs `tripwire refs reverse <node-id>` before
  modifying a concept node (as instructed by SKILL.md)

### F13 — JSON graph as working memory
- [ ] The agent runs `tripwire graph --format=json` to understand the
  project structure

---

## Phase 5: Explore the scoped project

After scoping completes (or even midway through), explore what was
created.

### Agenda (F2)

```bash
tripwire agenda --by status
```

**What to check:**
- [ ] Shows issues grouped by status (backlog, todo, etc.)
- [ ] Each issue has id, title, priority, executor
- [ ] Blocked issues are flagged
- [ ] Critical path is shown at the top

Try JSON:

```bash
tripwire agenda --by executor --format json | python3 -c "
import sys,json
d = json.load(sys.stdin)
print(f'{d[\"total_issues\"]} issues across {len(d[\"groups\"])} executors')
for g in d['groups']:
    print(f'  {g[\"key\"]}: {len(g[\"items\"])} issues')
"
```

Try filtering:

```bash
tripwire agenda --by status --filter "status:todo"
```

### Graph navigation (F10)

Pick an issue or node ID from the agenda output and explore:

```bash
# What does this issue depend on?
tripwire graph --type concept --upstream KBP-1 --format json | python3 -c "
import sys,json
d = json.load(sys.stdin)
print(f'Upstream of KBP-1: {len(d[\"nodes\"])} nodes, {len(d[\"edges\"])} edges')
for n in d['nodes']:
    print(f'  {n[\"id\"]} ({n[\"kind\"]})')
"

# What depends on this node?
tripwire graph --type concept --downstream <some-node-id> --format json
```

**What to check:**
- [ ] `--upstream` returns the node and everything it references
- [ ] `--downstream` returns the node and everything that references it
- [ ] Leaf nodes have empty edge sets
- [ ] The results make structural sense given the kb-pivot planning docs

### Selectors (F9)

```bash
# Validate only one issue and its downstream
tripwire validate --strict --format=json --select KBP-1+
```

**What to check:**
- [ ] Only findings related to KBP-1 and its referrers appear
- [ ] Exit code reflects only the selected subset
- [ ] Much fewer findings than full `tripwire validate`

Try upstream:

```bash
tripwire validate --strict --format=json --select +KBP-1
```

### Status dashboard

```bash
tripwire status
tripwire status --format json
```

### Reference inspection

```bash
tripwire refs list --format json
tripwire refs reverse <some-node-id>
```

**Feature tested:** F12 — see what references a given node.

### Refresh the cache (F18)

```bash
tripwire refresh
# → "graph cache already up-to-date" (if nothing changed)
```

Edit an issue file manually (change a status), then:

```bash
tripwire refresh
# → "graph cache rebuilt"
```

---

## Phase 6: Visual inspection (F19)

```bash
tripwire view --port 7777 --open
```

**What to check:**
- [ ] Browser opens to `http://127.0.0.1:7777`
- [ ] Concept graph rendered with Cytoscape.js — nodes and edges visible
- [ ] Issues table shows all issues grouped by status with colored badges
- [ ] Critical path displayed if one exists
- [ ] Page is read-only — no forms, no edit capabilities
- [ ] Dark theme, clean layout
- [ ] Ctrl+C in terminal stops the server cleanly

**Feature tested:** F19 (`tripwire view` — human brief-in surface).

---

## Phase 7: Incremental update

Back in Claude Code:

```
/pm-update Mark KBP-1 as in_progress
```

**What to observe:**
- [ ] Agent runs `tripwire brief` first
- [ ] Agent modifies the issue file directly
- [ ] Agent runs `tripwire validate --strict --format=json` after
- [ ] Agent checks `tripwire refs reverse KBP-1` if the issue is
  heavily referenced (per the red-flag table instruction)

Then try:

```
/pm-agenda
```

**What to check:**
- [ ] The `/pm-agenda` slash command runs `tripwire agenda --format=json`
  internally
- [ ] Produces an interpreted natural-language summary — not just
  raw data
- [ ] Mentions blocked items, recommendations, next logical action

---

## Phase 8: Interpreted commands

Test each interpretive slash command:

```
/pm-status
```
- [ ] Runs `tripwire status --format=json`, interprets with recommendations

```
/pm-graph
```
- [ ] Runs `tripwire graph --format=json`, analyses critical path and
  parallelizable work

```
/pm-validate
```
- [ ] Runs `tripwire validate --strict --format=json`, interprets errors
  and proposes fixes

---

## Phase 9: Commit and review

If everything looks good, commit the tripwire artifacts:

```bash
cd ~/Code/seido/projects/project-kb-pivot
git add project.yaml enums/ .claude/ sessions/ issues/ graph/ \
  templates/ orchestration/ planning/ standards.md agents/ \
  issue_templates/ comment_templates/ session_templates/
git status  # review what's staged
git commit -m "feat: initialize tripwire project management for kb-pivot"
```

---

## Feature verification checklist

After completing the flow, check off each v0.1 feature:

| # | Feature | How to verify | Pass? |
|---|---|---|---|
| F2 | `tripwire agenda` | Phase 5 — grouped output, filtering, JSON | |
| F4 | README durability framing | Read the README (not testable in-flow) | |
| F5 | Bite-sized plan template | Phase 4 — observe agent plan format | |
| F6 | PM delegation model | Phase 4 — agent stays PM, doesn't code | |
| F7 | Red-flag tables | Phase 4 — agent avoids anti-patterns | |
| F8 | Failing-first scaffold | Phase 4 — red-green validate cycle | |
| F9 | `--select` selectors | Phase 5 — subset validation | |
| F10 | `--upstream/--downstream` | Phase 5 — graph navigation | |
| F11 | Named validator categories | Phase 4/5 — grouped error output | |
| F12 | Backlinks documented | Phase 5 — `refs reverse` usage | |
| F13 | JSON graph documented | Phase 5 — `graph --format=json` usage | |
| F14 | Default workflow enum | Phase 3 — `ISSUE WORKFLOW` in brief | |
| F15 | `tripwire plan` preview | Phase 1 — dry-run output | |
| F18 | `tripwire refresh` | Phase 5 — cache rebuild | |
| F19 | `tripwire view` HTML | Phase 6 — visual inspection | |

---

## What to report back

After running the full flow, tell me:

1. **Gaps in execution** — did the PM agent produce something that
   doesn't match the design? Missing body sections, wrong file
   structure, bad references?
2. **Non-optimal output** — did the plan template feel right? Were
   the steps granular enough? Did the red-flag tables actually
   influence agent behavior?
3. **Feature failures** — did any command error out, produce wrong
   output, or behave unexpectedly?
4. **Missing features** — anything you wished existed during the flow
   that we haven't built yet?
5. **Workflow friction** — any step where the UX felt clunky or the
   command output was confusing?

I'll review the repo state post-creation and cross-reference against
the design to find any gaps the manual testing missed.
