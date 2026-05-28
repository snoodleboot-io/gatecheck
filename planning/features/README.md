# Features

Each feature lives in its own directory under `FEAT-NNNN-<slug>/`. A feature directory contains:

- **`feature.md`** — the feature spec. What it does, why, what's in scope, what's out.
- **`stories/`** — one file per story (`STY-NNNN-<slug>.md`). Stories are vertical slices sized for a single PR.

Tasks live as checklist items *inside* a story file (`- [ ] TSK-001 …`). Promote a task to a story if it grows past a day's work; never let a story file outgrow a single reviewer's attention span.

## Index

- [FEAT-0001 — Config loader](FEAT-0001-config-loader/feature.md)
