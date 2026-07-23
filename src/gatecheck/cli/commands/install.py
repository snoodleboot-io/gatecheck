"""`gatecheck install` — install git hooks into the current repository."""

from __future__ import annotations

from pathlib import Path

import click

from gatecheck.cli._config import resolve_config_path
from gatecheck.config import ConfigError, load_config
from gatecheck.install import InstallOutcome, has_on_event_groups, install_hooks
from gatecheck.runner import GitError


@click.command(help="Install gatecheck as the project's git hook runner.")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to check.toml. Default: discovered from the current directory upward.",
)
def install(config_path: Path | None) -> None:
    """Write git hook scripts for each group that declares an ``on-event``."""
    try:
        config = load_config(resolve_config_path(config_path))
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    if not has_on_event_groups(config):
        click.echo("Nothing to install — no group declares an 'on-event'.")
        return

    try:
        outcomes = install_hooks(config)
    except GitError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(_render(outcomes))


def _render(outcomes: tuple[InstallOutcome, ...]) -> str:
    """Render one line per git hook installed or skipped."""
    lines: list[str] = []
    for outcome in outcomes:
        groups = ", ".join(outcome.groups)
        if outcome.status == "installed":
            lines.append(f"installed  {outcome.git_hook}  ({groups})")
        else:
            lines.append(f"skipped    {outcome.git_hook}  — {outcome.detail}")
    return "\n".join(lines)
