"""Process helper functions."""

import os
import subprocess
import sys

from tripwire.core.process_helpers import is_alive, send_sigterm


class TestIsAlive:
    def test_current_process_is_alive(self):
        assert is_alive(os.getpid()) is True

    def test_nonexistent_pid(self):
        assert is_alive(4_000_000) is False


class TestSendSigterm:
    def test_sigterm_running_process(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            assert send_sigterm(proc.pid) is True
            proc.wait(timeout=5)
        finally:
            proc.kill()
            proc.wait()

    def test_sigterm_nonexistent_returns_false(self):
        assert send_sigterm(4_000_000) is False
