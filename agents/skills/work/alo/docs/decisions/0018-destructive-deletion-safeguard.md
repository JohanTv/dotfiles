---
id: "0018"
title: Safeguards against accidental worklog destruction during ticket deletion
status: accepted
created: 2026-11-01
summary: The delete command fails closed, reads live remote comments alongside local cache, and strictly rejects deletion if foreign worklogs exist.
---

# 0018 · Safeguards Against Accidental Worklog Destruction

Related: [principles.md](../principles.md), RFC [0011](../rfcs/0011-shared-cache-between-machines.md).

## Context

In Plane CE, worklog entries are stored as ticket comments with embedded telemetry blocks. Deleting an issue destroys all associated comments and historical worklogs irrevocably.

## Decision

- **Live Remote Inspection:** Before deletion, `delete` fetches live comments for the target issue via cursor pagination.
- **Fail Closed:** If the issue has no worklogs, deletion requires `--yes`. If it has own worklogs, it additionally requires `--discard-worklogs`. If it contains worklogs logged by other users, deletion is rejected unconditionally.
- **Default Path is Cancellation:** Team members are advised to transition issues to `Cancelled` rather than deleting issues with history.
- **Purge Sequence:** Confirm eligibility -> issue remote `DELETE` to Plane -> prune local cache upon HTTP 204.

## Consequences

- Accidental loss of billable or logged engineering hours is prevented.
