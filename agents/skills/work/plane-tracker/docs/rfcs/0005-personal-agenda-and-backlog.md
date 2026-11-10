---
id: "0005"
title: Personal activity agenda view and backlog deferral tracking
status: implemented
created: 2026-10-31
summary: Proposal for personal agenda reporting, tracking active load, overdue tickets, and documented backlog deferrals.
---

# 0005 · Personal Activity Agenda and Backlog Deferral Tracking

Related: [principles.md](../principles.md), Decision [0019](../decisions/0019-person-filters-and-assignment-history.md), RFC [0006](./0006-external-standby-datasource.md).

## Context

While `plane-tracker` tracks time and synchronizes issues, engineers often need a unified view answering: "What work is assigned to me, what is overdue, what was deferred, and why?".

## Proposal

1. **Phase 0 (Implemented in Decision 0019):** Persist assignees and creators in local cache; enable `--mine`, `--created`, and `--involved`.
2. **Phase 1 (`agenda` View):** Render a fast, offline-first personal dashboard:
   - **Active Load:** In-progress issues against recommended WIP limits, overdue items, and stalled issues (>N days without movement).
   - **Active Blockers / Standby (RFC 0006):** Issues in state `Pausado` with documented blockage reasons and elapsed standby days.
   - **Committed Work:** Issues in progress, priority, due date, age.
   - **Next:** Up next in backlog and review.
   - **Deferred Backlog:** Deferral reasons documented in worklog comments.
   - **Capacity Balance:** Weekly distribution across deep work, toil/support, and coordination buckets.
