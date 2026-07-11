"""Single-hook execution — argv assembly + subprocess → HookResult (STY-0013 / GAT-14).

``run_hook`` resolves a hook's environment (FEAT-0003), assembles its command from
``run`` and the hook's pre-resolved file list (STY-0011), runs it with the resolved
``bin_dir`` on ``PATH``, and captures the outcome. Env-resolution and spawn failures
become an ``error`` ``HookResult`` rather than an exception.
"""

from __future__ import annotations

import os
import shlex
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from gatecheck.config.hook_def import HookDef
from gatecheck.env import EnvError, EnvManager
from gatecheck.registry import RegistryError
from gatecheck.runner.hook_result import HookResult, HookStatus
from gatecheck.runner.process_runner import ProcessRunner, SubprocessProcessRunner

_FILES_TOKEN = "{files}"


def run_hook(
    hook: HookDef,
    files: Sequence[Path],
    *,
    env_manager: EnvManager | None = None,
    runner: ProcessRunner | None = None,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> HookResult:
    """Execute ``hook`` against ``files`` and return its ``HookResult``.

    Resolves the hook's environment (``env_manager``, default ``EnvManager()``),
    assembles argv (``{files}`` expands in place, else the files are appended), and
    runs it (``runner``, default ``SubprocessProcessRunner``) with ``bin_dir``
    prepended to ``PATH``. Env-resolution errors (``EnvError`` / ``RegistryError``)
    and spawn failures (``OSError``) yield an ``error`` result.
    """
    manager = EnvManager() if env_manager is None else env_manager
    process = SubprocessProcessRunner() if runner is None else runner
    base_env = dict(os.environ if environ is None else environ)

    try:
        resolved = manager.resolve(hook)
    except (EnvError, RegistryError) as exc:
        return HookResult(hook.id, "error", None, str(exc), 0.0)

    argv = _assemble_argv(hook.run, files)
    child_env = {
        **base_env,
        "PATH": os.pathsep.join([str(resolved.bin_dir), base_env.get("PATH", "")]),
    }

    start = time.monotonic()
    try:
        exit_code, output = process.run(argv, env=child_env, cwd=cwd)
    except OSError as exc:
        return HookResult(hook.id, "error", None, f"failed to execute {argv[0]!r}: {exc}", 0.0)
    duration = time.monotonic() - start

    status: HookStatus = "passed" if exit_code == 0 else "failed"
    return HookResult(hook.id, status, exit_code, output, duration)


def _assemble_argv(run: str, files: Sequence[Path]) -> list[str]:
    """Tokenize ``run`` and place the files (``{files}`` in place, else appended)."""
    file_args = [str(f) for f in files]
    argv: list[str] = []
    substituted = False
    for token in shlex.split(run):
        if token == _FILES_TOKEN:
            argv.extend(file_args)
            substituted = True
        else:
            argv.append(token)
    if not substituted:
        argv.extend(file_args)
    return argv
