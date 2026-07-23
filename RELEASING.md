# Releasing gatecheck

gatecheck publishes **two** distributions to PyPI:

| Package | Built by | Contents |
|---|---|---|
| `gatecheck-core` | maturin | the compiled PyO3 extension — a platform wheel matrix (Linux x86_64/aarch64, macOS x86_64/arm64, Windows x64), per Python version (cp311, cp312), plus an sdist |
| `gatecheck` | hatchling | the pure-Python host — one universal `py3-none-any` wheel + sdist. Depends on `gatecheck-core`. |

`pip install gatecheck` pulls the host, which pulls the matching core wheel for the
user's platform.

Publishing is automated by [`.github/workflows/release.yml`](.github/workflows/release.yml):
build both distributions → smoke-test them on Linux/macOS/Windows → **wait for manual
approval** → publish via PyPI Trusted Publishing (OIDC, no tokens) → create the GitHub
release.

---

## One-time setup

These cannot be scripted from CI — they need PyPI accounts and repo-admin rights. Do
them once, before the first release.

### 1. Create both PyPI projects with a Trusted Publisher

For **each** of `gatecheck` and `gatecheck-core`, on PyPI → the project → *Publishing* →
*Add a new pending publisher* (or *Manage → Publishing* if the project already exists):

| Field | Value |
|---|---|
| Owner | `snoodleboot-io` |
| Repository | `gatecheck` |
| Workflow name | `release.yml` |
| Environment | `release` |

Do the same on [TestPyPI](https://test.pypi.org/) if you want to rehearse (recommended
for the first release — see below).

No API tokens are stored anywhere. The workflow mints a short-lived OIDC token per run,
which PyPI trusts because of the binding above.

### 2. The `release` GitHub environment

Already created, and it **requires a reviewer** — the publish job pauses until someone
with access approves it in the Actions run. That is the human checkpoint before
anything reaches PyPI.

To change reviewers: repo → Settings → Environments → `release`.

---

## Cutting a release

### Rehearse on TestPyPI first (recommended for the first real release)

Actions → **release** → *Run workflow* → target `testpypi`. This builds everything,
smoke-tests it, waits for your approval, then publishes to TestPyPI. Verify:

```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ gatecheck
gatecheck --version
```

(The extra index is needed because the runtime deps live on real PyPI, not TestPyPI.)

### Publish for real

1. **Decide the version.** `scripts/compute_version.py` reads the conventional-commit
   history since the last tag and prints the next version:

   ```bash
   python scripts/compute_version.py
   ```

   `feat:` → minor, `fix:`/`perf:`/`refactor:` → patch, `BREAKING CHANGE:` → major,
   `docs:`/`chore:`/`ci:` alone → no release.

2. **Tag and push.** The tag is the version:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

3. **Approve.** The workflow builds, smoke-tests, then pauses on the `release`
   environment. Approve it in the Actions run.

4. Done — both packages are on PyPI and a GitHub release exists with the wheels
   attached and auto-generated notes.

---

## Versioning the two packages

They version **independently**, on purpose:

- `gatecheck` takes its version from the **git tag** (hatch-vcs). Every tag ships a new
  host.
- `gatecheck-core` takes its version from **`gatecheck-rs/Cargo.toml`**. It only needs
  republishing when the Rust changes.

The core publish uses `skip-existing`, so tagging a Python-only release doesn't error on
the already-published core.

> **When you change the Rust core, bump `version` in `gatecheck-rs/Cargo.toml`** (and,
> if the host needs the new core, the `gatecheck-core>=…` floor in `pyproject.toml`).
> Because `skip-existing` swallows a duplicate, forgetting the bump means the new core
> is silently *not* published — so treat a Cargo version bump as part of any core change.

---

## After the first successful publish

Update [`docs/getting-started/installation.md`](docs/getting-started/installation.md):
drop the "not yet published to PyPI" warning and lead with `pip install gatecheck`. The
from-source instructions become the contributor path.
