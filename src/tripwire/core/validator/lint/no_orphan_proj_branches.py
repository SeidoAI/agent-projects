"""Stub — implementation lands in the green step."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tripwire.core.validator import CheckResult, ValidationContext


def local_proj_branches(repo_dir: Path) -> list[str]:
    return []


def check(ctx: ValidationContext) -> list[CheckResult]:
    return []
