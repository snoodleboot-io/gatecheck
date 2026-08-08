"""Integration tests for `hooksmith run` (STY-0015 / GAT-17).

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

from hooksmith.cli.main import main

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
        # `run --offline` sets HOOKSMITH_OFFLINE in the process env; clear the mutation
        # so it cannot leak into later in-process tests.
        os.environ.pop("HOOKSMITH_OFFLINE", None)


@_skip
def test_fix_hook_does_not_touch_the_tree_when_nothing_matches() -> None:
    """BUG-0002 regression: a file-consuming hook must not run on an empty changeset.

    With `{files}` expanding to nothing, a tool like `ruff check --fix` falls back to
    scanning the whole project and rewrites files the change never touched. Here the
    stand-in truncates every file it is *not* given, so if it runs project-wide the
    untouched source is destroyed.
    """
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        Path("victim.py").write_text("ORIGINAL\n", encoding="utf-8")
        # A "formatter" that clobbers victim.py whenever it is invoked.
        Path("fixer.sh").write_text("#!/bin/sh\necho CLOBBERED > victim.py\n", encoding="utf-8")
        Path("fixer.sh").chmod(0o755)
        _write(
            "check.toml",
            '[[hook]]\nid = "fix"\nfrom = "system"\nrun = "./fixer.sh {files}"\nfiles = "*.py"\n',
        )
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "seed"], check=True, capture_output=True)

        # Act — nothing staged, so the hook's *.py glob routes it nothing
        result = runner.invoke(main, ["run"])

        # Assert — skipped, and the working tree is intact
        assert result.exit_code == 0, result.output
        assert "skip  fix" in result.output
        assert "no matching files" in result.output
        assert Path("victim.py").read_text(encoding="utf-8") == "ORIGINAL\n"


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
def test_commit_msg_run_checks_the_message_file() -> None:
    # Arrange — a system hook that reads the message file via {commit-msg}. A tiny
    # Python checker keeps this cross-platform (no shell-script exec bit / shebang).
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        Path("check_msg.py").write_text(
            "import sys\nsys.exit(0 if open(sys.argv[1]).read().startswith('feat') else 1)\n",
            encoding="utf-8",
        )
        _write(
            "check.toml",
            '[[hook]]\nid = "cc"\nfrom = "system"\n'
            'run = "python check_msg.py {commit-msg}"\npass-files = false\n'
            '[group.msg]\nhooks = ["cc"]\non-event = "commit-msg"\n',
        )
        Path("good.txt").write_text("feat: a thing\n", encoding="utf-8")
        Path("bad.txt").write_text("nope\n", encoding="utf-8")

        # Act / Assert — a conforming message passes
        ok = runner.invoke(main, ["run", "msg", "--commit-msg-file", "good.txt"])
        assert ok.exit_code == 0, ok.output
        assert "1 passed" in ok.output

        # …and a non-conforming one fails
        bad = runner.invoke(main, ["run", "msg", "--commit-msg-file", "bad.txt"])
        assert bad.exit_code == 1
        assert "FAIL  cc" in bad.output


@_skip
def test_commit_msg_file_is_mutually_exclusive_with_changeset_flags() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        _write(
            "check.toml",
            '[[hook]]\nid = "say"\nfrom = "system"\nrun = "echo hi"\npass-files = false\n',
        )
        Path("msg.txt").write_text("feat: x\n", encoding="utf-8")
        # Act
        result = runner.invoke(main, ["run", "--commit-msg-file", "msg.txt", "--all-files"])
        # Assert
        assert result.exit_code != 0
        assert "cannot be combined" in result.output


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
