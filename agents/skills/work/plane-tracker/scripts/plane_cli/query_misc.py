"""Consultas de las vistas simples: `whoami`, `attachment list` y `outbox list`.

Expone: whoami(), attachments(), outbox().
No hace: red ni imprimir. `outbox list` solo lee la cola local; `attachment list` transforma lo que freshness.fetch_attachments trajo de la API.
"""

from plane_cli.coverage import Coverage, Result
from plane_cli.outbox import list_items


def whoami(identity, coverage):
    return Result(rows=[identity], total=1, coverage=coverage)


def attachments(issue_ref, items, coverage):
    rows = [{"ticket": issue_ref, "id": a.get("id"), "name": (a.get("attributes") or {}).get("name"), "size": (a.get("attributes") or {}).get("size") or a.get("size"),
             "created_at": a.get("created_at")} for a in items]
    return Result(rows=rows, total=len(rows), coverage=coverage)


def outbox(conn, include_all=False):
    rows = [{**{k: v for k, v in item.items() if k != "duration_minutes"}, "minutes": item["duration_minutes"]} for item in list_items(conn, include_all=include_all)]
    return Result(rows=rows, total=len(rows), coverage=Coverage(source="local", complete=True))
