"""Offline-mode signal (STY-0034 / GAT-36).

A single environment variable, ``HOOKSMITH_OFFLINE``, marks a run as air-gapped: no
network is attempted anywhere. It is read wherever a network decision is made — the
``EnvManager`` (pypi pinning + uv build) and the planner (the ``requires-network``
hook marker). ``hooksmith run --offline`` sets it for the process; the variable alone
works too.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

OFFLINE_ENV = "HOOKSMITH_OFFLINE"


def is_offline(environ: Mapping[str, str] | None = None) -> bool:
    """True when ``HOOKSMITH_OFFLINE`` is set to a non-empty value in ``environ``."""
    env = os.environ if environ is None else environ
    return bool(env.get(OFFLINE_ENV))
