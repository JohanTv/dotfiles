"""Lecturas desde la caché local cuando Plane no responde: aviso de antigüedad, sincronización de tickets y snapshots.

Expone: warn_stale(), serve_stale(), fail_no_cache(), sync_project_issues(), needs_sync(), last_sync(), sync_issues_cache(), save_snapshot(), offline_issue(),
issue_stub().
No hace: formatear la salida de los comandos ni decidir cuándo estar sin conexión (eso lo señala PlaneUnavailable).
Servir datos vencidos solo ocurre ante PlaneUnavailable: con red, los TTL siguen mandando.
"""

import json
import sys
import urllib.error
import urllib.parse

from plane_cli import api, clock
from plane_cli.api import PlaneUnavailable, api_request
from plane_cli.errors import CliError
from plane_cli.timeutil import age_text

ISSUES_TTL = 1800  # 30 minutos
ISSUES_MAX_PAGES = 20
RATE_RESERVE = 3  # peticiones que se dejan sin gastar de cada ventana de tasa
ISSUE_FIELDS = "id,sequence_id,name,priority,state,created_at,updated_at,completed_at,start_date,target_date,archived_at,assignees,created_by,labels"
SNAPSHOT_KEEP_DAYS = 90
SNAPSHOT_MAX_ROWS = 300


def warn_stale(updated_at):
    sys.stderr.write(f"⚠ Datos locales de hace {age_text(clock.timestamp() - updated_at)}; Plane no responde.\n")


def fail_no_cache(what):
    """Plane no responde y no hay nada local: lanza un PlaneUnavailable (kind "no_cache") que el CLI traduce al código 3."""
    raise PlaneUnavailable("no_cache", "no", message=f"Plane no responde y no hay caché local de {what}.")


def serve_stale(rows, what):
    """Las filas locales (aunque hayan vencido) con su aviso; sin filas lanza PlaneUnavailable (ver fail_no_cache). Usa la fila más antigua."""
    if not rows:
        fail_no_cache(what)
    warn_stale(min(r["updated_at"] for r in rows))
    return rows


class RateBudgetExhausted(Exception):
    """El presupuesto de peticiones por ventana se agotó a mitad de una lectura: lo traído hasta ahora es parcial."""


def _check_budget():
    remaining = api.rate_limit()
    if remaining and remaining["remaining"] is not None and remaining["remaining"] <= RATE_RESERVE:
        raise RateBudgetExhausted()


def _fetch_all_issues(base_url, api_key, workspace, project_id):
    """(tickets, total_count del servidor o None, recortado). Un error HTTP definitivo se lanza como HTTPError; el presupuesto agotado, como RateBudgetExhausted."""
    results, cursor, total = [], None, None
    for _ in range(ISSUES_MAX_PAGES):
        _check_budget()
        url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/?per_page=100&fields={ISSUE_FIELDS}"
        if cursor:
            url += f"&cursor={urllib.parse.quote(cursor)}"
        data = api_request(url, api_key, raise_on_error=True)
        results += data.get("results", [])
        total = data.get("total_count", total)
        cursor = data.get("next_cursor")
        if not data.get("next_page_results") or not cursor:
            return results, total, False
    return results, total, True


def _ref_id(value):
    """UUID de una referencia a persona: Plane la devuelve como cadena o, según el endpoint, como objeto con `id`."""
    return value.get("id") if isinstance(value, dict) else value


def assignee_ids(issue):
    """Lista de UUID de los asignados de un issue (vacía si no hay o el dato no viene)."""
    return [i for i in (_ref_id(a) for a in (issue.get("assignees") or [])) if i]


def _label_names_by_id(conn, project_id):
    """{UUID: nombre} de las etiquetas del proyecto que hay en la tabla `labels` (la puebla resolve.sync_issues antes de sincronizar)."""
    return {r["id"]: r["name"].lower().strip() for r in conn.execute("SELECT id, name FROM labels WHERE project_id = ?", (project_id,))}


def last_sync(conn, project_id):
    """Instante (época) de la última sincronización de tickets del proyecto, o None si nunca hubo."""
    row = conn.execute("SELECT as_of FROM issue_sync WHERE project_id = ?", (project_id,)).fetchone()
    if row:
        return row["as_of"]
    row = conn.execute("SELECT MAX(updated_at) AS t FROM issues_cache WHERE project_id = ?", (project_id,)).fetchone()
    return row["t"] if row else None


def needs_sync(conn, project_id, force_refresh=False):
    """True si hay que ir a Plane: se fuerza, nunca se sincronizó o venció el TTL."""
    synced = last_sync(conn, project_id)
    return bool(force_refresh or not synced or (clock.timestamp() - synced) >= ISSUES_TTL)


def _mark_stale(conn, project_id):
    with conn:
        conn.execute("UPDATE issue_sync SET stale = 1 WHERE project_id = ?", (project_id,))


def sync_project_issues(conn, base_url, api_key, workspace, project_id, project_ident, force_refresh=False, offline=False):
    """Sincroniza los tickets del proyecto en SQLite (solo GET). Devuelve (estado, as_of) y nunca imprime ni termina el programa.

    Estados: `fresh` (vigente), `synced`, `stale` (se sirvió lo almacenado vencido: la red falló o se pidió --offline), `rate_limited` (se detuvo antes de
    agotar el presupuesto de tasa y se conserva lo almacenado), `forbidden` (403: el usuario no tiene acceso al proyecto) y `unavailable` (sin red ni datos).
    as_of es el instante de la última sincronización completa (None si no hay). Persiste por proyecto el recuento del servidor, el recorte y si se sirvió vencido.
    """
    previous = last_sync(conn, project_id)
    if offline or not needs_sync(conn, project_id, force_refresh):
        expired = previous is not None and clock.timestamp() - previous >= ISSUES_TTL
        return ("unavailable" if previous is None else "stale" if expired and offline else "fresh"), previous
    now = clock.timestamp()
    try:
        _check_budget()
        states_by_id = {s["id"]: (s["name"], s.get("group", "")) for s in
                        api_request(f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/states/", api_key, raise_on_error=True).get("results", [])}
        results, total, capped = _fetch_all_issues(base_url, api_key, workspace, project_id)
    except RateBudgetExhausted:
        if previous:
            _mark_stale(conn, project_id)
        return "rate_limited", previous
    except PlaneUnavailable:
        if previous:
            _mark_stale(conn, project_id)
        return ("stale" if previous else "unavailable"), previous
    except urllib.error.HTTPError as exc:
        exc.close()
        if exc.code == 403:
            return "forbidden", previous
        raise CliError("http_error", f"HTTP {exc.code} al leer los tickets de {project_ident}.", detail={"status": exc.code}) from exc

    label_names = _label_names_by_id(conn, project_id)
    with conn:
        conn.execute("DELETE FROM issues_cache WHERE project_id = ?", (project_id,))
        for iss in results:
            seq = iss.get("sequence_id")
            if not seq:
                continue
            s_info = states_by_id.get(iss.get("state"), ("Pendiente", "unstarted"))
            conn.execute("""
                INSERT INTO issues_cache (id, sequence_id, ticket_id, project_id, title, state_name, state_group, priority, labels_csv, updated_at,
                                          created_at, completed_at, start_date, target_date, archived_at, assignees_json, created_by, plane_updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (iss["id"], seq, f"{project_ident}-{seq}", project_id, iss.get("name", ""), s_info[0], s_info[1], iss.get("priority", "none"),
                  ",".join(sorted({label_names[i] for i in (_ref_id(l) for l in iss.get("labels") or []) if i in label_names})), now,
                  iss.get("created_at"), iss.get("completed_at"), iss.get("start_date"), iss.get("target_date"), iss.get("archived_at"),
                  json.dumps(assignee_ids(iss)), _ref_id(iss.get("created_by")), iss.get("updated_at")))
        conn.execute("DELETE FROM issues_fts;")
        conn.execute("INSERT INTO issues_fts (ticket_id, title, labels_csv) SELECT ticket_id, title, labels_csv FROM issues_cache;")
        conn.execute("""
            INSERT INTO issue_sync (project_id, total_count, fetched, capped, stale, as_of) VALUES (?, ?, ?, ?, 0, ?)
            ON CONFLICT(project_id) DO UPDATE SET total_count = excluded.total_count, fetched = excluded.fetched, capped = excluded.capped,
                stale = 0, as_of = excluded.as_of
        """, (project_id, total, len(results), int(capped), now))
    return "synced", now


def sync_issues_cache(conn, base_url, api_key, workspace, project_id, project_ident, force_refresh=False):
    """sync_project_issues para los comandos que aún no usan el modelo de vistas: avisa por stderr o falla con el código 3 si no hay nada local."""
    status, as_of = sync_project_issues(conn, base_url, api_key, workspace, project_id, project_ident, force_refresh=force_refresh)
    if status in ("stale", "rate_limited"):
        warn_stale(as_of)
    elif status == "unavailable":
        fail_no_cache(f"los tickets de {project_ident}")
    elif status == "forbidden":
        raise CliError("http_error", f"Sin acceso al proyecto {project_ident} (HTTP 403).", detail={"status": 403})


def save_snapshot(conn, issue, ticket_id, comments=None):
    """Guarda la última lectura completa de un ticket. Sin `comments` (--no-comments) solo se renueva el issue."""
    now = clock.timestamp()
    issue_json = json.dumps(issue, ensure_ascii=False)
    with conn:
        if comments is None:
            conn.execute("""
                INSERT INTO issue_snapshots (issue_id, ticket_id, fetched_at, issue_json) VALUES (?, ?, ?, ?)
                ON CONFLICT(issue_id) DO UPDATE SET ticket_id = excluded.ticket_id, fetched_at = excluded.fetched_at, issue_json = excluded.issue_json
            """, (issue["id"], ticket_id, now, issue_json))
        else:
            conn.execute("""
                INSERT INTO issue_snapshots (issue_id, ticket_id, fetched_at, issue_json, comments_json, comments_fetched_at) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(issue_id) DO UPDATE SET ticket_id = excluded.ticket_id, fetched_at = excluded.fetched_at, issue_json = excluded.issue_json,
                    comments_json = excluded.comments_json, comments_fetched_at = excluded.comments_fetched_at
            """, (issue["id"], ticket_id, now, issue_json, json.dumps(comments, ensure_ascii=False), now))
        conn.execute("DELETE FROM issue_snapshots WHERE fetched_at < ?", (now - SNAPSHOT_KEEP_DAYS * 86400,))
        conn.execute("DELETE FROM issue_snapshots WHERE issue_id NOT IN (SELECT issue_id FROM issue_snapshots ORDER BY fetched_at DESC LIMIT ?)",
                     (SNAPSHOT_MAX_ROWS,))


def offline_issue(conn, project_id, seq_id, uuid_ref, ticket_id):
    """Lo que hay en local de un ticket: snapshot completo o, a falta de él, los metadatos de issues_cache; None si no hay nada.

    Devuelve {"issue", "comments" (None si nunca se trajeron), "fetched_at", "metadata_only", "state_name"}.
    """
    snap = conn.execute("SELECT * FROM issue_snapshots WHERE issue_id = ? OR ticket_id = ? ORDER BY fetched_at DESC LIMIT 1",
                        (uuid_ref or "", ticket_id)).fetchone()
    if snap:
        issue = json.loads(snap["issue_json"])
        row = conn.execute("SELECT name FROM states WHERE id = ?", (issue.get("state"),)).fetchone()
        return {"issue": issue, "comments": json.loads(snap["comments_json"]) if snap["comments_json"] is not None else None,
                "fetched_at": snap["fetched_at"], "metadata_only": False, "state_name": row["name"] if row else None}
    row = conn.execute("SELECT * FROM issues_cache WHERE id = ? OR (project_id = ? AND sequence_id = ?) LIMIT 1", (uuid_ref or "", project_id, seq_id)).fetchone()
    if not row:
        return None
    issue = {"id": row["id"], "sequence_id": row["sequence_id"], "name": row["title"], "priority": row["priority"], "state": None,
             "created_at": row["created_at"], "completed_at": row["completed_at"], "start_date": row["start_date"], "target_date": row["target_date"]}
    return {"issue": issue, "comments": None, "fetched_at": row["updated_at"], "metadata_only": True, "state_name": row["state_name"]}


def issue_stub(conn, project_id, seq_id, uuid_ref, ticket_label):
    """Ticket reconstruido desde lo local para encolar sin red: {"id": None, "name", "sequence_id", "ticket_id"} (id nunca se conoce)."""
    local = offline_issue(conn, project_id, seq_id, uuid_ref, ticket_label)
    issue = local["issue"] if local else {}
    row = conn.execute("SELECT ticket_id, sequence_id, title FROM issues_cache WHERE ticket_id = ? OR id = ? LIMIT 1", (ticket_label, uuid_ref or "")).fetchone()
    return {"id": None, "name": issue.get("name") or (row["title"] if row else ""), "sequence_id": issue.get("sequence_id") or (row["sequence_id"] if row else seq_id),
            "ticket_id": row["ticket_id"] if row else None}
