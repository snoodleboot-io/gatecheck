# Private Registries

Resolve hooks from an internal index — Artifactory, Nexus, devpi, GitLab, CodeArtifact,
or a plain PEP 503 directory.

## Two ways

=== "Replace the default"

    Everything resolves against your index. Right for a repo that must not reach
    public PyPI at all.

    ```toml
    [sources]
    default-registry = "https://pkgs.corp.example.com/simple"
    ```

    ```toml
    [[hook]]
    id   = "ruff"
    from = "pypi:ruff==0.4.9"     # resolved against your index
    run  = "ruff check {files}"
    ```

=== "Add a named alias"

    Public PyPI stays the default; specific hooks opt into the internal index. Right
    when you publish a few internal tools but consume the rest publicly.

    ```toml
    [sources]
    default-registry = "https://pypi.org/simple"

    [sources.extra-registries]
    internal = "https://pkgs.corp.example.com/simple"
    ```

    ```toml
    [[hook]]
    id   = "house-style"
    from = "pypi+internal:house-style==2.1.0"   # note the +alias
    run  = "house-style {files}"
    ```

Aliases must match `[A-Za-z0-9_-]+`. Referencing an alias that isn't declared is an
error naming the requirement, so a typo can't silently fall back to public PyPI.

The inline form works too:

```toml
[sources]
extra-registries = { internal = "https://pkgs.corp.example.com/simple", legacy = "https://old.corp.example.com/simple" }
```

## The index URL is part of the cache key

Environments are addressed on `(package, version, index URL)`. `mytool==1.0` from
`internal` and `mytool==1.0` from public PyPI are **different cache entries** — a
private package can never be silently served from a public build, or vice versa.

Confirm what resolved with:

```console
$ hooksmith cache why house-style
source:    pypi house-style==2.1.0 @ https://pkgs.corp.example.com/simple  (pypi)
status:    hit — cached venv present — reused on the next run
```

## Authentication

hooksmith does not store credentials, and there is no auth field in `check.toml` —
deliberately, so secrets never end up in a file you commit. Authenticate the way your
index expects, through the environment:

**Credentials in the URL** (simplest for CI, keep it in a secret):

```toml
[sources]
default-registry = "https://pkgs.corp.example.com/simple"
```

```yaml
- run: hooksmith sync
  env:
    UV_INDEX_URL: https://${{ secrets.PKG_USER }}:${{ secrets.PKG_TOKEN }}@pkgs.corp.example.com/simple
```

**netrc**, which both the resolver and `uv` honour:

```bash
cat >> ~/.netrc <<'EOF'
machine pkgs.corp.example.com
login ci-bot
password $TOKEN
EOF
chmod 600 ~/.netrc
```

**Keyring / cloud-native auth** — AWS CodeArtifact, Google Artifact Registry and
similar typically mint a short-lived token you export before running:

```bash
export UV_INDEX_URL="https://aws:$(aws codeartifact get-authorization-token \
  --domain mydomain --query authorizationToken --output text)@mydomain-123456789012.d.codeartifact.us-east-1.amazonaws.com/pypi/myrepo/simple/"
hooksmith sync
```

!!! warning "Index URLs must be http or https"

    A `file://` or other scheme is rejected before any request is made. If you need a
    local directory index, serve it over HTTP.

## Mirrors and air-gapped networks

If your network has an internal **mirror** of PyPI, you don't need offline mode —
point `default-registry` at the mirror and everything works normally.

Offline mode is for having **no** egress at all. See
[Air-gapped / Offline](air-gapped.md); the two compose, since a warm cache doesn't care
which index filled it.

## Troubleshooting

**`unknown alias 'internal'`** — the alias isn't in `[sources.extra-registries]`, or is
spelled differently.

**`package not found`** — the index doesn't serve that name. Check it's published, and
that you're pointed at the right index; `cache why` prints the URL actually used.

**`network error querying index`** — DNS, proxy or TLS. Test the index directly:

```bash
curl -sSf https://pkgs.corp.example.com/simple/house-style/ | head
```

**Auth failures** — because credentials come from the environment, confirm they're
present at the point hooksmith runs. A git hook does not inherit your interactive
shell's exports; use `~/.netrc` or a login shell for local hooks.

## See also

- [Source Types](../config/sources.md) — `pypi:` and `pypi+alias:` in full.
- [Air-gapped / Offline](air-gapped.md) — no-egress runs.
- [`hooksmith cache why`](../cli/cache.md) — verify which index was used.
