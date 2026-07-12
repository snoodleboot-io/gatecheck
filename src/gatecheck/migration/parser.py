"""parse_precommit_config — read a .pre-commit-config.yaml into a typed model (STY-0019 / GAT-19).

Pure parse + validate: read the file, ``yaml.safe_load`` it, and validate against the
``PreCommitConfig`` schema. Any failure surfaces as a path-tagged ``MigrationError``.
"""

from __future__ import annotations

from pathlib import Path

import pydantic
import yaml

from gatecheck.migration.migration_error import MigrationError
from gatecheck.migration.precommit_config import PreCommitConfig


def parse_precommit_config(path: Path) -> PreCommitConfig:
    """Parse and validate ``path`` as a ``.pre-commit-config.yaml``.

    Raises ``MigrationError`` if the file is unreadable, is not valid YAML, does not
    contain a top-level mapping, or fails schema validation.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MigrationError(f"{path}: cannot read file: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MigrationError(f"{path}: invalid YAML: {exc}") from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise MigrationError(f"{path}: expected a mapping at the top level of the config")

    try:
        return PreCommitConfig.model_validate(data)
    except pydantic.ValidationError as exc:
        raise MigrationError(f"{path}: {exc}") from exc
