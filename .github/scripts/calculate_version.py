#!/usr/bin/env python3
"""Derived version calculator for gatecheck's trunk-based release pipeline.

Version schema: ``MAJOR.MINOR.PATCH[.devN]``

- MAJOR  — from the CI environment (``MAJOR_VERSION``); gatecheck stays on 0.x.
- MINOR  — the latest MINOR on PyPI for that MAJOR, + 1. First release (nothing on
           PyPI yet) starts at MINOR = 1, so the first published version is 0.1.0.
- PATCH  — the PR number on PR builds; 0 on a push to main.
- .devN  — the GitHub run number, appended for TestPyPI preview builds only.

Both distributions (the ``gatecheck`` host and the ``gatecheck-core`` extension)
share the one version this computes; the workflow injects it into
``src/gatecheck/__about__.py``, ``gatecheck-rs/Cargo.toml``, and the host's
``gatecheck-core==`` dependency pin before building.

PyPI is queried for the ``gatecheck`` host to find the baseline MINOR. A query
failure is fatal (strict mode) — we never want to silently reuse a MINOR and clash
with an existing release.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable

# First release starts here so the debut version is 0.1.0 (matching the seed
# gatecheck-rs/Cargo.toml version), not 0.0.0.
_FIRST_RELEASE_MINOR = 1

PyPILookup = Callable[[str], "tuple[int, int] | None"]


def query_pypi_major_minor(package_name: str) -> tuple[int, int] | None:
    """Return the (major, minor) of the latest version on PyPI, or None if absent.

    Raises on a network/parse failure so the caller can fail the build in strict mode.
    """
    package = package_name.strip()
    url = f"https://pypi.org/pypi/{package}/json"
    print(f"Querying PyPI: {url}")
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # Package has never been published — a legitimate first-release state.
            print(f"PyPI: {package} not found (404) — treating as first release")
            return None
        raise

    version = data["info"]["version"]
    # Only MAJOR.MINOR matter; ignore any PATCH/pre/post/dev/local suffix (PEP 440).
    match = re.match(r"^(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(f"PyPI version '{version}' could not be parsed")
    return int(match.group(1)), int(match.group(2))


class VersionCalculator:
    """Computes the build version from PyPI history and the GitHub event context."""

    def __init__(
        self, package_name: str = "gatecheck", pypi_lookup: PyPILookup | None = None
    ) -> None:
        self.package_name = package_name
        self._pypi_lookup = pypi_lookup or query_pypi_major_minor

    def _next_minor(self, major: int) -> int:
        pypi = self._pypi_lookup(self.package_name)
        if pypi is None:
            return _FIRST_RELEASE_MINOR
        pypi_major, pypi_minor = pypi
        # Same MAJOR: continue the line. A MAJOR bump restarts MINOR at 1.
        return pypi_minor + 1 if pypi_major == major else 1

    def calculate_version(
        self,
        *,
        major: int,
        pr_number: str | None,
        run_number: str | None,
        is_testpypi: bool,
        is_pr: bool,
        github_ref: str,
    ) -> str:
        """Return the version string for this build."""
        new_minor = self._next_minor(major)

        if pr_number is None:
            if is_pr:
                print("ERROR: PR number is required for PR builds", file=sys.stderr)
                sys.exit(1)
            if github_ref == "refs/heads/main":
                # A merge landed on main → the release version.
                return f"{major}.{new_minor}.0"
            # A feature-branch push → a throwaway dev build (never published).
            return f"{major}.{new_minor}.0.dev0"

        # PR build: PATCH is the PR number; TestPyPI previews add the run number.
        version = f"{major}.{new_minor}.{pr_number}"
        if is_testpypi and run_number:
            version = f"{version}.dev{run_number}"
        return version


def _extract_pr_number(github_ref: str) -> str | None:
    # PR refs look like refs/pull/28/merge.
    match = re.search(r"refs/pull/(\d+)/", github_ref)
    return match.group(1) if match else None


def main() -> None:
    package_name = os.environ.get("PACKAGE_NAME", "gatecheck").strip()

    env_major = os.environ.get("MAJOR_VERSION", "0").strip()
    try:
        major = int(env_major)
    except ValueError:
        print(f"ERROR: invalid MAJOR_VERSION '{env_major}', defaulting to 0")
        major = 0

    event_name = os.environ.get("GITHUB_EVENT_NAME", "push").strip()
    action = os.environ.get("GITHUB_EVENT_ACTION", "").strip()
    base_ref = os.environ.get("GITHUB_BASE_REF", "").strip()
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "").strip()
    github_ref = os.environ.get("GITHUB_REF", "").strip()

    is_pr = event_name == "pull_request"
    is_pr_to_main = base_ref in ("main", "refs/heads/main")
    pr_number = _extract_pr_number(github_ref) if is_pr else None

    # PR to main → TestPyPI preview. Push to main → PyPI release (gated downstream).
    is_testpypi = is_pr and is_pr_to_main and action != "closed"
    is_pypi = event_name == "push" and github_ref == "refs/heads/main"

    print(
        f"DEBUG: ref='{github_ref}' event='{event_name}' action='{action}' "
        f"base='{base_ref}' run='{run_number}' major={major} "
        f"is_pr={is_pr} pr_number={pr_number} testpypi={is_testpypi} pypi={is_pypi}"
    )

    version = VersionCalculator(package_name).calculate_version(
        major=major,
        pr_number=pr_number,
        run_number=run_number,
        is_testpypi=is_testpypi,
        is_pr=is_pr,
        github_ref=github_ref,
    )

    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"version={version}\n")
            f.write(f"should_publish_testpypi={str(is_testpypi).lower()}\n")
            f.write(f"should_publish_pypi={str(is_pypi).lower()}\n")

    print(f"Version: {version}")
    print(f"Publish TestPyPI: {is_testpypi}")
    print(f"Publish PyPI: {is_pypi}")


if __name__ == "__main__":
    main()
