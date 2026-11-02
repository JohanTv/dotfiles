"""Consulta de la vista `list`: selecciona, ordena y recorta tickets de la caché y arma el Result con su cobertura.

Expone: query(), select(), ticket_row().
No hace: red, escribir ni imprimir; solo lee SQLite a través de store_issues. Orden total y declarado en scope.order: con texto, relevancia y desempate
`-sequence`; sin texto, `plane_updated_at` descendente con NULL al final, luego proyecto y secuencia descendente. `total` es el recuento antes del límite.
El texto busca en título y etiquetas (no en la descripción) y la cobertura lo declara en detail.text_fields. Qué significa cada persona (docs/decisions/0019):
  assigned  asignado ahora (según la última sincronización de la caché);  created  creador del ticket;
  involved  la unión de asignado, creador, con horas tuyas (autor registrado en la base local) y asignado alguna vez (historial medido), con la razón de cada uno.
"""

import json
import re
from dataclasses import replace

import flow_metrics

from plane_cli import store_issues
from plane_cli.assignments import assignment_events_for, history_coverage
from plane_cli.coverage import Result, complete_list

_ID_LIKE = re.compile(r"^(?:[A-Za-z]+-)?\d+$")


def _project_of(row):
    return row["ticket_id"].rsplit("-", 1)[0]


def _ordered(rows, scope):
    """Orden total: con texto, relevancia y `-sequence`; sin texto, recencia descendente con NULL al final y desempate por proyecto y secuencia descendente."""
    if scope.text:
        return sorted(rows, key=lambda r: (r["rank"], -r["sequence_id"]))
    rows = sorted(rows, key=lambda r: (_project_of(r), -r["sequence_id"]))
    return sorted(rows, key=lambda r: r["plane_updated_at"] or "", reverse=True)  # estable: los NULL ("") quedan al final


def select(conn, scope, project_ids):
    """(tickets que cumplen el alcance, ordenados, cada uno {row, assignees, reasons}; cuántos se saltaron por no tener datos de asignación)."""
    person = scope.ticket_person
    relation, actor = (person["relation"], person["actor"]) if person else (None, None)
    mine, unsigned = store_issues.worklog_minutes(conn, actor) if relation == "involved" else ({}, {})
    ever = store_issues.ever_assigned(conn, actor) if relation == "involved" else set()
    out, unknown = [], 0
    for row in _ordered(store_issues.rows(conn, project_ids, scope.text), scope):
        if scope.state == "open" and (row["state_group"] in flow_metrics.TERMINAL_GROUPS or row["archived_at"]):
            continue
        if relation and row["assignees_json"] is None:
            unknown += 1
            continue
        assignees = json.loads(row["assignees_json"] or "[]")
        reasons = []
        if actor and actor in assignees:
            reasons.append("asignado")
        if actor and row["created_by"] == actor:
            reasons.append("creador")
        if relation == "involved":
            if mine.get(row["ticket_id"]):
                reasons.append(f"horas tuyas ({mine[row['ticket_id']]} min)")
            elif unsigned.get(row["ticket_id"]):
                reasons.append(f"horas sin autor registrado ({unsigned[row['ticket_id']]} min)")
            if row["id"] in ever and "asignado" not in reasons:
                reasons.append("fue asignado")
        keep = {None: True, "assigned": "asignado" in reasons, "created": "creador" in reasons, "involved": bool(reasons)}[relation]
        if keep:
            out.append({"row": row, "assignees": assignees, "reasons": reasons})
    return out, unknown


def ticket_row(conn, item, names, scope):
    """Fila del vocabulario `ticket` (breve si scope.brief)."""
    row = item["row"]
    base = {"ticket": row["ticket_id"], "title": row["title"], "state": row["state_name"] or "unknown", "state_group": row["state_group"],
            "project": _project_of(row)}
    if scope.brief:
        return base
    out = {**base, "priority": row["priority"], "created_by": row["created_by"], "labels": [x for x in (row["labels_csv"] or "").split(",") if x],
           "start_date": row["start_date"], "target_date": row["target_date"], "created_at": row["created_at"], "completed_at": row["completed_at"],
           "plane_updated_at": row["plane_updated_at"], "assignees": [{"id": a, "name": names.get(a) or a[:8]} for a in item["assignees"]]}
    if scope.ticket_person:
        out["reasons"] = item["reasons"]
    if scope.ticket_person and scope.ticket_person["relation"] == "involved":
        out["assignment_events"] = [{"at": e["at_utc"], "kind": e["kind"], "user_id": e["user_id"], "user_name": e["user_name"]}
                                    for e in assignment_events_for(conn, row["id"])]
    return out


def _detail(conn, scope, project_ids, acq, unknown):
    info, counts = store_issues.sync_info(conn, project_ids), store_issues.cached_counts(conn, project_ids)
    uuid_ident = {p.uuid: p.ident for p in scope.projects}
    mismatch = sorted(uuid_ident[pid] for pid in project_ids if pid in info and info[pid]["total_count"] is not None and info[pid]["total_count"] != counts.get(pid, 0))
    capped = sorted(uuid_ident[pid] for pid in project_ids if pid in info and info[pid]["capped"])
    unverifiable = any(pid not in info or info[pid]["total_count"] is None for pid in project_ids)
    detail = dict(acq.detail)
    detail["capped"] = sorted(set(detail.get("capped", [])) | set(capped))
    detail["count_mismatch"] = mismatch
    detail["legacy"] = bool(unknown) or (unverifiable and bool(project_ids))
    detail["text_fields"] = ["title", "labels"] if scope.text else []
    if scope.ticket_person:
        detail["assignment_snapshot"] = True
    if scope.ticket_person and scope.ticket_person["relation"] == "involved":
        verified, total = history_coverage(conn, [r["id"] for r in store_issues.rows(conn, project_ids)])
        detail["history"] = {"verified": verified, "total": total}
        detail["hours_scope"] = "local"
    return {k: v for k, v in detail.items() if v}


def _extra_notes(conn, scope):
    notes = []
    if scope.text and _ID_LIKE.match(scope.text):
        notes.append({"code": "text_looks_like_id", "text": f"El texto '{scope.text}' parece un ticket: se buscó como texto.", "hint": f"plane-tracker get {scope.text}"})
    if scope.ticket_person and scope.ticket_person["relation"] == "involved":
        unsigned = store_issues.unsigned_hours(conn)
        if unsigned:
            notes.append({"code": "hours_unsigned", "text": f"{unsigned} registro(s) de horas sin autor registrado (anteriores a esta versión o sin identidad).",
                          "hint": "plane-tracker report time --refresh"})
    return tuple(notes)


def query(conn, scope, catalogs, acq):
    """Result de `list`: filas del vocabulario `ticket`, total antes del límite y cobertura con `complete` calculado."""
    project_ids = [p.uuid for p in scope.projects]
    items, unknown = select(conn, scope, project_ids)
    page = items[:scope.limit] if scope.limit else items
    names = catalogs.member_names() if (not scope.brief and any(i["assignees"] for i in page)) else {}
    detail = _detail(conn, scope, project_ids, acq, unknown)
    cov = replace(acq, detail=detail)
    return Result(rows=[ticket_row(conn, i, names, scope) for i in page], total=len(items), coverage=replace(cov, complete=complete_list(cov)), extra_notes=_extra_notes(conn, scope))
