#!/usr/bin/env python3
"""fake-tmux — records every invocation to a log file at $FAKE_TMUX_LOG.

Simulates tmux behaviours needed by TmuxRuntime unit tests:
- ``new-session -d -s NAME ...`` records the session name.
- ``capture-pane -pt NAME`` emits the contents of $FAKE_TMUX_PANE_TEXT.
- ``send-keys -t NAME ...`` records the keys.
- ``has-session -t NAME`` exits 0 if $FAKE_TMUX_HAS/<name> exists, 1 otherwise.
- ``kill-session -t NAME`` removes $FAKE_TMUX_HAS/<name>.
- ``attach -t NAME`` exits 0.
"""

import os
import sys
from pathlib import Path


def main() -> int:
    log_path = os.environ.get("FAKE_TMUX_LOG")
    if log_path:
        with open(log_path, "a") as fh:
            fh.write(" ".join(sys.argv[1:]) + "\n")

    args = sys.argv[1:]
    if not args:
        return 0

    cmd = args[0]
    has_dir = Path(os.environ.get("FAKE_TMUX_HAS", "/tmp/fake_tmux_has"))
    has_dir.mkdir(parents=True, exist_ok=True)

    if cmd == "new-session":
        if "-s" in args:
            name = args[args.index("-s") + 1]
            (has_dir / name).touch()
        return 0

    if cmd == "capture-pane":
        text = os.environ.get("FAKE_TMUX_PANE_TEXT", "")
        sys.stdout.write(text)
        return 0

    if cmd == "send-keys":
        return 0

    if cmd == "has-session":
        if "-t" in args:
            name = args[args.index("-t") + 1]
            return 0 if (has_dir / name).exists() else 1
        return 1

    if cmd == "kill-session":
        if "-t" in args:
            name = args[args.index("-t") + 1]
            (has_dir / name).unlink(missing_ok=True)
        return 0

    if cmd == "attach":
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
