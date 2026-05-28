---
id: FEAT-NNNN
title: <short title>
status: Draft
owner: <name>
date: YYYY-MM-DD
prd: <PRD-NNNN section>
adrs: [ADR-NNNN, ...]
---

# FEAT-NNNN: <title>

## Summary

One paragraph: what this feature does for the user.

## Why

Link to the parent PRD section and the ADRs that shaped the approach. If this feature exists because of a constraint not captured in those docs, write it here.

## User-facing surface

What the user sees or types. CLI flags, config keys, output formats. Treat this section as the contract.

## Out of scope

What this feature does *not* cover. Helps prevent scope creep during story breakdown.

## Stories

List of stories that together complete this feature.

- [ ] [STY-NNNN — <title>](stories/STY-NNNN-<slug>.md)
- [ ] …

## Acceptance

How we know the feature is done — the conditions that must hold once every story above is shipped.
