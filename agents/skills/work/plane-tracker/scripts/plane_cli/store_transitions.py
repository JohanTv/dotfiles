"""Almacén de solo lectura de lo que necesita `report flow`: tickets del periodo, sus filas en caché, transiciones de estado y estados del proyecto.

Expone: flow_tickets(), issue_rows(), states_of(), transitions_of(), worklogs_of(), history_coverage().
No hace: red ni escribir (las transiciones las trae flow.fetch_transitions desde freshness). Es lo que permite calcular el flujo con `--offline`.
"""

import json
from datetime import timedelta, timezone

import session_clock


def _like(idents):
    return " OR ".join("ticket_id LIKE ?" for _ in idents), [f"{i}-%" for i in idents]


def _zone(offset):
    """timezone a partir de `+HH:MM` / `-HH:MM` (la zona con que se interpreta el periodo)."""
    sign = -1 if offset.startswith("-") else 1
    hours, minutes = offset.lstrip("+-").split(":")
    return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))


def flow_tickets(conn, idents, date_from, date_to, tz="+00:00"):
    """Etiquetas de los tickets con registros de horas en el periodo o cerrados en él, de los proyectos `idents`.

    El periodo es de calendario en la zona `tz` (las fechas de las horas ya lo son); `completed_at` es un instante UTC y se convierte a esa zona antes de comparar."""
    if not idents:
        return []
    like, params = _like(idents)
    found = {r["ticket_id"] for r in conn.execute(f"SELECT DISTINCT ticket_id FROM worklogs WHERE date >= ? AND date <= ? AND ({like})", [date_from, date_to, *params])}
    zone = _zone(tz)
    for r in conn.execute(f"SELECT ticket_id, completed_at FROM issues_cache WHERE completed_at IS NOT NULL AND ({like})", params):
        closed = session_clock.parse_time(r["completed_at"])
        if closed and date_from <= closed.astimezone(zone).date().isoformat() <= date_to:
            found.add(r["ticket_id"])
    return sorted(found)


def issue_rows(conn, labels):
    """{etiqueta: fila de issues_cache} de los tickets que la caché conoce."""
    if not labels:
        return {}
    marks = ",".join("?" for _ in labels)
    return {r["ticket_id"]: r for r in conn.execute(f"SELECT * FROM issues_cache WHERE ticket_id IN ({marks})", list(labels))}


def states_of(conn, project_id):
    """{id: {name, group}} de los estados del proyecto."""
    return {r["id"]: {"name": r["name"], "group": r["group_name"]} for r in conn.execute("SELECT id, name, group_name FROM states WHERE project_id = ?", (project_id,))}


def transitions_of(conn, issue_id):
    return [{"at": session_clock.parse_time(r["at_utc"]), "from_id": r["from_id"], "to_id": r["to_id"]}
            for r in conn.execute("SELECT at_utc, from_id, to_id FROM state_transitions WHERE issue_id = ? ORDER BY at_utc", (issue_id,))]


def worklogs_of(conn, label):
    """Registros de horas locales del ticket (de cualquier fecha) con sus tramos, tal como los espera flow_metrics."""
    out = []
    for r in conn.execute("SELECT date, start_time, end_time, duration_minutes, worker_type, plane_comment_id, raw_payload FROM worklogs WHERE ticket_id = ?", (label,)):
        entry = dict(r)
        try:
            entry["segments"] = json.loads(entry.pop("raw_payload") or "{}").get("segments")
        except ValueError:
            entry["segments"] = None
        out.append(entry)
    return out


def history_coverage(conn, labels):
    """(tickets con las transiciones al día, total): al día = traídas y el ticket no cambió en Plane desde entonces."""
    if not labels:
        return 0, 0
    marks = ",".join("?" for _ in labels)
    verified = conn.execute(f"SELECT COUNT(*) FROM issues_cache c JOIN flow_fetch f ON f.issue_id = c.id WHERE c.ticket_id IN ({marks}) AND f.issue_updated_at IS c.plane_updated_at",
                            list(labels)).fetchone()[0]
    return verified, len(labels)
