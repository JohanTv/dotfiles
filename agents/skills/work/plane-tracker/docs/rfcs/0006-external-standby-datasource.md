---
id: "0006"
title: Determine reliable data source for external standby and blockers
status: proposed
created: 2026-10-31
summary: Proposal to either substantiate external blocker durations with verifiable telemetry or remove the standby row from time reports.
---

# 0006 · Data Source for External Standby and Blockers

Related: [BACKLOG.md](../BACKLOG.md).

## Context

Time reports historically presented a row indicating "External Standby: 0h 00m" even when no telemetry capture mechanism existed to log blocker durations.

## Proposal

1. Evaluate whether executive reporting requires blocker tracking.
2. If required, implement a repeatable `--stopper "<reason>"` flag in `comment add`/`edit`, or compute duration automatically from ticket state transitions (`Paused` / `Blocked`).
3. If not required, omit the standby row from reports to prevent presenting unverified metrics.
