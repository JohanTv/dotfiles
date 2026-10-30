"""Cola de salida de comentarios: guardado previo (write-ahead), reclamo atómico, entrega idempotente y consultas.

Expone: Draft, Published, Rejected, publish_comment(), deliver(), claim(), release(), mark_sent(), make_client_id(), comments_url(),
search_remote(), discard_item(), owner_of(), open_keys(), count_open(), list_items(), drop_item(), pending_counts(), pending_notice(), fail(), constantes
(LEASE_SECONDS, OPEN_STATES, EXTERNAL_SOURCE...).
No hace: imprimir resultados de negocio ni decidir el orden de un flush (outbox_flush.py).

Solo `comment add` se encola. El comentario y su worklog provisional (fila de `worklogs` sin `plane_comment_id`, con la
misma clave que `wl_*` del item) se guardan antes del POST. Cada comentario lleva un `client_id` determinista dentro de
su bloque oculto y como `external_id`. Un item ambiguo (el POST pudo llegar: `maybe_delivered=1`, o `sending` con el
lease vencido) no se reenvía sin buscar antes ese `client_id` en los comentarios del ticket. Un comentario borrado a mano
en Plane mientras seguía en la cola con `maybe_delivered=1` puede recrearse una vez.
"""

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
from dataclasses import dataclass, field

from plane_cli import config
from plane_cli.api import PlaneUnavailable, api_request, fail_http, http_detail
from plane_cli.worklog import extract_metadata_from_comment, replace_metadata_block, strip_metadata_block, upsert_worklog

EXTERNAL_SOURCE = "plane-tracker"
LEASE_SECONDS = 180
MAX_TEXT_BYTES = 64 * 1024
MAX_OPEN_ITEMS = 200
SEARCH_MAX_PAGES = 10
OPEN_STATES = ("pending", "sending", "failed")
_OPEN_SQL = "state IN ('pending','sending','failed')"
_WL_KEY = "wl_ticket_id = ? AND wl_track = ? AND wl_date = ? AND wl_start_time = ?"
_WORKLOG_KEY = "ticket_id = ? AND track = ? AND date = ? AND start_time = ?"


@dataclass
class Draft:
    """Un comentario listo para publicar. `unavailable` es el PlaneUnavailable que impidió resolver el ticket (issue["id"] es None)."""
    base_url: str
    api_key: str
    workspace: str
    project_id: str
    issue: dict
    ticket_label: str
    html: str
    meta: dict
    entry: dict
    unavailable: object = None


@dataclass
class Published:
    """Resultado de publish_comment: state "sent" (con comment_id) o "queued" (reason = causa)."""
    state: str
    client_id: str
    outbox_id: int = None
    comment_id: str = None
    reason: str = None
    note: str = None
    extra: dict = field(default_factory=dict)


def fail(message, prefix="Error: "):
    sys.stderr.write(f"{prefix}{message}\n")
    sys.exit(1)


def stamp():
    return config.now().isoformat(timespec="seconds")


def make_client_id(ticket_label, track, date, start_time, html):
    """Identificador determinista del comentario: ticket, frente, inicio y texto visible (sin el bloque oculto)."""
    visible = hashlib.sha256(strip_metadata_block(html).strip().encode("utf-8")).hexdigest()
    key = f"{ticket_label}|{track}|{date}|{start_time}|{visible}"
    return "pt-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def comments_url(base_url, workspace, project_id, issue_id):
    return f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue_id}/comments/"


def _wl_params(item):
    return (item["wl_ticket_id"], item["wl_track"], item["wl_date"], item["wl_start_time"])


def claim(conn, item_id):
    """Reclamo atómico: pasa el item a `sending` con lease y devuelve su fila previa; None si otro proceso lo tiene."""
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT * FROM outbox WHERE id = ?", (item_id,)).fetchone()
        now = config.now().timestamp()
        free = row is not None and (row["state"] == "pending" or (row["state"] == "sending" and (row["lease_until"] or 0) < now))
        if free:
            conn.execute("UPDATE outbox SET state = 'sending', attempts = attempts + 1, maybe_delivered = 1, lease_until = ?, updated_at = ? WHERE id = ?",
                         (now + LEASE_SECONDS, stamp(), item_id))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return row if free else None


def _settle(conn, item_id, state, error, maybe):
    with conn:
        conn.execute("UPDATE outbox SET state = ?, last_error = ?, maybe_delivered = ?, lease_until = NULL, updated_at = ? WHERE id = ?",
                     (state, (error or "")[:300] or None, maybe, stamp(), item_id))


def release(conn, item_id, prev, exc):
    """El intento no llegó a una respuesta: el item vuelve a `pending`; conserva la ambigüedad previa y suma la de este intento."""
    maybe = 1 if prev["maybe_delivered"] or exc.delivered == "unknown" else 0
    _settle(conn, item_id, "pending", exc.cause, maybe)


def mark_sent(conn, item, comment_id):
    """Item enviado: enlaza el id del comentario en el item y en la fila provisional de worklogs."""
    with conn:
        conn.execute("UPDATE outbox SET state = 'sent', plane_comment_id = ?, sent_at = ?, updated_at = ?, last_error = NULL, lease_until = NULL WHERE id = ?",
                     (comment_id, stamp(), stamp(), item["id"]))
        if comment_id:
            conn.execute(f"UPDATE worklogs SET plane_comment_id = ? WHERE {_WORKLOG_KEY}", (comment_id, *_wl_params(item)))


def search_remote(url, api_key, client_id):
    """Id del comentario del ticket que lleva este client_id (en su HTML o como external_id); None si no aparece."""
    cursor = None
    for _ in range(SEARCH_MAX_PAGES):
        data = api_request(url + (f"?cursor={urllib.parse.quote(cursor)}" if cursor else ""), api_key, raise_on_error=True)
        for comment in data.get("results", []):
            if comment.get("external_id") == client_id or client_id in (comment.get("comment_html") or ""):
                return comment.get("id")
        cursor = data.get("next_cursor")
        if not data.get("next_page_results") or not cursor:
            break
    return None


def _existing_id(detail):
    try:
        return json.loads(detail).get("id")
    except (ValueError, AttributeError):
        return None


def _post(conn, item, url, api_key):
    """POST del item: ("sent", id, "created"|"exists"); un 409 con id del comentario existente cuenta como enviado."""
    try:
        res = api_request(url, api_key, method="POST", data=json.loads(item["payload_json"]), raise_on_error=True)
    except urllib.error.HTTPError as exc:
        detail = http_detail(exc)
        exc.close()
        existing = _existing_id(detail) if exc.code == 409 else None
        if not existing:
            raise Rejected(exc.code, detail)
        mark_sent(conn, item, existing)
        return ("sent", existing, "exists")
    mark_sent(conn, item, res.get("id"))
    return ("sent", res.get("id"), "created")


class Rejected(Exception):
    """La solicitud o su destino no se pueden atender (error definitivo de Plane o ticket inexistente)."""

    def __init__(self, status, detail):
        super().__init__(status)
        self.status, self.detail = status, detail


def deliver(conn, item, target_of, base_url, api_key, workspace):
    """Reclama el item y lo publica (buscando antes si es ambiguo).

    Devuelve ("sent", comment_id, how) con how en created|exists|found, ("busy",) si otro proceso lo tiene o
    ("rejected", status, detail) tras un error definitivo (el item queda `failed`; con 401 vuelve a `pending`).
    Ante un fallo transitorio el item vuelve a `pending` y se relanza PlaneUnavailable. `target_of()` devuelve
    (project_id, issue_id) y puede lanzar Rejected o PlaneUnavailable.
    """
    prev = claim(conn, item["id"])
    if prev is None:
        return ("busy",)
    ambiguous = bool(prev["maybe_delivered"]) or prev["state"] == "sending"
    try:
        project_id, issue_id = target_of()
        url = comments_url(base_url, workspace, project_id, issue_id)
        found = search_remote(url, api_key, item["client_id"]) if ambiguous else None
        if found:
            mark_sent(conn, item, found)
            return ("sent", found, "found")
        return _post(conn, item, url, api_key)
    except urllib.error.HTTPError as exc:
        status, detail = exc.code, http_detail(exc)
        exc.close()
        return _rejected(conn, item, prev, status, detail)
    except Rejected as exc:
        return _rejected(conn, item, prev, exc.status, exc.detail)
    except PlaneUnavailable as exc:
        release(conn, item["id"], prev, exc)
        raise


def _rejected(conn, item, prev, status, detail):
    if status == 429:
        exc = PlaneUnavailable("http_429", "no")
        release(conn, item["id"], prev, exc)
        raise exc
    _settle(conn, item["id"], "pending" if status == 401 else "failed", f"HTTP {status}: {detail}" if status else detail, prev["maybe_delivered"])
    return ("rejected", status, detail)


def discard_item(conn, item, previous=None):
    """Borra el item y su fila provisional (o restaura la fila de worklogs que existía antes)."""
    with conn:
        conn.execute("DELETE FROM outbox WHERE id = ?", (item["id"],))
        conn.execute(f"DELETE FROM worklogs WHERE {_WORKLOG_KEY} AND plane_comment_id IS NULL", _wl_params(item))
        if previous:
            columns = list(previous)
            conn.execute(f"INSERT OR REPLACE INTO worklogs ({','.join(columns)}) VALUES ({','.join('?' * len(columns))})", [previous[c] for c in columns])


def _enqueue(conn, draft, client_id):
    """Guarda el item `pending` y la fila provisional de worklogs en una sola transacción; devuelve (item, fila previa de worklogs)."""
    entry = draft.entry
    key = (entry["ticket_id"], entry["track"], entry["date"], entry["start_time"])
    payload = json.dumps({"comment_html": draft.html, "external_source": EXTERNAL_SOURCE, "external_id": client_id}, ensure_ascii=False)
    if len(payload.encode("utf-8")) > MAX_TEXT_BYTES:
        fail(f"el comentario supera el máximo de {MAX_TEXT_BYTES // 1024} KB.")
    owner = conn.execute(f"SELECT id FROM outbox WHERE {_WL_KEY} AND {_OPEN_SQL}", key).fetchone()
    if owner:
        fail(f"Ya hay un registro en cola con ese ticket/track/fecha/inicio (#{owner['id']}). Publícalo con 'outbox flush' o descártalo con 'outbox drop {owner['id']}'.", prefix="")
    if conn.execute(f"SELECT COUNT(*) FROM outbox WHERE {_OPEN_SQL}").fetchone()[0] >= MAX_OPEN_ITEMS:
        fail(f"la cola ya tiene {MAX_OPEN_ITEMS} registros abiertos; publícalos con 'outbox flush' antes de añadir más.")
    previous = conn.execute(f"SELECT * FROM worklogs WHERE {_WORKLOG_KEY}", key).fetchone()
    if previous:
        sys.stderr.write("⚠ Ya existía un worklog local con el mismo ticket/track/fecha/inicio: se sobrescribe (el comentario anterior sigue en Plane).\n")
    now = stamp()
    conn.execute("DELETE FROM outbox WHERE client_id = ? AND state = 'dropped'", (client_id,))
    cursor = conn.execute("INSERT INTO outbox (client_id, ticket_ref, payload_json, wl_ticket_id, wl_track, wl_date, wl_start_time, created_at, updated_at) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (client_id, draft.ticket_label, payload, *key, now, now))
    upsert_worklog(conn, entry)  # confirma también el INSERT anterior: ambas filas o ninguna
    return conn.execute("SELECT * FROM outbox WHERE id = ?", (cursor.lastrowid,)).fetchone(), dict(previous) if previous else None


def _queued(item, reason, **kwargs):
    return Published("queued", item["client_id"], outbox_id=item["id"], reason=reason, **kwargs)


def publish_comment(conn, draft):
    """Guarda el comentario y su worklog provisional y lo publica; sin Plane (o con la entrega dudosa) queda en la cola.

    Un error definitivo (p. ej. 400) deshace lo guardado, imprime el error y termina con código 1. Con PLANE_NO_QUEUE=1
    un fallo de disponibilidad deja el PlaneUnavailable sin encolar nada.
    """
    entry, meta = draft.entry, draft.meta
    client_id = meta["client_id"] = make_client_id(entry["ticket_id"], entry["track"], entry["date"], entry["start_time"], draft.html)
    draft.html = replace_metadata_block(draft.html, meta)
    no_queue = os.environ.get("PLANE_NO_QUEUE") == "1"
    existing = conn.execute("SELECT * FROM outbox WHERE client_id = ?", (client_id,)).fetchone()
    if existing and existing["state"] == "sent":
        return Published("sent", client_id, outbox_id=existing["id"], comment_id=existing["plane_comment_id"])
    if no_queue and draft.unavailable is not None:
        raise draft.unavailable
    reused = bool(existing) and existing["state"] != "dropped"
    previous = None
    if reused:
        item = existing
        if item["state"] == "failed":
            _settle(conn, item["id"], "pending", item["last_error"], item["maybe_delivered"])
    else:
        item, previous = _enqueue(conn, draft, client_id)
    if draft.unavailable is not None:
        if not reused:
            _settle(conn, item["id"], "pending", draft.unavailable.cause, 0)
        return _queued(item, draft.unavailable.kind)
    try:
        outcome = deliver(conn, item, lambda: (draft.project_id, draft.issue["id"]), draft.base_url, draft.api_key, draft.workspace)
    except PlaneUnavailable as exc:
        if no_queue and not reused:
            discard_item(conn, item, previous)
            raise
        return _queued(item, exc.kind)
    if outcome[0] == "sent":
        notes = {"exists": "El comentario ya existía en Plane (mismo external_id); no se duplicó.", "found": "El comentario ya estaba publicado en Plane; no se reenvió."}
        return Published("sent", client_id, outbox_id=item["id"], comment_id=outcome[1], note=notes.get(outcome[2]))
    if outcome[0] == "busy":
        return _queued(item, "in_progress")
    if not reused:
        discard_item(conn, item, previous)
    fail_http(comments_url(draft.base_url, draft.workspace, draft.project_id, draft.issue["id"]), outcome[1], outcome[2])


def owner_of(conn, ticket, track, date, start_time):
    """El item abierto (pending, sending o failed) cuya fila provisional de worklogs tiene esta clave; None si no hay."""
    return conn.execute(f"SELECT * FROM outbox WHERE {_WL_KEY} AND {_OPEN_SQL}", (ticket, track, date, start_time)).fetchone()


def open_keys(conn):
    """{(ticket, track, fecha, inicio)} de las filas provisionales de los items abiertos."""
    return {tuple(r) for r in conn.execute(f"SELECT wl_ticket_id, wl_track, wl_date, wl_start_time FROM outbox WHERE {_OPEN_SQL}")}


def count_open(conn, date_from, date_to, project=None, track=None):
    """Items abiertos cuya fecha de worklog cae en el periodo (filtrables por proyecto y track)."""
    query, params = f"SELECT COUNT(*) FROM outbox WHERE {_OPEN_SQL} AND wl_date >= ? AND wl_date <= ?", [date_from, date_to]
    if project:
        query, params = query + " AND wl_ticket_id LIKE ?", params + [f"{project.upper()}-%"]
    if track:
        query, params = query + " AND wl_track = ?", params + [track]
    return conn.execute(query, params).fetchone()[0]


def pending_counts(conn):
    """(pendientes de publicar, fallidos): los pendientes incluyen los que están en envío."""
    row = conn.execute("SELECT SUM(state IN ('pending','sending')), SUM(state = 'failed') FROM outbox").fetchone()
    return row[0] or 0, row[1] or 0


def pending_notice(conn):
    """Aviso de stderr con lo que queda por publicar; None si la cola está vacía."""
    pending, failed = pending_counts(conn)
    if failed:
        return f"⏳ Outbox: {pending} pendiente(s) de publicar, {failed} fallido(s) (revisa: plane-tracker outbox list). Ejecuta: plane-tracker outbox flush"
    return f"⏳ Outbox: {pending} pendiente(s) de publicar. Ejecuta: plane-tracker outbox flush" if pending else None


def _preview(html, width=80):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", strip_metadata_block(html))).strip()[:width]


def list_items(conn, include_all=False):
    """Items abiertos (o todos) en orden de creación, con una vista previa de 80 caracteres; nunca el payload completo."""
    where = "" if include_all else f"WHERE {_OPEN_SQL}"
    items = []
    for row in conn.execute(f"SELECT * FROM outbox {where} ORDER BY id"):
        html = json.loads(row["payload_json"]).get("comment_html", "")
        meta = extract_metadata_from_comment(html) or {}
        items.append({"id": row["id"], "client_id": row["client_id"], "state": row["state"], "ticket": row["ticket_ref"], "track": row["wl_track"],
                      "date": row["wl_date"], "start_time": row["wl_start_time"], "duration_minutes": meta.get("duration_minutes"),
                      "attempts": row["attempts"], "maybe_delivered": bool(row["maybe_delivered"]), "last_error": row["last_error"],
                      "plane_comment_id": row["plane_comment_id"], "created_at": row["created_at"], "preview": _preview(html)})
    return items


def drop_item(conn, item_id, force=False, keep_worklog=False):
    """Descarta un item abierto y borra su fila provisional de worklogs (salvo keep_worklog); termina con código 1 si no procede."""
    item = conn.execute("SELECT * FROM outbox WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        fail(f"no existe el registro #{item_id} en la cola.")
    if item["state"] not in OPEN_STATES:
        fail(f"el registro #{item_id} está en estado {item['state']}; solo se descartan los pendientes, en envío o fallidos.")
    if item["maybe_delivered"] and not force:
        fail(f"el registro #{item_id} pudo haberse enviado. Puede que ya esté publicado en Plane; revisa el ticket {item['ticket_ref']} o descártalo igualmente con --force.")
    with conn:
        conn.execute("UPDATE outbox SET state = 'dropped', lease_until = NULL, updated_at = ? WHERE id = ?", (stamp(), item_id))
        if not keep_worklog:
            conn.execute(f"DELETE FROM worklogs WHERE {_WORKLOG_KEY} AND plane_comment_id IS NULL", _wl_params(item))
    return item
