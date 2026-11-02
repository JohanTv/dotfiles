"""Consulta de la vista `report time`: las horas del autor en el periodo, su resumen y las notas propias de la vista.

Expone: query().
No hace: red ni escribir; solo lee SQLite (store_worklogs) y la cola local de salida. Solo cuentan las horas CON autor igual al del alcance (las de autor nulo se excluyen y se avisan
con `hours_unsigned`). Lo que no vino en el comentario consta en `provenance` y el balde por defecto va en `undeclared`, nunca sumado a `deep_work` (aviso `hours_defaulted`).
`summary.by_day` son minutos de reloj (unión de intervalos del día); `by_project` y `by_capacity`, esfuerzo (suma de `minutes`). Sin límite: `count == total`.
"""

import json
from dataclasses import replace

from plane_cli import store_worklogs
from plane_cli.coverage import Result, complete_time, settle
from plane_cli.outbox import count_open
from plane_cli.timeutil import calculate_klee_union_minutes, expand_segments, time_to_minutes

UNDECLARED = "undeclared"
CONTRACT_NAME = {"capacity_bucket": "capacity"}  # nombre de la columna -> nombre del contrato


def _row(r):
    defaulted = json.loads(r["defaulted_json"] or "[]")
    capacity_default = "capacity_bucket" in defaulted
    row = {"ticket": r["ticket_id"], "title": r["issue_name"] or None, "project": r["project_id"], "date": r["date"], "start_time": r["start_time"],
           "end_time": r["end_time"], "minutes": r["duration_minutes"], "track": r["track"], "capacity": r["capacity_bucket"], "phase": r["phase"],
           "role": r["role"], "worker_type": r["worker_type"], "notes": r["notes"], "author": r["author_id"],
           "provenance": {CONTRACT_NAME.get(f, f): "default" for f in defaulted}}
    stoppers = [s for s in json.loads(r["stoppers_json"] or "[]") if s]
    if stoppers:
        row["stoppers"] = stoppers
    try:
        segments = json.loads(r["raw_payload"] or "{}").get("segments")
    except ValueError:
        segments = None
    if segments:
        row["segments"] = segments
    return row, capacity_default


def _summary(entries):
    """entries: [(fila del contrato, balde por defecto)] -> {by_day, by_project, by_capacity, effort_clock_minutes, effort_compute_minutes}."""
    days, projects, capacities = {}, {}, {}
    for row, capacity_default in entries:
        for part in expand_segments([{"date": row["date"], "start_time": row["start_time"], "end_time": row["end_time"], "duration_minutes": row["minutes"],
                                      "raw_payload": json.dumps({"segments": row.get("segments")})}]):
            days.setdefault(row["date"], []).append((time_to_minutes(part["start_time"]), time_to_minutes(part["end_time"])))
        projects[row["project"]] = projects.get(row["project"], 0) + row["minutes"]
        bucket = UNDECLARED if capacity_default else row["capacity"]
        capacities[bucket] = capacities.get(bucket, 0) + row["minutes"]
    by_day = [{"key": d, "minutes": calculate_klee_union_minutes(iv)} for d, iv in sorted(days.items())]
    as_list = lambda totals: [{"key": k, "minutes": v} for k, v in sorted(totals.items())]
    return {"by_day": by_day, "by_project": as_list(projects), "by_capacity": as_list(capacities), "effort_clock_minutes": sum(d["minutes"] for d in by_day),
            "effort_compute_minutes": sum(row["minutes"] for row, _ in entries)}


def _notes(conn, scope, mine, unsigned, undeclared):
    idents = [p.ident for p in scope.projects]
    notes = []
    if unsigned:
        notes.append({"code": "hours_unsigned", "text": f"{unsigned} registro(s) de horas sin autor registrado: no cuentan como tuyos."})
    if undeclared:
        notes.append({"code": "hours_defaulted", "text": f"{undeclared} registro(s) sin balde de capacidad declarado: van en `undeclared`, no en `deep_work`."})
    period = scope.period
    pending = count_open(conn, period["from"], period["to"], idents[0] if len(idents) == 1 else None, scope.track)
    if pending:
        notes.append({"code": "pending_unpublished", "text": f"{pending} registro(s) de este periodo siguen sin publicarse."})
    return tuple(notes)


def query(conn, scope, acq):
    """Result de `report time`: filas del vocabulario `hours`, resumen y cobertura con `complete` calculado (y degradado a None si la vista añade avisos)."""
    idents = [p.ident for p in scope.projects]
    found = store_worklogs.rows(conn, idents, scope.period["from"], scope.period["to"], scope.track, scope.worker_type)
    unsigned = sum(1 for r in found if r["author_id"] is None)
    entries = [_row(r) for r in found if r["author_id"] == scope.hours_author]
    undeclared = sum(1 for _, default in entries if default)
    extra = _notes(conn, scope, entries, unsigned, undeclared)
    cov = settle(replace(acq, complete=complete_time(acq)), extra)
    return Result(rows=[row for row, _ in entries], total=len(entries), coverage=cov, summary=_summary(entries), extra_notes=extra)
