---
id: "0026"
title: Measuring time distribution against user-declared capacity plans
status: accepted
created: 2026-11-03
summary: Proposal to measure recorded time against user-configured engineering capacity targets (features, support, tech debt, learning, overhead).
---

# 0026 · Measuring Time Distribution Against User-Declared Plans

Related: [principles.md](../principles.md), Decision [0025](../decisions/0025-json-read-contract.md).

## Context

While `report time` aggregates logged hours by project and bucket, it historically lacked the ability to compare actual hours against planned allocations (e.g., 50% feature development, 30% support, 15% debt reduction, 5% learning).

## Proposal

1. **Taxonomy Alignment:** Classify work into clear classes (`feature`, `support`, `debt`, `learning`, `overhead`).
2. **Planned vs Actual Comparison:** Enable user configuration for weekly target distribution and display variances in `report time`.
3. **Transparent Non-Accounted Time:** Explicitly report untracked working hours to maintain honest metrics.
4. **Agent Time Segregation:** Distinctly isolate synthetic agent leverage minutes from human clock effort to prevent skewed ratios.
