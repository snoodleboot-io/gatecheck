# Contributing to gatecheck

Thanks for your interest in contributing. This document covers the development workflow, commit conventions, and release process.

## Development model: Trunk-Based Development

gatecheck uses strict trunk-based development:

- **`main` is always releasable.** Every commit that lands on main must pass all tests.
- **Feature branches are short-lived.** Open a PR, get review, merge. Don't let branches live longer than a few days.
- **No long-lived release branches.** Releases are cut from main via tags.
- **No feature flags in version control.** Code that isn't ready ships behind a runtime check or isn't merged.

### Branch naming

```
feature/<short-description>     # new functionality
fix/<short-description>         # bug fixes
chore/<short-description>       # maintenance, deps
docs/<short-description>        # documentation only
ci/<short-description>          # CI/CD changes
```

All branches merge to `main`. Never merge `main` back into a feature branch — rebase instead.

## Commit messages: Conventional Commits

gatecheck uses [Conventional Commits](https://www.conventionalcommits.org/) **strictly**. The CI version computation reads commit messages to determine the next version number.

### Format

```
<type>(<optional scope>): <description>

<optional body>

<optional footers>
```

### Types and their version impact

| Type | Description | Version bump |
|---|---|---|
| `feat` | New user-facing feature | MINOR |
| `fix` | Bug fix | PATCH |
| `perf` | Performance improvement | PATCH |
| `refactor` | Code restructuring, no behaviour change | PATCH |
| `revert` | Reverts a previous commit | PATCH |
| `docs` | Documentation only | none |
| `test` | Tests only | none |
| `chore` | Maintenance, dependency updates | none |
| `ci` | CI/CD pipeline changes | none |
| `style` | Formatting, whitespace | none |
| `build` | Build system changes | none |

### Breaking changes → MAJOR bump

A breaking change causes a MAJOR version bump. Declare it with a `BREAKING CHANGE:` footer:

```
feat(config): rename pass-filenames to pass-files

BREAKING CHANGE: The `pass-filenames` key in check.toml has been renamed
to `pass-files`. Update your configuration accordingly.
```

Or with a `!` after the type:

```
feat!: remove support for Python 3.10
```

**MAJOR bumps can ONLY happen through the CI pipeline.** You cannot bump the major version by manually editing a version file — there are none.

### Good examples

```
feat(workspace): add --affected flag for monorepo execution
fix(env): resolve venv detection failure on Windows paths with spaces
perf(runner): replace Python glob with Rust pattern engine (3x speedup)
docs(config): add examples for all source spec types
test(migration): add coverage for pre-commit-hooks type mapping
chore(deps): update pydantic to 2.7.0
ci: add macOS ARM64 wheel build to release matrix
```

### Bad examples

```
fixed stuff          # not conventional
WIP                  # not conventional
Update README        # not conventional, use docs: Update README
feat: add feature    # too vague — describe what the feature is
```

## Setting up

```bash
# Clone and enter
git clone https://github.com/snoodleboot-io/gatecheck
cd gatecheck

# Install Python deps
uv venv
uv pip install -e ".[dev]"

# Build the Rust extension (requires Rust toolchain)
cd gatecheck-rs
maturin develop --release
cd ..

# Install gatecheck itself as a git hook runner
gatecheck install

# Run tests
pytest tests/ -v
cargo test --manifest-path gatecheck-rs/Cargo.toml
```

## Running checks locally

```bash
# Everything (what CI runs)
gatecheck run --all-files

# Just linting (fast)
gatecheck run lint

# Just Rust
cargo test --manifest-path gatecheck-rs/Cargo.toml
cargo clippy --manifest-path gatecheck-rs/Cargo.toml

# Just Python
pytest tests/ -v --tb=short
```

## Versioning

**You never edit a version number in source.** There are no `VERSION` files, no
`__version__` strings, no `setup.cfg` version fields. The `gatecheck` version is
derived from the git tag by hatch-vcs at build time.

`scripts/compute_version.py` computes what the *next* tag should be, from the tag
history and conventional-commit messages:

1. Find the latest `vX.Y.Z` tag
2. Read all commits since it
3. Determine the bump level from commit types — `feat:` → minor, `fix:`/`perf:`/`refactor:`/`revert:` → patch, a `BREAKING CHANGE:` footer (or `--force-major`) → major, `docs:`/`chore:`/`ci:` alone → no release
4. Print `v(X+1).Y.Z`, `vX.(Y+1).Z`, or `vX.Y.(Z+1)`

```bash
python scripts/compute_version.py
```

You then create that tag yourself and push it (see [Release process](#release-process)).
The script *advises* the version; it does not push tags — tagging is a deliberate human
action so a release is never cut without one.

`gatecheck-core` (the Rust extension) versions separately, from
`gatecheck-rs/Cargo.toml`; bump it when the Rust changes. See
[RELEASING.md](RELEASING.md#versioning-the-two-packages).

## PR process

1. Branch from main: `git checkout -b feature/my-thing`
2. Make changes, commit with conventional commits
3. Push and open a PR against main
4. CI must be green before merge
5. Squash or rebase merges only — no merge commits on main
6. Delete your branch after merge

## Documentation

Docs live in `docs/` and are built with MkDocs Material. To preview locally:

```bash
uv pip install mkdocs-material mkdocs-minify-plugin mkdocs-git-revision-date-localized-plugin mkdocs-macros-plugin
mkdocs serve
```

The `pages` workflow deploys the docs (and the marketing landing page) to GitHub Pages on every merge to `main` that touches `docs/`, `website/` or `mkdocs.yml`.

## Release process

Full details, including the one-time PyPI Trusted Publisher setup, are in
[RELEASING.md](RELEASING.md). In short:

1. **Decide the version.** `python scripts/compute_version.py` reads the
   conventional-commit history since the last tag and prints the next version.
2. **Tag and push** — `git tag vX.Y.Z && git push origin vX.Y.Z`. The tag *is* the
   version.
3. The `release` workflow builds both distributions (`gatecheck` and `gatecheck-core`),
   smoke-tests them on Linux/macOS/Windows, then **pauses on the `release`
   environment** for a manual approval — a human reviews before anything reaches PyPI.
4. On approval it publishes to PyPI via Trusted Publishing (OIDC, no tokens) and creates
   the GitHub release with generated notes.

Tag creation is deliberately a human step, not auto-pushed from `main` — the approval
gate plus an explicit tag are two independent chances to catch a bad release.
