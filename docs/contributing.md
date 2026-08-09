# Contributing

Bug reports, questions and pull requests are all welcome at
[snoodleboot-io/hooksmith](https://github.com/snoodleboot-io/hooksmith).

## Getting set up

hooksmith is a Python host around a compiled Rust core, so you need both toolchains:

```bash
git clone https://github.com/snoodleboot-io/hooksmith
cd hooksmith

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,docs]"

# build and install the Rust extension into the venv
maturin develop --release -m hooksmith-rs/Cargo.toml
```

Verify:

```bash
hooksmith --version
pytest -q -m "not network"
```

## The gates

CI runs these on Linux and Windows, against Python 3.11 and 3.12. Run them before
opening a PR:

```bash
ruff check src tests scripts
ruff format --check src tests scripts
mypy src
pytest -m "not network"

# the Rust side
cargo fmt --manifest-path hooksmith-rs/Cargo.toml -- --check
cargo clippy --manifest-path hooksmith-rs/Cargo.toml -- -D warnings
cargo test --manifest-path hooksmith-rs/Cargo.toml
```

Coverage is gated at 85%.

hooksmith also checks itself — `hooksmith run full --all-files` runs the same tools
through its own runner.

## Test markers

| Marker | What it means |
|---|---|
| *(none)* | Hermetic unit test. No network, no real subprocess, no real repo. |
| `integration` | Touches the real filesystem, git, or the CLI end to end. |
| `network` | Reaches a real package index or downloads `uv`. **Deselected by default.** |
| `slow` | Long-running. |

The default suite is `pytest -m "not network"`. The network-marked tests run on a
scheduled nightly lane, because a live PyPI schema change or a moved `uv` release URL
should fail *somewhere* — just not in every PR.

## Conventions

**Dependencies are injected at seams, not mocked.** Anything that touches the outside
world sits behind a `typing.Protocol` — `RegistryClient`, `UvRunner`, `ProcessRunner`,
`GitClient`, `UvDownloader`, `HooksLocator`. Tests pass a fake; production passes the
real one. If you find yourself reaching for `unittest.mock` to patch an internal, the
seam is probably in the wrong place.

**Tests are Arrange–Act–Assert**, with the three phases commented. Test names state
the behaviour, not the function under test.

**Value objects are frozen dataclasses** (or frozen pydantic models for config).

**Errors carry structure.** `EnvError` has `hook_id` and `reason`; `RegistryError` has
the requirement and index URL. The rendered message is derived from those fields, not
formatted at the raise site.

**Docs are checked against the CLI.** `tests/unit/test_docs_cli_accuracy.py` extracts
every `hooksmith …` invocation written in the docs and walks it against the real click
command tree. If you document a flag before adding it to the CLI, that test fails —
deliberately.

## Commits and PRs

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(runner): skip hooks whose glob matches nothing
fix(registry): pin every artifact hash so pypi hooks install
docs(cli): write the CLI reference
```

The type and any `BREAKING CHANGE:` footer drive the version bump — see
[Versioning & Stability](design/versioning.md).

Branch names are `feat/<slug>` for features and `bug/<slug>` for fixes. Keep a PR to
one concern; if you find an unrelated problem while working, file it rather than
folding it in.

## Working on the docs

```bash
mkdocs serve          # live reload at http://127.0.0.1:8000
mkdocs build --strict # what CI runs — a broken link fails the build
```

`--strict` is not optional in CI: a dead internal link is a bug in a documentation
site, and it is much cheaper to catch here than after publishing.

## Working on the Rust core

The crate lives in `hooksmith-rs/` and is exposed to Python through PyO3. After
changing it, rebuild before running the Python tests:

```bash
maturin develop --release -m hooksmith-rs/Cargo.toml
```

The boundary is deliberately narrow — see [Rust Core](design/rust-core.md) for what
lives on which side and why.
