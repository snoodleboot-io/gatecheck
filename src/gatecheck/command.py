"""Command tokenization — split a hook's ``run`` into argv (STY-0025 / GAT-27).

One shared tokenizer so the tool name (``EnvManager._derive_tool``) and the executed
argv (``executor._assemble_argv``) are split the same way. POSIX uses ``shlex``'s
POSIX mode; Windows uses non-POSIX mode so backslash paths (``C:\\tools\\x``) survive.
"""

from __future__ import annotations

import shlex

from gatecheck import venv


def tokenize(run: str) -> list[str]:
    """Split ``run`` into tokens for the current platform.

    Raises ``ValueError`` (from ``shlex``) on unbalanced quotes, on both platforms.
    """
    if venv.is_windows():
        return shlex.split(run, posix=False)
    return shlex.split(run)
