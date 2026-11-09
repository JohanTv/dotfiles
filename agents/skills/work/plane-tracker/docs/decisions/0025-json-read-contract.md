---
id: "0025"
title: Stable read envelope contract plane-tracker/1
status: accepted
created: 2026-11-02
summary: Specification of the standard read envelope, family fields, error codes, and coverage metadata for all CLI read views.
---

# 0025 · Stable Read Envelope Contract `plane-tracker/1`

Promoted from RFC 0021 as the stable interface contract. Represents the machine-readable specification that any AI agent or external consumer can depend on across `--json` invocations.

## Read Envelope Structure

```json
{
  "schema": "plane-tracker/1",
  "view": "list",
  "scope": {"projects": ["PRJ"], "ticket_person": {"relation": "assigned", "actor": "<uuid>"}, "state": "open", "text": "form", "order": "rank,-sequence", "limit": 20},
  "total": 3,
  "count": 3,
  "results": [ { "...": "family vocabulary fields" } ],
  "summary": null,
  "coverage": {"source": "cache", "as_of": "2026-11-02T12:00:00Z", "age_s": 60, "stale": false, "complete": true, "unavailable": [], "detail": {}},
  "notes": []
}
```

| Key | Type | Description |
| :--- | :--- | :--- |
| `schema` | string | `plane-tracker/<n>`; breaking changes increment `<n>` via an ADR. |
| `view` | string | One of the registered views (`list`, `get`, `report time`, `report flow`, `worklog check`, `labels`, `projects`, `whoami`, `attachment list`, `outbox list`). |
| `scope` | object | Resolved filter scope applicable to the current view. |
| `total` | int | Total matching records before pagination limit. |
| `count` | int | Number of records returned in `results` (`len(results)`). |
| `results` | array | Data rows restricted strictly to the defined schema family. |
| `summary` | object \| null | Aggregate statistics when supported by the view. |
| `coverage` | object | Metadata describing data provenance, freshness, and completeness. |
| `notes` | array | Diagnostic notes (`{code, text, hint?}`) sorted by severity. |

## Vocabulary and Scope Keys

- Dimensions: `projects`, `person`, `period`, `state`, `text`
- Controls: `limit`, `refresh`, `offline`, `verbose`, `brief`
- Scope Keys: `projects`, `ticket_person`, `hours_author`, `period`, `state`, `text`, `order`, `limit`, `track`, `worker_type`
- Person Relations: `assigned`, `created`, `involved`
- States: `open`, `all`
- Coverage Sources: `cache`, `api`, `snapshot`, `local`, `mixed`
