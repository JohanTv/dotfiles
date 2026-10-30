"""Lecturas desde la caché local cuando Plane no responde: aviso de antigüedad, sincronización de tickets y snapshots.

Expone: age_text(), warn_stale(), serve_stale(), fail_no_cache(), sync_issues_cache(), save_snapshot(), offline_issue(),
cached_issues(), iso_utc().
No hace: formatear la salida de los comandos ni decidir cuándo estar sin conexión (eso lo señala PlaneUnavailable).
Servir datos vencidos solo ocurre ante PlaneUnavailable: con red, los TTL siguen mandando.
"""

import json
import sys
import time
import urllib.parse
from datetime import datetime, timezone

from plane_cli.api import PlaneUnavailable, api_request

ISSUES_TTL = 1800  # 30 minutos
ISSUES_MAX_PAGES = 20
SNAPSHOT_KEEP_DAYS = 90
SNAPSHOT_MAX_ROWS = 300
LIST_LIMIT = 50


def age_text(seconds):
    """Edad legible en min, h o d."""
    minutes = max(1, int(seconds // 60))
    if minutes < 60:
        return f"{minutes} min"
    if minutes < 1440:
        return f"{minutes // 60} h"
    return f"{minutes // 1440} d"


def warn_stale(updated_at):
    sys.stderr.write(f"⚠ Datos locales de hace {age_text(time.time() - updated_at)}; Plane no responde.\n")


def fail_no_cache(what):
    """Plane no responde y no hay nada local: lanza un PlaneUnavailable (kind "no_cache") que el CLI traduce al código 3."""
    raise PlaneUnavailable("no_cache", "no", message=f"Plane no responde y no hay caché local de {what}.")


def serve_stale(rows, what):
    """Las filas locales (aunque hayan vencido) con su aviso; sin filas lanza PlaneUnavailable (ver fail_no_cache). Usa la fila más antigua."""
    if not rows:
        fail_no_cache(what)
    warn_stale(min(r["updated_at"] for r in rows))
    return rows


def iso_utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def _fetch_all_issues(base_url, api_key, workspace, project_id):
    results, cursor = [], None
    for _ in range(ISSUES_MAX_PAGES):
        url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/?limit=100"
        if cursor:
            url += f"&cursor={urllib.parse.quote(cursor)}"
        data = api_request(url, api_key)
        results += data.get("results", [])
        cursor = data.get("next_cursor")
        if not data.get("next_page_results") or not cursor:
            break
    return results


def sync_issues_cache(conn, base_url, api_key, workspace, project_id, project_ident, force_refresh=False):
    """Sincroniza los issues del proyecto en SQLite (búsqueda FTS5 instantánea). Sin Plane sirve la caché existente."""
    now = time.time()
    row = conn.execute("SELECT MAX(updated_at) AS last_sync FROM issues_cache WHERE project_id = ?", (project_id,)).fetchone()
    last_sync = row["last_sync"] if row else None
    if not force_refresh and last_sync and (now - last_sync) < ISSUES_TTL:
        return
    states_by_id = {}
    try:
        url_states = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/states/"
        for s in api_request(url_states, api_key).get("results", []):
            states_by_id[s["id"]] = (s["name"], s.get("group", ""))
        results = _fetch_all_issues(base_url, api_key, workspace, project_id)
    except PlaneUnavailable:
        if last_sync:
            warn_stale(last_sync)
            return
        fail_no_cache(f"los tickets de {project_ident}")

    with conn:
        conn.execute("DELETE FROM issues_cache WHERE project_id = ?", (project_id,))
        for iss in results:
            seq = iss.get("sequence_id")
            if not seq:
                continue
            s_info = states_by_id.get(iss.get("state"), ("Pendiente", "unstarted"))
            conn.execute("""
                INSERT INTO issues_cache (id, sequence_id, ticket_id, project_id, title, state_name, state_group, priority, labels_csv, updated_at,
                                          created_at, completed_at, start_date, target_date, archived_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (iss["id"], seq, f"{project_ident}-{seq}", project_id, iss.get("name", ""), s_info[0], s_info[1], iss.get("priority", "none"), "", now,
                  iss.get("created_at"), iss.get("completed_at"), iss.get("start_date"), iss.get("target_date"), iss.get("archived_at")))
        conn.execute("DELETE FROM issues_fts;")
        conn.execute("INSERT INTO issues_fts (ticket_id, title, labels_csv) SELECT ticket_id, title, labels_csv FROM issues_cache;")


def save_snapshot(conn, issue, ticket_id, comments=None):
    """Guarda la última lectura completa de un ticket. Sin `comments` (--no-comments) solo se renueva el issue."""
    now = time.time()
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


def cached_issues(conn, project_id):
    """Hasta LIST_LIMIT tickets de la caché (sequence_id descendente) con la forma que usa `list` sin conexión."""
    rows = conn.execute("SELECT id, sequence_id, title, priority, state_name, updated_at FROM issues_cache WHERE project_id = ? "
                        "ORDER BY sequence_id DESC LIMIT ?", (project_id, LIST_LIMIT)).fetchall()
    return [{"id": r["id"], "sequence_id": r["sequence_id"], "name": r["title"], "priority": r["priority"], "state_name": r["state_name"],
             "cached_at": iso_utc(r["updated_at"])} for r in rows], (min(r["updated_at"] for r in rows) if rows else None)
