"""Publicación de la cola de salida (`outbox flush`): orden, límites, resolución del ticket y parada ante fallos.

Expone: flush_items(), OUTBOX_MAX_AGE_DAYS, PRUNE_DAYS, DEFAULT_LIMIT, PAUSE_SECONDS.
No hace: imprimir (lo hace cmd_outbox) ni la entrega de un item (outbox.deliver).
Publica por `id` ascendente; los items de más de OUTBOX_MAX_AGE_DAYS desde su creación se omiten salvo include_old
(nunca se borran solos). Un fallo transitorio detiene el flush; un error definitivo (400, 403, 404, 422, 500) deja el
item en `failed` y sigue con el siguiente; un 401 lo detiene todo. Los `sent` y `dropped` de más de PRUNE_DAYS se podan.
"""

import contextlib
import io
import os
import time
import urllib.error
from datetime import datetime, timedelta

from plane_cli import circuit, config
from plane_cli.api import PlaneUnavailable, api_request, http_detail, probe_plane
from plane_cli.outbox import Rejected, deliver, pending_counts, stamp
from plane_cli.resolve import resolve_issue, resolve_project_and_seq

OUTBOX_MAX_AGE_DAYS = 7
PRUNE_DAYS = 30
DEFAULT_LIMIT = 25
PAUSE_SECONDS = 1.0


def _resolve_target(conn, base_url, api_key, workspace, default_project_id, ticket_ref):
    """(project_id, issue_id) de un ticket: id de la caché verificado con un GET, o el listado paginado si la caché no lo conoce."""
    project_id, seq_id, uuid_ref, _ = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, ticket_ref)
    issue_id = uuid_ref
    if not issue_id:
        row = conn.execute("SELECT id FROM issues_cache WHERE project_id = ? AND sequence_id = ?", (project_id, seq_id)).fetchone()
        issue_id = row["id"] if row else None
    if issue_id:
        api_request(f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue_id}/", api_key, raise_on_error=True)
        return project_id, issue_id
    return project_id, resolve_issue(base_url, api_key, workspace, project_id, seq_id, None)["id"]


def _target_resolver(conn, base_url, api_key, workspace, default_project_id):
    """Resolvedor memoizado por ticket durante el flush; un ticket inexistente falla una sola vez (Rejected)."""
    memo = {}

    def target_of(ticket_ref):
        def resolve():
            if ticket_ref not in memo:
                buffer = io.StringIO()
                try:
                    with contextlib.redirect_stderr(buffer):
                        memo[ticket_ref] = _resolve_target(conn, base_url, api_key, workspace, default_project_id, ticket_ref)
                except SystemExit:
                    memo[ticket_ref] = Rejected(None, buffer.getvalue().strip() or "no se pudo resolver el ticket")
                except urllib.error.HTTPError as exc:
                    detail = http_detail(exc)
                    exc.close()
                    if exc.code in (401, 429):
                        raise Rejected(exc.code, detail)
                    memo[ticket_ref] = Rejected(exc.code, detail)
            if isinstance(memo[ticket_ref], Rejected):
                raise memo[ticket_ref]
            return memo[ticket_ref]
        return resolve
    return target_of


def _prepare(conn, retry_failed):
    cutoff = (config.now() - timedelta(days=PRUNE_DAYS)).isoformat(timespec="seconds")
    with conn:
        conn.execute("DELETE FROM outbox WHERE state IN ('sent', 'dropped') AND updated_at < ?", (cutoff,))
        if retry_failed:
            conn.execute("UPDATE outbox SET state = 'pending', updated_at = ? WHERE state = 'failed'", (stamp(),))


def _too_old(item, include_old):
    age = config.now() - datetime.fromisoformat(item["created_at"])
    return not include_old and age > timedelta(days=OUTBOX_MAX_AGE_DAYS)


def flush_items(conn, base_url, api_key, workspace, default_project_id, limit=DEFAULT_LIMIT, include_old=False, retry_failed=False, sleep=None):
    """Publica la cola. Devuelve {"sent", "failed", "skipped_old", "busy", "stopped", "unavailable", "pending", "failed_total"}.

    stopped es None, "unavailable" (con `unavailable`: el PlaneUnavailable) o "unauthorized".
    """
    sleep = sleep or time.sleep
    result = {"sent": [], "failed": [], "skipped_old": 0, "busy": 0, "stopped": None, "unavailable": None}
    _prepare(conn, retry_failed)
    if not probe_plane(base_url, api_key, force=True):
        offline = os.environ.get("PLANE_OFFLINE") == "1"
        kind, since = (None, None) if offline else circuit.last_failure()
        result.update(stopped="unavailable", unavailable=PlaneUnavailable("offline" if offline else (kind or "unknown"), "no", since=since))
        return _finish(conn, result)
    now = config.now().timestamp()
    candidates = conn.execute("SELECT * FROM outbox WHERE state = 'pending' OR (state = 'sending' AND lease_until < ?) ORDER BY id", (now,)).fetchall()
    target_of = _target_resolver(conn, base_url, api_key, workspace, default_project_id)
    processed = 0
    for item in candidates:
        if _too_old(item, include_old):
            result["skipped_old"] += 1
            continue
        if processed >= limit:
            break
        if processed:
            sleep(PAUSE_SECONDS)
        processed += 1
        try:
            outcome = deliver(conn, item, target_of(item["ticket_ref"]), base_url, api_key, workspace)
        except PlaneUnavailable as exc:
            result.update(stopped="unavailable", unavailable=exc)
            break
        info = {"id": item["id"], "client_id": item["client_id"], "ticket": item["ticket_ref"]}
        if outcome[0] == "sent":
            result["sent"].append({**info, "comment_id": outcome[1], "how": outcome[2]})
        elif outcome[0] == "busy":
            result["busy"] += 1
        elif outcome[1] == 401:
            result["stopped"] = "unauthorized"
            break
        else:
            result["failed"].append({**info, "status": outcome[1], "error": f"HTTP {outcome[1]}: {outcome[2]}" if outcome[1] else outcome[2]})
    return _finish(conn, result)


def _finish(conn, result):
    result["pending"], result["failed_total"] = pending_counts(conn)
    return result
