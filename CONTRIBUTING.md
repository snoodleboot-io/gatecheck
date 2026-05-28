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

**You never touch a version number.** There are no `VERSION` files, no `__version__` strings to update, no `setup.cfg` version fields.

The CI pipeline computes the version from the git tag history and conventional commit messages:

1. Find the latest `vX.Y.Z` tag
2. Read all commits since that tag
3. Determine bump level from commit types
4. Compute and tag `v(X+1).Y.Z`, `vX.(Y+1).Z`, or `vX.Y.(Z+1)`

If you want to understand what version a release would be, run:

```bash
python scripts/compute_version.py
```

**The only way to bump MAJOR is:**
1. Add `BREAKING CHANGE:` footer to a commit message, OR
2. Trigger the CI workflow manually with `bump_major = true`

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

Docs deploy automatically on merge to main (as the `dev` alias) and on each release (as a versioned alias).

## Release process

Releases are fully automated. You do not manually trigger a release.

1. Commits land on `main` via PRs
2. CI computes the next version from conventional commits
3. If there are releasable commits (feat/fix/perf/refactor), CI:
   - Creates a `vX.Y.Z` git tag
   - Builds wheels for all supported platforms
   - Publishes to PyPI via trusted publishing (OIDC)
   - Creates a GitHub release with generated changelog
   - Deploys versioned docs

The `release` GitHub Actions environment requires a manual approval step before publishing. This gives a human the chance to review the computed version and changelog before it goes out.
