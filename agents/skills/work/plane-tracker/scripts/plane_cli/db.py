"""Base de datos local SQLite3 (WAL): conexión y esquema.

Expone: get_db(), ensure_columns(), init_snapshot_table(), init_outbox_tables(), init_db().
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
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, sent_at TEXT
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outbox_state ON outbox(state, id);")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_outbox_wl_open
            ON outbox(wl_ticket_id, wl_track, wl_date, wl_start_time) WHERE state IN ('pending','sending','failed');
    """)


def init_db(conn):
    """Inicializa el esquema relacional e índices si no existen."""
    with conn:
        # 1. Tabla de Proyectos
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                identifier TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                workspace TEXT NOT NULL DEFAULT 'teamprogra',
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
        })

        init_snapshot_table(conn)
        init_outbox_tables(conn)

        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS issues_fts USING fts5(
                ticket_id UNINDEXED,
                title,
                labels_csv,
                tokenize = 'unicode61 remove_diacritics 2'
            );
        """)
