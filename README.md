<div align="center">

<img src="docs/assets/logo.svg" alt="gatecheck" width="120">

# gatecheck

**modern pre-commit actions, blazing fast.**

[![PyPI](https://img.shields.io/pypi/v/gatecheck?style=flat-square&color=e05e32&labelColor=0e0e0e)](https://pypi.org/project/gatecheck/)
[![Python](https://img.shields.io/pypi/pyversions/gatecheck?style=flat-square&color=e05e32&labelColor=0e0e0e)](https://pypi.org/project/gatecheck/)
[![CI](https://img.shields.io/github/actions/workflow/status/snoodleboot-io/gatecheck/ci.yml?branch=main&style=flat-square&color=e05e32&labelColor=0e0e0e)](https://github.com/snoodleboot-io/gatecheck/actions)
[![License](https://img.shields.io/github/license/snoodleboot-io/gatecheck?style=flat-square&color=e05e32&labelColor=0e0e0e)](LICENSE)
[![Built with Rust](https://img.shields.io/badge/built%20with-Rust-e05e32?style=flat-square&labelColor=0e0e0e)](gatecheck-rs/)
[![Docs](https://img.shields.io/badge/docs-gatecheck.dev-e05e32?style=flat-square&labelColor=0e0e0e)](https://gatecheck.dev)

</div>

---

gatecheck is the next-generation runner for your git pre-commit actions:

- **Installs hooks from PyPI** — `from = "pypi:ruff>=0.4"`
- **Supports private package registries** — `from = "pypi+internal:my-linter==1.0"`
- **Reuses your project's venv** — `from = "project"` for mypy, pytest, etc.
- **Understands monorepos** — per-package configs, `--affected` execution, dep graphs
- **Runs hooks in parallel** — DAG-based execution via Rust + rayon
- **Starts in under 10ms** — compiled Rust binary, no interpreter warmup
- **Explains cache decisions** — `gatecheck cache why black` tells you exactly why

## Install

```bash
pip install gatecheck
```

## Quick example

```toml
# check.toml

[[hook]]
id   = "ruff"
from = "pypi:ruff>=0.4"
run  = "ruff check --fix {files}"
files = "*.py"

[[hook]]
id   = "mypy"
from = "project"           # use the project's own venv — no shadow copies
run  = "mypy src/"
pass-files = false
when = { env-not = "SKIP_MYPY" }

[group.lint]
hooks    = ["ruff", "mypy"]
parallel = true
on-event = "commit"
```

```bash
gatecheck install    # install git hooks
gatecheck sync       # install hook environments
gatecheck run lint   # run the lint group
```

## What you get

| Capability | gatecheck |
|---|---|
| PyPI package sources (public + private) | ✓ native |
| Project venv reuse | ✓ `from = "project"` |
| Monorepo / workspace awareness | ✓ per-package configs |
| Affected-package execution | ✓ `--affected` |
| Parallel execution | ✓ Rust + rayon |
| Dependency graph (DAG) | ✓ topological waves |
| Lockfile reproducibility | ✓ `check.lock` |
| Branch / env / CI conditions | ✓ rich `when:` |
| Cache debugging | ✓ `cache why` |
| Startup time | ~8 ms |

## Importing existing hooks

```bash
gatecheck migrate   # reads your existing hook config, writes check.toml
```

Known PyPI-published hooks (black, ruff, isort, mypy, flake8, and more) are detected automatically and rewritten with PyPI sources.

## Documentation

Full documentation at **[gatecheck.dev](https://gatecheck.dev)**

- [Quick Start](https://gatecheck.dev/getting-started/quickstart/)
- [Configuration Reference](https://gatecheck.dev/config/reference/)
- [Monorepo Guide](https://gatecheck.dev/guides/monorepo/)
- [Architecture](https://gatecheck.dev/design/architecture/)

## Architecture

gatecheck has two layers:

**Python host** — config parsing (TOML), CLI (click + rich), environment management (uv-backed venvs)

**Rust core (`gatecheck-core`)** — DAG solver, parallel subprocess runner, file glob matching, SHA-256 cache keys, git integration, affected-package graph

The Rust layer is distributed as a compiled maturin wheel. Users `pip install gatecheck` and get a native binary — no Rust toolchain required.

```
┌─────────────────────────────────────┐
│   Python: config · cli · env · ws   │
├──────────────┬──────────────────────┤
│              │  PyO3 boundary       │
├──────────────┴──────────────────────┤
│   Rust: DAG · runner · cache · git  │
└─────────────────────────────────────┘
```

## Development

```bash
git clone https://github.com/snoodleboot-io/gatecheck
cd gatecheck
uv venv && uv pip install -e ".[dev]"
cd gatecheck-rs && maturin develop --release && cd ..
pytest tests/ && cargo test --manifest-path gatecheck-rs/Cargo.toml
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development guide, commit conventions, and release process.

## License

MIT — see [LICENSE](LICENSE)
