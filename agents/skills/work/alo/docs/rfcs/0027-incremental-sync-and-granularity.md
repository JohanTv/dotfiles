---
id: "0027"
title: Incremental delta sync, target granularity, and CQS separation
status: implemented
created: 2026-11-09
summary: Architectural overhaul establishing strict CQS for read views, granular sync targets, SQLite watermark timestamps, and early-exit pagination.
---

# 0027 · Incremental Delta Sync, Target Granularity, and CQS Separation

Related: Decision [0028](../decisions/0028-cqs-delta-sync-watermarks.md), [principles.md](../principles.md).

## Context

Prior versions conflated reading and mutating state: `list` triggered network fetches upon cache expiration or `--refresh`, violating Command-Query Separation (CQS) and causing erratic read latencies. Simultaneously, `sync` performed a monolithic full download of 30 days of comments and deleted all cached issues prior to re-inserting them.

## Implemented Architecture

1. **Strict Command-Query Separation (CQS):**
   - `list`, `get`, and `report time --offline` are pure queries running against local SQLite (<5ms).
   - All network mutations are managed strictly via `plane-tracker sync <target>`.
2. **Granular Sync Targets:**
   - `sync tickets [-p PRJ]` (tickets only, fast delta ~1s).
   - `sync hours` (telemetry comments and worklogs).
   - `sync catalogs` (states, labels, projects).
   - `sync all` (complete synchronization).
3. **Delta Sync Watermarks (`sync_watermarks`):**
   - SQLite table storing `last_synced_at` ISO timestamps per entity and project.
   - Paginates Plane API with `order_by=-updated_at` and terminates pagination as soon as an issue's `updated_at` is older than the stored watermark.
   - Upserts issue records without destroying table indexes; automatic FTS5 triggers synchronize search indices reactively.
   - Full re-sync is explicitly supported via `--deep`.

## Verification and Results

- Zero-moment ticket discovery drops from ~5-8s to <0.1s.
- Routine delta synchronizations require 1-2 API requests rather than exhaustive pagination sweeps.
