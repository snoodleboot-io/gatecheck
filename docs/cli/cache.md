# `gatecheck cache`

Inspect and reclaim the hook environment cache.

```console
$ gatecheck cache why <HOOK>   # why is this hook a hit or a miss?
$ gatecheck cache clear        # reclaim the space
```

## Where the cache lives

```
$XDG_CACHE_HOME/gatecheck/        # ~/.cache/gatecheck by default
├── env-v1/<sha256>/…             # one uv-backed venv per pinned environment
└── bin/uv                        # the bootstrapped uv, if one was downloaded
```

Each environment is addressed by a SHA-256 over `(scheme, package, version, index
URL)`. Nothing about your project path or the hook's id goes into the key, which is
why two hooks — or ten packages in a monorepo — pinning the same tool share a single
venv.

---

## `cache why`

```console
$ gatecheck cache why <HOOK> [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--config FILE` | `check.toml` | Path to the configuration file. |
| `--json` | off | Emit the explanation as JSON. |

Cache behaviour that you can't inspect is indistinguishable from a bug. `why` shows
the whole derivation:

```console
$ gatecheck cache why ruff
hook:      ruff
source:    pypi ruff==0.4.9 @ https://pypi.org/simple  (pypi)
status:    hit — cached venv present — reused on the next run
cache key: c457c8e5d6e9fa66e6ceaad24b12056c95040649193ce946d8b7e7a43baa4b8c
  hashed:  sha256('env-v1' + 'pypi' + 'ruff' + '0.4.9' + 'https://pypi.org/simple')
cache dir: /home/you/.cache/gatecheck/env-v1/c457c8e5…
```

| Status | Meaning |
|---|---|
| `hit` | The venv exists and will be reused. |
| `miss` | No venv yet — the next run builds it. |
| `not-applicable` | A `project` or `system` hook. It reuses a binary already on the machine, so no environment is cached. |

Bump a pinned version and the key changes, so the status flips to `miss` — that's the
mechanism, made visible. `why` never builds anything and never spawns `uv`; it's safe
to run at any time.

An unknown hook id exits non-zero and lists the ids that do exist.

!!! note "`why` may reach the network"

    For a `pypi:` hook, deriving the key requires knowing the resolved *version*, so
    an unpinned requirement (`pypi:ruff>=0.4`) queries the index. An exact pin
    (`pypi:ruff==0.4.9`) resolves locally.

---

## `cache clear`

```console
$ gatecheck cache clear [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--all` | off | Also remove the bootstrapped `uv`, not just the environments. |
| `--dry-run` | off | Report what would be removed, without deleting anything. |

```console
$ gatecheck cache clear --dry-run
Would remove 12 cached environments, freeing 431.7 MiB.

$ gatecheck cache clear
Removed 12 cached environments, freeing 431.7 MiB.
```

Clearing is always safe: every environment is reproducible from `check.toml`, so the
worst case is that the next run rebuilds what it needs. Nothing is lost but time.

`--all` additionally removes the `uv` that gatecheck bootstrapped for itself. Use it
when you want the cache directory genuinely empty; the next run re-downloads `uv`
unless one is already on your `PATH` or `GATECHECK_UV` is set.

Clearing is tolerant of a concurrent run and of a cache that doesn't exist yet:

```console
$ gatecheck cache clear
Removed 0 cached environments, freeing 0 B.
```

!!! warning "There is no partial eviction"

    `clear` removes everything (or everything plus `uv`). gatecheck does not track
    last-used times, so there's no "prune anything older than N days". If you need
    that granularity, delete individual `env-v1/<key>/` directories — `cache why`
    tells you which key belongs to which hook.

## See also

- [`gatecheck sync`](sync.md) — populate the cache deliberately.
- [Air-gapped / Offline](../guides/air-gapped.md) — persisting the cache across CI jobs.
