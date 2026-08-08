# Config Design

Why `check.toml` looks the way it does, and how it's loaded.

## TOML, not YAML

pre-commit uses YAML. hooksmith uses TOML, on purpose.

YAML's flexibility is its problem: the [Norway
problem](https://hitchdev.com/strictyaml/why/implicit-typing-removed/) (`no` becomes
`false`), significant whitespace that breaks on a stray space, and multiple ways to
write the same structure. A configuration file that a tool *and* a human both edit
should have exactly one obvious spelling for each thing. TOML has that; it was designed
for it.

The cost is that deeply nested structures are more verbose in TOML. hooksmith's config
is deliberately shallow — a flat list of hooks, a flat set of groups — so that cost
never really lands.

## Fail loud, fail early, fail located

Every model is `extra="forbid"`. An unknown key is an **error**, not a silently
ignored line:

```console
$ hooksmith run
Error: check.toml:12:1: Extra inputs are not permitted (field: pass_filenames)
```

That's a real failure mode worth designing against. In a config where unknown keys are
ignored, `pass_filenames` (pre-commit's spelling) instead of `pass-files` looks like it
works and silently does nothing — you'd debug the *hook* for an hour before suspecting
the *key*. Rejecting it, with the line and column, turns an hour into a second.

The error carries `path:line:col` because a config error you have to hunt for is a
config error that wastes your time. The loader parses the file twice for this: once
with `tomllib` for speed, and — only on failure — again with `tomlkit`, which preserves
source positions, so the pydantic validation error can be mapped back to the exact span
in the file.

## Hyphens outside, underscores inside

TOML idiom is hyphens; Python identifiers can't contain them. So the config uses
hyphens everywhere (`pass-files`, `depends-on`, `on-event`, `fail-fast`,
`max-workers`, `env-not`) and pydantic aliases map each to its underscore attribute.
Both spellings are accepted at load, but the hyphenated form is canonical and the one
the docs use.

The reserved word `from` — the most important field — maps to the `from_` attribute
internally, which is the one place the seam shows.

## Value objects are frozen

Every parsed structure is a frozen pydantic model or a frozen dataclass. Config is read
once and never mutated; downstream code takes a `HooksmithConfig` and can't
accidentally reach back and change it. Immutability also makes the content-addressed
cache honest — a `ResolvedPyPISource` can't change out from under the key derived from
it.

## Round-tripping

`load_config` and `dump_config` are inverses: anything loaded can be dumped, and the
result loads back to an equal config. This is what makes
[`hooksmith migrate`](../cli/migrate.md) trustworthy — it builds a `HooksmithConfig` in
memory and serializes it through the *same* dumper any hand-written config uses, so
migration output is a first-class config file, not a second-class generated one.

The dumper omits fields at their default (`pass-files = true`, an empty `depends-on`)
so output stays minimal and human-editable, and serializes `when` as an inline table
rather than expanding it into a `[hook.when]` sub-table, because that's how a person
would write it.

## Sources are a discriminated string, not a nested table

A hook's origin is one string — `pypi:ruff==0.4.9`, `project`, `system` — rather than a
nested `[hook.source]` table with a `kind` field. It parses into a discriminated union
(`PyPISource`, `ProjectSource`, `SystemSource`, `UnsupportedSource`), but the *surface*
is a single familiar-looking spec.

The reasoning: a source is identity, and identity reads best as one token. `pypi:ruff`
is instantly legible; a four-line table saying the same thing is not. Reserving
`local:`/`git:`/`docker:` in the same grammar (even though they're
[not implemented](../config/sources.md)) means adding them later is a resolver change,
not a config-schema break.

## Validation is layered

Loading runs three passes, each with its own error domain:

1. **TOML syntax** — malformed TOML → `ConfigError` with the parse position.
2. **Schema** — pydantic validation (types, required fields, unknown keys, enums like
   `on-event`) → `ConfigError` with the field location.
3. **Source specs** — the `from` strings are parsed and their *syntax* checked, so a
   malformed `pypi:` spec fails at load with `path:line:col`.

What load does **not** do is touch the world. A `pypi:` hook whose package doesn't
exist, or a `system` tool that isn't installed, loads fine — those are
*runtime/environment* conditions (`RegistryError`, `SourceResolutionError`), surfaced
when the hook actually runs, not config errors. Keeping that line sharp means "my
config is valid" and "my tools are available" are two separate, separately-debuggable
questions.

## See also

- [check.toml Reference](../config/reference.md) — every field.
- [Configuration](../config/index.md) — the task-shaped guide.
