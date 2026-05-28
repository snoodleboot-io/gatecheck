---
id: FEAT-0001
title: Config loader
status: Draft
owner: TBD
date: 2026-05-28
prd: PRD-0001 § Scope — Config
adrs: [ADR-0001]
---

# FEAT-0001: Config loader

## Summary

Parse a project's `check.toml` into a fully validated, typed in-memory model that the rest of `gatecheck` consumes. Surface schema errors with file/line context so users can fix their config without guessing.

## Why

Every other subsystem — sources, environments, runner, workspace — reads the result of this feature. Getting the model right (and the error messages humane) determines how the whole tool feels. See [PRD-0001 § Scope — Config](../../prd/0001-gatecheck.md#scope) and [ADR-0001](../../adr/0001-python-host-rust-core.md) for why the loader sits on the Python side.

## User-facing surface

- **Input**: a `check.toml` file at the workspace root, optionally with `check.toml` files in subpackages for monorepo overrides (covered by a later feature).
- **Schema**: `[[hook]]`, `[group.<name>]`, `[sources]` tables as documented in [docs/config/reference.md](../../../docs/config/reference.md).
- **Error format**: `check.toml:LINE:COL: <message>` — single line, parseable by IDE error matchers.
- **Python API**: `from gatecheck.config import load_config; cfg: GatecheckConfig = load_config(Path("check.toml"))`.

## Out of scope

- Monorepo merging of multiple `check.toml` files (separate feature).
- Source-spec *resolution* against PyPI (separate feature — this feature only validates the shape).
- Live reloading on file change.

## Stories

- [ ] [STY-0001 — Load `check.toml` into a validated model](stories/STY-0001-load-check-toml.md)
- [ ] STY-0002 — Surface schema errors with file/line context (not yet written)
- [ ] STY-0003 — Round-trip dump for `gatecheck migrate` output (not yet written)

## Acceptance

- A valid `check.toml` parses into a `GatecheckConfig` object whose fields match the documented schema.
- An invalid `check.toml` produces an error whose first line matches `check.toml:\d+:\d+:` and whose body names the offending key.
- The loader has no runtime dependency on the Rust core (importable in a pure-Python environment).
