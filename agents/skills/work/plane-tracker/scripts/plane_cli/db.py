"""Base de datos local SQLite3 (WAL): conexión y esquema.

Expone: get_db(), ensure_columns(), init_snapshot_table(), init_outbox_tables(), init_people_tables(), init_db().
No hace: consultas de negocio ni acceso a red.
La caché contiene texto de comentarios: el directorio se deja en 0700 y la base en 0600 (los archivos -wal y -shm
heredan los permisos de la base).
"""

import os
import sqlite3

from plane_cli import config


def _restrict_permissions(path, mode):
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def get_db():
    """Retorna una conexión a SQLite3 con WAL mode y timeout defensivo."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    _restrict_permissions(config.CACHE_DIR, 0o700)
    try:
        os.close(os.open(config.db_file(), os.O_RDWR | os.O_CREAT, 0o600))
    except OSError:
        pass
    _restrict_permissions(config.db_file(), 0o600)
    conn = sqlite3.connect(config.db_file(), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def ensure_columns(conn, table, columns):
    """Añade las columnas que falten (ALTER TABLE no admite IF NOT EXISTS)."""
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    for name, decl in columns.items():
        if name in existing:
            continue
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise


def init_snapshot_table(conn):
    """Última lectura completa de cada ticket (get), para consultarla sin conexión."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS issue_snapshots (
            issue_id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL, fetched_at REAL NOT NULL,
            issue_json TEXT NOT NULL, comments_json TEXT, comments_fetched_at REAL
        );
    """)


def init_outbox_tables(conn):
    """Cola de salida de comentarios pendientes de publicar (ver outbox.py)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL DEFAULT 'comment' CHECK (kind IN ('comment')),
            ticket_ref TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            wl_ticket_id TEXT NOT NULL, wl_track TEXT NOT NULL, wl_date TEXT NOT NULL, wl_start_time TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','sending','sent','failed','dropped')),
            attempts INTEGER NOT NULL DEFAULT 0,
            maybe_delivered INTEGER NOT NULL DEFAULT 0 CHECK (maybe_delivered IN (0,1)),
            last_error TEXT, plane_comment_id TEXT, lease_until REAL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, sent_at TEXT,
            target_base_url TEXT, target_workspace TEXT
        );
    """)
    ensure_columns(conn, "outbox", {"target_base_url": "TEXT", "target_workspace": "TEXT"})
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outbox_state ON outbox(state, id);")
    conn.execute("DROP INDEX IF EXISTS idx_outbox_wl_open;")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_outbox_wl_open_ws
            ON outbox(COALESCE(target_workspace, ''), wl_ticket_id, wl_track, wl_date, wl_start_time) WHERE state IN ('pending','sending','failed');
    """)


def init_people_tables(conn):
    """Personas: miembros del workspace, historial de asignación medido (ver assignments.py) y las columnas que registran quién hizo qué."""
    # Quién registró las horas (UUID del autor del comentario). NULL = sin autor registrado (filas anteriores o sin identidad): nunca se supone propio.
    ensure_columns(conn, "worklogs", {"author_id": "TEXT"})
    # Marca de que el historial de asignación de ese ticket ya se trajo (cachés previas solo traían las transiciones de estado).
    ensure_columns(conn, "flow_fetch", {"assignments_fetched": "INTEGER NOT NULL DEFAULT 0"})
    # Personas del workspace (UUID -> nombre) para mostrar asignados sin consultar Plane cada vez.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
    """)
    # Historial de asignación medido (independiente de issues_cache: sobrevive a su resync). Solo lo que se trajo de las actividades.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS assignment_events (
            event_id TEXT PRIMARY KEY,
            issue_id TEXT NOT NULL,
            ticket_id TEXT NOT NULL,
            at_utc TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('added','removed')),
            user_id TEXT NOT NULL,
            user_name TEXT
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assignment_issue ON assignment_events(issue_id, at_utc);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assignment_user ON assignment_events(user_id, kind);")


def init_core_tables(conn):
    """Proyectos, metadatos de sincronización y registros de trabajo (worklogs v2.2) con sus índices."""
    # 1. Tabla de Proyectos
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            identifier TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            workspace TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL
        );
    """)

    # 2. Tabla de Metadatos de Sincronización
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
    """)

    # 3. Tabla Principal de Registros de Trabajo (Worklogs v2.2)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS worklogs (
            ticket_id TEXT NOT NULL,
            track TEXT NOT NULL DEFAULT 'main',
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL CHECK (duration_minutes >= 0),
            plane_comment_id TEXT,
            project_id TEXT NOT NULL,
            issue_name TEXT NOT NULL DEFAULT '',
            worker_type TEXT NOT NULL DEFAULT 'human',
            capacity_bucket TEXT NOT NULL DEFAULT 'deep_work',
            phase TEXT NOT NULL DEFAULT 'construction_dev',
            role TEXT NOT NULL DEFAULT 'backend_engineer',
            notes TEXT NOT NULL DEFAULT '',
            stoppers_json TEXT NOT NULL DEFAULT '[]',
            raw_payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (ticket_id, track, date, start_time)
        );
    """)

    # Índices
    conn.execute("CREATE INDEX IF NOT EXISTS idx_worklogs_date_start ON worklogs(date, start_time);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_worklogs_ticket_track ON worklogs(ticket_id, track);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_worklogs_project_date ON worklogs(project_id, date);")


def init_catalog_tables(conn):
    """Etiquetas y estados por proyecto, con TTL."""
    # 4. Tabla de Etiquetas (Labels) con TTL
    conn.execute("""
        CREATE TABLE IF NOT EXISTS labels (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_labels_project ON labels(project_id);")

    # 5. Tabla de Estados (States) con TTL
    conn.execute("""
        CREATE TABLE IF NOT EXISTS states (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            group_name TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_states_project ON states(project_id);")


def init_issue_tables(conn):
    """Caché de tickets para búsqueda local, historial de transiciones, marcas de foco y las fechas del ciclo de vida."""
    # 6. Tabla de Issues Cache para búsqueda FTS5 en Momento Cero (< 2ms)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS issues_cache (
            id TEXT PRIMARY KEY,
            sequence_id INTEGER NOT NULL,
            ticket_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            state_name TEXT NOT NULL,
            state_group TEXT NOT NULL,
            priority TEXT NOT NULL,
            labels_csv TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_proj ON issues_cache(project_id, state_group);")
    # Historial de transiciones de estado (independiente de issues_cache: sobrevive a su resync)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS state_transitions (
            activity_id TEXT PRIMARY KEY,
            issue_id TEXT NOT NULL,
            ticket_id TEXT NOT NULL,
            at_utc TEXT NOT NULL,
            from_id TEXT,
            to_id TEXT NOT NULL,
            from_name TEXT,
            to_name TEXT
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transitions_issue ON state_transitions(issue_id, at_utc);")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flow_fetch (
            issue_id TEXT PRIMARY KEY,
            fetched_at REAL NOT NULL,
            issue_updated_at TEXT
        );
    """)
    # Marcas de foco: en qué ticket trabaja cada sesión de agente (solo local)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            ticket TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_marks_session ON session_marks(session_id, started_at);")
    # Fechas del ciclo de vida (cachés previas no las tienen): ALTER idempotente y tolerante a concurrencia.
    ensure_columns(conn, "issues_cache", {
        "created_at": "TEXT", "completed_at": "TEXT", "start_date": "TEXT",
        "target_date": "TEXT", "archived_at": "TEXT",
        # Quién tiene el ticket y quién lo creó (lista JSON de UUID y UUID) y cuándo lo tocó Plane (updated_at de Plane, no de la sincronización).
        "assignees_json": "TEXT", "created_by": "TEXT", "plane_updated_at": "TEXT",
    })


def init_sync_state(conn):
    """Estado de la última sincronización de tickets por proyecto (recuento del servidor, recorte, si se sirvió vencido) y acceso a cada proyecto."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS issue_sync (
            project_id TEXT PRIMARY KEY,
            total_count INTEGER,
            fetched INTEGER NOT NULL DEFAULT 0,
            capped INTEGER NOT NULL DEFAULT 0,
            stale INTEGER NOT NULL DEFAULT 0,
            as_of REAL NOT NULL
        );
    """)
    ensure_columns(conn, "projects", {"is_member": "INTEGER NOT NULL DEFAULT 1", "archived": "INTEGER NOT NULL DEFAULT 0"})
    # Marca de sincronización de horas por proyecto y periodo (defecto 0010): `complete` = se leyeron todos los comentarios candidatos; `unmeasured` = comentarios con
    # telemetría sin fecha u hora que no entraron. Procedencia de los campos de cada fila (defecto 0022): lista JSON de los que NO vinieron del comentario.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS worklog_sync (
            project_ident TEXT NOT NULL,
            date_from TEXT NOT NULL,
            date_to TEXT NOT NULL,
            as_of REAL NOT NULL,
            complete INTEGER NOT NULL DEFAULT 0,
            unmeasured INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (project_ident, date_from, date_to)
        );
    """)
    ensure_columns(conn, "worklogs", {"defaulted_json": "TEXT NOT NULL DEFAULT '[]'"})
    # Comentarios ya leídos por ticket (para que una sincronización a medias avance en la siguiente en vez de repetir los más recientes): el ticket no cambió desde entonces.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS worklog_issue_sync (
            issue_id TEXT PRIMARY KEY,
            issue_updated_at TEXT,
            as_of REAL NOT NULL
        );
    """)
    # Marcas de agua de sincronización delta por dominio y proyecto (RFC 0027).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_watermarks (
            domain TEXT NOT NULL,
            project_id TEXT NOT NULL,
            last_sync_timestamp REAL NOT NULL,
            server_high_watermark TEXT,
            status TEXT NOT NULL DEFAULT 'synced',
            items_synced INTEGER NOT NULL DEFAULT 0,
            pages_fetched INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL,
            PRIMARY KEY (domain, project_id)
        );
    """)


def init_search_index(conn):
    """Índice FTS5 de los tickets en caché y triggers automáticos de sincronización (RFC 0027)."""
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS issues_fts USING fts5(
            ticket_id UNINDEXED,
            title,
            labels_csv,
            tokenize = 'unicode61 remove_diacritics 2'
        );
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_issues_cache_ai AFTER INSERT ON issues_cache BEGIN
            INSERT INTO issues_fts (rowid, ticket_id, title, labels_csv) VALUES (new.rowid, new.ticket_id, new.title, new.labels_csv);
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_issues_cache_ad AFTER DELETE ON issues_cache BEGIN
            DELETE FROM issues_fts WHERE rowid = old.rowid;
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_issues_cache_au AFTER UPDATE ON issues_cache BEGIN
            DELETE FROM issues_fts WHERE rowid = old.rowid;
            INSERT INTO issues_fts (rowid, ticket_id, title, labels_csv) VALUES (new.rowid, new.ticket_id, new.title, new.labels_csv);
        END;
    """)


def init_db(conn):
    """Inicializa el esquema relacional e índices si no existen."""
    with conn:
        init_core_tables(conn)
        init_catalog_tables(conn)
        init_issue_tables(conn)
        init_snapshot_table(conn)
        init_outbox_tables(conn)
        init_people_tables(conn)
        init_sync_state(conn)
        init_search_index(conn)
