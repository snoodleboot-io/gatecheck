"""Load and validate a check.toml into a typed GatecheckConfig (BUILD-0001-ARCH §4, BUILD-0002-ARCH §5)."""

from __future__ import annotations

import stat
import tomllib
from pathlib import Path

import pydantic
import tomlkit

from gatecheck.config._error_translator import (
    _locate_validation_errors,
    _parse_toml_error,
)
from gatecheck.config.config_error import ConfigError
from gatecheck.config.gatecheck_config import GatecheckConfig


def load_config(path: Path) -> GatecheckConfig:
    """Parse `path` (a check.toml) and return a validated GatecheckConfig."""
    st = path.stat()
    if not stat.S_ISREG(st.st_mode):
        raise OSError(f"check.toml must be a regular file, got: {path}")
    # 1 MiB cap — real configs are < 10 KiB; this bounds parse-time DoS surface.
    if st.st_size > 1 << 20:
        raise OSError(f"check.toml exceeds 1 MiB (was {st.st_size} bytes): {path}")
    source = path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(source)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(path, [_parse_toml_error(e)]) from e
    try:
        return GatecheckConfig.model_validate(data)
    except pydantic.ValidationError as e:
        toml_doc = tomlkit.parse(source)
        raise ConfigError(path, _locate_validation_errors(e, source, toml_doc)) from e
