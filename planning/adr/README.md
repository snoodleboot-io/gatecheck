# Architecture Decision Records

This directory contains the ADRs for `hooksmith`. Each ADR captures one decision: the context that forced it, the choice made, and what changed because of it.

## Format

We use a lightweight MADR-inspired layout. The template lives at [`../templates/adr.md`](../templates/adr.md). Sections, in order:

1. **Frontmatter** (id, title, status, author, date, supersedes/superseded-by).
2. **Context** — what made this decision necessary.
3. **Decision** — one or two sentences, stated as fact.
4. **Consequences** — positive, negative, and follow-up effects.
5. **Alternatives considered** — what lost, and why.

## Immutability

Once an ADR moves to `Status: Accepted`, **it is not edited**. If the decision changes:

1. Write a new ADR with the next number.
2. Set the new ADR's `supersedes:` field to the old ADR's ID.
3. In a single follow-up commit, set the old ADR's `status: Superseded` and `superseded-by:` to point at the new one.

This keeps the history of *why* the project is the way it is — useful for new contributors and for re-litigating decisions only when the context has actually changed.

## Status values

`Draft → Proposed → Accepted → Superseded | Withdrawn`

- **Draft** — being written, no review yet.
- **Proposed** — open for review on a PR.
- **Accepted** — merged; treat as immutable.
- **Superseded** — replaced by a later ADR.
- **Withdrawn** — never accepted; kept for the historical record.

## Index

- [ADR-0001 — Python host + Rust core split](0001-python-host-rust-core.md)
