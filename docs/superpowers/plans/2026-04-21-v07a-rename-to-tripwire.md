# Tripwire v0.7a — Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the project from `keel` to `tripwire`. Every import path, CLI command, config field, dotfile, skill doc, and cross-reference changes in one coherent PR.

**Architecture:** Single-branch rename. Python package `src/keel/` → `src/tripwire/`. CLI adds both `tripwire` and `tw` console scripts. Config fields (`keel_version`, `.keel.lock`, `.keel/`, etc.) all change together. Clean cut: no aliases, no transitional parsers, no dual-mode support. After merge, main reflects the new world entirely.

**Tech Stack:** Python 3.13, uv, Pydantic, Click, ruff, pytest.

**Spec:** `docs/specs/2026-04-20-v07-unified.md` §4.

**Scope:** v0.7a only. v0.7b (8 feature phases) is a separate plan written after this merges.

---

## Execution context

This plan runs in a dedicated git worktree at `.worktrees/v0.7a-rename/`. Branch `feature/v0.7a-rename` off main. Create the worktree before starting Task 1.

```bash
cd /Users/maia/Code/seido/projects/keel
git worktree add .worktrees/v0.7a-rename -b feature/v0.7a-rename main
cd .worktrees/v0.7a-rename
uv sync
```

## File structure after rename

```
src/tripwire/                  ← was src/keel/
├── __init__.py
├── cli/
│   ├── main.py                ← both `tripwire` and `tw` scripts entry here
│   └── ...
├── core/
├── models/
├── templates/
├── ui/
└── ...

pyproject.toml                 ← name = "tripwire", scripts = {tripwire, tw}

Project state (in managed projects):
project.yaml                   ← `tripwire_version` field (was keel_version)
.tripwire.lock                 ← was .keel.lock
.tripwire/                     ← was .keel/
  merge-briefs/
  commands/                    ← NEW in v0.7 (project-level slash overrides; dir exists, files optional)
  spawn/                       ← NEW in v0.7 (project-level spawn overrides; dir exists, files optional)
~/.tripwire/logs/              ← was ~/.keel/logs/
```

## Unchanged after rename

- Python module structure inside the package (all files inside `src/tripwire/` keep their names)
- Slash command file names (`pm-session-queue.md` etc. — no "keel" in the names)
- Test file names and locations (`tests/unit/`, `tests/integration/` — just imports update)
- External APIs (subprocess calls, gh CLI interactions, claude CLI interactions)

---

## Task 1: Verify baseline

Before changing anything, confirm the current state is green so we can spot regressions cleanly.

**Files:** none changed

- [ ] **Step 1: Run the full test suite on main**

```bash
cd /Users/maia/Code/seido/projects/keel/.worktrees/v0.7a-rename
uv run pytest tests/ -q 2>&1 | tail -5
```

Expected: all tests pass (870-ish, exact count varies as v0.6c landed).

If any fail: stop. Investigate. Baseline must be clean before proceeding.

- [ ] **Step 2: Run the linter on main**

```bash
uv run ruff check
uv run ruff format --check
```

Expected: all clean.

---

## Task 2: PyPI name availability check

The spec notes (§4.4) that `tripwire` may be taken on PyPI. Check early so Task 18 (version bump + tag) doesn't discover this mid-flight.

**Files:** none changed yet

- [ ] **Step 1: Check `tripwire` availability**

```bash
curl -sf https://pypi.org/pypi/tripwire/json -o /dev/null && echo "TAKEN" || echo "AVAILABLE"
```

- [ ] **Step 2: If taken, fall back to `tripwire-pm`**

If the above prints `TAKEN`: use `tripwire-pm` as the PyPI distribution name wherever this plan says `name = "tripwire"` in pyproject.toml. The *Python package name* (import name, directory name) stays `tripwire` regardless. Only the distribution name on PyPI changes.

Record the chosen name in a scratch file so later tasks are consistent:

```bash
echo "PYPI_NAME=tripwire" > .worktrees/v0.7a-rename/.pypi-name
# or
echo "PYPI_NAME=tripwire-pm" > .worktrees/v0.7a-rename/.pypi-name
```

Do not commit `.pypi-name` — add to `.gitignore` if necessary. This is just a scratch note for later tasks.

---

## Task 3: Rename the package directory

The foundational move. Every subsequent task depends on `src/tripwire/` existing at the right path.

**Files:**
- Rename: `src/keel/` → `src/tripwire/`
- Remove: stale `__pycache__` directories

- [ ] **Step 1: Move the directory**

```bash
git mv src/keel src/tripwire
```

Expected: the directory moves, git tracks the rename.

- [ ] **Step 2: Purge stale pycache**

```bash
find src/tripwire -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find tests -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
```

- [ ] **Step 3: Verify directory structure**

```bash
ls src/tripwire/
```

Expected: `__init__.py cli core models templates ui`

- [ ] **Step 4: Commit**

Tests won't pass yet because imports aren't updated. That's fine — the rename itself is safe as a first commit; Task 4 fixes imports.

```bash
git add -A
git commit -m "rename: move src/keel/ to src/tripwire/"
```

---

## Task 4: Update import paths (package-wide)

Every `from keel.X import Y` and `import keel.X` in both source and tests needs to change.

**Files:**
- Modify: every `.py` file under `src/tripwire/` and `tests/` that imports from the package.

- [ ] **Step 1: Find every affected file**

```bash
grep -rln "from keel\|import keel" src/tripwire/ tests/ 2>/dev/null > /tmp/keel-imports.txt
wc -l /tmp/keel-imports.txt
```

Expected: ~60-70 files.

- [ ] **Step 2: Replace imports in bulk (macOS sed)**

```bash
while IFS= read -r f; do
  sed -i '' \
    -e 's/^from keel\./from tripwire./g' \
    -e 's/^from keel import/from tripwire import/g' \
    -e 's/^import keel$/import tripwire/g' \
    -e 's/^import keel\./import tripwire./g' \
    "$f"
done < /tmp/keel-imports.txt
```

Note: these regexes anchor on `^` (start of line) to avoid catching strings that happen to contain "keel" mid-line (docstrings, comments referencing the old name).

- [ ] **Step 3: Verify no imports remain**

```bash
grep -rn "^from keel\|^import keel" src/tripwire/ tests/ 2>/dev/null
```

Expected: no output.

- [ ] **Step 4: Also patch `monkeypatch.setattr` and `patch(...)` string references**

Test mocks often reference modules as strings like `patch("keel.cli.session._launch_claude")`. Replace those too:

```bash
grep -rln "\"keel\." tests/ src/tripwire/ 2>/dev/null > /tmp/keel-strings.txt
while IFS= read -r f; do
  sed -i '' 's/"keel\./"tripwire./g' "$f"
done < /tmp/keel-strings.txt

# And single-quoted variants
grep -rln "'keel\." tests/ src/tripwire/ 2>/dev/null > /tmp/keel-strings-sq.txt
while IFS= read -r f; do
  sed -i '' "s/'keel\\./'tripwire./g" "$f"
done < /tmp/keel-strings-sq.txt
```

- [ ] **Step 5: Run tests to see what breaks**

```bash
uv run pytest tests/ -q 2>&1 | tail -20
```

Many failures expected at this point because pyproject.toml still says `name = "keel"` and console_scripts point at keel. This is where Task 5 lands.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "rename: update import paths keel → tripwire (src + tests)"
```

---

## Task 5: Update pyproject.toml

The package name, distribution name, and console scripts all change.

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read current entries**

```bash
grep -n "keel\|^name\|project.scripts" pyproject.toml
```

- [ ] **Step 2: Update `[project]` block**

Open `pyproject.toml`. In the `[project]` section:

```toml
# BEFORE
name = "keel"

# AFTER
name = "tripwire"          # or "tripwire-pm" if PyPI name is taken (see Task 2)
```

Keep `version = "0.6.0"` for now. Task 18 bumps to `0.7.0`.

- [ ] **Step 3: Update `[project.scripts]`**

Replace the single-entry scripts block:

```toml
# BEFORE
[project.scripts]
keel = "keel.cli.main:cli"

# AFTER
[project.scripts]
tripwire = "tripwire.cli.main:cli"
tw = "tripwire.cli.main:cli"
```

- [ ] **Step 4: Search for any other keel references**

```bash
grep -n "keel" pyproject.toml
```

If matches appear (test config, coverage paths, etc.), update them to `tripwire`. Likely candidates: `[tool.pytest.ini_options]` paths, `[tool.coverage]` source lists.

- [ ] **Step 5: Re-sync dependencies**

```bash
uv sync
```

Expected: uv detects the name change and re-resolves. Takes ~30 seconds. Now both `tripwire` and `tw` should be available as console scripts in the venv.

- [ ] **Step 6: Verify scripts installed**

```bash
uv run tripwire --help | head -5
uv run tw --help | head -5
```

Expected: both show the CLI help (same command).

- [ ] **Step 7: Run the full test suite**

```bash
uv run pytest tests/ -q 2>&1 | tail -5
```

Expected: most pass now. Some may still fail due to templates or hardcoded strings referencing "keel"; Tasks 6-11 handle those.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "rename: update pyproject.toml name and console scripts"
```

---

## Task 6: Rename path constants

The `paths.py` module holds `.keel.lock`, `.keel/merge-briefs`, and similar string constants. These need updating and the matching fixture data/tests with them.

**Files:**
- Modify: `src/tripwire/core/paths.py`
- Modify: any tests that reference the string constants

- [ ] **Step 1: Update path constants**

Edit `src/tripwire/core/paths.py`. Find these constants and update the string values:

```python
# BEFORE
PROJECT_LOCK = ".keel.lock"
MERGE_BRIEFS_DIR = ".keel/merge-briefs"

# AFTER
PROJECT_LOCK = ".tripwire.lock"
MERGE_BRIEFS_DIR = ".tripwire/merge-briefs"
```

- [ ] **Step 2: Search for any other `.keel` / `keel/` literal strings in core**

```bash
grep -rn '\.keel\|"keel/' src/tripwire/core/ 2>/dev/null
```

Update each match to `.tripwire` / `"tripwire/` respectively.

- [ ] **Step 3: Update test fixtures referencing old paths**

```bash
grep -rn '\.keel\.lock\|\.keel/' tests/ 2>/dev/null > /tmp/keel-paths-tests.txt
cat /tmp/keel-paths-tests.txt
```

For each match, replace `.keel.lock` → `.tripwire.lock`, `.keel/` → `.tripwire/`. Use `sed`:

```bash
awk -F: '{print $1}' /tmp/keel-paths-tests.txt | sort -u | while read f; do
  sed -i '' \
    -e 's/\.keel\.lock/.tripwire.lock/g' \
    -e 's/\.keel\//.tripwire\//g' \
    "$f"
done
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "rename: update .keel path constants to .tripwire"
```

---

## Task 7: Rename `keel_version` field to `tripwire_version`

The project and workspace models carry a `keel_version` field (or similar). These are the canonical version stamps that new projects get and CI pins against.

**Files:**
- Modify: `src/tripwire/models/project.py`
- Modify: `src/tripwire/models/workspace.py`
- Modify: any code that reads/writes `keel_version`
- Modify: test fixtures + test projects that declare the field

- [ ] **Step 1: Find all references**

```bash
grep -rn "keel_version" src/tripwire/ tests/ 2>/dev/null
```

Expected: ~20-30 references across models, stores, validator, tests.

- [ ] **Step 2: Replace `keel_version` → `tripwire_version` in source**

```bash
grep -rln "keel_version" src/tripwire/ 2>/dev/null | while read f; do
  sed -i '' 's/keel_version/tripwire_version/g' "$f"
done
```

- [ ] **Step 3: Replace in tests**

```bash
grep -rln "keel_version" tests/ 2>/dev/null | while read f; do
  sed -i '' 's/keel_version/tripwire_version/g' "$f"
done
```

- [ ] **Step 4: Also update fixture YAML in tests**

```bash
grep -rln "keel_version" tests/ 2>/dev/null
```

If any `.yaml` files appear: they're test fixtures. The sed in Step 3 already handled `.yaml` files (grep/sed don't filter by extension); verify by re-running the grep and confirming zero results.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "rename: keel_version field → tripwire_version in models and fixtures"
```

---

## Task 8: Update CLI help text, docstrings, and user-facing messages

Python files have module-level docstrings, CLI help strings, and error message formatting that mention "keel". These are user-facing and need updating.

**Files:**
- Modify: `src/tripwire/cli/main.py` (top-level CLI description)
- Modify: all `src/tripwire/cli/*.py` (per-command help text)
- Modify: `src/tripwire/cli/init.py` (init messages, CLAUDE.md template references)
- Modify: any `raise ClickException("... keel ...")` call sites

- [ ] **Step 1: Find user-facing "keel" references in CLI and core**

```bash
grep -rn '"keel"\|"Keel"\|Keel \|\`keel\`\|\bkeel\b' src/tripwire/cli/ src/tripwire/core/ 2>/dev/null | head -40
```

This will catch docstrings, f-strings, and click help text.

- [ ] **Step 2: Review and replace case-by-case**

Go file-by-file. For each match:
- If it's a docstring or CLI help text describing the tool: replace "keel" with "tripwire".
- If it's a CLI command reference like `Run \`keel validate\``: replace with `Run \`tripwire validate\``.
- If it's a repo-name reference (e.g., `SeidoAI/keel`): leave alone for now — see Task 10 for repo handling.

Some specific hot spots to check:
- `src/tripwire/cli/main.py` — the top-level group docstring
- `src/tripwire/cli/init.py` — welcome message, CLAUDE.md rendering
- `src/tripwire/cli/validate.py` — "Run `keel validate --strict`" in hints
- `src/tripwire/cli/lint.py` — lint command descriptions

Use ripgrep + manual editing here, not bulk sed, because some "keel" references (in comments about history, or in strings that are part of test data) should not change.

- [ ] **Step 3: Run tests after each file**

```bash
uv run pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "rename: update CLI help text and user-facing messages"
```

---

## Task 9: Update templates — CLAUDE.md, standards, slash commands, skills, examples

The `src/tripwire/templates/` tree contains Jinja templates shipped to projects via `tripwire init`. Every reference to "keel" in these becomes "tripwire".

**Files:**
- Modify: `src/tripwire/templates/project/CLAUDE.md.j2`
- Modify: `src/tripwire/templates/standards.md.j2`
- Modify: every `src/tripwire/templates/commands/pm-*.md` (slash command bodies)
- Modify: every `src/tripwire/templates/skills/**/*.md` (skill docs, references, examples)
- Modify: `src/tripwire/templates/enums/**/*.yaml` (descriptions)
- Modify: `src/tripwire/templates/artifacts/manifest.yaml` if it mentions keel in comments

- [ ] **Step 1: Find every reference in templates**

```bash
grep -rln "keel\|\.keel" src/tripwire/templates/ 2>/dev/null > /tmp/keel-templates.txt
wc -l /tmp/keel-templates.txt
```

Expected: ~40-60 files.

- [ ] **Step 2: Bulk replace the common patterns**

```bash
while IFS= read -r f; do
  sed -i '' \
    -e 's/`keel /`tripwire /g' \
    -e 's/keel validate/tripwire validate/g' \
    -e 's/keel lint/tripwire lint/g' \
    -e 's/keel brief/tripwire brief/g' \
    -e 's/keel agenda/tripwire agenda/g' \
    -e 's/keel session/tripwire session/g' \
    -e 's/keel issue/tripwire issue/g' \
    -e 's/keel next-key/tripwire next-key/g' \
    -e 's/keel refs/tripwire refs/g' \
    -e 's/keel node/tripwire node/g' \
    -e 's/keel workspace/tripwire workspace/g' \
    -e 's/keel ci/tripwire ci/g' \
    -e 's/keel init/tripwire init/g' \
    -e 's/\.keel\.lock/.tripwire.lock/g' \
    -e 's/\.keel\//.tripwire\//g' \
    "$f"
done < /tmp/keel-templates.txt
```

- [ ] **Step 3: Find remaining `keel` references**

```bash
grep -rn "\bkeel\b" src/tripwire/templates/ 2>/dev/null
```

For each remaining match, review in context and decide:
- Generic prose like "You are using keel to manage this project" → update to tripwire
- Historical references (e.g., "in v0.5 keel's ...") → update or leave (PM judgment)
- Code examples where a variable happens to be named `keel` → leave

Go through the list and update manually where needed.

- [ ] **Step 4: Update CLAUDE.md.j2 explicitly**

This is the file that gets rendered into every new project. Open `src/tripwire/templates/project/CLAUDE.md.j2` and verify:
- Tool name references → tripwire
- Command invocations (`keel validate` → `tripwire validate`)
- `keel_version` → `tripwire_version` (should already be handled by Task 7)
- Any meta-references to the framework → tripwire

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/ -q 2>&1 | tail -5
```

Some tests may still fail if test projects reference old names in their YAML. That's Task 12. Proceed.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "rename: update templates (CLAUDE.md, slash commands, skills) to tripwire"
```

---

## Task 10: Update repo references and docs

Text in `docs/`, `README.md`, and `CONTRIBUTING.md` (if present) referring to the project by name or linking to GitHub URLs.

**Files:**
- Modify: `README.md`
- Modify: `docs/**/*.md` (except `docs/specs/` — those are historical records)
- Modify: `docs/superpowers/plans/` except this plan

- [ ] **Step 1: Find `keel` in README and docs**

```bash
grep -rln "\bkeel\b\|\.keel\|SeidoAI/keel" README.md docs/ 2>/dev/null | \
  grep -v "docs/specs/" > /tmp/keel-docs.txt
wc -l /tmp/keel-docs.txt
cat /tmp/keel-docs.txt
```

- [ ] **Step 2: Replace**

```bash
while IFS= read -r f; do
  sed -i '' \
    -e 's/SeidoAI\/keel/SeidoAI\/tripwire/g' \
    -e 's/`keel /`tripwire /g' \
    -e 's/keel validate/tripwire validate/g' \
    -e 's/keel lint/tripwire lint/g' \
    -e 's/keel brief/tripwire brief/g' \
    -e 's/keel agenda/tripwire agenda/g' \
    -e 's/keel session/tripwire session/g' \
    -e 's/keel issue/tripwire issue/g' \
    -e 's/keel next-key/tripwire next-key/g' \
    -e 's/keel refs/tripwire refs/g' \
    -e 's/keel init/tripwire init/g' \
    -e 's/\.keel\.lock/.tripwire.lock/g' \
    -e 's/\.keel\//.tripwire\//g' \
    "$f"
done < /tmp/keel-docs.txt
```

- [ ] **Step 3: Handle `README.md` manually**

`README.md` likely has a project tagline, install instructions, and introductory text. Open it and ensure:
- Top-of-file project name/title → Tripwire
- Install instructions reference `tripwire` (PyPI package)
- Any URL to GitHub (`SeidoAI/keel` → `SeidoAI/tripwire`) — these will keep working even before the GitHub repo rename due to GitHub's automatic redirects, but they should be updated for correctness.
- Example CLI invocations → `tripwire X` or `tw X`

- [ ] **Step 4: Historical specs stay as-is**

Files in `docs/specs/` are point-in-time design records. Do NOT rewrite them; they reference `keel` because that was the name when they were written. The v0.7 spec itself already uses `tripwire` because it was written after the brainstorm decision.

Verify:

```bash
grep -l "^name.*tripwire\|^# Tripwire" docs/specs/2026-04-20-v07-unified.md
```

Expected: match. If not, the spec file needs a title update — but that should already have been done when the spec was written.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/
git commit -m "rename: update README and docs references to tripwire"
```

---

## Task 11: Log directory path update

The `_launch_claude` function and the log_path default in `tripwire/cli/session.py` reference `~/.keel/logs/`. Update to `~/.tripwire/logs/`.

**Files:**
- Modify: `src/tripwire/cli/session.py` (look for `keel/logs` or `.keel/logs`)

- [ ] **Step 1: Find log path references**

```bash
grep -rn "keel/logs\|\.keel/logs" src/tripwire/ tests/ 2>/dev/null
```

- [ ] **Step 2: Replace**

```bash
grep -rln "keel/logs\|\.keel/logs" src/tripwire/ tests/ 2>/dev/null | while read f; do
  sed -i '' \
    -e 's/\.keel\/logs/.tripwire\/logs/g' \
    -e 's/keel\/logs/tripwire\/logs/g' \
    "$f"
done
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "rename: update log directory path to ~/.tripwire/logs/"
```

---

## Task 12: Migrate test projects

Three tracked test projects (`kb-pivot`, `graph-ui-v2`, `project-keel-ui-init`) live outside the keel repo at `/Users/maia/Code/seido/projects/`. Their `project.yaml` declares `keel_version`. These must migrate.

**Files:** outside the current worktree. Modified in sibling project directories.

**Note on scope:** per standing memory instruction, work only within authorized repo scope. The three test projects are explicitly mentioned in the v0.7 spec as needing migration, so they're in scope. Confirm with the user before running this task if any ambiguity.

- [ ] **Step 1: List the test projects**

```bash
ls -d /Users/maia/Code/seido/projects/kb-pivot \
     /Users/maia/Code/seido/projects/project-graph-ui-v2 \
     /Users/maia/Code/seido/projects/project-keel-ui-init 2>/dev/null
```

Expected: all three directories exist. If one is missing, note it but continue with the others.

- [ ] **Step 2: Update `project.yaml` in each**

For each project:

```bash
for proj in /Users/maia/Code/seido/projects/kb-pivot \
            /Users/maia/Code/seido/projects/project-graph-ui-v2 \
            /Users/maia/Code/seido/projects/project-keel-ui-init ; do
  [ -f "$proj/project.yaml" ] || continue
  sed -i '' \
    -e 's/^keel_version:/tripwire_version:/g' \
    -e 's/keel_version:/tripwire_version:/g' \
    "$proj/project.yaml"
done
```

Note: these projects are separate git repos. They need their own commits. Coordinate with the user before committing changes to them. If user prefers, *prepare* these changes locally but let them handle the commits in each repo's own PR.

- [ ] **Step 3: Rename any `.keel.lock` / `.keel/` dirs present**

Per-project:

```bash
for proj in /Users/maia/Code/seido/projects/kb-pivot \
            /Users/maia/Code/seido/projects/project-graph-ui-v2 \
            /Users/maia/Code/seido/projects/project-keel-ui-init ; do
  [ -f "$proj/.keel.lock" ] && mv "$proj/.keel.lock" "$proj/.tripwire.lock"
  [ -d "$proj/.keel" ] && mv "$proj/.keel" "$proj/.tripwire"
done
```

- [ ] **Step 4: Validate each project with the new CLI**

```bash
cd /Users/maia/Code/seido/projects/keel/.worktrees/v0.7a-rename
for proj in /Users/maia/Code/seido/projects/kb-pivot \
            /Users/maia/Code/seido/projects/project-graph-ui-v2 \
            /Users/maia/Code/seido/projects/project-keel-ui-init ; do
  echo "=== $proj ==="
  [ -f "$proj/project.yaml" ] || { echo "skip (no project.yaml)"; continue; }
  uv run tripwire validate --project-dir "$proj" --strict 2>&1 | tail -3
done
```

Expected: each validates cleanly (or with only pre-existing warnings, not new errors tied to the rename).

If a project fails validation because of a lingering `keel` reference in its own issue/session YAMLs: that's a content issue for that project. Log it in the PR description; don't fix it in this rename PR.

- [ ] **Step 5: Do not commit test project changes here**

This plan's PR is in `SeidoAI/tripwire`. Each test project is its own repo. Their changes go in their own PRs. Note the migration state in this PR's description so whoever merges coordinates.

---

## Task 13: Check for stale references

After Tasks 3-11, verify every `keel` reference is gone from places that should be tripwire.

**Files:** none changed; verification only

- [ ] **Step 1: Find stragglers in source**

```bash
grep -rn "\bkeel\b" src/tripwire/ 2>/dev/null | \
  grep -v "\.pyc\|__pycache__\|keel_" | head -30
```

Review each match. Legitimate reasons to keep "keel":
- In a historical reference like "migrated from keel in v0.7"
- In a string that's part of test data where the literal "keel" is needed (rare)
- In a comment describing backwards-compat behavior (shouldn't exist; we did clean cut)

For anything else, update it.

- [ ] **Step 2: Find stragglers in templates**

```bash
grep -rn "\bkeel\b" src/tripwire/templates/ 2>/dev/null
```

Expected: near-zero. Each match: review and fix.

- [ ] **Step 3: Check tests**

```bash
grep -rn "\bkeel\b" tests/ 2>/dev/null | head -30
```

Some "keel" in tests may be legitimate (e.g., a test checks that an error message mentions "keel" historically — unlikely but possible). Review each.

- [ ] **Step 4: Check that console scripts work**

```bash
uv run tripwire --help | head -3
uv run tw --help | head -3
uv run tripwire validate --help | head -5
uv run tw session --help | head -5
```

All four should output valid help text.

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git diff --cached --stat  # review what's changing
git commit -m "rename: clean up stragglers"
```

If no stragglers: skip commit.

---

## Task 14: Full test suite + lint

Full green on the renamed codebase. This is the go/no-go gate before merging.

**Files:** none changed; verification only

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest tests/ -v 2>&1 | tail -20
```

Expected: all tests pass. Exact count should match the baseline (Task 1) — renames don't add or remove tests.

If count differs: investigate. Usually means a test file got skipped (import error) or a new test got added mid-rename.

- [ ] **Step 2: Run ruff check**

```bash
uv run ruff check
```

Expected: clean.

- [ ] **Step 3: Run ruff format check**

```bash
uv run ruff format --check
```

Expected: clean. If files need formatting:

```bash
uv run ruff format
git add -A
git commit -m "rename: format files"
```

- [ ] **Step 4: Run a smoke test on a real project**

Check that `tripwire brief` works against one of the test projects:

```bash
uv run tripwire brief --project-dir /Users/maia/Code/seido/projects/project-graph-ui-v2 2>&1 | head -20
```

Expected: brief output renders with project state. If error: investigate.

---

## Task 15: Push branch and open PR

**Files:** none changed; git operation

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feature/v0.7a-rename
```

- [ ] **Step 2: Create the PR**

```bash
gh pr create --title "v0.7a: rename keel → tripwire" --body "$(cat <<'EOF'
## Summary

Renames the package from `keel` to `tripwire` per the v0.7 spec
(§4 of `docs/specs/2026-04-20-v07-unified.md`).

**Scope — this PR:**
- Package directory: `src/keel/` → `src/tripwire/`
- CLI console scripts: `tripwire` (canonical) + `tw` (alias)
- Import paths across source and tests
- Config fields: `keel_version` → `tripwire_version`
- Dotfiles: `.keel.lock` → `.tripwire.lock`, `.keel/` → `.tripwire/`
- Log directory: `~/.keel/logs/` → `~/.tripwire/logs/`
- Templates: CLAUDE.md, slash commands, skill docs, examples
- README and non-spec docs

**Out of scope (separate PRs in test project repos):**
- Migrations for the three test projects (kb-pivot, graph-ui-v2,
  keel-ui-init) — their `project.yaml` and dotfile renames happen
  in their own PRs.

**Out of scope (v0.7b):**
- Configurability pass, vocabulary alignment, per-issue artifacts,
  spawn config refactor, monitor/review/complete commands, CI.
  These land in the v0.7b plan after this merges.

## Test plan

- [ ] Full test suite passes (baseline count preserved)
- [ ] ruff check clean
- [ ] ruff format --check clean
- [ ] Both `tripwire` and `tw` console scripts resolve
- [ ] `tripwire brief` works against a real project directory

## After merge

1. Rename GitHub repo `SeidoAI/keel` → `SeidoAI/tripwire` (GitHub
   auto-redirects old URLs)
2. Open migration PRs in each of the three test project repos
3. Write v0.7b implementation plan (separate document)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Share PR URL with user for review**

The PR URL is printed by `gh pr create`. Report it back.

---

## Task 16: Await PR merge (no action by executor)

The executor stops here. Merging the PR is the user's decision. Once merged, the repo rename step (GitHub UI) also happens.

Steps the user takes outside this plan:
1. Review the PR
2. Merge (squash or rebase per repo convention)
3. Rename GitHub repo in settings: `keel` → `tripwire`
4. Coordinate migration PRs in the three test project repos

---

## Task 17: Post-merge repo rename verification

After the user renames the GitHub repo, verify the redirect works and local remote URLs update.

**Files:** none changed; git operation

- [ ] **Step 1: Confirm the repo rename landed**

```bash
gh repo view SeidoAI/tripwire --json name,url | head -5
```

Expected: returns repo metadata showing the new name.

- [ ] **Step 2: Update the local clone's remote URL**

```bash
cd /Users/maia/Code/seido/projects/keel
git remote set-url origin https://github.com/SeidoAI/tripwire.git
git remote get-url origin
```

- [ ] **Step 3: Consider renaming the local directory**

The local clone is at `/Users/maia/Code/seido/projects/keel/`. The user may want to rename it to `/Users/maia/Code/seido/projects/tripwire/`. This is purely cosmetic and entirely user choice — nothing in the codebase depends on the directory name being a specific value.

If renaming: close all worktrees first, then:

```bash
cd /Users/maia/Code/seido/projects/
git worktree list  # check no stale worktrees in keel/
mv keel tripwire
cd tripwire
uv sync  # re-resolve paths
```

This is optional. Leave as "user's call" in the PR description.

---

## Task 18: Tag v0.7a

A pre-release tag so we can reference this state in subsequent work.

**Files:** none changed; git operation

- [ ] **Step 1: Ensure main is at the merged commit**

```bash
git checkout main
git pull origin main
git log --oneline -5
```

Expected: the merge commit for v0.7a is at or near HEAD.

- [ ] **Step 2: Tag**

```bash
git tag -a v0.7a -m "v0.7a: rename keel → tripwire"
git push origin v0.7a
```

Note: NO PyPI publish at this tag. That happens in v0.7b Phase 8 alongside the version bump to 0.7.0 and the full publish workflow. v0.7a is a repo milestone tag only.

- [ ] **Step 3: Announce**

Report back to the user: "v0.7a merged and tagged. Ready to write the v0.7b plan when you are."

---

## Verification summary

Before declaring v0.7a complete:

1. `uv run pytest tests/ -q` — all pass (matches baseline count)
2. `uv run ruff check` — clean
3. `uv run ruff format --check` — clean
4. `uv run tripwire --help` and `uv run tw --help` both work
5. `uv run tripwire brief --project-dir <any test project>` works
6. `grep -rn '\bkeel\b' src/tripwire/` returns near-zero (only legitimate historical references)
7. `grep -rn 'keel_version' src/ tests/` returns zero
8. GitHub repo renamed to `SeidoAI/tripwire`
9. Tag `v0.7a` pushed

## What this plan does NOT do

- Configurability pass (Phase 0)
- Vocabulary alignment / `verified` status (Phase 1)
- Per-issue artifacts / insights capture (Phase 2)
- Canonical spawn config (Phase 3)
- Monitor / review / complete commands (Phases 4-6)
- CI / PyPI publishing (Phases 7-8)
- README reorganization with design principles

Each of these lands in the v0.7b plan, written after this v0.7a plan executes and merges.
