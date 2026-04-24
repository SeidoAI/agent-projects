# Keel v1.0 — Package split (keel-projects / keel-ui / keel-containers)

**Status**: idea (deferred to major release)
**Date**: 2026-04-16
**Replaces**: [[dec-single-package-monorepo]] (partially — keeps the
monorepo, splits the package)
**Source**: parallel-agent development pain during keel-ui-init
scoping + execution

---

## 1. The problem

Keel is a single Python package (`pip install keel`) containing three
logically independent modules: projects (core CLI + validator),
UI (FastAPI + React dashboard), and containers (Docker execution
runtime). The single-package decision was made for simplicity before
parallel agent development was a reality.

Now that multiple agents work in the same repo simultaneously
(PM agent on project files, backend-coder on `src/keel/ui/`,
frontend-coder on `src/keel/ui/frontend/`, keel-projects agent on
`src/keel/core/`), the shared-package model creates concrete pain:

1. **`pyproject.toml` is a merge-conflict magnet.** Every module
   adds deps to the same file. Two agents touching it on different
   branches guarantees conflicts.
2. **Import boundaries are unenforced.** Nothing prevents
   `keel.core` from importing `keel.ui`. The `[projects]` extra
   would break at runtime, but there's no development-time guard.
3. **Tests share a namespace.** `tests/ui/` and `tests/unit/` run
   under the same `pytest` invocation. No isolation.
4. **Release coupling.** A bugfix in `keel.core` forces a release
   that includes whatever half-finished state `keel.ui` is in.
5. **The `src/keel/` nesting is redundant.** `src/keel/core/`,
   `src/keel/ui/`, `src/keel/containers/` — the `keel/` level
   exists only because Python packaging requires
   `src/<package_name>/`.

## 2. The proposal

Split into three independently-installable packages sharing the
`keel.` namespace via PEP 420 implicit namespace packages. Keep the
monorepo — one git repo, three packages.

### 2.1 Physical layout

```
keel/                               # git repo root (unchanged)
├── packages/
│   ├── keel-projects/
│   │   ├── pyproject.toml          # pydantic, click, yaml, rich, jinja2
│   │   ├── src/keel/projects/      # was src/keel/core/ + src/keel/models/
│   │   │   ├── cli/                # was src/keel/cli/
│   │   │   ├── core/               # store, graph, validator, etc.
│   │   │   ├── models/             # pydantic models
│   │   │   └── templates/          # jinja templates, skill templates
│   │   └── tests/
│   │
│   ├── keel-ui/
│   │   ├── pyproject.toml          # depends on keel-projects + fastapi, etc.
│   │   ├── src/keel/ui/
│   │   │   ├── server.py
│   │   │   ├── routes/
│   │   │   ├── services/
│   │   │   ├── ws/
│   │   │   └── frontend/           # React app
│   │   └── tests/
│   │
│   └── keel-containers/
│       ├── pyproject.toml          # depends on keel-projects + docker
│       ├── src/keel/containers/
│       └── tests/
│
├── pyproject.toml                  # meta-package: depends on all three
├── docs/
└── .github/
```

**Key property:** no `keel/__init__.py` at the namespace level.
`keel.projects`, `keel.ui`, `keel.containers` are independent
packages that happen to share the `keel.` prefix. Python's implicit
namespace package mechanism (PEP 420) makes this work without a
shared init file.

### 2.2 Import paths (migration)

| Before (v0.x) | After (v1.0) |
|---|---|
| `from keel.core.store import ...` | `from keel.projects.core.store import ...` |
| `from keel.models.issue import ...` | `from keel.projects.models.issue import ...` |
| `from keel.cli.main import cli` | `from keel.projects.cli.main import cli` |
| `from keel.ui.server import ...` | `from keel.ui.server import ...` (unchanged) |
| `from keel.ui.config import ...` | `from keel.ui.config import ...` (unchanged) |
| `import keel.containers` | `import keel.containers` (unchanged) |

UI and containers imports don't change. Only core/models/cli move
under `keel.projects`.

### 2.3 Install commands

```bash
pip install keel               # meta-package → installs all three
pip install keel-projects      # just CLI + validator (was keel[projects])
pip install keel-ui            # dashboard (pulls keel-projects as dep)
pip install keel-containers    # execution runtime (pulls keel-projects)
```

The `keel` meta-package's `pyproject.toml` is trivial:
```toml
[project]
dependencies = ["keel-projects", "keel-ui", "keel-containers"]
```

### 2.4 Dev experience with uv workspaces

`uv` has first-class monorepo workspace support:

```toml
# root pyproject.toml
[tool.uv.workspace]
members = ["packages/*"]
```

`uv sync` in the root installs all three packages in editable mode.
`uv run pytest packages/keel-projects/tests/` runs only projects
tests. Each package's `pyproject.toml` can declare its own deps
without conflicting with the others.

## 3. What this solves

| Problem | How it's solved |
|---|---|
| pyproject.toml conflicts | Each package has its own — no shared file |
| Import boundary enforcement | Cross-package = explicit dependency declaration; import linter becomes trivial |
| Test isolation | Each package has own test suite; CI runs them independently |
| Release coupling | Can release keel-projects 1.0.1 without touching keel-ui |
| Parallel agent safety | Agents own disjoint package directories |
| The `src/keel/` redundancy | Eliminated — `packages/keel-ui/src/keel/ui/` is the natural path |

## 4. What this doesn't solve

- Cross-package API stability (keel-ui depends on keel-projects
  internals — need a stable public API boundary)
- Shared CI config (still one repo, one `.github/workflows/`)
- The meta-package still needs coordinated version bumps for
  major releases

## 5. Migration strategy

1. Create `packages/` directory structure
2. Move files with `git mv` to preserve history
3. Split `pyproject.toml` into per-package files
4. Add `[tool.uv.workspace]` to root
5. Add compatibility shims: `keel.core` → `keel.projects.core`
   re-exports for one release cycle
6. Update all internal imports
7. Run full test suite against new layout
8. Remove shims in the following release

Estimated effort: ~2 weeks (including import migration, CI updates,
and testing).

## 6. Open questions

- **Should `keel.cli` stay with projects or become its own package?**
  The CLI registers commands from all three modules (projects, ui,
  containers). It could be a fourth package or stay with projects
  (which is where most commands live). Lean: stays with projects;
  UI and containers register their commands via entry points.
- **Entry point registration vs direct import for CLI commands.**
  Currently `cli/main.py` directly imports `from keel.cli.ui import
  ui_cmd`. With the split, this becomes a cross-package import.
  Better: use `importlib.metadata.entry_points` so each package
  registers its own CLI commands. Cleaner but more indirection.
- **Should the namespace be `keel.projects` or just keep `keel.core`
  under the `keel-projects` package?** I.e.,
  `from keel.core.store import ...` (package is keel-projects,
  import path has `core`) vs `from keel.projects.store import ...`
  (import path matches package name). Lean: match package name for
  clarity.
- **React frontend**: stays inside `keel-ui` package
  (`packages/keel-ui/src/keel/ui/frontend/`) or moves to its own
  top-level `packages/keel-ui-frontend/`? Lean: stays inside
  keel-ui — it's built into the Python wheel, not independently
  deployable.

## 7. Decision to revisit

This spec replaces [[dec-single-package-monorepo]] which chose the
single-package model for simplicity. The parallel-agent workflow
has made the costs concrete:
- 2 pyproject.toml conflicts in the first 2 sessions
- 0 import boundary violations caught by tooling (no tooling exists)
- Test runs include unrelated modules (UI tests run during core
  changes)

Revisit at v1.0 when the UI and containers modules are stable enough
that the migration cost is worth the ongoing benefit.
