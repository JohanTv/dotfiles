"""Flujo por work item: lead/cycle time, tiempo por estado y esfuerzo (para `get --history`) y la lectura incremental de las transiciones de estado.

Expone: build_ticket_flow(), flow_to_json(), fetch_transitions(), transitions_fresh(), worklogs_from_comments().
No hace: escribir en Plane.
"""

import json
import sys
import urllib.error
import urllib.parse

import flow_metrics
import session_clock

from plane_cli.api import api_request
from plane_cli.assignments import assignment_rows, record_assignments
from plane_cli.resolve import get_states_map
from plane_cli.timeutil import time_to_minutes
from plane_cli.worklog import extract_metadata_from_comment
from plane_cli import clock


FLOW_TTL_SECONDS = 3600
FLOW_MAX_PAGES = 20


def load_states_by_id(conn, base_url, api_key, workspace, project_id):
    get_states_map(conn, base_url, api_key, workspace, project_id)
    rows = conn.execute("SELECT id, name, group_name FROM states WHERE project_id = ?", (project_id,)).fetchall()
    return {r["id"]: {"name": r["name"], "group": r["group_name"]} for r in rows}


def transitions_fresh(conn, issue):
    """True si las transiciones del ticket están al día: traídas con su historial, sin que el ticket haya cambiado, y (si sigue abierto) hace menos de una hora."""
    cached = conn.execute("SELECT fetched_at, issue_updated_at, assignments_fetched FROM flow_fetch WHERE issue_id = ?", (issue["id"],)).fetchone()
    return bool(cached and cached["issue_updated_at"] == issue.get("updated_at") and cached["assignments_fetched"]
                and (issue.get("completed_at") or clock.timestamp() - cached["fetched_at"] < FLOW_TTL_SECONDS))


def fetch_transitions(conn, base_url, api_key, workspace, project_id, issue, ticket_label, strict=False):
    """Transiciones de estado del issue (Plane no tiene endpoint por proyecto: una llamada por ticket).

    Incremental: un ticket cuyo updated_at no cambió no se vuelve a pedir (los abiertos expiran a la hora). Las mismas actividades traen los
    cambios de asignado (assignments.py); un ticket sin ese historial se vuelve a pedir una vez. Con `strict` una falla de red se propaga (barrido).
    """
    now = clock.timestamp()
    if not transitions_fresh(conn, issue):
        found, assigned, cursor = [], [], None
        try:
            for _ in range(FLOW_MAX_PAGES):
                url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/activities/?per_page=100"
                if cursor:
                    url += f"&cursor={urllib.parse.quote(cursor)}"
                data = api_request(url, api_key, raise_on_error=True)
                for a in data.get("results", []):
                    assigned += assignment_rows(a, issue["id"], ticket_label)
                    if a.get("field") == "state" and a.get("new_identifier") and a.get("created_at"):
                        found.append((a["id"], issue["id"], ticket_label, a["created_at"], a.get("old_identifier"),
                                      a["new_identifier"], a.get("old_value"), a.get("new_value")))
                if not data.get("next_page_results"):
                    break
                cursor = data.get("next_cursor")
            with conn:
                conn.executemany("INSERT OR REPLACE INTO state_transitions VALUES (?,?,?,?,?,?,?,?)", found)
                record_assignments(conn, assigned)
                conn.execute("INSERT OR REPLACE INTO flow_fetch (issue_id, fetched_at, issue_updated_at, assignments_fetched) VALUES (?,?,?,1)",
                             (issue["id"], now, issue.get("updated_at")))
        except (urllib.error.URLError, OSError) as exc:
            if strict:
                raise
            sys.stderr.write(f"⚠ Sin conexión con Plane para {ticket_label} ({exc}): se usan las transiciones almacenadas.\n")
    rows = conn.execute("SELECT at_utc, from_id, to_id FROM state_transitions WHERE issue_id = ? ORDER BY at_utc", (issue["id"],)).fetchall()
    return [{"at": session_clock.parse_time(r["at_utc"]), "from_id": r["from_id"], "to_id": r["to_id"]} for r in rows]


def worklogs_from_comments(comments):
    """Worklogs de TODOS los comentarios del ticket (complementa la caché local, que puede no tenerlos)."""
    out, seen = [], set()
    for c in comments:
        if c.get("id") in seen:
            continue
        seen.add(c.get("id"))
        meta = extract_metadata_from_comment(c.get("comment_html", ""))
        if not meta:
            continue
        dur = meta.get("duration_minutes") or meta.get("duration_net_minutes")
        if not dur and meta.get("start_time") and meta.get("end_time"):
            dur = time_to_minutes(meta["end_time"]) - time_to_minutes(meta["start_time"])
            if dur < 0:
                dur += 24 * 60
        if not dur or dur < 1 or not meta.get("date"):
            continue  # sin fecha medida no se puede ubicar en la ventana del flujo
        out.append({"date": meta.get("date"), "start_time": meta.get("start_time"), "end_time": meta.get("end_time"),
                    "duration_minutes": dur, "worker_type": meta.get("worker_type", "human"), "plane_comment_id": c.get("id"),
                    "segments": meta.get("segments")})
    return out


def build_ticket_flow(conn, base_url, api_key, workspace, project_id, issue, ticket_label):
    states = load_states_by_id(conn, base_url, api_key, workspace, project_id)
    transitions = fetch_transitions(conn, base_url, api_key, workspace, project_id, issue, ticket_label)
    # Esfuerzo = worklogs locales (los registrados con --duration no viajan en el comentario) ∪ los que
    # traen metadata en los comentarios de Plane, sin duplicar por id de comentario.
    wls = [dict(r) for r in conn.execute(
        "SELECT date, start_time, end_time, duration_minutes, worker_type, plane_comment_id, raw_payload FROM worklogs WHERE ticket_id = ?", (ticket_label,))]
    for w in wls:
        try:
            w["segments"] = json.loads(w.pop("raw_payload") or "{}").get("segments")
        except ValueError:
            w["segments"] = None
    known = {w["plane_comment_id"] for w in wls if w["plane_comment_id"]}
    try:
        c_url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
        wls += [w for w in worklogs_from_comments(api_request(c_url, api_key, raise_on_error=True).get("results", []))
                if w["plane_comment_id"] not in known]
    except (urllib.error.URLError, OSError):
        sys.stderr.write(f"⚠ Sin acceso a los comentarios de {ticket_label}: esfuerzo solo de la caché local.\n")
    created = session_clock.parse_time(issue.get("created_at"))
    if not created:
        return None, transitions, states
    flow = flow_metrics.compute_flow(
        {"name": issue.get("name"), "created_at": created, "completed_at": session_clock.parse_time(issue.get("completed_at")), "state": issue.get("state")},
        transitions, states, wls, clock.now())
    return flow, transitions, states


def flow_to_json(flow):
    out = dict(flow)
    for key in ("created", "closed"):
        out[key] = out[key].isoformat() if out.get(key) else None
    return out
