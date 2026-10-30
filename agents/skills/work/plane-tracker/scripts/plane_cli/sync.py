"""Sincronización de los worklogs registrados en los comentarios de Plane hacia SQLite.

Expone: sync_remote_worklogs().
No hace: imprimir reportes.
"""

import sys
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from plane_cli.api import api_request
from plane_cli.resolve import get_actor_uuid, get_projects_map
from plane_cli.timeutil import time_to_minutes
from plane_cli.worklog import extract_metadata_from_comment, upsert_worklog


def sync_remote_worklogs(conn, base_url, api_key, workspace, date_from_str, date_to_str, filter_project=None):
    """Sincroniza comentarios de Plane para tickets actualizados y los persiste en SQLite con descargas paralelas."""
    sys.stderr.write("🔄 Sincronizando registros de actividad desde Plane API...\n")
    projects_map = get_projects_map(conn, base_url, api_key, workspace)

    # Filtro por autor: solo mis comentarios alimentan mi reporte (los tickets pueden ser compartidos)
    actor_uuid = get_actor_uuid(base_url, api_key, workspace)
    if not actor_uuid:
        sys.stderr.write("⚠ Sin PLANE_USERNAME/PLANE_ACTOR_UUID: el sync mezclará horas de compañeros en tickets compartidos.\n")
    
    try:
        d_from = datetime.strptime(date_from_str, "%Y-%m-%d").date() - timedelta(days=1)
    except Exception:
        d_from = datetime.now().date() - timedelta(days=7)

    target_idents = []
    if filter_project:
        f_up = filter_project.upper()
        if f_up in projects_map:
            target_idents = [f_up]
    else:
        for pref in ["OMNIFY", "OPS", "OMNICANAL"]:
            if pref in projects_map:
                target_idents.append(pref)

    candidate_tasks = []
    for ident in target_idents:
        proj = projects_map[ident]
        proj_id = proj["id"]
        url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{proj_id}/issues/?order_by=-updated_at&limit=15"
        try:
            data = api_request(url, api_key, raise_on_error=True)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                continue
            pass
        except Exception:
            continue

        for iss in data.get("results", []):
            up_str = iss.get("updated_at")
            if not up_str:
                continue
            try:
                iss_up = datetime.fromisoformat(up_str.replace("Z", "+00:00")).date()
                if iss_up < d_from:
                    continue
            except Exception:
                pass
            candidate_tasks.append((ident, proj_id, iss))

    def fetch_comments_for_issue(task):
        ident, proj_id, iss = task
        c_url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{proj_id}/issues/{iss['id']}/comments/"
        try:
            c_data = api_request(c_url, api_key, raise_on_error=True)
            return ident, iss, c_data.get("results", [])
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                return ident, iss, []
            return ident, iss, []
        except Exception:
            return ident, iss, []

    synced_count = 0
    skipped_foreign = 0
    skipped_no_duration = 0
    if candidate_tasks:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(fetch_comments_for_issue, t) for t in candidate_tasks]
            for fut in as_completed(futures):
                ident, iss, comments = fut.result()
                for c in comments:
                    # Filtro por autor: los tickets compartidos no deben contaminar mi reporte
                    author = c.get("created_by") or c.get("actor")
                    if actor_uuid and author and author != actor_uuid:
                        skipped_foreign += 1
                        continue

                    html = c.get("comment_html", "")
                    meta = extract_metadata_from_comment(html)
                    if meta:
                        # Duración explícita (nunca inventar 60 min): metadata o rango start/end
                        dur = meta.get("duration_minutes") or meta.get("duration_net_minutes")
                        if not dur and meta.get("start_time") and meta.get("end_time"):
                            dur = time_to_minutes(meta["end_time"]) - time_to_minutes(meta["start_time"])
                            if dur < 0:
                                dur += 24 * 60
                        if not dur or dur < 1:
                            skipped_no_duration += 1
                            continue

                        ticket_label = f"{ident}-{iss.get('sequence_id')}"
                        entry = {
                            "ticket_id": ticket_label,
                            "track": meta.get("track", "main"),
                            "issue_name": iss.get("name", ""),
                            "date": meta.get("date", datetime.now().strftime("%Y-%m-%d")),
                            "start_time": meta.get("start_time", (datetime.now() - timedelta(minutes=dur)).strftime("%H:%M")),
                            "end_time": meta.get("end_time", datetime.now().strftime("%H:%M")),
                            "duration_minutes": dur,
                            "worker_type": meta.get("worker_type", "human"),
                            "capacity_bucket": meta.get("capacity_bucket", "deep_work"),
                            "phase": meta.get("phase", "dev"),
                            "role": meta.get("role", "backend_engineer"),
                            "notes": meta.get("notes", iss.get("name", "")),
                            "stoppers": meta.get("stoppers", []),
                            "plane_comment_id": c.get("id"),
                            "created_at": c.get("created_at"),
                            "raw_payload": meta
                        }
                        upsert_worklog(conn, entry)
                        synced_count += 1

    # Actualizar watermark de sync
    now = time.time()
    with conn:
        conn.execute("""
            INSERT INTO sync_metadata (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
        """, (f"sync:{workspace}", datetime.now().isoformat(), now))

    if synced_count > 0:
        sys.stderr.write(f"✔ Se sincronizaron {synced_count} registros telemétricos en SQLite3.\n")
    else:
        sys.stderr.write("ℹ Sincronización completa: sin nuevos registros telemétricos.\n")
