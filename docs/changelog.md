# Changelog

All notable changes to gatecheck are documented here.
This file is **automatically generated** by the CI release pipeline — do not edit manually.

Changes are grouped by type and follow [Conventional Commits](https://www.conventionalcommits.org/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

_Changes on `main` not yet released._

---

## [0.1.0] — 2025-01-01

### ✨ Features

- Initial release of gatecheck
- `pypi:`, `pypi+<alias>:`, `git:`, `local:`, `docker:`, `project`, `system` source types
- Rust-powered parallel DAG runner via PyO3 + rayon
- Workspace (monorepo) support with per-package config inheritance
- `--affected` flag for affected-package execution in monorepos
- Transitive dependency propagation in workspace dependency graphs
- `when:` conditions: branch, env, files-match, on-ci
- Named groups with parallel execution and `on-event` git hook binding
- `gatecheck install` — git hook installer
- `gatecheck sync` — environment sync with uv
- `gatecheck cache why/clear` — transparent cache management
- `gatecheck migrate` — automated `.pre-commit-config.yaml` → `check.toml` conversion
- `gatecheck run --affected` — workspace-aware execution, results prefixed `<package>:<hook>`
- `check.toml` or `[tool.gatecheck]` in `pyproject.toml`
- Sub-10ms startup on no-op commits (vs 300ms+ for pre-commit)

[Unreleased]: https://github.com/snoodleboot-io/gatecheck/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/snoodleboot-io/gatecheck/releases/tag/v0.1.0
