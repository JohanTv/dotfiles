"""Historial de asignación de un ticket: qué cambios de asignado se midieron y con qué cobertura.

Expone: assignment_rows(), record_assignments(), assignment_events_for(), history_coverage(), sweep_history().
No hace: inferir tramos entre eventos ni quién tuvo el ticket entre ellos. Solo guarda los cambios que las actividades de Plane trajeron;
la ausencia de un evento no prueba que nunca hubo asignación (puede no haberse traído o no existir).
La forma del evento (`field == "assignees"`, UUID en `new_identifier` al añadir y en `old_identifier` al quitar, nombre en `new_value`/`old_value`)
es la que se espera de Plane y está por verificar contra una instancia real.
"""

import urllib.error

from plane_cli.api import PlaneUnavailable


def assignment_rows(activity, issue_id, ticket_label):
    """Filas de `assignment_events` de una actividad (vacío si no es un cambio de asignados). Una actividad puede añadir y quitar a la vez."""
    if activity.get("field") != "assignees" or not activity.get("created_at"):
        return []
    rows = []
    for kind, ident, name in (("added", activity.get("new_identifier"), activity.get("new_value")),
                              ("removed", activity.get("old_identifier"), activity.get("old_value"))):
        if ident:
            rows.append((f"{activity.get('id')}:{kind}", issue_id, ticket_label, activity["created_at"], kind, ident, name))
    return rows


def record_assignments(conn, rows):
    conn.executemany("INSERT OR REPLACE INTO assignment_events VALUES (?,?,?,?,?,?,?)", rows)


def assignment_events_for(conn, issue_id):
    """Eventos medidos del ticket, en orden cronológico."""
    return [dict(r) for r in conn.execute(
        "SELECT at_utc, kind, user_id, user_name FROM assignment_events WHERE issue_id = ? ORDER BY at_utc, event_id", (issue_id,))]


def history_coverage(conn, issue_ids):
    """(tickets del alcance con el historial al día, total): al día = traído y el ticket no cambió en Plane desde entonces."""
    if not issue_ids:
        return 0, 0
    marks = ",".join("?" for _ in issue_ids)
    covered = conn.execute(
        f"SELECT COUNT(*) FROM issues_cache c JOIN flow_fetch f ON f.issue_id = c.id "
        f"WHERE c.id IN ({marks}) AND f.assignments_fetched = 1 AND f.issue_updated_at IS c.plane_updated_at", list(issue_ids)).fetchone()[0]
    return covered, len(issue_ids)


def _pending(conn, rows):
    """Tickets del alcance cuyo historial falta o quedó atrás, los tocados más recientemente primero."""
    out = []
    for r in rows:
        f = conn.execute("SELECT issue_updated_at, assignments_fetched FROM flow_fetch WHERE issue_id = ?", (r["id"],)).fetchone()
        if not f or not f["assignments_fetched"] or f["issue_updated_at"] != r["plane_updated_at"]:
            out.append(r)
    return sorted(out, key=lambda r: r["plane_updated_at"] or "", reverse=True)


def sweep_history(conn, base_url, api_key, workspace, rows, budget, fetch):
    """Trae el historial de hasta `budget` tickets pendientes de `rows` (filas de issues_cache), reanudable: lo ya traído no se repite.

    `fetch(row)` pide las actividades de un ticket (flow.fetch_transitions en modo estricto). Se detiene ante la primera falla de red (429, circuito
    abierto, Plane caído) sin perder lo ya guardado. Devuelve (tickets traídos, interrumpido, pendientes que quedaron).
    """
    pending = _pending(conn, rows)
    done, interrupted = 0, False
    for row in pending[:budget]:
        try:
            fetch(row)
        except (PlaneUnavailable, urllib.error.URLError, OSError):
            interrupted = True
            break
        done += 1
    return done, interrupted, len(pending) - done
