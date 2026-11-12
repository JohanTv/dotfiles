# Development Documentation

Engineering decisions and architectural proposals for `plane-tracker`. Agents do not load this folder during runtime. Operational usage guides reside in [`../references/`](../references/README.md).

- **Index with Document Status:** [INDEX.md](./INDEX.md) (generated).
- **Design Principles:** [principles.md](./principles.md).
- **Public Repository Boundaries:** [0007](./decisions/0007-instance-agnostic-documents.md).
- **Resolved Bugs & Fixes:** [CHANGELOG.md](./CHANGELOG.md).
- **Pending Defects & Deferred Improvements:** [BACKLOG.md](./BACKLOG.md).

## Categories

| Directory | Purpose | Lifecycle |
| :--- | :--- | :--- |
| `decisions/` | Architectural Decisions (ADR) | `accepted` \| `superseded` |
| `rfcs/` | Design Proposals and RFCs | `draft` → `proposed` → `accepted` → `implemented` \| `rejected` \| `superseded` |

## Conventions

1. **Naming:** `NNNN-slug-in-lowercase.md`. Each `NNNN` identifier is unique across all categories and never reused.
2. **Mandatory Front-Matter:**
   ```yaml
   ---
   id: "0028"
   title: Short Descriptive Title
   status: accepted
   created: 2026-11-09
   summary: One-line summary for the index table.
   ---
   ```
3. **Instance Agnostic:** Never include real URLs, API tokens, customer names, or employee identities.
4. **Index Regeneration:** After creating or editing a document, update the index via `python3 scripts/docs_index.py`.
