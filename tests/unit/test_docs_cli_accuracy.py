"""Docs must only document commands that exist (BUG-0003 / GAT-44).

The docs once described a CLI that was never built — `gatecheck workspace list`,
`cache prune`, `run --hook`, `migrate --dry-run` and more — including on the
quickstart page a first-time user lands on. This test extracts every ``gatecheck …``
invocation from the documentation, the README and the marketing page, and walks it
against the real click command tree, so prose can never drift from the CLI again.

Only invocations inside **code** (fenced blocks, inline spans, or HTML ``<code>``)
are checked; prose that merely begins with the word "gatecheck" is ignored.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import click
import pytest

from gatecheck.cli.main import main

_REPO_ROOT = Path(__file__).resolve().parents[2]

_FENCED = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_INLINE = re.compile(r"`([^`\n]+)`")
_HTML_CODE = re.compile(r"<code[^>]*>(.*?)</code>", re.DOTALL | re.IGNORECASE)
# A real invocation starts a line (optionally after a `$ ` prompt). This deliberately
# skips prose and shell comments that merely mention gatecheck mid-line, and the
# negative lookahead avoids matching the `gatecheck-core` package name.
_INVOCATION = re.compile(r"^[ \t]*(?:\$ )?(gatecheck(?![-\w])[^\n|>&#]*)", re.MULTILINE)


def _sources() -> list[Path]:
    """Every documentation surface that can carry a command."""
    paths = sorted((_REPO_ROOT / "docs").rglob("*.md"))
    for extra in ("README.md", "website/index.html"):
        candidate = _REPO_ROOT / extra
        if candidate.exists():
            paths.append(candidate)
    return paths


def _code_spans(text: str, path: Path) -> list[str]:
    """The code regions of a document — where commands legitimately live."""
    if path.suffix == ".html":
        return _HTML_CODE.findall(text)
    return _FENCED.findall(text) + _INLINE.findall(text)


def _invocations() -> list[tuple[Path, str]]:
    """Extract ``(file, command)`` for every gatecheck invocation written in code."""
    found: list[tuple[Path, str]] = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        for span in _code_spans(text, path):
            for raw in _INVOCATION.findall(span):
                command = raw.strip().rstrip("\\").strip()
                # Skip prose-in-backticks like `gatecheck is fast` by requiring the
                # remainder to look like arguments, not a sentence.
                if _looks_like_prose(command):
                    continue
                found.append((path, command))
    return found


def _looks_like_prose(command: str) -> bool:
    """True when the text after ``gatecheck`` reads as a sentence rather than argv."""
    rest = command[len("gatecheck") :].strip()
    if not rest:
        return False  # bare `gatecheck` is a legitimate invocation
    first = rest.split()[0]
    return not (first.startswith("-") or first.replace("-", "").isalnum()) or " " in first


def _walk(command: str) -> None:
    """Resolve ``command`` against the click tree; raise AssertionError if it cannot exist."""
    tokens = shlex.split(command)[1:]  # drop the program name
    node: click.Command = main
    seen: list[str] = ["gatecheck"]

    for token in tokens:
        if token.startswith("-"):
            option = token.split("=", 1)[0]
            valid = {opt for param in node.params for opt in param.opts + param.secondary_opts}
            assert option in valid, (
                f"`{' '.join(seen)}` has no option {option!r} (valid: {', '.join(sorted(valid))})"
            )
            continue
        if isinstance(node, click.Group):
            child = node.get_command(click.Context(node), token)
            if child is not None:
                node = child
                seen.append(token)
                continue
            # A token that is not a subcommand of a group is an unknown command.
            assert not _is_command_like(token), (
                f"`{' '.join(seen)}` has no subcommand {token!r} "
                f"(valid: {', '.join(sorted(node.list_commands(click.Context(node))))})"
            )
        # Otherwise the token is a positional argument or an option value — fine.


def _is_command_like(token: str) -> bool:
    """True for a bare word that would have to be a subcommand (not a placeholder/value)."""
    if token.startswith(("<", "$", "{", '"', "'")) or token.endswith(">"):
        return False
    return token.replace("-", "").replace("_", "").isalpha()


@pytest.mark.parametrize(
    ("path", "command"),
    [pytest.param(p, c, id=f"{p.name}::{c[:60]}") for p, c in _invocations()],
)
def test_documented_command_exists(path: Path, command: str) -> None:
    """Every documented gatecheck invocation must resolve against the real CLI."""
    try:
        _walk(command)
    except ValueError as exc:  # unbalanced quotes in a doc snippet
        pytest.fail(f"{path.relative_to(_REPO_ROOT)}: cannot parse {command!r}: {exc}")


def test_invocations_were_actually_found() -> None:
    """Guard the guard: a broken extractor must not silently pass everything."""
    assert len(_invocations()) > 20
