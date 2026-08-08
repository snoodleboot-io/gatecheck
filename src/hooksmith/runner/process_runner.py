"""ProcessRunner — the subprocess boundary for hook execution (STY-0013 / GAT-14).

``ProcessRunner`` is a single injectable ``typing.Protocol`` so ``run_hook``
unit-tests against a fake — no real subprocess. ``SubprocessProcessRunner`` is the
default impl and the only place a hook's command is actually spawned; it returns the
exit code and the combined stdout+stderr.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol


class ProcessRunner(Protocol):
    """The injectable process boundary: run ``argv`` and return ``(exit_code, output)``."""

    def run(
        self, argv: list[str], *, env: Mapping[str, str], cwd: Path | None
    ) -> tuple[int, str]: ...


class SubprocessProcessRunner:
    """Default ``ProcessRunner`` over ``subprocess.run`` (combined stdout+stderr)."""

    def run(self, argv: list[str], *, env: Mapping[str, str], cwd: Path | None) -> tuple[int, str]:
        """Run ``argv`` to completion; return its exit code and combined output.

        ``OSError`` (e.g. the command cannot be spawned) propagates to the caller,
        which maps it to an ``error`` result.
        """
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            env=dict(env),
            cwd=cwd,
        )
        return completed.returncode, (completed.stdout or "") + (completed.stderr or "")
