"""Every JSONL append routes through ``core.jsonl_log.append_jsonl``.

Philosophy §7 ("Filesystem-native, file-watcher transport") makes the
append-only JSONL logs (audit, events, routing telemetry) load-bearing:

    *"Tripwire is git-native: every entity is a file, every change is
    a commit, every audit is `git log` or `git blame`."*

The framework has three of these logs, each consumed by different
readers:

  - ``.tripwire/audit.jsonl`` — audit trail of transitions, read on
    PM-agent session recovery and by human auditors.
  - ``events/<UTC-date>.jsonl`` — workflow event stream, read by the
    UI file-watcher → WebSocket → frontend dashboard.
  - ``sessions/.routing_telemetry.jsonl`` — per-session telemetry,
    read by ``tripwire session analyze-routing``.

All three are POSIX-append-atomic JSONL: ``open("a").write(line+"\\n")``
where ``len(line) < PIPE_BUF`` (~4 KiB). The kernel guarantees that
each write hits the file as a single atomic chunk; readers either see
the full record or no record, never a torn one.

This **discipline** has to be a single helper. Three sites
hand-rolling the same ``open("a")`` pattern were the round-2 finding
this test now pins. Today every JSONL append in ``src/tripwire/``
must route through :func:`tripwire.core.jsonl_log.append_jsonl`; raw
``open(..., "a")`` against a ``.jsonl`` target is forbidden.
"""

from __future__ import annotations

import re
from pathlib import Path

import tripwire

SRC_ROOT = Path(tripwire.__file__).parent

# The helper itself is the one allowed site for `open("a")` against a
# JSONL path. Other modules call the helper.
ALLOWED_RAW_APPEND_SITES = {
    SRC_ROOT / "core" / "jsonl_log.py",
    # The inbox-resolve service uses tempfile+rename (true atomic
    # write) against `.md`, not `.jsonl` — but its tmp.write_text
    # could trip a naive pattern. We scan specifically for `.jsonl`
    # targets so this file is excluded by content, not by allowlist.
}

# Pattern: `open(..., "a"...)` or `open(..., 'a'...)` where the path
# being opened (any arg before mode) mentions `.jsonl` literally. This
# is intentionally narrow — we want to catch raw JSONL appends, not
# every `open` in the tree.
RAW_JSONL_APPEND = re.compile(
    r"\.open\(\s*[\"\']a[\"\']", re.IGNORECASE
)


def _line_targets_jsonl(line: str) -> bool:
    """True if the line names a `.jsonl` path (literal or via a
    function whose name suggests it). Heuristic but tight: we only
    flag `open("a")` when the same line also mentions `.jsonl` OR
    `audit_log` OR `telemetry` OR `events` log paths."""
    if ".jsonl" in line:
        return True
    # Names of helpers/path-builders we know return jsonl paths.
    for hint in ("audit_log_path", "telemetry_path", "events_dir"):
        if hint in line:
            return True
    return False


def test_no_raw_open_a_on_jsonl_paths():
    """No source file outside ``core/jsonl_log.py`` opens a JSONL file
    in append mode directly.

    Concretely: ``path.open("a")`` and ``open(path, "a")`` are
    forbidden when the target is a ``.jsonl`` log. Use
    ``tripwire.core.jsonl_log.append_jsonl`` instead.
    """
    violations: list[str] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        if py_file in ALLOWED_RAW_APPEND_SITES:
            continue
        text = py_file.read_text(encoding="utf-8")
        # Walk surrounding context: a single line that contains the
        # append-mode `open` matters; the same line should also name
        # a jsonl-shaped path. (Two-line spreads — open() args on the
        # next line — are caught at code review; the regex stays
        # one-line for clarity.)
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if RAW_JSONL_APPEND.search(line) and _line_targets_jsonl(line):
                rel = py_file.relative_to(SRC_ROOT.parent)
                violations.append(f"  {rel}:{line_no}: {line.strip()}")

    assert not violations, (
        "Philosophy §7 violation — raw `open(..., \"a\")` on a JSONL log.\n"
        "All three of audit / events / telemetry route through one helper:\n"
        "`tripwire.core.jsonl_log.append_jsonl`. A new raw-append site is\n"
        "duplication that drifts (per-call-site json.dumps options,\n"
        "missing parent.mkdir, etc.).\n"
        "\n"
        "Offending sites:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: replace `with path.open(\"a\")` with\n"
        "  from tripwire.core.jsonl_log import append_jsonl\n"
        "  append_jsonl(path, record, **dumps_kwargs)"
    )


def test_jsonl_helper_lives_in_core_not_in_ui_services():
    """``append_jsonl`` lives at ``tripwire.core.jsonl_log`` — not in
    ``ui/services/``. Audit / events / telemetry are core concerns;
    the helper's home should reflect that.

    The previous home (``ui.services._atomic_write``) was a misnomer:
    that module is named for tempfile+rename atomicity, but JSONL
    appends use kernel-level append atomicity instead. Different
    mechanism, different module.
    """
    expected = SRC_ROOT / "core" / "jsonl_log.py"
    assert expected.exists(), (
        f"`{expected.relative_to(SRC_ROOT.parent)}` is missing. "
        f"The JSONL helper is a core concern — recreate it there, not "
        f"in `ui/services/`."
    )

    legacy = SRC_ROOT / "ui" / "services" / "_atomic_write.py"
    if legacy.exists():
        legacy_text = legacy.read_text(encoding="utf-8")
        assert "append_jsonl" not in legacy_text, (
            "Philosophy §7 violation — `append_jsonl` is still defined or "
            "re-exported from `ui.services._atomic_write`. That module's "
            "name implies tempfile+rename; JSONL appends use a different "
            "(POSIX kernel-append) mechanism. Move all references to "
            "`tripwire.core.jsonl_log`."
        )
