# Installation

!!! warning "Not yet published to PyPI"

    gatecheck is pre-release. There is no `pip install gatecheck` yet — the wheel
    matrix and publishing pipeline are still being built, so for now you install by
    building from source.

    Once wheels are published this page will lead with `pip install gatecheck`, and
    the from-source route below becomes the contributor path.

## Requirements

| | |
|---|---|
| **Python** | 3.11 or 3.12 |
| **Rust** | a stable toolchain — gatecheck ships a compiled core |
| **git** | required at run time; the changeset comes from git |
| **uv** | optional — auto-downloaded on first use if absent |

## From source

```bash
git clone https://github.com/snoodleboot-io/gatecheck
cd gatecheck

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e .
maturin develop --release -m gatecheck-rs/Cargo.toml
```

The second command compiles the Rust core (`gatecheck_core`) and installs it into the
same environment. `pip install -e .` alone is not enough — the native extension is not
on PyPI, which is exactly why there is no wheel yet.

Verify:

```console
$ gatecheck --version
gatecheck, version 0.1.dev…
```

Both `gatecheck` and the shorter `gc` alias are installed.

## Platform support

| Platform | Status |
|---|---|
| Linux (x86_64, aarch64) | supported, tested in CI |
| macOS (x86_64, arm64) | supported |
| Windows | supported, tested in CI |

Windows is a first-class target, not an afterthought — the venv layout (`Scripts\`
vs `bin/`), executable resolution (`PATHEXT`, `.exe`/`.bat`/`.cmd`) and command
tokenization are all platform-aware, and the full test suite runs on `windows-latest`
against both Python versions.

## About `uv`

gatecheck builds hook environments with [uv](https://docs.astral.sh/uv/). You do not
have to install it: if `uv` is not found, a pinned, checksum-verified copy is
downloaded once into the cache (`~/.cache/gatecheck/bin/uv`) and reused thereafter.

To control that:

| Variable | Effect |
|---|---|
| `GATECHECK_UV` | Use the `uv` at this path instead of searching. |
| `GATECHECK_NO_BOOTSTRAP` | Never auto-download. A missing `uv` becomes a clear error. |

Auto-bootstrap covers Linux, macOS and Windows on x86_64 and aarch64. In an
[air-gapped environment](../guides/air-gapped.md), warm the cache from a
network-enabled step or provide `uv` yourself.

Hooks that use `from = "system"` or `from = "project"` never need `uv` at all — they
reuse a binary already on the machine.

## Where things are stored

```
$XDG_CACHE_HOME/gatecheck/        # ~/.cache/gatecheck by default
├── env-v1/<sha256>/…             # one venv per pinned environment
└── bin/uv                        # the bootstrapped uv, if downloaded
```

Nothing is written into your project except the git hooks that
[`gatecheck install`](../cli/install.md) creates. To reclaim the space, see
[`gatecheck cache clear`](../cli/cache.md).

## Next

- [Quick Start](quickstart.md) — a working `check.toml` in a couple of minutes.
- [Migration from pre-commit](migration.md) — already have a `.pre-commit-config.yaml`?
