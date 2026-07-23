# `gatecheck sync`

Build every hook's environment ahead of time, so the first run isn't the slow one.

```console
$ gatecheck sync [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--config FILE` | discovered | Path to the config. Default: found by searching upward for `check.toml` or a `[tool.gatecheck]` `pyproject.toml`. |

`run` builds environments on demand anyway, so `sync` is never *required* — it just
moves the cost somewhere you'd rather pay it: a setup step, a CI prep job, or a
network-enabled stage before an [air-gapped run](../guides/air-gapped.md).

## Output

```console
$ gatecheck sync
built   ruff
cached  mypy
ready   cargo-clippy
ERROR   house-style
        cannot resolve environment for hook 'house-style': tool 'house-style' not found on PATH

3 ready, 1 error
```

| Status | Meaning |
|---|---|
| `built` | A uv-backed venv was created for this hook. |
| `cached` | A matching environment already existed — nothing to do. |
| `ready` | A `project` or `system` hook. It reuses a binary that's already on the machine, so there's no environment to build. |
| `ERROR` | The environment could not be resolved. The reason is printed underneath. |

Exit code is `1` if any hook errored, else `0`.

Sync is not all-or-nothing: one broken hook doesn't stop the others from being built,
so a single run tells you about every problem at once.

## What "cached" means

Environments are content-addressed on `(package, version, index URL)`. Two hooks — or
two packages in a monorepo — asking for `pypi:ruff==0.4.9` from the same index resolve
to the same cache key and share one venv.

That's why `sync` is cheap to re-run: it only builds what genuinely isn't there yet.

```console
$ gatecheck sync    # second time
cached  ruff
cached  mypy
ready   cargo-clippy

3 ready, 0 error
```

Use [`gatecheck cache why <hook>`](cache.md) to see the key and whether it's a hit.

## In CI

Cache the environment directory and `sync` becomes a no-op on subsequent runs:

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/gatecheck
    key: gatecheck-${{ runner.os }}-${{ hashFiles('check.toml') }}

- run: gatecheck sync
- run: gatecheck run --base "$GITHUB_BASE_REF"
```

Keying on `check.toml` invalidates the cache exactly when your pinned tools change.

## Air-gapped runners

`sync` is the network-enabled half of the air-gapped pattern: warm the cache where
there *is* egress, then run offline against it.

```bash
gatecheck sync                  # network available
gatecheck run --offline         # no egress; a cache miss is a clear error
```

See the [air-gapped guide](../guides/air-gapped.md) for the full recipe, including why
offline mode requires exact version pins.

## See also

- [`gatecheck cache`](cache.md) — inspect and reclaim what `sync` built.
- [Source Types](../config/sources.md) — which `from` values need an environment at all.
