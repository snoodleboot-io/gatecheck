"""`gatecheck sync` — create/update hook environments to match check.toml."""

from __future__ import annotations

from pathlib import Path

import click

from gatecheck.config import ConfigError, load_config
from gatecheck.env import SyncOutcome, sync_environments

_LABEL = {"built": "built ", "cached": "cached", "ready": "ready ", "error": "ERROR "}


@click.command(help="Create or update the per-hook environments described in check.toml.")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path("check.toml"),
    show_default=True,
    help="Path to check.toml.",
)
@click.pass_context
def sync(ctx: click.Context, config_path: Path) -> None:
    """Resolve every hook's environment ahead of a run."""
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    outcomes = sync_environments(config)
    click.echo(_render(outcomes))
    ctx.exit(1 if any(o.status == "error" for o in outcomes) else 0)


def _render(outcomes: tuple[SyncOutcome, ...]) -> str:
    """Render the per-hook sync report ending in a one-line summary."""
    lines: list[str] = []
    for outcome in outcomes:
        lines.append(f"{_LABEL[outcome.status]}  {outcome.hook_id}")
        if outcome.status == "error" and outcome.detail:
            lines.append(f"        {outcome.detail}")
    errors = sum(1 for o in outcomes if o.status == "error")
    lines.append("")
    lines.append(f"{len(outcomes) - errors} ready, {errors} error")
    return "\n".join(lines)
