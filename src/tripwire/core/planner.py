"""Dry-run preview of what ``tripwire init`` would produce.

Used by ``tripwire plan`` to show the directory tree, file list, and
template contents without writing anything to disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tripwire.cli.init import (
    CREATED_DIRS,
    JINJA_RENDERED_SUBDIRS,
    ROOT_J2_FILES,
    VERBATIM_TEMPLATE_MAPPINGS,
    _jinja_env,
)
from tripwire.templates import get_templates_dir


@dataclass
class PlannedFile:
    """A file that would be created."""

    rel_path: str
    size_bytes: int
    source: str  # "jinja", "verbatim", "gitkeep"


@dataclass
class PlanPreview:
    """The full preview of what init would produce."""

    target_name: str
    dirs: list[str] = field(default_factory=list)
    files: list[PlannedFile] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.files)

    def to_json(self) -> dict:
        return {
            "target_name": self.target_name,
            "total_files": self.total_files,
            "total_dirs": len(self.dirs),
            "dirs": self.dirs,
            "files": [
                {
                    "rel_path": f.rel_path,
                    "size_bytes": f.size_bytes,
                    "source": f.source,
                }
                for f in self.files
            ],
        }


def preview_init(
    project_name: str = "my-project",
    key_prefix: str = "MP",
    base_branch: str = "main",
    description: str = "",
) -> PlanPreview:
    """Compute what ``tripwire init`` would create without writing anything."""
    templates_dir = get_templates_dir()
    preview = PlanPreview(target_name=project_name)

    # 1. Directories
    for rel in CREATED_DIRS:
        preview.dirs.append(rel)

    # 2. Jinja-rendered files
    env = _jinja_env(templates_dir)
    context = {
        "project_name": project_name,
        "key_prefix": key_prefix,
        "base_branch": base_branch,
        "description": description,
        "repos": [],
        "created_at": "2026-01-01T00:00:00Z",
    }
    for subdir in JINJA_RENDERED_SUBDIRS:
        source_root = templates_dir / subdir
        if not source_root.is_dir():
            continue
        for source in sorted(source_root.rglob("*.j2")):
            if source.name == "__init__.py":
                continue
            rel = source.relative_to(source_root)
            dest_name = str(rel).removesuffix(".j2")
            try:
                tpl = env.get_template(f"{subdir}/{rel}")
                rendered = tpl.render(**context)
                preview.files.append(
                    PlannedFile(
                        rel_path=dest_name,
                        size_bytes=len(rendered.encode("utf-8")),
                        source="jinja",
                    )
                )
            except Exception:
                preview.files.append(
                    PlannedFile(rel_path=dest_name, size_bytes=0, source="jinja")
                )

    # 3. Verbatim copies
    for src_subdir, dest_subdir in VERBATIM_TEMPLATE_MAPPINGS:
        source_root = templates_dir / src_subdir
        if not source_root.is_dir():
            continue
        for source in sorted(source_root.rglob("*")):
            if source.is_dir() or source.name == "__init__.py":
                continue
            rel = source.relative_to(source_root)
            dest_rel = f"{dest_subdir}/{rel}"
            preview.files.append(
                PlannedFile(
                    rel_path=dest_rel,
                    size_bytes=source.stat().st_size,
                    source="verbatim",
                )
            )

    # 4. Root Jinja files
    for src_name, dest_name in ROOT_J2_FILES:
        source = templates_dir / src_name
        if source.is_file():
            try:
                tpl = env.get_template(src_name)
                rendered = tpl.render(**context)
                preview.files.append(
                    PlannedFile(
                        rel_path=dest_name,
                        size_bytes=len(rendered.encode("utf-8")),
                        source="jinja",
                    )
                )
            except Exception:
                preview.files.append(
                    PlannedFile(rel_path=dest_name, size_bytes=0, source="jinja")
                )

    # 5. .gitkeep files
    for rel in CREATED_DIRS:
        preview.files.append(
            PlannedFile(rel_path=f"{rel}/.gitkeep", size_bytes=0, source="gitkeep")
        )

    return preview
