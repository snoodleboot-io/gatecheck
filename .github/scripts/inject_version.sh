#!/usr/bin/env bash
# Inject the CI-computed version into every place hooksmith's two distributions read
# it from, so the host and core build as one unified version (STY-0044 / GAT-53):
#   • src/hooksmith/__about__.py  — the host version (hatchling reads it)
#   • hooksmith-rs/Cargo.toml     — the core version (maturin reads it)
#   • pyproject.toml              — the host's exact hooksmith-core== pin
#
# Usage: inject_version.sh <version>
set -euo pipefail

version="${1:?usage: inject_version.sh <version>}"

# Host version. Anchored to the assignment so nothing else in the file is touched.
sed -i "s/^__version__ = .*/__version__ = \"${version}\"/" src/hooksmith/__about__.py

# Core version — the [package] version line only (^version, not rust-version / deps).
sed -i "s/^version *= *\".*\"/version = \"${version}\"/" hooksmith-rs/Cargo.toml

# Host → core exact pin (was hooksmith-core>=…); the trailing comment is preserved.
sed -i "s/\"hooksmith-core[^\"]*\"/\"hooksmith-core==${version}\"/" pyproject.toml

echo "Injected version ${version}:"
grep '^__version__' src/hooksmith/__about__.py
grep '^version' hooksmith-rs/Cargo.toml | head -1
grep 'hooksmith-core==' pyproject.toml
