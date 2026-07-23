"""`gatecheck run` — execute one or more hook groups against the changeset."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from gatecheck.cli._config import resolve_config_path
from gatecheck.config import ConfigError, GatecheckConfig, load_config
from gatecheck.offline import OFFLINE_ENV
from gatecheck.runner import (
    GitError,
    PlanError,
    RunReport,
    SubprocessGitClient,
    build_plan,
    build_report,
    resolve_changeset,
    route_files,
    run_plan,
)
from gatecheck.workspace import WorkspaceError, discover_workspace, run_affected


@click.command(help="Run a hook group (or all hooks) against the current changeset.")
@click.argument("group", required=False)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to check.toml. Default: discovered from the current directory upward.",
)
@click.option("--all-files", is_flag=True, help="Run against every tracked file, not just staged.")
@click.option(
    "--base",
    "base",
    metavar="REF",
    default=None,
    help="Run against files changed since REF (merge-base), instead of the staged set.",
)
@click.option("--affected", is_flag=True, help="Run only on packages affected by the changeset.")
@click.option(
    "--offline",
    is_flag=True,
    help="Never touch the network; a cache miss is a clear error (sets GATECHECK_OFFLINE).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit the run report as JSON.")
@click.pass_context
def run(
    ctx: click.Context,
    group: str | None,
    config_path: Path | None,
    all_files: bool,
    base: str | None,
    affected: bool,
    offline: bool,
    as_json: bool,
) -> None:
    """Resolve the changeset, plan the hooks, execute them, and report."""
    if all_files and base is not None:
        raise click.ClickException("--all-files and --base are mutually exclusive")
    if offline:
        os.environ[OFFLINE_ENV] = "1"

    resolved_config = resolve_config_path(config_path)

    if affected:
        _run_affected(ctx, resolved_config, all_files, base, as_json)
        return

    try:
        config = load_config(resolved_config)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    # Resolve the git context once (base changeset + branch) so the plan's
    # `when` conditions (branch* / files-match) can be evaluated before routing.
    git = SubprocessGitClient()
    try:
        changeset = resolve_changeset([], all_files=all_files, base=base, git=git)
        branch = git.current_branch()
    except GitError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        plan = build_plan(
            config,
            group=group,
            branch=branch,
            changed_files=[f.as_posix() for f in changeset.files],
        )
    except PlanError as exc:
        raise click.ClickException(str(exc)) from exc

    running = [hook for level in plan.levels for hook in level]
    files_by_hook = route_files(running, changeset.files)

    fail_fast = _fail_fast(config, group)
    max_workers = _max_workers(config, group)
    results = run_plan(plan, files_by_hook, fail_fast=fail_fast, max_workers=max_workers)

    report = build_report(plan, results)
    _emit(report, as_json)
    ctx.exit(report.exit_code)


def _emit(report: RunReport, as_json: bool) -> None:
    """Print the report as JSON or the human rendering — nothing else on stdout."""
    click.echo(json.dumps(report.to_dict(), indent=2) if as_json else report.render())


def _fail_fast(config: GatecheckConfig, group: str | None) -> bool:
    """The group's ``fail-fast`` setting; ``False`` for an all-hooks run."""
    if group is None:
        return False
    group_def = config.group.get(group)
    return bool(group_def.fail_fast) if group_def is not None else False


def _max_workers(config: GatecheckConfig, group: str | None) -> int | None:
    """The concurrency cap for this run.

    An all-hooks run (no group) is unbounded (``None`` → rayon's global pool). A
    group runs serially (``1``) unless ``parallel = true``, in which case it is capped
    at the group's ``max-workers``.
    """
    if group is None:
        return None
    group_def = config.group.get(group)
    if group_def is None:
        return None
    if not group_def.parallel:
        return 1
    return group_def.max_workers


def _run_affected(
    ctx: click.Context,
    config_path: Path,
    all_files: bool,
    base: str | None = None,
    as_json: bool = False,
) -> None:
    """Run only the hooks of packages affected by the changeset (monorepo mode)."""
    try:
        workspace = discover_workspace(config_path)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        changeset = resolve_changeset([], all_files=all_files, base=base)
    except GitError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        results = run_affected(workspace, changeset.files)
    except (WorkspaceError, PlanError) as exc:
        raise click.ClickException(str(exc)) from exc

    report = RunReport(results=results, skipped=(), not_run=())
    _emit(report, as_json)
    ctx.exit(report.exit_code)
