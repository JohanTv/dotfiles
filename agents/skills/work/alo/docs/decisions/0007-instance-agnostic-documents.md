---
id: "0007"
title: Documentation is agnostic of instances, organizations, and individuals
status: accepted
created: 2026-10-31
summary: Repository documents must not contain hosts, IPs, real names, or real worklog data; instance-specific data lives outside the repository.
---

# 0007 · Documentation is Agnostic of Instances, Organizations, and Individuals

## Context

The repository is public and the tool may be used against any Plane deployment. Documentation and test fixtures must remain strictly generic without real customer names, infrastructure IPs, or corporate identifiers.

## Decision

- Documentation uses generic roles ("tech lead", "commercial rep"), synthetic ticket keys (`PROJ-123`), and example endpoints (`https://plane.example.com`).
- Concrete instance metadata (hosts, API tokens, user UUIDs, worklogs) resides strictly in local environment configuration or Plane itself, never in tracked repository files.
- Example payloads and tests use synthetic test fixtures.

## Consequences

- All new documents and test fixtures are verified for absence of real hostnames, IPs, or corporate identities.
