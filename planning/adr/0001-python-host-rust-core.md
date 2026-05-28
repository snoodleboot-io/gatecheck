---
id: ADR-0001
title: Split the implementation into a Python host and a Rust core
status: Accepted
author: TBD
date: 2026-05-28
supersedes: none
superseded-by: none
---

# ADR-0001: Split the implementation into a Python host and a Rust core

## Context

`gatecheck` has two distinct kinds of workload:

1. **Config, CLI, and environment management.** TOML parsing, package resolution against PyPI / private registries, uv-backed venv creation, monorepo discovery. These benefit from a rich ecosystem (`pydantic`, `click`, `uv`, the Python packaging stack) and don't sit on the hot path.
2. **Hot-path execution.** DAG-based parallel subprocess fan-out, file glob matching, SHA-256 cache key generation, git plumbing. Latency here is the whole point — a hook runner that adds 300 ms before doing anything useful loses the comparison against pre-commit before it starts.

Pure Python gives away the second category. Pure Rust gives away the first (rewriting the Python packaging world in Rust is out of scope for this project).

The user-facing distribution constraint: `pip install gatecheck` must work without requiring a Rust toolchain. Wheels need to be prebuilt.

## Decision

`gatecheck` is implemented as a **Python host** (`src/gatecheck/`, click + rich + pydantic) that imports a **Rust core** (`gatecheck-rs/`, PyO3 bindings, packaged as a maturin-built wheel named `gatecheck-core`). The CLI entry point, config parsing, and environment management live in Python. The DAG solver, parallel runner, cache hashing, git integration, and glob engine live in Rust.

## Consequences

- **Positive**
  - Sub-10 ms startup via the compiled Rust binary on the hot path.
  - Python ecosystem available for everything that touches packaging.
  - Rust core is independently testable (`cargo test`) without a Python runtime.
  - Users install one wheel and get both halves; no Rust toolchain on user machines.

- **Negative**
  - Two languages, two build systems (`hatch` + `maturin`), two test suites in CI.
  - The PyO3 boundary is a real surface — type marshalling has a cost and adds a place where bugs hide.
  - Releases require platform-specific wheel builds (Linux x86_64/aarch64, macOS x86_64/arm64, Windows x86_64) instead of one universal sdist.

- **Neutral / follow-ups**
  - The PyO3 boundary contract is documented in `docs/design/architecture.md` and will need its own ADR if it changes shape.
  - A future ADR will pick the maturin distribution strategy (abi3 vs per-Python-version wheels).

## Alternatives considered

- **Pure Python.** Simplest to build and distribute. Rejected — cold start and per-hook subprocess fan-out are the headline performance claims, and Python alone can't hit them.
- **Pure Rust with a TOML-based config.** Fastest possible runtime. Rejected — reimplementing PyPI resolution, venv management, and the Python packaging story in Rust is months of work for marginal benefit on top of `uv`'s existing Python API.
- **Python host + Go core.** Go is easier to build and distribute as a single binary. Rejected — there is no first-class story for embedding Go into a Python wheel; `cgo` is awkward and PyO3 is mature.
- **Python host + C/C++ extension.** Same shape as the chosen path, but with a much worse developer experience and a memory-safety footgun on the hot path. Rejected.
