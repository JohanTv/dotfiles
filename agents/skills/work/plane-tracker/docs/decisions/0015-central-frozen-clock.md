---
id: "0015"
title: Central clock module in production and frozen clock in test harnesses
status: accepted
created: 2026-11-01
summary: All time reads pass through a single clock module, and golden tests freeze time via a dedicated launcher without runtime environment flags.
---

# 0015 · Central Clock Module and Frozen Test Clock

Related: [0012](./0012-fast-testing-strategy.md).

## Context

Tests previously drifted or broke when fixture dates matched real-time calendar days. Direct calls to `datetime.now()` across production prevented deterministic replay.

## Decision

- `plane_cli/clock.py` is the single source of truth for current time (`timestamp()`, `now()`, `local_now()`, `local_today()`). AST fitness tests verify zero unapproved time calls outside this module.
- Golden tests execute through `tests/plane_clock.py` to freeze the wall clock deterministically without masking timestamps in golden fixtures.
- Test suites can run with arbitrary frozen timestamps (`run_parallel.py --freeze <ISO>`).

## Consequences

- Worklog calculation bugs are immediately caught by deterministic golden outputs.
- No debug or mock flags are required in production runtime.
