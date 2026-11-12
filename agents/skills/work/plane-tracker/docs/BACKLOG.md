# Engineering Backlog

Open technical considerations, pending defects, and deferred improvements for `plane-tracker`.

## Known Defects

- **0031 · Past-day worklogs fall back to the publication instant as `end_time`:** `comment add --date <past day> --duration N` without `--since`/`--until` records the publication hour as the end of the window, a documented fallback for retroactive entries. On a past day that fallback is semantically invalid: records logged in one sitting all end at the same minute, so the day's union collapses below the declared effort (the active clock under-reports) while per-ticket consolidation reports an inflated AI leverage (`active_mins / wall_minutes`). With early records the same fallback stretches the union towards the publication hour, so a single day can claim a far longer span than the work done. `report time` buckets and unions per day, so the distortion is intra-day, not cross-day. Fix: warn or reject a past `--date` without an explicit window, and anchor the default edges to the recorded day.
- **0032 · `comment edit --duration` leaves duration and window contradictory:** editing only the duration is documented as "change only what is requested", but `corrected_metadata` keeps the previous `start_time`/`end_time`, so the worklog declares N minutes inside a window sized by the old duration. Reports keep counting the old span until `--since`/`--until` are passed by hand, and nothing warns about the mismatch. Fix: derive the free edge from the new duration (keeping the anchored one) or warn that the clock will not change.

## Deferred Enhancements

- **0033 · Comments without a worklog:** every publication currently demands hours; without `--duration` and without measured evidence `comment add` only prints a proposal and exits. A `--no-worklog` flag would publish text-only comments while stating explicitly that no telemetry was recorded (see [P1](../principles.md) and [P2](../principles.md)).
- **0011 · Multi-Machine Cache Architecture:** Guidelines and workflow conventions for multi-workstation environments via Plane API delta sync ([RFC 0011](rfcs/0011-shared-cache-between-machines.md)).
- **0014 · Personal and Work Contexts:** Profile isolation (`~/.config/plane-tracker/profiles/`) and interchangeable issue tracker adapters (Plane, Linear, Markdown) ([RFC 0014](rfcs/0014-personal-and-work-contexts.md)).

## Recently Implemented

- **0005 · Personal Agenda Dashboard:** Offline-first personal dashboard with WIP limits and stalled work detection ([RFC 0005](rfcs/0005-personal-agenda-and-backlog.md)).
- **0006 · Blocker Telemetry & Standby Metrics:** Standby duration in `report flow` from state transitions and qualitative blockers in `agenda` ([RFC 0006](rfcs/0006-external-standby-datasource.md)).
- **0026 · Capacity Target Distribution & Variances:** Measuring recorded effort against user-declared capacity targets in `report time` ([RFC 0026](rfcs/0026-time-distribution-against-plan.md)).
