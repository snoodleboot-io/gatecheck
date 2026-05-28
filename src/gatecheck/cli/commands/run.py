"""`gatecheck run` — execute one or more hook groups."""

from __future__ import annotations

import click


@click.command(help="Run a hook group (or all groups) against the current changeset.")
@click.argument("group", required=False)
@click.option("--all-files", is_flag=True, help="Run against every tracked file, not just staged.")
@click.option("--affected", is_flag=True, help="Run only on packages affected by the changeset.")
def run(group: str | None, all_files: bool, affected: bool) -> None:
    raise NotImplementedError("gatecheck run — scaffolding only")
