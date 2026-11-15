# Engineering Backlog

Open technical considerations, pending defects, and deferred improvements for `plane-tracker`.

## Known Defects

(None pending)

## Deferred Enhancements

- **0011 · Multi-Machine Cache Architecture:** Guidelines and workflow conventions for multi-workstation environments via Plane API delta sync ([RFC 0011](rfcs/0011-shared-cache-between-machines.md)).
- **0014 · Personal and Work Contexts:** Profile isolation (`~/.config/plane-tracker/profiles/`) and interchangeable issue tracker adapters (Plane, Linear, Markdown) ([RFC 0014](rfcs/0014-personal-and-work-contexts.md)).

## Recently Implemented

- **0031 · Strict Past-Day Window Bounds:** `comment add --date <past_day>` rejects manual duration without an explicit window, preventing active clock collapse and AI leverage distortion.
- **0032 · Coherent Free-Edge Derivation on Duration Edits:** `comment edit --duration N` anchors `start_time` and recalculates `end_time` strictly preserving the duration-window invariant $\Delta(\text{start}, \text{end}) = \text{duration}$.
- **0033 · Decoupled Text Comments Without Worklogs:** Support for `--no-worklog` in `comment add`, allowing coordination and note-taking without spurious time tracking or database collisions.

- **0005 · Personal Agenda Dashboard:** Offline-first personal dashboard with WIP limits and stalled work detection ([RFC 0005](rfcs/0005-personal-agenda-and-backlog.md)).
- **0006 · Blocker Telemetry & Standby Metrics:** Standby duration in `report flow` from state transitions and qualitative blockers in `agenda` ([RFC 0006](rfcs/0006-external-standby-datasource.md)).
- **0026 · Capacity Target Distribution & Variances:** Measuring recorded effort against user-declared capacity targets in `report time` ([RFC 0026](rfcs/0026-time-distribution-against-plan.md)).
