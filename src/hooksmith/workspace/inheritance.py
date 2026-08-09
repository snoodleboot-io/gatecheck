"""Config inheritance — resolve a package's effective config (STY-0017 / GAT-22).

Layers a package's ``check.toml`` over the workspace root per its ``inherit`` mode
(``merge`` / ``override`` / ``none``). Pure — no filesystem, no I/O.
"""

from __future__ import annotations

from hooksmith.config import HooksmithConfig
from hooksmith.config.hook_def import HookDef
from hooksmith.config.workspace_spec import InheritMode


def effective_config(root: HooksmithConfig, package: HooksmithConfig) -> HooksmithConfig:
    """Resolve ``package``'s effective config against the workspace ``root``.

    The mode is the package's ``[package].inherit`` when set, else the workspace's
    ``[workspace].inherit`` (default ``merge``). ``merge`` layers the package over the
    root (hooks by id, groups by name, sources fall back to the root); ``override`` and
    ``none`` ignore the root and use the package's own config. The result carries the
    package's ``[package]`` table and no ``[workspace]``.
    """
    mode = _resolve_mode(root, package)
    if mode == "merge":
        hooks = _merge_hooks(root.hook, package.hook)
        groups = {**root.group, **package.group}
        sources = package.sources if package.sources is not None else root.sources
    else:  # "override" / "none" — the package stands alone.
        hooks = list(package.hook)
        groups = dict(package.group)
        sources = package.sources
    return HooksmithConfig(hook=hooks, group=groups, sources=sources, package=package.package)


def _resolve_mode(root: HooksmithConfig, package: HooksmithConfig) -> InheritMode:
    """The package's inherit mode: its own override, else the workspace default."""
    if package.package is not None and package.package.inherit is not None:
        return package.package.inherit
    return root.workspace.inherit if root.workspace is not None else "merge"


def _merge_hooks(root_hooks: list[HookDef], package_hooks: list[HookDef]) -> list[HookDef]:
    """Layer ``package_hooks`` over ``root_hooks`` by id (root order kept; new appended)."""
    order = [hook.id for hook in root_hooks]
    merged = {hook.id: hook for hook in root_hooks}
    for hook in package_hooks:
        if hook.id not in merged:
            order.append(hook.id)
        merged[hook.id] = hook
    return [merged[hook_id] for hook_id in order]
