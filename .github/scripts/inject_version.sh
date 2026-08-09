#!/usr/bin/env bash
# Inject the CI-computed version into every place hooksmith's two distributions read
# it from, so the host and core build as one unified version (STY-0044 / GAT-53):
#   • src/hooksmith/__about__.py  — the host version (hatchling reads it)
#   • hooksmith-rs/Cargo.toml     — the core version (maturin reads it)
#   • pyproject.toml              — the host's exact hooksmith-core== pin
#
# Uses `perl -pi` rather than `sed -i`: the release matrix builds on macOS too, and
# BSD sed's `-i` needs a mandatory backup-suffix argument that GNU sed rejects, so a
# `sed -i "s/…/…/"` that works on Linux fails on macOS. perl -pi is identical on both.
#
# Usage: inject_version.sh <version>
set -euo pipefail

version="${1:?usage: inject_version.sh <version>}"

# Host version. Anchored to the assignment so nothing else in the file is touched.
perl -pi -e "s/^__version__ = .*/__version__ = \"${version}\"/" src/hooksmith/__about__.py

# Core version — the [package] version line only (^version, not rust-version / deps).
perl -pi -e "s/^version\s*=\s*\".*\"/version = \"${version}\"/" hooksmith-rs/Cargo.toml

# Host → core exact pin (was hooksmith-core>=…); the trailing comment is preserved.
perl -pi -e "s/\"hooksmith-core[^\"]*\"/\"hooksmith-core==${version}\"/" pyproject.toml

echo "Injected version ${version}:"
grep '^__version__' src/hooksmith/__about__.py
grep '^version' hooksmith-rs/Cargo.toml | head -1
grep 'hooksmith-core==' pyproject.toml
