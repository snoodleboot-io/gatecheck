"""`gatecheck migrate` — convert a .pre-commit-config.yaml into check.toml."""

from __future__ import annotations

from pathlib import Path

import click

from gatecheck.config import dump_config
from gatecheck.migration import MigrationError, map_precommit, parse_precommit_config


@click.command(help="Read .pre-commit-config.yaml and write a check.toml.")
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path(".pre-commit-config.yaml"),
    show_default=True,
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("check.toml"),
    show_default=True,
)
def migrate(input_path: Path, output_path: Path) -> None:
    """Translate a pre-commit config into a gatecheck check.toml (best-effort)."""
    try:
        precommit = parse_precommit_config(input_path)
    except MigrationError as exc:
        raise click.ClickException(str(exc)) from exc

    config, warnings = map_precommit(precommit)
    dump_config(config, output_path)

    click.echo(f"Wrote {len(config.hook)} hook(s) to {output_path}")
    for warning in warnings:
        click.echo(f"warning: {warning}")
