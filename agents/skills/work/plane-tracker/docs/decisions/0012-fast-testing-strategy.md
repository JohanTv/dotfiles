---
id: "0012"
title: Fast testing strategy - process parallelism, responsive fake server, and zero-wait launcher
status: accepted
created: 2026-10-31
summary: Reduced test suite execution from 157s sequential to ~30-40s parallel without altering production code or introducing external dependencies.
---

# 0012 · Fast Testing Strategy

## Context

The full test suite (over 400 tests) required ~157 seconds sequentially. Running tests during development needed to be fast, reliable, and isolated without exhausting machine resources.

## Decision

1. **Responsive and Quiet Fake HTTP Server:** Uses `serve_forever(poll_interval=0.01)` to eliminate teardown delays and suppresses deliberate connection drops.
2. **Zero-Wait Test Launcher (`tests/plane_fast.py`):** Runs the exact production `main()` but shortens read timeouts to 1s in test harnesses.
3. **Process-Level Parallelism (`tests/run_parallel.py`):** Standard library only (`ThreadPoolExecutor` spawning low-priority worker processes). Each worker runs in an isolated temporary `HOME`/`TMPDIR` without inheriting ambient `PLANE_*` credentials. Heavy test modules are partitioned per-method.
4. **Standard Reference:** Sequential `python3 -m unittest discover -s tests` remains the baseline for single test debugging and golden updates (`GOLDEN_UPDATE=1`).

## Consequences

- Full parallel suite runs reliably in ~30 seconds across multi-core systems.
- Zero external dependencies required (no pytest or xdist needed).
