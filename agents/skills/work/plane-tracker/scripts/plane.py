#!/usr/bin/env python3
"""
plane.py - CLI Integral y Resiliente para Plane CE v1.2.3 con Persistencia SQLite3 (v2.3).
Soporta:
  - Base de datos local SQLite3 con WAL Mode (Zero-Lock, concurrencia segura para subagentes)
  - Descubrimiento dinámico de proyectos (OMNIFY, OPS, OMNILEADS, CDP) en base de datos
  - Bitácoras dual-layer (humano + metadata oculta v2.2 con soporte de tracks y worker_type)
  - Fusión matemática de intervalos (Klee's Measure) para reportes sin horas duplicadas
  - Transiciones de estado seguras y asignación de prioridades y etiquetas
  - Tolerancia a fallos de red y backoff defensivo ante HTTP 429
  - Salida formateada y soporte `--json` para agentes de IA y dashboards
"""

import sys
import os
import json
import sqlite3
import subprocess
import urllib.request
import urllib.error
import urllib.parse
import re
import time
import argparse
import mimetypes
import uuid
import fcntl
import contextlib
from datetime import datetime, timedelta, date, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import session_clock
import flow_metrics

from plane_cli import config
from plane_cli.config import get_env_or_fail, positive_int

# ------------------------------------------------------------------------------
# Conversor Markdown → HTML (stdlib, sin dependencias externas)
# Soporta el subconjunto que Plane CE/Tiptap renderiza correctamente:
#   ## Headings, **bold**, `code`, ```blocks```, listas -, tablas |, párrafos
# ------------------------------------------------------------------------------

def markdown_to_html(md: str) -> str:
    """
    Convierte Markdown a HTML compatible con Plane CE (Tiptap/ProseMirror).
    Sin dependencias externas — usa solo re y stdlib.
    """
    if not md or not md.strip():
        return "<p></p>"

    # Normalizar saltos de línea
    md = md.replace("\r\n", "\n").replace("\r", "\n")

    lines = md.split("\n")
    html_parts = []
    i = 0

    def escape(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def inline(s):
        """Aplica formato inline: bold, italic, inline-code, links."""
        # Inline code (antes que bold/italic para no procesar su interior)
        s = re.sub(r"`([^`]+)`", lambda m: f"<code>{escape(m.group(1))}</code>", s)
        # Bold+italic ***text***
        s = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", s)
        # Bold **text**
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        # Italic *text* (no afecta ** ya procesado)
        s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
        # Strikethrough ~~text~~
        s = re.sub(r"~~(.+?)~~", r"<s>\1</s>", s)
        # Links [text](url)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    while i < len(lines):
        line = lines[i]

        # Fenced code block ```lang ... ```
        fence_m = re.match(r"^```(\w*)", line)
        if fence_m:
            lang = fence_m.group(1) or ""
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(escape(lines[i]))
                i += 1
            code_body = "\n".join(code_lines)
            lang_attr = f' class="language-{lang}"' if lang else ""
            html_parts.append(f"<pre><code{lang_attr}>{code_body}</code></pre>")
            i += 1
            continue

        # Headings ## / # / ###
        h_m = re.match(r"^(#{1,6})\s+(.*)", line)
        if h_m:
            level = len(h_m.group(1))
            text = inline(escape(h_m.group(2)))
            html_parts.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # Horizontal rule ---
        if re.match(r"^[-*_]{3,}\s*$", line):
            html_parts.append("<hr>")
            i += 1
            continue

        # Unordered list block (lines starting with - or *)
        if re.match(r"^[-*]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i]):
                item_text = inline(escape(re.sub(r"^[-*]\s+", "", lines[i])))
                items.append(f"<li>{item_text}</li>")
                i += 1
            html_parts.append("<ul>" + "".join(items) + "</ul>")
            continue

        # Ordered list block (lines starting with 1. 2. etc)
        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i]):
                item_text = inline(escape(re.sub(r"^\d+\.\s+", "", lines[i])))
                items.append(f"<li>{item_text}</li>")
                i += 1
            html_parts.append("<ol>" + "".join(items) + "</ol>")
            continue

        # Blockquote > text
        if re.match(r"^>\s*", line):
            bq_lines = []
            while i < len(lines) and re.match(r"^>\s*", lines[i]):
                bq_lines.append(inline(escape(re.sub(r"^>\s*", "", lines[i]))))
                i += 1
            html_parts.append("<blockquote><p>" + "<br>".join(bq_lines) + "</p></blockquote>")
            continue

        # Table (lines containing |)
        if "|" in line and i + 1 < len(lines) and re.match(r"^[|\s\-:]+$", lines[i + 1]):
            header_cells = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2  # skip separator line
            rows = []
            while i < len(lines) and "|" in lines[i]:
                row_cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(row_cells)
                i += 1
            th = "".join(f"<th>{inline(escape(c))}</th>" for c in header_cells)
            tbody_rows = "".join(
                "<tr>" + "".join(f"<td>{inline(escape(c))}</td>" for c in row) + "</tr>"
                for row in rows
            )
            html_parts.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tbody_rows}</tbody></table>")
            continue

        # Checkbox list item - [ ] / - [x]
        if re.match(r"^[-*]\s+\[[ xX]\]", line):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+\[[ xX]\]", lines[i]):
                checked = "x" in lines[i][3:5].lower()
                text = inline(escape(re.sub(r"^[-*]\s+\[[ xX]\]\s*", "", lines[i])))
                chk = ' checked=""' if checked else ""
                items.append(f'<li><input type="checkbox"{chk} disabled> {text}</li>')
                i += 1
            html_parts.append('<ul class="task-list">' + "".join(items) + "</ul>")
            continue

        # Empty line → paragraph break (ya manejado por acumulación)
        if not line.strip():
            i += 1
            continue

        # Paragraph: acumular líneas continuas
        para_lines = []
        while i < len(lines) and lines[i].strip() and not re.match(
            r"^(#{1,6}\s|```|[-*]\s|>\s|\d+\.\s+|[|\-*_]{3})", lines[i]
        ):
            para_lines.append(inline(escape(lines[i])))
            i += 1
        if para_lines:
            html_parts.append("<p>" + "<br>".join(para_lines) + "</p>")

    return "\n".join(html_parts) or "<p></p>"


PROJECTS_TTL = 86400  # 24 horas
SYNC_COOLDOWN = 300   # 5 minutos

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# ------------------------------------------------------------------------------
# Conexión y Gestión de Base de Datos SQLite3 (WAL Mode)
# ------------------------------------------------------------------------------

def get_db():
    """Retorna una conexión a SQLite3 con WAL mode y timeout defensivo."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
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

        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS issues_fts USING fts5(
                ticket_id UNINDEXED,
                title,
                labels_csv,
                tokenize = 'unicode61 remove_diacritics 2'
            );
        """)

# ------------------------------------------------------------------------------
# Entorno y Red
# ------------------------------------------------------------------------------


REQUEST_LOG_MAX_BYTES = 1_000_000

def log_request(method, url, status, elapsed_ms, attempt, error=None):
    """JSONL con metadatos de cada llamada (sin cuerpos ni cabeceras) para diagnosticar latencia y caídas."""
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        log_path = config.request_log()
        if os.path.exists(log_path) and os.path.getsize(log_path) > REQUEST_LOG_MAX_BYTES:
            os.replace(log_path, log_path + ".1")
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "method": method,
                  "path": urllib.parse.urlparse(url).path, "status": status, "ms": int(elapsed_ms),
                  "attempt": attempt, "error": error}
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass

def api_request(url, api_key, method="GET", data=None, timeout=10, max_retries=3, raise_on_error=False):
    """Ejecuta peticiones HTTP a la API de Plane con tolerancia a 429 (Rate Limit) y registro de latencia."""
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                log_request(method, url, resp.status, (time.monotonic() - started) * 1000, attempt + 1)
                if resp.status == 204:
                    return {}
                content = resp.read().decode("utf-8")
                return json.loads(content) if content else {}
        except urllib.error.HTTPError as e:
            log_request(method, url, e.code, (time.monotonic() - started) * 1000, attempt + 1)
            if e.code == 429 and attempt < max_retries - 1:
                retry_after = int(e.headers.get("Retry-After", 1))
                time.sleep(retry_after + 0.5)
                continue
            if raise_on_error:
                raise e
            err_msg = e.read().decode("utf-8")
            sys.stderr.write(f"Error HTTP {e.code} en {url}: {err_msg}\n")
            sys.exit(1)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            reason = str(getattr(e, "reason", e))[:80]
            log_request(method, url, None, (time.monotonic() - started) * 1000, attempt + 1, error=f"{type(e).__name__}: {reason}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            if raise_on_error:
                raise e
            sys.stderr.write(f"Error de red/conexión con Plane ({url}): {e}\n")
            sys.exit(1)

# ------------------------------------------------------------------------------
# Gestión de Proyectos con Caché en SQLite3
# ------------------------------------------------------------------------------

def get_projects_map(conn, base_url, api_key, workspace, force_refresh=False):
    """Obtiene el mapa de identifier -> UUID de proyectos desde SQLite o Plane API."""
    now = time.time()
    if not force_refresh:
        rows = conn.execute("SELECT identifier, project_id, name, updated_at FROM projects WHERE workspace = ?", (workspace,)).fetchall()
        if rows and all((now - r["updated_at"]) < PROJECTS_TTL for r in rows):
            return {r["identifier"]: {"id": r["project_id"], "name": r["name"], "identifier": r["identifier"]} for r in rows}

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/"
    data = api_request(url, api_key)
    projects_map = {}
    with conn:
        for proj in data.get("results", []):
            ident = proj.get("identifier", "").upper()
            if ident:
                p_id = proj["id"]
                p_name = proj["name"]
                projects_map[ident] = {"id": p_id, "name": p_name, "identifier": ident}
                conn.execute("""
                    INSERT INTO projects (identifier, project_id, name, workspace, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(identifier) DO UPDATE SET
                        project_id = excluded.project_id,
                        name = excluded.name,
                        workspace = excluded.workspace,
                        updated_at = excluded.updated_at;
                """, (ident, p_id, p_name, workspace, now))

    return projects_map

def get_project_identifier(conn, base_url, api_key, workspace, project_id):
    """Devuelve el identifier humano (ej. 'OPS') a partir del UUID de un proyecto."""
    if not project_id:
        return None

    row = conn.execute(
        "SELECT identifier FROM projects WHERE project_id = ? AND workspace = ?",
        (project_id, workspace)
    ).fetchone()
    if row and row["identifier"]:
        return row["identifier"].upper()

    # Fallback: cualquier caché local del UUID, aunque sea de otro workspace conocido
    row = conn.execute(
        "SELECT identifier FROM projects WHERE project_id = ?",
        (project_id,)
    ).fetchone()
    if row and row["identifier"]:
        return row["identifier"].upper()

    # Último recurso: refrescar desde la API (mejor esfuerzo, nunca aborta el comando)
    try:
        projects_map = get_projects_map(conn, base_url, api_key, workspace, force_refresh=True)
    except SystemExit:
        return None
    except Exception:
        return None
    for ident, proj in projects_map.items():
        if proj["id"] == project_id:
            return ident.upper()
    return None

def detect_ticket_from_git():
    """Intenta inferir el identificador de ticket desde la rama actual de git."""
    try:
        cmd = ["git", "branch", "--show-current"]
        branch = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        if not branch:
            cmd = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
            branch = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        match = re.search(r"([A-Za-z0-9_]+-\d+)", branch)
        if match:
            return match.group(1).upper()
    except Exception:
        pass
    return None

def resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, issue_ref=None):
    """
    Deduce el proyecto y número de secuencia a partir del issue_ref o rama de Git.
    Soporta: 'OMNIFY-162', 'OPS-44', '162', UUID o None/@ (autodetección de Git).
    """
    if not issue_ref or issue_ref in ("@", ".", "current", "--current", "this"):
        git_ticket = detect_ticket_from_git()
        if git_ticket:
            sys.stderr.write(f"ℹ Ticket auto-detectado desde la rama actual de Git: {git_ticket}\n")
            issue_ref = git_ticket
        else:
            sys.stderr.write("Error: No se especificó ticket y no se detectó identificador en la rama actual de Git.\n")
            sys.stderr.write("Usa: 'plane-tracker comment OMNIFY-162' o cámbiate a una rama como 'feature/OMNIFY-162'.\n")
            sys.exit(1)

    if re.match(r"^[0-9a-fA-F-]{36}$", issue_ref):
        return default_project_id, None, issue_ref, issue_ref

    match = re.match(r"^([A-Za-z0-9_]+)-(\d+)$", issue_ref.strip())
    if match:
        prefix = match.group(1).upper()
        seq_id = int(match.group(2))
        projects_map = get_projects_map(conn, base_url, api_key, workspace)
        if prefix in projects_map:
            return projects_map[prefix]["id"], seq_id, None, f"{prefix}-{seq_id}"

        projects_map = get_projects_map(conn, base_url, api_key, workspace, force_refresh=True)
        if prefix in projects_map:
            return projects_map[prefix]["id"], seq_id, None, f"{prefix}-{seq_id}"

        sys.stderr.write(f"Error: Prefijo de proyecto '{prefix}' no encontrado en el workspace '{workspace}'.\n")
        sys.stderr.write(f"Proyectos disponibles: {', '.join(projects_map.keys())}\n")
        sys.exit(1)

    if re.match(r"^\d+$", issue_ref.strip()):
        return default_project_id, int(issue_ref.strip()), None, f"OMNIFY-{issue_ref.strip()}"

    sys.stderr.write(f"Error: Formato de ticket no reconocido: '{issue_ref}'. Usa 'OMNIFY-162', 'OPS-44' o solo '162'.\n")
    sys.exit(1)

def resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref=None):
    """Resuelve un ticket con paginación robusta."""
    if uuid_ref:
        url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{uuid_ref}/"
        return api_request(url, api_key)

    cursor = None
    while True:
        url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/"
        if cursor:
            url += f"?cursor={urllib.parse.quote(cursor)}"

        data = api_request(url, api_key)
        for iss in data.get("results", []):
            if iss.get("sequence_id") == seq_id:
                return iss

        if not data.get("next_page_results") or not data.get("next_cursor"):
            break
        cursor = data.get("next_cursor")

    sys.stderr.write(f"Error: Ticket #{seq_id} no encontrado en el proyecto.\n")
    sys.exit(1)

def get_states_map(conn, base_url, api_key, workspace, project_id, force_refresh=False):
    """Mapea nombres y slugs de estados a su UUID usando caché SQLite3 con TTL."""
    now = time.time()
    if conn and not force_refresh:
        rows = conn.execute("SELECT id, name, slug, group_name, is_default, updated_at FROM states WHERE project_id = ?", (project_id,)).fetchall()
        if rows and all((now - r["updated_at"]) < PROJECTS_TTL for r in rows):
            mapping = {}
            for r in rows:
                name_clean = r["name"].lower().strip()
                slug_clean = r["slug"].lower().strip()
                mapping[name_clean] = r["id"]
                mapping[slug_clean] = r["id"]
                norm = name_clean.replace("ó", "o").replace("é", "e").replace("á", "a").replace("í", "i").replace("ú", "u")
                mapping[norm] = r["id"]
            return mapping

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/states/"
    data = api_request(url, api_key)
    mapping = {}
    if conn:
        with conn:
            for st in data.get("results", []):
                s_id = st["id"]
                s_name = st["name"]
                s_slug = st["slug"]
                s_group = st.get("group", "")
                s_def = 1 if st.get("default") else 0
                conn.execute("""
                    INSERT INTO states (id, project_id, name, slug, group_name, is_default, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        slug = excluded.slug,
                        group_name = excluded.group_name,
                        is_default = excluded.is_default,
                        updated_at = excluded.updated_at;
                """, (s_id, project_id, s_name, s_slug, s_group, s_def, now))

    for st in data.get("results", []):
        name_clean = st["name"].lower().strip()
        slug_clean = st["slug"].lower().strip()
        mapping[name_clean] = st["id"]
        mapping[slug_clean] = st["id"]
        norm = name_clean.replace("ó", "o").replace("é", "e").replace("á", "a").replace("í", "i").replace("ú", "u")
        mapping[norm] = st["id"]
    return mapping

def get_labels_map(conn, base_url, api_key, workspace, project_id, force_refresh=False):
    """Mapea nombres de etiquetas a su UUID con paginación y caché SQLite3 con TTL."""
    now = time.time()
    if conn and not force_refresh:
        rows = conn.execute("SELECT id, name, color, updated_at FROM labels WHERE project_id = ?", (project_id,)).fetchall()
        if rows and all((now - r["updated_at"]) < PROJECTS_TTL for r in rows):
            return {r["name"].lower().strip(): r["id"] for r in rows}

    mapping = {}
    cursor = None
    all_labels = []
    while True:
        url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/labels/"
        if cursor:
            url += f"?cursor={urllib.parse.quote(cursor)}"

        data = api_request(url, api_key)
        for lb in data.get("results", []):
            mapping[lb["name"].lower().strip()] = lb["id"]
            all_labels.append(lb)

        if not data.get("next_page_results") or not data.get("next_cursor"):
            break
        cursor = data.get("next_cursor")

    if conn and all_labels:
        with conn:
            for lb in all_labels:
                conn.execute("""
                    INSERT INTO labels (id, project_id, name, color, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        color = excluded.color,
                        updated_at = excluded.updated_at;
                """, (lb["id"], project_id, lb["name"], lb.get("color", ""), now))

    return mapping

# ------------------------------------------------------------------------------
# Telemetría y Metadata (v2.2)
# ------------------------------------------------------------------------------

def extract_metadata_from_comment(comment_html):
    """Extrae metadata telemétrica oculta (<!-- PLANE_WORKLOG_METADATA ... -->) o deduce de tabla."""
    if not comment_html:
        return None

    # 1. Bloque JSON telemétrico oficial v2.1 / v2.2
    meta_match = re.search(r"<!--\s*PLANE_WORKLOG_METADATA\s*([\s\S]*?)\s*-->", comment_html)
    if meta_match:
        try:
            data = json.loads(meta_match.group(1).strip())
            if "date" in data and ("start_time" in data or "notes" in data):
                return data
        except Exception:
            pass

    # 2. Inferencia desde tabla markdown
    date_match = re.search(r"\*\*Fecha\*\*\s*\|\s*(\d{4}-\d{2}-\d{2})", comment_html)
    session_match = re.search(r"\*\*Sesión\*\*\s*\|\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", comment_html)
    notes_match = re.search(r"\*\*(?:Resumen|Notas|Detalle)\*\*\s*\|\s*([^|\n<]+)", comment_html)
    bucket_match = re.search(r"\*\*Capacidad\*\*\s*\|\s*`?([a-z_]+)`?", comment_html)
    track_match = re.search(r"\*\*Track\*\*\s*\|\s*`?([a-zA-Z0-9_-]+)`?", comment_html)

    if session_match:
        s_time = session_match.group(1)
        e_time = session_match.group(2)
        try:
            t1 = datetime.strptime(s_time, "%H:%M")
            t2 = datetime.strptime(e_time, "%H:%M")
            dur = int((t2 - t1).total_seconds() / 60)
            if dur < 0:
                dur += 24 * 60
        except Exception:
            dur = 60

        d_str = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")
        notes_str = notes_match.group(1).strip() if notes_match else ""
        bucket_str = bucket_match.group(1).strip() if bucket_match else "deep_work"
        track_str = track_match.group(1).strip() if track_match else "main"

        return {
            "schema_version": "2.2",
            "date": d_str,
            "start_time": s_time,
            "end_time": e_time,
            "duration_minutes": dur,
            "track": track_str,
            "worker_type": "human",
            "capacity_bucket": bucket_str,
            "notes": notes_str,
            "stoppers": [],
            "phase": "dev"
        }

    return None

def upsert_worklog(conn, entry):
    """Inserta o actualiza un registro de trabajo en SQLite3 de forma idempotente."""
    now = time.time()
    t_id = entry.get("ticket_id", "GENERAL")
    track = entry.get("track", "main")
    d_str = entry.get("date", datetime.now().strftime("%Y-%m-%d"))
    s_time = entry.get("start_time", "09:00")
    e_time = entry.get("end_time", "10:00")
    dur = entry.get("duration_minutes", 60)
    p_id = t_id.split("-")[0] if "-" in t_id else "GENERAL"
    i_name = entry.get("issue_name", "")
    w_type = entry.get("worker_type", "human")
    bucket = entry.get("capacity_bucket", "deep_work")
    phase = entry.get("phase", "dev")
    role = entry.get("role", "backend_engineer")
    notes = entry.get("notes", "")
    stoppers = json.dumps(entry.get("stoppers", []), ensure_ascii=False)
    comment_id = entry.get("plane_comment_id") or entry.get("id")
    raw_payload = json.dumps(entry.get("raw_payload", entry), ensure_ascii=False)
    created_at = entry.get("created_at", datetime.now().isoformat())

    with conn:
        conn.execute("""
            INSERT INTO worklogs (
                ticket_id, track, date, start_time, end_time, duration_minutes,
                plane_comment_id, project_id, issue_name, worker_type,
                capacity_bucket, phase, role, notes, stoppers_json, raw_payload,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticket_id, track, date, start_time) DO UPDATE SET
                end_time = excluded.end_time,
                duration_minutes = excluded.duration_minutes,
                plane_comment_id = COALESCE(excluded.plane_comment_id, worklogs.plane_comment_id),
                issue_name = CASE WHEN excluded.issue_name != '' THEN excluded.issue_name ELSE worklogs.issue_name END,
                worker_type = excluded.worker_type,
                capacity_bucket = excluded.capacity_bucket,
                phase = excluded.phase,
                role = excluded.role,
                notes = excluded.notes,
                stoppers_json = excluded.stoppers_json,
                raw_payload = excluded.raw_payload,
                updated_at = excluded.updated_at;
        """, (
            t_id, track, d_str, s_time, e_time, dur,
            comment_id, p_id, i_name, w_type,
            bucket, phase, role, notes, stoppers, raw_payload,
            created_at, now
        ))

# ------------------------------------------------------------------------------
# Sincronización Remota con Plane API
# ------------------------------------------------------------------------------

def get_actor_uuid(base_url, api_key, workspace):
    """
    UUID del usuario activo en Plane, usado para filtrar el sync y no imputar
    al reporte los comentarios de compañeros en tickets compartidos.

    Fuentes: PLANE_ACTOR_UUID (UUID directo) o PLANE_USERNAME (display_name / email).
    Si no está configurado, devuelve None y el sync queda sin filtro (con advertencia).
    """
    explicit = os.environ.get("PLANE_ACTOR_UUID")
    if explicit:
        return explicit.strip()

    username = os.environ.get("PLANE_USERNAME", "").strip().lower()
    if not username:
        return None

    members = api_request(f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/members/", api_key)
    members = members if isinstance(members, list) else members.get("results", [])
    for r in members:
        candidates = {
            str(r.get("display_name") or "").strip().lower(),
            str(r.get("email") or "").strip().lower(),
            str(r.get("first_name") or "").strip().lower(),
        }
        if username in candidates:
            return r.get("id")

    sys.stderr.write(f"⚠ PLANE_USERNAME='{username}' no coincide con ningún miembro del workspace.\n")
    return None

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

# ------------------------------------------------------------------------------
# Algoritmo de Fusión de Intervalos de Klee (Interval Merging)
# ------------------------------------------------------------------------------

def time_to_minutes(t_str):
    try:
        h, m = map(int, t_str.split(":"))
        return h * 60 + m
    except Exception:
        return 0

def minutes_to_time(m):
    h = (m // 60) % 24
    mins = m % 60
    return f"{h:02d}:{mins:02d}"

def calculate_klee_union_minutes(intervals):
    """Calcula la longitud de la unión de intervalos sin duplicar solapamientos (Medida de Lebesgue en 1D)."""
    if not intervals:
        return 0
    sorted_int = sorted(intervals, key=lambda x: x[0])
    union_mins = 0
    cur_start, cur_end = sorted_int[0]

    for s, e in sorted_int[1:]:
        if s <= cur_end:
            cur_end = max(cur_end, e)
        else:
            union_mins += (cur_end - cur_start)
            cur_start, cur_end = s, e
    union_mins += (cur_end - cur_start)
    return union_mins

def expand_segments(rows):
    """Un worklog con segmentos (actividad intercalada entre tickets) se reporta como un bloque por segmento."""
    out = []
    for row in rows:
        entry = dict(row)
        try:
            segments = json.loads(entry.get("raw_payload") or "{}").get("segments")
        except ValueError:
            segments = None
        if not segments:
            out.append(entry)
            continue
        for idx, seg in enumerate(segments):
            part = dict(entry, start_time=seg["start"], end_time=seg["end"], duration_minutes=seg["minutes"])
            if idx:
                part["notes"] = "(continuación)"
            out.append(part)
    return out

def merge_daily_worklogs(rows):
    """
    Agrupa y fusiona registros para el formato ejecutivo:
    titulo / inicio / fin / notas
    
    1. Registros del mismo ticket con solapamiento temporal se unifican en un único bloque continuo.
    2. Registros de distintos tickets preservan su horario real.
    3. El total día se calcula mediante la unión de Lebesgue (Klee's Measure) para tiempo reloj real.
    """
    if not rows:
        return [], 0, 0

    tickets_map = {}
    for r in rows:
        tid = r["ticket_id"]
        tickets_map.setdefault(tid, []).append(r)

    consolidated = []
    all_raw_intervals = []
    total_compute_minutes = 0

    for tid, t_entries in tickets_map.items():
        sorted_t = sorted(t_entries, key=lambda x: time_to_minutes(x["start_time"]))
        merged_blocks = []

        for e in sorted_t:
            s_m = time_to_minutes(e["start_time"])
            e_m = time_to_minutes(e["end_time"])
            dur = e["duration_minutes"]
            total_compute_minutes += dur
            all_raw_intervals.append((s_m, e_m))

            track_name = e["track"]
            worker = e["worker_type"]
            actor_tag = " [Subagente]" if "subagent" in worker.lower() else ""
            track_tag = f"Track: {track_name}" if track_name != "main" else "General"
            note_content = f"[{track_tag}{actor_tag} ({e['start_time']}-{e['end_time']})]: {e['notes']}"

            try:
                stoppers_list = json.loads(e["stoppers_json"])
            except Exception:
                stoppers_list = []

            if not merged_blocks:
                merged_blocks.append({
                    "ticket_id": tid,
                    "issue_name": e["issue_name"],
                    "start_min": s_m,
                    "end_min": e_m,
                    "active_mins": dur,
                    "notes_list": [note_content],
                    "stoppers": stoppers_list,
                    "workers": {worker}
                })
            else:
                last = merged_blocks[-1]
                # Solapamiento o contigüidad (<= 5 min)
                if s_m <= last["end_min"] + 5:
                    last["end_min"] = max(last["end_min"], e_m)
                    last["active_mins"] += dur
                    last["notes_list"].append(note_content)
                    last["stoppers"].extend(stoppers_list)
                    last["workers"].add(worker)
                else:
                    merged_blocks.append({
                        "ticket_id": tid,
                        "issue_name": e["issue_name"],
                        "start_min": s_m,
                        "end_min": e_m,
                        "active_mins": dur,
                        "notes_list": [note_content],
                        "stoppers": stoppers_list,
                        "workers": {worker}
                    })

        for b in merged_blocks:
            wall_m = b["end_min"] - b["start_min"]
            leverage = round(b["active_mins"] / wall_m, 2) if wall_m > 0 else 1.0
            combined_notes = " | ".join(b["notes_list"])
            if len(b["notes_list"]) > 1 or leverage > 1.0:
                combined_notes += f" (Consolidado: {b['active_mins']}m esfuerzo en {wall_m}m reloj | AI Leverage: {leverage}x)"

            consolidated.append({
                "ticket_id": b["ticket_id"],
                "issue_name": b["issue_name"],
                "start_time": minutes_to_time(b["start_min"]),
                "end_time": minutes_to_time(b["end_min"]),
                "start_min": b["start_min"],
                "wall_minutes": wall_m,
                "active_minutes": b["active_mins"],
                "notes": combined_notes,
                "stoppers": list(set(b["stoppers"])),
                "workers": list(b["workers"])
            })

    consolidated.sort(key=lambda x: x["start_min"])
    day_wall_clock_minutes = calculate_klee_union_minutes(all_raw_intervals)

    return consolidated, day_wall_clock_minutes, total_compute_minutes


# ------------------------------------------------------------------------------
# Propuesta de duración medida (nunca se registra sola)
#   - Se mide con "tramos de actividad" de la sesión del agente (solo timestamps).
#   - Lo ya registrado y lo reservado por otras propuestas pendientes se RESTA: nada se cuenta dos veces,
#     sin importar el orden en que se acepten.
#   - Con marcas `focus`, cada ticket recibe solo el tiempo de sus propios intervalos.
# ------------------------------------------------------------------------------

PROPOSAL_TTL_SECONDS = 30 * 60
# Reuniones y soporte no dejan huella en un transcript: ahí siempre se pregunta.
NO_PROPOSAL_BUCKETS = ("toil_support", "coordination")
MAX_PROPOSAL_WARN_MINUTES = 8 * 60
FOCUS_KEEP_DAYS = 3


def _hhmm_utc(day, hhmm):
    return datetime.strptime(f"{day} {hhmm}", "%Y-%m-%d %H:%M").astimezone(timezone.utc)

@contextlib.contextmanager
def proposal_store():
    """last_proposal.json con lectura-modificación-escritura atómica y exclusión entre procesos."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    proposal_path = config.proposal_file()
    with open(proposal_path + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(proposal_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            data = {}
        if not isinstance(data.get("proposals"), dict) or not isinstance(data.get("groups"), dict):
            data = {"proposals": {}, "groups": {}}
        cutoff = time.time() - PROPOSAL_TTL_SECONDS
        data["proposals"] = {k: v for k, v in data["proposals"].items() if v.get("ts", 0) > cutoff}
        data["groups"] = {k: v for k, v in data["groups"].items() if v.get("ts", 0) > cutoff}
        yield data
        tmp = proposal_path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(tmp, proposal_path)

def _entry_key(ticket, session_id):
    return f"{ticket}|{session_id}"

def _drop_ticket(data, tickets, session_id):
    """Quita las propuestas pendientes de esos tickets SOLO en esa sesión (otras sesiones no se tocan)."""
    for t in tickets:
        data["proposals"].pop(_entry_key(t, session_id), None)
    for gid in list(data["groups"]):
        group = data["groups"][gid]
        if group.get("session") != session_id:
            continue
        for t in tickets:
            group["parts"].pop(t, None)
        if not group["parts"]:
            del data["groups"][gid]

def save_proposal(ticket, proposal):
    with proposal_store() as data:
        _drop_ticket(data, [ticket], proposal["session_id"])
        data["proposals"][_entry_key(ticket, proposal["session_id"])] = {"ts": time.time(), "ticket": ticket, "proposal": proposal}

def save_group(group_id, parts):
    """parts: {ticket: propuesta} de una misma sesión; reemplaza lo pendiente de esos tickets en ella."""
    session_id = next(iter(parts.values()))["session_id"]
    with proposal_store() as data:
        _drop_ticket(data, list(parts), session_id)
        data["groups"][group_id] = {"ts": time.time(), "session": session_id, "parts": parts}

def load_recent_proposal(ticket, session_id=None):
    """La propuesta vigente del ticket (suelta o parte de un reparto) de esa sesión, la más reciente.

    Sin `session_id` solo se devuelve si hay una única sesión con propuesta para el ticket: con varias
    terminales abiertas no se adivina cuál es la tuya.
    """
    with proposal_store() as data:
        found = []
        for entry in data["proposals"].values():
            if entry.get("ticket") == ticket:
                found.append((entry["ts"], entry["proposal"]))
        for group in data["groups"].values():
            if ticket in group["parts"]:
                found.append((group["ts"], group["parts"][ticket]))
    if session_id:
        found = [f for f in found if f[1].get("session_id") == session_id]
    elif len({f[1].get("session_id") for f in found}) > 1:
        return None
    return max(found, key=lambda x: x[0])[1] if found else None

def consume_proposal(ticket, session_id):
    """Una propuesta aceptada no puede volver a usarse (evita registrar dos veces lo mismo)."""
    with proposal_store() as data:
        _drop_ticket(data, [ticket], session_id)

def current_session_id(args, worker_type):
    """Id de la sesión de ESTA terminal (env var, --session o directorio sin ambigüedad), o None."""
    agent = getattr(args, "agent", None) or session_clock.agent_from_worker_type(worker_type) or session_clock.detect_agent()
    if not agent:
        return None
    return session_clock.resolve_session(agent, os.getcwd(), getattr(args, "session", None))[0]

def _proposal_runs(proposal):
    return [(session_clock.parse_time(seg["start_utc"]), session_clock.parse_time(seg["end_utc"])) for seg in proposal.get("segments", [])]

def reserved_runs(session_id, exclude_tickets):
    """Intervalos de propuestas pendientes de ESTA sesión para otros tickets (se reservan hasta aceptarse o caducar)."""
    out = []
    with proposal_store() as data:
        pending = [(e["ticket"], e["proposal"]) for e in data["proposals"].values()]
        for group in data["groups"].values():
            pending += list(group["parts"].items())
    for ticket, proposal in pending:
        if ticket not in exclude_tickets and proposal.get("session_id") == session_id:
            out += _proposal_runs(proposal)
    return out

def session_coverage(conn, session_id, today):
    """Intervalos de hoy ya registrados como worklog de esta sesión (propuestos o declarados)."""
    out = []
    rows = conn.execute("SELECT start_time, end_time, raw_payload FROM worklogs WHERE date = ? AND raw_payload LIKE ?", (today, f"%{session_id}%")).fetchall()
    for row in rows:
        try:
            meta = json.loads(row["raw_payload"])
        except ValueError:
            continue
        if (meta.get("measured_by") or {}).get("session") != session_id:
            continue
        try:
            if meta.get("segments"):
                for seg in meta["segments"]:
                    start = session_clock.parse_time(seg.get("start_utc")) or _hhmm_utc(today, seg["start"])
                    end = session_clock.parse_time(seg.get("end_utc")) or _hhmm_utc(today, seg["end"])
                    out.append((start, end))
            else:
                out.append((_hhmm_utc(today, row["start_time"]), _hhmm_utc(today, row["end_time"])))
        except (KeyError, ValueError):
            continue
    return out

def focus_intervals(conn, session_id, day_start, now):
    """{ticket: [(inicio, fin)]} de las marcas de foco de la sesión recortadas a [day_start, now]."""
    out = {}
    rows = conn.execute("SELECT ticket, started_at, ended_at FROM session_marks WHERE session_id = ? ORDER BY started_at", (session_id,)).fetchall()
    for row in rows:
        start = max(session_clock.parse_time(row["started_at"]), day_start)
        end = min(session_clock.parse_time(row["ended_at"]) if row["ended_at"] else now, now)
        if end > start:
            out.setdefault(row["ticket"], []).append((start, end))
    return out

def _parse_clock(text, day_start):
    """'HH:MM' (hora local del día pedido) o ISO-8601 -> datetime UTC."""
    text = text.strip()
    if re.match(r"^\d{1,2}:\d{2}$", text):
        hour, minute = (int(x) for x in text.split(":"))
        return day_start.astimezone().replace(hour=hour, minute=minute, second=0, microsecond=0).astimezone(timezone.utc)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"Hora inválida '{text}': usa HH:MM o ISO-8601.")
    return (parsed.astimezone() if parsed.tzinfo is None else parsed).astimezone(timezone.utc)

def _resolve_window(args, now):
    """Día medido (hoy o --date) y ventana dentro de él: el día completo (hasta ahora si es hoy) o --since/--until."""
    date_arg = getattr(args, "date", None)
    if date_arg:
        try:
            day = datetime.strptime(date_arg, "%Y-%m-%d")
        except ValueError:
            raise ValueError("--date debe tener el formato YYYY-MM-DD.")
        day_start = day.astimezone(timezone.utc)
        day_str = date_arg
    else:
        day_start = config.local_midnight_utc(now)
        day_str = now.astimezone().strftime("%Y-%m-%d")
    if day_start > now:
        raise ValueError("--date no puede ser una fecha futura.")
    day_end = min((day_start.astimezone() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc), now)
    start, end, notes, override = day_start, day_end, [], None
    since, until = getattr(args, "since", None), getattr(args, "until", None)
    if since or until:
        if since:
            start = _parse_clock(since, day_start)
        if until:
            end = _parse_clock(until, day_start)
        if end > day_end:
            end = day_end
            notes.append("--until quedaba fuera del día o en el futuro: se recorta.")
        if start < day_start or end < day_start:
            raise ValueError("La ventana debe estar dentro de un único día (cruzaría la medianoche): registra cada día por separado.")
        if start >= end:
            raise ValueError("--since debe ser anterior a --until.")
        override = {"since": start.isoformat(), "until": end.isoformat()}
    return {"day": day_str, "day_start": day_start, "day_end": day_end, "start": start, "end": end, "notes": notes, "override": override}

def _runs_to_segments(runs, minutes):
    """Segmentos para guardar en el worklog: minutos enteros que suman exactamente `minutes`."""
    weights = [max((e - s).total_seconds(), 1.0) for s, e in runs]
    shares = session_clock.largest_remainder(minutes, weights)
    segs = []
    for (start, end), share in zip(runs, shares):
        if share < 1:
            continue
        segs.append({"start": start.astimezone().strftime("%H:%M"), "end": end.astimezone().strftime("%H:%M"), "minutes": share,
                     "start_utc": start.isoformat(), "end_utc": end.isoformat()})
    return segs

def _proposal_from_runs(ctx, runs, extras):
    minutes = int(round(session_clock.total_minutes(runs)))
    segs = _runs_to_segments(runs, minutes)
    first, last = runs[0][0].astimezone(), runs[-1][1].astimezone()
    gross = (runs[-1][1] - runs[0][0]).total_seconds() / 60.0
    warnings = list(extras.get("notes", []))
    if minutes > MAX_PROPOSAL_WARN_MINUTES:
        warnings.append(f"La propuesta supera {MAX_PROPOSAL_WARN_MINUTES // 60} h: revisa si la sesión cubre varios tickets.")
    if len(runs) > 1:
        warnings.append(f"Hay {len(runs) - 1} pausa(s) de más de 10 min descontadas (pueden ser lectura humana, no inactividad).")
    if ctx["agent"] == "agy":
        warnings.append("agy solo expone hitos de la conversación: la medición es aproximada.")
    if extras.get("excluded", 0) >= 1:
        warnings.append(f"Se excluyeron {extras['excluded']:.0f} min ya registrados o reservados para esta sesión.")
    if extras.get("unattributed", 0) >= 1:
        warnings.append(f"{extras['unattributed']:.0f} min de la sesión no tienen foco asignado (no se reparten solos).")
    return {
        "ok": True, "agent": ctx["agent"], "session_id": ctx["session_id"], "origin": ctx["origin"],
        "confidence": session_clock.CONFIDENCE[ctx["agent"]], "attribution": extras["attribution"],
        "minutes": minutes, "net_minutes": round(session_clock.total_minutes(runs), 1), "gross_minutes": round(gross, 1),
        "pauses": max(len(runs) - 1, 0), "events": ctx["events"],
        "date": first.strftime("%Y-%m-%d"), "start_time": first.strftime("%H:%M"), "end_time": last.strftime("%H:%M"),
        "segments": segs, "window": extras["window"], "window_override": extras.get("override"),
        "excluded_minutes": round(extras.get("excluded", 0), 1), "unattributed_minutes": round(extras.get("unattributed", 0), 1),
        "warnings": warnings,
    }

def _measure(conn, args, worker_type, exclude_tickets, ticket, use_focus):
    """Tramos de actividad medibles (ya restados los registrados/reservados). Devuelve (ctx, runs, extras) o un dict de error."""
    agent = getattr(args, "agent", None) or session_clock.agent_from_worker_type(worker_type) or session_clock.detect_agent()
    if not agent:
        return {"ok": False, "reason": "No se pudo determinar el agente (usa --agent claude|opencode|agy o --worker-type agent:<x>)."}
    session_id, origin, cands = session_clock.resolve_session(agent, os.getcwd(), getattr(args, "session", None))
    if not session_id:
        listed = [{"id": sid, "last_activity": ts.astimezone().strftime("%Y-%m-%d %H:%M")} for sid, ts in cands]
        return {"ok": False, "agent": agent, "candidates": listed,
                "reason": f"No se pudo determinar la sesión de {agent}: {origin}. Indica --session <id>."}
    stamps = session_clock.timestamps(agent, session_id)
    if not stamps:
        return {"ok": False, "agent": agent, "session_id": session_id, "reason": f"Sin evidencia de tiempos para la sesión {session_id} ({agent})."}

    now = config.now()
    try:
        win = _resolve_window(args, now)
    except ValueError as exc:
        return {"ok": False, "agent": agent, "session_id": session_id, "reason": str(exc)}
    w_start, w_end, notes, override = win["start"], win["end"], win["notes"], win["override"]
    inside = [t for t in stamps if w_start <= t <= w_end]
    if agent == "agy":
        runs = [(inside[0], inside[-1])] if len(inside) >= 2 else []
    else:
        runs = session_clock.active_runs(stamps, w_start, w_end)

    extras = {"attribution": "session", "notes": notes, "override": override,
              "window": f"{w_start.astimezone().strftime('%H:%M')}–{'24:00' if w_end.astimezone().strftime('%H:%M') == '00:00' and w_end > w_start else w_end.astimezone().strftime('%H:%M')}"}
    marks = focus_intervals(conn, session_id, win["day_start"], win["day_end"]) if use_focus else {}
    if marks:
        all_marked = [iv for ivs in marks.values() for iv in ivs]
        extras["unattributed"] = session_clock.total_minutes(session_clock.subtract(runs, all_marked))
        mine = marks.get(ticket)
        if not mine:
            return {"ok": False, "agent": agent, "session_id": session_id,
                    "reason": f"Hay marcas de foco hoy ({', '.join(sorted(marks))}) pero ninguna para {ticket}: usa `plane-tracker focus {ticket}` o registra con --duration."}
        runs = session_clock.intersect(runs, mine)
        extras["attribution"] = "focus"

    covered = session_coverage(conn, session_id, win["day"]) + reserved_runs(session_id, exclude_tickets)
    before = session_clock.total_minutes(runs)
    runs = session_clock.subtract(runs, covered)
    extras["excluded"] = before - session_clock.total_minutes(runs)
    ctx = {"agent": agent, "session_id": session_id, "origin": origin, "events": len(inside)}
    return ctx, runs, extras

def build_proposal(conn, args, capacity_bucket, worker_type, ticket):
    """Mide la sesión (solo tiempos) y devuelve un dict; 'ok' False significa preguntar."""
    if capacity_bucket in NO_PROPOSAL_BUCKETS:
        return {"ok": False, "reason": f"El balde '{capacity_bucket}' (soporte/reuniones) no deja huella en un transcript: pregunta la duración."}
    measured = _measure(conn, args, worker_type, {ticket}, ticket, use_focus=True)
    if isinstance(measured, dict):
        return measured
    ctx, runs, extras = measured
    if int(round(session_clock.total_minutes(runs))) < 1:
        return {"ok": False, "agent": ctx["agent"], "session_id": ctx["session_id"],
                "reason": "No hay actividad medible en la ventana (o ya está registrada/reservada para esta sesión)."}
    return _proposal_from_runs(ctx, runs, extras)

def build_split(conn, args, spec, worker_type):
    """Reparte la actividad medible entre varios tickets: {ticket: propuesta} contiguas y sin solape."""
    tickets = [part.split("=")[0].strip().upper() for part in spec.split(",") if "=" in part]
    measured = _measure(conn, args, worker_type, set(tickets), None, use_focus=False)
    if isinstance(measured, dict):
        return measured
    ctx, runs, extras = measured
    total = int(round(session_clock.total_minutes(runs)))
    try:
        shares = session_clock.parse_split(spec, total)
    except ValueError as exc:
        return {"ok": False, "agent": ctx["agent"], "session_id": ctx["session_id"], "reason": str(exc)}
    pieces = session_clock.cut_runs(runs, [m for _, m in shares])
    group = uuid.uuid4().hex[:8]
    parts = {}
    for (ticket, minutes), piece in zip(shares, pieces):
        if not piece:
            return {"ok": False, "agent": ctx["agent"], "session_id": ctx["session_id"], "reason": f"{ticket} se queda sin actividad con ese reparto."}
        proposal = _proposal_from_runs(ctx, piece, dict(extras, attribution="split"))
        proposal["split"] = {"group": group, "of": total, "share": minutes}
        parts[ticket] = proposal
    return {"ok": True, "group": group, "total": total, "parts": parts}

def print_proposal(proposal, ticket, stream):
    if not proposal["ok"]:
        stream.write(f"✖ Sin propuesta para {ticket}: {proposal['reason']}\n")
        for c in proposal.get("candidates", []):
            stream.write(f"   • {c['id']}  (última actividad {c['last_activity']})\n")
        stream.write("   Pregunta cuánto demoró; no se infiere ni se inventa.\n")
        return
    stream.write(f"⏱  Propuesta para {ticket}: {proposal['minutes']} min ({proposal['start_time']}–{proposal['end_time']}, {proposal['date']})\n")
    stream.write(f"   • Fuente   : {proposal['agent']} · sesión {proposal['session_id']} ({proposal['origin']}) · confianza {proposal['confidence']}\n")
    stream.write(f"   • Medición : neta {proposal['net_minutes']} min · bruta {proposal['gross_minutes']} min · {len(proposal['segments'])} tramo(s) · atribución {proposal['attribution']}\n")
    stream.write(f"   • Ventana  : {proposal['window']}\n")
    if proposal.get("split"):
        stream.write(f"   • Reparto  : parte de {proposal['split']['of']} min medidos (grupo {proposal['split']['group']}); no se recalcula mientras esté vigente\n")
    for w in proposal["warnings"]:
        stream.write(f"   ⚠ {w}\n")

def print_split(result, stream):
    stream.write(f"⏱  Reparto de {result['total']} min medidos (grupo {result['group']}):\n")
    for ticket, proposal in result["parts"].items():
        stream.write(f"   • {ticket:<10} {proposal['minutes']:>4} min  ({proposal['start_time']}–{proposal['end_time']})\n")
    first = next(iter(result["parts"].values()))
    stream.write(f"   • Fuente: {first['agent']} · sesión {first['session_id']} · confianza {first['confidence']} · ventana {first['window']}\n")
    for w in first["warnings"]:
        stream.write(f"   ⚠ {w}\n")

def worklog_metadata_block(meta):
    """Comentario HTML oculto con la telemetría del worklog (los '--' se escapan para no cerrarlo)."""
    payload = json.dumps(meta, ensure_ascii=False, sort_keys=True).replace("--", "\\u002d\\u002d")
    return f"<!-- PLANE_WORKLOG_METADATA {payload} -->"

_BLOCK_RE = re.compile(r"<!--\s*PLANE_WORKLOG_METADATA[\s\S]*?-->")

def find_metadata_block(html):
    match = _BLOCK_RE.search(html or "")
    return match.group(0) if match else None

def replace_metadata_block(html, meta):
    """Sustituye el bloque oculto (o lo añade si no existe) sin tocar el texto visible."""
    block = worklog_metadata_block(meta)
    if _BLOCK_RE.search(html or ""):
        return _BLOCK_RE.sub(lambda _m: block, html, count=1)
    return (html or "") + "\n" + block

def corrected_metadata(old, duration, track=None, capacity_bucket=None, worker_type=None, force=False, edited_at=None):
    """Metadata corregida de un worklog existente: conserva sesión, tramos y demás, y deja rastro de la corrección."""
    meta = dict(old)
    segments = meta.get("segments")
    if segments and duration != sum(seg.get("minutes", 0) for seg in segments):
        if not force:
            raise ValueError("El worklog tiene tramos medidos que suman otra duración; usa --force para descartar los tramos y fijar la duración.")
        meta.pop("segments", None)
    meta["previous_duration_minutes"] = old.get("duration_minutes")
    meta["duration_minutes"] = duration
    for key, value in (("track", track), ("capacity_bucket", capacity_bucket), ("worker_type", worker_type)):
        if value:
            meta[key] = value
    measured_by = dict(meta.get("measured_by") or {})
    measured_by["was"] = measured_by.get("kind")
    measured_by["kind"] = "corrected"
    meta["measured_by"] = measured_by
    meta["edited_at"] = edited_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return meta

def derived_start(end_dt, duration):
    """HH:MM de inicio derivado de la duración; nunca antes de las 00:00 del día del fin."""
    start = end_dt - timedelta(minutes=duration)
    if start.date() != end_dt.date():
        sys.stderr.write("⚠ La duración cruza la medianoche: el inicio se limita a 00:00 del día del registro.\n")
        return "00:00"
    return start.strftime("%H:%M")

# ------------------------------------------------------------------------------
# Comandos CLI
# ------------------------------------------------------------------------------

def cmd_comment(args, conn, base_url, api_key, workspace, default_project_id):
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    args.issue = issue_ref
    content = ""
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    elif args.message:
        content = args.message
    else:
        content = sys.stdin.read()

    if not content.strip():
        sys.stderr.write("Error: El comentario está vacío.\n")
        sys.exit(1)
    reject_placeholders(content)

    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)

    # --- Duración explícita (NUNCA estimar por defecto) ---------------------------------
    # Se valida ANTES de publicar: no puede quedar un comentario en Plane sin su worklog.
    # Fuentes válidas: metadata dual-layer (duration_minutes / duration_net_minutes) o --duration N.
    meta = extract_metadata_from_comment(content)
    meta_duration = None
    if meta:
        meta_duration = meta.get("duration_minutes") or meta.get("duration_net_minutes")
    duration = getattr(args, "duration", None) or meta_duration

    proposal = None
    if not duration:
        capacity_hint = getattr(args, "capacity_bucket", None) or (meta.get("capacity_bucket") if meta else None) or "deep_work"
        worker_hint = getattr(args, "worker_type", None) or (meta.get("worker_type") if meta else None)
        proposal_key = issue_ref.upper()
        if getattr(args, "accept_proposal", False):
            if capacity_hint in NO_PROPOSAL_BUCKETS:
                sys.stderr.write(f"Error: el balde '{capacity_hint}' (soporte/reuniones) no admite propuesta medida; usa --duration.\n")
                sys.exit(1)
            proposal = load_recent_proposal(proposal_key, current_session_id(args, worker_hint))
            if not proposal:
                sys.stderr.write(f"Error: no hay una propuesta reciente (<30 min) de esta sesión para {proposal_key}. Repite sin --accept-proposal para generarla.\n")
                sys.exit(1)
            duration = proposal["minutes"]
        else:
            pending = load_recent_proposal(proposal_key, current_session_id(args, worker_hint))
            result = pending if pending and pending.get("split") else build_proposal(conn, args, capacity_hint, worker_hint, proposal_key)
            print_proposal(result, proposal_key, sys.stderr)
            if result["ok"]:
                if result.get("split"):
                    sys.stderr.write(f"   (parte del reparto pendiente {result['split']['group']})\n")
                else:
                    save_proposal(proposal_key, result)
                sys.stderr.write("   Para registrarla tal cual: repite el comando con --accept-proposal; para ajustarla usa --duration N.\n")
            else:
                sys.stderr.write("Usa --duration <minutos> o incluye el bloque PLANE_WORKLOG_METADATA con 'duration_minutes'.\n")
            sys.exit(1)

    try:
        duration = int(duration)
    except (TypeError, ValueError):
        sys.stderr.write("Error: la duración debe ser un entero de minutos (ej: --duration 5).\n")
        sys.exit(1)

    if duration < 1 or duration > 24 * 60:
        sys.stderr.write(f"Error: duración fuera de rango ({duration} min). Debe estar entre 1 y 1440 minutos.\n")
        sys.exit(1)

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
    # Convertir Markdown → HTML si el contenido no viene ya como HTML
    if content.strip().startswith("<") and ">" in content:
        comment_html = content
    else:
        comment_html = markdown_to_html(content)

    # Caching atómico en SQLite3
    now = datetime.now()
    # Etiqueta real del ticket: identifier del proyecto resuelto (OPS-13, nunca OMNIFY-13 por defecto)
    proj_ident = get_project_identifier(conn, base_url, api_key, workspace, project_id)
    if not proj_ident and issue_ref and "-" in issue_ref:
        proj_ident = issue_ref.split("-")[0].upper()
    seq_label = issue.get("sequence_id") or seq_id
    ticket_label = f"{proj_ident}-{seq_label}" if proj_ident and seq_label else args.issue
    
    # Determinar track, worker_type y capacity_bucket (prioridad: flags de CLI -> metadata -> default)
    track = getattr(args, "track", None) or (meta.get("track") if meta else None) or "main"
    worker_type = getattr(args, "worker_type", None) or (meta.get("worker_type") if meta else None) or "human"
    capacity_bucket = getattr(args, "capacity_bucket", None) or (meta.get("capacity_bucket") if meta else None) or "deep_work"

    if not meta:
        clean_text = re.sub(r"<[^>]+>", "", content).strip()
        meta = {
            "schema_version": "2.2",
            "date": now.strftime("%Y-%m-%d"),
            "start_time": derived_start(now, duration),
            "end_time": now.strftime("%H:%M"),
            "duration_minutes": duration,
            "track": track,
            "worker_type": worker_type,
            "capacity_bucket": capacity_bucket,
            "notes": clean_text[:120] if clean_text else issue.get("name", ""),
            "stoppers": [],
            "phase": "dev"
        }
    else:
        meta["track"] = track
        meta["worker_type"] = worker_type
        meta["capacity_bucket"] = capacity_bucket
        meta["duration_minutes"] = duration
        # Horarios honestos: si la metadata no los trae, se derivan de la duración reportada
        meta.setdefault("date", now.strftime("%Y-%m-%d"))
        meta.setdefault("end_time", now.strftime("%H:%M"))
        if not meta.get("start_time"):
            end_t = datetime.strptime(meta["end_time"], "%H:%M")
            meta["start_time"] = derived_start(end_t, duration)

    if proposal:
        meta["date"] = proposal["date"]
        meta["start_time"] = proposal["start_time"]
        meta["end_time"] = proposal["end_time"]
        meta["segments"] = proposal["segments"]
        meta["measured_by"] = {
            "kind": "proposal_split" if proposal.get("split") else "proposal", "adapter": proposal["agent"],
            "confidence": proposal["confidence"], "session": proposal["session_id"], "gross_minutes": proposal["gross_minutes"],
            "attribution": proposal["attribution"],
        }
        if proposal.get("split"):
            meta["measured_by"]["split"] = proposal["split"]
        if proposal.get("window_override"):
            meta["measured_by"]["window_override"] = proposal["window_override"]
    else:
        # Duración declarada (no medida): se audita aparte; la sesión (si se resuelve sin ambigüedad) evita doble conteo.
        declared = {"kind": "declared", "worker_type": worker_type}
        declared_agent = getattr(args, "agent", None) or session_clock.agent_from_worker_type(worker_type) or session_clock.detect_agent()
        if declared_agent:
            declared_session = session_clock.resolve_session(declared_agent, os.getcwd(), getattr(args, "session", None))[0]
            if declared_session:
                declared["session"] = declared_session
        meta["measured_by"] = declared

    # El comentario viaja con su propia telemetría (bloque HTML oculto que Plane conserva): así las horas
    # sobreviven a la pérdida de la caché local y se pueden reconstruir con `report --sync`.
    if "PLANE_WORKLOG_METADATA" not in comment_html:
        comment_html += "\n" + worklog_metadata_block(meta)
    res = api_request(url, api_key, method="POST", data={"comment_html": comment_html})

    entry = {
        "id": res.get("id"),
        "ticket_id": ticket_label,
        "track": track,
        "issue_name": issue.get("name", ""),
        "date": meta.get("date", now.strftime("%Y-%m-%d")),
        "start_time": meta.get("start_time", derived_start(now, duration)),
        "end_time": meta.get("end_time", now.strftime("%H:%M")),
        "duration_minutes": duration,
        "worker_type": worker_type,
        "capacity_bucket": capacity_bucket,
        "phase": meta.get("phase", "dev"),
        "role": meta.get("role", "backend_engineer"),
        "notes": meta.get("notes", issue.get("name", "")),
        "stoppers": meta.get("stoppers", []),
        "plane_comment_id": res.get("id"),
        "created_at": datetime.now().isoformat(),
        "raw_payload": meta
    }
    clash = conn.execute(
        "SELECT 1 FROM worklogs WHERE ticket_id = ? AND track = ? AND date = ? AND start_time = ?",
        (entry["ticket_id"], entry["track"], entry["date"], entry["start_time"]),
    ).fetchone()
    if clash:
        sys.stderr.write("⚠ Ya existía un worklog local con el mismo ticket/track/fecha/inicio: se sobrescribe (el comentario anterior sigue en Plane).\n")
    upsert_worklog(conn, entry)
    if proposal:
        consume_proposal(issue_ref.upper(), proposal["session_id"])

    if getattr(args, "json", False):
        print(json.dumps({"status": "ok", "action": "comment", "issue_id": issue["id"], "sequence_id": issue.get("sequence_id"), "comment_id": res.get("id")}))
    else:
        print(f"✔ Comentario publicado exitosamente en {args.issue} (ID Comentario: {res.get('id')})")

def cmd_propose_duration(args, conn, base_url, api_key, workspace, default_project_id):
    """Solo lectura: mide la sesión y muestra la propuesta (o el reparto --split) sin registrar nada."""
    capacity = getattr(args, "capacity_bucket", None) or "deep_work"
    worker_type = getattr(args, "worker_type", None)
    if getattr(args, "split", None):
        result = build_split(conn, args, args.split, worker_type)
        if result["ok"]:
            # Validar que cada ticket exista antes de reservar el reparto.
            for ticket in result["parts"]:
                resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, ticket)
            save_group(result["group"], result["parts"])
        if getattr(args, "json", False):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif result["ok"]:
            print_split(result, sys.stdout)
            print("   Registra cada parte con: plane-tracker comment <TICKET> -m \"...\" --accept-proposal")
        else:
            print_proposal(result, "reparto", sys.stdout)
        sys.exit(0 if result["ok"] else 1)

    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    key = issue_ref.upper()
    pending = load_recent_proposal(key, current_session_id(args, worker_type))
    explicit_window = bool(getattr(args, "since", None) or getattr(args, "until", None))
    if pending and pending.get("split") and not explicit_window:
        result = pending  # reparto vigente: no se recalcula para no solaparlo
    else:
        result = build_proposal(conn, args, capacity, worker_type, key)
        if result["ok"]:
            save_proposal(key, result)
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_proposal(result, key, sys.stdout)
    sys.exit(0 if result["ok"] else 1)

def _resolve_own_comment(args, base_url, api_key, workspace, project_id, issue):
    """ID del comentario a tocar: el indicado, o el último comentario propio del ticket."""
    if args.comment_id:
        return args.comment_id
    actor = get_actor_uuid(base_url, api_key, workspace)
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
    res = api_request(url, api_key)
    comments = res if isinstance(res, list) else res.get("results", [])
    own = [c for c in comments if not actor or c.get("actor") == actor]
    if not own:
        sys.stderr.write("Error: No hay comentarios propios en el ticket. Indica el ID con --comment-id.\n")
        sys.exit(1)
    return max(own, key=lambda c: c.get("created_at", "")).get("id")


def cmd_comment_delete(args, conn, base_url, api_key, workspace, default_project_id):
    """Elimina un comentario en Plane y su worklog en la BD local."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    cid = _resolve_own_comment(args, base_url, api_key, workspace, project_id, issue)
    api_request(f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/{cid}/", api_key, method="DELETE")
    with conn:
        n = conn.execute("DELETE FROM worklogs WHERE plane_comment_id = ?", (cid,)).rowcount
    print(f"✔ Comentario {cid} eliminado de {issue_ref} ({n} worklog local(es) borrado(s))")


def cmd_comment_edit(args, conn, base_url, api_key, workspace, default_project_id):
    """Edita el texto de un comentario y/o registra su worklog local, sin publicar otro comentario."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    cid = _resolve_own_comment(args, base_url, api_key, workspace, project_id, issue)
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/{cid}/"

    content = args.message
    if content is not None:
        reject_placeholders(content)
    row = conn.execute("SELECT raw_payload FROM worklogs WHERE plane_comment_id = ?", (cid,)).fetchone()
    local_meta = json.loads(row["raw_payload"]) if row else None
    if content is not None:
        html = content if content.strip().startswith("<") and ">" in content else markdown_to_html(content)
        if "PLANE_WORKLOG_METADATA" not in html:
            # Editar el texto no debe perder la telemetría: se conserva el bloque que ya traía el comentario.
            existing = find_metadata_block(api_request(url, api_key).get("comment_html"))
            if existing:
                html += "\n" + existing
            elif local_meta:
                html += "\n" + worklog_metadata_block(local_meta)
        api_request(url, api_key, method="PATCH", data={"comment_html": html})
        print(f"✔ Comentario {cid} actualizado en {issue_ref}")
    elif getattr(args, "embed_metadata", False):
        if not local_meta:
            sys.stderr.write("Error: no hay worklog local vinculado a ese comentario; usa --duration para registrarlo.\n")
            sys.exit(1)
        current = api_request(url, api_key).get("comment_html") or ""
        if "PLANE_WORKLOG_METADATA" in current:
            print(f"✔ El comentario {cid} ya lleva su metadata")
        else:
            api_request(url, api_key, method="PATCH", data={"comment_html": current + "\n" + worklog_metadata_block(local_meta)})
            print(f"✔ Metadata del worklog añadida al comentario {cid} (sin cambiar su texto visible)")

    if args.duration:
        c = api_request(url, api_key)
        current_html = c.get("comment_html") or ""
        proj_ident = get_project_identifier(conn, base_url, api_key, workspace, project_id)
        old_meta = extract_metadata_from_comment(current_html) if find_metadata_block(current_html) else None
        if old_meta:
            # Corrección: se parte del bloque existente (sesión, tramos, fechas) y se cambia solo lo pedido.
            try:
                meta = corrected_metadata(old_meta, args.duration, args.track, args.capacity_bucket, args.worker_type, getattr(args, "force", False))
            except ValueError as exc:
                sys.stderr.write(f"Error: {exc}\n")
                sys.exit(1)
        else:
            # Comentario sin telemetría: su hora de publicación (local) es el fin; inicio = fin - duración
            end = datetime.fromisoformat(c["created_at"].replace("Z", "+00:00")).astimezone()
            start = end - timedelta(minutes=args.duration)
            notes = re.sub(r"<[^>]+>", "", current_html).strip()[:120] or issue.get("name", "")
            meta = {"schema_version": "2.2", "date": start.strftime("%Y-%m-%d"), "start_time": start.strftime("%H:%M"),
                    "end_time": end.strftime("%H:%M"), "duration_minutes": args.duration, "track": args.track or "main",
                    "worker_type": args.worker_type or "human", "capacity_bucket": args.capacity_bucket or "deep_work",
                    "notes": notes, "stoppers": [], "phase": "dev", "measured_by": {"kind": "declared", "worker_type": args.worker_type or "human"}}
        with conn:  # un worklog por comentario: se reemplaza por id de comentario (no por clave primaria)
            conn.execute("DELETE FROM worklogs WHERE plane_comment_id = ?", (cid,))
        upsert_worklog(conn, {**meta, "ticket_id": f"{proj_ident}-{issue.get('sequence_id') or seq_id}",
                              "issue_name": issue.get("name", ""), "plane_comment_id": cid, "raw_payload": meta})
        api_request(url, api_key, method="PATCH", data={"comment_html": replace_metadata_block(current_html, meta)})
        print(f"✔ Worklog {'corregido' if old_meta else 'vinculado'} en {cid}: {meta['date']} {meta['start_time']}-{meta['end_time']} ({args.duration} min, {meta['track']}, {meta['capacity_bucket']})")
    elif content is None and not getattr(args, "embed_metadata", False):
        sys.stderr.write("Advertencia: nada que hacer (usa -m y/o --duration).\n")


def cmd_link(args, conn, base_url, api_key, workspace, default_project_id):
    """Adjunta un enlace (PR, doc) al work item: aparece en su panel de enlaces, sin notificar como comentario."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    if not re.match(r"^https?://", args.url):
        sys.stderr.write("Error: la URL debe empezar por http:// o https://\n")
        sys.exit(1)
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/links/"
    existing = api_request(url, api_key).get("results", [])
    if any(l.get("url") == args.url for l in existing):
        print(f"✔ {issue_ref} ya tiene ese enlace")
        return
    api_request(url, api_key, method="POST", data={"url": args.url, "title": args.title or args.url})
    print(f"✔ Enlace añadido a {issue_ref}: {args.title or args.url}")

def cmd_update(args, conn, base_url, api_key, workspace, default_project_id):
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    args.issue = issue_ref
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    patch_data = {}

    if args.state:
        states_map = get_states_map(conn, base_url, api_key, workspace, project_id)
        target_state = args.state.lower().strip().replace("ó", "o").replace("é", "e").replace("á", "a")
        if target_state not in states_map:
            sys.stderr.write(f"Error: Estado desconocido '{args.state}'. Estados válidos en proyecto: {', '.join(states_map.keys())}\n")
            sys.exit(1)
        patch_data["state"] = states_map[target_state]

    if args.priority:
        prio = args.priority.lower().strip()
        if prio not in ("urgent", "high", "medium", "low", "none"):
            sys.stderr.write(f"Error: Prioridad desconocida '{args.priority}'. Opciones: urgent, high, medium, low, none.\n")
            sys.exit(1)
        patch_data["priority"] = prio

    if args.labels:
        labels_map = get_labels_map(conn, base_url, api_key, workspace, project_id)
        label_ids = []
        for raw_l in args.labels.split(","):
            l = raw_l.strip().lower()
            if l:
                if l in labels_map:
                    label_ids.append(labels_map[l])
                else:
                    sys.stderr.write(f"Advertencia: Etiqueta '{l}' no existe en el proyecto. Ignorada.\n")
        patch_data["labels"] = label_ids

    for arg, field in (("start_date", "start_date"), ("due_date", "target_date")):
        val = getattr(args, arg, None)
        if val:
            try:
                datetime.strptime(val, "%Y-%m-%d")
            except ValueError:
                sys.stderr.write(f"Error: Fecha inválida '{val}'. Formato: YYYY-MM-DD.\n")
                sys.exit(1)
            patch_data[field] = val

    if not patch_data:
        sys.stderr.write("Advertencia: No se indicaron cambios para actualizar (--state, --priority, --labels, --start-date o --due-date).\n")
        return

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/"
    res = api_request(url, api_key, method="PATCH", data=patch_data)
    
    if getattr(args, "json", False):
        print(json.dumps({"status": "ok", "action": "update", "issue_id": issue["id"], "sequence_id": issue.get("sequence_id"), "patched": patch_data}))
    else:
        changes = []
        if "state" in patch_data: changes.append(f"Estado ➔ {args.state}")
        if "priority" in patch_data: changes.append(f"Prioridad ➔ {args.priority}")
        if "labels" in patch_data: changes.append(f"Etiquetas ➔ {args.labels}")
        if "start_date" in patch_data: changes.append(f"Inicio ➔ {patch_data['start_date']}")
        if "target_date" in patch_data: changes.append(f"Vence ➔ {patch_data['target_date']}")
        print(f"✔ Ticket {args.issue} actualizado con éxito: [{', '.join(changes)}]")

def cmd_create(args, conn, base_url, api_key, workspace, default_project_id):
    """Crea un nuevo ticket en Plane y devuelve su identificador para ramas Git."""
    project_id = default_project_id
    project_ident = "OMNIFY"

    projects_map = get_projects_map(conn, base_url, api_key, workspace)
    if getattr(args, "project", None):
        p_upper = args.project.upper()
        if p_upper in projects_map:
            project_id = projects_map[p_upper]["id"]
            project_ident = p_upper
        else:
            projects_map = get_projects_map(conn, base_url, api_key, workspace, force_refresh=True)
            if p_upper in projects_map:
                project_id = projects_map[p_upper]["id"]
                project_ident = p_upper
            else:
                sys.stderr.write(f"Error: Proyecto '{args.project}' no encontrado. Opciones: {', '.join(projects_map.keys())}\n")
                sys.exit(1)
    else:
        for k, v in projects_map.items():
            if v["id"] == project_id:
                project_ident = k
                break

    payload = {
        "name": args.title.strip()
    }

    if getattr(args, "description", None):
        desc = args.description.strip()
        if desc.startswith("<") and ">" in desc:
            # Ya viene como HTML explícito
            payload["description_html"] = desc
        else:
            # Markdown → HTML
            payload["description_html"] = markdown_to_html(desc)

    if getattr(args, "priority", None):
        payload["priority"] = args.priority.lower()

    if getattr(args, "start_date", None):
        payload["start_date"] = args.start_date
    if getattr(args, "due_date", None):
        payload["target_date"] = args.due_date

    if getattr(args, "state", None):
        states_map = get_states_map(conn, base_url, api_key, workspace, project_id)
        norm_state = args.state.lower().strip().replace("ó", "o").replace("é", "e").replace("á", "a")
        if norm_state in states_map:
            payload["state"] = states_map[norm_state]
        else:
            sys.stderr.write(f"Error: Estado desconocido '{args.state}'. Estados válidos: {', '.join(states_map.keys())}\n")
            sys.exit(1)

    if getattr(args, "labels", None):
        labels_map = get_labels_map(conn, base_url, api_key, workspace, project_id)
        label_ids = []
        for l in args.labels.split(","):
            l_clean = l.strip().lower()
            if l_clean:
                if l_clean in labels_map:
                    label_ids.append(labels_map[l_clean])
                else:
                    sys.stderr.write(f"Advertencia: Etiqueta '{l_clean}' no encontrada en el proyecto. Se omitirá.\n")
        if label_ids:
            payload["labels"] = label_ids

    attach_paths = getattr(args, "attach", None) or []
    validate_attachment_paths(attach_paths)

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/"
    res = api_request(url, api_key, method="POST", data=payload)

    # Plane no admite adjuntos en la creación: se suben justo después (el ticket ya existe si alguno falla).
    attached, attach_errors = [], []
    for path in attach_paths:
        try:
            name, _ = upload_attachment(base_url, api_key, workspace, project_id, res["id"], path)
            attached.append(name)
        except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError, SystemExit) as exc:
            attach_errors.append(f"{path}: {exc}")

    seq_id = res.get("sequence_id")
    ticket_ref = f"{project_ident}-{seq_id}" if seq_id else res.get("id")
    web_url = f"{base_url.rstrip('/')}/{workspace}/projects/{project_id}/issues/{res.get('id')}"

    # Generar sugerencia de rama inteligente según prefijo [FASE]
    branch_type = "feat"
    clean_title = args.title.strip()
    phase_match = re.match(r"^\[([A-Za-z]+)\]\s*(.*)$", clean_title)
    if phase_match:
        f_prefix = phase_match.group(1).lower()
        clean_title = phase_match.group(2)
        type_map = {
            "spike": "spike",
            "rfc": "spike",
            "fix": "fix",
            "feat": "feat",
            "infra": "infra",
            "qa": "test",
            "test": "test",
            "refactor": "refactor"
        }
        branch_type = type_map.get(f_prefix, "feat")

    clean_desc = re.sub(r"[^a-zA-Z0-9]+", "-", clean_title.lower()).strip("-")
    if len(clean_desc) > 35:
        clean_desc = clean_desc[:35].rstrip("-")
    branch_sugg = f"{branch_type}/{ticket_ref}-{clean_desc}"

    if getattr(args, "json", False):
        print(json.dumps({
            "status": "ok",
            "action": "create",
            "ticket": ticket_ref,
            "id": res.get("id"),
            "sequence_id": seq_id,
            "name": res.get("name"),
            "branch_suggestion": branch_sugg,
            "url": web_url,
            "attachments": attached,
            "attachment_errors": attach_errors,
            "raw": res
        }, indent=2))
    else:
        print(f"\n🎉 Ticket creado exitosamente: {ticket_ref}")
        print(f"   • Título: {res.get('name')}")
        print(f"   • Prioridad: {res.get('priority', 'none').upper()}")
        print(f"   • Enlace: {web_url}")
        print(f"   • Sugerencia de rama Git: {branch_sugg}")
        if attached:
            print(f"   • Adjuntos: {', '.join(attached)}")
        for err in attach_errors:
            sys.stderr.write(f"   ⚠ No se pudo adjuntar {err} (el ticket sí se creó; usa plane-tracker attach {ticket_ref} <archivo>)\n")
        print("")

def format_lifecycle(issue):
    """'completado' con su lead time, o 'abierto desde hace …' (calendario, UTC)."""
    created = session_clock.parse_time(issue.get("created_at"))
    if not created:
        return "Ciclo     : ?"
    completed = session_clock.parse_time(issue.get("completed_at"))
    end = completed or datetime.now(timezone.utc)
    days = (end - created).total_seconds() / 86400.0
    span = f"{days:.1f} días" if days >= 1 else format_minutes(int((end - created).total_seconds() // 60))
    if completed:
        return f"Ciclo     : completado {completed.astimezone().strftime('%Y-%m-%d %H:%M')} (lead time {span})"
    return f"Ciclo     : abierto desde hace {span}"


# ------------------------------------------------------------------------------
# Flujo por work item: lead time, cycle time, tiempo por estado y esfuerzo
# ------------------------------------------------------------------------------

FLOW_TTL_SECONDS = 3600
FLOW_MAX_PAGES = 20

def format_span(minutes):
    if minutes is None:
        return "—"
    return f"{minutes / 1440:.1f} d" if minutes >= 1440 else format_minutes(int(round(minutes)))

def load_states_by_id(conn, base_url, api_key, workspace, project_id):
    get_states_map(conn, base_url, api_key, workspace, project_id)
    rows = conn.execute("SELECT id, name, group_name FROM states WHERE project_id = ?", (project_id,)).fetchall()
    return {r["id"]: {"name": r["name"], "group": r["group_name"]} for r in rows}

def fetch_transitions(conn, base_url, api_key, workspace, project_id, issue, ticket_label):
    """Transiciones de estado del issue (Plane no tiene endpoint por proyecto: una llamada por ticket).

    Incremental: un ticket cuyo updated_at no cambió no se vuelve a pedir (los abiertos expiran a la hora).
    """
    now = time.time()
    cached = conn.execute("SELECT fetched_at, issue_updated_at FROM flow_fetch WHERE issue_id = ?", (issue["id"],)).fetchone()
    fresh = bool(
        cached and cached["issue_updated_at"] == issue.get("updated_at")
        and (issue.get("completed_at") or now - cached["fetched_at"] < FLOW_TTL_SECONDS)
    )
    if not fresh:
        found, cursor = [], None
        try:
            for _ in range(FLOW_MAX_PAGES):
                url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/activities/?per_page=100"
                if cursor:
                    url += f"&cursor={urllib.parse.quote(cursor)}"
                data = api_request(url, api_key, raise_on_error=True)
                for a in data.get("results", []):
                    if a.get("field") == "state" and a.get("new_identifier") and a.get("created_at"):
                        found.append((a["id"], issue["id"], ticket_label, a["created_at"], a.get("old_identifier"),
                                      a["new_identifier"], a.get("old_value"), a.get("new_value")))
                if not data.get("next_page_results"):
                    break
                cursor = data.get("next_cursor")
            with conn:
                conn.executemany("INSERT OR REPLACE INTO state_transitions VALUES (?,?,?,?,?,?,?,?)", found)
                conn.execute("INSERT OR REPLACE INTO flow_fetch VALUES (?,?,?)", (issue["id"], now, issue.get("updated_at")))
        except (urllib.error.URLError, OSError) as exc:
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
        if not dur or dur < 1:
            continue
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
        transitions, states, wls, datetime.now(timezone.utc))
    return flow, transitions, states

def flow_to_json(flow):
    out = dict(flow)
    for key in ("created", "closed"):
        out[key] = out[key].isoformat() if out.get(key) else None
    return out

def print_flow(flow, transitions, states, stream=None):
    out = stream or sys.stdout
    outcome = {"completed": "completado", "cancelled": "cancelado", "open": "abierto"}[flow["outcome"]]
    out.write("\n🔁 Flujo (calendario; esfuerzo = worklogs locales + metadata en comentarios)\n")
    out.write(f"   • Resultado : {outcome}\n")
    out.write(f"   • Lead time : {format_span(flow['lead_minutes'])}{' (hasta hoy)' if flow['outcome'] == 'open' else ''}\n")
    out.write(f"   • Cycle     : {format_span(flow['cycle_active_minutes'])} activo · {format_span(flow['cycle_gross_minutes'])} bruto (Pausado excluido del activo)\n")
    out.write(f"   • Esfuerzo  : {format_span(flow['effort_clock_minutes'])} reloj · {format_span(flow['effort_compute_minutes'])} cómputo ({flow['worklogs']} worklogs)\n")
    if flow["effort_clock_over_cycle"] is not None:
        out.write(f"   • Reloj/cycle: {flow['effort_clock_over_cycle']:.2f} (señal secundaria: espera de terceros y paralelismo la distorsionan)\n")
    if flow["by_state_minutes"]:
        out.write("   • Estados   : " + " · ".join(f"{k} {format_span(v)}" for k, v in flow["by_state_minutes"].items()) + "\n")
    if flow["worklogs_before_created"] or flow["worklogs_after_closed"]:
        out.write(f"   • Fuera de ventana: {flow['worklogs_before_created']} antes de crear · {flow['worklogs_after_closed']} después de cerrar\n")
    if flow["flags"]:
        out.write("   • Flags     : " + ", ".join(flow["flags"]) + "\n")
    for t in transitions:
        a = states.get(t["from_id"], {}).get("name", "?")
        b = states.get(t["to_id"], {}).get("name", "?")
        out.write(f"   {t['at'].astimezone().strftime('%Y-%m-%d %H:%M')}  {a} → {b}\n")
    out.write("\n")

def cmd_report_flow(args, conn, base_url, api_key, workspace, default_project_id, s_str, e_str):
    """Flujo por ticket del periodo: los que tienen worklogs en caché o se cerraron en él."""
    proj = getattr(args, "project", None)
    like = f"{proj.upper()}-%" if proj else "%"
    labels = {r["ticket_id"] for r in conn.execute(
        "SELECT DISTINCT ticket_id FROM worklogs WHERE date >= ? AND date <= ? AND ticket_id LIKE ?", (s_str, e_str, like))}
    labels |= {r["ticket_id"] for r in conn.execute(
        "SELECT ticket_id FROM issues_cache WHERE completed_at IS NOT NULL AND substr(completed_at, 1, 10) >= ? "
        "AND substr(completed_at, 1, 10) <= ? AND ticket_id LIKE ?", (s_str, e_str, like))}
    rows, flows = [], []
    for label in sorted(labels):
        try:
            project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, label)
            issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
            flow, transitions, states = build_ticket_flow(conn, base_url, api_key, workspace, project_id, issue, label)
        except SystemExit:
            sys.stderr.write(f"⚠ {label}: no se pudo consultar en Plane (¿eliminado?); se omite.\n")
            continue
        if flow:
            flows.append(flow)
            rows.append((label, issue.get("name", ""), flow))
    agg = flow_metrics.aggregate(flows)

    if getattr(args, "json", False):
        print(json.dumps({"period": [s_str, e_str], "tickets": [{"ticket": l, "title": n, **flow_to_json(f)} for l, n, f in rows], "summary": agg},
                         indent=2, ensure_ascii=False))
        return
    print(f"\n🔁 Flujo por ticket · {s_str} → {e_str} (calendario; lead/cycle en UTC)")
    if not rows:
        print("   (sin tickets con worklogs en caché ni cerrados en el periodo; usa --sync para traer más)\n")
        return
    for label, title, f in rows:
        outcome = {"completed": "✔", "cancelled": "✖", "open": "…"}[f["outcome"]]
        flags = f" [{', '.join(f['flags'])}]" if f["flags"] else ""
        print(f"  {outcome} {label:<10} lead {format_span(f['lead_minutes']):<8} cycle {format_span(f['cycle_active_minutes']):<8} "
              f"esfuerzo {format_span(f['effort_clock_minutes'])} reloj / {format_span(f['effort_compute_minutes'])} cómputo{flags}")
        print(f"      {title[:70]}")
    print(f"\n   Resumen: {agg['completed']} completados · {agg['cancelled']} cancelados · {agg['open']} abiertos")
    print(f"   Mediana lead {format_span(agg['median_lead_minutes'])} (n={agg['n_lead']}) · cycle {format_span(agg['median_cycle_minutes'])} (n={agg['n_cycle']}); "
          f"{agg['excluded']} excluidos (umbrella, instant_close, no_transition)")
    print("   Nota: el esfuerzo sale de los worklogs de la caché local y de la metadata en los comentarios; lo no registrado no aparece.\n")


# ------------------------------------------------------------------------------
# Adjuntos del work item (flujo de Plane: crear -> subir a almacenamiento -> confirmar)
# ------------------------------------------------------------------------------

ATTACH_MAX_BYTES = 50 * 1024 * 1024

def build_multipart(fields, filename, content_type, data):
    """multipart/form-data para el POST firmado de almacenamiento (el archivo debe ir al final)."""
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8") for k, v in fields.items()]
    safe_name = filename.replace('"', "_")
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe_name}"\r\nContent-Type: {content_type}\r\n\r\n'.encode("utf-8") + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"

def upload_attachment(base_url, api_key, workspace, project_id, issue_id, path):
    attachments_url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue_id}/issue-attachments/"
    name = os.path.basename(path)
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    with open(path, "rb") as handle:
        data = handle.read()
    created = api_request(attachments_url, api_key, method="POST", data={"name": name, "type": content_type, "size": len(data)})
    asset_id, upload = created["asset_id"], created["upload_data"]
    body, header = build_multipart(upload["fields"], name, content_type, data)
    try:
        req = urllib.request.Request(upload["url"], data=body, headers={"Content-Type": header}, method="POST")
        with urllib.request.urlopen(req, timeout=60):
            pass
        api_request(f"{attachments_url}{asset_id}/", api_key, method="PATCH", data={"is_uploaded": True})
    except BaseException:
        # No dejar un adjunto "pendiente" huérfano si falla la subida o la confirmación.
        try:
            api_request(f"{attachments_url}{asset_id}/", api_key, method="DELETE", raise_on_error=True)
        except Exception:
            pass
        raise
    return name, len(data)

def local_stamp(value):
    moment = session_clock.parse_time(value)
    return moment.astimezone().strftime("%Y-%m-%d %H:%M") if moment else ""

def validate_attachment_paths(paths):
    """Valida antes de tocar Plane: así un ticket no queda creado a medias por un archivo inválido."""
    for path in paths:
        if not os.path.isfile(path):
            sys.stderr.write(f"Error: '{path}' no es un archivo.\n")
            sys.exit(1)
        if os.path.getsize(path) > ATTACH_MAX_BYTES:
            sys.stderr.write(f"Error: '{path}' supera {ATTACH_MAX_BYTES // (1024 * 1024)} MB.\n")
            sys.exit(1)

def delete_attachment(base_url, api_key, workspace, project_id, issue_id, attachment_id):
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue_id}/issue-attachments/{attachment_id}/"
    api_request(url, api_key, method="DELETE")

def cmd_attach(args, conn, base_url, api_key, workspace, default_project_id):
    """Sube archivos al work item; con --replace ID sustituye un adjunto (sube el nuevo y luego borra el viejo)."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    validate_attachment_paths(args.files)
    if args.replace and len(args.files) != 1:
        sys.stderr.write("Error: --replace admite exactamente un archivo.\n")
        sys.exit(1)
    for path in args.files:
        try:
            name, size = upload_attachment(base_url, api_key, workspace, project_id, issue["id"], path)
        except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError) as exc:
            sys.stderr.write(f"Error subiendo '{path}': {exc}\n")
            sys.exit(1)
        print(f"✔ Adjunto subido a {issue_ref}: {name} ({size / 1024:.1f} KB)")
        if args.replace:
            delete_attachment(base_url, api_key, workspace, project_id, issue["id"], args.replace)
            print(f"✔ Adjunto anterior {args.replace} eliminado (reemplazado)")

def cmd_attachments(args, conn, base_url, api_key, workspace, default_project_id):
    """Lista los adjuntos del work item."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/issue-attachments/"
    if getattr(args, "delete", None):
        delete_attachment(base_url, api_key, workspace, project_id, issue["id"], args.delete)
        print(f"✔ Adjunto {args.delete} eliminado de {issue_ref}")
        return
    data = api_request(url, api_key)
    items = data if isinstance(data, list) else data.get("results", [])
    rows = [{"id": a.get("id"), "name": (a.get("attributes") or {}).get("name"), "size": (a.get("attributes") or {}).get("size") or a.get("size"),
             "created_at": a.get("created_at")} for a in items]
    if getattr(args, "json", False):
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    print(f"\n📎 Adjuntos de {issue_ref} ({len(rows)}):")
    for r in rows:
        print(f"   • {r['name']}  ({(r['size'] or 0) / 1024:.1f} KB)  {local_stamp(r['created_at'])}  {r['id']}")
    print("")

# ------------------------------------------------------------------------------
# Salud de la conexión con Plane (a partir del registro de llamadas)
# ------------------------------------------------------------------------------

def summarize_requests(records, since):
    """Agrega el registro de llamadas posteriores a `since` (datetime UTC)."""
    recent = []
    for r in records:
        ts = session_clock.parse_time(r.get("ts"))
        if ts and ts >= since:
            recent.append((ts, r))
    lat = sorted(r["ms"] for _, r in recent if r.get("status"))
    failures = [(ts, r) for ts, r in recent if not r.get("status") or r["status"] >= 400]
    by_error = {}
    for _, r in failures:
        key = r.get("error") or f"HTTP {r.get('status')}"
        by_error[key] = by_error.get(key, 0) + 1
    pct = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None
    return {"requests": len(recent), "failures": len(failures), "retried": sum(1 for _, r in recent if r.get("attempt", 1) > 1),
            "p50_ms": pct(0.5), "p95_ms": pct(0.95), "max_ms": lat[-1] if lat else None,
            "errors": by_error, "last_failures": [dict(r, ts=ts.astimezone().strftime("%Y-%m-%d %H:%M:%S")) for ts, r in failures[-5:]]}

def cmd_health(args, conn, base_url, api_key, workspace, default_project_id):
    """Latencia y errores de las últimas llamadas a Plane (caídas, timeouts, lentitud)."""
    records = []
    for path in (config.request_log() + ".1", config.request_log()):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        records.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            continue
    summary = summarize_requests(records, datetime.now(timezone.utc) - timedelta(hours=args.hours))
    if getattr(args, "json", False):
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return
    print(f"\n🩺 Plane · últimas {args.hours} h: {summary['requests']} llamadas, {summary['failures']} fallidas, {summary['retried']} con reintento")
    print(f"   • Latencia: p50 {summary['p50_ms']} ms · p95 {summary['p95_ms']} ms · máx {summary['max_ms']} ms")
    for key, count in sorted(summary["errors"].items(), key=lambda kv: -kv[1]):
        print(f"   • {count} × {key}")
    for f in summary["last_failures"]:
        print(f"     {f['ts']}  {f['method']} {f['path'][-60:]}  → {f.get('error') or 'HTTP ' + str(f.get('status'))} ({f['ms']} ms)")
    print("")

def cmd_focus(args, conn, base_url, api_key, workspace, default_project_id):
    """Marca en qué ticket trabaja esta sesión; `propose-duration` atribuye a cada ticket solo sus intervalos."""
    agent = getattr(args, "agent", None) or session_clock.detect_agent()
    if not agent:
        sys.stderr.write("Error: no se pudo determinar el agente (usa --agent claude|opencode|agy).\n")
        sys.exit(1)
    session_id, origin, cands = session_clock.resolve_session(agent, os.getcwd(), getattr(args, "session", None))
    if not session_id:
        sys.stderr.write(f"Error: no se pudo determinar la sesión de {agent}: {origin}. Indica --session <id>.\n")
        for sid, ts in cands:
            sys.stderr.write(f"   • {sid}  (última actividad {ts.astimezone().strftime('%Y-%m-%d %H:%M')})\n")
        sys.exit(1)

    now = config.now()
    iso = now.isoformat(timespec="seconds")
    with conn:  # las marcas son útiles solo el día en curso: se purgan las antiguas
        conn.execute("DELETE FROM session_marks WHERE COALESCE(ended_at, started_at) < ?", ((now - timedelta(days=FOCUS_KEEP_DAYS)).isoformat(timespec="seconds"),))
    current = conn.execute("SELECT id, ticket FROM session_marks WHERE session_id = ? AND ended_at IS NULL", (session_id,)).fetchall()

    if getattr(args, "status", False):
        stamps = session_clock.timestamps(agent, session_id)
        midnight = config.local_midnight_utc(now)
        runs = session_clock.active_runs(stamps, midnight, now)
        marks = focus_intervals(conn, session_id, midnight, now)
        per_ticket = {t: session_clock.total_minutes(session_clock.intersect(runs, ivs)) for t, ivs in marks.items()}
        unattributed = session_clock.total_minutes(session_clock.subtract(runs, [iv for ivs in marks.values() for iv in ivs]))
        result = {"session": session_id, "agent": agent, "current": current[0]["ticket"] if current else None,
                  "tickets": {t: round(m, 1) for t, m in per_ticket.items()}, "unattributed_minutes": round(unattributed, 1)}
        if getattr(args, "json", False):
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return
        print(f"\n🎯 Foco de la sesión {session_id} ({agent}) · hoy")
        print(f"   • Ahora: {result['current'] or '— (sin foco)'}")
        for t, m in sorted(result["tickets"].items(), key=lambda kv: -kv[1]):
            print(f"   • {t:<10} {m:.0f} min atribuidos")
        print(f"   • Sin foco : {unattributed:.0f} min (no se atribuyen solos)\n")
        return

    if getattr(args, "off", False):
        with conn:
            conn.execute("UPDATE session_marks SET ended_at = ? WHERE session_id = ? AND ended_at IS NULL", (iso, session_id))
        print("✔ Foco cerrado" + (f" (era {current[0]['ticket']})" if current else " (no había foco abierto)"))
        return

    if not args.issue:
        sys.stderr.write("Error: indica el ticket (plane-tracker focus OMNIFY-205), o usa --off / --status.\n")
        sys.exit(1)
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    ticket = issue_ref.upper()
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    state = conn.execute("SELECT group_name FROM states WHERE id = ?", (issue.get("state"),)).fetchone()
    if state and state["group_name"] in flow_metrics.TERMINAL_GROUPS:
        sys.stderr.write(f"⚠ {ticket} está en un estado terminal ({state['group_name']}); la marca se crea igual.\n")
    if any(row["ticket"] == ticket for row in current):
        print(f"✔ El foco ya está en {ticket}")
        return
    with conn:
        conn.execute("UPDATE session_marks SET ended_at = ? WHERE session_id = ? AND ended_at IS NULL", (iso, session_id))
        conn.execute("INSERT INTO session_marks (session_id, agent, ticket, started_at) VALUES (?,?,?,?)", (session_id, agent, ticket, iso))
    previous = f" (antes {current[0]['ticket']})" if current else ""
    print(f"✔ Foco en {ticket}{previous} · sesión {session_id} ({agent})")


# ------------------------------------------------------------------------------
# Relevo (Handoff Snapshot): la herramienta solo junta hechos de git local; el criterio lo pone quien trabajó
# ------------------------------------------------------------------------------

PLACEHOLDER = "[COMPLETAR]"

class HandoffError(Exception):
    pass

def reject_placeholders(text):
    """Un texto con marcadores sin completar (fuera del bloque oculto) nunca se publica."""
    if PLACEHOLDER in re.sub(r"<!--[\s\S]*?-->", "", text or ""):
        sys.stderr.write(f"Error: el texto aún tiene marcadores {PLACEHOLDER}; complétalos antes de publicar.\n")
        sys.exit(1)

def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=15)

def sanitize_remote(url):
    """'owner/repo' de un remoto ssh o https de GitHub, sin credenciales; None si no se reconoce."""
    url = (url or "").strip()
    match = re.match(r"^(?:ssh://)?git@github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url)
    if not match:
        parsed = urllib.parse.urlparse(url)
        match = re.match(r"^/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", parsed.path) if parsed.hostname == "github.com" else None
    return f"{match.group(1)}/{match.group(2)}" if match else None

def handoff_facts(base=None):
    """Hechos del repo del directorio actual (solo git local, sin red). Lanza HandoffError si el relevo no sería útil."""
    if _git("rev-parse", "--show-toplevel").returncode != 0:
        raise HandoffError("No estás dentro de un repositorio git.")
    branch = _git("symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    if not branch:
        raise HandoffError("HEAD desacoplado: cambia a una rama antes del relevo.")
    sha = _git("rev-parse", "HEAD").stdout.strip()
    remotes = _git("remote").stdout.split()
    if not remotes:
        raise HandoffError("El repositorio no tiene remoto: otra persona no podría retomar el trabajo.")
    unpushed = int(_git("rev-list", "--count", "HEAD", "--not", "--remotes").stdout.strip() or 0)
    if unpushed:
        raise HandoffError(f"{unpushed} commit(s) sin pushear (según el último fetch local); haz push antes del relevo.")
    containing = [r for r in _git("for-each-ref", "--contains", "HEAD", "refs/remotes", "--format=%(refname:short)").stdout.split() if not r.endswith("/HEAD")]
    preferred = [r for r in containing if r.endswith("/" + branch)]
    where = (preferred or containing or ["?"])[0]
    remote_name = "origin" if "origin" in remotes else remotes[0]
    repo = sanitize_remote(_git("remote", "get-url", remote_name).stdout)
    dirty = len([line for line in _git("status", "--porcelain").stdout.splitlines() if line.strip()])
    facts = {"branch": branch.replace("`", ""), "sha": sha, "where": where.replace("`", ""), "repo": repo, "dirty": dirty,
             "base": None, "ahead_of_base": None}
    if base:
        if not re.match(r"^[A-Za-z0-9._/-]+$", base) or base.startswith("-"):
            raise HandoffError(f"Nombre de base inválido: {base!r}.")
        if _git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{base}").returncode != 0:
            raise HandoffError(f"No existe origin/{base} localmente (¿falta un fetch?).")
        facts["base"] = base
        facts["ahead_of_base"] = int(_git("rev-list", "--count", f"origin/{base}..HEAD").stdout.strip() or 0)
    return facts

def format_handoff(facts):
    lines = [
        "### 🔄 Relevo de Tarea (Handoff Snapshot)",
        f"- **Avance realizado:** {PLACEHOLDER}",
        f"- **Rama Git / Commit:** `{facts['branch']}` @ `{facts['sha']}` (en {facts['where']}, según el último fetch local)",
    ]
    detail = [f"Repo: {facts['repo'] or 'remoto no reconocido'}"]
    if facts["base"]:
        detail.append(f"Base: {facts['base']} ({facts['ahead_of_base']} commit(s) sobre origin/{facts['base']})")
    detail.append("working tree limpio" if not facts["dirty"] else f"⚠ {facts['dirty']} archivo(s) sin commitear")
    lines.append("  " + " · ".join(detail))
    lines += [f"- **Estado actual:** {PLACEHOLDER}", f"- **Stoppers / Próximo paso:** {PLACEHOLDER}"]
    return "\n".join(lines)

def cmd_handoff(args, conn, base_url, api_key, workspace, default_project_id):
    """Imprime el borrador del relevo (no publica). Avance, estado y próximos pasos los completa quien trabajó."""
    try:
        facts = handoff_facts(getattr(args, "base", None))
    except HandoffError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        sys.exit(1)
    print(format_handoff(facts))
    ticket = args.issue or detect_ticket_from_git() or "<TICKET>"
    sys.stderr.write(f"\nCompleta los {PLACEHOLDER}, guarda el texto en un archivo y publícalo con:\n"
                     f"  plane-tracker comment {ticket} -f relevo.md --duration <min>   (o --accept-proposal)\n")

# ------------------------------------------------------------------------------
# Consistencia entre la caché local y los comentarios de Plane (report --check)
# ------------------------------------------------------------------------------

CHECK_FIELDS = ("date", "start_time", "end_time", "duration_minutes", "track", "capacity_bucket", "worker_type")
CHECK_ERRORS = ("duplicate", "orphan", "mismatch", "missing_local")

def check_worklogs(local_rows, comments, s_str, e_str):
    """Compara filas locales con sus comentarios. comments: {id: {'meta': dict|None, 'has_block': bool}}."""
    issues = []
    by_cid = {}
    for row in local_rows:
        cid = row.get("plane_comment_id")
        if not cid:
            issues.append({"code": "unlinked", "ticket": row["ticket_id"], "comment_id": None, "detail": f"{row['date']} {row['start_time']} sin comentario asociado"})
            continue
        by_cid.setdefault(cid, []).append(row)
    for cid, rows in by_cid.items():
        ticket = rows[0]["ticket_id"]
        if len(rows) > 1:
            issues.append({"code": "duplicate", "ticket": ticket, "comment_id": cid, "detail": f"{len(rows)} filas locales para el mismo comentario"})
        comment = comments.get(cid)
        if comment is None:
            issues.append({"code": "orphan", "ticket": ticket, "comment_id": cid, "detail": "el comentario ya no existe en Plane"})
            continue
        if not comment["has_block"]:
            issues.append({"code": "no_block", "ticket": ticket, "comment_id": cid, "detail": "el comentario no lleva telemetría: no se reconstruiría con --sync"})
            continue
        for row in rows:
            diffs = [f"{f}: local {row.get(f)!r} ≠ Plane {comment['meta'].get(f)!r}" for f in CHECK_FIELDS
                     if comment["meta"].get(f) is not None and str(comment["meta"].get(f)) != str(row.get(f))]
            if diffs:
                issues.append({"code": "mismatch", "ticket": ticket, "comment_id": cid, "detail": "; ".join(diffs)})
    tickets = {r["ticket_id"] for r in local_rows}
    for cid, comment in comments.items():
        meta = comment.get("meta") or {}
        if comment["has_block"] and cid not in by_cid and meta.get("duration_minutes") and s_str <= str(meta.get("date", "")) <= e_str:
            issues.append({"code": "missing_local", "ticket": next(iter(tickets), "?"), "comment_id": cid,
                           "detail": f"comentario con telemetría ({meta.get('date')} {meta.get('start_time')}, {meta.get('duration_minutes')} min) sin fila local; usa report --sync"})
    return issues

def cmd_report_check(args, conn, base_url, api_key, workspace, default_project_id, s_str, e_str):
    """Solo lectura: detecta duplicados, huérfanos, diferencias y filas sin telemetría en el periodo."""
    proj = getattr(args, "project", None)
    like = f"{proj.upper()}-%" if proj else "%"
    rows = [dict(r) for r in conn.execute("SELECT * FROM worklogs WHERE date >= ? AND date <= ? AND ticket_id LIKE ? ORDER BY ticket_id, date, start_time",
                                          (s_str, e_str, like))]
    by_ticket = {}
    for r in rows:
        by_ticket.setdefault(r["ticket_id"], []).append(r)
    results, issues = {}, []
    for label, t_rows in sorted(by_ticket.items()):
        try:
            project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, label)
            issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
            c_url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
            raw = api_request(c_url, api_key, raise_on_error=True).get("results", [])
        except (SystemExit, urllib.error.URLError, OSError):
            issues.append({"code": "unreachable", "ticket": label, "comment_id": None, "detail": "no se pudo consultar el ticket en Plane"})
            continue
        comments = {}
        for c in raw:
            html = c.get("comment_html") or ""
            has_block = bool(find_metadata_block(html))
            comments[c["id"]] = {"has_block": has_block, "meta": extract_metadata_from_comment(html) if has_block else None}
        found = check_worklogs(t_rows, comments, s_str, e_str)
        results[label] = (len(t_rows), found)
        issues += found
    errors = [i for i in issues if i["code"] in CHECK_ERRORS]
    if getattr(args, "json", False):
        print(json.dumps({"period": [s_str, e_str], "issues": issues, "ok": not errors}, indent=2, ensure_ascii=False))
    else:
        print(f"\n🔎 Consistencia worklogs ↔ comentarios · {s_str} → {e_str}")
        if not by_ticket:
            print("   (no hay worklogs locales en el periodo)")
        for label, (count, found) in results.items():
            print(f"   {'✔' if not [i for i in found if i['code'] in CHECK_ERRORS] else '✖'} {label}: {count} worklog(s)")
            for i in found:
                print(f"      [{i['code']}] {i['detail']}" + (f"  ({i['comment_id'][:8]})" if i["comment_id"] else ""))
        for i in issues:
            if i["code"] == "unreachable":
                print(f"   ? {i['ticket']}: {i['detail']}")
        print(f"\n   Resumen: {len(errors)} inconsistencia(s), {len(issues) - len(errors)} aviso(s). Solo lectura: corrige con comment-edit o report --sync.\n")
    sys.exit(1 if errors else 0)


def cmd_get(args, conn, base_url, api_key, workspace, default_project_id):
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    args.issue = issue_ref
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)

    # Obtener comentarios del ticket para análisis de contexto y handoff
    comments = []
    skip_comments = getattr(args, "no_comments", False)
    if not skip_comments:
        try:
            url_c = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
            comments_data = api_request(url_c, api_key)
            comments = comments_data.get("results", [])
        except Exception:
            pass

    total_comments = len(comments)
    last = getattr(args, "last", None)
    if last:
        comments = comments[-last:]
    first_idx = total_comments - len(comments) + 1
    limit = None if getattr(args, "full", False) else 300

    get_states_map(conn, base_url, api_key, workspace, project_id)
    state_row = conn.execute("SELECT name FROM states WHERE id = ?", (issue.get("state"),)).fetchone()
    state_name = state_row["name"] if state_row else "?"

    flow = transitions = flow_states = None
    if getattr(args, "history", False):
        flow, transitions, flow_states = build_ticket_flow(conn, base_url, api_key, workspace, project_id, issue, issue_ref)

    if getattr(args, "json", False):
        issue_copy = dict(issue)
        if flow:
            issue_copy["flow"] = flow_to_json(flow)
        issue_copy["comments"] = comments
        issue_copy["comments_skipped"] = skip_comments
        issue_copy["total_comments"] = None if skip_comments else total_comments
        issue_copy["state_name"] = None if state_name == "?" else state_name
        if getattr(args, "no_description", False):
            issue_copy.pop("description_html", None)
            issue_copy.pop("description", None)
        print(json.dumps(issue_copy, indent=2))
        return

    print(f"\n📌 {args.issue}: {issue.get('name')}")
    print(f"   • Estado    : {state_name}")
    print(f"   • Prioridad : {issue.get('priority', 'none').upper()}")
    print(f"   • Creado el : {(issue.get('created_at') or '?')[:10]}")
    if issue.get("start_date") or issue.get("target_date"):
        print(f"   • Plan      : {issue.get('start_date') or '—'} → {issue.get('target_date') or '—'}")
    print(f"   • {format_lifecycle(issue)}")
    print(f"   • UUID      : {issue.get('id')}")

    desc = "" if getattr(args, "no_description", False) else (issue.get("description_html") or "")
    clean_desc = re.sub(r"<[^>]+>", " ", desc).strip()
    if clean_desc:
        clean_desc = " ".join(clean_desc.split())
        if limit and len(clean_desc) > limit:
            clean_desc = clean_desc[: limit - 3] + "..."
        print(f"\n📄 Descripción:")
        print(f"   {clean_desc}")

    if flow:
        print_flow(flow, transitions, flow_states)

    if comments:
        shown = f"{len(comments)} de {total_comments}" if len(comments) < total_comments else str(total_comments)
        print(f"\n💬 Contexto de Relevo / Comentarios ({shown}):")
        for i, c in enumerate(comments, first_idx):
            c_html = c.get("comment_html") or ""
            # Remover bloques de metadata oculta
            text_only = re.sub(r"<!--[\s\S]*?-->", "", c_html)
            text_only = re.sub(r"<[^>]+>", " ", text_only).strip()
            text_only = " ".join(text_only.split())
            if limit and len(text_only) > limit:
                text_only = text_only[: limit - 3] + "..."
            created = c.get("created_at", "")[:16].replace("T", " ")
            print(f"   [{i}] ({created}): {text_only}")
    print("")

def cmd_list(args, conn, base_url, api_key, workspace, default_project_id):
    project_id = default_project_id
    if getattr(args, "project", None):
        projects_map = get_projects_map(conn, base_url, api_key, workspace)
        p_upper = args.project.upper()
        if p_upper in projects_map:
            project_id = projects_map[p_upper]["id"]
        else:
            sys.stderr.write(f"Error: Proyecto '{args.project}' no encontrado. Opciones: {', '.join(projects_map.keys())}\n")
            sys.exit(1)

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/?limit=50"
    data = api_request(url, api_key)
    results = data.get("results", [])

    if getattr(args, "json", False):
        print(json.dumps(results, indent=2))
    else:
        print(f"\n📋 Tickets recientes ({len(results)} obtenidos):")
        for iss in results[:15]:
            prio = f"[{iss.get('priority', 'none').upper()}]"
            seq = iss.get("sequence_id", "?")
            print(f"  • #{seq:<4} {prio:<9} {iss.get('name')[:65]}")
        print("")

def cmd_labels(args, conn, base_url, api_key, workspace, default_project_id):
    """Lista las etiquetas disponibles en un proyecto desde SQLite o Plane."""
    project_id = default_project_id
    project_ident = "OMNIFY"
    projects_map = get_projects_map(conn, base_url, api_key, workspace)

    if getattr(args, "project", None):
        p_upper = args.project.upper()
        if p_upper in projects_map:
            project_id = projects_map[p_upper]["id"]
            project_ident = p_upper
        else:
            sys.stderr.write(f"Error: Proyecto '{args.project}' no encontrado. Opciones: {', '.join(projects_map.keys())}\n")
            sys.exit(1)
    else:
        for k, v in projects_map.items():
            if v["id"] == project_id:
                project_ident = k
                break

    force_refresh = getattr(args, "refresh", False)
    get_labels_map(conn, base_url, api_key, workspace, project_id, force_refresh=force_refresh)

    rows = conn.execute("SELECT id, name, color FROM labels WHERE project_id = ? ORDER BY name ASC", (project_id,)).fetchall()

    if getattr(args, "json", False):
        print(json.dumps([{"id": r["id"], "name": r["name"], "color": r["color"]} for r in rows], indent=2))
        return

    print(f"\n🏷  Etiquetas disponibles para el proyecto {project_ident} ({len(rows)}):")
    for r in rows:
        color_str = f"({r['color']})" if r["color"] else ""
        print(f"  • {r['name']:<18} {color_str}")
    print(f"\n💡 Úsalas en: plane-tracker create ... --labels 'backend,bug'\n")

def cmd_projects(args, conn, base_url, api_key, workspace):
    """Lista los proyectos disponibles en Plane y cacheados dinámicamente en SQLite."""
    force_refresh = getattr(args, "refresh", False)
    projects_map = get_projects_map(conn, base_url, api_key, workspace, force_refresh=force_refresh)

    if getattr(args, "json", False):
        print(json.dumps(list(projects_map.values()), indent=2))
        return

    print(f"\n📂 Proyectos en el workspace '{workspace}':")
    for ident, data in sorted(projects_map.items()):
        print(f"  • {ident:<14} ➔  {data['name']}")
    print(f"\n💡 Proyecto principal por defecto: OMNIFY (ej: OMNIFY-175 o solo '175').")
    print(f"   Usa 'plane-tracker projects --refresh' para forzar sincronización con el servidor Plane.\n")

def sync_issues_cache(conn, base_url, api_key, workspace, project_id, project_ident, force_refresh=False):
    """Sincroniza issues del proyecto en SQLite para búsquedas instantáneas (< 2ms) con FTS5."""
    now = time.time()
    if not force_refresh:
        row = conn.execute("SELECT MAX(updated_at) as last_sync FROM issues_cache WHERE project_id = ?", (project_id,)).fetchone()
        if row and row["last_sync"] and (now - row["last_sync"]) < 1800:
            return

    states_map_by_id = {}
    try:
        url_states = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/states/"
        s_data = api_request(url_states, api_key)
        for s in s_data.get("results", []):
            states_map_by_id[s["id"]] = (s["name"], s.get("group", ""))
    except Exception:
        pass

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/?limit=100"
    data = api_request(url, api_key)
    results = data.get("results", [])

    with conn:
        conn.execute("DELETE FROM issues_cache WHERE project_id = ?", (project_id,))
        for iss in results:
            seq = iss.get("sequence_id")
            if not seq:
                continue
            t_id = f"{project_ident}-{seq}"
            s_info = states_map_by_id.get(iss.get("state"), ("Pendiente", "unstarted"))
            conn.execute("""
                INSERT INTO issues_cache (id, sequence_id, ticket_id, project_id, title, state_name, state_group, priority, labels_csv, updated_at,
                                          created_at, completed_at, start_date, target_date, archived_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (iss["id"], seq, t_id, project_id, iss.get("name", ""), s_info[0], s_info[1], iss.get("priority", "none"), "", now,
                  iss.get("created_at"), iss.get("completed_at"), iss.get("start_date"), iss.get("target_date"), iss.get("archived_at")))

        # Sincronizar tabla FTS5
        conn.execute("DELETE FROM issues_fts;")
        conn.execute("""
            INSERT INTO issues_fts (ticket_id, title, labels_csv)
            SELECT ticket_id, title, labels_csv FROM issues_cache;
        """)

def cmd_search(args, conn, base_url, api_key, workspace, default_project_id):
    """Búsqueda ultra-rápida FTS5 (< 2ms) en el Momento Cero para detectar tickets existentes."""
    project_id = default_project_id
    project_ident = "OMNIFY"
    projects_map = get_projects_map(conn, base_url, api_key, workspace)

    if getattr(args, "project", None):
        p_upper = args.project.upper()
        if p_upper in projects_map:
            project_id = projects_map[p_upper]["id"]
            project_ident = p_upper
        else:
            sys.stderr.write(f"Error: Proyecto '{args.project}' no encontrado.\n")
            sys.exit(1)
    else:
        for k, v in projects_map.items():
            if v["id"] == project_id:
                project_ident = k
                break

    force_refresh = getattr(args, "refresh", False)
    try:
        sync_issues_cache(conn, base_url, api_key, workspace, project_id, project_ident, force_refresh=force_refresh)
    except Exception as e:
        sys.stderr.write(f"⚠ Modo offline / advertencia de red: no se pudo sincronizar Plane ({e}). Consultando caché local SQLite.\n")

    raw_query = args.query.strip()
    matches = []

    # Fast-path si la consulta es un número o identificador directo (ej: "197" o "OMNIFY-197")
    seq_match = re.match(r"^(?:[A-Za-z]+-)?(\d+)$", raw_query)
    if seq_match:
        target_seq = int(seq_match.group(1))
        row = conn.execute("SELECT ticket_id, title, state_name, state_group, priority FROM issues_cache WHERE sequence_id = ? AND project_id = ?", (target_seq, project_id)).fetchone()
        if row:
            matches = [dict(row)]

    if not matches:
        stop_words = {"de", "del", "la", "las", "el", "los", "en", "un", "una", "unos", "unas", "por", "para", "con", "y", "o", "a", "al", "que", "se", "es"}
        tokens = [re.sub(r"[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]", "", t) for t in raw_query.split()]
        tokens = [t for t in tokens if t and t.lower() not in stop_words]

        if tokens:
            fts_query = " OR ".join(f'"{t}"*' for t in tokens)
            try:
                sql = """
                    SELECT c.ticket_id, c.title, c.state_name, c.state_group, c.priority
                    FROM issues_fts f
                    JOIN issues_cache c ON f.ticket_id = c.ticket_id
                    WHERE issues_fts MATCH ? AND c.project_id = ?
                    ORDER BY rank
                    LIMIT 5;
                """
                rows = conn.execute(sql, (fts_query, project_id)).fetchall()
                matches = [dict(r) for r in rows]
            except Exception:
                pass

    if not matches and tokens:
        like_clauses = " OR ".join("title LIKE ?" for _ in tokens[:3])
        params = [f"%{t}%" for t in tokens[:3]] + [project_id]
        sql = f"""
            SELECT ticket_id, title, state_name, state_group, priority
            FROM issues_cache
            WHERE ({like_clauses}) AND project_id = ?
            LIMIT 5;
        """
        try:
            rows = conn.execute(sql, params).fetchall()
            matches = [dict(r) for r in rows]
        except Exception:
            pass

    if getattr(args, "json", False):
        print(json.dumps({
            "query": raw_query,
            "project": project_ident,
            "count": len(matches),
            "results": matches
        }, indent=2))
        return

    if matches:
        print(f"\n🔍 Coincidencias encontradas en {project_ident} ({len(matches)}):")
        for m in matches:
            prio = f"[{m['priority'].upper()}]"
            state = f"({m['state_name']})"
            print(f"  • {m['ticket_id']:<12} {state:<14} {prio:<9} {m['title']}")
        print(f"\n💡 Para trabajar en uno existente: git checkout -b feat/{matches[0]['ticket_id']}-descripcion")
        print(f"   O crea uno nuevo si es diferente: plane-tracker create \"[FEAT] ...\"\n")
    else:
        print(f"\nℹ No se encontraron tickets similares a '{raw_query}' en {project_ident}.")
        print(f"💡 Es un requerimiento NUEVO. Créalo con: plane-tracker create \"[FEAT] {raw_query}\"\n")

# ------------------------------------------------------------------------------
# Generador de Reportes de Actividad en Formato Híbrido (cmd_report)
# ------------------------------------------------------------------------------

def format_minutes(m):
    h = m // 60
    mins = m % 60
    return f"{h}h {mins:02d}m"

def render_day_block(date_obj, rows):
    """Renderiza el bloque de un día usando Interval Merging de Klee."""
    dia_nombre = DIAS_SEMANA[date_obj.weekday()]
    d_str = date_obj.strftime("%d/%m/%Y")
    lines = []

    if not rows:
        return f"ℹ Sin registros de actividad para {dia_nombre} {d_str}.\n"

    merged_entries, wall_clock_mins, total_compute_mins = merge_daily_worklogs(expand_segments(rows))

    by_project = {}
    all_stoppers = []

    for e in merged_entries:
        lines.append(f"titulo: [{e['ticket_id']}] {e['issue_name']}")
        lines.append(f"inicio: {e['start_time']}")
        lines.append(f"fin: {e['end_time']}")
        lines.append(f"notas: {e['notes']}")
        lines.append("")

        pref = e["ticket_id"].split("-")[0] if "-" in e["ticket_id"] else "Otros"
        by_project[pref] = by_project.get(pref, 0) + e["wall_minutes"]
        for st in e["stoppers"]:
            if st and st not in all_stoppers:
                all_stoppers.append(st)

    proj_parts = [f"{k}: {format_minutes(v)}" for k, v in by_project.items()]
    proj_str = " | ".join(proj_parts) if proj_parts else "N/A"

    lines.append("-" * 80)
    lines.append(f"📊 Total día: {format_minutes(wall_clock_mins)} reloj activa ({proj_str})")
    
    if total_compute_mins > wall_clock_mins:
        leverage = round(total_compute_mins / wall_clock_mins, 2) if wall_clock_mins > 0 else 1.0
        lines.append(f"🚀 AI Leverage Multiplier: {leverage}x ({format_minutes(total_compute_mins)} de esfuerzo entregado en {format_minutes(wall_clock_mins)} reloj)")

    if all_stoppers:
        lines.append(f"⏸️ Standby externo: {', '.join(all_stoppers)}")
    else:
        lines.append("⏸️ Standby externo: 0h 00m (Sin bloqueos reportados)")

    return "\n".join(lines)

def cmd_report(args, conn, base_url, api_key, workspace, default_project_id):
    today = datetime.now().date()
    is_week = getattr(args, "week", False)
    custom_date = getattr(args, "date", None)
    force_sync = getattr(args, "sync", False)

    if is_week:
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif custom_date:
        try:
            target = datetime.strptime(custom_date, "%Y-%m-%d").date()
            start_date = target
            end_date = target
        except ValueError:
            sys.stderr.write(f"Error: Formato de fecha inválido '{custom_date}'. Usa YYYY-MM-DD.\n")
            sys.exit(1)
    else:
        start_date = today
        end_date = today

    s_str = start_date.strftime("%Y-%m-%d")
    e_str = end_date.strftime("%Y-%m-%d")

    if getattr(args, "check", False):
        return cmd_report_check(args, conn, base_url, api_key, workspace, default_project_id, s_str, e_str)
    if getattr(args, "flow", False):
        return cmd_report_flow(args, conn, base_url, api_key, workspace, default_project_id, s_str, e_str)

    # Verificar si necesitamos sincronizar remotamente
    sync_meta = conn.execute("SELECT updated_at FROM sync_metadata WHERE key = ?", (f"sync:{workspace}",)).fetchone()
    last_synced = sync_meta["updated_at"] if sync_meta else 0
    now = time.time()

    # Contar registros existentes en el rango
    count_row = conn.execute("SELECT COUNT(*) as cnt FROM worklogs WHERE date >= ? AND date <= ?", (s_str, e_str)).fetchone()
    has_entries = count_row["cnt"] > 0

    needs_sync = force_sync or (not has_entries and (now - last_synced > SYNC_COOLDOWN))
    if needs_sync:
        sync_remote_worklogs(conn, base_url, api_key, workspace, s_str, e_str, filter_project=getattr(args, "project", None))

    # Construir query SQL indexada con filtros opcionales
    query = "SELECT * FROM worklogs WHERE date >= ? AND date <= ?"
    params = [s_str, e_str]

    if getattr(args, "project", None):
        query += " AND project_id = ?"
        params.append(args.project.upper())

    if getattr(args, "track", None):
        query += " AND track = ?"
        params.append(args.track)

    if getattr(args, "worker_type", None):
        query += " AND worker_type = ?"
        params.append(args.worker_type)

    query += " ORDER BY date ASC, start_time ASC"
    rows = conn.execute(query, params).fetchall()

    if getattr(args, "json", False):
        result = [dict(r) for r in rows]
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # Renderizado en texto
    if is_week:
        num_semana = start_date.isocalendar()[1]
        print("=" * 80)
        print(f"📅 REPORTE SEMANAL - SEMANA {num_semana} ({start_date.strftime('%d/%m/%Y')} al {end_date.strftime('%d/%m/%Y')})")
        print("=" * 80 + "\n")

        all_week_intervals = []
        total_week_compute = 0
        week_by_project = {}
        all_week_stoppers = []

        cur = start_date
        limit_day = min(end_date, today)
        while cur <= limit_day:
            cur_s = cur.strftime("%Y-%m-%d")
            day_rows = [r for r in rows if r["date"] == cur_s]
            dia_nombre = DIAS_SEMANA[cur.weekday()]
            print(f"[{dia_nombre} {cur.strftime('%d/%m/%Y')}]")
            print(render_day_block(cur, day_rows))
            print("")

            for r in expand_segments(day_rows):
                s_m = time_to_minutes(r["start_time"])
                e_m = time_to_minutes(r["end_time"])
                dur = r["duration_minutes"]
                all_week_intervals.append((s_m, e_m))
                total_week_compute += dur
                pref = r["ticket_id"].split("-")[0] if "-" in r["ticket_id"] else "Otros"
                week_by_project[pref] = week_by_project.get(pref, 0) + dur
                try:
                    for st in json.loads(r["stoppers_json"]):
                        if st and st not in all_week_stoppers:
                            all_week_stoppers.append(st)
                except Exception:
                    pass

            cur += timedelta(days=1)

        week_wall_clock = calculate_klee_union_minutes(all_week_intervals)
        proj_parts = [f"{k}: {format_minutes(v)}" for k, v in week_by_project.items()]
        proj_str = " | ".join(proj_parts) if proj_parts else "N/A"

        print("=" * 80)
        print(f"🏆 TOTAL SEMANA: {format_minutes(week_wall_clock)} reloj activa ({proj_str})")
        if total_week_compute > week_wall_clock:
            leverage = round(total_week_compute / week_wall_clock, 2) if week_wall_clock > 0 else 1.0
            print(f"🚀 AI Leverage Multiplier: {leverage}x ({format_minutes(total_week_compute)} de esfuerzo total entregado)")
        if all_week_stoppers:
            print(f"⏸️ STANDBY TOTAL: {', '.join(all_week_stoppers)}")
        print("=" * 80 + "\n")

    else:
        target = start_date
        dia_nombre = DIAS_SEMANA[target.weekday()]
        print("=" * 80)
        print(f"📋 REPORTE DE ACTIVIDAD - {dia_nombre.upper()} {target.strftime('%d/%m/%Y')}")
        print("=" * 80 + "\n")
        print(render_day_block(target, rows))
        print("\n" + "=" * 80)

# ------------------------------------------------------------------------------
# Comando: whoami — Verificación de setup inicial
# ------------------------------------------------------------------------------

def cmd_whoami(conn, base_url, api_key, workspace):
    """Muestra la configuración activa y verifica que el usuario esté resuelto en Plane."""
    print(f"🌐 PLANE_BASE_URL  : {base_url}")
    print(f"🏢 PLANE_WORKSPACE : {workspace}")

    plane_username = os.environ.get("PLANE_USERNAME", "")
    actor_uuid_env = os.environ.get("PLANE_ACTOR_UUID", "")

    if actor_uuid_env:
        print(f"🔑 PLANE_ACTOR_UUID: {actor_uuid_env} (configurado directamente)")
        resolved = actor_uuid_env
    elif plane_username:
        print(f"👤 PLANE_USERNAME  : {plane_username} (resolviendo UUID...)")
        resolved = get_actor_uuid(base_url, api_key, workspace)
        if resolved:
            print(f"✅ UUID resuelto   : {resolved}")
            print(f"\n💡 Tip: para acelerar futuros syncs, agrega a ~/.zshrc.local:")
            print(f"   export PLANE_ACTOR_UUID=\"{resolved}\"")
        else:
            print(f"❌ No se pudo resolver el UUID para PLANE_USERNAME='{plane_username}'")
            print("   Verifica que el nombre o email coincida exactamente con tu perfil en Plane.")
            sys.exit(1)
    else:
        print("⚠️  Ni PLANE_USERNAME ni PLANE_ACTOR_UUID están configurados.")
        print("   El sync funcionará pero mezclará horas de todos los autores en tickets compartidos.")
        print("\n📋 Setup requerido en ~/.zshrc.local:")
        print("   export PLANE_USERNAME=\"tu@email.com\"  # o tu display_name en Plane")
        print("   # Opcional (más robusto):")
        print("   export PLANE_ACTOR_UUID=\"xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx\"")
        resolved = None

    if resolved:
        print(f"\n✅ Configuración válida. Puedes usar plane-tracker normalmente.")

# ------------------------------------------------------------------------------
# Entrypoint CLI
# ------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CLI de Plane CE para Agentes de IA y Reportes de Actividad (v2.3 SQLite3)")
    parser.add_argument("--json", action="store_true", help="Salida en formato JSON para agentes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # comment
    p_comment = subparsers.add_parser("comment", help="Publicar comentario en un ticket")
    p_comment.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    p_comment.add_argument("-m", "--message", help="Mensaje del comentario")
    p_comment.add_argument("-f", "--file", help="Archivo con el contenido")
    p_comment.add_argument("--track", help="Frente de trabajo (ej: main, subagent, review, datepicker)")
    p_comment.add_argument("--capacity", "--capacity-bucket", dest="capacity_bucket",
                           choices=["deep_work", "toil_support", "coordination", "tooling_dx", "research_rd", "tech_debt_paydown"],
                           help="Balde de capacidad de la sesión")
    p_comment.add_argument("--worker-type", choices=["human", "subagent", "agent:agy", "agent:claude", "agent:opencode"], help="Tipo de ejecutor")
    p_comment.add_argument("--duration", type=int, metavar="MIN",
                           help="Duración neta de la sesión en minutos (requerido si el contenido no lleva metadata telemétrica). Ej: --duration 5")
    p_comment.add_argument("--accept-proposal", action="store_true",
                           help="Registrar la duración propuesta (solo vale si se mostró hace menos de 30 min para este ticket)")
    p_comment.add_argument("--agent", choices=list(session_clock.AGENTS), help="Agente cuya sesión se mide (por defecto: según --worker-type o el entorno)")
    p_comment.add_argument("--session", metavar="ID", help="ID de la sesión del agente (por defecto: variable de entorno o directorio de trabajo)")
    p_comment.add_argument("--json", action="store_true", help="Salida en JSON")

    # link
    p_link = subparsers.add_parser("link", help="Adjuntar un enlace (PR, doc) al work item")
    p_link.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-205)")
    p_link.add_argument("url", help="URL del enlace (https://...)")
    p_link.add_argument("--title", help="Texto visible del enlace (por defecto: la URL)")

    # attach / attachments
    p_attach = subparsers.add_parser("attach", help="Subir archivos al work item")
    p_attach.add_argument("issue", help="Ticket (ej: OMNIFY-205)")
    p_attach.add_argument("files", nargs="+", help="Archivo(s) a adjuntar (máx. 50 MB cada uno)")
    p_attach.add_argument("--replace", metavar="ID", help="Id de un adjunto a sustituir: sube el nuevo y, si salió bien, borra el anterior")
    p_attachments = subparsers.add_parser("attachments", help="Listar los adjuntos del work item")
    p_attachments.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-205)")
    p_attachments.add_argument("--json", action="store_true", help="Salida en JSON")
    p_attachments.add_argument("--delete", metavar="ID", help="Eliminar el adjunto con ese id")

    # health
    p_health = subparsers.add_parser("health", help="Latencia y errores recientes de la API de Plane")
    p_health.add_argument("--hours", type=positive_int, default=24, help="Ventana en horas (por defecto 24)")
    p_health.add_argument("--json", action="store_true", help="Salida en JSON")

    # handoff
    p_handoff = subparsers.add_parser("handoff", help="Imprimir el borrador del relevo (Handoff Snapshot) con los hechos de git del directorio actual")
    p_handoff.add_argument("issue", nargs="?", default=None, help="Ticket (solo para la sugerencia de publicación)")
    p_handoff.add_argument("--base", metavar="BRANCH", help="Rama base para contar 'N commits sobre origin/BRANCH' (nunca se asume)")

    # focus
    p_focus = subparsers.add_parser("focus", help="Marcar en qué ticket trabaja esta sesión (reparte el tiempo medido por ticket)")
    p_focus.add_argument("issue", nargs="?", default=None, help="Ticket en el que empiezas a trabajar")
    p_focus.add_argument("--off", action="store_true", help="Cerrar la marca de foco actual")
    p_focus.add_argument("--status", action="store_true", help="Ver el tiempo atribuido hoy a cada ticket")
    p_focus.add_argument("--agent", choices=list(session_clock.AGENTS), help="Agente de la sesión (por defecto: según el entorno)")
    p_focus.add_argument("--session", metavar="ID", help="ID de la sesión del agente")
    p_focus.add_argument("--json", action="store_true", help="Salida en JSON")

    # propose-duration
    p_prop = subparsers.add_parser("propose-duration", help="Medir la sesión del agente y proponer una duración (no registra nada)")
    p_prop.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    p_prop.add_argument("--agent", choices=list(session_clock.AGENTS), help="Agente cuya sesión se mide")
    p_prop.add_argument("--session", metavar="ID", help="ID de la sesión del agente")
    p_prop.add_argument("--worker-type", choices=["human", "subagent", "agent:agy", "agent:claude", "agent:opencode"], help="Tipo de ejecutor")
    p_prop.add_argument("--capacity", "--capacity-bucket", dest="capacity_bucket",
                        choices=["deep_work", "toil_support", "coordination", "tooling_dx", "research_rd", "tech_debt_paydown"],
                        help="Balde de capacidad (toil_support y coordination no admiten propuesta)")
    p_prop.add_argument("--split", metavar="SPEC", help="Repartir lo medido entre tickets: 'A=60%%,B=rest' o 'A=40m,B=rest' (ignora las marcas de foco)")
    p_prop.add_argument("--date", metavar="YYYY-MM-DD", help="Día a medir (por defecto hoy): para sesiones de días anteriores")
    p_prop.add_argument("--since", metavar="HH:MM|ISO", help="Inicio de la ventana medida (hora local del día medido)")
    p_prop.add_argument("--until", metavar="HH:MM|ISO", help="Fin de la ventana medida (hora local del día medido)")
    p_prop.add_argument("--json", action="store_true", help="Salida en JSON")

    # create
    p_create = subparsers.add_parser("create", help="Crear un nuevo ticket / work item en Plane")
    p_create.add_argument("title", help="Título del ticket")
    p_create.add_argument("-d", "--description", help="Descripción o notas del ticket")
    p_create.add_argument("-p", "--project", help="Identificador del proyecto (por defecto OMNIFY)")
    p_create.add_argument("--priority", choices=["urgent", "high", "medium", "low", "none"], default="none", help="Prioridad del ticket")
    p_create.add_argument("--state", help="Estado inicial (por defecto Backlog)")
    p_create.add_argument("--labels", help="Etiquetas separadas por comas (ej: backend,bug,spike)")
    p_create.add_argument("--start-date", help="Fecha de inicio YYYY-MM-DD")
    p_create.add_argument("--due-date", help="Fecha de vencimiento YYYY-MM-DD")
    p_create.add_argument("--attach", nargs="+", metavar="FILE", help="Archivo(s) a adjuntar al crear el ticket (máx. 50 MB cada uno)")
    p_create.add_argument("--json", action="store_true", help="Salida en JSON")

    # comment-delete / comment-edit
    p_cdel = subparsers.add_parser("comment-delete", help="Eliminar un comentario (por defecto el último propio) y su worklog local")
    p_cdel.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OPS-13)")
    p_cdel.add_argument("--comment-id", help="UUID del comentario (por defecto: último comentario propio)")
    p_cedit = subparsers.add_parser("comment-edit", help="Editar un comentario y/o vincularle su worklog local sin publicar otro")
    p_cedit.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OPS-13)")
    p_cedit.add_argument("--comment-id", help="UUID del comentario (por defecto: último comentario propio)")
    p_cedit.add_argument("-m", "--message", help="Nuevo texto del comentario")
    p_cedit.add_argument("--track", help="Frente de trabajo")
    p_cedit.add_argument("--capacity", "--capacity-bucket", dest="capacity_bucket",
                         choices=["deep_work", "toil_support", "coordination", "tooling_dx", "research_rd", "tech_debt_paydown"])
    p_cedit.add_argument("--worker-type", choices=["human", "subagent", "agent:agy", "agent:claude", "agent:opencode"])
    p_cedit.add_argument("--duration", type=int, metavar="MIN", help="Duración en minutos: registra el worklog usando la hora de publicación como fin")
    p_cedit.add_argument("--embed-metadata", action="store_true", help="Añadir al comentario el bloque oculto de metadata de su worklog local (sin cambiar el texto visible)")
    p_cedit.add_argument("--force", action="store_true", help="Con --duration: descartar los tramos medidos del worklog cuando la nueva duración no coincide")

    # update
    p_update = subparsers.add_parser("update", help="Actualizar estado, prioridad o etiquetas de un ticket")
    p_update.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    p_update.add_argument("--state", help="Nuevo estado: Backlog, Pendiente, Progreso, Pruebas, Revisión, Completado, Pausado, Cancelado")
    p_update.add_argument("--priority", help="Prioridad: urgent, high, medium, low, none")
    p_update.add_argument("--labels", help="Etiquetas separadas por comas (ej: sms,backend,bug)")
    p_update.add_argument("--start-date", help="Fecha de inicio YYYY-MM-DD")
    p_update.add_argument("--due-date", help="Fecha de vencimiento YYYY-MM-DD")
    p_update.add_argument("--json", action="store_true", help="Salida en JSON")

    # get
    p_get = subparsers.add_parser("get", help="Obtener detalles de un ticket")
    p_get.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    p_get.add_argument("--json", action="store_true", help="Salida en JSON")
    p_get.add_argument("--no-comments", action="store_true", help="No traer ni mostrar comentarios (ahorra tokens)")
    p_get.add_argument("--last", type=positive_int, metavar="N", help="Mostrar solo los últimos N comentarios (por defecto: todos)")
    p_get.add_argument("--full", action="store_true", help="Sin truncar descripción ni comentarios (por defecto 300 caracteres)")
    p_get.add_argument("--no-description", action="store_true", help="Omitir la descripción")
    p_get.add_argument("--history", action="store_true", help="Añadir flujo: lead/cycle time, tiempo por estado, esfuerzo y transiciones")

    # list
    p_list = subparsers.add_parser("list", help="Listar tickets del proyecto")
    p_list.add_argument("-p", "--project", help="Identificador del proyecto (ej: OMNIFY, OPS, OMNILEADS)")
    p_list.add_argument("--json", action="store_true", help="Salida en JSON")

    # search
    p_search = subparsers.add_parser("search", help="Búsqueda ultra-rápida FTS5 (< 2ms) de tickets en Momento Cero")
    p_search.add_argument("query", help="Texto de búsqueda (ej: 'validaciones formulario', 'webhook sms')")
    p_search.add_argument("-p", "--project", help="Identificador del proyecto (por defecto OMNIFY)")
    p_search.add_argument("--refresh", action="store_true", help="Forzar sincronización remota con Plane")
    p_search.add_argument("--json", action="store_true", help="Salida en JSON")

    # labels
    p_labels = subparsers.add_parser("labels", help="Listar etiquetas disponibles en un proyecto cacheadas en SQLite")
    p_labels.add_argument("-p", "--project", help="Identificador del proyecto (por defecto OMNIFY)")
    p_labels.add_argument("--refresh", action="store_true", help="Forzar sincronización remota con la API de Plane")
    p_labels.add_argument("--json", action="store_true", help="Salida en JSON")

    # projects
    p_proj = subparsers.add_parser("projects", help="Listar proyectos disponibles en Plane cacheados en SQLite")
    p_proj.add_argument("--refresh", action="store_true", help="Forzar sincronización remota con la API de Plane")
    p_proj.add_argument("--json", action="store_true", help="Salida en JSON")

    # whoami
    subparsers.add_parser("whoami", help="Verificar configuración activa: muestra workspace, usuario y UUID resuelto")

    # report
    p_report = subparsers.add_parser("report", help="Generar reporte de actividades en formato híbrido con Interval Merging")
    group_date = p_report.add_mutually_exclusive_group()
    group_date.add_argument("--today", action="store_true", help="Reporte del día actual (por defecto)")
    group_date.add_argument("--week", action="store_true", help="Reporte de la semana actual")
    group_date.add_argument("--date", help="Reporte de fecha específica (YYYY-MM-DD)")
    p_report.add_argument("-p", "--project", help="Filtrar por proyecto (ej: OMNIFY, OPS)")
    p_report.add_argument("--track", help="Filtrar por track (ej: main, subagent)")
    p_report.add_argument("--worker-type", help="Filtrar por tipo de trabajador (human, subagent)")
    p_report.add_argument("--sync", action="store_true", help="Forzar sincronización remota con Plane")
    p_report.add_argument("--check", action="store_true", help="Solo lectura: compara los worklogs locales con sus comentarios en Plane (duplicados, huérfanos, diferencias)")
    p_report.add_argument("--flow", action="store_true", help="Flujo por ticket del periodo: lead/cycle time, tiempo por estado y esfuerzo")
    p_report.add_argument("--json", action="store_true", help="Salida en formato JSON")

    args = parser.parse_args()

    base_url = get_env_or_fail("PLANE_BASE_URL", "URL de Plane")
    api_key = get_env_or_fail("PLANE_API_KEY", "API Key de Plane")
    workspace = os.environ.get("PLANE_WORKSPACE_SLUG", "teamprogra")
    default_project_id = os.environ.get("PLANE_PROJECT_ID", "58371da4-cf62-4299-8fd4-99c1052b2eb3")

    conn = get_db()
    init_db(conn)

    try:
        if args.command == "comment":
            cmd_comment(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "attach":
            cmd_attach(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "attachments":
            cmd_attachments(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "health":
            cmd_health(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "handoff":
            cmd_handoff(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "focus":
            cmd_focus(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "link":
            cmd_link(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "propose-duration":
            cmd_propose_duration(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "comment-delete":
            cmd_comment_delete(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "comment-edit":
            cmd_comment_edit(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "create":
            cmd_create(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "update":
            cmd_update(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "get":
            cmd_get(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "list":
            cmd_list(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "search":
            cmd_search(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "labels":
            cmd_labels(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "projects":
            cmd_projects(args, conn, base_url, api_key, workspace)
        elif args.command == "report":
            cmd_report(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "whoami":
            cmd_whoami(conn, base_url, api_key, workspace)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
