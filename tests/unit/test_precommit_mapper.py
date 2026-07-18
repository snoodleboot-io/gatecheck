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


def test_simple_files_regex_maps_to_glob() -> None:
    # Arrange — a single anchored extension is safely mappable
    precommit = _precommit(
        [{"repo": "https://github.com/psf/black", "hooks": [{"id": "black", "files": r"\.py$"}]}]
    )
    # Act
    config, warnings = map_precommit(precommit)
    # Assert — translated to a glob, no warning
    assert _by_id(config)["black"].files == "*.py"
    assert warnings == []


def test_complex_files_regex_still_warns() -> None:
    # Arrange — an alternation is not safely a single glob
    precommit = _precommit(
        [
            {
                "repo": "https://github.com/psf/black",
                "hooks": [{"id": "black", "files": r"\.(py|pyi)$"}],
            }
        ]
    )
    # Act
    config, warnings = map_precommit(precommit)
    # Assert — left untranslated with a warning
    assert _by_id(config)["black"].files is None
    assert any("files" in w and "regex" in w for w in warnings)


def test_pass_filenames_false_maps_to_pass_files_false() -> None:
    # Arrange
    precommit = _precommit(
        [
            {
                "repo": "https://github.com/psf/black",
                "hooks": [{"id": "black", "pass_filenames": False}],
            }
        ]
    )
    # Act
    config, _ = map_precommit(precommit)
    # Assert
    assert _by_id(config)["black"].pass_files is False


def test_pass_filenames_true_is_default() -> None:
    # Arrange
    precommit = _precommit(
        [
            {
                "repo": "https://github.com/psf/black",
                "hooks": [{"id": "black", "pass_filenames": True}],
            }
        ]
    )
    # Act
    config, _ = map_precommit(precommit)
    # Assert — the gatecheck default (True) is retained
    assert _by_id(config)["black"].pass_files is True


def test_codespell_maps_to_pypi() -> None:
    # Arrange
    precommit = _precommit(
        [
            {
                "repo": "https://github.com/codespell-project/codespell",
                "rev": "v2.3.0",
                "hooks": [{"id": "codespell"}],
            }
        ]
    )
    # Act
    config, warnings = map_precommit(precommit)
    # Assert
    assert _by_id(config)["codespell"].from_ == "pypi:codespell==2.3.0"
    assert _by_id(config)["codespell"].run == "codespell"
    assert warnings == []


def test_shellcheck_py_runs_shellcheck() -> None:
    # Arrange — the pypi package name differs from the run command
    precommit = _precommit(
        [
            {
                "repo": "https://github.com/shellcheck-py/shellcheck-py",
                "rev": "v0.10.0.1",
                "hooks": [{"id": "shellcheck"}],
            }
        ]
    )
    # Act
    config, _ = map_precommit(precommit)
    # Assert
    assert _by_id(config)["shellcheck"].from_ == "pypi:shellcheck-py==0.10.0.1"
    assert _by_id(config)["shellcheck"].run == "shellcheck"


def test_prettier_mirror_maps_to_system_with_warning() -> None:
    # Arrange — a node tool gatecheck cannot source from PyPI
    precommit = _precommit(
        [
            {
                "repo": "https://github.com/pre-commit/mirrors-prettier",
                "rev": "v3.1.0",
                "hooks": [{"id": "prettier"}],
            }
        ]
    )
    # Act
    config, warnings = map_precommit(precommit)
    # Assert — system source + a PATH warning
    assert _by_id(config)["prettier"].from_ == "system"
    assert _by_id(config)["prettier"].run == "prettier"
    assert any("system tool 'prettier'" in w for w in warnings)


def test_pre_commit_hooks_uses_hook_id_as_command() -> None:
    # Arrange — the multi-hook pre-commit-hooks repo: each hook is its own script
    precommit = _precommit(
        [
            {
                "repo": "https://github.com/pre-commit/pre-commit-hooks",
                "rev": "v4.6.0",
                "hooks": [{"id": "end-of-file-fixer"}, {"id": "check-yaml"}],
            }
        ]
    )
    # Act
    config, _ = map_precommit(precommit)
    # Assert — same package, per-hook commands
    hooks = _by_id(config)
    assert hooks["end-of-file-fixer"].from_ == "pypi:pre-commit-hooks==4.6.0"
    assert hooks["end-of-file-fixer"].run == "end-of-file-fixer"
    assert hooks["check-yaml"].run == "check-yaml"


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
