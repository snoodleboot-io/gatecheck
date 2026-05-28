"""`gatecheck migrate` — convert a .pre-commit-config.yaml into check.toml."""

from __future__ import annotations

from pathlib import Path

import click


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
    raise NotImplementedError("gatecheck migrate — scaffolding only")
