# Engineering Backlog

Open technical considerations and deferred improvements for `plane-tracker`.

## Deferred Enhancements

- **0003 · External Standby Data Source:** Design a telemetry mechanism or external data source for logging blocker / standby durations (RFC 0006).
- **0004 · Verify `external_id` GET Contract:** Validate whether Plane API returns `external_id` in comment listings on all deployment versions.
- **0009 · Complete Repository Data Sanitization:** Verify complete scrubbing of residual mock UUIDs and placeholder instance names from golden test fixtures.
- **0013 · Multi-Instance Outbox Target:** Add destination instance metadata to SQLite outbox entries to safely route pending queued mutations when switching profiles.
- **0023 · HTTP 403 Read Graceful Degradation:** Improve multi-project read operations (`list --all-projects`) to degrade gracefully with partial coverage warnings when encountering permission restrictions on inaccessible projects.
