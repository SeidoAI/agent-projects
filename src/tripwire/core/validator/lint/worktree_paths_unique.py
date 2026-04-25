"""Stub — implementation lands in the green step."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tripwire.core.validator import CheckResult, ValidationContext


def check(ctx: ValidationContext) -> list[CheckResult]:
    return []
