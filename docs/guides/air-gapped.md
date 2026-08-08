# Air-gapped / Offline Runs

hooksmith can run in a no-egress environment — a sandboxed CI job, a locked-down
build agent, or a fully air-gapped network. The model is **two phases**:

1. **Warm the cache online.** In a step that *does* have network, run `hooksmith sync`
   to pin every `pypi:` hook and build its uv-backed environment into the
   content-addressed cache.
2. **Run offline.** In the no-egress step, run `hooksmith run --offline`. Nothing
   touches the network; every environment is served from the warm cache, and a cache
   miss is a clear, immediate error instead of a hang.

## Offline mode

Offline mode is a single signal: the `HOOKSMITH_OFFLINE` environment variable (set by
`--offline`). When it is active:

- **`pypi:` hooks** are resolved **locally**. The package index is never queried, so a
  hook must carry an **exact pin** (`from = "pypi:ruff==0.4.9"`). A range or bare name
  (`pypi:ruff`, `pypi:ruff>=0.4`) cannot be resolved without the index and raises a
  clear error telling you to pin it or run `hooksmith sync` online first.
- A **cache hit** runs with zero network — no index query, no `uv`, no download.
- A **cache miss** fails fast: *"offline: no cached environment for `ruff==0.4.9`; run
  `hooksmith sync` while online first to warm the cache."*
- **`system:` / `project:` hooks** are unaffected — they reuse a binary already on the
  machine and never needed the network.

## Hooks that need network at run time

Some hooks reach the network when they *run* (a linter that phones home, a
license-check that queries an API). These can't work offline, but they shouldn't fail
the run either. Mark them so an offline run **skips** them with a clear reason instead:

```toml
[[hook]]
id  = "license-audit"
from = "pypi:my-audit==1.2.0"
run = "my-audit"
when = { requires-network = true }
```

Online, the hook runs normally. Offline (`HOOKSMITH_OFFLINE` / `run --offline`), it is
skipped — not failed — and shown distinctly in the report:

```
skip  license-audit  (requires network — skipped in offline mode)

1 passed, 1 skipped
```

The exit code stays `0`: a network-skip is a skip, not a failure.

```bash
# Pin exactly so offline resolution is deterministic.
# check.toml → from = "pypi:ruff==0.4.9"

# online prep step
hooksmith sync

# no-egress step
hooksmith run --offline        # or: HOOKSMITH_OFFLINE=1 hooksmith run
```

## The cache

Environments live under the user cache dir, keyed by a SHA-256 of
`(scheme, package, version, index-url)`:

```
$XDG_CACHE_HOME/hooksmith/        # ~/.cache/hooksmith by default
├── env-v1/<sha256>/…             # one uv-backed venv per pinned environment
└── bin/uv                        # the bootstrapped uv (if auto-bootstrapped)
```

Persist that directory across jobs and the offline step needs no network at all.

## CI cache-restore recipe (GitHub Actions)

Warm the cache in a network-enabled job (or step), key it on `check.toml`, then restore
it in the sandboxed job and run offline:

```yaml
jobs:
  hooksmith:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Restore (or later save) the content-addressed environment cache.
      - uses: actions/cache@v4
        with:
          path: ~/.cache/hooksmith
          key: hooksmith-${{ runner.os }}-${{ hashFiles('check.toml') }}

      # Network-enabled: pin + build any missing environments.
      - run: hooksmith sync

      # No-egress: everything is served from the warm cache.
      - run: hooksmith run --offline --all-files
```

The cache key is `check.toml`'s hash, so it invalidates exactly when your pinned tools
change. On a hit, `hooksmith sync` finds every environment already present and builds
nothing; `hooksmith run --offline` then executes with no network.

## Internal indexes

If your air-gapped network has an **internal mirror** rather than no network at all,
you do not need offline mode — point hooksmith at the mirror instead:

```toml
[sources]
default-registry = "https://pypi.internal.example.com/simple"

# or a named alias, used as pypi+internal:ruff==0.4.9
[sources.extra-registries]
internal = "https://pypi.internal.example.com/simple"
```

See [Private Registries](private-registries.md).

## uv bootstrap

Building a `pypi:` environment needs `uv`. hooksmith auto-bootstraps a pinned `uv` into
the cache on first use — a one-time network download. In an air-gapped runner this must
already be present:

- Warm it in the online `hooksmith sync` step (it lands at `~/.cache/hooksmith/bin/uv`
  and is restored with the rest of the cache), **or**
- Provide `uv` yourself and set `HOOKSMITH_UV=/path/to/uv`, **or**
- Set `HOOKSMITH_NO_BOOTSTRAP=1` to forbid the download (a missing `uv` then becomes a
  clear error rather than an attempted fetch).

In `--offline` runs a cache hit never needs `uv` at all, so a fully warm cache sidesteps
this entirely.
