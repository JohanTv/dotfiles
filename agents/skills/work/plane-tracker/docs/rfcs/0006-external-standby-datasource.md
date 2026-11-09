---
id: "0006"
title: Determine reliable data source for external standby and blockers
status: proposed
created: 2026-10-31
summary: Proposal to unify external blocker visibility with agenda dashboards (RFC 0005) and report flow metrics instead of overloading comment telemetry.
---

# 0006 · Data Source for External Standby and Blockers

Related: [BACKLOG.md](../BACKLOG.md), [RFC 0005](./0005-personal-agenda-and-backlog.md), [CLI_DESIGN_GUARD](../../references/CLI_DESIGN_GUARD.md).

## Context

Time reports historically presented a row indicating `"⏸️ Standby externo: 0h 00m (Sin bloqueos reportados)"` even though no verifiable telemetry mechanism exists to capture blocker durations.

Earlier proposals considered introducing a `--stopper "<reason>"` flag to `comment add` or `comment edit`.

## Original Essence and Business Value

The motivation behind capturing external standby addresses a critical operational need:
1. **Preventing the "Invisibility" of Stalled Work:** Engineering time is not exclusively active flow. Work regularly stops due to external dependencies (pending infrastructure credentials, tech lead PR reviews, client feedback, third-party vendor downtime).
2. **Leadership Bottleneck Visibility:** If an engineer logs zero hours because a task is blocked, a conventional report misleadingly implies inactivity or developer delay. Leadership needs visibility into blocked initiatives to intervene and unblock the team.
3. **Why Earlier Approaches Failed:**
   * Compact comment templates (≤700 chars, adopted for token economy) removed the historical JSON block (`is_blocked`, `blocker_details`), leaving `stoppers_json` unpopulated.
   * Attempting to revive it via `--stopper "<reason>"` on `comment add` created an architectural antipattern: it conflated effort telemetry with ticket lifecycle state, had no duration metric, and duplicated the native Plane state `Pausado`.

## Architectural Evaluation (CLI Design Guard)

Evaluating `--stopper` against the [CLI Design Guard](../../references/CLI_DESIGN_GUARD.md) confirms it must be rejected:
1. **Domain Isolation:** `comment add` governs *Session Effort Telemetry* (minutes, track, capacity). Blockers govern *Ticket State Lifecycle*.
2. **Telemetry Without Duration:** A text reason does not measure time. Displaying `0h 00m` or requiring manual minutes (`--stopper-duration`) injects synthetic guesses.
3. **Canonical Primitive:** The CLI already has a native mechanism for blockers:
   ```bash
   plane-tracker update <TICKET> --state Pausado
   ```

## Convergence Plan: Unification with Agenda and Flow Metrics

Rather than forcing blockers into daily worklog comments, the essence is captured across two purpose-built views:

### 1. Qualitative Blocker Visibility in `agenda` (RFC 0005)
The personal and team dashboard (`plane-tracker agenda` / [RFC 0005](./0005-personal-agenda-and-backlog.md)) is the natural home for active impediments:
* List tickets currently in state `Pausado`.
* Display the blockage reason (extracted from the last comment's "Siguiente / bloqueo" bullet or transition note) and elapsed days in standby (`Pausado hace 1.5 d`).
* Provides leadership and developers with immediate visibility of stalled work without touching worklog telemetry.

### 2. Quantitative Blocker Telemetry in `report flow`
Cycle time and lead time analysis (`plane-tracker report flow`) is the natural home for duration metrics:
* Measure standby duration automatically from state transition audit logs (`In Progress -> Paused` to `Paused -> In Progress`).
* Zero manual flags or estimated minutes; 100% verified state data.

### 3. Cleanup of `report time`
* Prune the synthetic `"⏸️ Standby externo: 0h 00m"` row from `timeutil.py` and `render_time.py`.
* Deprecate the unused `stoppers_json` database column.
* Daily time reports remain strictly dedicated to verifiable engineering effort.
