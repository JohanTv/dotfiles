# Changelog

Historical fixes and resolutions implemented in `plane-tracker`.

## Resolved Issues

- **0001 · Retroactive Time Logging:** Added exact `--start-time` and `--end-time` calculation to prevent timestamp drift when recording declared worklogs.
- **0004 · Comment `external_id` Verification:** Verified live Plane CE/Cloud API contract; confirmed Plane preserves and returns both `external_source` and `external_id` in GET comment payloads, backing outbox deduplication with fallback HTML parsing.
- **0009 · Repository Data Sanitization:** Scrubbed residual hardcoded workspace slug (`teamprogra`) and project UUID fallbacks from `cli.py` and `db.py`; enforced strict environment configuration (`PLANE_WORKSPACE_SLUG`).
- **0010 · Partial Period Sync in Reports:** Ensured `report time` synchronizes remote worklogs even when local database contains partial records for the period.
- **0013 · Multi-Instance Outbox Target:** Added destination instance and workspace metadata (`target_base_url`, `target_workspace`) to SQLite outbox entries, isolating flush execution, stderr pending notices, unique worklog constraints, and reporting coverage to matching workspaces, with RFC 3986 URL normalization.
- **0016 · Unescaped Telemetry Metadata Blocks:** Corrected markdown-to-HTML conversion so `<!-- PLANE_WORKLOG_METADATA ... -->` comments are cleanly preserved and hidden across comment edit and add workflows.
- **0017 · Comprehensive Worklog Sync:** Removed hardcoded project limits; enabled multi-project worklog synchronization and reliable pagination.
- **0020 · Issue Cache Label Persistence:** Fixed `sync_issues_cache` to serialize and persist `labels_csv` into SQLite FTS5 tables instead of empty strings.
- **0022 · Explicit Telemetry Defaults vs Measured:** Disambiguated default fallback values from explicit metadata attributes (bucket, phase, worker type) in telemetry envelopes.
- **0023 · HTTP 403 Read Graceful Degradation:** Improved multi-project worklog sync and time reports (`report time --all-projects`) to degrade gracefully on 403 Forbidden responses, recording `forbidden` in coverage details and emitting `source_forbidden` notes without crashing.
- **0024 · Read View Query Optimization:** Replaced unbounded full issue scans with targeted lookups and early exit to minimize network payload and token consumption.
