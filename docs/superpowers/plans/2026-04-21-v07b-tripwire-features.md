# Tripwire v0.7b — Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship v0.7b's eight feature phases — configurability pass, vocabulary alignment with verified stage, per-issue artifacts with insights capture, canonical spawn configuration, session monitor/review/complete commands, and CI + PyPI publishing.

**Architecture:** Phased rollout on a single branch (`feature/v0.7b`). Phase 0 externalizes hardcoded domain concepts, unblocking later phases that need YAML-driven config. Phase 1 renames phase vocabulary and adds the `verified` stage. Phase 2 enforces per-issue developer/verified notes and captures agent-proposed concept-node updates. Phase 3 moves spawn invocation into YAML. Phases 4-6 add PM lifecycle CLI commands and slash wrappers. Phases 7-8 ship CI for the tripwire repo and PyPI publishing with project workflow templates.

**Tech Stack:** Python 3.13, uv, Pydantic, Click, ruff, pytest, Jinja2, GitHub Actions, PyPI.

**Spec:** `docs/superpowers/specs/2026-04-20-v07-unified-design.md` §5-12.

**Prerequisite:** v0.7a rename merged (`src/tripwire/` exists, CLI is `tripwire`/`tw`, `tripwire_version` field, `.tripwire.lock` etc.).

---

## Execution context

Dedicated worktree. Create before Phase 0:

```bash
cd /Users/maia/Code/seido/projects/tripwire  # or keel/ if local dir not renamed
git worktree add .worktrees/v0.7b -b feature/v0.7b main
cd .worktrees/v0.7b
uv sync
uv run pytest tests/ -q 2>&1 | tail -3   # baseline
```

## Phase dependency graph

```
Phase 0 (configurability) ─┬─→ Phase 1 (vocabulary + verified)
                           │        │
                           │        ▼
                           │   Phase 2 (per-issue artifacts + insights)
                           │        │
                           │        ▼
                           │   Phase 5 (review) ─→ Phase 6 (complete)
                           │        ▲
                           │        │ (writes verified.md side-effect)
                           │
                           └─→ Phase 3 (spawn config)
                                    │
                                    ▼
                               Phase 4 (monitor)

Phase 7 (tripwire CI)  ← independent
Phase 8 (PyPI + project CI) ← after Phase 7
```

Suggested execution order: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. Each phase merges to `feature/v0.7b` on success; final merge to main after Phase 8.

## File structure overview

```
src/tripwire/
├── templates/
│   ├── enums/
│   │   ├── artifact_phase.yaml           [NEW, Phase 0]
│   │   ├── agent_type.yaml                [NEW, Phase 0]
│   │   ├── branch_type.yaml               [NEW, Phase 0]
│   │   ├── issue_status.yaml              [MODIFIED, Phase 1: add `verified`]
│   │   └── session_status.yaml            [MODIFIED, Phase 1: add `verified`]
│   ├── spawn/
│   │   └── defaults.yaml                  [NEW, Phase 3]
│   ├── issue_artifacts/
│   │   ├── manifest.yaml                  [NEW, Phase 2]
│   │   ├── developer.md.j2                [NEW, Phase 2]
│   │   └── verified.md.j2                 [NEW, Phase 2]
│   ├── artifacts/
│   │   └── manifest.yaml                  [MODIFIED, Phase 1: rename phases]
│   ├── commands/
│   │   ├── pm-session-monitor.md          [NEW, Phase 4]
│   │   ├── pm-session-review.md           [NEW, Phase 5]
│   │   ├── pm-session-complete.md         [NEW, Phase 6]
│   │   └── pm-issue-artifact.md           [NEW, Phase 2]
│   └── project/
│       └── .github/workflows/
│           └── tripwire.yml.j2            [NEW, Phase 8]
├── models/
│   ├── manifest.py                        [MODIFIED, Phase 0: Literal → str]
│   ├── issue_artifacts.py                 [NEW, Phase 2]
│   ├── insights.py                        [NEW, Phase 2]
│   ├── session.py                         [MODIFIED, Phase 3: spawn_config]
│   └── project.py                         [MODIFIED, Phase 0+2+3: override fields]
├── core/
│   ├── branch_naming.py                   [MODIFIED, Phase 0: load from YAML]
│   ├── enum_loader.py                     [MODIFIED, Phase 0: support new enums]
│   ├── spawn_config.py                    [NEW, Phase 3]
│   ├── stream_json.py                     [NEW, Phase 4]
│   ├── session_monitor.py                 [NEW, Phase 4]
│   ├── session_review.py                  [NEW, Phase 5]
│   ├── session_complete.py                [NEW, Phase 6]
│   ├── issue_artifact_store.py            [NEW, Phase 2]
│   ├── insights_store.py                  [NEW, Phase 2]
│   └── validator.py                       [MODIFIED, Phase 1 coherence; Phase 2 artifacts]
├── cli/
│   ├── session.py                         [MODIFIED, all phases: monitor/review/complete/spawn refactor]
│   ├── issue.py                           [NEW, Phase 2: issue artifact commands]
│   ├── ci.py                              [NEW, Phase 8]
│   ├── init.py                            [MODIFIED, Phase 8: create .github/workflows/]
│   └── main.py                            [MODIFIED, register new command groups]

.github/workflows/
├── ci.yml                                 [NEW, Phase 7]
└── publish.yml                            [NEW, Phase 8]
```

---

# Phase 0 — Configurability pass

**Goal:** Externalize hardcoded domain concepts to YAML, unblocking downstream phases.

## Task 0.1: Ship `artifact_phase.yaml`

**Files:**
- Create: `src/tripwire/templates/enums/artifact_phase.yaml`

- [ ] **Step 1: Write the YAML file**

```yaml
name: ArtifactPhase
description: Stages at which artifacts are produced
values:
  - id: planning
    label: Planning
    description: PM scoping and plan writing
  - id: in_progress
    label: In progress
    description: Execution agent implementing
  - id: in_review
    label: In review
    description: PM reviewing PR
  - id: verified
    label: Verified
    description: QA agent verifying tests + acceptance criteria
  - id: done
    label: Done
    description: Complete and merged
```

- [ ] **Step 2: Commit**

```bash
git add src/tripwire/templates/enums/artifact_phase.yaml
git commit -m "phase 0: ship artifact_phase.yaml with verified stage"
```

## Task 0.2: Ship `agent_type.yaml`

**Files:**
- Create: `src/tripwire/templates/enums/agent_type.yaml`

- [ ] **Step 1: Write the YAML**

```yaml
name: AgentType
description: Agent roles that produce or own artifacts
values:
  - id: pm
    label: PM agent
    description: Project manager — scopes, reviews, completes sessions
  - id: execution-agent
    label: Execution agent
    description: Implements issues; writes developer.md
  - id: verification-agent
    label: Verification agent
    description: Verifies acceptance criteria; writes verified.md
  - id: human
    label: Human
    description: Direct human author (used for retroactive attribution)
```

- [ ] **Step 2: Commit**

```bash
git add src/tripwire/templates/enums/agent_type.yaml
git commit -m "phase 0: ship agent_type.yaml"
```

## Task 0.3: Ship `branch_type.yaml`

**Files:**
- Create: `src/tripwire/templates/enums/branch_type.yaml`

- [ ] **Step 1: Write the YAML**

```yaml
name: BranchType
description: Allowed branch type prefixes (conventional commits style)
values:
  - id: feat
    label: Feature
    description: New user-facing capability
  - id: fix
    label: Fix
    description: Bug fix
  - id: refactor
    label: Refactor
    description: Non-functional code changes
  - id: docs
    label: Docs
    description: Documentation only
  - id: chore
    label: Chore
    description: Tooling / maintenance
  - id: test
    label: Test
    description: Test-only changes
```

- [ ] **Step 2: Commit**

```bash
git add src/tripwire/templates/enums/branch_type.yaml
git commit -m "phase 0: ship branch_type.yaml"
```

## Task 0.4: Refactor `models/manifest.py` — ArtifactPhase + AgentType

Switch from Python `Literal` to `str` with loader-time validation.

**Files:**
- Modify: `src/tripwire/models/manifest.py`
- Test: `tests/unit/test_manifest_model.py` (may need adjustment)

- [ ] **Step 1: Read current definitions**

```bash
grep -n "ArtifactPhase\|AgentType" src/tripwire/models/manifest.py | head -10
```

Expected: `AgentType` and `ArtifactPhase` are Python `Literal[...]` types on lines 15-16ish.

- [ ] **Step 2: Write failing test for YAML-loaded validation**

Add to `tests/unit/test_manifest_model.py`:

```python
def test_artifact_entry_accepts_unknown_phase_at_model_level(tmp_path):
    """Model accepts any str for produced_at; loader validates against YAML enum."""
    from tripwire.models.manifest import ArtifactEntry

    # This used to raise because Literal; after refactor it shouldn't.
    entry = ArtifactEntry(
        name="test",
        file="test.md",
        template="test.md.j2",
        produced_at="some_custom_phase",   # not in tripwire default set
        produced_by="pm",
        required=True,
    )
    assert entry.produced_at == "some_custom_phase"


def test_artifact_entry_validation_happens_in_loader(tmp_path_project):
    """Loading a manifest with an unknown phase raises at load time."""
    from tripwire.core.enum_loader import load_enum

    # With a project override that redefines artifact_phase, validation uses that override.
    (tmp_path_project / "enums").mkdir(exist_ok=True)
    (tmp_path_project / "enums" / "artifact_phase.yaml").write_text(
        "name: ArtifactPhase\nvalues:\n  - id: only_this_phase\n"
    )
    loaded = load_enum(tmp_path_project, "artifact_phase")
    assert loaded == ["only_this_phase"]
```

- [ ] **Step 3: Run test — expect FAIL (imports / functions don't exist yet)**

```bash
uv run pytest tests/unit/test_manifest_model.py::test_artifact_entry_accepts_unknown_phase_at_model_level -v
```

Expected: ValidationError from Pydantic because `produced_at` is currently a Literal.

- [ ] **Step 4: Refactor the model**

Open `src/tripwire/models/manifest.py`. Change:

```python
# BEFORE
from typing import Literal
AgentType = Literal["pm", "execution-agent", "verification-agent"]
ArtifactPhase = Literal["planning", "implementing", "verifying", "completion"]

class ArtifactEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    file: str
    template: str
    produced_at: ArtifactPhase
    produced_by: AgentType
    owned_by: AgentType | None = None
    required: bool = True
    approval_gate: bool = False
```

After:

```python
# AFTER — string types, validated by loader, not by Pydantic
class ArtifactEntry(BaseModel):
    """Artifact manifest entry.

    `produced_at` and `produced_by` / `owned_by` are validated against
    the project's active artifact_phase.yaml and agent_type.yaml enums
    at manifest-load time, not at model-validation time.
    """

    model_config = ConfigDict(extra="forbid")
    name: str
    file: str
    template: str
    produced_at: str   # validated against artifact_phase enum
    produced_by: str   # validated against agent_type enum
    owned_by: str | None = None
    required: bool = True
    approval_gate: bool = False
```

Remove the `AgentType` and `ArtifactPhase` Literal aliases entirely from the file. If anything still imports them, we'll fix in the next step.

- [ ] **Step 5: Find references to the removed literals**

```bash
grep -rn "AgentType\|ArtifactPhase" src/tripwire/ tests/ 2>/dev/null | grep -v "\.pyc"
```

For each match:
- If it was just `from tripwire.models.manifest import AgentType` etc — delete the import.
- If it was used as a type hint — replace with `str`.
- If it was used in a test assertion — revise the test (types are strings now).

- [ ] **Step 6: Extend `core/enum_loader.py` if needed**

Check whether `enum_loader.py` already supports loading `artifact_phase`, `agent_type`, `branch_type`:

```bash
grep -n "load_enum\|_enum_file" src/tripwire/core/enum_loader.py | head
```

The loader already supports arbitrary enum names by looking up `<project>/enums/<name>.yaml` or falling back to `src/tripwire/templates/enums/<name>.yaml`. No change needed unless there's specific name allowlisting.

- [ ] **Step 7: Add manifest-loader validation**

In whichever module loads `templates/artifacts/manifest.yaml` (check `_load_manifest_for_check` references), add validation:

```python
# In src/tripwire/core/session_readiness.py or wherever ArtifactManifest is loaded:
from tripwire.core.enum_loader import load_enum

def load_artifact_manifest(project_dir: Path) -> ArtifactManifest:
    manifest_path = project_dir / "templates" / "artifacts" / "manifest.yaml"
    data = yaml.safe_load(manifest_path.read_text())
    manifest = ArtifactManifest.model_validate(data)

    # Validate produced_at and produced_by / owned_by against active enums.
    allowed_phases = set(load_enum(project_dir, "artifact_phase"))
    allowed_agents = set(load_enum(project_dir, "agent_type"))

    for entry in manifest.artifacts:
        if entry.produced_at not in allowed_phases:
            raise ValueError(
                f"Manifest entry {entry.name!r} has produced_at={entry.produced_at!r} "
                f"not in artifact_phase enum: {sorted(allowed_phases)}"
            )
        if entry.produced_by not in allowed_agents:
            raise ValueError(f"Manifest entry {entry.name!r} produced_by unknown: {entry.produced_by!r}")
        if entry.owned_by and entry.owned_by not in allowed_agents:
            raise ValueError(f"Manifest entry {entry.name!r} owned_by unknown: {entry.owned_by!r}")

    return manifest
```

Find every existing call site of `ArtifactManifest.model_validate(...)` and route through this new loader.

- [ ] **Step 8: Run tests**

```bash
uv run pytest tests/unit/test_manifest_model.py -v
uv run pytest tests/ -q 2>&1 | tail -5
```

Expected: new tests pass; existing tests pass (Phase 1 will update fixtures that reference old phase values).

- [ ] **Step 9: Commit**

```bash
git add src/tripwire/models/manifest.py src/tripwire/core/ tests/unit/test_manifest_model.py
git commit -m "phase 0: externalize ArtifactPhase + AgentType to YAML-loaded enums"
```

## Task 0.5: Refactor `branch_naming.py` — load branch types from YAML

**Files:**
- Modify: `src/tripwire/core/branch_naming.py`
- Test: `tests/unit/test_branch_naming.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_branch_naming.py`:

```python
def test_branch_types_loaded_from_project_override(tmp_path_project):
    """Project can override allowed branch types via enums/branch_type.yaml."""
    from tripwire.core.branch_naming import is_valid_branch_name

    # Default: feat/, fix/, etc. pass
    assert is_valid_branch_name("feat/api", project_dir=tmp_path_project)
    assert not is_valid_branch_name("wip/api", project_dir=tmp_path_project)

    # Override to add `wip`
    (tmp_path_project / "enums").mkdir(exist_ok=True)
    (tmp_path_project / "enums" / "branch_type.yaml").write_text(
        """name: BranchType
values:
  - id: feat
  - id: fix
  - id: wip
"""
    )
    assert is_valid_branch_name("wip/api", project_dir=tmp_path_project)
```

- [ ] **Step 2: Run test — expect FAIL (no project_dir parameter yet)**

```bash
uv run pytest tests/unit/test_branch_naming.py::test_branch_types_loaded_from_project_override -v
```

- [ ] **Step 3: Refactor the module**

Edit `src/tripwire/core/branch_naming.py`:

```python
# BEFORE (roughly)
ALLOWED_TYPES = ("feat", "fix", "refactor", "docs", "chore", "test")

def is_valid_branch_name(name: str) -> bool:
    ...
```

After:

```python
from pathlib import Path
from tripwire.core.enum_loader import load_enum

_DEFAULT_TYPES = ("feat", "fix", "refactor", "docs", "chore", "test")


def _allowed_types(project_dir: Path | None) -> tuple[str, ...]:
    """Load allowed branch types. Project override wins over tripwire default."""
    if project_dir is None:
        return _DEFAULT_TYPES
    try:
        loaded = load_enum(project_dir, "branch_type")
        return tuple(loaded) if loaded else _DEFAULT_TYPES
    except FileNotFoundError:
        return _DEFAULT_TYPES


def is_valid_branch_name(name: str, *, project_dir: Path | None = None) -> bool:
    if "/" not in name:
        return False
    branch_type, _, _ = name.partition("/")
    if branch_type not in _allowed_types(project_dir):
        return False
    # ... rest of the existing validation (slug length etc.)


def parse_branch_name(name: str, *, project_dir: Path | None = None) -> tuple[str, str]:
    # Same refactor: accept project_dir, use _allowed_types
    ...


def derive_branch_name(session_id: str, primary_issue_kind: str, *, project_dir: Path | None = None) -> str:
    if primary_issue_kind not in _allowed_types(project_dir):
        raise BranchNameError(f"Issue kind {primary_issue_kind!r} not in allowed branch types")
    ...


ALLOWED_TYPES = _DEFAULT_TYPES  # kept for backward-compat of module imports; remove in v0.8
```

- [ ] **Step 4: Update callers**

```bash
grep -rn "is_valid_branch_name\|parse_branch_name\|derive_branch_name" src/tripwire/ tests/ 2>/dev/null | head -10
```

For each call site that has access to `project_dir`, update the call to pass it. Call sites without access pass `None` (uses defaults). Don't break any existing behavior — callers that didn't pass `project_dir` before continue to work as before.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/test_branch_naming.py tests/ -q 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add src/tripwire/core/branch_naming.py tests/unit/test_branch_naming.py src/tripwire/cli/
git commit -m "phase 0: load branch types from YAML with project override"
```

## Task 0.6: Add `project.yaml.artifact_manifest_overrides` + `issue_artifact_manifest_overrides` fields

**Files:**
- Modify: `src/tripwire/models/project.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_project_model.py`:

```python
def test_project_supports_artifact_overrides():
    from tripwire.models.project import ProjectConfig

    p = ProjectConfig(
        name="test",
        key_prefix="TST",
        artifact_manifest_overrides=[
            {
                "name": "extra-doc",
                "file": "extra.md",
                "template": "extra.md.j2",
                "produced_at": "in_progress",
                "produced_by": "execution-agent",
            }
        ],
    )
    assert len(p.artifact_manifest_overrides) == 1


def test_project_supports_issue_artifact_overrides():
    from tripwire.models.project import ProjectConfig

    p = ProjectConfig(
        name="test",
        key_prefix="TST",
        issue_artifact_manifest_overrides=[
            {
                "name": "extra-issue-doc",
                "file": "extra.md",
                "template": "extra.md.j2",
                "produced_by": "execution-agent",
                "required_at_status": "in_review",
            }
        ],
    )
    assert len(p.issue_artifact_manifest_overrides) == 1
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Add the fields**

In `src/tripwire/models/project.py`, add:

```python
from tripwire.models.manifest import ArtifactEntry

class ProjectConfig(BaseModel):
    # ... existing fields ...
    artifact_manifest_overrides: list[ArtifactEntry] = Field(default_factory=list)
    issue_artifact_manifest_overrides: list[dict] = Field(default_factory=list)
    # Note: issue_artifact_manifest_overrides uses list[dict] here; Phase 2 introduces
    # IssueArtifactEntry and tightens the type.
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/models/project.py tests/unit/test_project_model.py
git commit -m "phase 0: add artifact_manifest_overrides fields to ProjectConfig"
```

## Task 0.7: Project-level slash command overrides

**Files:**
- Modify: `src/tripwire/core/paths.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_paths.py
def test_project_command_path_falls_back_to_tripwire_default(tmp_path_project):
    from tripwire.core.paths import resolve_command_path, TRIPWIRE_COMMANDS_DIR

    # No project override: returns tripwire default path
    result = resolve_command_path(tmp_path_project, "pm-scope")
    assert str(result).endswith("templates/commands/pm-scope.md")


def test_project_command_path_prefers_project_override(tmp_path_project):
    from tripwire.core.paths import resolve_command_path

    override_dir = tmp_path_project / ".tripwire" / "commands"
    override_dir.mkdir(parents=True)
    (override_dir / "pm-scope.md").write_text("# custom")

    result = resolve_command_path(tmp_path_project, "pm-scope")
    assert result == override_dir / "pm-scope.md"
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

Add to `src/tripwire/core/paths.py`:

```python
TRIPWIRE_DIR = ".tripwire"
TRIPWIRE_COMMANDS_DIR = ".tripwire/commands"
TRIPWIRE_SPAWN_DIR = ".tripwire/spawn"


def tripwire_dir(project_dir: Path) -> Path:
    return project_dir / TRIPWIRE_DIR


def project_commands_dir(project_dir: Path) -> Path:
    return project_dir / TRIPWIRE_COMMANDS_DIR


def project_spawn_dir(project_dir: Path) -> Path:
    return project_dir / TRIPWIRE_SPAWN_DIR


def resolve_command_path(project_dir: Path, command_name: str) -> Path:
    """Resolve a slash command file, preferring project override."""
    override = project_commands_dir(project_dir) / f"{command_name}.md"
    if override.is_file():
        return override
    # Fall back to tripwire-shipped template
    import tripwire
    tripwire_root = Path(tripwire.__file__).parent
    return tripwire_root / "templates" / "commands" / f"{command_name}.md"
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/core/paths.py tests/unit/test_paths.py
git commit -m "phase 0: add resolve_command_path with project override"
```

## Task 0.8: Phase 0 verification

- [ ] **Step 1: Full test suite**

```bash
uv run pytest tests/ -q 2>&1 | tail -5
```

Expected: pass. Any lingering failures are from fixtures still using old `implementing` / `verifying` / `completion` phase names — those are addressed by Phase 1.

- [ ] **Step 2: Lint**

```bash
uv run ruff check && uv run ruff format --check
```

Fix as needed.

---

# Phase 1 — Vocabulary alignment + verified stage

**Goal:** Rename phase vocabulary (`implementing` → `in_progress`, `verifying` → `in_review`, `completion` → `done`), add `verified` stage, add Layer 2 + Layer 3 coherence checks. Clean cut — no aliases.

## Task 1.1: Update shipped `issue_status.yaml` to include `verified`

**Files:**
- Modify: `src/tripwire/templates/enums/issue_status.yaml`

- [ ] **Step 1: Add verified entry**

Open the file. Insert a `verified` entry between `in_review` and `done`:

```yaml
# After the `in_review` entry
  - id: verified
    label: Verified
    color: green
    description: QA verified (PM fills this role until a QA agent ships)
  - id: done
    # ... existing ...
```

- [ ] **Step 2: Add transition**

In `ProjectConfig.status_transitions` default (find where it's set, likely `src/tripwire/models/project.py` or a `_defaults.py`):

Make sure `in_review → verified` and `verified → done` are allowed:

```python
# default transitions
{
    "backlog": ["todo", "done"],
    "todo": ["in_progress", "done"],
    "in_progress": ["in_review", "todo"],
    "in_review": ["verified", "in_progress"],
    "verified": ["done", "in_review"],  # allow reopen
    "done": [],
}
```

- [ ] **Step 3: Commit**

```bash
git add src/tripwire/templates/enums/issue_status.yaml src/tripwire/models/project.py
git commit -m "phase 1: add verified stage to default IssueStatus + transitions"
```

## Task 1.2: Rename phases in `templates/artifacts/manifest.yaml`

**Files:**
- Modify: `src/tripwire/templates/artifacts/manifest.yaml`

- [ ] **Step 1: Replace values**

```bash
sed -i '' \
  -e 's/produced_at: implementing$/produced_at: in_progress/' \
  -e 's/produced_at: verifying$/produced_at: in_review/' \
  -e 's/produced_at: completion$/produced_at: done/' \
  src/tripwire/templates/artifacts/manifest.yaml
```

- [ ] **Step 2: Verify**

```bash
grep "produced_at" src/tripwire/templates/artifacts/manifest.yaml
```

Expected: only `planning`, `in_progress`, `in_review`, `done` values appear.

- [ ] **Step 3: Commit**

```bash
git add src/tripwire/templates/artifacts/manifest.yaml
git commit -m "phase 1: rename phase values in artifact manifest"
```

## Task 1.3: Rename phases in every Python reference

**Files:**
- Modify: `src/tripwire/core/validator.py` and any other `*.py` referencing the old literals
- Modify: test fixtures

- [ ] **Step 1: Find references**

```bash
grep -rn 'implementing\|verifying\|completion' src/tripwire/ tests/ 2>/dev/null | \
  grep -v "\.pyc" | \
  grep -v "# " | \
  head -40
```

Careful: some matches may be legitimate (e.g., CLI help text that talks about "the implementing phase" in prose). Review each match. For values in:
- String literals used as phase values (e.g., `produced_at: "implementing"`)
- Enum-matching logic (e.g., `if phase == "completion":`)
- Test expectations

...replace. For:
- Prose that happens to contain the word "implementing" as a verb
- Historical comments

...leave.

- [ ] **Step 2: Replace the value-form literals**

Use careful scoped sed on each identified file. Example for validator.py:

```bash
sed -i '' \
  -e 's/"implementing"/"in_progress"/g' \
  -e 's/"verifying"/"in_review"/g' \
  -e 's/"completion"/"done"/g' \
  -e "s/'implementing'/'in_progress'/g" \
  -e "s/'verifying'/'in_review'/g" \
  -e "s/'completion'/'done'/g" \
  src/tripwire/core/validator.py
```

Repeat for each file identified in Step 1.

- [ ] **Step 3: Test fixtures**

```bash
grep -rln '"implementing"\|"verifying"\|"completion"\|implementing$\|verifying$\|completion$' tests/ 2>/dev/null
```

For each:
- If it's a string literal in a fixture dict: replace.
- If it's a YAML fragment: replace the value only (not the key).

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/ -q 2>&1 | tail -10
```

Expected: most pass. Investigate each failure.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "phase 1: rename phase literals across source and fixtures"
```

## Task 1.4: Update `session_status.yaml` to include `verified`

**Files:**
- Modify: `src/tripwire/templates/enums/session_status.yaml`

- [ ] **Step 1: Edit**

Add `verified` between `in_review` and `done`:

```yaml
  - id: verified
    label: Verified
    color: green
    description: Session's PR verified
```

- [ ] **Step 2: Commit**

```bash
git add src/tripwire/templates/enums/session_status.yaml
git commit -m "phase 1: add verified to session_status enum"
```

## Task 1.5: Layer 2 coherence test

**Files:**
- Create: `tests/unit/test_phase_status_coherence.py`

- [ ] **Step 1: Write test**

```python
"""Layer 2 coherence: artifact phases must align with issue statuses."""

from pathlib import Path

import yaml


SESSION_ONLY_PHASES = frozenset({"planning"})


def _load_enum_values(name: str) -> set[str]:
    import tripwire
    root = Path(tripwire.__file__).parent
    data = yaml.safe_load((root / "templates" / "enums" / f"{name}.yaml").read_text())
    return {entry["id"] for entry in data["values"]}


def test_artifact_phases_align_with_issue_status():
    phases = _load_enum_values("artifact_phase")
    statuses = _load_enum_values("issue_status")

    overlap_required = phases - SESSION_ONLY_PHASES
    missing = overlap_required - statuses
    assert not missing, (
        f"ArtifactPhase values {sorted(missing)} don't match IssueStatus. "
        f"Either rename them, add to SESSION_ONLY_PHASES, or add to issue_status.yaml."
    )
```

- [ ] **Step 2: Run test — expect PASS**

```bash
uv run pytest tests/unit/test_phase_status_coherence.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_phase_status_coherence.py
git commit -m "phase 1: Layer 2 coherence test — ArtifactPhase ⊆ IssueStatus"
```

## Task 1.6: Layer 3 coherence validator

**Files:**
- Modify: `src/tripwire/core/validator.py`
- Test: `tests/unit/test_validator_coherence.py`

- [ ] **Step 1: Write failing test**

```python
"""Layer 3 coherence validator — session status vs issue statuses."""

import pytest
from click.testing import CliRunner


def test_coherence_lags_warning(tmp_path_project, save_test_session, save_test_issue):
    """Session in_review but issue in_progress → warning, not error."""
    save_test_issue(tmp_path_project, "TST-1", status="in_progress")
    save_test_session(tmp_path_project, "s1", status="in_review", issues=["TST-1"])

    from tripwire.cli.validate import validate_cmd
    runner = CliRunner()
    result = runner.invoke(validate_cmd, ["--project-dir", str(tmp_path_project), "--format=json"])
    import json
    report = json.loads(result.output)
    codes = [f["code"] for f in report.get("findings", [])]
    assert "coherence/issue_status_lags_session" in codes


def test_coherence_ahead_error(tmp_path_project, save_test_session, save_test_issue):
    """Session in_progress but issue done → error."""
    save_test_issue(tmp_path_project, "TST-1", status="done")
    save_test_session(tmp_path_project, "s1", status="in_progress", issues=["TST-1"])

    from tripwire.cli.validate import validate_cmd
    runner = CliRunner()
    result = runner.invoke(validate_cmd, ["--project-dir", str(tmp_path_project), "--format=json"])
    import json
    report = json.loads(result.output)
    errors = [f for f in report.get("findings", []) if f["severity"] == "error"]
    codes = [e["code"] for e in errors]
    assert "coherence/issue_status_ahead_of_session" in codes
```

- [ ] **Step 2: Run tests — FAIL**

- [ ] **Step 3: Implement coherence check in validator**

Add a new check function in `src/tripwire/core/validator.py`:

```python
COHERENCE_MATRIX: dict[str, dict[str, str]] = {
    # session_status: { issue_status: severity }
    # severity: "ok" | "lag_warn" | "ahead_error"
    "planning": {
        "backlog": "ok", "todo": "ok",
        "in_progress": "lag_warn", "in_review": "lag_warn",
        "verified": "lag_warn", "done": "lag_warn",
    },
    "in_progress": {
        "backlog": "ahead_error", "todo": "ok",
        "in_progress": "ok", "in_review": "ok",
        "verified": "lag_warn", "done": "lag_warn",
    },
    "in_review": {
        "backlog": "ahead_error", "todo": "ahead_error",
        "in_progress": "ahead_error",
        "in_review": "ok", "verified": "ok", "done": "ok",
    },
    "verified": {
        "backlog": "ahead_error", "todo": "ahead_error",
        "in_progress": "ahead_error", "in_review": "ahead_error",
        "verified": "ok", "done": "ok",
    },
    "done": {
        "backlog": "ahead_error", "todo": "ahead_error",
        "in_progress": "ahead_error", "in_review": "ahead_error",
        "verified": "ahead_error", "done": "ok",
    },
}


def check_session_issue_coherence(ctx: ValidationContext) -> list[CheckResult]:
    """Layer 3: session status vs issue statuses must be coherent."""
    results: list[CheckResult] = []
    for session in ctx.sessions:
        session_row = COHERENCE_MATRIX.get(session.status, {})
        for issue_key in session.issues:
            issue = ctx.issues_by_key.get(issue_key)
            if issue is None:
                continue
            verdict = session_row.get(issue.status, "ok")
            if verdict == "ok":
                continue
            code = (
                "coherence/issue_status_ahead_of_session"
                if verdict == "ahead_error"
                else "coherence/issue_status_lags_session"
            )
            severity = Severity.ERROR if verdict == "ahead_error" else Severity.WARNING
            results.append(
                CheckResult(
                    code=code,
                    severity=severity,
                    file=f"sessions/{session.id}/session.yaml",
                    message=(
                        f"Session {session.id!r} ({session.status}) has issue "
                        f"{issue_key!r} at {issue.status!r} — {verdict.replace('_', ' ')}."
                    ),
                    hint=(
                        "Either advance the issue status or step the session back to a "
                        "phase that matches."
                    ),
                )
            )
    return results
```

Register the check in the validator's check registry (find where other checks are registered).

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/core/validator.py tests/unit/test_validator_coherence.py
git commit -m "phase 1: Layer 3 coherence validator (session status vs issue statuses)"
```

## Task 1.7: Migrate test project session YAMLs

**Files:** outside the repo, in 3 test projects.

- [ ] **Step 1: Apply status rename in each test project**

```bash
for proj in /Users/maia/Code/seido/projects/kb-pivot \
            /Users/maia/Code/seido/projects/project-graph-ui-v2 \
            /Users/maia/Code/seido/projects/project-keel-ui-init ; do
  find "$proj/sessions" -name "session.yaml" -exec sed -i '' \
    -e 's/^status: implementing$/status: in_progress/' \
    -e 's/^status: verifying$/status: in_review/' \
    -e 's/^status: completion$/status: done/' \
    -e 's/^current_state: implementing$/current_state: in_progress/' \
    -e 's/^current_state: verifying$/current_state: in_review/' \
    -e 's/^current_state: completion$/current_state: done/' \
    {} + 2>/dev/null
done
echo "done"
```

- [ ] **Step 2: Verify each project validates**

```bash
for proj in /Users/maia/Code/seido/projects/kb-pivot \
            /Users/maia/Code/seido/projects/project-graph-ui-v2 \
            /Users/maia/Code/seido/projects/project-keel-ui-init ; do
  echo "=== $proj ==="
  uv run tripwire validate --project-dir "$proj" 2>&1 | tail -3
done
```

- [ ] **Step 3: Do not commit test project changes here — each project has its own PR**

## Task 1.8: Phase 1 verification

```bash
uv run pytest tests/ -q 2>&1 | tail -5
uv run ruff check && uv run ruff format --check
```

Both clean.

---

# Phase 2 — Per-issue artifacts + insights capture

**Goal:** Enforce `developer.md` and `verified.md`. Capture agent-proposed concept-node insights.

## Task 2.1: Ship issue artifact manifest

**Files:**
- Create: `src/tripwire/templates/issue_artifacts/manifest.yaml`

- [ ] **Step 1: Write**

```yaml
artifacts:
  - name: developer
    file: developer.md
    template: developer.md.j2
    produced_by: execution-agent
    owned_by: execution-agent
    required: true
    required_at_status: in_review

  - name: verified
    file: verified.md
    template: verified.md.j2
    produced_by: verification-agent
    owned_by: verification-agent
    required: true
    required_at_status: verified
```

- [ ] **Step 2: Commit**

```bash
git add src/tripwire/templates/issue_artifacts/manifest.yaml
git commit -m "phase 2: ship issue artifact manifest"
```

## Task 2.2: Ship issue artifact templates

**Files:**
- Create: `src/tripwire/templates/issue_artifacts/developer.md.j2`
- Create: `src/tripwire/templates/issue_artifacts/verified.md.j2`

- [ ] **Step 1: developer.md.j2**

```markdown
# Developer notes — {{ issue.id }}

## What I built

{# Brief — 1-3 sentences on what changed and why. #}

## Key decisions

{# Non-obvious choices: library selection, architectural splits, patterns
   future agents should know about. #}

## Files touched

{# Bulleted list. The PR diff captures what; this captures why. #}

## Tests added

{# What scenarios covered, what you deliberately didn't cover. #}

## Stop-and-ask points triggered

{# Did any execution constraints fire? If yes, what did you do? If no, "none". #}

## Followups

{# Things noticed but not fixed in this issue. Each should become a new issue
   or a comment on an existing one — don't leave them buried here. #}
```

- [ ] **Step 2: verified.md.j2**

```markdown
# Verification notes — {{ issue.id }}

**Verified by**: {# pm-agent | verification-agent | human #}
**Verified at**: {# date #}
**Verdict**: {# approved | approved-with-followups | rejected #}

## Acceptance criteria

{% for criterion in issue.acceptance_criteria -%}
- [ ] {{ criterion }} — {# evidence: file:line, test name, or "manual smoke" #}
{% endfor %}

## Deviations found

{# Files touched outside scope, dependencies added beyond spec, layout changes. #}

## Follow-up issues created

{# Bulleted list of new issue keys created from verification findings. #}
```

- [ ] **Step 3: Commit**

```bash
git add src/tripwire/templates/issue_artifacts/
git commit -m "phase 2: ship issue artifact templates (developer, verified)"
```

## Task 2.3: IssueArtifactEntry + IssueArtifactManifest models

**Files:**
- Create: `src/tripwire/models/issue_artifacts.py`
- Test: `tests/unit/test_issue_artifact_model.py`

- [ ] **Step 1: Write failing test**

```python
"""IssueArtifactEntry + IssueArtifactManifest models."""
import pytest
from pydantic import ValidationError


def test_issue_artifact_entry_minimal():
    from tripwire.models.issue_artifacts import IssueArtifactEntry

    entry = IssueArtifactEntry(
        name="developer",
        file="developer.md",
        template="developer.md.j2",
        produced_by="execution-agent",
        required_at_status="in_review",
    )
    assert entry.owned_by == "execution-agent"  # defaults from produced_by
    assert entry.required is True


def test_issue_artifact_manifest_loads():
    from tripwire.models.issue_artifacts import IssueArtifactManifest

    manifest = IssueArtifactManifest(
        artifacts=[
            {
                "name": "developer",
                "file": "developer.md",
                "template": "developer.md.j2",
                "produced_by": "execution-agent",
                "required_at_status": "in_review",
            }
        ]
    )
    assert len(manifest.artifacts) == 1


def test_issue_artifact_entry_rejects_unknown_field():
    from tripwire.models.issue_artifacts import IssueArtifactEntry

    with pytest.raises(ValidationError):
        IssueArtifactEntry(
            name="x", file="x.md", template="x.md.j2",
            produced_by="execution-agent", required_at_status="in_review",
            bogus="nope",
        )
```

- [ ] **Step 2: Run — FAIL (module doesn't exist)**

- [ ] **Step 3: Create module**

`src/tripwire/models/issue_artifacts.py`:

```python
"""Per-issue artifact manifest models."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IssueArtifactEntry(BaseModel):
    """One entry in the issue-artifact manifest."""

    model_config = ConfigDict(extra="forbid")

    name: str
    file: str
    template: str
    produced_by: str              # validated against agent_type enum at load time
    owned_by: str | None = None
    required: bool = True
    required_at_status: str       # validated against issue_status enum at load time

    @model_validator(mode="after")
    def _default_owned_by(self) -> IssueArtifactEntry:
        if self.owned_by is None:
            object.__setattr__(self, "owned_by", self.produced_by)
        return self


class IssueArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifacts: list[IssueArtifactEntry] = Field(default_factory=list)
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/models/issue_artifacts.py tests/unit/test_issue_artifact_model.py
git commit -m "phase 2: IssueArtifactEntry + IssueArtifactManifest models"
```

## Task 2.4: Issue artifact store + loader

**Files:**
- Create: `src/tripwire/core/issue_artifact_store.py`

- [ ] **Step 1: Write failing test**

```python
"""Issue artifact store: load manifest, merge overrides, status ordering."""


def test_load_default_manifest(tmp_path_project):
    from tripwire.core.issue_artifact_store import load_issue_artifact_manifest

    manifest = load_issue_artifact_manifest(tmp_path_project)
    names = {e.name for e in manifest.artifacts}
    assert names == {"developer", "verified"}


def test_status_at_or_past():
    from tripwire.core.issue_artifact_store import status_at_or_past

    # Default order: backlog < todo < in_progress < in_review < verified < done
    assert status_at_or_past("in_review", "in_review") is True
    assert status_at_or_past("verified", "in_review") is True
    assert status_at_or_past("in_progress", "in_review") is False
    assert status_at_or_past("done", "verified") is True


def test_project_override_appends(tmp_path_project):
    from tripwire.core.issue_artifact_store import load_issue_artifact_manifest
    # Configure project.yaml with an override
    import yaml as _yaml
    p = tmp_path_project / "project.yaml"
    data = _yaml.safe_load(p.read_text())
    data["issue_artifact_manifest_overrides"] = [
        {
            "name": "custom-audit",
            "file": "custom-audit.md",
            "template": "custom-audit.md.j2",
            "produced_by": "execution-agent",
            "required_at_status": "done",
        }
    ]
    p.write_text(_yaml.safe_dump(data))
    manifest = load_issue_artifact_manifest(tmp_path_project)
    assert any(e.name == "custom-audit" for e in manifest.artifacts)
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

`src/tripwire/core/issue_artifact_store.py`:

```python
"""Load issue artifact manifest, merge project overrides, status ordering."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from tripwire.core.enum_loader import load_enum
from tripwire.core.store import load_project
from tripwire.models.issue_artifacts import IssueArtifactEntry, IssueArtifactManifest


def _shipped_manifest_path() -> Path:
    import tripwire
    return Path(tripwire.__file__).parent / "templates" / "issue_artifacts" / "manifest.yaml"


def load_issue_artifact_manifest(project_dir: Path) -> IssueArtifactManifest:
    """Load the shipped manifest, apply project overrides, validate against enums."""
    shipped_data = yaml.safe_load(_shipped_manifest_path().read_text(encoding="utf-8"))
    artifacts: dict[str, dict] = {a["name"]: a for a in shipped_data.get("artifacts", [])}

    try:
        project = load_project(project_dir)
        for override in (project.issue_artifact_manifest_overrides or []):
            artifacts[override["name"]] = override
    except Exception:
        pass

    entries = [IssueArtifactEntry.model_validate(a) for a in artifacts.values()]

    # Validate enum membership
    allowed_statuses = set(load_enum(project_dir, "issue_status"))
    allowed_agents = set(load_enum(project_dir, "agent_type"))

    for entry in entries:
        if entry.required_at_status not in allowed_statuses:
            raise ValueError(
                f"Issue artifact {entry.name!r} has required_at_status="
                f"{entry.required_at_status!r} not in issue_status enum"
            )
        if entry.produced_by not in allowed_agents:
            raise ValueError(
                f"Issue artifact {entry.name!r} produced_by={entry.produced_by!r} "
                f"not in agent_type enum"
            )

    return IssueArtifactManifest(artifacts=entries)


def _status_ordering(project_dir: Path) -> list[str]:
    """Return IssueStatus in canonical order (reads enum file's declaration order)."""
    return load_enum(project_dir, "issue_status")


def status_at_or_past(current: str, threshold: str, project_dir: Path | None = None) -> bool:
    """Is `current` >= `threshold` in the enum's declared order?"""
    if project_dir is None:
        # Use tripwire default ordering
        default_order = ["backlog", "todo", "in_progress", "in_review", "verified", "done"]
        order = default_order
    else:
        order = _status_ordering(project_dir)
    try:
        return order.index(current) >= order.index(threshold)
    except ValueError:
        return False
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/core/issue_artifact_store.py tests/unit/test_issue_artifact_store.py
git commit -m "phase 2: issue_artifact_store with manifest loader + status ordering"
```

## Task 2.5: Validator — `check_issue_artifact_presence`

**Files:**
- Modify: `src/tripwire/core/validator.py`
- Test: `tests/unit/test_validator_issue_artifacts.py`

- [ ] **Step 1: Failing test**

```python
def test_issue_at_in_review_missing_developer_errors(
    tmp_path_project, save_test_issue
):
    save_test_issue(tmp_path_project, "TST-1", status="in_review")
    # No developer.md

    from tripwire.cli.validate import validate_cmd
    from click.testing import CliRunner
    import json
    runner = CliRunner()
    result = runner.invoke(validate_cmd, ["--project-dir", str(tmp_path_project), "--format=json"])
    report = json.loads(result.output)
    codes = [f["code"] for f in report.get("findings", [])]
    assert "issue_artifact/missing" in codes


def test_issue_at_done_missing_verified_errors(
    tmp_path_project, save_test_issue
):
    # Create developer.md so we only flag verified
    save_test_issue(tmp_path_project, "TST-1", status="done")
    (tmp_path_project / "issues" / "TST-1" / "developer.md").write_text("# done\n")

    from tripwire.cli.validate import validate_cmd
    from click.testing import CliRunner
    import json
    runner = CliRunner()
    result = runner.invoke(validate_cmd, ["--project-dir", str(tmp_path_project), "--format=json"])
    report = json.loads(result.output)
    findings = [f for f in report.get("findings", []) if f["code"] == "issue_artifact/missing"]
    assert any("verified.md" in f["message"] for f in findings)


def test_issue_at_todo_no_artifacts_required(tmp_path_project, save_test_issue):
    save_test_issue(tmp_path_project, "TST-1", status="todo")
    from tripwire.cli.validate import validate_cmd
    from click.testing import CliRunner
    import json
    runner = CliRunner()
    result = runner.invoke(validate_cmd, ["--project-dir", str(tmp_path_project), "--format=json"])
    report = json.loads(result.output)
    codes = [f["code"] for f in report.get("findings", [])]
    assert "issue_artifact/missing" not in codes
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Add check**

Add to `src/tripwire/core/validator.py`:

```python
def check_issue_artifact_presence(ctx: ValidationContext) -> list[CheckResult]:
    """Every issue at status ≥ required_at_status must have the file."""
    from tripwire.core.issue_artifact_store import (
        load_issue_artifact_manifest,
        status_at_or_past,
    )
    from tripwire.core import paths

    results: list[CheckResult] = []
    try:
        manifest = load_issue_artifact_manifest(ctx.project_dir)
    except Exception as e:
        results.append(
            CheckResult(
                code="issue_artifact_manifest/invalid",
                severity=Severity.ERROR,
                file="templates/issue_artifacts/manifest.yaml",
                message=f"Failed to load issue artifact manifest: {e}",
            )
        )
        return results

    for issue in ctx.issues:
        for entry in manifest.artifacts:
            if not entry.required:
                continue
            if not status_at_or_past(issue.status, entry.required_at_status, ctx.project_dir):
                continue
            file_path = paths.issue_dir(ctx.project_dir, issue.id) / entry.file
            if not file_path.is_file():
                results.append(
                    CheckResult(
                        code="issue_artifact/missing",
                        severity=Severity.ERROR,
                        file=f"issues/{issue.id}/{entry.file}",
                        message=(
                            f"Issue {issue.id!r} is at status {issue.status!r} "
                            f"and must have {entry.file!r}."
                        ),
                        hint=(
                            f"Run `tripwire issue artifact init {issue.id} "
                            f"{entry.name}`."
                        ),
                    )
                )
    return results
```

Register the check.

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/core/validator.py tests/unit/test_validator_issue_artifacts.py
git commit -m "phase 2: check_issue_artifact_presence validator"
```

## Task 2.6: Status transition guards

**Files:**
- Modify: `src/tripwire/core/validator.py` (add transition check)

- [ ] **Step 1: Failing test**

```python
def test_transition_in_progress_to_in_review_blocked_without_developer(
    tmp_path_project, save_test_issue
):
    """Attempt to set status in_review without developer.md should be flagged
    by validator when transitions are tracked."""
    # For v0.7, the transition guard is an error issued at the moment of
    # in-review status if developer.md is missing — it's actually subsumed by
    # check_issue_artifact_presence. Verify by setting status=in_review without
    # artifact and confirming error.
    save_test_issue(tmp_path_project, "TST-1", status="in_review")

    from tripwire.cli.validate import validate_cmd
    from click.testing import CliRunner
    import json
    runner = CliRunner()
    result = runner.invoke(validate_cmd, ["--project-dir", str(tmp_path_project), "--format=json"])
    report = json.loads(result.output)
    codes = [f["code"] for f in report.get("findings", [])]
    assert "issue_artifact/missing" in codes
```

In v0.7, the transition guard IS the artifact presence check (§7.4 of spec: "in_progress → in_review blocked without developer.md" == "status in_review errors if developer.md missing"). The check we added in Task 2.5 covers this. No new code needed.

- [ ] **Step 2: Run — PASS (Task 2.5 covers it)**

- [ ] **Step 3: Note in commit**

```bash
git commit --allow-empty -m "phase 2: transition guards subsumed by check_issue_artifact_presence"
```

## Task 2.7: CLI — `tripwire issue` group

**Files:**
- Create: `src/tripwire/cli/issue.py`
- Modify: `src/tripwire/cli/main.py` (register group)

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_issue_cli.py
from click.testing import CliRunner


def test_issue_artifact_list_shows_missing(tmp_path_project, save_test_issue):
    save_test_issue(tmp_path_project, "TST-1", status="in_review")

    from tripwire.cli.issue import issue_cmd
    runner = CliRunner()
    result = runner.invoke(issue_cmd, ["artifact", "list", "TST-1",
                                        "--project-dir", str(tmp_path_project)])
    assert result.exit_code == 0
    assert "developer.md" in result.output
    assert "MISSING" in result.output


def test_issue_artifact_init_writes_file(tmp_path_project, save_test_issue):
    save_test_issue(tmp_path_project, "TST-1", status="in_review")

    from tripwire.cli.issue import issue_cmd
    runner = CliRunner()
    result = runner.invoke(issue_cmd, ["artifact", "init", "TST-1", "developer",
                                        "--project-dir", str(tmp_path_project)])
    assert result.exit_code == 0, result.output
    assert (tmp_path_project / "issues" / "TST-1" / "developer.md").is_file()


def test_issue_artifact_init_refuses_overwrite(tmp_path_project, save_test_issue):
    save_test_issue(tmp_path_project, "TST-1", status="in_review")
    (tmp_path_project / "issues" / "TST-1" / "developer.md").write_text("# existing")

    from tripwire.cli.issue import issue_cmd
    runner = CliRunner()
    result = runner.invoke(issue_cmd, ["artifact", "init", "TST-1", "developer",
                                        "--project-dir", str(tmp_path_project)])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement CLI**

`src/tripwire/cli/issue.py`:

```python
"""`tripwire issue` — per-issue operations."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import click
from jinja2 import Environment, FileSystemLoader
from rich.console import Console
from rich.table import Table

from tripwire.cli._utils import require_project as _require_project
from tripwire.core import paths
from tripwire.core.issue_artifact_store import load_issue_artifact_manifest
from tripwire.core.store import load_issue

console = Console()


@click.group(name="issue")
def issue_cmd() -> None:
    """Per-issue operations (artifact + insights subgroups)."""


@issue_cmd.group(name="artifact")
def issue_artifact_cmd() -> None:
    """Issue artifact operations (developer.md, verified.md)."""


@issue_artifact_cmd.command("list")
@click.argument("issue_key")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]),
              default="text")
def issue_artifact_list_cmd(issue_key: str, project_dir: Path, output_format: str) -> None:
    """List expected artifacts for an issue and their presence state."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        issue = load_issue(resolved, issue_key)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    manifest = load_issue_artifact_manifest(resolved)

    rows = []
    for entry in manifest.artifacts:
        file_path = paths.issue_dir(resolved, issue_key) / entry.file
        rows.append({
            "name": entry.name,
            "file": entry.file,
            "required": entry.required,
            "required_at_status": entry.required_at_status,
            "produced_by": entry.produced_by,
            "present": file_path.is_file(),
            "issue_status": issue.status,
        })

    if output_format == "json":
        click.echo(json.dumps(rows, indent=2))
        return

    table = Table(title=f"Issue {issue_key} artifacts")
    table.add_column("name")
    table.add_column("file")
    table.add_column("required_at")
    table.add_column("produced_by")
    table.add_column("state")
    for row in rows:
        state = "✓ present" if row["present"] else "MISSING"
        table.add_row(row["name"], row["file"], row["required_at_status"],
                      row["produced_by"], state)
    console.print(table)


@issue_artifact_cmd.command("init")
@click.argument("issue_key")
@click.argument("artifact_name")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option("--force", is_flag=True, default=False,
              help="Overwrite existing artifact")
@click.option("--produced-by", default=None,
              help="Override the produced_by attribution (defaults to manifest)")
def issue_artifact_init_cmd(
    issue_key: str, artifact_name: str, project_dir: Path, force: bool,
    produced_by: str | None,
) -> None:
    """Render the artifact template into the issue directory."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        issue = load_issue(resolved, issue_key)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    manifest = load_issue_artifact_manifest(resolved)
    entry = next((e for e in manifest.artifacts if e.name == artifact_name), None)
    if entry is None:
        raise click.ClickException(
            f"Unknown artifact {artifact_name!r}. Available: "
            f"{', '.join(e.name for e in manifest.artifacts)}"
        )

    target = paths.issue_dir(resolved, issue_key) / entry.file
    if target.is_file() and not force:
        raise click.ClickException(
            f"{target} already exists. Use --force to overwrite."
        )

    # Render template
    import tripwire
    template_root = Path(tripwire.__file__).parent / "templates" / "issue_artifacts"
    env = Environment(loader=FileSystemLoader(str(template_root)), keep_trailing_newline=True)
    template = env.get_template(entry.template)
    rendered = template.render(
        issue=issue,
        project_dir=resolved,
        produced_by=produced_by or entry.produced_by,
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    click.echo(f"Wrote {target.relative_to(resolved)}")


@issue_artifact_cmd.command("verify")
@click.argument("issue_key")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
def issue_artifact_verify_cmd(issue_key: str, project_dir: Path) -> None:
    """Run artifact-presence check for a single issue."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        issue = load_issue(resolved, issue_key)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    from tripwire.core.issue_artifact_store import status_at_or_past
    manifest = load_issue_artifact_manifest(resolved)

    missing: list[str] = []
    for entry in manifest.artifacts:
        if not entry.required:
            continue
        if not status_at_or_past(issue.status, entry.required_at_status, resolved):
            continue
        file_path = paths.issue_dir(resolved, issue_key) / entry.file
        if not file_path.is_file():
            missing.append(entry.file)

    if missing:
        for f in missing:
            click.echo(f"MISSING: {f}")
        raise click.exceptions.Exit(1)
    click.echo("All required artifacts present.")
```

Register in `src/tripwire/cli/main.py`:

```python
from tripwire.cli.issue import issue_cmd
cli.add_command(issue_cmd)
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/cli/issue.py src/tripwire/cli/main.py tests/unit/test_issue_cli.py
git commit -m "phase 2: tripwire issue artifact CLI (list/init/verify)"
```

## Task 2.8: Slash command `/pm-issue-artifact`

**Files:**
- Create: `src/tripwire/templates/commands/pm-issue-artifact.md`

- [ ] **Step 1: Write**

```markdown
---
name: pm-issue-artifact
description: Create or update a per-issue artifact (developer.md, verified.md).
argument-hint: "<issue-key> <artifact-name>"
---

You are the project manager. Load the project-manager skill if not active.

$ARGUMENTS

Workflow:

1. Parse `<issue-key> <artifact-name>` from the arguments.
2. Run `tripwire issue artifact list <issue-key>` to see what's expected
   and what's present/missing.
3. If the requested artifact is already present:
   - For `verified.md` attributed to `pm-agent`: open it, read the existing
     verdict, and append a `## Re-review <date>` section with any new
     findings rather than overwriting.
   - For `developer.md`: this should only be written by the execution agent.
     Do not overwrite. Alert the user and suggest the execution agent write it.
   - For `verified.md` attributed to a non-PM agent: do not overwrite.
     Factor the existing content into any review output.
4. If the requested artifact is missing:
   - Run `tripwire issue artifact init <issue-key> <artifact-name> --produced-by pm-agent`.
   - Open the rendered template and fill in the sections based on:
     - The issue body (acceptance criteria, requirements)
     - The PR diff (for verified.md, check each criterion)
     - Your review judgment
5. Run `tripwire validate --strict`. Fix any errors.
6. Commit: `artifact: <artifact-name> for <issue-key>`.
```

- [ ] **Step 2: Commit**

```bash
git add src/tripwire/templates/commands/pm-issue-artifact.md
git commit -m "phase 2: /pm-issue-artifact slash command"
```

## Task 2.9: Insights — model + store

**Files:**
- Create: `src/tripwire/models/insights.py`
- Create: `src/tripwire/core/insights_store.py`
- Test: `tests/unit/test_insights.py`

- [ ] **Step 1: Failing test**

```python
def test_insights_file_roundtrip(tmp_path_project, save_test_session):
    from tripwire.models.insights import InsightsFile, NodeProposal
    from tripwire.core.insights_store import save_insights, load_insights

    save_test_session(tmp_path_project, "s1")
    sid = "s1"

    insights = InsightsFile(proposals=[
        NodeProposal(
            kind="new_node",
            id="pg-vacuum-tuning",
            name="PostgreSQL VACUUM tuning for high-write workloads",
            body="Tuning notes...",
            related=["database"],
            rationale="Operational tuning worth elevating.",
        ),
    ])
    save_insights(tmp_path_project, sid, insights)

    loaded = load_insights(tmp_path_project, sid)
    assert len(loaded.proposals) == 1
    assert loaded.proposals[0].id == "pg-vacuum-tuning"


def test_node_proposal_update_kind():
    from tripwire.models.insights import NodeProposal

    p = NodeProposal(
        kind="update_node",
        id="auth-system",
        delta="Added refresh token rotation on suspicious IP change.",
        rationale="Node description is stale w.r.t. security.",
    )
    assert p.kind == "update_node"
    assert p.delta is not None
    assert p.body is None
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

`src/tripwire/models/insights.py`:

```python
"""Agent-proposed concept node insights."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NodeProposal(BaseModel):
    """One proposed node addition or update."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["new_node", "update_node"]
    id: str
    name: str | None = None                  # for new_node; optional for update
    body: str | None = None                  # for new_node; full description
    delta: str | None = None                 # for update_node; described change
    related: list[str] = Field(default_factory=list)
    rationale: str

    @model_validator(mode="after")
    def _validate_fields_per_kind(self) -> NodeProposal:
        if self.kind == "new_node":
            if not self.body:
                raise ValueError("new_node proposals require `body`")
            if not self.name:
                raise ValueError("new_node proposals require `name`")
        elif self.kind == "update_node":
            if not self.delta:
                raise ValueError("update_node proposals require `delta`")
        return self


class InsightsFile(BaseModel):
    """Contents of sessions/<id>/insights.yaml."""

    model_config = ConfigDict(extra="forbid")
    proposals: list[NodeProposal] = Field(default_factory=list)
```

`src/tripwire/core/insights_store.py`:

```python
"""Read/write sessions/<id>/insights.yaml + insights.rejected.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

from tripwire.core import paths
from tripwire.models.insights import InsightsFile


def insights_path(project_dir: Path, session_id: str) -> Path:
    return paths.session_dir(project_dir, session_id) / "insights.yaml"


def rejected_path(project_dir: Path, session_id: str) -> Path:
    return paths.session_dir(project_dir, session_id) / "insights.rejected.yaml"


def load_insights(project_dir: Path, session_id: str) -> InsightsFile:
    p = insights_path(project_dir, session_id)
    if not p.is_file():
        return InsightsFile()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return InsightsFile.model_validate(data)


def save_insights(project_dir: Path, session_id: str, file: InsightsFile) -> None:
    p = insights_path(project_dir, session_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = file.model_dump(exclude_none=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def record_rejection(project_dir: Path, session_id: str, proposal_id: str, reason: str) -> None:
    p = rejected_path(project_dir, session_id)
    existing = {}
    if p.is_file():
        existing = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    entries = existing.get("rejected", [])
    entries.append({"id": proposal_id, "reason": reason})
    existing["rejected"] = entries
    p.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/models/insights.py src/tripwire/core/insights_store.py \
        tests/unit/test_insights.py
git commit -m "phase 2: insights model + store"
```

## Task 2.10: CLI — `tripwire session insights`

**Files:**
- Modify: `src/tripwire/cli/session.py`
- Test: `tests/unit/test_insights_cli.py`

- [ ] **Step 1: Failing test**

```python
def test_insights_list(tmp_path_project, save_test_session):
    save_test_session(tmp_path_project, "s1")
    from tripwire.models.insights import InsightsFile, NodeProposal
    from tripwire.core.insights_store import save_insights
    save_insights(tmp_path_project, "s1", InsightsFile(proposals=[
        NodeProposal(kind="new_node", id="x", name="X", body="desc.", rationale="r"),
    ]))

    from tripwire.cli.session import session_cmd
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(session_cmd, ["insights", "list", "s1",
                                          "--project-dir", str(tmp_path_project)])
    assert result.exit_code == 0
    assert "x" in result.output


def test_insights_apply_new_node(tmp_path_project, save_test_session):
    save_test_session(tmp_path_project, "s1")
    from tripwire.models.insights import InsightsFile, NodeProposal
    from tripwire.core.insights_store import save_insights
    save_insights(tmp_path_project, "s1", InsightsFile(proposals=[
        NodeProposal(kind="new_node", id="pg-tuning", name="PG Tuning",
                     body="tuning notes", rationale="useful"),
    ]))

    from tripwire.cli.session import session_cmd
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(session_cmd,
                           ["insights", "apply", "s1", "--proposal", "pg-tuning",
                            "--project-dir", str(tmp_path_project)])
    assert result.exit_code == 0, result.output
    node_path = tmp_path_project / "nodes" / "pg-tuning.yaml"
    assert node_path.is_file()
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement subcommand group**

Add to `src/tripwire/cli/session.py`:

```python
@session_cmd.group(name="insights")
def session_insights_cmd() -> None:
    """Session-proposed concept node insights."""


@session_insights_cmd.command("list")
@click.argument("session_id")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]),
              default="text")
def session_insights_list_cmd(session_id: str, project_dir: Path, output_format: str) -> None:
    from tripwire.core.insights_store import load_insights
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    insights = load_insights(resolved, session_id)

    if output_format == "json":
        click.echo(insights.model_dump_json(indent=2, exclude_none=True))
        return

    if not insights.proposals:
        click.echo("No insight proposals.")
        return

    for p in insights.proposals:
        click.echo(f"{p.kind} {p.id}")
        if p.kind == "new_node":
            click.echo(f"  name: {p.name}")
            click.echo(f"  rationale: {p.rationale}")
        else:
            click.echo(f"  delta: {p.delta}")
            click.echo(f"  rationale: {p.rationale}")
        click.echo("")


@session_insights_cmd.command("apply")
@click.argument("session_id")
@click.option("--proposal", "proposal_id", required=True,
              help="The proposal id to apply")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
def session_insights_apply_cmd(session_id: str, proposal_id: str, project_dir: Path) -> None:
    from tripwire.core.insights_store import load_insights, save_insights
    from tripwire.core.node_store import load_node, save_node
    from tripwire.models import ConceptNode

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    insights = load_insights(resolved, session_id)

    proposal = next((p for p in insights.proposals if p.id == proposal_id), None)
    if proposal is None:
        raise click.ClickException(f"Unknown proposal id {proposal_id!r}")

    if proposal.kind == "new_node":
        node = ConceptNode(
            id=proposal.id,
            type="model",
            name=proposal.name,
            status="active",
            body=proposal.body or "",
            related=proposal.related,
        )
        save_node(resolved, node, update_cache=False)
        click.echo(f"Created node {proposal.id}")
    else:
        try:
            node = load_node(resolved, proposal.id)
        except FileNotFoundError as exc:
            raise click.ClickException(
                f"Cannot apply update: node {proposal.id!r} does not exist."
            ) from exc
        # Append the delta to the node body with a timestamped section.
        from datetime import datetime, timezone
        stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        new_body = node.body.rstrip() + f"\n\n## Updated {stamp} (session {session_id})\n{proposal.delta}\n"
        save_node(resolved, node.model_copy(update={"body": new_body}), update_cache=False)
        click.echo(f"Updated node {proposal.id}")

    # Remove the applied proposal from insights.yaml
    remaining = [p for p in insights.proposals if p.id != proposal_id]
    save_insights(resolved, session_id, insights.model_copy(update={"proposals": remaining}))


@session_insights_cmd.command("reject")
@click.argument("session_id")
@click.option("--proposal", "proposal_id", required=True)
@click.option("--reason", default="", help="Why rejected (for audit)")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
def session_insights_reject_cmd(session_id: str, proposal_id: str, reason: str,
                                 project_dir: Path) -> None:
    from tripwire.core.insights_store import load_insights, save_insights, record_rejection
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    insights = load_insights(resolved, session_id)

    proposal = next((p for p in insights.proposals if p.id == proposal_id), None)
    if proposal is None:
        raise click.ClickException(f"Unknown proposal id {proposal_id!r}")

    record_rejection(resolved, session_id, proposal_id, reason)
    remaining = [p for p in insights.proposals if p.id != proposal_id]
    save_insights(resolved, session_id, insights.model_copy(update={"proposals": remaining}))
    click.echo(f"Rejected proposal {proposal_id}")
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/cli/session.py tests/unit/test_insights_cli.py
git commit -m "phase 2: tripwire session insights (list/apply/reject)"
```

## Task 2.11: Spawn system prompt addition for insights

This wires the insights prompt into the default spawn system prompt. Defers the actual file change to Phase 3 (spawn config) — we'll add a placeholder note here.

- [ ] **Commit an intentional placeholder**

```bash
git commit --allow-empty -m "phase 2: insights system prompt text landed with spawn config in Phase 3"
```

## Task 2.12: Backfill test projects

**Files:** outside the repo

- [ ] **Step 1: Backfill `developer.md`**

For each test project, for each issue at status `in_review` or `verified` or `done`, write a stub `developer.md`:

```bash
for proj in /Users/maia/Code/seido/projects/kb-pivot \
            /Users/maia/Code/seido/projects/project-graph-ui-v2 \
            /Users/maia/Code/seido/projects/project-keel-ui-init ; do
  [ -d "$proj/issues" ] || continue
  for issue_dir in "$proj/issues/"*/; do
    issue_key=$(basename "$issue_dir")
    issue_yaml="$issue_dir/issue.yaml"
    [ -f "$issue_yaml" ] || continue
    status=$(grep "^status:" "$issue_yaml" | awk '{print $2}')
    case "$status" in
      in_review|verified|done)
        dev_md="$issue_dir/developer.md"
        if [ ! -f "$dev_md" ]; then
          cat > "$dev_md" <<EOF
# Developer notes — $issue_key

## Backfill notice

This artifact was created retroactively during the v0.7 migration.
The issue was closed before per-issue artifacts were enforced.
See git history for the original PR and commits.
EOF
        fi
        ;;
    esac
  done
done
```

- [ ] **Step 2: Backfill `verified.md`**

```bash
for proj in /Users/maia/Code/seido/projects/kb-pivot \
            /Users/maia/Code/seido/projects/project-graph-ui-v2 \
            /Users/maia/Code/seido/projects/project-keel-ui-init ; do
  [ -d "$proj/issues" ] || continue
  for issue_dir in "$proj/issues/"*/; do
    issue_key=$(basename "$issue_dir")
    issue_yaml="$issue_dir/issue.yaml"
    [ -f "$issue_yaml" ] || continue
    status=$(grep "^status:" "$issue_yaml" | awk '{print $2}')
    case "$status" in
      verified|done)
        v_md="$issue_dir/verified.md"
        if [ ! -f "$v_md" ]; then
          cat > "$v_md" <<EOF
# Verification notes — $issue_key

**Verified by**: pm-agent
**Verified at**: $(date -u +%Y-%m-%d)
**Verdict**: approved

## Backfill notice

This artifact was created retroactively during the v0.7 migration.
The issue was approved before per-issue artifacts were enforced.
See git history for the original PR and merge.
EOF
        fi
      ;;
    esac
  done
done
```

- [ ] **Step 3: Validate each test project**

```bash
for proj in /Users/maia/Code/seido/projects/kb-pivot \
            /Users/maia/Code/seido/projects/project-graph-ui-v2 \
            /Users/maia/Code/seido/projects/project-keel-ui-init ; do
  echo "=== $proj ==="
  uv run tripwire validate --project-dir "$proj" --strict 2>&1 | tail -3
done
```

- [ ] **Step 4: Do not commit here — each project needs its own PR**

## Task 2.13: Phase 2 verification

```bash
uv run pytest tests/ -q 2>&1 | tail -5
uv run ruff check && uv run ruff format --check
```

---

# Phase 3 — Canonical spawn configuration

**Goal:** Move the `claude -p` invocation from Python strings to YAML template, with session/project override precedence.

## Task 3.1: Ship `spawn/defaults.yaml`

**Files:**
- Create: `src/tripwire/templates/spawn/defaults.yaml`

- [ ] **Step 1: Write**

```yaml
# Default spawn configuration. Projects override via
# project.yaml.spawn_defaults or <project>/.tripwire/spawn/defaults.yaml.
# Sessions override via session.yaml.spawn_config.
# Precedence: session > project > tripwire default.

invocation:
  command: claude
  background: true
  log_path_template: "~/.tripwire/logs/{project_slug}/{session_id}-{timestamp}.log"

config:
  model: opus
  fallback_model: sonnet
  effort: max
  permission_mode: bypassPermissions
  disallowed_tools: [Agent]
  max_turns: 200
  max_budget_usd: 50
  output_format: stream-json

prompt_template: |
  {plan}

  You are the {agent} agent for session {session_id}.
  Execute the plan. Stop at stop-and-ask points.
  Open a PR titled '{branch_type}({session_slug}): {session_name}' when done.

  Before you end the session: ask honestly — did you learn anything future
  agents in this area would benefit from inheriting? Not "what did I do"
  (that's developer.md) but "what insight would I want the next agent
  working near this to start from?" If yes, propose it in insights.yaml
  as a node addition or update. If nothing qualifies — if every insight
  is either obvious, already in a node, or specific to this session —
  leave the file absent. Do not force it.

system_prompt_append: |
  tripwire session: {session_id}; project: {project_slug}
  If context is getting heavy, use /compact to free space.
  Do not use the Agent tool — you are a single-agent session.
  Do not use /batch — the work is already decomposed in your plan.
```

- [ ] **Step 2: Commit**

```bash
git add src/tripwire/templates/spawn/defaults.yaml
git commit -m "phase 3: ship spawn/defaults.yaml"
```

## Task 3.2: SpawnConfig models

**Files:**
- Modify: `src/tripwire/models/session.py` (add SpawnConfig)
- Create: `src/tripwire/models/spawn.py` for full SpawnDefaults + Invocation

- [ ] **Step 1: Failing test**

```python
def test_spawn_defaults_load():
    from tripwire.models.spawn import SpawnDefaults
    import yaml
    from pathlib import Path
    import tripwire

    path = Path(tripwire.__file__).parent / "templates" / "spawn" / "defaults.yaml"
    data = yaml.safe_load(path.read_text())
    defaults = SpawnDefaults.model_validate(data)

    assert defaults.config.model == "opus"
    assert defaults.config.max_budget_usd == 50
    assert "{plan}" in defaults.prompt_template


def test_spawn_config_session_override():
    from tripwire.models.session import SpawnConfig

    sc = SpawnConfig(config={"model": "sonnet", "max_budget_usd": 10})
    assert sc.config["model"] == "sonnet"
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Create model**

`src/tripwire/models/spawn.py`:

```python
"""Spawn configuration models (shared between tripwire defaults + session/project overrides)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SpawnInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = "claude"
    background: bool = True
    log_path_template: str = "~/.tripwire/logs/{project_slug}/{session_id}-{timestamp}.log"


class SpawnConfigValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = "opus"
    fallback_model: str = "sonnet"
    effort: str = "max"
    permission_mode: str = "bypassPermissions"
    disallowed_tools: list[str] = Field(default_factory=lambda: ["Agent"])
    max_turns: int = 200
    max_budget_usd: int = 50
    output_format: str = "stream-json"


class SpawnDefaults(BaseModel):
    """Full tripwire-shipped defaults."""
    model_config = ConfigDict(extra="forbid")
    invocation: SpawnInvocation = Field(default_factory=SpawnInvocation)
    config: SpawnConfigValues = Field(default_factory=SpawnConfigValues)
    prompt_template: str = ""
    system_prompt_append: str = ""
```

Add `SpawnConfig` to `src/tripwire/models/session.py` for per-session overrides:

```python
class SpawnConfig(BaseModel):
    """Per-session spawn overrides. Any subset of SpawnDefaults."""
    model_config = ConfigDict(extra="forbid")
    invocation: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    prompt_template: str | None = None
    system_prompt_append: str | None = None
```

And add to `AgentSession`:

```python
    spawn_config: SpawnConfig | None = None
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/models/spawn.py src/tripwire/models/session.py tests/unit/test_spawn_models.py
git commit -m "phase 3: spawn configuration models"
```

## Task 3.3: `core/spawn_config.py` — load + merge

**Files:**
- Create: `src/tripwire/core/spawn_config.py`
- Test: `tests/unit/test_spawn_config.py`

- [ ] **Step 1: Failing test**

```python
def test_load_spawn_defaults(tmp_path_project):
    from tripwire.core.spawn_config import load_resolved_spawn_config
    # No overrides — returns tripwire default
    resolved = load_resolved_spawn_config(tmp_path_project, session=None)
    assert resolved.config.model == "opus"
    assert resolved.config.max_budget_usd == 50


def test_project_override_merges(tmp_path_project):
    import yaml
    # Project-level override
    p = tmp_path_project / "project.yaml"
    data = yaml.safe_load(p.read_text())
    data["spawn_defaults"] = {"config": {"max_budget_usd": 100}}
    p.write_text(yaml.safe_dump(data))

    from tripwire.core.spawn_config import load_resolved_spawn_config
    resolved = load_resolved_spawn_config(tmp_path_project, session=None)
    assert resolved.config.max_budget_usd == 100
    assert resolved.config.model == "opus"   # default stays


def test_session_override_wins(tmp_path_project, save_test_session):
    save_test_session(tmp_path_project, "s1",
                      spawn_config={"config": {"model": "sonnet"}})
    from tripwire.core.session_store import load_session
    session = load_session(tmp_path_project, "s1")

    from tripwire.core.spawn_config import load_resolved_spawn_config
    resolved = load_resolved_spawn_config(tmp_path_project, session=session)
    assert resolved.config.model == "sonnet"
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

`src/tripwire/core/spawn_config.py`:

```python
"""Load and merge spawn configuration with session > project > default precedence."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tripwire.models.session import AgentSession
from tripwire.models.spawn import SpawnDefaults


def _shipped_path() -> Path:
    import tripwire
    return Path(tripwire.__file__).parent / "templates" / "spawn" / "defaults.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge override into base. Override wins at leaves."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_resolved_spawn_config(
    project_dir: Path,
    session: AgentSession | None = None,
) -> SpawnDefaults:
    """Resolve spawn config with precedence: session > project > tripwire default."""
    # Tripwire shipped
    base_data = yaml.safe_load(_shipped_path().read_text(encoding="utf-8"))

    # Project override from .tripwire/spawn/defaults.yaml
    project_override_path = project_dir / ".tripwire" / "spawn" / "defaults.yaml"
    if project_override_path.is_file():
        override_data = yaml.safe_load(project_override_path.read_text(encoding="utf-8")) or {}
        base_data = _deep_merge(base_data, override_data)

    # Project.yaml.spawn_defaults
    from tripwire.core.store import load_project
    try:
        project = load_project(project_dir)
        if hasattr(project, "spawn_defaults") and project.spawn_defaults:
            base_data = _deep_merge(base_data, project.spawn_defaults)
    except Exception:
        pass

    # Session override
    if session and session.spawn_config:
        session_override = session.spawn_config.model_dump(exclude_none=True)
        base_data = _deep_merge(base_data, session_override)

    return SpawnDefaults.model_validate(base_data)


def render_prompt(defaults: SpawnDefaults, **ctx: Any) -> str:
    """Render the prompt template with the provided context vars."""
    return defaults.prompt_template.format(**ctx)


def render_system_append(defaults: SpawnDefaults, **ctx: Any) -> str:
    return defaults.system_prompt_append.format(**ctx)


def build_claude_args(
    defaults: SpawnDefaults,
    *,
    prompt: str,
    system_append: str,
    session_id: str,
    resume: bool = False,
) -> list[str]:
    """Build the full claude CLI args from the resolved config."""
    cfg = defaults.config
    args = [
        defaults.invocation.command,
        "-p", prompt,
        "--name", session_id,
        "--effort", cfg.effort,
        "--model", cfg.model,
        "--fallback-model", cfg.fallback_model,
        "--permission-mode", cfg.permission_mode,
        "--disallowedTools", ",".join(cfg.disallowed_tools),
        "--max-turns", str(cfg.max_turns),
        "--max-budget-usd", str(cfg.max_budget_usd),
        "--output-format", cfg.output_format,
        "--append-system-prompt", system_append,
    ]
    if resume:
        args.append("--resume")
    return args
```

Add `spawn_defaults: dict` field to `ProjectConfig`:

```python
# src/tripwire/models/project.py
spawn_defaults: dict | None = None
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/core/spawn_config.py src/tripwire/models/project.py \
        tests/unit/test_spawn_config.py
git commit -m "phase 3: spawn config resolver with precedence merging"
```

## Task 3.4: Refactor `_launch_claude` to use config

**Files:**
- Modify: `src/tripwire/cli/session.py`

- [ ] **Step 1: Find existing function**

```bash
grep -n "_launch_claude" src/tripwire/cli/session.py
```

- [ ] **Step 2: Replace implementation**

Replace the current `_launch_claude` function body to build args via `build_claude_args`:

```python
def _launch_claude(
    wt_path: Path,
    plan_content: str,
    session: AgentSession,
    project_dir: Path,
    branch_type: str,
    resume: bool = False,
) -> tuple[int, str]:
    """Launch `claude -p` as a background process. Returns (pid, log_path)."""
    from tripwire.core.spawn_config import (
        build_claude_args,
        load_resolved_spawn_config,
        render_prompt,
        render_system_append,
    )
    from tripwire.core.store import load_project
    import subprocess
    from datetime import datetime, timezone

    defaults = load_resolved_spawn_config(project_dir, session=session)
    project = load_project(project_dir)
    project_slug = project.name.lower().replace(" ", "-")

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    log_path = Path(defaults.invocation.log_path_template.format(
        project_slug=project_slug,
        session_id=session.id,
        timestamp=ts,
    )).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = render_prompt(
        defaults,
        plan=plan_content,
        agent=session.agent,
        session_id=session.id,
        session_name=session.name,
        session_slug=session.id,
        branch_type=branch_type,
    )
    system_append = render_system_append(
        defaults,
        session_id=session.id,
        project_slug=project_slug,
    )

    args = build_claude_args(
        defaults, prompt=prompt, system_append=system_append,
        session_id=session.id, resume=resume,
    )

    log_file = open(log_path, "w")
    try:
        proc = subprocess.Popen(
            args,
            cwd=str(wt_path),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_file.close()

    return proc.pid, str(log_path)
```

Update callers of `_launch_claude` to match the new signature (pass the full session object).

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/ -q 2>&1 | tail -5
```

Fix any callers that broke. The v0.6c test `test_spawn_creates_worktree` mocked `_launch_claude` with return_value=99999; update the mock to return a tuple `(99999, "/tmp/log")`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "phase 3: refactor _launch_claude to use canonical spawn config"
```

## Task 3.5: Phase 3 verification

```bash
uv run pytest tests/ -q 2>&1 | tail -5
uv run ruff check && uv run ruff format --check
```

---

# Phase 4 — Session monitor

**Goal:** `tripwire session monitor` + `/pm-session-monitor` for self-paced observation of executing sessions.

## Task 4.1: stream-json parser

**Files:**
- Create: `src/tripwire/core/stream_json.py`
- Test: `tests/unit/test_stream_json.py`

- [ ] **Step 1: Failing test**

```python
def test_parse_tool_use_event():
    from tripwire.core.stream_json import parse_event

    line = '{"type":"tool_use","tool":"Edit","input":{"file_path":"x.py"},"turn":2}'
    event = parse_event(line)
    assert event.kind == "tool_use"
    assert event.tool == "Edit"
    assert event.turn == 2


def test_parse_usage_event():
    from tripwire.core.stream_json import parse_event

    line = '{"type":"usage","total_tokens":15234,"cost_usd":0.42,"turn":2}'
    event = parse_event(line)
    assert event.kind == "usage"
    assert event.cost_usd == 0.42


def test_parse_unknown_event_preserved_as_info():
    from tripwire.core.stream_json import parse_event

    line = '{"type":"completely_new_event_type","data":"something"}'
    event = parse_event(line)
    assert event.kind == "info"


def test_parse_malformed_line_returns_none():
    from tripwire.core.stream_json import parse_event

    assert parse_event("not json") is None
    assert parse_event("") is None
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

`src/tripwire/core/stream_json.py`:

```python
"""Parse stream-json output from `claude -p`."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class StreamEvent:
    kind: str         # tool_use | tool_result | assistant | error | usage | info
    turn: int | None = None
    tool: str | None = None
    content: Any | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    raw: dict | None = None


_HARD_CODED_KINDS = {"tool_use", "tool_result", "assistant", "error", "usage"}


def parse_event(line: str) -> StreamEvent | None:
    """Parse one JSONL line into a StreamEvent. Returns None on malformed input."""
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    event_type = data.get("type", "info")
    kind = event_type if event_type in _HARD_CODED_KINDS else "info"

    return StreamEvent(
        kind=kind,
        turn=data.get("turn"),
        tool=data.get("tool"),
        content=data.get("content") or data.get("message") or data.get("output"),
        total_tokens=data.get("total_tokens"),
        cost_usd=data.get("cost_usd"),
        raw=data,
    )


def tail_events(log_path):
    """Generator yielding StreamEvents as they're appended to the log."""
    import time
    from pathlib import Path

    log = Path(log_path)
    with log.open("r", encoding="utf-8") as f:
        # Start at end for live tailing
        f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            event = parse_event(line)
            if event is not None:
                yield event
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/core/stream_json.py tests/unit/test_stream_json.py
git commit -m "phase 4: stream-json parser"
```

## Task 4.2: Monitor snapshot logic

**Files:**
- Create: `src/tripwire/core/session_monitor.py`
- Test: `tests/unit/test_session_monitor.py`

- [ ] **Step 1: Failing test**

```python
def test_snapshot_from_log(tmp_path, tmp_path_project, save_test_session):
    log = tmp_path / "session.log"
    log.write_text(
        '{"type":"assistant","message":"I will start","turn":1}\n'
        '{"type":"tool_use","tool":"Edit","input":{"file_path":"x.py"},"turn":2}\n'
        '{"type":"usage","total_tokens":5000,"cost_usd":0.20,"turn":2}\n'
    )
    save_test_session(tmp_path_project, "s1", status="executing",
                      runtime_state={"pid": 12345, "log_path": str(log),
                                      "claude_session_id": "sid"})

    from tripwire.core.session_monitor import take_snapshot
    snap = take_snapshot(tmp_path_project, "s1")
    assert snap.source == "stream-json"
    assert snap.latest_tool == "Edit"
    assert snap.total_cost_usd == pytest.approx(0.20)
    assert snap.turn == 2


def test_snapshot_falls_back_to_polling_when_log_missing(tmp_path_project, save_test_session):
    save_test_session(tmp_path_project, "s1", status="executing",
                      runtime_state={"pid": 12345, "log_path": "/nope/missing.log",
                                      "claude_session_id": "sid"})
    from tripwire.core.session_monitor import take_snapshot
    snap = take_snapshot(tmp_path_project, "s1")
    assert snap.source == "polling"


def test_stuck_detection_no_events_in_threshold(tmp_path):
    from tripwire.core.session_monitor import detect_stuck
    # Empty log past threshold: stuck
    log = tmp_path / "session.log"
    log.write_text("")
    # Mtime set to 30 min ago
    import os, time
    past = time.time() - 30 * 60
    os.utime(log, (past, past))
    assert detect_stuck(log, threshold_minutes=10) is True
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

`src/tripwire/core/session_monitor.py`:

```python
"""Session monitor snapshot logic — stream-json primary, git/gh fallback."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from tripwire.core.session_store import load_session
from tripwire.core.stream_json import parse_event


@dataclass
class MonitorSnapshot:
    session_id: str
    status: str
    source: str                           # "stream-json" | "polling" | "no-data"
    turn: int | None = None
    total_cost_usd: float | None = None
    latest_tool: str | None = None
    latest_tool_input: dict | None = None
    pr_number: int | None = None
    branch: str | None = None
    last_commit_sha: str | None = None
    process_alive: bool | None = None
    stuck: bool = False
    errors: list[str] = field(default_factory=list)


def take_snapshot(project_dir: Path, session_id: str) -> MonitorSnapshot:
    session = load_session(project_dir, session_id)
    snap = MonitorSnapshot(session_id=session_id, status=session.status, source="no-data")

    log_path = session.runtime_state.log_path
    if log_path and Path(log_path).is_file():
        _populate_from_log(snap, Path(log_path))
        snap.source = "stream-json"
    else:
        _populate_from_polling(snap, project_dir, session)
        snap.source = "polling"

    # Process alive check
    pid = session.runtime_state.pid
    if pid:
        from tripwire.core.process_helpers import is_alive
        snap.process_alive = is_alive(pid)

    return snap


def _populate_from_log(snap: MonitorSnapshot, log: Path) -> None:
    latest_tool_event = None
    usage_event = None
    last_turn = None

    with log.open("r", encoding="utf-8") as f:
        for line in f:
            event = parse_event(line)
            if event is None:
                continue
            if event.kind == "tool_use":
                latest_tool_event = event
            elif event.kind == "usage":
                usage_event = event
            elif event.kind == "error":
                snap.errors.append(str(event.content))
            if event.turn is not None:
                last_turn = event.turn

    if latest_tool_event is not None:
        snap.latest_tool = latest_tool_event.tool
        snap.latest_tool_input = latest_tool_event.raw.get("input") if latest_tool_event.raw else None
    if usage_event is not None:
        snap.total_cost_usd = usage_event.cost_usd
    snap.turn = last_turn
    snap.stuck = detect_stuck(log, threshold_minutes=10)


def _populate_from_polling(snap: MonitorSnapshot, project_dir: Path, session) -> None:
    import subprocess
    # Branch + latest commit from worktree (if present)
    wt = None
    for entry in session.runtime_state.worktrees:
        wt = Path(entry.worktree_path)
        snap.branch = entry.branch
        break
    if wt and wt.is_dir():
        try:
            result = subprocess.run(
                ["git", "-C", str(wt), "log", "-1", "--format=%h"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                snap.last_commit_sha = result.stdout.strip()
        except Exception:
            pass

    # PR via gh
    if snap.branch:
        try:
            result = subprocess.run(
                ["gh", "pr", "list", "--head", snap.branch, "--json", "number", "--limit", "1"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                prs = json.loads(result.stdout)
                if prs:
                    snap.pr_number = prs[0].get("number")
        except Exception:
            pass


def detect_stuck(log: Path, *, threshold_minutes: int = 10) -> bool:
    """Return True if the log hasn't been modified in threshold_minutes."""
    if not log.is_file():
        return False
    age_seconds = time.time() - log.stat().st_mtime
    return age_seconds > threshold_minutes * 60
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/core/session_monitor.py tests/unit/test_session_monitor.py
git commit -m "phase 4: session_monitor with stream-json + polling fallback"
```

## Task 4.3: CLI — `tripwire session monitor`

**Files:**
- Modify: `src/tripwire/cli/session.py`
- Test: `tests/unit/test_session_monitor_cli.py`

- [ ] **Step 1: Failing test**

```python
def test_monitor_empty_project(tmp_path_project):
    from tripwire.cli.session import session_cmd
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(session_cmd, ["monitor", "--project-dir", str(tmp_path_project)])
    assert result.exit_code == 0
    assert "no executing sessions" in result.output.lower() or "no sessions" in result.output.lower()


def test_monitor_specific_session(tmp_path_project, save_test_session):
    save_test_session(tmp_path_project, "s1", status="executing",
                      runtime_state={"pid": 99999, "claude_session_id": "sid"})
    from tripwire.cli.session import session_cmd
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(session_cmd, ["monitor", "s1",
                                          "--project-dir", str(tmp_path_project)])
    assert result.exit_code == 0
    assert "s1" in result.output
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Add subcommand**

```python
@session_cmd.command("monitor")
@click.argument("session_ids", nargs=-1)
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]),
              default="text")
def session_monitor_cmd(session_ids: tuple[str, ...], project_dir: Path,
                         output_format: str) -> None:
    """One-shot snapshot of executing sessions. Slash wrapper turns this into a loop."""
    from tripwire.core.session_monitor import take_snapshot
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    sessions = list_sessions(resolved)
    if session_ids:
        sessions = [s for s in sessions if s.id in session_ids]
    else:
        sessions = [s for s in sessions if s.status == "executing"]

    if not sessions:
        click.echo("No executing sessions.")
        return

    snaps = [take_snapshot(resolved, s.id) for s in sessions]

    if output_format == "json":
        from dataclasses import asdict
        click.echo(json.dumps([asdict(s) for s in snaps], indent=2, default=str))
        return

    for snap in snaps:
        click.echo(f"{snap.session_id}  {snap.status}  source={snap.source}")
        if snap.turn is not None:
            click.echo(f"  turn: {snap.turn}")
        if snap.total_cost_usd is not None:
            click.echo(f"  cost: ${snap.total_cost_usd:.2f}")
        if snap.latest_tool:
            click.echo(f"  latest tool: {snap.latest_tool}")
        if snap.branch:
            pr = f" (PR #{snap.pr_number})" if snap.pr_number else ""
            click.echo(f"  branch: {snap.branch}{pr}")
        if snap.errors:
            for err in snap.errors[-3:]:
                click.echo(f"  error: {err}")
        if snap.stuck:
            click.echo("  ⚑ STUCK (no log activity in 10min)")
        if snap.process_alive is False:
            click.echo("  ⚑ PROCESS DEAD")
        click.echo()
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/cli/session.py tests/unit/test_session_monitor_cli.py
git commit -m "phase 4: tripwire session monitor CLI"
```

## Task 4.4: Slash command `/pm-session-monitor`

**Files:**
- Create: `src/tripwire/templates/commands/pm-session-monitor.md`

- [ ] **Write**

```markdown
---
name: pm-session-monitor
description: Self-paced monitoring loop over executing sessions.
argument-hint: "[session-id ...] [auto-remediate <event-types>]"
---

You are the project manager. Load the project-manager skill if not active.

$ARGUMENTS

Auto-remediation defaults: read-only. You only elevate to auto-remediation
(re-engage stuck sessions, attach /autofix-pr, etc.) when the user's
arguments explicitly request it (e.g., "auto-remediate stuck" or
"auto-remediate ci-failure").

Workflow (self-paced via /loop dynamic mode):

1. Run `tripwire session monitor [session-ids] --format json`.
2. Parse the JSON snapshot.
3. Summarise in ≤10 lines: each session's status, turn, cost, latest tool,
   branch, PR status, any errors or stuck flags.
4. Take actions (read-only by default):
   - If any session's PR just opened and review hasn't run at this HEAD:
     run `/pm-session-review <session-id>`.
   - If any session is stuck: alert, don't re-engage unless user opted in.
   - If any session failed: alert, list resumption command.
   - If all sessions completed: run gap analysis and recommend next launches.
5. Decide pacing for next tick:
   - Active commits flowing: wait 60–90s.
   - Waiting for CI: wait 120–270s.
   - All idle (no commits 10+ min): wait 600–1200s.
   - Event detected: immediate.
6. ScheduleWakeup with the chosen interval.
7. At every tick, commit the monitor snapshot to the project repo:
   `chore: monitor snapshot <YYYY-MM-DDTHH:MM:SSZ>`.
```

- [ ] **Commit**

```bash
git add src/tripwire/templates/commands/pm-session-monitor.md
git commit -m "phase 4: /pm-session-monitor slash command"
```

## Task 4.5: Phase 4 verification

```bash
uv run pytest tests/ -q 2>&1 | tail -5
uv run ruff check && uv run ruff format --check
```

---

# Phase 5 — Session review

**Goal:** Structured review of PR against issue specs; writes verified.md; posts PR comments.

## Task 5.1: Review core module

**Files:**
- Create: `src/tripwire/core/session_review.py`
- Test: `tests/unit/test_session_review.py`

- [ ] **Step 1: Failing test**

```python
def test_acceptance_criteria_parsed_from_issue_body():
    from tripwire.core.session_review import parse_acceptance_criteria

    body = """
## Acceptance criteria
- [ ] Users can log in with email
- [ ] Auth token expires after 15 minutes
- [ ] Refresh token rotates on suspicious IP change
"""
    criteria = parse_acceptance_criteria(body)
    assert len(criteria) == 3
    assert "email" in criteria[0]


def test_deviation_unspec_files_detected():
    from tripwire.core.session_review import detect_deviations

    scope_paths = ["src/auth/"]
    pr_files = ["src/auth/jwt.py", "src/payments/stripe.py"]
    devs = detect_deviations(pr_files, scope_paths)
    assert "src/payments/stripe.py" in devs["unspec_files"]
    assert "src/auth/jwt.py" not in devs["unspec_files"]
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

`src/tripwire/core/session_review.py`:

```python
"""Session review: check PR diff against issue specs."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class IssueReview:
    key: str
    criteria: list[str]
    criteria_met: list[bool]
    criteria_evidence: list[str | None]


@dataclass
class Deviations:
    unspec_files: list[str] = field(default_factory=list)
    extra_deps: list[str] = field(default_factory=list)
    layout_divergence: list[str] = field(default_factory=list)


@dataclass
class ReviewReport:
    session_id: str
    pr_number: int | None
    issue_reviews: list[IssueReview] = field(default_factory=list)
    deviations: Deviations = field(default_factory=Deviations)
    plan_adherence_ok: bool = True
    plan_unmatched_steps: list[str] = field(default_factory=list)
    stop_and_ask_violations: list[str] = field(default_factory=list)
    verdict: str = "approved"              # "approved" | "approved_with_notes" | "rejected"

    @property
    def exit_code(self) -> int:
        if self.verdict == "rejected":
            return 2
        if self.verdict == "approved_with_notes":
            return 1
        return 0


def parse_acceptance_criteria(body: str) -> list[str]:
    """Extract bullets under `## Acceptance criteria`."""
    # Find the section
    pattern = re.compile(r"##\s+Acceptance criteria\s*\n(.*?)(?:\n##\s|$)", re.S)
    m = pattern.search(body)
    if not m:
        return []
    section = m.group(1)
    items: list[str] = []
    for line in section.splitlines():
        line = line.strip()
        if line.startswith("- [ ]") or line.startswith("- [x]") or line.startswith("- [X]"):
            items.append(line[5:].strip())
    return items


def detect_deviations(pr_files: list[str], scope_paths: list[str]) -> dict:
    """Flag PR files outside declared scope."""
    scope_paths = [p.rstrip("/") + "/" for p in scope_paths]
    unspec: list[str] = []
    for f in pr_files:
        if not any(f.startswith(sp) for sp in scope_paths):
            unspec.append(f)
    return {"unspec_files": unspec}


def check_plan_adherence(plan_md: str, pr_files: list[str]) -> tuple[bool, list[str]]:
    """Very lightweight — look for file references in plan markdown and check if
    each appears in the PR diff. Unmatched steps are reported."""
    # Find all code-like references to paths
    paths_in_plan = re.findall(r"`([a-zA-Z0-9_./\-]+\.(?:py|ts|tsx|js|md|yaml|yml))`", plan_md)
    unmatched: list[str] = []
    for p in set(paths_in_plan):
        if p not in pr_files:
            unmatched.append(p)
    return (len(unmatched) == 0, unmatched)


def check_stop_and_ask(issue_body: str, pr_files: list[str]) -> list[str]:
    """Scan issue body for 'stop and ask' clauses; no automated detection of
    whether they triggered. Returns the clauses so the reviewer can inspect
    manually."""
    pattern = re.compile(r"^(.*stop.{0,3}and.{0,3}ask.*)$", re.M | re.I)
    return [m.strip() for m in pattern.findall(issue_body)]
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/core/session_review.py tests/unit/test_session_review.py
git commit -m "phase 5: session_review core module (criteria, deviations, plan adherence)"
```

## Task 5.2: CLI — `tripwire session review`

**Files:**
- Modify: `src/tripwire/cli/session.py`

- [ ] **Implement**

Add:

```python
@session_cmd.command("review")
@click.argument("session_id")
@click.option("--pr", "pr_number", type=int, default=None,
              help="PR number (auto-detected if omitted)")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]),
              default="text")
@click.option("--post-pr-comments/--no-post-pr-comments", default=True,
              help="Post findings as PR comments via gh")
@click.option("--write-verified/--no-write-verified", default=True,
              help="Write verified.md side-effect for each issue in the session")
def session_review_cmd(session_id: str, pr_number: int | None, project_dir: Path,
                        output_format: str, post_pr_comments: bool,
                        write_verified: bool) -> None:
    """Review session PR against issue specs. Writes verified.md, posts PR comments."""
    import subprocess
    import json as _json
    from tripwire.core.session_review import (
        parse_acceptance_criteria, detect_deviations, check_plan_adherence,
        check_stop_and_ask, IssueReview, Deviations, ReviewReport,
    )
    from tripwire.core.store import load_issue
    from tripwire.core import paths

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    session = load_session(resolved, session_id)

    # Discover PR number if not given
    if pr_number is None:
        # Try from handoff or from gh pr list
        for wt in session.runtime_state.worktrees:
            try:
                result = subprocess.run(
                    ["gh", "pr", "list", "--head", wt.branch, "--json", "number", "--limit", "1"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    prs = _json.loads(result.stdout)
                    if prs:
                        pr_number = prs[0]["number"]
                        break
            except Exception:
                pass

    # Fetch PR files
    pr_files: list[str] = []
    if pr_number is not None:
        try:
            result = subprocess.run(
                ["gh", "pr", "view", str(pr_number), "--json", "files"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                data = _json.loads(result.stdout)
                pr_files = [f["path"] for f in data.get("files", [])]
        except Exception:
            pass

    report = ReviewReport(session_id=session_id, pr_number=pr_number)

    # Per-issue review
    for issue_key in session.issues:
        try:
            issue = load_issue(resolved, issue_key)
        except FileNotFoundError:
            continue
        criteria = parse_acceptance_criteria(issue.body)
        # Lightweight: we can't verify criteria automatically; mark as "requires manual review"
        # but still list them for the PM's output.
        ir = IssueReview(
            key=issue_key,
            criteria=criteria,
            criteria_met=[False] * len(criteria),
            criteria_evidence=[None] * len(criteria),
        )
        report.issue_reviews.append(ir)

    # Deviations — use combined Repo scope from all issues
    scope_paths: list[str] = []
    for ir in report.issue_reviews:
        try:
            issue = load_issue(resolved, ir.key)
            # Parse `## Repo scope` from body
            m = re.search(r"##\s+Repo scope\s*\n(.*?)(?:\n##\s|$)", issue.body, re.S)
            if m:
                for line in m.group(1).splitlines():
                    line = line.strip()
                    if line.startswith("- "):
                        scope_paths.append(line[2:].strip())
        except Exception:
            pass
    devs = detect_deviations(pr_files, scope_paths)
    report.deviations.unspec_files = devs["unspec_files"]

    # Plan adherence
    plan_path = paths.session_plan_path(resolved, session_id)
    if plan_path.is_file():
        plan_md = plan_path.read_text(encoding="utf-8")
        ok, unmatched = check_plan_adherence(plan_md, pr_files)
        report.plan_adherence_ok = ok
        report.plan_unmatched_steps = unmatched

    # Verdict
    if report.deviations.unspec_files or not report.plan_adherence_ok:
        report.verdict = "approved_with_notes"
    # For v0.7 — acceptance criteria are listed but not auto-verified; PM must manually check

    # Output
    if output_format == "json":
        from dataclasses import asdict
        click.echo(_json.dumps(asdict(report), indent=2, default=str))
    else:
        click.echo(f"Session Review: {session_id} (PR #{pr_number})\n")
        click.echo(f"Verdict: {report.verdict}")
        click.echo(f"\nIssues:")
        for ir in report.issue_reviews:
            click.echo(f"  {ir.key}: {len(ir.criteria)} criteria (manual verification needed)")
        if report.deviations.unspec_files:
            click.echo(f"\nDeviations (unspec'd files):")
            for f in report.deviations.unspec_files:
                click.echo(f"  - {f}")
        if report.plan_unmatched_steps:
            click.echo(f"\nPlan adherence issues:")
            for s in report.plan_unmatched_steps:
                click.echo(f"  - {s} (referenced in plan, absent from PR)")

    # Post to PR if requested
    if post_pr_comments and pr_number and output_format == "text":
        comment = f"## Tripwire session review\n\nVerdict: `{report.verdict}`\n"
        if report.deviations.unspec_files:
            comment += "\n**Files outside issue scope:**\n"
            for f in report.deviations.unspec_files:
                comment += f"- `{f}`\n"
        try:
            subprocess.run(
                ["gh", "pr", "comment", str(pr_number), "--body", comment],
                check=True, capture_output=True,
            )
            click.echo(f"\n(posted to PR #{pr_number})")
        except Exception:
            pass

    # Write verified.md side-effect
    if write_verified:
        _write_verified_for_session(resolved, session, report)

    raise click.exceptions.Exit(report.exit_code)


def _write_verified_for_session(project_dir, session, report):
    """Write verified.md for each issue in the session."""
    from datetime import datetime, timezone
    from tripwire.core import paths

    for ir in report.issue_reviews:
        verified_path = paths.issue_dir(project_dir, ir.key) / "verified.md"
        if verified_path.is_file():
            # Append re-review section
            existing = verified_path.read_text(encoding="utf-8")
            stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            addition = (f"\n\n## Re-review {stamp} (session {session.id})\n"
                         f"Verdict: {report.verdict}\n")
            verified_path.write_text(existing + addition, encoding="utf-8")
        else:
            stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            content = (f"# Verification notes — {ir.key}\n\n"
                        f"**Verified by**: pm-agent\n"
                        f"**Verified at**: {stamp}\n"
                        f"**Verdict**: {report.verdict}\n\n"
                        f"## Acceptance criteria\n\n")
            for crit in ir.criteria:
                content += f"- [ ] {crit} — manual verification needed\n"
            verified_path.parent.mkdir(parents=True, exist_ok=True)
            verified_path.write_text(content, encoding="utf-8")
```

- [ ] **Commit**

```bash
git add src/tripwire/cli/session.py
git commit -m "phase 5: tripwire session review CLI (writes verified.md, posts PR comment)"
```

## Task 5.3: Slash command `/pm-session-review`

**Files:**
- Create: `src/tripwire/templates/commands/pm-session-review.md`

- [ ] **Write**

```markdown
---
name: pm-session-review
description: Structured review of a session's PR against issue specs.
argument-hint: "<session-id> [--pr <number>]"
---

You are the project manager. Load the project-manager skill if not active.

$ARGUMENTS

Workflow:

1. Parse `<session-id>` from the arguments.
2. Run `tripwire session review <session-id> --format json`.
3. Parse the JSON report.
4. For each issue in the session, do a manual pass:
   - Open `issues/<key>/issue.yaml` and read acceptance criteria.
   - Open the PR diff (`gh pr view <pr> --diff`) and evaluate each criterion
     against the actual code.
   - Update verified.md with specific evidence (file:line, test name,
     or "manual smoke passed") for each criterion.
5. If any unverified criteria remain, set the verdict to `rejected`.
6. If the CLI already returned exit 2, confirm and stop; the PR is blocking
   until addressed.
7. Post a PR comment summarising the review (the CLI already does this; your
   job is to add per-finding inline comments if needed).
8. Report back with:
   - Overall verdict
   - Any blocking findings that must be fixed
   - Suggested follow-up issues
```

- [ ] **Commit**

```bash
git add src/tripwire/templates/commands/pm-session-review.md
git commit -m "phase 5: /pm-session-review slash command"
```

## Task 5.4: Phase 5 verification

```bash
uv run pytest tests/ -q 2>&1 | tail -5
uv run ruff check && uv run ruff format --check
```

---

# Phase 6 — Session complete

**Goal:** Orchestrate session close-out: verify merged PR + artifacts, reconcile nodes (PM-reviewed), close issues, cleanup.

## Task 6.1: `core/session_complete.py`

**Files:**
- Create: `src/tripwire/core/session_complete.py`
- Test: `tests/unit/test_session_complete.py`

- [ ] **Step 1: Failing test**

```python
def test_complete_refuses_non_executing(tmp_path_project, save_test_session):
    save_test_session(tmp_path_project, "s1", status="planned")
    from tripwire.core.session_complete import complete_session
    with pytest.raises(ValueError) as exc:
        complete_session(tmp_path_project, "s1", dry_run=True)
    assert "not_active" in str(exc.value) or "status" in str(exc.value).lower()


def test_complete_refuses_without_artifacts(tmp_path_project, save_test_session,
                                              save_test_issue):
    save_test_issue(tmp_path_project, "TST-1", status="in_review")
    # No developer.md or verified.md
    save_test_session(tmp_path_project, "s1", status="in_review", issues=["TST-1"])
    from tripwire.core.session_complete import complete_session
    with pytest.raises(ValueError) as exc:
        complete_session(tmp_path_project, "s1", dry_run=True,
                         skip_pr_merge_check=True)
    assert "missing_artifacts" in str(exc.value) or "artifact" in str(exc.value).lower()
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

`src/tripwire/core/session_complete.py`:

```python
"""Session complete orchestration."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from tripwire.core import paths
from tripwire.core.issue_artifact_store import load_issue_artifact_manifest, status_at_or_past
from tripwire.core.session_store import load_session, save_session
from tripwire.core.store import load_issue


class CompleteError(ValueError):
    """Raised when complete refuses to proceed."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass
class CompleteResult:
    session_id: str
    issues_closed: list[str] = field(default_factory=list)
    worktrees_removed: list[str] = field(default_factory=list)
    node_diffs: list[dict] = field(default_factory=list)     # for PM review
    sessions_unblocked: list[str] = field(default_factory=list)


def complete_session(
    project_dir: Path,
    session_id: str,
    *,
    dry_run: bool = False,
    force: bool = False,
    force_review: bool = False,
    skip_artifact_check: bool = False,
    skip_worktree_cleanup: bool = False,
    skip_pr_merge_check: bool = False,
) -> CompleteResult:
    session = load_session(project_dir, session_id)
    result = CompleteResult(session_id=session_id)

    # Status gate
    if session.status not in ("in_progress", "in_review", "verified") and not force:
        raise CompleteError("complete/not_active",
                             f"Session status is {session.status!r}, not completable.")

    # PR merged check
    if not skip_pr_merge_check and not force:
        _verify_pr_merged(session)

    # Artifact check
    if not skip_artifact_check:
        _verify_issue_artifacts(project_dir, session)

    # Compute node diffs for PM review
    result.node_diffs = _compute_node_diffs(project_dir, session)

    if dry_run:
        return result

    # Close issues
    for issue_key in session.issues:
        try:
            issue = load_issue(project_dir, issue_key)
        except FileNotFoundError:
            continue
        if issue.status != "done":
            issue.status = "done"
            from tripwire.core.store import save_issue
            save_issue(project_dir, issue)
            result.issues_closed.append(issue_key)

    # Transition session
    session.status = "done"
    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)
    session.updated_at = now
    if session.engagements:
        last = session.engagements[-1]
        if last.ended_at is None:
            last.ended_at = now
            last.outcome = "completed"
    save_session(project_dir, session)

    # Worktree cleanup
    if not skip_worktree_cleanup:
        for wt in session.runtime_state.worktrees:
            try:
                from tripwire.core.git_helpers import worktree_remove
                worktree_remove(Path(wt.clone_path), Path(wt.worktree_path))
                result.worktrees_removed.append(wt.worktree_path)
            except Exception:
                pass

    return result


def _verify_pr_merged(session):
    for wt in session.runtime_state.worktrees:
        try:
            result = subprocess.run(
                ["gh", "pr", "list", "--head", wt.branch, "--state", "merged",
                  "--json", "number", "--limit", "1"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                prs = json.loads(result.stdout)
                if prs:
                    return
        except Exception:
            pass
    raise CompleteError("complete/pr_not_merged",
                         "No merged PR found for any session branch.")


def _verify_issue_artifacts(project_dir, session):
    manifest = load_issue_artifact_manifest(project_dir)
    missing: list[str] = []
    for issue_key in session.issues:
        try:
            issue = load_issue(project_dir, issue_key)
        except FileNotFoundError:
            continue
        for entry in manifest.artifacts:
            if not entry.required:
                continue
            if not status_at_or_past(issue.status, entry.required_at_status, project_dir):
                continue
            file_path = paths.issue_dir(project_dir, issue_key) / entry.file
            if not file_path.is_file():
                missing.append(f"{issue_key}/{entry.file}")
    if missing:
        raise CompleteError(
            "complete/missing_artifacts",
            f"Missing required artifacts: {', '.join(missing)}",
        )


def _compute_node_diffs(project_dir, session):
    """Stub: compare node descriptions to PR diffs. Full implementation deferred."""
    # For v0.7 this is advisory only. The CLI reports diffs; PM decides.
    # Real impl would diff each issue-referenced node against the PR diff.
    return []
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/core/session_complete.py tests/unit/test_session_complete.py
git commit -m "phase 6: session_complete core (status + artifact + PR gate)"
```

## Task 6.2: CLI — `tripwire session complete`

**Files:**
- Modify: `src/tripwire/cli/session.py`

- [ ] **Implement**

```python
@session_cmd.command("complete")
@click.argument("session_id")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option("--skip-artifact-check", is_flag=True, default=False)
@click.option("--skip-worktree-cleanup", is_flag=True, default=False)
@click.option("--skip-pr-merge-check", is_flag=True, default=False)
@click.option("--force", is_flag=True, default=False)
@click.option("--force-review", is_flag=True, default=False)
@click.option("--dry-run", is_flag=True, default=False)
def session_complete_cmd(session_id: str, project_dir: Path,
                          skip_artifact_check: bool, skip_worktree_cleanup: bool,
                          skip_pr_merge_check: bool, force: bool,
                          force_review: bool, dry_run: bool) -> None:
    """Complete a session: verify gates, close issues, cleanup."""
    from tripwire.core.session_complete import complete_session, CompleteError

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        result = complete_session(
            resolved, session_id,
            dry_run=dry_run, force=force, force_review=force_review,
            skip_artifact_check=skip_artifact_check,
            skip_worktree_cleanup=skip_worktree_cleanup,
            skip_pr_merge_check=skip_pr_merge_check,
        )
    except CompleteError as e:
        raise click.ClickException(f"{e.code}: {e}") from e

    if dry_run:
        click.echo(f"Dry run: session {session_id} can be completed.")
        if result.node_diffs:
            click.echo(f"  Node diffs to review: {len(result.node_diffs)}")
        return

    click.echo(f"Session {session_id} → done")
    for iss in result.issues_closed:
        click.echo(f"  closed: {iss}")
    for wt in result.worktrees_removed:
        click.echo(f"  removed worktree: {wt}")
```

- [ ] **Commit**

```bash
git add src/tripwire/cli/session.py
git commit -m "phase 6: tripwire session complete CLI"
```

## Task 6.3: Slash command `/pm-session-complete`

**Files:**
- Create: `src/tripwire/templates/commands/pm-session-complete.md`

- [ ] **Write**

```markdown
---
name: pm-session-complete
description: Close out a session — review, artifacts, node reconciliation, cleanup.
argument-hint: "<session-id> [closing note]"
---

You are the project manager. Load the project-manager skill if not active.

$ARGUMENTS

Workflow:

1. Parse `<session-id>` from arguments.
2. Run `tripwire session complete <session-id> --dry-run` to preview the
   close-out. If it fails, address the issue (e.g., missing artifacts,
   PR not merged) and retry.
3. If the session's PR hasn't been reviewed at its current HEAD:
   run `/pm-session-review <session-id>`. Handle blocking findings
   (exit code 2 refuses completion) before proceeding.
4. Review proposed node diffs (the dry-run output lists them):
   - For each proposed node update, read the diff context, decide whether
     to apply, and edit the proposed text if needed.
   - Apply approved diffs by writing the node file(s).
   - Dismiss irrelevant proposals.
5. Review proposed insight-driven node additions/updates from
   `sessions/<session-id>/insights.yaml` (if present):
   - Run `tripwire session insights list <session-id>`.
   - For each proposal: accept (`tripwire session insights apply <session-id>
     --proposal <id>`) or reject (`tripwire session insights reject
     <session-id> --proposal <id> --reason "..."`).
6. Run `tripwire session complete <session-id>` (real).
7. Run `tripwire validate --strict` — the Layer 3 coherence check should
   pass now that issues and session both read `done`.
8. Commit: `complete: <session-id> (<comma-separated issue keys>)`.
9. Report back:
   - Issues closed
   - Nodes updated (with downstream impact via `tripwire refs reverse`)
   - Sessions unblocked
   - Recommended next launches
```

- [ ] **Commit**

```bash
git add src/tripwire/templates/commands/pm-session-complete.md
git commit -m "phase 6: /pm-session-complete slash command"
```

## Task 6.4: Phase 6 verification

```bash
uv run pytest tests/ -q 2>&1 | tail -5
uv run ruff check && uv run ruff format --check
```

---

# Phase 7 — Tripwire-tool CI

**Goal:** `.github/workflows/ci.yml` runs on every PR + push to main.

## Task 7.1: Create ci.yml

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Write**

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          python-version: "3.13"
      - name: Sync
        run: uv sync
      - name: Ruff check
        run: uv run ruff check
      - name: Ruff format check
        run: uv run ruff format --check
      - name: Pytest
        run: uv run pytest tests/ -q
```

- [ ] **Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "phase 7: tripwire CI workflow (ruff + pytest on 3.13)"
```

## Task 7.2: Verify CI runs on a sample PR

Push the branch and verify the CI workflow triggers. No test needed locally; GitHub Actions provides the verification.

---

# Phase 8 — PyPI publish + project CI templates

**Goal:** Publish on tag; `tripwire init` creates project `.github/workflows/tripwire.yml`; `tripwire ci install` for existing projects.

## Task 8.1: Publish workflow

**Files:**
- Create: `.github/workflows/publish.yml`

- [ ] **Write**

```yaml
name: Publish to PyPI

on:
  push:
    tags: ["v*"]

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Build
        run: uv build
      - name: Publish
        run: uv publish --token ${{ secrets.PYPI_API_TOKEN }}
```

- [ ] **Commit**

```bash
git add .github/workflows/publish.yml
git commit -m "phase 8: PyPI publish workflow on tag push"
```

## Task 8.2: Project CI workflow template

**Files:**
- Create: `src/tripwire/templates/project/.github/workflows/tripwire.yml.j2`

- [ ] **Write**

```yaml
name: Tripwire checks

on:
  pull_request:
  push:
    branches: [main, master]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Install tripwire
        run: uv tool install tripwire=={% raw %}{{ tripwire_version }}{% endraw %}
      - name: Validate
        run: tripwire validate --strict --format=json
      - name: Lint scoping
        run: tripwire lint scoping
      - name: Lint handoff
        run: tripwire lint handoff
      - name: Lint session
        run: tripwire lint session
      - name: Brief (smoke test)
        run: tripwire brief --format=json > /dev/null
```

- [ ] **Commit**

```bash
git add src/tripwire/templates/project/.github/workflows/tripwire.yml.j2
git commit -m "phase 8: project CI workflow template"
```

## Task 8.3: CLI — `tripwire ci install`

**Files:**
- Create: `src/tripwire/cli/ci.py`
- Modify: `src/tripwire/cli/main.py` (register)
- Test: `tests/unit/test_ci_cli.py`

- [ ] **Step 1: Failing test**

```python
def test_ci_install_writes_workflow(tmp_path_project):
    import yaml
    # Ensure tripwire_version is set in project.yaml
    p = tmp_path_project / "project.yaml"
    data = yaml.safe_load(p.read_text())
    data["tripwire_version"] = "0.7.0"
    p.write_text(yaml.safe_dump(data))

    from tripwire.cli.ci import ci_cmd
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(ci_cmd, ["install", "--project-dir", str(tmp_path_project)])
    assert result.exit_code == 0, result.output
    wf = tmp_path_project / ".github" / "workflows" / "tripwire.yml"
    assert wf.is_file()
    assert "tripwire==0.7.0" in wf.read_text()


def test_ci_install_refuses_overwrite(tmp_path_project):
    wf_dir = tmp_path_project / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "tripwire.yml").write_text("# existing")

    from tripwire.cli.ci import ci_cmd
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(ci_cmd, ["install", "--project-dir", str(tmp_path_project)])
    assert result.exit_code != 0


def test_ci_install_force_overwrites(tmp_path_project):
    wf_dir = tmp_path_project / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "tripwire.yml").write_text("# existing")
    # Set version
    import yaml
    p = tmp_path_project / "project.yaml"
    data = yaml.safe_load(p.read_text())
    data["tripwire_version"] = "0.7.0"
    p.write_text(yaml.safe_dump(data))

    from tripwire.cli.ci import ci_cmd
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(ci_cmd, ["install", "--project-dir", str(tmp_path_project),
                                     "--force"])
    assert result.exit_code == 0, result.output
    wf = tmp_path_project / ".github" / "workflows" / "tripwire.yml"
    assert "0.7.0" in wf.read_text()
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

`src/tripwire/cli/ci.py`:

```python
"""`tripwire ci` — CI workflow management."""
from __future__ import annotations

from pathlib import Path

import click
from jinja2 import Environment, FileSystemLoader

from tripwire.cli._utils import require_project as _require_project
from tripwire.core.store import load_project


@click.group(name="ci")
def ci_cmd() -> None:
    """CI workflow operations."""


@ci_cmd.command("install")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option("--force", is_flag=True, default=False)
def ci_install_cmd(project_dir: Path, force: bool) -> None:
    """Render .github/workflows/tripwire.yml from template."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    project = load_project(resolved)
    version = getattr(project, "tripwire_version", None)
    if not version:
        raise click.ClickException(
            "project.yaml.tripwire_version is not set. "
            "Add it (e.g., tripwire_version: 0.7.0) before running `tripwire ci install`."
        )

    target = resolved / ".github" / "workflows" / "tripwire.yml"
    if target.exists() and not force:
        raise click.ClickException(
            f"{target} already exists. Use --force to overwrite."
        )

    import tripwire
    template_root = Path(tripwire.__file__).parent / "templates" / "project" / ".github" / "workflows"
    env = Environment(loader=FileSystemLoader(str(template_root)), keep_trailing_newline=True)
    template = env.get_template("tripwire.yml.j2")
    rendered = template.render(tripwire_version=version)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    click.echo(f"Installed CI workflow at {target.relative_to(resolved)}")
```

Register in `src/tripwire/cli/main.py`:

```python
from tripwire.cli.ci import ci_cmd
cli.add_command(ci_cmd)
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/cli/ci.py src/tripwire/cli/main.py tests/unit/test_ci_cli.py
git commit -m "phase 8: tripwire ci install command"
```

## Task 8.4: `tripwire init` creates .github/workflows/

**Files:**
- Modify: `src/tripwire/cli/init.py`

- [ ] **Step 1: Failing test**

```python
def test_init_creates_ci_workflow_by_default(tmp_path):
    from tripwire.cli.init import init_cmd
    from click.testing import CliRunner
    target = tmp_path / "newproj"
    runner = CliRunner()
    result = runner.invoke(init_cmd, [str(target), "--name", "Test",
                                       "--key-prefix", "TST",
                                       "--tripwire-version", "0.7.0"])
    assert result.exit_code == 0
    wf = target / ".github" / "workflows" / "tripwire.yml"
    assert wf.is_file()
    assert "tripwire==0.7.0" in wf.read_text()


def test_init_skip_ci_flag(tmp_path):
    from tripwire.cli.init import init_cmd
    from click.testing import CliRunner
    target = tmp_path / "newproj"
    runner = CliRunner()
    result = runner.invoke(init_cmd, [str(target), "--name", "Test",
                                       "--key-prefix", "TST",
                                       "--skip-ci"])
    assert result.exit_code == 0
    wf = target / ".github" / "workflows" / "tripwire.yml"
    assert not wf.exists()
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Modify `init.py`**

Add a `--skip-ci` option and render the workflow by default:

```python
# Add to options
@click.option("--skip-ci", is_flag=True, default=False,
              help="Don't create .github/workflows/tripwire.yml")
@click.option("--tripwire-version", default=None, envvar="TRIPWIRE_VERSION",
              help="Version to pin in CI workflow (defaults to current tripwire version)")

# In the init_cmd body, after other files are rendered:
if not skip_ci:
    tripwire_version = tripwire_version or _current_tripwire_version()
    _render_ci_workflow(target_dir, tripwire_version)


def _current_tripwire_version() -> str:
    from importlib.metadata import version
    try:
        return version("tripwire")
    except Exception:
        return "0.7.0"


def _render_ci_workflow(target_dir: Path, version: str) -> None:
    import tripwire
    from jinja2 import Environment, FileSystemLoader

    template_root = Path(tripwire.__file__).parent / "templates" / "project" / ".github" / "workflows"
    env = Environment(loader=FileSystemLoader(str(template_root)), keep_trailing_newline=True)
    rendered = env.get_template("tripwire.yml.j2").render(tripwire_version=version)
    wf = target_dir / ".github" / "workflows" / "tripwire.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(rendered, encoding="utf-8")
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/cli/init.py tests/unit/test_init.py
git commit -m "phase 8: tripwire init creates .github/workflows/ by default"
```

## Task 8.5: Bump version to 0.7.0

**Files:**
- Modify: `pyproject.toml`

- [ ] **Bump**

```bash
sed -i '' 's/^version = "0.6.0"$/version = "0.7.0"/' pyproject.toml
grep "^version" pyproject.toml
```

- [ ] **Commit**

```bash
git add pyproject.toml
git commit -m "chore: bump to 0.7.0"
```

## Task 8.6: Update README with design principles

**Files:**
- Modify: `README.md`

- [ ] **Add principles section**

Edit README.md, near the top, add a "Design principles" section pulling in the 5 key principles verbatim from spec §2.1–§2.5:

```markdown
## Design principles

### 1. The graph is the synchronization layer that makes drift impossible

<copy §2.1 from spec>

### 2. Deviation is expected; tripwires catch what prevention can't

<copy §2.2 from spec>

### 3. Config over convention, with opinions

<copy §2.3 from spec>

### 4. Work compounds; sessions are knowledge-producing events

<copy §2.4 from spec>

### 5. Decomposition is a first-class product

<copy §2.5 from spec>

See CONTRIBUTING.md for supporting principles.
```

- [ ] **Commit**

```bash
git add README.md
git commit -m "phase 8: README design principles section"
```

## Task 8.7: Phase 8 verification

```bash
uv run pytest tests/ -q 2>&1 | tail -5
uv run ruff check && uv run ruff format --check
```

## Task 8.8: Merge feature/v0.7b to main and tag

- [ ] **Push branch**

```bash
git push -u origin feature/v0.7b
```

- [ ] **Open PR, merge after review**

```bash
gh pr create --title "v0.7b: features" --body "<summary covering all phases>"
```

- [ ] **After merge, tag and publish**

```bash
git checkout main
git pull
git tag -a v0.7.0 -m "v0.7.0"
git push origin v0.7.0
```

The publish.yml workflow fires on tag push; verify PyPI upload succeeds.

---

## Final verification

1. `tripwire validate --strict` passes on all 3 test projects (once they migrate status + backfill).
2. `pip install tripwire==0.7.0` works from PyPI.
3. `tripwire init newproj` creates `.github/workflows/tripwire.yml`.
4. `/pm-session-monitor`, `/pm-session-review`, `/pm-session-complete` slash commands land in shipped templates.

---

## What this plan does NOT do

- Container-aware monitor (deferred to post-v0.7)
- Multi-project workspace monitor (post-v0.7)
- Agent messaging MCP integration (post-v0.7)
- Auto-remediation by default (read-only is default; slash-command args elevate)
- A dedicated verification agent (PM fills verified role in v0.7)

Each of these awaits a future plan.
