# Planning

This directory is where work for `gatecheck` is shaped before code is written. The hierarchy goes from the broadest question (*should we build it?*) down to the smallest unit of work (*who's doing what today?*):

```
PRD  →  ADR  →  Feature  →  Story  →  Task
```

- **PRD** (Product Requirements Doc): *what* and *why*. Problem statement, target users, scope, success metrics. There is typically one per major product cut.
- **ADR** (Architecture Decision Record): *how, at the architectural level*. One decision per record. Immutable once accepted — supersede with a new ADR rather than editing.
- **Feature**: a coherent capability that delivers value end-to-end. Cites the PRD section it serves and any ADRs it depends on.
- **Story**: a vertical slice of a feature, sized to fit in a single PR. User-facing or developer-facing, but always demoable.
- **Task**: a checklist item *inside* a story file. Small, actionable, completable in hours. If a task grows past a day's work, promote it to a story.

## Directory layout

```
planning/
├── prd/                       PRDs, numbered
├── adr/                       ADRs, numbered + immutable
├── features/                  one directory per feature
│   └── FEAT-NNNN-<slug>/
│       ├── feature.md
│       └── stories/
│           └── STY-NNNN-<slug>.md
└── templates/                 copy-and-fill starting points
```

## ID conventions

| Kind     | Prefix | Example         |
| -------- | ------ | --------------- |
| PRD      | none   | `0001-gatecheck.md` |
| ADR      | `ADR-` | `0001-python-host-rust-core.md` |
| Feature  | `FEAT-`| `FEAT-0001-config-loader` |
| Story    | `STY-` | `STY-0001-load-check-toml.md` |
| Task     | `TSK-` | `- [ ] TSK-001 Parse the [[hook]] array` |

Numbers are **zero-padded to 4 digits** (3 for tasks within a story) and **never reused**. If a doc is abandoned, mark it `Status: Withdrawn` and leave its file in place — gaps in the sequence are fine.

## Status lifecycle

Every PRD, ADR, Feature, and Story carries a `Status:` line in its frontmatter:

```
Draft → Proposed → Accepted → Implemented → Superseded | Withdrawn
```

- **Draft**: still being written; no one is acting on it.
- **Proposed**: ready for review.
- **Accepted**: agreed; work may begin (for ADRs, this is the immutable-from-now state).
- **Implemented**: shipped to `main`.
- **Superseded** / **Withdrawn**: replaced by another doc / abandoned. Link to the replacement.

## Linking rules

Links flow **upward**: smaller docs cite their parents, not the other way around.

- A Feature lists the **PRD section** it serves and the **ADRs** it depends on.
- A Story lists its parent **Feature**.
- A Task is inside a Story file — no link needed.

Use relative markdown links: `[ADR-0001](../../adr/0001-python-host-rust-core.md)`.

## Starting a new doc

1. Copy the matching file from `templates/` into the right directory.
2. Pick the next free number (4 digits).
3. Fill in the frontmatter (`Status: Draft`, date, author).
4. Open a PR. Reviewers look at the *doc*, not the code — that comes next.

## Seed examples

The repo ships with one of each so the format is concrete:

- [PRD-0001 — gatecheck](prd/0001-gatecheck.md)
- [ADR-0001 — Python host + Rust core split](adr/0001-python-host-rust-core.md)
- [FEAT-0001 — Config loader](features/FEAT-0001-config-loader/feature.md)
- [STY-0001 — Load check.toml](features/FEAT-0001-config-loader/stories/STY-0001-load-check-toml.md)
