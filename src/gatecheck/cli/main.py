"""Root click group for the gatecheck CLI."""

from __future__ import annotations

import click

from gatecheck import __version__
from gatecheck.cli.commands import cache, install, migrate, run, sync


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    help="gatecheck — pre-commit, done right.",
)
@click.version_option(__version__, prog_name="gatecheck")
def main() -> None:
    """Root command group."""


main.add_command(install.install)
main.add_command(sync.sync)
main.add_command(run.run)
main.add_command(cache.cache)
main.add_command(migrate.migrate)
