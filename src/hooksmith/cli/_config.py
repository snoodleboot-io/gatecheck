"""Shared config-path resolution for the CLI (GAT-48).

Every command that reads configuration accepts an optional ``--config PATH``. When it
is omitted, the config is discovered by walking up from the working directory (like
ruff, pre-commit, and friends). This helper centralizes that so the behaviour — and
the not-found error — is identical across ``run`` / ``sync`` / ``install`` / ``cache``.
"""

from __future__ import annotations

from pathlib import Path

import click

from hooksmith.config import discover_config


def resolve_config_path(config_path: Path | None) -> Path:
    """Return the explicit ``--config`` path, or discover one from the CWD.

    Raises ``click.ClickException`` when nothing is given and no config is found in the
    working directory or any parent.
    """
    if config_path is not None:
        return config_path
    found = discover_config(Path.cwd())
    if found is None:
        raise click.ClickException(
            "no check.toml found in this directory or any parent "
            "(and no [tool.hooksmith] table in a pyproject.toml). "
            "Create a check.toml, or pass --config PATH."
        )
    return found
