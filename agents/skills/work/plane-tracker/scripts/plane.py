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
from datetime import datetime, timedelta, date
from concurrent.futures import ThreadPoolExecutor, as_completed

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


CACHE_DIR = os.path.expanduser("~/.cache/plane")
DB_FILE = os.path.join(CACHE_DIR, "worklogs.db")
PROJECTS_TTL = 86400  # 24 horas
SYNC_COOLDOWN = 300   # 5 minutos

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# ------------------------------------------------------------------------------
# Conexión y Gestión de Base de Datos SQLite3 (WAL Mode)
# ------------------------------------------------------------------------------

def get_db():
    """Retorna una conexión a SQLite3 con WAL mode y timeout defensivo."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

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

def load_zshrc_local_if_needed():
    """Carga variables desde ~/.zshrc.local si no están en el entorno."""
    local_env = os.path.expanduser("~/.zshrc.local")
    if os.path.isfile(local_env):
        try:
            with open(local_env, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("export "):
                        line = line[7:].strip()
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k not in os.environ and v:
                                os.environ[k] = v
        except Exception:
            pass

def get_env_or_fail(var_name, description):
    load_zshrc_local_if_needed()
    val = os.environ.get(var_name)
    if not val:
        sys.stderr.write(f"Error: Variable de entorno '{var_name}' ({description}) no configurada.\n")
        sys.stderr.write("Defínela en ~/.zshrc.local o en tu entorno antes de ejecutar este script.\n")
        sys.exit(1)
    return val

def api_request(url, api_key, method="GET", data=None, timeout=10, max_retries=3, raise_on_error=False):
    """Ejecuta peticiones HTTP a la API de Plane con tolerancia a 429 (Rate Limit)."""
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 204:
                    return {}
                content = resp.read().decode("utf-8")
                return json.loads(content) if content else {}
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                retry_after = int(e.headers.get("Retry-After", 1))
                time.sleep(retry_after + 0.5)
                continue
            if raise_on_error:
                raise e
            err_msg = e.read().decode("utf-8")
            sys.stderr.write(f"Error HTTP {e.code} en {url}: {err_msg}\n")
            sys.exit(1)
        except urllib.error.URLError as e:
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

    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)

    # --- Duración explícita (NUNCA estimar por defecto) ---------------------------------
    # Se valida ANTES de publicar: no puede quedar un comentario en Plane sin su worklog.
    # Fuentes válidas: metadata dual-layer (duration_minutes / duration_net_minutes) o --duration N.
    meta = extract_metadata_from_comment(content)
    meta_duration = None
    if meta:
        meta_duration = meta.get("duration_minutes") or meta.get("duration_net_minutes")
    duration = getattr(args, "duration", None) or meta_duration

    if not duration:
        sys.stderr.write("Error: Falta la duración de la sesión y no se puede estimar.\n")
        sys.stderr.write("Usa --duration <minutos> (ej: --duration 5) o incluye el bloque PLANE_WORKLOG_METADATA\n")
        sys.stderr.write("con 'duration_minutes' en el contenido.\n")
        sys.stderr.write("Si el trabajo ocurrió fuera de la conversación, el agente debe preguntar cuánto demoró; no inferir ni inventar.\n")
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
    res = api_request(url, api_key, method="POST", data={"comment_html": comment_html})

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
            "start_time": (now - timedelta(minutes=duration)).strftime("%H:%M"),
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
            meta["start_time"] = (end_t - timedelta(minutes=duration)).strftime("%H:%M")

    entry = {
        "id": res.get("id"),
        "ticket_id": ticket_label,
        "track": track,
        "issue_name": issue.get("name", ""),
        "date": meta.get("date", now.strftime("%Y-%m-%d")),
        "start_time": meta.get("start_time", (now - timedelta(minutes=duration)).strftime("%H:%M")),
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
    upsert_worklog(conn, entry)

    if getattr(args, "json", False):
        print(json.dumps({"status": "ok", "action": "comment", "issue_id": issue["id"], "sequence_id": issue.get("sequence_id"), "comment_id": res.get("id")}))
    else:
        print(f"✔ Comentario publicado exitosamente en {args.issue} (ID Comentario: {res.get('id')})")

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

    if not patch_data:
        sys.stderr.write("Advertencia: No se indicaron cambios para actualizar (--state, --priority o --labels).\n")
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

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/"
    res = api_request(url, api_key, method="POST", data=payload)

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
            "raw": res
        }, indent=2))
    else:
        print(f"\n🎉 Ticket creado exitosamente: {ticket_ref}")
        print(f"   • Título: {res.get('name')}")
        print(f"   • Prioridad: {res.get('priority', 'none').upper()}")
        print(f"   • Enlace: {web_url}")
        print(f"   • Sugerencia de rama Git: {branch_sugg}\n")

def cmd_get(args, conn, base_url, api_key, workspace, default_project_id):
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    args.issue = issue_ref
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)

    # Obtener comentarios del ticket para análisis de contexto y handoff
    comments = []
    try:
        url_c = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
        comments_data = api_request(url_c, api_key)
        comments = comments_data.get("results", [])
    except Exception:
        pass

    if getattr(args, "json", False):
        issue_copy = dict(issue)
        issue_copy["comments"] = comments
        print(json.dumps(issue_copy, indent=2))
        return

    print(f"\n📌 {args.issue}: {issue.get('name')}")
    print(f"   • Prioridad : {issue.get('priority', 'none').upper()}")
    print(f"   • Creado el : {issue.get('created_at')[:10]}")
    print(f"   • UUID      : {issue.get('id')}")

    desc = issue.get("description_html") or ""
    clean_desc = re.sub(r"<[^>]+>", " ", desc).strip()
    if clean_desc:
        clean_desc = " ".join(clean_desc.split())
        if len(clean_desc) > 300:
            clean_desc = clean_desc[:297] + "..."
        print(f"\n📄 Descripción:")
        print(f"   {clean_desc}")

    if comments:
        print(f"\n💬 Contexto de Relevo / Comentarios ({len(comments)}):")
        for i, c in enumerate(comments, 1):
            c_html = c.get("comment_html") or ""
            # Remover bloques de metadata oculta
            text_only = re.sub(r"<!--[\s\S]*?-->", "", c_html)
            text_only = re.sub(r"<[^>]+>", " ", text_only).strip()
            text_only = " ".join(text_only.split())
            if len(text_only) > 300:
                text_only = text_only[:297] + "..."
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
                INSERT INTO issues_cache (id, sequence_id, ticket_id, project_id, title, state_name, state_group, priority, labels_csv, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (iss["id"], seq, t_id, project_id, iss.get("name", ""), s_info[0], s_info[1], iss.get("priority", "none"), "", now))

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

    merged_entries, wall_clock_mins, total_compute_mins = merge_daily_worklogs(rows)

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

            for r in day_rows:
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
    p_comment.add_argument("--json", action="store_true", help="Salida en JSON")

    # create
    p_create = subparsers.add_parser("create", help="Crear un nuevo ticket / work item en Plane")
    p_create.add_argument("title", help="Título del ticket")
    p_create.add_argument("-d", "--description", help="Descripción o notas del ticket")
    p_create.add_argument("-p", "--project", help="Identificador del proyecto (por defecto OMNIFY)")
    p_create.add_argument("--priority", choices=["urgent", "high", "medium", "low", "none"], default="none", help="Prioridad del ticket")
    p_create.add_argument("--state", help="Estado inicial (por defecto Backlog)")
    p_create.add_argument("--labels", help="Etiquetas separadas por comas (ej: backend,bug,spike)")
    p_create.add_argument("--json", action="store_true", help="Salida en JSON")

    # update
    p_update = subparsers.add_parser("update", help="Actualizar estado, prioridad o etiquetas de un ticket")
    p_update.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    p_update.add_argument("--state", help="Nuevo estado: Backlog, Pendiente, Progreso, Pruebas, Revisión, Completado, Pausado, Cancelado")
    p_update.add_argument("--priority", help="Prioridad: urgent, high, medium, low, none")
    p_update.add_argument("--labels", help="Etiquetas separadas por comas (ej: sms,backend,bug)")
    p_update.add_argument("--json", action="store_true", help="Salida en JSON")

    # get
    p_get = subparsers.add_parser("get", help="Obtener detalles de un ticket")
    p_get.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    p_get.add_argument("--json", action="store_true", help="Salida en JSON")

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
