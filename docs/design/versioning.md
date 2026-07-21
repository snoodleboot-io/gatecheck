# Versioning & Stability

gatecheck follows [Semantic Versioning 2.0.0](https://semver.org/) with one strict constraint:

> **The MAJOR version can only be bumped through CI.**

## The rule

There are no `VERSION` files. No `__version__ = "..."` strings to keep in sync. No `pyproject.toml` version fields to update before releasing. The version number lives exclusively in git tags, and CI computes and creates those tags.

This means:

- A developer cannot accidentally release a major version by editing a file
- The release history is always consistent with the commit history
- The changelog is always generated from the actual commits, not from what someone remembered to write

## How versions are computed

CI runs `scripts/compute_version.py` on every push to `main`. It:

1. Finds the most recent `vX.Y.Z` tag via `git describe`
2. Reads all commits since that tag using `git log`
3. Parses each commit message for Conventional Commits syntax
4. Determines the bump level from the highest-priority commit type

```
Commit types → bump level
─────────────────────────
BREAKING CHANGE footer  → MAJOR
feat:                   → MINOR  
fix: / perf: / refactor:→ PATCH
docs: / test: / chore:  → (none)
```

5. Outputs the next version to GitHub Actions outputs
6. If there are releasable commits, the release job creates the tag

## The MAJOR bump special case

A MAJOR bump requires one of:

1. **A `BREAKING CHANGE:` footer** in any commit message since the last tag:
   ```
   feat(config): rename pass-filenames to pass-files
   
   BREAKING CHANGE: The `pass-filenames` key in check.toml has been renamed
   to `pass-files`. Update the key in your check.toml.
   ```

2. **A `!` after the type** (shorthand):
   ```
   feat!: drop Python 3.10 support
   ```

3. **Manual workflow dispatch** with `bump_major = true` — for cases where a MAJOR bump is appropriate but the commit message doesn't cleanly express it (rare).

This is intentional friction. Bumping MAJOR means committing to a backwards-incompatible change. Having to make that declaration in the commit message itself means it's tied to the specific commit that introduces the break, making the git history self-documenting.

## Commit message policy

All commits on `main` must follow [Conventional Commits](https://www.conventionalcommits.org/). The branch protection ruleset enforces this via a commit message regex:

```
^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9-]+\))?(!)?: .{1,100}
```

PR titles are also validated (squash merges use the PR title as the commit message).

## Stability policy

### `0.x.y` — initial development

In the `0.x.y` range, MINOR bumps may include breaking changes. This is standard semver for pre-1.0 software. Once the API stabilises, we'll ship `1.0.0`.

### `1.x.y` and above

Full semver guarantees:
- PATCH: backwards-compatible bug fixes only
- MINOR: backwards-compatible new features
- MAJOR: backwards-incompatible changes, with migration path documented

### Deprecation policy

Features deprecated in `X.Y.0` are removed no earlier than `X+1.0.0`. Deprecation warnings are emitted at runtime for at least one minor version before removal.

## Release cadence

gatecheck does not follow a fixed release calendar. Releases happen when releasable commits accumulate on `main`. In practice this means:

- Bug fixes ship within days of landing on `main`
- Features ship when they're ready (typically with the PR that adds them)
- There are no "release trains" or scheduled dates

## Version in code

The package version is read at runtime from the installed package metadata:

```python
# src/gatecheck/__init__.py
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("gatecheck")
except PackageNotFoundError:
    __version__ = "0.0.0+dev"  # running from source, uninstalled
```

This means the version in code is always derived from the installed package, which is always derived from the git tag. No manual sync required.

## Verifying the next version locally

```bash
python scripts/compute_version.py
# Current version : 0.2.1
# Commits analysed: 7
# Bump level      : MINOR
# Next version    : 0.3.0
```

With `--force-major`:

```bash
python scripts/compute_version.py --force-major=true
# Bump level      : MAJOR
# Next version    : 1.0.0
```
