"""Serialise a GatecheckConfig to a check.toml file (BUILD-0003-ARCH)."""

from __future__ import annotations

from pathlib import Path

import tomlkit
import tomlkit.items

from gatecheck.config.gatecheck_config import GatecheckConfig


def dump_config(config: GatecheckConfig, path: Path) -> None:
    """Write *config* to *path* as a valid check.toml."""
    data = config.model_dump(by_alias=True, exclude_none=True, exclude_defaults=True)
    doc = _build_document(data)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def _build_document(data: dict[str, object]) -> tomlkit.TOMLDocument:
    doc = tomlkit.document()
    sources_data = data.get("sources")
    if isinstance(sources_data, dict) and sources_data:
        src_table = tomlkit.table()
        for key, value in sources_data.items():
            src_table.add(key, value)
        doc.add("sources", src_table)
    hook_list = data.get("hook")
    if isinstance(hook_list, list) and hook_list:
        doc.add("hook", _build_hook_aot(hook_list))
    group_dict = data.get("group")
    if isinstance(group_dict, dict) and group_dict:
        doc.add("group", _build_group_table(group_dict))
    return doc


def _build_hook_aot(hook_list: list[object]) -> tomlkit.items.AoT:
    hooks_aot = tomlkit.aot()
    for hook_data in hook_list:
        if not isinstance(hook_data, dict):
            continue
        t = tomlkit.table()
        for key, value in hook_data.items():
            if key == "when" and isinstance(value, dict):
                t.add(key, _build_inline_table(value))
            else:
                t.add(key, value)
        hooks_aot.append(t)
    return hooks_aot


def _build_group_table(group_dict: dict[str, object]) -> tomlkit.items.Table:
    group_super = tomlkit.table(is_super_table=True)
    for name, gdef_data in group_dict.items():
        if not isinstance(gdef_data, dict):
            continue
        gt = tomlkit.table()
        for key, value in gdef_data.items():
            gt.add(key, value)
        group_super.add(name, gt)
    return group_super


def _build_inline_table(when_data: dict[str, object]) -> tomlkit.items.InlineTable:
    wt = tomlkit.inline_table()
    for key, value in when_data.items():
        wt.append(key, value)
    return wt
