---
id: "0006"
title: Determine reliable data source for external standby and blockers
status: proposed
created: 2026-10-31
summary: Proposal to either substantiate external blocker durations with verifiable state-transition telemetry or remove the synthetic standby row from time reports.
---

# 0006 · Data Source for External Standby and Blockers

Related: [BACKLOG.md](../BACKLOG.md), [CLI_DESIGN_GUARD](../../references/CLI_DESIGN_GUARD.md).

## Context

Time reports historically presented a row indicating `"⏸️ Standby externo: 0h 00m (Sin bloqueos reportados)"` even though no verifiable telemetry mechanism exists to capture blocker durations.

Previous discussions considered introducing a `--stopper "<reason>"` flag to `comment add` or `comment edit`.

## Architectural Evaluation (CLI Design Guard)

Evaluating the proposed `--stopper` flag against the [CLI Design Guard](../../references/CLI_DESIGN_GUARD.md) heuristics reveals critical design flaws:

1. **Violation of Domain Isolation (Single Responsibility):**
   `comment add` / `comment edit` governs *Session Worklog Telemetry* (effort, track, capacity bucket). A stopper is a *Ticket State Transition* (blockage, impediment). Overloading worklog commands with ticket lifecycle concerns creates tight coupling and hidden side-effects.
2. **Telemetry Without Duration:**
   Passing `--stopper "<reason>"` annotates a text reason but provides no timestamped duration. Synthetic durations or manual minutes would represent unverified guesswork.
3. **Existing Canonical Primitive:**
   The CLI already possesses a deterministic mechanism for external blockers:
   ```bash
   plane-tracker update <TICKET> --state Pausado
   ```
   When work resumes, the ticket transitions back:
   ```bash
   plane-tracker update <TICKET> --state Progreso
   ```

## Proposal

We reject adding `--stopper` to `comment add` / `comment edit`. Instead, choose between:

### Option A: Prune Standby Row from Reports (Recommended)
* Remove `"⏸️ Standby externo"` from `plane-tracker report time` and `render_time.py`.
* Deprecate the unused `stoppers_json` database column and remove hardcoded `"stoppers": []` fixtures.
* **Benefit:** Eliminates dead schema baggage and guarantees that 100% of metrics presented in reports are verifiable telemetry.

### Option B: Automatic State-Transition Telemetry (Deferred)
* Compute blocker duration automatically from ticket audit transitions (`In Progress -> Paused` to `Paused -> In Progress`).
* Requires synchronizing Plane activity history into local SQLite.
* Zero manual CLI flags required; respects CQS and domain boundaries.
