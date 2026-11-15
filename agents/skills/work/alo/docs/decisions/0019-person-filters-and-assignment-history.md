---
id: "0019"
title: Person filters in list and verified assignment history
status: accepted
created: 2026-11-02
summary: Supported --mine, --created, and --involved filters over SQLite cache, tracking assignment events durable across cache refreshes.
---

# 0019 · Person Filters in `list` and Verified Assignment History

Related: [principles.md](../principles.md), RFC [0005](../rfcs/0005-personal-agenda-and-backlog.md).

## Context

The CLI needed the ability to answer personal capacity questions ("what tasks belong to me?", "where did I participate?"). Ticket reassignment across team members meant "assigned now" is insufficient to track historical participation.

## Decision

- **`--mine`** filters by currently assigned issues.
- **`--created`** filters by creator.
- **`--involved`** unions assigned now, creator, author of logged hours, and historical assignees with documented provenance.
- **Durable Assignment Table:** Assignment events (`assignment_events`) are persisted in SQLite, surviving `issues_cache` rebuilds.
- **Fail Closed Identity:** `PLANE_USERNAME` resolves once and is cached. Without valid identity, personal filters exit with a descriptive usage error.

## Consequences

- Offline-first execution: all personal filters query local SQLite cache.
- Freshness metadata explicitly declares age of cached assignment state.
