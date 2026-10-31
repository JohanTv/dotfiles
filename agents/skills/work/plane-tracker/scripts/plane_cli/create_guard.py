"""Guarda contra tickets duplicados al crear: un reintento tras un POST sin confirmar no debe crear otro igual.

Expone: recent_duplicates(), mark_unconfirmed(), clear_mark(), DUPLICATE_WINDOW_HOURS.
No hace: decidir qué hacer con un duplicado (lo hace el comando) ni impedir crear un ticket del mismo título si se pide.
La comparación es siempre contra la caché local (sin red). Solo cuando una creación anterior del mismo título quedó sin
confirmar se fuerza un refresco de la caché antes de comparar.
"""

import hashlib
import re
import time

import session_clock
from plane_cli.api import PlaneUnavailable
from plane_cli.cache import age_text, sync_issues_cache

DUPLICATE_WINDOW_HOURS = 24


def _norm(title):
    return re.sub(r"\s+", " ", (title or "").strip()).casefold()


def _mark_key(project_id, title):
    return "create_unconfirmed:" + hashlib.sha256(f"{project_id}|{_norm(title)}".encode()).hexdigest()[:20]


def mark_unconfirmed(conn, project_id, title):
    """Marca que se va a enviar la creación de este título; sigue viva mientras no se confirme el resultado."""
    with conn:
        conn.execute("INSERT OR REPLACE INTO sync_metadata (key, value, updated_at) VALUES (?, ?, ?)",
                     (_mark_key(project_id, title), _norm(title), time.time()))


def clear_mark(conn, project_id, title):
    with conn:
        conn.execute("DELETE FROM sync_metadata WHERE key = ?", (_mark_key(project_id, title),))


def _has_open_mark(conn, project_id, title):
    row = conn.execute("SELECT updated_at FROM sync_metadata WHERE key = ?", (_mark_key(project_id, title),)).fetchone()
    return bool(row) and time.time() - row["updated_at"] < DUPLICATE_WINDOW_HOURS * 3600


def recent_duplicates(conn, base_url, api_key, workspace, project_id, project_ident, title):
    """[(ticket_id, antigüedad)] de los tickets del proyecto con el mismo título creados en la ventana de duplicados."""
    unconfirmed = _has_open_mark(conn, project_id, title)
    refreshed = False
    if unconfirmed:
        try:
            sync_issues_cache(conn, base_url, api_key, workspace, project_id, project_ident, force_refresh=True)
            refreshed = True
        except PlaneUnavailable:
            pass
    cutoff = time.time() - DUPLICATE_WINDOW_HOURS * 3600
    wanted, found = _norm(title), []
    for row in conn.execute("SELECT ticket_id, title, created_at FROM issues_cache WHERE project_id = ?", (project_id,)):
        created = session_clock.parse_time(row["created_at"])
        if created and created.timestamp() >= cutoff and _norm(row["title"]) == wanted:
            found.append((row["ticket_id"], age_text(time.time() - created.timestamp())))
    if unconfirmed and refreshed and not found:
        clear_mark(conn, project_id, title)  # la creación anterior no llegó a aplicarse: se puede reintentar
    return found
