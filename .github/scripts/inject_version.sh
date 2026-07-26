#!/usr/bin/env bash
# Inject the CI-computed version into every place gatecheck's two distributions read
# it from, so the host and core build as one unified version (STY-0044 / GAT-53):
#   • src/gatecheck/__about__.py  — the host version (hatchling reads it)
#   • gatecheck-rs/Cargo.toml     — the core version (maturin reads it)
#   • pyproject.toml              — the host's exact gatecheck-core== pin
#
# Usage: inject_version.sh <version>
set -euo pipefail

version="${1:?usage: inject_version.sh <version>}"

# Host version. Anchored to the assignment so nothing else in the file is touched.
sed -i "s/^__version__ = .*/__version__ = \"${version}\"/" src/gatecheck/__about__.py

# Core version — the [package] version line only (^version, not rust-version / deps).
sed -i "s/^version *= *\".*\"/version = \"${version}\"/" gatecheck-rs/Cargo.toml

# Host → core exact pin (was gatecheck-core>=…); the trailing comment is preserved.
sed -i "s/\"gatecheck-core[^\"]*\"/\"gatecheck-core==${version}\"/" pyproject.toml

echo "Injected version ${version}:"
grep '^__version__' src/gatecheck/__about__.py
grep '^version' gatecheck-rs/Cargo.toml | head -1
grep 'gatecheck-core==' pyproject.toml
