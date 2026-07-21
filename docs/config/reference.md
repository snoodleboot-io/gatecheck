# check.toml Reference

gatecheck is configured via `check.toml`. In a monorepo, each package can have its own `check.toml` that inherits from the workspace root.

## Locating the file

Commands read `check.toml` from the current directory. Point elsewhere with `--config PATH`:

```bash
gatecheck run --config config/check.toml
```

!!! note "No `pyproject.toml` support or upward search yet"

    Config currently lives in a `check.toml` you run against directly. Reading
    `[tool.gatecheck]` from `pyproject.toml`, and searching upward from a
    subdirectory, are both planned but **not yet implemented**
    ([GAT-48](https://linear.app/snoodleboot/issue/GAT-48)). For now, run from the
    directory that holds `check.toml`, or pass `--config`.

## Top-level sections

| Section | Description |
|---|---|
| `[sources]` | Registry configuration |
| `[[hook]]` | Hook definitions (array of tables) |
| `[group.<name>]` | Named execution groups |
| `[workspace]` | Monorepo / workspace settings |
| `[package]` | Per-package settings (in package-level configs) |

---

## `[sources]`

```toml
[sources]
default-registry = "https://pypi.org/simple"  # default
extra-registries = { internal = "https://pkg.example.com/simple" }
```

The equivalent sub-table form is also accepted:

```toml
[sources.extra-registries]
internal = "https://pkg.example.com/simple"
```

| Field | Type | Default | Description |
|---|---|---|---|
| `default-registry` | string | PyPI | Index URL for `pypi:` sources |
| `extra-registries` | dict of `alias → url` | `{}` | Named private indexes. Each alias must match `[A-Za-z0-9_-]+` and map to a non-empty index URL. A `pypi+<alias>:` source resolves against `extra-registries[<alias>]`. |

---

## `[[hook]]`

Each `[[hook]]` table defines one hook. The double brackets mean it's an array — multiple `[[hook]]` blocks are collected in order.

### Required fields

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier. Referenced by `[group.<name>].hooks` and `depends-on`. |
| `from` | string | Source spec — see [Source Types](sources.md). |
| `run` | string | Command to execute. `{files}` is replaced with matching staged files. |

### Optional fields

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | same as `id` | Human-readable display name |
| `pass-files` | bool | `true` | Whether to append matching files to the command |
| `files` | string | (all) | Glob pattern — only files matching this pattern are passed |
| `exclude` | string | (none) | Glob pattern — files matching this are excluded |
| `depends-on` | list of strings | `[]` | Hook IDs this hook must run after |
| `fail-fast` | bool | `false` | Stop all hooks if this one fails |
| `packages` | list of strings | (all) | Workspace: restrict this hook to specific packages |
| `when` | inline table | (always) | Conditional execution — see below |

### `when` conditions

All conditions are AND-ed. A hook only runs when all present conditions pass.

```toml
[[hook]]
id = "mypy"
from = "project"
run = "mypy src/"
when = { env-not = "SKIP_MYPY", branch-not = "release/*" }
```

| Key | Type | Description |
|---|---|---|
| `branch` | string | Run only on this exact branch name |
| `branch-not` | glob | Skip when the current branch matches this glob (e.g. `release/*`) |
| `branch-matches` | glob | Run only when the current branch matches this glob |
| `files-match` | glob | Run only if at least one changed file matches |
| `env` | string | Run only if this env var is set |
| `env-not` | string | Skip if this env var is set |
| `on-ci` | bool | `true` = CI only, `false` = never on CI |
| `requires-network` | bool | `true` = **skip** (not fail) when the run is offline (`GATECHECK_OFFLINE` / `run --offline`) |

All glob patterns are `fnmatch`-style and case-sensitive (as with the `files` /
`exclude` globs), so `/` is matched like any other character. CI is detected via the
`CI` or `GITHUB_ACTIONS` environment variables. The branch conditions read the
current branch via `git branch --show-current` (empty on a detached HEAD, in which
case the branch conditions do not apply). Conditions are checked in the order above;
the first one that fails is the reported skip reason.

### Full hook example

```toml
[[hook]]
id          = "mypy"
name        = "Type checker"
from        = "project"
run         = "mypy src/ --config-file mypy.ini"
pass-files  = false
depends-on  = ["ruff"]
fail-fast   = false
packages    = ["api", "worker"]   # workspace only
when = {
  env-not       = "SKIP_MYPY",
  branch-not    = "release/*",
  on-ci         = false
}
```

---

## `[group.<name>]`

Groups are named collections of hooks with execution settings.

```toml
[group.lint]
hooks     = ["ruff", "ruff-format", "isort"]
parallel  = true
fail-fast = true
on-event  = "commit"
```

| Field | Type | Default | Description |
|---|---|---|---|
| `hooks` | list of strings | required | Hook IDs to include |
| `parallel` | bool | `false` | Run this group's hooks concurrently. When `false`, hooks run **serially** (one at a time), still in dependency order |
| `fail-fast` | bool | `false` | Stop scheduling new hooks after the first failure |
| `max-workers` | int ≥ 1 | 4 | Max hooks in flight at once when `parallel = true` (the concurrency cap) |
| `on-event` | string | (none) | Git event: `"commit"` or `"push"` |

When `on-event` is set and `gatecheck install` is run, this group is automatically wired to the corresponding git hook — `commit` → `.git/hooks/pre-commit`, `push` → `.git/hooks/pre-push`. Several groups may target the same event; they are written into that hook in declared order. Any other value is rejected at config load.

---

## `[workspace]`

Present only in the workspace root config (top-level monorepo).

```toml
[workspace]
packages = ["packages/*", "libs/*", "services/api"]
inherit  = "merge"
```

| Field | Type | Default | Description |
|---|---|---|---|
| `packages` | list of globs/paths | required | Package directories to include |
| `inherit` | `"merge"` \| `"override"` \| `"none"` | `"merge"` | How package configs relate to root |

### Inheritance modes

- **`merge`** — package config layered on top of root. Child hooks with the same `id` override parent hooks. Groups are merged the same way.
- **`override`** — package config replaces root entirely. Use when a package has a completely different tool stack.
- **`none`** — package config is standalone. Root hooks do not run for this package.

---

## `[package]`

Present only in package-level configs (inside a workspace package directory).

```toml
[package]
depends-on = ["shared", "utils"]
python     = "3.9"
inherit    = "merge"
```

| Field | Type | Default | Description |
|---|---|---|---|
| `depends-on` | list of strings | `[]` | Package names this package depends on. Used by `--affected` to propagate execution to downstream packages when a dependency changes. |
| `python` | string | — | **Accepted but not yet honoured.** The field validates, but nothing reads it — environments are built with whatever interpreter `uv` selects. Tracked in [GAT-47](https://linear.app/snoodleboot/issue/GAT-47). |
| `inherit` | `"merge"` \| `"override"` \| `"none"` | workspace default | Per-package override of the workspace inherit mode |

---

## Source spec syntax

The `from` field accepts a URI-style source spec:

| Spec | Example | Description |
|---|---|---|
| `pypi:<spec>` | `pypi:ruff>=0.4,<1` | Public PyPI; PEP 440 specifiers supported |
| `pypi+<alias>:<spec>` | `pypi+internal:my-linter==1.0` | Private registry (alias from `[sources]`) |
| `project` | `project` | A tool already in the project's venv (`$VIRTUAL_ENV` or `.venv`) |
| `system` | `system` | A tool already on `PATH` — no environment management |

!!! warning "Not yet supported: `local:`, `git:`, `docker:`"

    These three schemes **parse** — a `check.toml` using them loads without a syntax
    error — but resolving one raises `'<scheme>' sources are not supported`. They are
    recognized so the error is clear rather than a confusing parse failure, and so
    they are reserved rather than silently reinterpreted.

    Today, reach for `system` (a tool your image or machine already provides) or
    `pypi:` (anything published to an index, including your own private one).

See [Source Types](sources.md) for detailed documentation on each source type.

### Parsed source model

For tools that need to classify a hook's `from` spec, `gatecheck.sources.parse_source` turns the raw string into a typed, validated model. It performs **pure parsing only** — no filesystem, network, or subprocess access — and is the entry point the resolver and runner use to `match` on a source's kind without re-parsing the raw string.

```python
from gatecheck.sources import parse_source

parse_source("pypi:ruff>=0.4,<1")
# PyPISource(kind='pypi', requirement='ruff>=0.4,<1', registry=None)

parse_source("pypi+internal:org-linter==2.1.0")
# PyPISource(kind='pypi', requirement='org-linter==2.1.0', registry='internal')

parse_source("project")   # ProjectSource(kind='project')
parse_source("system")    # SystemSource(kind='system')
```

`parse_source` returns one of four frozen models, unified by the `ParsedSource` union and discriminated by a `kind` literal:

| Model | `kind` | Fields | Returned for |
|---|---|---|---|
| `PyPISource` | `"pypi"` | `requirement: str`, `registry: str \| None` | `pypi:<req>`, `pypi+<alias>:<req>` |
| `ProjectSource` | `"project"` | (none) | `project` |
| `SystemSource` | `"system"` | (none) | `system` |
| `UnsupportedSource` | `"unsupported"` | `scheme: "local" \| "git" \| "docker"` | `local:…`, `git:…`, `docker:…` |

The `requirement` string is carried through **verbatim** — it is not PEP 508 / version-range validated here (that is resolution's concern). `registry` is the `[sources]` alias name, or `None` for the default registry; it is not resolved against `[sources]` at parse time.

Because `ParsedSource` is a `kind`-discriminated union, callers can branch with structural pattern matching:

```python
from gatecheck.sources import (
    parse_source, PyPISource, ProjectSource, SystemSource, UnsupportedSource,
)

match parse_source(spec):
    case PyPISource(requirement=req, registry=reg): ...
    case ProjectSource(): ...
    case SystemSource(): ...
    case UnsupportedSource(scheme=scheme): ...
```

#### Unsupported vs. invalid

These are distinct outcomes:

- **Unsupported (recognized).** `local:`, `git:`, and `docker:` are recognized schemes that FEAT-0002 does not yet resolve. `parse_source` returns an `UnsupportedSource` for them — it does **not** raise — so the caller can emit a "not yet supported" message rather than "unknown source". A hook with such a `from` therefore loads cleanly through `load_config`.
- **Invalid.** A syntactically malformed spec raises `SourceSpecError` (a `ValueError` subclass) with the message form `invalid source spec '<spec>': <reason>`. Invalid cases include an empty/whitespace spec, a bare word other than `project`/`system` (e.g. `ruff`), an unknown scheme (e.g. `bogus:thing`, and also `project:x` / `system:x` since those keywords take no payload), an empty `pypi:` requirement, and a malformed `pypi+<alias>:` spec (missing colon, empty alias, alias not matching `[A-Za-z0-9_-]+`, or empty requirement).

When the spec came from a loaded `check.toml`, `load_config` catches the `SourceSpecError` and re-raises it as a `ConfigError` with `check.toml:LINE:COL:` context anchored at the offending hook's `from` key, naming both the bad spec and the hook id. `parse_source` itself stays location- and I/O-free; only the translation lives in the config layer.

### Resolving `project` / `system` sources

Where `parse_source` gives a `from` spec *meaning*, `gatecheck.sources.resolve_source` gives the two non-network kinds *location* — it turns a `SystemSource` or `ProjectSource` into a concrete, absolute executable on this machine. It is a **filesystem lookup only**: no network, no venv creation, no subprocess execution. It resolves what already exists; it never builds an environment.

```python
from gatecheck.sources import parse_source, resolve_source

resolve_source(parse_source("system"), "ruff")
# ResolvedTool(tool='ruff', executable=PosixPath('/usr/bin/ruff'), origin='system')

resolve_source(parse_source("project"), "mypy", workspace_root=Path("/repo"))
# ResolvedTool(tool='mypy', executable=PosixPath('/repo/.venv/bin/mypy'), origin='project')
```

```python
def resolve_source(
    source: ParsedSource,
    tool: str,
    *,
    workspace_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> ResolvedTool: ...
```

| Argument | Default | Description |
|---|---|---|
| `source` | required | The classified `ParsedSource` from `parse_source(hook.from_)`. Only `SystemSource` / `ProjectSource` resolve. |
| `tool` | required | The bare command name to locate (e.g. `"ruff"`) — the first shell token of `HookDef.run`. `resolve_source` does not tokenize `run` itself. |
| `workspace_root` | `Path.cwd()` | Project root under which `.venv` is discovered for a `ProjectSource`. Real workspace discovery is out of scope. |
| `environ` | `os.environ` | Environment mapping read for `PATH` (system) and `VIRTUAL_ENV` (project). Injectable so callers and tests stay hermetic. |

It returns a `ResolvedTool` — a frozen pydantic model (`model_config = ConfigDict(frozen=True, extra="forbid")`) mirroring the source models:

| Field | Type | Meaning |
|---|---|---|
| `tool` | `str` | The requested command name, echoed back. |
| `executable` | `Path` | The **absolute** path to the resolved executable (always `Path(...).resolve()`-d). |
| `origin` | `"project"` \| `"system"` | Which rule produced the result, for runner/cache explainability. |

#### Discovery rules

- **`system`** — `tool` is located on `PATH` via `shutil.which(tool, path=environ.get("PATH"))` (standard `which` semantics: first `PATH` directory with an executable match wins), then absolutized. `origin="system"`.
- **`project`** — `tool` is located in the project's own already-existing environment, in this precedence order (first qualifying candidate wins):
  1. **Active venv** — if `VIRTUAL_ENV` is set and non-empty: `<VIRTUAL_ENV>/bin/<tool>`.
  2. **Discovered project venv** — `<workspace_root>/.venv/bin/<tool>`.

  A candidate qualifies only if it exists, is a regular file (following symlinks), and is executable (`os.access(path, os.X_OK)`). The result is absolutized with `origin="project"`. Only the POSIX `bin/` layout is probed in v1 (the Windows `Scripts\` layout is a documented fast-follower). A missing `.venv` is a not-found error — **never** a trigger to create one.

Given the same `(source, tool, PATH, VIRTUAL_ENV, workspace_root, filesystem state)`, `resolve_source` returns an equal `ResolvedTool` (or raises the same error) on every call — it performs no network, no subprocess, and no filesystem writes.

#### Resolution errors are runtime, not config, errors

When a tool cannot be located — or when `source` is a `PyPISource` (delegated to the Environments feature) or an `UnsupportedSource` — `resolve_source` raises `SourceResolutionError` (a `ValueError` subclass) carrying structured `tool` / `kind` / `reason` fields, with the message form:

```
cannot resolve '<tool>' from <kind> source: <reason>
```

| `kind` | When | `reason` |
|---|---|---|
| `system` | tool absent from `PATH` | `not found on PATH` |
| `project` | tool in neither venv location | `not found in project environment (checked $VIRTUAL_ENV/bin and <workspace_root>/.venv/bin)` |
| `pypi` | a `pypi:` source | `pypi source resolution is delegated to Environments (STY-0006), not handled here` |
| `unsupported` | a `local:` / `git:` / `docker:` source | `'<scheme>' sources are not supported` |

Unlike `SourceSpecError` — a *syntax* error in `check.toml`, knowable at load time and re-raised by `load_config` as a `ConfigError` with `path:line:col` context — a `SourceResolutionError` is a **runtime/environment** condition: the `from` and `run` are syntactically valid, but the tool is absent on this machine right now. It has no `check.toml:line:col` meaning, so it does **not** map to `ConfigError` and is **not** raised from `load_config`. Loading a config whose tool happens to be absent still succeeds; the error surfaces only when `resolve_source` is called (typically caught by the runner, which reports the failing hook).

### Resolving `pypi:` / `pypi+alias:` sources

Where `resolve_source` handles the two non-network kinds, `gatecheck.registry.resolve_pypi_source` handles the network kind: it turns a `PyPISource` into a **pinned distribution descriptor** by querying the registry's [PEP 503](https://peps.python.org/pep-0503/) simple index (with [PEP 691](https://peps.python.org/pep-0691/) JSON content negotiation and an HTML fallback). It resolves the requirement to a single exact version against a known index URL; it does **not** create a venv, download an artifact, or install anything — that is the Environments feature's job.

```python
from gatecheck.registry import resolve_pypi_source
from gatecheck.sources import parse_source

resolve_pypi_source(parse_source("pypi:ruff>=0.4,<1"), cfg.sources)
# ResolvedPyPISource(kind='pypi', requirement='ruff>=0.4,<1', name='ruff',
#                    version='0.4.9', index_url='https://pypi.org/simple',
#                    registry=None, sha256=..., url=..., filename=...)
```

```python
def resolve_pypi_source(
    source: PyPISource,
    sources: SourceSpec | None,
    *,
    client: RegistryClient | None = None,
    allow_prereleases: bool = False,
) -> ResolvedPyPISource: ...
```

| Argument | Default | Description |
|---|---|---|
| `source` | required | The `PyPISource` from `parse_source(hook.from_)` — its verbatim `requirement` and optional registry alias (`registry`). |
| `sources` | required | The parsed `[sources]` table (`GatecheckConfig.sources`, may be `None`). Supplies `default-registry` and `extra-registries`. |
| `client` | `UrllibRegistryClient()` | The injectable network seam (a `RegistryClient` Protocol). Tests pass a fake to stay hermetic; auth/proxy config plugs in here later. |
| `allow_prereleases` | `False` | Caller override for pre-release selection. The specifier itself can still opt in per PEP 440. |

It returns a frozen `ResolvedPyPISource` (`model_config = ConfigDict(frozen=True, extra="forbid")`):

| Field | Type | Meaning |
|---|---|---|
| `kind` | `Literal["pypi"]` | Discriminator, consistent with `PyPISource`. |
| `requirement` | `str` | The original requirement text, echoed back. |
| `name` | `str` | The **canonicalized** project name. |
| `version` | `str` | The **selected** exact version, e.g. `"0.4.9"`. |
| `index_url` | `str` | The resolved index URL the version was pinned against. |
| `registry` | `str \| None` | The `[sources]` alias used, or `None` for the default. |
| `sha256` / `url` / `filename` | `str \| None` | *(best-effort)* the selected version's chosen file (wheel preferred over sdist); `None` when unavailable. |

The **load-bearing contract is `name` + `version` + `index_url`** — enough to install `name==version --index-url <index_url>` deterministically. The optional artifact fields are advisory metadata for hash-pinning and cache/explainability, not authoritative wheel selection.

#### Index and version selection rules

- **Alias → URL.** `registry=None` resolves to `sources.default-registry` (or the built-in `https://pypi.org/simple` when unset). `registry="internal"` resolves to `sources.extra-registries["internal"]`.
- **Version selection.** The requirement's [PEP 440](https://peps.python.org/pep-0440/) specifier is applied to the versions the index lists; the **highest satisfying** version wins. A bare name selects the latest non-pre-release.
- **Pre-releases** are excluded unless the specifier opts in, `allow_prereleases=True`, or only pre-releases satisfy the specifier.
- **Yanked releases** ([PEP 592](https://peps.python.org/pep-0592/)) are excluded from range matches but selectable when pinned exactly (`==<yanked>`) and no non-yanked version matches.
- **Markers / extras** in a requirement are **rejected** with a clear `RegistryError`, not silently ignored.

#### Registry failures are runtime, not config, errors

Every failure raises `gatecheck.registry.RegistryError` (a `ValueError` subclass) with structured `requirement` / `index_url` / `reason` fields and the message form:

```
cannot resolve '<requirement>' against <index>: <reason>
```

| When | `index_url` | `reason` |
|---|---|---|
| Undeclared registry alias | `None` (`<unresolved index>` in the message) | `unknown registry alias '<alias>' (not declared in [sources].extra-registries)` |
| Invalid PEP 508 requirement | resolved URL | `invalid requirement: <detail>` |
| Markers / extras present | resolved URL | `requirement markers/extras are not supported` |
| Package not found (index 404) | resolved URL | `package '<name>' not found on index` |
| No version satisfies the specifier | resolved URL | `no version of '<name>' satisfies '<specifier>'` |
| Network / timeout | resolved URL | `network error querying index: <detail>` (chained via `raise … from`) |
| Malformed index response | resolved URL | `malformed index response from <url>` |

Like `SourceResolutionError`, a `RegistryError` is a **runtime/environment** condition (network / index state), never a `check.toml` syntax error — it does **not** map to `ConfigError` and is **not** raised from `load_config`. Loading a `pypi:` hook succeeds; network resolution runs only when `resolve_pypi_source` is called.

### Environments — resolving a hook to an executable

Where `parse_source` classifies a `from` spec and `resolve_source` locates the two non-network kinds, `gatecheck.env.EnvManager` turns a whole `HookDef` into an **executable environment**. It derives the tool name from the hook's `run`, dispatches on the source kind, and returns a `ResolvedEnv`. This is the **non-venv path**: `project` / `system` reuse an already-existing binary; it performs no network, no subprocess, no venv creation, and no filesystem writes.

```python
from gatecheck.env import EnvManager, ResolvedEnv

EnvManager().resolve(hook)  # hook.from_ == "system", hook.run == "ruff check ."
# ResolvedEnv(bin_dir=PosixPath('/usr/bin'), cache_key='…64 hex chars…')
```

```python
class EnvManager:
    def __init__(
        self,
        workspace_root: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None: ...

    def resolve(self, hook: HookDef) -> ResolvedEnv: ...
```

`workspace_root` / `environ` are stored as-is (including `None`) and forwarded verbatim to `resolve_source`, which resolves the defaults (`Path.cwd()` / `os.environ`) lazily — so an `EnvManager` stays a deterministic, hermetically testable function of its injected inputs.

`resolve` returns a `ResolvedEnv` — a frozen `dataclass`:

| Field | Type | Meaning |
|---|---|---|
| `bin_dir` | `Path` | The directory containing the hook's executable — the parent of the resolved executable (`ResolvedTool.executable.parent`). An already-existing absolute directory; **never created**. |
| `cache_key` | `str` | A 64-char lowercase SHA-256 hex digest that deterministically identifies this environment. |

#### Tool-name rule

The tool to locate is the **first shell token of `run`**: `shlex.split(hook.run)[0]` (POSIX tokenization, so quoted / escaped program names are handled correctly). There is no `tool` field in `check.toml`. A `run` that yields no tokens (whitespace-only) or cannot be tokenized (unbalanced quotes) raises `EnvError`.

#### Dispatch by source kind

| `from` kind | Behavior |
|---|---|
| `system` / `project` | `resolve_source` locates the tool (see [Resolving `project` / `system` sources](#resolving-project-system-sources)); `bin_dir` is the resolved executable's parent, and `cache_key` is derived over `("env-v1", origin, executable path)`. Because `origin` (`"project"` vs `"system"`) is part of the key material, the same binary reached two ways keys distinctly. |
| `pypi:` / `pypi+alias:` | Pinned via `resolve_pypi_source`, then built (or reused from cache) as a **uv-backed venv** — see [uv-backed `pypi` environments](#uv-backed-pypi-environments) below. `bin_dir` is the cached venv's `bin/`. |
| `local:` / `git:` / `docker:` | Unsupported — raises `EnvError`. |

#### `EnvError` and propagated errors

`EnvManager` raises `gatecheck.env.EnvError` (a `ValueError` subclass) for the env-domain cases above. It carries structured `hook_id` / `reason` fields with the message form:

```
cannot resolve environment for hook '<id>': <reason>
```

| Case | `reason` |
|---|---|
| `run` yields no tool name (empty / whitespace-only) or unbalanced quotes | `cannot derive a tool name from run = '<run>'` |
| `pypi:` — `uv` binary not found on the host | `uv is required to build pypi environments but was not found (set GATECHECK_UV or install uv; auto-bootstrap is STY-0010)` |
| `pypi:` — `uv` failed to build the venv (non-zero exit) | `uv failed to build the environment for '<name>==<version>': <detail>` |
| `pypi:` — built venv lacks the tool named by `run` | `tool '<tool>' is not present in the built environment for '<name>==<version>'` |
| `local:` / `git:` / `docker:` source | `'<scheme>' sources are not supported` |

Errors raised by the underlying source / registry layers are **not** re-wrapped — they propagate unchanged so their structured fields survive: a `SourceSpecError` (malformed `from`, from `parse_source`), a `SourceResolutionError` (tool absent, from `resolve_source`), and a `RegistryError` (a `pypi:` requirement that cannot be pinned — network / index state, from `resolve_pypi_source`). Like those errors, an `EnvError` is a **runtime/environment** condition, not a `check.toml` syntax error — it does **not** map to `ConfigError` and is **not** raised from `load_config`.

#### uv-backed `pypi` environments

A `from = "pypi:<req>"` / `pypi+<alias>:<req>` hook resolves to an isolated,
content-addressed virtualenv built by [uv](https://docs.astral.sh/uv/):

1. The requirement is pinned to an exact distribution by `resolve_pypi_source` (see [Resolving `pypi:` / `pypi+alias:` sources](#resolving-pypi-pypialias-sources)).
2. A **cache key** is derived as a SHA-256 over `("env-v1", "pypi", name, version, index_url)` — content-addressed on the pinned distribution, so the same `name==version` from the same index is built **once** and reused across hooks, runs, and projects.
3. On a cache **miss**, `uv venv` + `uv pip install <name>==<version> --index-url <url>` build the venv in a temp directory that is atomically published into the cache slot (a failed build never leaves a partial environment). When the registry supplied a `sha256`, the install uses `--require-hashes`.
4. `bin_dir` is the cached venv's `bin/` directory.

The cache lives under the **user cache directory** — `$XDG_CACHE_HOME/gatecheck/env-v1/<key>/` (falling back to `~/.cache/gatecheck/env-v1/<key>/`).

**`uv` is discovered or auto-bootstrapped.** `uv` is a host binary, **not** a Python dependency in `pyproject.toml`. It is located at run time via the `GATECHECK_UV` override, else `PATH`. If it is not found, gatecheck **auto-bootstraps** a pinned, checksum-verified `uv` into the user cache (`$XDG_CACHE_HOME/gatecheck/bin/uv`) and reuses it thereafter — a one-time network download from the Astral GitHub releases, verified against a hardcoded SHA-256. Auto-bootstrap supports Linux and macOS (x86_64 / aarch64); on other platforms, or when disabled, `EnvManager` raises `EnvError`.

Set **`GATECHECK_NO_BOOTSTRAP`** (any non-empty value) to disable auto-bootstrap — useful for air-gapped or CI environments that must provide their own `uv`; a missing `uv` then errors instead of downloading.

Run **`gatecheck sync`** to pre-create (or verify) every hook's environment ahead of time — it reports each hook as `built` (a new uv venv), `cached` (already present), `ready` (a `project` / `system` binary that needs no environment), or `error`, and exits non-zero if any could not be resolved.

### Cache — explaining a hook's environment

`gatecheck cache why <hook>` explains, for a single hook in `check.toml`, how its cache key is derived and whether its environment is already cached — **read-only**: it never builds a venv or writes to the cache.

```console
$ gatecheck cache why ruff
hook:      ruff
source:    pypi ruff==0.4.2 @ https://pypi.org/simple  (pypi)
status:    miss — no cached venv yet — built on the next run
cache key: 3f9a…(64 hex chars)
  hashed:  sha256('env-v1' + 'pypi' + 'ruff' + '0.4.2' + 'https://pypi.org/simple')
cache dir: /home/you/.cache/gatecheck/env-v1/3f9a…
```

- **`status`** is `hit` when the content-addressed venv slot already exists, `miss` when it would be built on the next run, or `not-applicable` for `project` / `system` hooks (which reuse an existing binary and cache no environment).
- The **`hashed:`** line lists the exact material behind the `cache key`, so the digest is reproducible by hand.
- For a `pypi:` hook this pins the requirement, which **may query the registry** (network); it never builds the venv.
- `--json` emits the same fields as a JSON object for tooling. `--config` points at a non-default `check.toml`. An unknown `<hook>` exits non-zero and lists the available hook ids.

> Cache eviction (`gatecheck cache clear`) is not yet implemented.

### Runner — resolving the changeset

Before running hooks, `gatecheck.runner.resolve_changeset` determines **which files each hook runs against**:

- The base file set is the **staged** files by default (`git diff --cached`), or **every tracked** file with `--all-files` (`git ls-files`). Deleted files are excluded (you can't lint a file that's gone).
- Each hook then receives: **no files** when `pass-files = false`; the **whole changeset** when it has no `files` glob; otherwise only the files matching its **`files`** glob. Matching is `fnmatch`-style and case-sensitive, so `files = "*.py"` matches `.py` files at any depth.

The git query is the only side effect and sits behind an injectable seam, so resolution is deterministic and testable offline. A `run`'s `{files}` placeholder substitution and the actual execution happen in the runner's later stages, not here.

### Runner — the execution plan

`gatecheck.runner.build_plan` turns the config into a dependency-ordered `ExecutionPlan` (no execution):

- **Selection:** a named `[group.<name>]` (hooks in the group's order) or every hook (declared order) when no group is given.
- **`when` filter:** hooks excluded by their `when` conditions (`env` / `env-not`, `on-ci`, `branch` / `branch-not` / `branch-matches`, `files-match`) are set aside as **skipped, with a reason**, not dropped silently. The current branch and the changeset are passed in from the git seam; when that context is absent a branch/`files-match` condition is fail-open (the hook runs). CI is detected via the `CI` or `GITHUB_ACTIONS` environment variables.
- **Empty-file-set filter:** a hook with `pass-files = true` whose `files`/`exclude` globs match **nothing in this changeset** is skipped with the reason `no matching files`. This is a safety rule, not an optimization: with an empty `{files}`, most tools fall back to scanning the whole project, so a `--fix` hook would silently rewrite files the change never touched. Hooks with `pass-files = false` are exempt — they never wanted files and are meant to run project-wide (`mypy src/`, `cargo clippy`), which makes `pass-files = false` the "always run" escape hatch.
- **`depends-on` DAG:** dependencies are resolved into a directed graph and topologically sorted into **levels** — hooks in the same level have no dependency between them and may run concurrently; later levels wait for earlier ones. A dependency that isn't running (skipped or outside the group) drops its edge; a dependency on a hook that doesn't exist, or a dependency cycle, is a `PlanError`.

### Runner — executing a hook

`gatecheck.runner.run_hook` runs one hook and returns a `HookResult`:

- **Command:** `run` is tokenized (`shlex`); a standalone **`{files}`** token expands to the hook's files in place, otherwise the files are appended after the command. The files are the ones routed to that hook by the changeset step, so `pass-files = false` simply yields no file arguments.
- **Environment:** the hook's `ResolvedEnv` (from the Environments layer) contributes its `bin/` directory to the front of `PATH`, so the hook's own tool is found first.
- **Result:** `HookResult(hook_id, status, exit_code, output, duration)` — `status` is `passed` (exit 0), `failed` (non-zero exit), or `error` (the environment couldn't be resolved or the command couldn't be spawned). Combined stdout+stderr is captured. The subprocess sits behind an injectable seam, so execution is testable without spawning anything.

### Runner — parallel execution engine

`gatecheck.runner.run_plan` executes an `ExecutionPlan` through the native **`gatecheck_core`** (Rust) **dynamic scheduler** (`run_graph`):

- The plan's running hooks and their in-plan dependency edges are handed to Rust as a graph. A hook starts **the moment all of its dependencies finish** — there is **no wave barrier**, so a freed hook begins while unrelated peers are still running. On uneven graphs (one slow hook in a level) this cuts wall-clock versus the old wave scheduler. Because a hook's environment work and subprocess wait release the GIL, concurrently-scheduled hooks genuinely overlap (rayon).
- **Fail-fast** (a group setting): the first hook that does not pass stops the scheduling of any **not-yet-started** hook (in-flight hooks finish). A hook downstream of a failure therefore never starts — its dependencies only complete after the failure is recorded. When independent hooks race the failing one, the exact set that started is best-effort (as with any parallel runner), but the returned ordering is always deterministic.
- **Concurrency cap:** a group's `max-workers` bounds how many hooks are in flight at once — the scheduler keeps a ready queue and only launches up to the cap, launching the next as each finishes. A group with `parallel = false` runs **serially** (cap of 1, still in dependency order); `parallel = true` caps at `max-workers` (default 4). An all-hooks run (no group) is unbounded — rayon's global pool.
- **Result ordering is deterministic:** `run_plan` returns the executed `HookResult`s in the plan's node order (flattened levels), independent of completion timing.
- The Rust core owns scheduling and parallelism; each hook is still executed by the Python `run_hook` (which owns environment resolution and the subprocess), called back per node.

---

## Complete example

```toml
[sources]
default-registry = "https://pypi.org/simple"
extra-registries = { internal = "https://pkg.example.com/simple" }

[[hook]]
id   = "ruff"
from = "pypi:ruff>=0.4"
run  = "ruff check --fix {files}"
files = "*.py"

[[hook]]
id   = "ruff-format"
from = "pypi:ruff>=0.4"
run  = "ruff format {files}"
files = "*.py"
depends-on = ["ruff"]

[[hook]]
id        = "mypy"
from      = "project"
run       = "mypy src/"
pass-files = false
when      = { env-not = "SKIP_MYPY" }

[[hook]]
id   = "private-linter"
from = "pypi+internal:org-linter==2.1.0"
run  = "org-lint {files}"

[[hook]]
id   = "check-secrets"
from = "pypi:detect-secrets"
run  = "detect-secrets audit .secrets.baseline"
pass-files = false
when = { on-ci = true }

[group.format]
hooks     = ["ruff-format"]
parallel  = false
on-event  = "commit"

[group.lint]
hooks     = ["ruff", "mypy"]
parallel  = true
fail-fast = false
on-event  = "commit"

[group.full]
hooks     = ["ruff", "ruff-format", "mypy", "check-secrets"]
parallel  = true
fail-fast = false
on-event  = "push"
```

---

## Python API

For tools that need to consume `check.toml` programmatically, `gatecheck.config.load_config` is the entry point. It returns a fully validated `GatecheckConfig` object built from four pydantic models that mirror the documented schema. The function is synchronous and side-effect-free beyond reading the file.

```python
from pathlib import Path
from gatecheck.config import load_config

cfg = load_config(Path("check.toml"))
for hook in cfg.hook:
    print(hook.id, hook.from_, hook.run)
for name, group in cfg.group.items():
    print(name, group.hooks, group.parallel)
```

The package exposes exactly seven public symbols, all re-exported from `gatecheck.config`:

| Symbol | Kind | Source module |
|---|---|---|
| `ConfigError` | exception | `gatecheck.config.config_error` |
| `GatecheckConfig` | pydantic model | `gatecheck.config.gatecheck_config` |
| `GroupDef` | pydantic model | `gatecheck.config.group_def` |
| `HookDef` | pydantic model | `gatecheck.config.hook_def` |
| `SourceSpec` | pydantic model | `gatecheck.config.source_spec` |
| `dump_config` | function | `gatecheck.config.dumper` |
| `load_config` | function | `gatecheck.config.loader` |

### `dump_config`

```python
from gatecheck.config import dump_config

dump_config(config: GatecheckConfig, path: Path) -> None
```

Serialize a `GatecheckConfig` back to a valid `check.toml` file at `path`. Complements `load_config` — where `load_config` reads and validates a TOML file into a typed model, `dump_config` writes a typed model back to a TOML file.

#### Round-trip contract

`dump_config` and `load_config` are inverses of each other:

```python
from pathlib import Path
from gatecheck.config import dump_config, load_config

original = load_config(Path("check.toml"))
dump_config(original, Path("check.copy.toml"))
copy = load_config(Path("check.copy.toml"))
assert original == copy  # round-trip fidelity
```

Any `GatecheckConfig` produced by `load_config` can be passed to `dump_config`, and the resulting file will produce an equal `GatecheckConfig` when loaded again.

#### Field omission

Fields are omitted from the output when their value is `None` or when their value equals the pydantic-declared default for that field. This keeps the output clean and human-editable — only fields with meaningful, non-default values appear in the file.

Examples of omitted fields: `pass-files = true` (default is `true`), `depends-on = []` (default is empty list), `when` when no conditions are set.

#### TOML structure

The output uses the same idiomatic TOML constructs as a hand-written `check.toml`:

- `[[hook]]` — each hook is emitted as an array-of-tables block.
- `[group.<name>]` — each group uses a dotted-table header.
- `when = { … }` — conditional execution is serialized as an inline table, never a sub-table.

Sections whose data is absent (`hook` list empty, `group` dict empty, `sources` is `None`) are not written to the output at all.

TOML key names use hyphens (`pass-files`, `depends-on`, `from`, `on-event`, `fail-fast`, `env-not`, `on-ci`, `default-registry`), matching the canonical `check.toml` format.

#### Errors

`dump_config` is synchronous and side-effect-free beyond writing `path`. The following OS errors propagate unchanged — no new exception types are introduced:

| Exception | Cause |
|---|---|
| `IsADirectoryError` (or `OSError`) | `path` is an existing directory |
| `FileNotFoundError` | `path`'s parent directory does not exist |
| `PermissionError` | `path` is not writable |

#### Example

```python
from pathlib import Path
from gatecheck.config import GatecheckConfig, HookDef, dump_config

cfg = GatecheckConfig(
    hook=[
        HookDef(**{"id": "ruff", "from": "pypi:ruff>=0.4", "run": "ruff check --fix {files}", "files": "*.py"}),
    ]
)
dump_config(cfg, Path("check.toml"))
```

The above produces:

```toml
[[hook]]
id = "ruff"
from = "pypi:ruff>=0.4"
run = "ruff check --fix {files}"
files = "*.py"
```

Note that `pass-files` is absent because its value (`true`) equals the default.

---

### Error handling

`load_config` raises `gatecheck.config.ConfigError` for any config-shape problem — malformed TOML or a schema violation. `ConfigError` subclasses `ValueError`, so existing `except ValueError:` callers continue to work without changes.

#### `ConfigError` format

`str(exc)` is one line per error in the IDE-parseable form `path:line:col: message`, with multiple errors joined by `\n`. This matches the convention used by compilers, `ruff`, `mypy`, and similar tools, so the output works directly with IDE error matchers, vim's quickfix list, and grep/sed pipelines.

A full line looks like:

```
check.toml:5:3: Field required (field: hook.0.id)
```

#### Example

```python
from pathlib import Path
from gatecheck.config import ConfigError, load_config

try:
    cfg = load_config(Path("check.toml"))
except ConfigError as exc:
    for line in str(exc).splitlines():
        print(line)
```

#### Underlying exception identity

`ConfigError` is raised with PEP 3134 exception chaining, so `exc.__cause__` is the original `tomllib.TOMLDecodeError` (malformed TOML) or `pydantic.ValidationError` (schema violation). Callers that need programmatic access to the raw exception — for example, `pydantic.ValidationError.errors()` for structured error data — can read it directly off `__cause__`:

```python
import pydantic
from gatecheck.config import ConfigError, load_config

try:
    cfg = load_config(Path("check.toml"))
except ConfigError as exc:
    if isinstance(exc.__cause__, pydantic.ValidationError):
        for err in exc.__cause__.errors():
            ...  # structured handling
```

#### Errors that are NOT wrapped

Errors raised before TOML parsing propagate as their native exception types and are NOT wrapped in `ConfigError`:

- `FileNotFoundError` — `path` does not exist.
- `PermissionError` — `path` exists but cannot be opened for reading.
- `OSError` — `path` is not a regular file, or exceeds the 1 MiB size cap.

### TOML aliases

TOML keys idiomatically use hyphens, but Python identifiers cannot. Every hyphenated key (`pass-files`, `depends-on`, `on-event`, `fail-fast`, `env-not`, `on-ci`, `default-registry`) maps to an underscored Python attribute (`pass_files`, `depends_on`, `on_event`, etc.). The reserved-word case `from` maps to `from_`. Because each model sets `populate_by_name=True`, both forms work at construction time:

```python
from gatecheck.config import HookDef

HookDef(**{"id": "ruff", "from": "pypi:ruff", "run": "ruff check"})
```
