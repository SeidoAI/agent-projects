"""Template-tree copy + Jinja rendering for ``tripwire init``.

The packaged ``tripwire/templates/`` tree is the source of truth for
what a freshly-init'd project looks like; this module owns the
copy-and-render pipeline that lays it down.

Three distinct sub-paths (see :func:`copy_templates`):

1. **Jinja-rendered subdirs** (currently ``project/``): ``.j2`` files
   are rendered through Jinja with the init context and the suffix is
   stripped; non-``.j2`` files are copied verbatim.
2. **Verbatim subdirs** (``enums/``, ``issue_templates/``, etc.):
   files copy as-is, including ``.j2`` suffix (agents render at
   runtime). Source subdir name may map to a different destination.
3. **Root-level files** (``standards.md.j2``): Jinja-rendered into the
   project root.

The CLI wrapper at ``cli/init.py:init_cmd`` calls these in sequence
after collecting the rendering context.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from tripwire.core import paths

PROJECT_TEMPLATE_SUBDIR = "project"

# Template subdirectories that get Jinja2-rendered at init time.
# Files under these directories are RENDERED through Jinja with the
# project context (project_name, key_prefix, etc.) and the `.j2` suffix
# is stripped in the destination filename.
JINJA_RENDERED_SUBDIRS: tuple[str, ...] = (PROJECT_TEMPLATE_SUBDIR,)

# Mapping from source subdirectory under `templates/` to destination
# relative path under the project root. Files are copied verbatim
# (including any `.j2` suffix — agents render these at runtime).
#
# `project` is handled separately because its files are rendered into
# the project root.
#
# `agent_templates` → `agents` is a rename (the source name is clearer
# for the package, but the destination name matches the rest of the
# plan's layout).
#
# `artifacts` is the one exception that stays nested under `templates/`
# in the destination — it's the set of templates that SESSIONS use to
# produce their session artifacts at runtime.
VERBATIM_TEMPLATE_MAPPINGS: tuple[tuple[str, str], ...] = (
    ("enums", "enums"),
    ("issue_templates", "issue_templates"),
    ("comment_templates", "comment_templates"),
    ("artifacts", "templates/artifacts"),
    ("scoping-artifacts", "plans/artifacts"),
    ("agent_templates", "agents"),
    ("session_templates", "session_templates"),
    ("orchestration", "orchestration"),
    ("skills", ".claude/skills"),
    ("commands", ".claude/commands"),
)

# Standalone files (at `templates/` root, not under a subdirectory) that
# should be rendered into the project root. `standards.md.j2` is the
# only one in v0.
ROOT_J2_FILES: tuple[tuple[str, str], ...] = (("standards.md.j2", "standards.md"),)

CREATED_DIRS = [
    paths.ISSUES_DIR,
    paths.NODES_DIR,
    paths.SESSIONS_DIR,
    paths.PLANS_DIR,
]


def _jinja_env(templates_dir: Path) -> Environment:
    """Construct a Jinja2 environment rooted at the templates directory.

    ``StrictUndefined`` catches typos in template variables — better to
    fail the init than silently produce a file with ``{{ missing_var }}``.
    """
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )


def _map_destination(rel: Path) -> Path:
    """Translate a template-relative path to its destination path.

    - ``gitignore.j2`` → ``.gitignore``
    - ``foo.yaml.j2`` → ``foo.yaml``
    - ``foo.md.j2`` → ``foo.md``
    - Everything else: strip the ``.j2`` extension if present.
    """
    if rel.name == "gitignore.j2":
        return rel.with_name(".gitignore")
    if rel.suffix == ".j2":
        return rel.with_suffix("")
    return rel


def copy_templates(
    templates_dir: Path, target_dir: Path, context: dict[str, Any]
) -> list[Path]:
    """Copy the packaged templates tree into the target.

    Raises:
        ValueError: when the packaged ``project/`` subdir is missing.
            That's a packaging defect, not a user error.

    Returns the list of destination paths written.
    """
    env = _jinja_env(templates_dir)
    written: list[Path] = []

    # 1. Jinja-rendered subdirs (currently only `project/`).
    for subdir in JINJA_RENDERED_SUBDIRS:
        source_root = templates_dir / subdir
        if not source_root.is_dir():
            raise ValueError(
                f"Packaged templates directory missing: {source_root}. "
                "This is a package installation problem."
            )
        for source in sorted(source_root.rglob("*")):
            if source.is_dir() or source.name == "__init__.py":
                continue
            rel = source.relative_to(source_root)
            dest = target_dir / _map_destination(rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == ".j2":
                template_name = str(Path(subdir) / rel)
                rendered = env.get_template(template_name).render(**context)
                dest.write_text(rendered, encoding="utf-8")
            else:
                shutil.copy2(source, dest)
            written.append(dest)

    # 2. Verbatim subdirs — copied as-is, with optional rename.
    for src_subdir, dest_subdir in VERBATIM_TEMPLATE_MAPPINGS:
        source_root = templates_dir / src_subdir
        if not source_root.is_dir():
            # Subdir doesn't exist yet (e.g. `skills` before Step 10).
            continue
        dest_root = target_dir / dest_subdir
        for source in sorted(source_root.rglob("*")):
            if source.is_dir() or source.name == "__init__.py":
                continue
            rel = source.relative_to(source_root)
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            written.append(dest)

    # 3. Root-level Jinja files.
    for src_name, dest_name in ROOT_J2_FILES:
        source = templates_dir / src_name
        if not source.is_file():
            continue
        dest = target_dir / dest_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        rendered = env.get_template(src_name).render(**context)
        dest.write_text(rendered, encoding="utf-8")
        written.append(dest)

    return written


def create_project_dirs(target_dir: Path) -> list[Path]:
    """Create the empty project subdirectories with ``.gitkeep`` markers."""
    created: list[Path] = []
    for rel in CREATED_DIRS:
        dir_path = target_dir / rel
        dir_path.mkdir(parents=True, exist_ok=True)
        gitkeep = dir_path / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
        created.append(dir_path)
    return created
