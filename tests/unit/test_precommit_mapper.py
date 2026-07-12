"""Unit tests for gatecheck.migration.map_precommit (STY-0020 / GAT-23).

Pure mapping; a round-trip through dump_config/load_config confirms the output is a
valid check.toml. Covers known repos, rev pinning, args, unknown-repo + files
warnings, local → system, and id de-duplication. AAA structure throughout.
"""

from __future__ import annotations

from pathlib import Path

from gatecheck.config import dump_config, load_config
from gatecheck.migration import PreCommitConfig, map_precommit


def _precommit(repos: list[dict[str, object]]) -> PreCommitConfig:
    return PreCommitConfig.model_validate({"repos": repos})


def _by_id(config: object) -> dict[str, object]:
    return {h.id: h for h in config.hook}  # type: ignore[attr-defined]


def test_known_repo_maps_to_pypi_with_run_command() -> None:
    # Arrange
    precommit = _precommit(
        [
            {
                "repo": "https://github.com/astral-sh/ruff-pre-commit",
                "rev": "v0.4.0",
                "hooks": [{"id": "ruff", "args": ["--fix"]}, {"id": "ruff-format"}],
            }
        ]
    )
    # Act
    config, warnings = map_precommit(precommit)
    # Assert
    hooks = _by_id(config)
    assert hooks["ruff"].from_ == "pypi:ruff==0.4.0"
    assert hooks["ruff"].run == "ruff check --fix"
    assert hooks["ruff-format"].run == "ruff format"
    assert warnings == []


def test_unpinnable_rev_warns() -> None:
    # Arrange — a non-version rev (a git sha)
    precommit = _precommit(
        [{"repo": "https://github.com/psf/black", "rev": "abc123", "hooks": [{"id": "black"}]}]
    )
    # Act
    config, warnings = map_precommit(precommit)
    # Assert
    assert _by_id(config)["black"].from_ == "pypi:black"
    assert any("could not be pinned" in w for w in warnings)


def test_unknown_repo_is_best_effort_with_warning() -> None:
    # Arrange
    precommit = _precommit(
        [
            {
                "repo": "https://github.com/acme/custom-linter",
                "hooks": [{"id": "custom", "entry": "custom-lint"}],
            }
        ]
    )
    # Act
    config, warnings = map_precommit(precommit)
    # Assert
    assert _by_id(config)["custom"].from_ == "pypi:custom-linter"
    assert _by_id(config)["custom"].run == "custom-lint"
    assert any("best-effort" in w for w in warnings)


def test_local_repo_maps_to_system() -> None:
    # Arrange
    precommit = _precommit(
        [
            {
                "repo": "local",
                "hooks": [{"id": "my-check", "entry": "make lint", "language": "system"}],
            }
        ]
    )
    # Act
    config, _ = map_precommit(precommit)
    # Assert
    assert _by_id(config)["my-check"].from_ == "system"
    assert _by_id(config)["my-check"].run == "make lint"


def test_files_pattern_emits_warning() -> None:
    # Arrange
    precommit = _precommit(
        [{"repo": "https://github.com/psf/black", "hooks": [{"id": "black", "files": r"\.py$"}]}]
    )
    # Act
    _, warnings = map_precommit(precommit)
    # Assert
    assert any("files" in w and "regex" in w for w in warnings)


def test_duplicate_ids_are_deduplicated() -> None:
    # Arrange — two repos both provide a hook id "black"
    precommit = _precommit(
        [
            {"repo": "https://github.com/psf/black", "hooks": [{"id": "black"}]},
            {"repo": "https://github.com/other/black", "hooks": [{"id": "black"}]},
        ]
    )
    # Act
    config, _ = map_precommit(precommit)
    # Assert
    assert sorted(h.id for h in config.hook) == ["black", "black-2"]


def test_output_round_trips_through_config_loader(tmp_path: Path) -> None:
    # Arrange
    precommit = _precommit(
        [
            {
                "repo": "https://github.com/astral-sh/ruff-pre-commit",
                "rev": "v0.4.0",
                "hooks": [{"id": "ruff"}],
            }
        ]
    )
    config, _ = map_precommit(precommit)
    out = tmp_path / "check.toml"
    # Act — dump then load
    dump_config(config, out)
    reloaded = load_config(out)
    # Assert
    assert [h.id for h in reloaded.hook] == ["ruff"]
    assert reloaded.hook[0].from_ == "pypi:ruff==0.4.0"
