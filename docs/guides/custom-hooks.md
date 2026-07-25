# Writing Custom Hooks

Not every check is a published package. Project scripts, `make` targets, non-Python
tools and one-off shell commands are all hooks too.

## A script in your repo

```toml
[[hook]]
id    = "no-todos"
from  = "system"
run   = "./scripts/check-todos.sh {files}"
files = "*.py"
```

```sh title="scripts/check-todos.sh"
#!/bin/sh
# Fail if any file contains a bare TODO with no issue reference, e.g. TODO(GAT-12).
status=0
for file in "$@"; do
    if grep -n 'TODO' "$file" | grep -v 'TODO('; then
        echo "$file: TODO without an issue reference" >&2
        status=1
    fi
done
exit $status
```

```bash
chmod +x scripts/check-todos.sh
```

The contract is just a process: **receive file paths as arguments, exit `0` to pass and
non-zero to fail.** Anything printed on failure is shown in the report, indented under
the hook.

!!! note "`from = "system"`, not `local:`"

    `local:` is reserved but [not yet implemented](../config/sources.md). Use `system`
    with a relative command. Hooks inherit gatecheck's working directory — the
    directory you invoked it from, or the package directory under `--affected` — so
    `./scripts/…` resolves relative to that.

## Non-Python tools

```toml
[[hook]]
id         = "cargo-clippy"
from       = "system"
run        = "cargo clippy -- -D warnings"
pass-files = false

[[hook]]
id    = "shellcheck"
from  = "system"
run   = "shellcheck {files}"
files = "*.sh"

[[hook]]
id    = "prettier"
from  = "system"
run   = "prettier --check {files}"
files = "*.{ts,tsx,css,md}"
```

These rely on the tool being installed already. That's the trade-off of `system`:
zero setup, but reproducibility is on you. Where a tool *is* published to an index,
prefer `pypi:` — `shellcheck-py` and `ruff` both are.

!!! warning "`*.{ts,tsx}` is not brace expansion"

    Globs are `fnmatch`-style: `*`, `?`, `[seq]`. Brace alternation is **not**
    supported, so `*.{ts,tsx}` matches a file literally named that. Use one hook per
    extension, or a broader glob plus an `exclude`.

## Receiving files

```toml
run = "mytool {files}"           # explicit position
run = "mytool --strict {files}"  # anywhere in the command
run = "mytool"                   # appended at the end
run = "mytool"                   # with pass-files = false: no files at all
```

`{files}` is replaced in place; without it the paths are appended. Paths are
repo-relative and POSIX-style.

A hook whose glob matches nothing is **skipped**, not run with an empty list — so you
never have to defend against "no arguments means scan everything". Hooks with
`pass-files = false` always run.

## Project-wide checks

Some tools take no file arguments at all:

```toml
[[hook]]
id         = "pytest"
from       = "project"
run        = "pytest -q"
pass-files = false
when       = { files-match = "*.py" }
```

`pass-files = false` says "never pass files"; `files-match` says "only bother when
Python changed". That pairing is the idiom for expensive project-wide tools.

## Checking the commit message

A hook in a [`commit-msg` group](../config/groups.md) checks the pending commit
message instead of files. Reference the message file with `{commit-msg}`:

```toml
[[hook]]
id   = "no-wip"
from = "system"
run  = "./scripts/no-wip.sh {commit-msg}"

[group.msg]
hooks    = ["no-wip"]
on-event = "commit-msg"
```

```sh title="scripts/no-wip.sh"
#!/bin/sh
# Reject messages that still say WIP.
grep -qi '\bwip\b' "$1" && { echo "message still marked WIP"; exit 1; }
exit 0
```

`{commit-msg}` expands to the message-file path passed by git; the hook's `files`
glob is ignored in this mode. See [`gatecheck run`](../cli/run.md#message-check-mode).

## Quoting and arguments

`run` is tokenized like a shell command line — quotes group arguments, but there is
**no shell**: no pipes, redirection, globbing, `&&`, or variable expansion.

```toml
run = "mytool --msg 'hello world'"    # two args: --msg, hello world
run = "mytool a | grep b"             # NOT a pipe — '|' is a literal argument
```

If you need shell features, put them in a script and call that. It's more readable and
testable than a long `run` line anyway.

## Testing a hook

```bash
gatecheck run --all-files            # everything, ignoring what's staged
git add path/to/file && gatecheck run
```

Remember a passing hook's output isn't printed — only failures are. To see what a hook
receives, make it fail temporarily, or run the command by hand.

## Exit codes

| Exit | Report | Meaning |
|---|---|---|
| `0` | `ok` | Passed. |
| non-zero | `FAIL` | Failed. Output is shown. |
| couldn't start | `ERR` | The tool wasn't found, or the environment couldn't be built. |

`ERR` versus `FAIL` matters: `FAIL` is your code, `ERR` is the setup.

## Auto-fixing hooks

A hook that rewrites files (`ruff --fix`, `prettier --write`) works fine, with two
things to know:

1. **It only sees matched files** — gatecheck skips it entirely when nothing matches,
   so it can't wander off across the repo.
2. **Fixed files are not re-staged.** After an auto-fix during a commit hook, `git add`
   the changes and commit again. gatecheck deliberately doesn't touch your index.

Give auto-fixers their own commit-time group with `fail-fast = true` so you find out
immediately.

## Sharing hooks across a monorepo

Define once at the workspace root; every package inherits it under `merge`. A package
overrides by declaring the same `id`. See
[Monorepo / Workspace](../config/workspace.md).

## See also

- [Source Types](../config/sources.md) — `system` versus `project` versus `pypi:`.
- [Conditions & Filters](../config/conditions.md) — `files`, `exclude`, `when`.
- [check.toml Reference](../config/reference.md) — every field.
