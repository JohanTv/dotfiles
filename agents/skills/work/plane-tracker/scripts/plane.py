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
            sys.stderr.write("Usa: 'plane comment OMNIFY-162' o cámbiate a una rama como 'feature/OMNIFY-162'.\n")
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

def get_states_map(base_url, api_key, workspace, project_id):
    """Mapea nombres y slugs de estados a su UUID."""
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/states/"
    data = api_request(url, api_key)
    mapping = {}
    for st in data.get("results", []):
        name_clean = st["name"].lower().strip()
        slug_clean = st["slug"].lower().strip()
        mapping[name_clean] = st["id"]
        mapping[slug_clean] = st["id"]
        norm = name_clean.replace("ó", "o").replace("é", "e").replace("á", "a").replace("í", "i").replace("ú", "u")
        mapping[norm] = st["id"]
    return mapping

def get_labels_map(base_url, api_key, workspace, project_id):
    """Mapea nombres de etiquetas a su UUID con soporte de paginación."""
    mapping = {}
    cursor = None
    while True:
        url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/labels/"
        if cursor:
            url += f"?cursor={urllib.parse.quote(cursor)}"

        data = api_request(url, api_key)
        for lb in data.get("results", []):
            mapping[lb["name"].lower().strip()] = lb["id"]

        if not data.get("next_page_results") or not data.get("next_cursor"):
            break
        cursor = data.get("next_cursor")

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

def sync_remote_worklogs(conn, base_url, api_key, workspace, date_from_str, date_to_str, filter_project=None):
    """Sincroniza comentarios de Plane para tickets actualizados y los persiste en SQLite con descargas paralelas."""
    sys.stderr.write("🔄 Sincronizando registros de actividad desde Plane API...\n")
    projects_map = get_projects_map(conn, base_url, api_key, workspace)
    
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
    if candidate_tasks:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(fetch_comments_for_issue, t) for t in candidate_tasks]
            for fut in as_completed(futures):
                ident, iss, comments = fut.result()
                for c in comments:
                    html = c.get("comment_html", "")
                    meta = extract_metadata_from_comment(html)
                    if meta:
                        ticket_label = f"{ident}-{iss.get('sequence_id')}"
                        entry = {
                            "ticket_id": ticket_label,
                            "track": meta.get("track", "main"),
                            "issue_name": iss.get("name", ""),
                            "date": meta.get("date", datetime.now().strftime("%Y-%m-%d")),
                            "start_time": meta.get("start_time", "09:00"),
                            "end_time": meta.get("end_time", "10:00"),
                            "duration_minutes": meta.get("duration_minutes", 60),
                            "worker_type": meta.get("worker_type", "human"),
                            "capacity_bucket": meta.get("capacity_bucket", "deep_work"),
                            "phase": meta.get("phase", "dev"),
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
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
    res = api_request(url, api_key, method="POST", data={"comment_html": content})

    # Caching atómico en SQLite3
    meta = extract_metadata_from_comment(content)
    ticket_label = f"{issue.get('project_detail', {}).get('identifier', 'OMNIFY')}-{issue.get('sequence_id')}" if "sequence_id" in issue else args.issue
    
    # Determinar track y worker_type (prioridad: flags de CLI -> metadata -> default)
    track = getattr(args, "track", None) or (meta.get("track") if meta else None) or "main"
    worker_type = getattr(args, "worker_type", None) or (meta.get("worker_type") if meta else None) or "human"

    if not meta:
        clean_text = re.sub(r"<[^>]+>", "", content).strip()
        meta = {
            "schema_version": "2.2",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "start_time": datetime.now().strftime("%H:%M"),
            "end_time": (datetime.now() + timedelta(minutes=30)).strftime("%H:%M"),
            "duration_minutes": 30,
            "track": track,
            "worker_type": worker_type,
            "capacity_bucket": "deep_work",
            "notes": clean_text[:120] if clean_text else issue.get("name", ""),
            "stoppers": [],
            "phase": "dev"
        }
    else:
        meta["track"] = track
        meta["worker_type"] = worker_type

    entry = {
        "id": res.get("id"),
        "ticket_id": ticket_label,
        "track": track,
        "issue_name": issue.get("name", ""),
        "date": meta.get("date", datetime.now().strftime("%Y-%m-%d")),
        "start_time": meta.get("start_time", "09:00"),
        "end_time": meta.get("end_time", "10:00"),
        "duration_minutes": meta.get("duration_minutes", 60),
        "worker_type": worker_type,
        "capacity_bucket": meta.get("capacity_bucket", "deep_work"),
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
        states_map = get_states_map(base_url, api_key, workspace, project_id)
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
        labels_map = get_labels_map(base_url, api_key, workspace, project_id)
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

def cmd_get(args, conn, base_url, api_key, workspace, default_project_id):
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    args.issue = issue_ref
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    
    if getattr(args, "json", False):
        print(json.dumps(issue, indent=2))
    else:
        print(f"\n📌 {args.issue}: {issue.get('name')}")
        print(f"   Prioridad : {issue.get('priority')}")
        print(f"   Creado el : {issue.get('created_at')}")
        print(f"   UUID      : {issue.get('id')}\n")

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
    p_comment.add_argument("--worker-type", choices=["human", "subagent", "agent:agy", "agent:claude", "agent:opencode"], help="Tipo de ejecutor")
    p_comment.add_argument("--json", action="store_true", help="Salida en JSON")

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
        elif args.command == "update":
            cmd_update(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "get":
            cmd_get(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "list":
            cmd_list(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "report":
            cmd_report(args, conn, base_url, api_key, workspace, default_project_id)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
