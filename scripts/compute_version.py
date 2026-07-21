#!/usr/bin/env python3
"""
compute_version.py — Semantic version calculator for gatecheck CI.

Reads the git log since the last tag, parses conventional commits,
and outputs the next version + changelog to GitHub Actions output format.

Rules:
  MAJOR bump: any commit with `BREAKING CHANGE:` footer, OR --force-major flag
  MINOR bump: any `feat:` or `feat(scope):` commit
  PATCH bump: any `fix:`, `perf:`, `refactor:`, `revert:` commit
  No bump:    `docs:`, `style:`, `test:`, `chore:`, `ci:` commits only

The MAJOR version can ONLY be bumped through this script (in CI).
It cannot be manually edited in source files.

Output (GitHub Actions output format):
  version=X.Y.Z
  tag=vX.Y.Z
  should_release=true|false
  changelog=<markdown text>
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum


class BumpLevel(Enum):
    NONE = 0
    PATCH = 1
    MINOR = 2
    MAJOR = 3

    def __gt__(self, other):
        return self.value > other.value

    def __ge__(self, other):
        return self.value >= other.value


# Conventional commit pattern
CC_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?: (?P<desc>.+)$",
    re.MULTILINE,
)

BREAKING_FOOTER_RE = re.compile(r"^BREAKING CHANGE:", re.MULTILINE)

BUMP_MAP: dict[str, BumpLevel] = {
    "feat": BumpLevel.MINOR,
    "fix": BumpLevel.PATCH,
    "perf": BumpLevel.PATCH,
    "refactor": BumpLevel.PATCH,
    "revert": BumpLevel.PATCH,
    "docs": BumpLevel.NONE,
    "style": BumpLevel.NONE,
    "test": BumpLevel.NONE,
    "chore": BumpLevel.NONE,
    "ci": BumpLevel.NONE,
    "build": BumpLevel.NONE,
}


@dataclass
class ConventionalCommit:
    sha: str
    type: str
    scope: str | None
    description: str
    body: str
    breaking: bool
    raw: str


@dataclass
class VersionPlan:
    current: tuple[int, int, int]
    next: tuple[int, int, int]
    bump: BumpLevel
    commits: list[ConventionalCommit] = field(default_factory=list)
    force_major: bool = False


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def get_latest_tag() -> str | None:
    """Return the most recent semver tag, or None if no tags exist."""
    try:
        tag = git("describe", "--tags", "--abbrev=0", "--match", "v[0-9]*.[0-9]*.[0-9]*")
        return tag
    except subprocess.CalledProcessError:
        return None


def parse_tag(tag: str) -> tuple[int, int, int]:
    """Parse 'v1.2.3' -> (1, 2, 3)."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", tag)
    if not m:
        raise ValueError(f"Cannot parse tag: {tag!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def commits_since(tag: str | None) -> list[dict]:
    """Return list of {sha, subject, body} dicts since tag (or all commits)."""
    if tag:
        log_range = f"{tag}..HEAD"
    else:
        log_range = "HEAD"

    raw = git("log", log_range, "--format=%H%x00%s%x00%b%x01")
    commits = []
    for entry in raw.split("\x01"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("\x00", 2)
        commits.append(
            {
                "sha": parts[0] if len(parts) > 0 else "",
                "subject": parts[1] if len(parts) > 1 else "",
                "body": parts[2] if len(parts) > 2 else "",
            }
        )
    return commits


def parse_conventional(commit: dict) -> ConventionalCommit | None:
    """Parse a commit dict into a ConventionalCommit, or None if non-conventional."""
    subject = commit["subject"]
    m = CC_RE.match(subject)
    if not m:
        return None

    is_breaking = bool(m.group("breaking")) or bool(
        BREAKING_FOOTER_RE.search(commit.get("body", ""))
    )

    return ConventionalCommit(
        sha=commit["sha"][:8],
        type=m.group("type"),
        scope=m.group("scope"),
        description=m.group("desc"),
        body=commit.get("body", ""),
        breaking=is_breaking,
        raw=subject,
    )


def compute_bump(commits: list[ConventionalCommit], force_major: bool) -> BumpLevel:
    if force_major:
        return BumpLevel.MAJOR

    level = BumpLevel.NONE
    for c in commits:
        if c.breaking:
            return BumpLevel.MAJOR
        bump = BUMP_MAP.get(c.type, BumpLevel.NONE)
        if bump > level:
            level = bump

    return level


def next_version(current: tuple[int, int, int], bump: BumpLevel) -> tuple[int, int, int]:
    major, minor, patch = current
    if bump == BumpLevel.MAJOR:
        return (major + 1, 0, 0)
    elif bump == BumpLevel.MINOR:
        return (major, minor + 1, 0)
    elif bump == BumpLevel.PATCH:
        return (major, minor, patch + 1)
    else:
        return current


def build_changelog(
    commits: list[ConventionalCommit],
    version: tuple[int, int, int],
) -> str:
    """Build a markdown changelog section."""
    from datetime import date

    ver_str = f"{version[0]}.{version[1]}.{version[2]}"
    today = date.today().isoformat()

    sections: dict[str, list[str]] = {
        "breaking": [],
        "feat": [],
        "fix": [],
        "perf": [],
        "refactor": [],
        "other": [],
    }

    for c in commits:
        scope = f"**{c.scope}**: " if c.scope else ""
        line = f"- {scope}{c.description} ({c.sha})"

        if c.breaking:
            sections["breaking"].append(line)
        elif c.type in sections:
            sections[c.type].append(line)
        else:
            sections["other"].append(line)

    parts = [f"## [{ver_str}] — {today}\n"]

    if sections["breaking"]:
        parts.append("### ⚠️ Breaking Changes\n")
        parts.extend(sections["breaking"])
        parts.append("")

    if sections["feat"]:
        parts.append("### ✨ Features\n")
        parts.extend(sections["feat"])
        parts.append("")

    if sections["fix"]:
        parts.append("### 🐛 Bug Fixes\n")
        parts.extend(sections["fix"])
        parts.append("")

    if sections["perf"]:
        parts.append("### ⚡ Performance\n")
        parts.extend(sections["perf"])
        parts.append("")

    if sections["refactor"]:
        parts.append("### ♻️ Refactoring\n")
        parts.extend(sections["refactor"])
        parts.append("")

    if sections["other"]:
        parts.append("### 🔧 Other\n")
        parts.extend(sections["other"])
        parts.append("")

    return "\n".join(parts)


def gh_output(key: str, value: str) -> None:
    """Write a GitHub Actions output variable, handling multiline values."""
    if "\n" in value:
        delimiter = "EOF_GATECHECK"
        print(f"{key}<<{delimiter}")
        print(value)
        print(delimiter)
    else:
        print(f"{key}={value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute next semantic version.")
    parser.add_argument(
        "--force-major", default="false", help="Force a MAJOR bump ('true'/'false')"
    )
    args = parser.parse_args()

    force_major = args.force_major.lower() == "true"

    # ---- Get current version from latest tag ----
    latest_tag = get_latest_tag()
    if latest_tag:
        current = parse_tag(latest_tag)
    else:
        current = (0, 0, 0)
        print("No existing tags found — starting from 0.0.0", file=sys.stderr)

    # ---- Analyse commits since last tag ----
    raw_commits = commits_since(latest_tag)
    conventional = [c for raw in raw_commits if (c := parse_conventional(raw)) is not None]

    non_conventional = len(raw_commits) - len(conventional)
    if non_conventional:
        print(f"⚠ {non_conventional} non-conventional commit(s) ignored.", file=sys.stderr)

    # ---- Compute bump level ----
    bump = compute_bump(conventional, force_major=force_major)
    next_ver = next_version(current, bump)

    current_str = ".".join(str(x) for x in current)
    next_str = ".".join(str(x) for x in next_ver)
    tag = f"v{next_str}"

    print(f"Current version : {current_str}", file=sys.stderr)
    print(f"Commits analysed: {len(conventional)}", file=sys.stderr)
    print(f"Bump level      : {bump.name}", file=sys.stderr)
    print(f"Next version    : {next_str}", file=sys.stderr)
    print(f"Force major     : {force_major}", file=sys.stderr)

    # ---- Should we actually release? ----
    should_release = bump > BumpLevel.NONE or force_major

    if not should_release:
        print("No releasable commits — skipping release.", file=sys.stderr)
        gh_output("version", current_str)
        gh_output("tag", f"v{current_str}")
        gh_output("should_release", "false")
        gh_output("changelog", "No changes.")
        return

    # ---- Build changelog ----
    changelog = build_changelog(conventional, next_ver)

    # ---- Emit GitHub Actions outputs ----
    gh_output("version", next_str)
    gh_output("tag", tag)
    gh_output("should_release", "true")
    gh_output("changelog", changelog)


if __name__ == "__main__":
    main()
