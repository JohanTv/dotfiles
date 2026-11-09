# Design Principles of plane-tracker

These principles guide what gets built and how. RFCs and decisions cite them by reference. All content in this repository is public: see [0007](./decisions/0007-instance-agnostic-documents.md).

## P1 · Visibility of Invisible Work
Support, meetings, ad-hoc requests, and coordination constitute real engineering work. If untracked, they disappear from visibility, falsely suggesting inactivity. The tool must make logging friction-free (one CLI command) and elevate this work alongside core feature development.

## P2 · Autonomy
Engineers retain full ownership of what is logged, when, and what gets published. Nothing is submitted automatically without user confirmation, nothing is guessed on their behalf, and time tracking measures timestamps, not keystrokes or private content.

## P3 · Data for the Engineer, Not Just Management
Every metric captured must first serve the engineer doing the work: understanding active WIP, overdue commitments, and weekly time distribution. Upward reporting is an explicit derived projection controlled by the engineer.

## P4 · Cognitive Load Reduction
The number of open tasks an engineer holds in memory is a measurable quantity. Work-in-progress (WIP) visibility, ticket age, and concise session worklogs exist to reduce context switching and cognitive strain.

## P5 · Expectation Management
Commitments, possibilities, and reports must align honestly. A deadline that passes silently or a dashboard claiming metrics without telemetry breaks trust. Forecasting relies on empirical distributions (cycle time percentiles), never wishful estimates.

## Core Technical Principles
- **Limited Work in Progress (Little's Law):** Restricting active WIP shortens cycle times and reduces cognitive burden.
- **Local-First & CQS:** Read operations run locally against SQLite; mutations happen explicitly via sync or publication commands.
- **Single Source of Truth:** Upstream state belongs in Plane; document lifecycle state belongs in document front-matter.
- **Do Not Claim What Was Not Measured:** If telemetry is missing or partial, reports must state this clearly or remain silent.

Related: [RFC 0005](./rfcs/0005-personal-agenda-and-backlog.md).
