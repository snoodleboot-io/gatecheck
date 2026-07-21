"""Integration tests for `gatecheck run` (STY-0015 / GAT-17).

End-to-end via click's ``CliRunner`` in an isolated filesystem with a real git repo
and real ``system`` hooks (``echo`` / ``false``). Marked ``integration`` and skipped
when the required tools are absent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from gatecheck.cli.main import main

pytestmark = pytest.mark.integration

_TOOLS_PRESENT = all(shutil.which(t) is not None for t in ("git", "echo", "false"))
_skip = pytest.mark.skipif(not _TOOLS_PRESENT, reason="git/echo/false not all on PATH")


def _init_repo() -> None:
    subprocess.run(["git", "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], check=True, capture_output=True)


def _write(name: str, body: str) -> None:
    Path(name).write_text(body, encoding="utf-8")


@_skip
def test_run_all_hooks_pass_exits_zero() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        _write(
            "check.toml",
            '[[hook]]\nid = "say"\nfrom = "system"\nrun = "echo hi"\npass-files = false\n',
        )
        # Act
        result = runner.invoke(main, ["run"])
        # Assert
        assert result.exit_code == 0, result.output
        assert "ok" in result.output
        assert "1 passed" in result.output


@_skip
def test_run_offline_flag_runs_system_hooks() -> None:
    # Arrange — system hooks need no network, so --offline is a no-op for them.
    runner = CliRunner()
    try:
        with runner.isolated_filesystem():
            _init_repo()
            _write(
                "check.toml",
                '[[hook]]\nid = "say"\nfrom = "system"\nrun = "echo hi"\npass-files = false\n',
            )
            # Act — the flag is accepted and the run still passes
            result = runner.invoke(main, ["run", "--offline"])
            # Assert
            assert result.exit_code == 0, result.output
            assert "1 passed" in result.output
    finally:
        # `run --offline` sets GATECHECK_OFFLINE in the process env; clear the mutation
        # so it cannot leak into later in-process tests.
        os.environ.pop("GATECHECK_OFFLINE", None)


@_skip
def test_run_json_emits_parseable_report_only() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        _write(
            "check.toml",
            '[[hook]]\nid = "say"\nfrom = "system"\nrun = "echo hi"\npass-files = false\n',
        )
        # Act
        result = runner.invoke(main, ["run", "--json"])
        # Assert — stdout is the JSON document and nothing else (pipes into jq)
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["summary"]["passed"] == 1
        assert payload["exit_code"] == 0
        assert payload["results"][0]["hook_id"] == "say"
        assert "ok  " not in result.output  # the human rendering must not leak


@_skip
def test_run_json_still_exits_nonzero_on_failure() -> None:
    # Arrange — a hook that fails
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        _write(
            "check.toml",
            '[[hook]]\nid = "nope"\nfrom = "system"\nrun = "false"\npass-files = false\n',
        )
        # Act
        result = runner.invoke(main, ["run", "--json"])
        # Assert — still usable as a gate, and still valid JSON
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["exit_code"] == 1
        assert payload["summary"]["failed"] == 1


@_skip
def test_run_base_and_all_files_are_mutually_exclusive() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        _write(
            "check.toml",
            '[[hook]]\nid = "say"\nfrom = "system"\nrun = "echo hi"\npass-files = false\n',
        )
        # Act
        result = runner.invoke(main, ["run", "--all-files", "--base", "main"])
        # Assert — a clean error, not a silent precedence rule
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output


@_skip
def test_run_base_with_unknown_ref_errors_clearly() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        _write(
            "check.toml",
            '[[hook]]\nid = "say"\nfrom = "system"\nrun = "echo hi"\npass-files = false\n',
        )
        # Act — a ref that does not exist must not resolve to an empty, passing run
        result = runner.invoke(main, ["run", "--base", "no-such-ref"])
        # Assert
        assert result.exit_code != 0
        assert "Traceback" not in result.output


@_skip
def test_run_base_selects_files_changed_since_the_ref() -> None:
    # Arrange — a commit on main, then a branch that changes one file
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        _write("base.py", "x = 1\n")
        _write(
            "check.toml",
            '[[hook]]\nid = "show"\nfrom = "system"\nrun = "echo"\nfiles = "*.py"\n',
        )
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "base"], check=True, capture_output=True)
        # The default branch name varies by git config, so read it rather than assume.
        base_ref = subprocess.run(
            ["git", "branch", "--show-current"], check=True, capture_output=True, text=True
        ).stdout.strip()
        subprocess.run(["git", "checkout", "-qb", "feature"], check=True, capture_output=True)
        _write("added.py", "y = 2\n")
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "add"], check=True, capture_output=True)

        # Act — nothing is staged, so only --base can find the change
        result = runner.invoke(main, ["run", "--base", base_ref])

        # Assert — the run resolved against the ref and completed. (Which files were
        # selected is asserted precisely against real git in
        # test_changeset_base_real_git.py; the report only echoes hook output on failure.)
        assert result.exit_code == 0, result.output
        assert "1 passed" in result.output


@_skip
def test_run_failing_hook_exits_one_and_shows_output() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        _write(
            "check.toml",
            '[[hook]]\nid = "nope"\nfrom = "system"\nrun = "false"\npass-files = false\n',
        )
        # Act
        result = runner.invoke(main, ["run"])
        # Assert
        assert result.exit_code == 1, result.output
        assert "FAIL  nope" in result.output
        assert "1 failed" in result.output


@_skip
def test_run_unknown_group_errors() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        _write("check.toml", '[[hook]]\nid = "say"\nfrom = "system"\nrun = "echo hi"\n')
        # Act
        result = runner.invoke(main, ["run", "ghost"])
        # Assert
        assert result.exit_code != 0
        assert "unknown group 'ghost'" in result.output
