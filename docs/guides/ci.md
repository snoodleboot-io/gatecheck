# CI Integration

hooksmith integrates naturally into GitHub Actions, GitLab CI, and any other CI system.

## GitHub Actions

### Run on pull requests

```yaml title=".github/workflows/checks.yml"
name: Checks

on:
  pull_request:
  push:
    branches: [main]

jobs:
  hooksmith:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - uses: astral-sh/setup-uv@v3

      - name: Install hooksmith
        run: uv pip install --system hooksmith

      - name: Sync hook environments
        run: hooksmith sync

      - name: Run hooks (all files)
        run: hooksmith run --all-files
```

### Monorepo — affected packages only

```yaml
- name: Run affected checks
  env:
    BASE_SHA: ${{ github.event.pull_request.base.sha }}
  run: |
    hooksmith run --affected --base "$BASE_SHA"
```

### JSON output for annotations

```yaml
- name: Run hooksmith (JSON output)
  run: |
    hooksmith run --all-files --json | tee /tmp/hooksmith-results.json
  continue-on-error: true

- name: Annotate failures
  if: always()
  uses: actions/github-script@v7
  with:
    script: |
      const results = require('/tmp/hooksmith-results.json');
      // Process and annotate...
```

### Skip hooks on CI

```toml
# check.toml — skip slow hooks on CI, run them on push instead
[[hook]]
id   = "mypy"
from = "project"
run  = "mypy src/"
pass-files = false
when = { on-ci = false }         # skip on CI entirely

[[hook]]
id   = "mypy-ci"
from = "project"
run  = "mypy src/ --strict"
pass-files = false
when = { on-ci = true }          # stricter check on CI only
```

## GitLab CI

```yaml title=".gitlab-ci.yml"
hooksmith:
  image: python:3.12-slim
  before_script:
    - pip install hooksmith
    - hooksmith sync
  script:
    - hooksmith run --all-files
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
```

## Caching environments

hooksmith stores hook environments in `~/.cache/hooksmith/`. Cache this between runs:

### GitHub Actions cache

```yaml
- name: Cache hooksmith envs
  uses: actions/cache@v4
  with:
    path: ~/.cache/hooksmith
    key: hooksmith-${{ hashFiles('check.toml', 'check.lock') }}
    restore-keys: |
      hooksmith-
```

### GitLab CI cache

```yaml
cache:
  key:
    files:
      - check.toml
      - check.lock
  paths:
    - .cache/hooksmith/
variables:
  XDG_CACHE_HOME: "$CI_PROJECT_DIR/.cache"
```

## Environment variables

| Variable | Effect |
|---|---|
| `SKIP_MYPY=1` | Skips hooks with `when = { env-not = "SKIP_MYPY" }` |
| `CI=true` | Triggers `when = { on-ci = true }` hooks |
| `GITHUB_ACTIONS=true` | Also detected as CI |
| `HOOKSMITH_CACHE_DIR` | Override default cache location |
| `HOOKSMITH_MAX_WORKERS` | Override default thread pool size |

## Speed

On a typical CI run with warm cache:

```
$ time hooksmith run --all-files

  ✓ ruff          (1.2s)  0 issues
  ✓ ruff-format   (0.4s)  no changes
  ✓ mypy          (8.1s)  no issues

  3 passed  in 8.3s

real    0m8.31s   # dominated by mypy, not hooksmith overhead
```

The hooksmith overhead itself (startup + DAG + file enumeration) is ~8ms.
