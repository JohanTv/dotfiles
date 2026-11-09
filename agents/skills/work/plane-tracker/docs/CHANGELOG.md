# Changelog

Historical fixes and resolutions implemented in `plane-tracker`.

## Resolved Issues

- **0001 · Retroactive Time Logging:** Added exact `--start-time` and `--end-time` calculation to prevent timestamp drift when recording declared worklogs.
- **0010 · Partial Period Sync in Reports:** Ensured `report time` synchronizes remote worklogs even when local database contains partial records for the period.
- **0016 · Unescaped Telemetry Metadata Blocks:** Corrected markdown-to-HTML conversion so `<!-- PLANE_WORKLOG_METADATA ... -->` comments are cleanly preserved and hidden across comment edit and add workflows.
- **0017 · Comprehensive Worklog Sync:** Removed hardcoded project limits; enabled multi-project worklog synchronization and reliable pagination.
- **0020 · Issue Cache Label Persistence:** Fixed `sync_issues_cache` to serialize and persist `labels_csv` into SQLite FTS5 tables instead of empty strings.
- **0022 · Explicit Telemetry Defaults vs Measured:** Disambiguated default fallback values from explicit metadata attributes (bucket, phase, worker type) in telemetry envelopes.
- **0024 · Read View Query Optimization:** Replaced unbounded full issue scans with targeted lookups and early exit to minimize network payload and token consumption.
