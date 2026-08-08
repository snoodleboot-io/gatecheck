# Monorepo Model

How workspace discovery, config inheritance and the affected-set calculation fit
together. For the how-to, see [Monorepo Setup](../guides/monorepo.md); this is the why.

## The goal: run the least that's correct

A monorepo CI run has one job — check what the change could have broken, and nothing
else. Too much and every one-line PR runs the whole repo; too little and a change slips
through unchecked. The whole design is in service of computing that set correctly, then
running exactly it.

Three pieces get there:

1. **Discovery** — which directories are packages.
2. **Inheritance** — what config each package effectively has.
3. **The affected set** — which packages a change reaches.

## Discovery

The root `[workspace].packages` is a list of globs. A directory is a package when it
matches one *and* contains a `check.toml`. The package's **name is its directory name**
— no separate id to keep in sync, no registry to maintain.

Requiring a `check.toml` (not just a glob match) means the workspace is defined by what
actually has configuration, so an empty or half-built directory that happens to match
`packages/*` isn't mistaken for a package.

## Inheritance: merge, override, none

A package's effective config is its own `check.toml` combined with the root's, per its
`inherit` mode. The three modes exist because monorepos aren't uniform:

- **`merge`** (default) — root hooks apply, the package layers on top, and a package
  hook sharing an id replaces the root's. This is the "shared baseline plus local
  additions" case, which is most of them.
- **`override`** — the package replaces the root entirely. For a package with a
  genuinely different stack (a Go service, a frontend) where the baseline is simply
  wrong.
- **`none`** — the package is standalone. Same effect as `override`, different stated
  intent: `override` says "I'm replacing the baseline", `none` says "the baseline was
  never meant for me".

Resolution is layered, not merged field-by-field: a child hook with the same id
*replaces* the parent's rather than deep-merging its fields, because a half-merged hook
(the parent's `files` with the child's `run`) is rarely what anyone means and always
surprising.

## The affected set

`depends-on` in each `[package]` builds a directed graph: an edge from a package to
each package it depends on. The affected set is computed by inverting that graph.

```
libs/shared ←── packages/api ←── packages/worker
                      ↑
             packages/frontend
```

**A change propagates to dependents, transitively.** Change `shared`, and `api`,
`worker` and `frontend` are all affected — because they consume it. Change `api`, and
only `worker` is (it depends on `api`); `shared` is not, because a dependency isn't
affected by its dependent.

The algorithm: find directly-changed packages (a changed file lives under their
directory), then walk the *reverse* dependency edges to collect every transitive
dependent. Declaration order is preserved so output is deterministic. A `depends-on`
naming an unknown package, or a cycle, is a config error caught before anything runs.

### Root changes affect everything

A changed file under **no** package — the root `check.toml`, a lockfile, CI config,
shared tooling — marks **every** package affected.

This is a deliberate bias toward safety. A shared file can influence any package, and
the two ways to be wrong aren't symmetric: over-running wastes some CI minutes;
under-running ships a package the change actually broke. For a checker, the first is
always the right mistake to make. A configurable "root triggers" allow-list could
narrow it later, but the safe default ships first.

## Execution

Affected packages run through the ordinary [runner](../cli/run.md), once per package,
with three adjustments:

- The **working directory** is the package's, so relative commands resolve locally.
- The changeset is **filtered to that package's files**, so each package's hooks see
  only their own changes.
- Results are **prefixed** `<package>:<hook>` in the report.

Everything else — planning, the `when` conditions, dynamic parallel scheduling — is
the single-package machinery, reused unchanged.

## Environments are still global

Package isolation is about *config and file scope*, not environments. Ten packages
pinning `ruff==0.4.9` still share **one** venv, because the
[environment cache](environments.md) is content-addressed on `(name, version, index)` —
the package name is deliberately *not* in the key. You get per-package hook selection
without paying to build the same tool ten times.

## Why not a build system

Bazel and friends model this far more richly — file-level dependency graphs, remote
caching, hermetic actions. hooksmith deliberately doesn't: it's a hook runner, and its
graph is package-level and declared, not inferred from the source. The bet is that
package-granularity affectedness captures most of the value of "run less" without asking
you to adopt a build system to get it. If you already have one, keep using it; hooksmith
sits alongside.

## See also

- [Monorepo Setup](../guides/monorepo.md) — the walkthrough.
- [Monorepo / Workspace config](../config/workspace.md) — `[workspace]` and `[package]`.
- [`hooksmith run --affected`](../cli/run.md) — the command.
