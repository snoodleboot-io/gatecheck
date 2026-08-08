# Versioning & Stability

hooksmith follows [Semantic Versioning 2.0.0](https://semver.org/) with one strict constraint:

> **The MAJOR version can only be bumped through CI.**

## The rule

There are no `VERSION` files to hand-edit and no version tags to cut. The version is
**computed in CI at build time** from PyPI history plus the GitHub event, then injected
into both distributions before they build. A developer cannot release a particular
version by editing a file — the pipeline decides it.

## How versions are computed

The version is `MAJOR.MINOR.PATCH[.devN]`, produced by
[`.github/scripts/calculate_version.py`](https://github.com/snoodleboot-io/hooksmith/blob/main/.github/scripts/calculate_version.py):

| Segment | Source |
|---|---|
| `MAJOR` | the `MAJOR_VERSION` env in `release.yml` — the **only** place it can change. Currently `0`. |
| `MINOR` | the latest `MINOR` for that `MAJOR` published on PyPI, **+ 1**. First release starts at `0.1.0`. |
| `PATCH` | the PR number on PR builds; `0` on a push to `main`. |
| `.devN` | the GitHub run number — TestPyPI preview builds only. |

Because MINOR is read back from PyPI and incremented, **every merge to `main` is a new
MINOR** (`0.1.0`, `0.2.0`, …). Nothing to remember, nothing to sync.

## The MAJOR bump special case

Bumping MAJOR — for example cutting the first stable `1.0.0` — is a deliberate edit to
`MAJOR_VERSION` in [`release.yml`](https://github.com/snoodleboot-io/hooksmith/blob/main/.github/workflows/release.yml).
MINOR then restarts at `1` for the new major. This is intentional friction: a MAJOR bump
means committing to a backwards-incompatible change, so it lives in a reviewed change to
the release workflow rather than falling out of a commit message.

## Both distributions, one version

hooksmith ships two packages — the `hooksmith` host and the compiled `hooksmith-core`.
[`inject_version.sh`](https://github.com/snoodleboot-io/hooksmith/blob/main/.github/scripts/inject_version.sh)
writes the single computed version into `src/hooksmith/__about__.py` (host),
`hooksmith-rs/Cargo.toml` (core), and the host's `hooksmith-core==` pin, so a given
release is always the *same* version across both.

## Commit message policy

All commits on `main` follow [Conventional Commits](https://www.conventionalcommits.org/),
enforced by the `commit-msg` hook (`cz check`) and by branch protection. This keeps the
history readable and PR titles meaningful (squash merges use the PR title). It no longer
drives version numbers — that is PyPI's job now — but it remains the house style.

## Stability policy

### `0.x.y` — initial development

In the `0.x.y` range, MINOR bumps may include breaking changes. This is standard semver
for pre-1.0 software. Once the API stabilises, we'll ship `1.0.0` by bumping
`MAJOR_VERSION`.

### `1.x.y` and above

Full semver guarantees:
- PATCH: backwards-compatible bug fixes only
- MINOR: backwards-compatible new features
- MAJOR: backwards-incompatible changes, with migration path documented

### Deprecation policy

Features deprecated in `X.Y.0` are removed no earlier than `X+1.0.0`. Deprecation
warnings are emitted at runtime for at least one minor version before removal.

## Release cadence

hooksmith does not follow a fixed release calendar. Because a release *is* a merge to
`main` (behind a manual approval before PyPI), features and fixes ship when their PR
lands. There are no "release trains" or scheduled dates.

## Version in code

The package version is read at runtime from the installed package metadata, falling back
to the injected placeholder when running from an uninstalled checkout:

```python
# src/hooksmith/__init__.py
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("hooksmith")
except PackageNotFoundError:
    from hooksmith.__about__ import __version__  # source checkout, uninstalled
```

`src/hooksmith/__about__.py` holds a `0.0.0.dev0` placeholder locally; CI rewrites it to
the computed version at build time. See [Releasing hooksmith](https://github.com/snoodleboot-io/hooksmith/blob/main/RELEASING.md)
for the full flow.
