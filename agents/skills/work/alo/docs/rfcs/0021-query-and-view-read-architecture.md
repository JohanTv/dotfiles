---
id: "0021"
title: Architectural model for queries, views, and JSON envelopes
status: implemented
created: 2026-11-02
summary: Architectural overhaul establishing layer separation, standardized envelope contracts, and fitness function safeguards (F1-F15).
---

# 0021 · Query and View Read Architecture

Related: Decision [0025](../decisions/0025-json-read-contract.md), [principles.md](../principles.md).

## Context

Prior to this architecture, CLI read operations coupled network access, database queries, terminal rendering, and error handling into ad-hoc scripts. Adding views or supporting LLM agents produced inconsistent formatting and fragile error handling.

## Implemented Architecture

1. **Layer Separation:**
   - **Data Access (`store_*`):** Low-level SQLite operations and cache hydration.
   - **Query Engine (`query_*`):** Scope resolution, filtering, and aggregate calculations.
   - **Renderers (`render_*`):** Terminal output formatting (tabular, colors, markdown).
   - **Envelope (`envelope`):** Standard `plane-tracker/1` JSON envelope for machine/agent integration.
2. **Fitness Functions (F1-F15):** Automated architectural tests in `tests/test_architecture.py` verifying layer boundaries, zero unapproved network calls in offline reads, and contract consistency.
3. **Migration Completed:** All 9 phases (0 through 8) were implemented and verified with golden test suites.
