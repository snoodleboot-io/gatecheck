# Environment Strategy

How gatecheck turns `from = "pypi:ruff==0.4.9"` into a runnable tool, and why the cache
is shaped the way it is.

## The problem with cloning

pre-commit's model is: clone a git repo, create an environment from it, hope the repo's
`.pre-commit-hooks.yaml` is correct. That couples *what tool you run* to *a git ref of
a wrapper repo*, and it means every tool author has to maintain a pre-commit shim.

gatecheck's model is: a tool is a **package**. `ruff` is `pypi:ruff==0.4.9` — the same
thing you'd `pip install`. No shim repo, no clone, and the version you pin is the
version that runs.

## Two kinds of source, two strategies

**`system` and `project` reuse what exists.** No environment is built; a filesystem
lookup finds the binary (on `PATH`, or in your venv) and that's it. These are pure and
hermetic — the same inputs always resolve to the same path — and they never touch the
network.

**`pypi:` builds an isolated venv.** The requirement is resolved to an exact version
against the index, then `uv` builds a venv containing just that tool. This is the only
path that touches the network, and only on a cache miss.

## Content-addressed caching

The cache key is a SHA-256 over exactly the inputs that should invalidate an
environment:

```
key = sha256("env-v1" + "pypi" + name + version + index_url)
```

Everything about that choice is deliberate:

- **`version`, not the requirement string.** `pypi:ruff>=0.4` and `pypi:ruff==0.4.9`
  that resolve to the same version share a venv. What you cache is what you'd *run*,
  not how you *asked* for it.
- **`index_url` is in the key.** `mytool==1.0` from a private index and from public
  PyPI are different builds; the key keeps them distinct, so a private package can
  never be served from a public one.
- **The project path is *not* in the key.** Ten hooks, or ten packages in a monorepo,
  pinning `ruff==0.4.9` share **one** venv. The cache is global to the user, addressed
  by content, so the same content is built once.
- **`env-v1` is a scheme tag.** If the key derivation ever has to change, the tag bumps
  and old entries are simply never hit again — no migration, no stale-cache bug.

The hash *input* is what determines reuse, so the cache is as honest as the key. If two
things should share an environment, their keys are equal by construction; if they
shouldn't, they can't collide.

## Atomic builds

A venv is built into a temp directory and then `os.replace`-d into its final slot —
atomically. Three properties fall out of that:

- A **crash mid-build** leaves a temp dir, never a half-populated cache slot that a
  later run would mistake for a hit.
- Two processes **racing** to build the same key both succeed: the loser's atomic
  replace loses, it discards its temp, and it uses the winner's slot. No lock needed.
- A **cache hit skips the build callback entirely** — the healthy slot is returned
  without `uv` ever being consulted. This is what makes [offline runs](../guides/air-gapped.md)
  possible: a warm cache needs no network and no `uv`.

## uv, and bootstrapping it

Environments are built with [uv](https://docs.astral.sh/uv/), which is fast enough that
building a fresh venv isn't the bottleneck a `pip`-based approach would be.

`uv` is a host binary, not a Python dependency. gatecheck finds it via `GATECHECK_UV`,
then `PATH`, and if it's absent, **bootstraps** a pinned, checksum-verified copy into
the cache (`~/.cache/gatecheck/bin/uv`) — a one-time download from Astral's releases,
verified against a hardcoded SHA-256. The download is behind an injectable seam, so the
whole environment layer unit-tests offline against a fake.

`GATECHECK_NO_BOOTSTRAP` forbids the download, turning a missing `uv` into a clear error
rather than an attempted fetch — the right behaviour for a locked-down runner.

## Integrity: every artifact hash

When `uv` installs a `pypi:` tool, gatecheck pins **every** known artifact hash for the
resolved version under `--require-hashes`, not just one representative wheel. A
distribution ships one wheel per platform, and the installer resolves the wheel for the
*current* machine — so pinning a single hash would fail everywhere but the machine that
computed it. Listing them all (the lockfile pattern) means the install succeeds and is
still hash-verified. (This was learned the hard way; see the
[changelog](../changelog.md).)

## Explainability

Cache behaviour you can't see is indistinguishable from a bug, so it's inspectable:

```console
$ gatecheck cache why ruff
source:    pypi ruff==0.4.9 @ https://pypi.org/simple  (pypi)
status:    hit — cached venv present — reused on the next run
cache key: c457c8e5…
  hashed:  sha256('env-v1' + 'pypi' + 'ruff' + '0.4.9' + 'https://pypi.org/simple')
```

`why` derives the same key `resolve` would, and reports hit or miss, without building
anything. If the cache surprises you, it can show you why it did what it did.

## Where it lives

```
$XDG_CACHE_HOME/gatecheck/
├── env-v1/<sha256>/…   # one venv per (name, version, index)
└── bin/uv              # the bootstrapped uv
```

Reclaim it with [`gatecheck cache clear`](../cli/cache.md); everything is reproducible
from `check.toml`, so the worst case of clearing is a rebuild.

## See also

- [Source Types](../config/sources.md) — choosing `pypi:` / `project` / `system`.
- [`gatecheck sync`](../cli/sync.md) and [`cache`](../cli/cache.md) — driving it.
- [Air-gapped / Offline](../guides/air-gapped.md) — the warm-cache pattern.
