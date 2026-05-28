"""`gatecheck cache` — inspect and manage the hook cache."""

from __future__ import annotations

import click


@click.group(help="Inspect and manage the hook cache.")
def cache() -> None:
    """Cache command group."""


@cache.command(help="Explain why a hook hit or missed the cache.")
@click.argument("hook")
def why(hook: str) -> None:
    raise NotImplementedError("gatecheck cache why — scaffolding only")


@cache.command(help="Remove cached results.")
@click.option("--all", "clear_all", is_flag=True, help="Clear every cache entry.")
def clear(clear_all: bool) -> None:
    raise NotImplementedError("gatecheck cache clear — scaffolding only")
