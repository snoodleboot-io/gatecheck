"""`gatecheck cache` — inspect and manage the hook cache."""

from __future__ import annotations

import json
from pathlib import Path

import click

from gatecheck.cli._config import resolve_config_path
from gatecheck.config import ConfigError, load_config
from gatecheck.env import EnvError, EnvManager, clear_cache
from gatecheck.env.env_cache import default_cache_root
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
    default=None,
    help="Path to check.toml. Default: discovered from the current directory upward.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit the explanation as JSON.")
def why(hook: str, config_path: Path | None, as_json: bool) -> None:
    """Explain hook ``HOOK``'s cache key and hit/miss status."""
    resolved_config = resolve_config_path(config_path)
    try:
        config = load_config(resolved_config)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    hook_def = next((h for h in config.hook if h.id == hook), None)
    if hook_def is None:
        available = ", ".join(h.id for h in config.hook) or "(none)"
        raise click.ClickException(
            f"no hook with id '{hook}' in {resolved_config} (available: {available})"
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


@cache.command(help="Remove cached hook environments.")
@click.option(
    "--all",
    "clear_all",
    is_flag=True,
    help="Also remove the bootstrapped uv, not just cached environments.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Report what would be removed without deleting anything.",
)
def clear(clear_all: bool, dry_run: bool) -> None:
    """Remove cached hook environments from the user cache."""
    cache_root = default_cache_root()
    outcome = clear_cache(cache_root, include_uv=clear_all, dry_run=dry_run)

    verb = "Would remove" if dry_run else "Removed"
    plural = "" if outcome.removed == 1 else "s"
    click.echo(
        f"{verb} {outcome.removed} cached environment{plural}, "
        f"freeing {_human_bytes(outcome.freed_bytes)}."
    )


def _human_bytes(size: int) -> str:
    """Render ``size`` bytes with a binary unit (e.g. ``1.5 MiB``)."""
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            precision = 0 if unit == "B" else 1
            return f"{value:.{precision}f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TiB"  # pragma: no cover — loop always returns first
