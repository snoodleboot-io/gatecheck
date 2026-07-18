"""Package graph + the affected set for ``gatecheck run --affected`` (STY-0018 / GAT-24).

Builds the package dependency graph from ``[package].depends-on``, computes which
packages a changeset affects (directly-changed plus their transitive dependents), and
runs each affected package's effective hooks through the engine.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from gatecheck.runner import HookResult, build_plan, route_files, run_plan
from gatecheck.workspace.inheritance import effective_config
from gatecheck.workspace.loader import DiscoveredPackage, Workspace


class WorkspaceError(ValueError):
    """Raised for an unknown package dependency or a dependency cycle."""


def affected_packages(
    workspace: Workspace, changed_files: Sequence[Path]
) -> tuple[DiscoveredPackage, ...]:
    """Return the packages a changeset affects, in workspace-declared order.

    A package is affected when its directory contains a changed file, or when it
    (transitively) depends on such a package. A changed file that lives under **no**
    package directory is treated as a shared/root change (root ``check.toml``, a
    top-level lockfile, CI config, …) and conservatively marks **every** package
    affected. Raises ``WorkspaceError`` for a ``depends-on`` naming an unknown package
    or forming a cycle.
    """
    by_name = {package.name: package for package in workspace.packages}
    deps = _validated_deps(workspace, by_name)

    if _has_root_change(workspace, changed_files):
        directly = set(by_name)  # a shared/root file affects all packages
    else:
        directly = _directly_changed(workspace, changed_files)

    dependents: dict[str, list[str]] = {name: [] for name in by_name}
    for name, dep_names in deps.items():
        for dep in dep_names:
            dependents[dep].append(name)

    affected: set[str] = set()
    stack = list(directly)
    while stack:
        current = stack.pop()
        if current in affected:
            continue
        affected.add(current)
        stack.extend(dependents[current])

    return tuple(package for package in workspace.packages if package.name in affected)


def run_affected(workspace: Workspace, changed_files: Sequence[Path]) -> tuple[HookResult, ...]:
    """Run each affected package's effective hooks; results are prefixed ``<package>:<hook>``."""
    results: list[HookResult] = []
    for package in affected_packages(workspace, changed_files):
        effective = effective_config(workspace.root, package.config)
        plan = build_plan(effective)
        package_rel = package.path.relative_to(workspace.root_dir)
        package_files = [
            Path(f).relative_to(package_rel)
            for f in changed_files
            if _is_under(Path(f), package_rel)
        ]
        running = [hook for level in plan.levels for hook in level]
        files_by_hook = route_files(running, package_files)
        for result in run_plan(plan, files_by_hook, cwd=package.path):
            results.append(_prefixed(package.name, result))
    return tuple(results)


def _directly_changed(workspace: Workspace, changed_files: Sequence[Path]) -> set[str]:
    """Names of packages whose directory contains at least one changed file."""
    changed: set[str] = set()
    for package in workspace.packages:
        package_rel = package.path.relative_to(workspace.root_dir)
        if any(_is_under(Path(f), package_rel) for f in changed_files):
            changed.add(package.name)
    return changed


def _has_root_change(workspace: Workspace, changed_files: Sequence[Path]) -> bool:
    """True when some changed file lives under no package directory (a shared/root file)."""
    package_rels = [package.path.relative_to(workspace.root_dir) for package in workspace.packages]
    return any(not any(_is_under(Path(f), rel) for rel in package_rels) for f in changed_files)


def _validated_deps(
    workspace: Workspace, by_name: dict[str, DiscoveredPackage]
) -> dict[str, list[str]]:
    """Build the ``name -> depends-on`` map, rejecting unknown names and cycles."""
    deps: dict[str, list[str]] = {}
    for package in workspace.packages:
        package_deps = package.config.package.depends_on if package.config.package else []
        for dep in package_deps:
            if dep not in by_name:
                raise WorkspaceError(f"package '{package.name}' depends on unknown package '{dep}'")
        deps[package.name] = list(package_deps)
    _check_acyclic(deps)
    return deps


def _check_acyclic(deps: dict[str, list[str]]) -> None:
    """Raise ``WorkspaceError`` if the dependency graph contains a cycle (DFS coloring)."""
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(name: str) -> None:
        visiting.add(name)
        for dep in deps[name]:
            if dep in visiting:
                raise WorkspaceError(f"dependency cycle involving package '{dep}'")
            if dep not in done:
                visit(dep)
        visiting.discard(name)
        done.add(name)

    for name in deps:
        if name not in done:
            visit(name)


def _is_under(file_path: Path, package_rel: Path) -> bool:
    """True when ``file_path`` (repo-relative) lives inside ``package_rel``."""
    try:
        file_path.relative_to(package_rel)
    except ValueError:
        return False
    return True


def _prefixed(package_name: str, result: HookResult) -> HookResult:
    return HookResult(
        f"{package_name}:{result.hook_id}",
        result.status,
        result.exit_code,
        result.output,
        result.duration,
    )
