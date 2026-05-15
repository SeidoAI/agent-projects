"""Regression tests for :mod:`tripwire.runtimes.bg_task`.

The bug being guarded against (PM-handoff #6, D1): an earlier
streaming-and-poll implementation could capture 0 bytes of output even
when the subprocess wrote to stdout. The contract is "after the bg-task
completes, captured output equals what the subprocess wrote."
"""

from __future__ import annotations

import sys

import pytest

from tripwire.runtimes.bg_task import BgTaskResult, run_bg_task


class TestRunBgTask:
    def test_captures_nonzero_stdout_for_known_nonempty_command(self):
        """Regression: a command that writes a line to stdout must
        produce non-zero captured output. The 0-byte race we replaced
        would have silently returned an empty string here."""
        result = run_bg_task([sys.executable, "-c", "print('hello-bg-task')"])

        assert isinstance(result, BgTaskResult)
        assert result.returncode == 0
        assert not result.timed_out
        # Contract: captured stdout equals what the subprocess wrote.
        assert "hello-bg-task" in result.stdout
        # Stronger contract — the full payload (rstripped of newline)
        # must be present, not just a fragment.
        assert result.stdout.rstrip("\n") == "hello-bg-task"

    def test_captures_multiline_stdout_exactly(self):
        """Every byte the subprocess wrote to stdout must round-trip
        through the helper. Catches buffer-truncation regressions."""
        script = "import sys; sys.stdout.write('a\\nb\\nc\\n'); sys.stdout.flush()"
        result = run_bg_task([sys.executable, "-c", script])

        assert result.returncode == 0
        assert result.stdout == "a\nb\nc\n"

    def test_captures_stderr_separately_from_stdout(self):
        """stderr and stdout are distinct streams in the result; one
        does not bleed into the other."""
        script = (
            "import sys; sys.stdout.write('to-out\\n'); sys.stderr.write('to-err\\n')"
        )
        result = run_bg_task([sys.executable, "-c", script])

        assert "to-out" in result.stdout
        assert "to-out" not in result.stderr
        assert "to-err" in result.stderr
        assert "to-err" not in result.stdout

    def test_returncode_propagates_nonzero_exit(self):
        result = run_bg_task([sys.executable, "-c", "import sys; sys.exit(7)"])
        assert result.returncode == 7
        assert not result.timed_out

    def test_timeout_kills_long_running_child(self):
        """A child that won't exit on its own is killed and the helper
        flags ``timed_out=True``. We don't assert on returncode beyond
        non-zero — kill semantics vary by platform."""
        # Sleeps far longer than the timeout; communicate(timeout=...)
        # must raise, we kill, and return timed_out=True.
        result = run_bg_task(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.5,
        )
        assert result.timed_out is True
        assert result.returncode != 0

    def test_cwd_is_honoured(self, tmp_path):
        """``cwd`` parameter routes through to Popen so the child runs
        where the caller asked."""
        result = run_bg_task(
            [sys.executable, "-c", "import os; print(os.getcwd())"],
            cwd=tmp_path,
        )
        assert result.returncode == 0
        # Resolve both ends — macOS /var vs /private/var, etc.
        from pathlib import Path

        assert Path(result.stdout.strip()).resolve() == tmp_path.resolve()

    def test_empty_output_command_returns_empty_string_not_none(self):
        """A command that writes nothing yields ``""`` (not ``None``).
        Defensive: callers can ``.strip()`` / ``.splitlines()`` without
        a None-check."""
        result = run_bg_task([sys.executable, "-c", "pass"])
        assert result.returncode == 0
        assert result.stdout == ""
        assert result.stderr == ""

    def test_env_override_reaches_child(self):
        """``env`` parameter is passed through verbatim. Guard against
        a future refactor that drops the kwarg."""
        result = run_bg_task(
            [
                sys.executable,
                "-c",
                "import os; print(os.environ.get('TRIPWIRE_TEST_VAR', '<unset>'))",
            ],
            env={"TRIPWIRE_TEST_VAR": "set-by-test", "PATH": ""},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "set-by-test"


@pytest.mark.parametrize("payload_len", [1, 16, 1024, 65536])
def test_captures_full_payload_at_various_sizes(payload_len: int):
    """The race we replaced manifested at any payload size — the buffer
    could be drained or not depending on timing. Exercise a range of
    sizes; every byte must round-trip."""
    script = f"import sys; sys.stdout.write('x' * {payload_len})"
    result = run_bg_task([sys.executable, "-c", script])
    assert result.returncode == 0
    assert len(result.stdout) == payload_len
    assert result.stdout == "x" * payload_len
