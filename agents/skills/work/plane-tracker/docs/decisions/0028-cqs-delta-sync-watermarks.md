---
id: "0028"
title: CQS separation and timestamp-based delta sync watermarks
status: accepted
created: 2026-11-09
summary: Architectural decision enforcing strict CQS (read views are 100% offline-first queries) and delta sync using ISO timestamps and SQLite sync_watermarks.
---

# 0028 · CQS Separation and Timestamp-Based Delta Sync Watermarks

Related: RFC [0027](../rfcs/0027-incremental-sync-and-granularity.md).

## Context

Previous iterations coupled read operations (`list`) with network synchronization attempts, which led to high latency (~8-15s), unnecessary API pagination, and token bloat during agent discovery workflows. Furthermore, running `sync` triggered an exhaustive 30-day worklog download every time.

## Decision

1. **Strict Command-Query Separation (CQS):**
   - Read commands (`list`, `get`, `report time --offline`) execute purely against the local SQLite store without network side-effects.
   - Synchronization is the exclusive responsibility of `plane-tracker sync <target>`.
2. **Granular Sync Targets:**
   - Supported targets: `tickets`, `hours`, `catalogs`, and `all`.
   - `plane-tracker sync tickets [-p PRJ]` performs a fast delta synchronization (~1s) instead of fetching historical worklogs.
3. **Timestamp Watermarks (`sync_watermarks`):**
   - Stores `last_synced_at` ISO timestamps per entity/project in SQLite.
   - Queries Plane API using `order_by=-updated_at` and halts pagination upon encountering issues older than the stored watermark.
   - Forced re-index is available via `--deep`.
4. **Reactive FTS5 Sync Triggers:**
   - Database triggers (`trg_issues_cache_ai`, `trg_issues_cache_au`, `trg_issues_cache_ad`) keep the FTS5 full-text index in sync automatically on issue upsert/delete.

## Consequences

- Zero-moment agent ticket lookups complete in <0.1s against local SQLite.
- Network API calls and token waste are reduced by >90% during routine CLI operations.
