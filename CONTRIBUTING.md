# Contributing to hooksmith

Thanks for your interest in contributing. This document covers the development workflow, commit conventions, and release process.

## Development model: Trunk-Based Development

hooksmith uses strict trunk-based development:

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

hooksmith uses [Conventional Commits](https://www.conventionalcommits.org/) **strictly**. The CI version computation reads commit messages to determine the next version number.

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
git clone https://github.com/snoodleboot-io/hooksmith
cd hooksmith

# Install Python deps
uv venv
uv pip install -e ".[dev]"

# Build the Rust extension (requires Rust toolchain)
cd hooksmith-rs
maturin develop --release
cd ..

# Install hooksmith itself as a git hook runner
hooksmith install

# Run tests
pytest tests/ -v
cargo test --manifest-path hooksmith-rs/Cargo.toml
```

## Running checks locally

```bash
# Everything (what CI runs)
hooksmith run --all-files

# Just linting (fast)
hooksmith run lint

# Just Rust
cargo test --manifest-path hooksmith-rs/Cargo.toml
cargo clippy --manifest-path hooksmith-rs/Cargo.toml

# Just Python
pytest tests/ -v --tb=short
```

## Versioning

**You never edit a version number in source.** There are no `VERSION` files to bump and
no tags to cut. The version is **computed in CI at build time** — `MAJOR.MINOR.PATCH`
where MAJOR is pinned in the workflow, MINOR is the latest on PyPI + 1, and PATCH is the
PR number (or `0` on a push to main). Both distributions (`hooksmith` and
`hooksmith-core`) get that one version injected before they build.

`src/hooksmith/__about__.py` carries a `0.0.0.dev0` placeholder for local installs; CI
rewrites it (and `hooksmith-rs/Cargo.toml`, and the `hooksmith-core==` pin) per build.
See [docs/design/versioning.md](docs/design/versioning.md) and
[RELEASING.md](RELEASING.md) for the full model.

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
[RELEASING.md](RELEASING.md). In short — it's **trunk-based, no tags**:

1. **Open a PR to `main`.** The `release` workflow builds both distributions, smoke-tests
   them on Linux/macOS/Windows, and publishes a `.devN` preview to **TestPyPI**.
2. **Merge the PR.** The push to `main` rebuilds at `0.<minor>.0` and **pauses on the
   `release` environment** — a human approves before anything reaches PyPI.
3. On approval it publishes both packages to PyPI via Trusted Publishing (OIDC, no
   tokens).

The MINOR number comes from PyPI, so every merge is a fresh release. To bump MAJOR, edit
`MAJOR_VERSION` in `.github/workflows/release.yml`.
