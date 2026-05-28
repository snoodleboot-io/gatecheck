"""`gatecheck install` — install git hooks into the current repository."""

from __future__ import annotations

import click


@click.command(help="Install gatecheck as the project's git hook runner.")
def install() -> None:
    raise NotImplementedError("gatecheck install — scaffolding only")
