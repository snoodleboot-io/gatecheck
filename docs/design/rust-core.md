# Rust Core

gatecheck is a **Python host** around a **Rust core**. This page describes what
actually crosses the boundary today, and where the boundary is headed.

The rationale for the split is [ADR-0001](https://github.com/snoodleboot-io/gatecheck/blob/main/planning/adr/0001-python-host-rust-core.md);
the short version: config, packaging and CLI want Python's ecosystem, while
hot-path subprocess scheduling wants compiled parallelism, and neither half should
have to be written in the other's language.

## What's actually in Rust today

One thing: **the parallel execution engine**, `gatecheck_core.run_graph`, in
[`gatecheck-rs/src/runner.rs`](https://github.com/snoodleboot-io/gatecheck/blob/main/gatecheck-rs/src/runner.rs).

```rust
#[pyfunction]
fn run_graph(
    py: Python<'_>,
    nodes: Vec<String>,        // hook ids, in a topologically valid order
    deps: Vec<Vec<usize>>,     // deps[i] = indices node i depends on
    execute: PyObject,         // Python callback: run one hook -> exit status
    fail_fast: bool,
    max_workers: Option<usize>,
) -> PyResult<Vec<String>>     // ids that executed, in input order
```

That's the whole boundary. The graph goes in, a Python callback runs each hook, the
executed ids come back. Everything else — parsing, planning, environment building,
git — is Python calling into that one function at the end.

### Why this piece, specifically

It's the only part that is both **hot** and **parallel**. The scheduler starts each
hook the instant its dependencies finish (dynamic, not wave-barriered), which on an
uneven dependency graph is a real wall-clock win — and doing it in Rust with
[rayon](https://docs.rs/rayon/) gives genuine OS-thread parallelism for the subprocess
waits.

The trick that makes it work across the language boundary: the GIL is released around
the whole rayon scope (`py.allow_threads`) and re-acquired per callback
(`Python::with_gil`). So while one hook's subprocess is blocked in the kernel, other
hooks' callbacks run — the Python side never serializes the waits.

Determinism is preserved despite the parallelism: hooks may *finish* in any order, but
`run_graph` returns them in input order, so the report is identical run to run.

## What's still in Python (and the ADR says will move)

The crate has stub modules — `cache.rs`, `dag.rs`, `git.rs`, `glob.rs` — that register
nothing yet. The logic they name currently lives in Python:

| Concern | Today | ADR-0001 direction |
|---|---|---|
| DAG topological sort | Python (`runner/plan.py`) | Rust (`dag.rs`) |
| Cache key hashing | Python (`hashlib`) | Rust (`cache.rs`) |
| git plumbing | Python (`subprocess`) | Rust (`git.rs`) |
| glob matching | Python (`fnmatch`) | Rust (`glob.rs`) |

This is deliberate sequencing, not drift: the boundary was proven with the piece that
mattered most (parallel execution), and the rest moves across only if profiling shows
it earns the marshalling cost. Documenting the *current* state honestly matters more
than matching the aspiration — a stub that claims to be implemented is worse than an
empty one.

## The boundary contract

Three rules keep the seam narrow and debuggable:

1. **Data in, data out.** Only plain values cross — strings, ints, lists. No Python
   objects with behaviour, no Rust structs leaking into Python. The graph is
   index-based (`deps: Vec<Vec<usize>>`) precisely so nothing but numbers and strings
   has to marshal.
2. **Python owns side effects.** Rust schedules; the `execute` callback — pure
   Python — resolves the environment, spawns the subprocess, and captures output. Rust
   never touches the filesystem or spawns a process itself. That keeps every
   injectable seam (`ProcessRunner`, `EnvManager`) on the Python side where the tests
   already are.
3. **One function, not an API.** The surface is `run_graph`, full stop. A narrow
   boundary is a small attack surface for the classic FFI bug — a lifetime or
   thread-safety mistake that only shows up under load.

## Building and testing it

The core is a separate crate, exposed via [PyO3](https://pyo3.rs/) and built with
[maturin](https://www.maturin.rs/):

```bash
maturin develop --release -m gatecheck-rs/Cargo.toml   # build + install into the venv
cargo test --manifest-path gatecheck-rs/Cargo.toml     # test without Python
cargo clippy --manifest-path gatecheck-rs/Cargo.toml -- -D warnings
```

The crate is independently testable with `cargo test` — no Python runtime required —
which is one of the reasons the boundary is kept this narrow.

## Distribution

Because the core is compiled, gatecheck ships as **platform wheels** (Linux
x86_64/aarch64, macOS x86_64/arm64, Windows x86_64), not a universal sdist. A user
runs `pip install` and gets both halves; no Rust toolchain on their machine. The
wheel-matrix release pipeline is the last piece of that story still being built.

## See also

- [Architecture Overview](architecture.md) — the full data flow.
- [Contributing](../contributing.md#working-on-the-rust-core) — the dev loop.
