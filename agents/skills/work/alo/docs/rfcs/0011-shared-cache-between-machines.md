---
id: "0011"
title: Multi-machine cache architecture and remote sync considerations
status: proposed
created: 2026-10-31
summary: Evaluation of multi-machine state sharing, concluding to keep local SQLite caches synchronized via Plane API rather than introducing third-party databases.
---

# 0011 · Multi-Machine Cache Architecture

Related: [principles.md](../principles.md), RFC [0014](./0014-personal-and-work-contexts.md).

## Context

Developers working across multiple workstations (e.g. office workstation and home laptop) interact with the same Plane instance. We evaluated whether a shared remote database (e.g. Supabase, Turso) was required.

## Proposal

- **Plane is the Single Remote Authority:** Issue and comment telemetry stored in Plane remains the authoritative upstream record.
- **Local SQLite Caches are Disposable:** Each machine maintains its local SQLite cache, refreshed via granular delta sync.
- **Machine Handoff Protocol:** Developers flush pending outbox queues (`plane-tracker outbox flush`) before switching machines and sync on the target machine.
- **Decision:** Reject introducing a separate remote database, preserving local-first privacy, offline capability, and zero external infrastructure requirements.
