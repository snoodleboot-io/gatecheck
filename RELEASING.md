# Releasing hooksmith

hooksmith publishes **two** distributions to PyPI:

| Package | Built by | Contents |
|---|---|---|
| `hooksmith-core` | maturin | the compiled PyO3 extension — a platform wheel matrix (Linux x86_64/aarch64, macOS x86_64/arm64, Windows x64), per Python version (cp311, cp312), plus an sdist |
| `hooksmith` | hatchling | the pure-Python host — one universal `py3-none-any` wheel + sdist. Depends on `hooksmith-core`. |

`pip install hooksmith` pulls the host, which pulls the matching core wheel for the
user's platform.

Releases are **trunk-based** — there are no version tags to cut. The version is
computed in CI and everything flows from merging to `main`. See
[`.github/workflows/release.yml`](.github/workflows/release.yml).

---

## How versioning works

The version is `MAJOR.MINOR.PATCH[.devN]`, computed at build time by
[`.github/scripts/calculate_version.py`](.github/scripts/calculate_version.py) and
injected into both distributions by
[`.github/scripts/inject_version.sh`](.github/scripts/inject_version.sh) — into
`src/hooksmith/__about__.py` (host), `hooksmith-rs/Cargo.toml` (core), and the host's
`hooksmith-core==` pin. **Both packages always share one version.**

| Segment | Source |
|---|---|
| `MAJOR` | the `MAJOR_VERSION` env in the workflow — the **only** place it can be bumped. Currently `0`. |
| `MINOR` | the latest `MINOR` for that `MAJOR` on PyPI, **+ 1**. First release starts at `0.1.0`. |
| `PATCH` | the PR number on PR builds; `0` on a push to main. |
| `.devN` | the GitHub run number — TestPyPI previews only. |

Because MINOR is read from PyPI and incremented, **every merge to main is a new
MINOR** (`0.1.0`, `0.2.0`, …). There is no manual version file to edit.

To bump MAJOR (e.g. the first stable `1.0.0`), change `MAJOR_VERSION` in
`release.yml`. MINOR then restarts at `1` for the new major.

---

## The flow

| Event | Version | Publishes to | Gated? |
|---|---|---|---|
| Open / update a PR to `main` | `0.<minor>.<PR>.dev<run>` | **TestPyPI** | no |
| Merge the PR (push to `main`) | `0.<minor>.0` | **PyPI** | **yes — manual approval** |
| `workflow_dispatch` | `0.<minor>.0` | your chosen target | pypi target is gated |

Every build (both events) runs the full two-distribution build + the Linux/macOS/Windows
smoke test first. Only then does a publish job run.

The **push-to-main → PyPI** publish pauses on the `release` GitHub environment and waits
for a human to approve it in the Actions run. That is the checkpoint before anything
reaches real PyPI.

Publishing uses PyPI Trusted Publishing (OIDC) — no API tokens are stored anywhere. The
workflow mints a short-lived token per run.

---

## One-time setup

These need PyPI accounts and repo-admin rights. Do them once, before the first release.

### 1. Trusted Publishers on PyPI (and TestPyPI)

For **each** of `hooksmith` and `hooksmith-core`, on PyPI → the project → *Publishing* →
*Add a new pending publisher*:

| Field | PyPI value | TestPyPI value |
|---|---|---|
| Owner | `snoodleboot-io` | `snoodleboot-io` |
| Repository | `hooksmith` | `hooksmith` |
| Workflow name | `release.yml` | `release.yml` |
| Environment | `release` | `testpypi` |

The PR-preview publish runs in the `testpypi` environment; the real publish runs in
`release`. Bind each accordingly.

### 2. GitHub environments

- **`release`** — must **require a reviewer**. This is the human gate before PyPI.
- **`testpypi`** — no reviewer needed (previews should be automatic on every PR).

Configure both at repo → Settings → Environments.

---

## Rehearsing

Open a PR to `main`: it builds everything and publishes a `.devN` preview to TestPyPI
automatically. Verify:

```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ hooksmith
hooksmith --version
```

(The extra index is needed because the runtime deps live on real PyPI, not TestPyPI.)

`Actions → release → Run workflow` also lets you rehearse on demand (target `testpypi`).

---

## Cutting a real release

There is nothing to tag. **Merge a PR to `main`**, then approve the `release`
environment when the run pauses. Both packages land on PyPI at `0.<minor>.0`.

---

## After the first successful publish

Update [`docs/getting-started/installation.md`](docs/getting-started/installation.md):
drop the "not yet published to PyPI" warning and lead with `pip install hooksmith`. The
from-source instructions become the contributor path.
