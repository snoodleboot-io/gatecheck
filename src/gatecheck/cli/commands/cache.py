"""`gatecheck cache` — inspect and manage the hook cache."""

from __future__ import annotations

import json
from pathlib import Path

import click

from gatecheck.config import ConfigError, load_config
from gatecheck.env import EnvError, EnvManager
from gatecheck.registry import RegistryError


@click.group(help="Inspect and manage the hook cache.")
def cache() -> None:
    """Cache command group."""


@cache.command(help="Explain why a hook hit or missed the cache.")
@click.argument("hook")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path("check.toml"),
    show_default=True,
    help="Path to check.toml.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit the explanation as JSON.")
def why(hook: str, config_path: Path, as_json: bool) -> None:
    """Explain hook ``HOOK``'s cache key and hit/miss status."""
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    hook_def = next((h for h in config.hook if h.id == hook), None)
    if hook_def is None:
        available = ", ".join(h.id for h in config.hook) or "(none)"
        raise click.ClickException(
            f"no hook with id '{hook}' in {config_path} (available: {available})"
        )

    manager = EnvManager(sources=config.sources)
    try:
        explanation = manager.explain(hook_def)
    except (EnvError, RegistryError) as exc:
        raise click.ClickException(str(exc)) from exc

    if as_json:
        click.echo(json.dumps(explanation.to_dict(), indent=2))
    else:
        click.echo(explanation.render())


@cache.command(help="Remove cached results.")
@click.option("--all", "clear_all", is_flag=True, help="Clear every cache entry.")
def clear(clear_all: bool) -> None:
    raise NotImplementedError("gatecheck cache clear — scaffolding only")
