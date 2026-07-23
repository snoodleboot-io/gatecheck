"""Load and validate a check.toml into a typed GatecheckConfig (BUILD-0001-ARCH §4, BUILD-0002-ARCH §5)."""

from __future__ import annotations

import stat
import tomllib
from pathlib import Path

import pydantic
import tomlkit

from gatecheck.config._error_translator import (
    _locate_source_spec_errors,
    _locate_validation_errors,
    _parse_toml_error,
)
from gatecheck.config.config_error import ConfigError
from gatecheck.config.gatecheck_config import GatecheckConfig


def load_config(path: Path) -> GatecheckConfig:
    """Parse `path` and return a validated GatecheckConfig.

    A ``check.toml`` is validated as the whole document. A ``pyproject.toml`` is
    validated from its ``[tool.gatecheck]`` table; error locations are anchored into
    that table so ``path:line:col`` stays accurate in either file.
    """
    st = path.stat()
    if not stat.S_ISREG(st.st_mode):
        raise OSError(f"config must be a regular file, got: {path}")
    # 1 MiB cap — real configs are < 10 KiB; this bounds parse-time DoS surface.
    if st.st_size > 1 << 20:
        raise OSError(f"config exceeds 1 MiB (was {st.st_size} bytes): {path}")
    source = path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(source)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(path, [_parse_toml_error(e)]) from e

    if path.name == "pyproject.toml":
        data, prefix = _extract_pyproject_table(data, path)
    else:
        prefix = ""

    try:
        config = GatecheckConfig.model_validate(data)
    except pydantic.ValidationError as e:
        toml_doc = tomlkit.parse(source)
        raise ConfigError(path, _locate_validation_errors(e, source, toml_doc, prefix)) from e
    spec_errors = _locate_source_spec_errors(config, source, prefix)
    if spec_errors:
        raise ConfigError(path, spec_errors)
    return config


def _extract_pyproject_table(data: dict[str, object], path: Path) -> tuple[dict[str, object], str]:
    """Return the ``[tool.gatecheck]`` sub-table and its source prefix, or raise ConfigError.

    A ``pyproject.toml`` with no ``[tool.gatecheck]`` is a user error worth naming
    clearly, not a silent empty config.
    """
    tool = data.get("tool")
    table = tool.get("gatecheck") if isinstance(tool, dict) else None
    if not isinstance(table, dict):
        raise ConfigError(path, [(1, 1, "no [tool.gatecheck] table in pyproject.toml")])
    return table, "tool.gatecheck"
