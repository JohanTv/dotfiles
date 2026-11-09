"""Almacén de solo lectura de los tickets en caché: filas de `issues_cache`, estado de sincronización por proyecto y datos de personas.

Expone: rows(), sync_info(), cached_counts(), worklog_minutes(), unsigned_hours(), ever_assigned(), search_tokens().
No hace: red, escribir en SQLite ni imprimir (la escritura es de cache.py). Devuelve filas sqlite3.Row con el vocabulario de la base.
"""

import re

STOP_WORDS = {"de", "del", "la", "las", "el", "los", "en", "un", "una", "unos", "unas", "por", "para", "con", "y", "o", "a", "al", "que", "se", "es"}


def search_tokens(text):
    """Palabras de búsqueda: sin signos ni palabras vacías."""
    tokens = [re.sub(r"[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]", "", t) for t in text.split()]
    return [t for t in tokens if t and t.lower() not in STOP_WORDS]


def _marks(items):
    return ",".join("?" for _ in items)


def rows(conn, project_ids, text=None):
    """Tickets de los proyectos, sin ordenar. Con texto: los que coinciden en título o etiquetas (FTS con prefijos, o LIKE si FTS no encuentra), con `rank` (menor = más relevante)."""
    ids = list(project_ids)
    if not ids:
        return []
    if not text:
        return conn.execute(f"SELECT *, 0 AS rank FROM issues_cache WHERE project_id IN ({_marks(ids)})", ids).fetchall()
    tokens = search_tokens(text)
    if not tokens:
        return []
    try:
        found = conn.execute(f"SELECT c.*, f.rank AS rank FROM issues_fts f JOIN issues_cache c ON f.ticket_id = c.ticket_id "
                             f"WHERE issues_fts MATCH ? AND c.project_id IN ({_marks(ids)})", [" OR ".join(f'"{t}"*' for t in tokens)] + ids).fetchall()
    except Exception:
        found = []
    if found:
        return found
    like = " OR ".join("title LIKE ?" for _ in tokens[:3])
    return conn.execute(f"SELECT *, 0 AS rank FROM issues_cache WHERE ({like}) AND project_id IN ({_marks(ids)})", [f"%{t}%" for t in tokens[:3]] + ids).fetchall()


def sync_info(conn, project_ids):
    """{project_id: fila de issue_sync} de los proyectos que se sincronizaron alguna vez."""
    ids = list(project_ids)
    if not ids:
        return {}
    return {r["project_id"]: r for r in conn.execute(f"SELECT * FROM issue_sync WHERE project_id IN ({_marks(ids)})", ids)}


def cached_counts(conn, project_ids):
    """{project_id: tickets en caché}."""
    ids = list(project_ids)
    if not ids:
        return {}
    return {r["project_id"]: r["n"] for r in conn.execute(f"SELECT project_id, COUNT(*) AS n FROM issues_cache WHERE project_id IN ({_marks(ids)}) GROUP BY project_id", ids)}


def worklog_minutes(conn, actor):
    """({ticket: minutos míos}, {ticket: minutos sin autor registrado}) de la base local."""
    mine, unsigned = {}, {}
    for r in conn.execute("SELECT ticket_id, author_id, SUM(duration_minutes) AS m FROM worklogs GROUP BY ticket_id, author_id"):
        if r["author_id"] is None:
            unsigned[r["ticket_id"]] = r["m"]
        elif r["author_id"] == actor:
            mine[r["ticket_id"]] = r["m"]
    return mine, unsigned


def unsigned_hours(conn):
    """Registros de horas locales sin autor registrado."""
    return conn.execute("SELECT COUNT(*) FROM worklogs WHERE author_id IS NULL").fetchone()[0]


def ever_assigned(conn, actor):
    """UUID de los tickets en cuyo historial medido el actor fue asignado alguna vez."""
    if not actor:
        return set()
    return {r["issue_id"] for r in conn.execute("SELECT DISTINCT issue_id FROM assignment_events WHERE user_id = ? AND kind = 'added'", (actor,))}


def get_watermark(conn, domain, project_id):
    """Fila de sync_watermarks para el dominio y proyecto o None si nunca se sincronizó (RFC 0027)."""
    row = conn.execute("SELECT * FROM sync_watermarks WHERE domain = ? AND project_id = ?", (domain, project_id)).fetchone()
    return dict(row) if row else None


def set_watermark(conn, domain, project_id, last_sync_timestamp, server_high_watermark, status="synced",
                  items_synced=0, pages_fetched=0, duration_ms=0, updated_at=None):
    """Guarda o actualiza la marca de agua de sincronización delta (RFC 0027)."""
    now = updated_at if updated_at is not None else last_sync_timestamp
    conn.execute("""
        INSERT INTO sync_watermarks (domain, project_id, last_sync_timestamp, server_high_watermark, status,
                                     items_synced, pages_fetched, duration_ms, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(domain, project_id) DO UPDATE SET
            last_sync_timestamp = excluded.last_sync_timestamp,
            server_high_watermark = excluded.server_high_watermark,
            status = excluded.status,
            items_synced = excluded.items_synced,
            pages_fetched = excluded.pages_fetched,
            duration_ms = excluded.duration_ms,
            updated_at = excluded.updated_at
    """, (domain, project_id, last_sync_timestamp, server_high_watermark, status, items_synced, pages_fetched, duration_ms, now))

