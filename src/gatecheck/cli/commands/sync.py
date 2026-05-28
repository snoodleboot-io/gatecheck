"""`gatecheck sync` — create/update hook environments to match check.toml."""

from __future__ import annotations

import click


@click.command(help="Create or update the per-hook environments described in check.toml.")
def sync() -> None:
    raise NotImplementedError("gatecheck sync — scaffolding only")
