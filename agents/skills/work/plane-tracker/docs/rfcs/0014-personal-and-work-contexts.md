---
id: "0014"
title: Contexts, profiles, and interchangeable task management sources
status: proposed
created: 2026-11-01
summary: Deferred proposal exploring multi-profile isolation (personal vs corporate) and abstracting issue trackers (Plane, Linear, Markdown).
---

# 0014 · Contexts, Profiles, and Interchangeable Task Sources

Related: [principles.md](../principles.md), RFC [0011](./0011-shared-cache-between-machines.md).

## Context

The CLI currently assumes a single corporate Plane environment. Engineers often navigate multiple contexts (professional employment, personal research, open-source projects) and may track tasks across diverse backends (Plane, Linear, GitHub Issues, or local Markdown files).

## Proposal

1. **Profile Isolation:** Support separate profiles with distinct SQLite databases, credentials, and configuration directories (e.g. `~/.config/plane-tracker/profiles/<profile>/`).
2. **Activity Ledger as Core:** Position the local activity ledger and time analytics as the primary system, treating remote trackers as pluggable sync adapters.
3. **Pluggable Tracker Adapters:** Define standard interfaces for task resolution and time logging across external providers.
