# hooksmith-core

The native (Rust + PyO3) core of [hooksmith](../README.md). Built and distributed as a maturin wheel named `hooksmith-core`; imported from Python as `hooksmith_core`.

Owned subsystems:

| Module    | Responsibility                                        |
| --------- | ----------------------------------------------------- |
| `dag`     | Topological sort + wave builder for hook execution.   |
| `runner`  | Rayon-backed parallel subprocess fan-out.             |
| `cache`   | SHA-256 cache-key generation and hit/miss tracking.   |
| `git`     | Staged file and branch-name plumbing.                 |
| `glob`    | File pattern matching for `files = "..."` hook entries. |

## Build

```
maturin develop --release
```

See [planning/adr/0001-python-host-rust-core.md](../planning/adr/0001-python-host-rust-core.md) for why this crate exists, and [docs/design/architecture.md](../docs/design/architecture.md) for how it fits.
