"""Single source of the package version.

The real version is injected by CI/CD at build time — the release pipeline computes
MAJOR.MINOR.PATCH from PyPI history + PR context and rewrites this file before the
build (see .github/scripts/calculate_version.py and .github/workflows/release.yml).
Local and editable installs use this dev placeholder.
"""

__version__ = "0.0.0.dev0"
