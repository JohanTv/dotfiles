#!/usr/bin/env python3
"""
plane.py - CLI Integral y Resiliente para Plane CE v1.2.3.
Soporta:
  - Descubrimiento dinámico de proyectos (OMNIFY, OPS, OMNILEADS, CDP, etc.) con caché local
  - Paginación robusta de tickets, comentarios y etiquetas
  - Timeout de red, reintentos con backoff defensivo ante HTTP 429
  - Publicación de bitácoras dual-layer (humano + metadata oculta)
  - Transiciones de estado (Backlog, Pendiente, Progreso, Pruebas, Revisión, Completado, Pausado)
  - Prioridades y etiquetas humanas dinámicas
  - Generación de reportes de actividad (--today, --week, --date) en formato híbrido
  - Salida formateada y soporte `--json` para agentes de IA y dashboards
"""

import sys
import os
import json
import urllib.request
import urllib.error
import urllib.parse
import re
import time
import argparse
from datetime import datetime, timedelta, date

CACHE_DIR = os.path.expanduser("~/.cache/plane")
CACHE_FILE = os.path.join(CACHE_DIR, "projects_cache.json")
WORKLOGS_CACHE = os.path.join(CACHE_DIR, "worklogs_cache.json")
CACHE_TTL = 86400  # 24 horas

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

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

def get_projects_map(base_url, api_key, workspace, force_refresh=False):
    """Obtiene el mapa de identifier -> UUID de proyectos con caché local."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    now = time.time()

    if not force_refresh and os.path.isfile(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                if now - cache_data.get("_timestamp", 0) < CACHE_TTL:
                    return cache_data.get("projects", {})
        except Exception:
            pass

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/"
    data = api_request(url, api_key)
    projects_map = {}
    for proj in data.get("results", []):
        ident = proj.get("identifier", "").upper()
        if ident:
            projects_map[ident] = {
                "id": proj["id"],
                "name": proj["name"],
                "identifier": ident
            }

    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"_timestamp": now, "projects": projects_map}, f, indent=2)
    except Exception:
        pass

    return projects_map

def resolve_project_and_seq(base_url, api_key, workspace, default_project_id, issue_ref):
    """
    Deduce el proyecto y número de secuencia a partir del issue_ref.
    Soporta: 'OMNIFY-162', 'OPS-44', '162' o UUID.
    """
    if re.match(r"^[0-9a-fA-F-]{36}$", issue_ref):
        return default_project_id, None, issue_ref

    match = re.match(r"^([A-Za-z0-9_]+)-(\d+)$", issue_ref.strip())
    if match:
        prefix = match.group(1).upper()
        seq_id = int(match.group(2))
        projects_map = get_projects_map(base_url, api_key, workspace)
        if prefix in projects_map:
            return projects_map[prefix]["id"], seq_id, None

        projects_map = get_projects_map(base_url, api_key, workspace, force_refresh=True)
        if prefix in projects_map:
            return projects_map[prefix]["id"], seq_id, None

        sys.stderr.write(f"Error: Prefijo de proyecto '{prefix}' no encontrado en el workspace '{workspace}'.\n")
        sys.stderr.write(f"Proyectos disponibles: {', '.join(projects_map.keys())}\n")
        sys.exit(1)

    if re.match(r"^\d+$", issue_ref.strip()):
        return default_project_id, int(issue_ref.strip()), None

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
# Gestión de Caché Local de Registros de Trabajo (Worklogs)
# ------------------------------------------------------------------------------

def load_worklogs_cache():
    """Carga la caché local de registros de trabajo y timestamp de último sync."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.isfile(WORKLOGS_CACHE):
        try:
            with open(WORKLOGS_CACHE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("worklogs", []), data.get("_last_synced", 0)
        except Exception:
            pass
    return [], 0

def save_worklogs_cache(worklogs, mark_sync=False):
    """Guarda registros de trabajo en la caché local sin duplicados."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    _, last_synced = load_worklogs_cache()
    if mark_sync:
        last_synced = time.time()

    seen = set()
    unique = []
    for wl in sorted(worklogs, key=lambda x: (x.get("date", ""), x.get("start_time", ""))):
        key = wl.get("id") or f"{wl.get('ticket_id')}_{wl.get('date')}_{wl.get('start_time')}"
        if key not in seen:
            seen.add(key)
            unique.append(wl)
    try:
        with open(WORKLOGS_CACHE, "w", encoding="utf-8") as f:
            json.dump({"_version": "2.1", "_last_synced": last_synced, "worklogs": unique}, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return unique

def extract_metadata_from_comment(comment_html):
    """
    Extrae metadata telemétrica oculta (<!-- PLANE_WORKLOG_METADATA ... -->)
    o deduce los datos a partir de la tabla markdown del comentario.
    """
    if not comment_html:
        return None

    # 1. Bloque JSON telemétrico estructurado
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

        return {
            "date": d_str,
            "start_time": s_time,
            "end_time": e_time,
            "duration_minutes": dur,
            "capacity_bucket": bucket_str,
            "notes": notes_str,
            "stoppers": [],
            "schema_version": "2.1"
        }

    return None

def sync_remote_worklogs(base_url, api_key, workspace, date_from_str, date_to_str, filter_project=None):
    """
    Sincroniza remotamente comentarios desde Plane para tickets actualizados
    entre date_from_str y date_to_str.
    """
    sys.stderr.write("🔄 Sincronizando registros de actividad desde Plane API...\n")
    projects_map = get_projects_map(base_url, api_key, workspace)
    cached, _ = load_worklogs_cache()
    cached_ids = {e.get("id") for e in cached if e.get("id")}
    new_entries = []

    try:
        d_from = datetime.strptime(date_from_str, "%Y-%m-%d").date() - timedelta(days=1)
    except Exception:
        d_from = datetime.now().date() - timedelta(days=7)

    # Filtrar o priorizar proyectos relevantes
    target_idents = []
    if filter_project:
        f_up = filter_project.upper()
        if f_up in projects_map:
            target_idents = [f_up]
    else:
        # Priorizar Omnify y Operaciones (proyectos activos de desarrollo y soporte)
        for pref in ["OMNIFY", "OPS", "OMNICANAL"]:
            if pref in projects_map:
                target_idents.append(pref)

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

            c_url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{proj_id}/issues/{iss['id']}/comments/"
            try:
                time.sleep(0.1)  # Evitar 429
                c_data = api_request(c_url, api_key, raise_on_error=True)
            except urllib.error.HTTPError as e:
                if e.code in (401, 403, 404):
                    continue
                pass
            except Exception:
                continue

            for c in c_data.get("results", []):
                c_id = c.get("id")
                if c_id in cached_ids:
                    continue

                html = c.get("comment_html", "")
                meta = extract_metadata_from_comment(html)
                if meta:
                    ticket_label = f"{ident}-{iss.get('sequence_id')}"
                    entry = {
                        "id": c_id,
                        "ticket_id": ticket_label,
                        "issue_name": iss.get("name", ""),
                        "date": meta.get("date", datetime.now().strftime("%Y-%m-%d")),
                        "start_time": meta.get("start_time", "09:00"),
                        "end_time": meta.get("end_time", "10:00"),
                        "duration_minutes": meta.get("duration_minutes", 60),
                        "capacity_bucket": meta.get("capacity_bucket", "deep_work"),
                        "phase": meta.get("phase", "dev"),
                        "notes": meta.get("notes", iss.get("name", "")),
                        "stoppers": meta.get("stoppers", []),
                        "related_ticket_id": meta.get("related_ticket_id"),
                        "created_at": c.get("created_at")
                    }
                    new_entries.append(entry)
                    cached_ids.add(c_id)

    if new_entries:
        cached.extend(new_entries)
        save_worklogs_cache(cached, mark_sync=True)
        sys.stderr.write(f"✔ Se importaron {len(new_entries)} registros nuevos desde Plane.\n")
    else:
        save_worklogs_cache(cached, mark_sync=True)
        sys.stderr.write("ℹ Sincronización completa: no se hallaron nuevos registros telemétricos.\n")

    return cached

# ------------------------------------------------------------------------------
# Comandos
# ------------------------------------------------------------------------------

def cmd_comment(args, base_url, api_key, workspace, default_project_id):
    project_id, seq_id, uuid_ref = resolve_project_and_seq(base_url, api_key, workspace, default_project_id, args.issue)
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

    # Caching local automático del worklog para reportes instantáneos
    meta = extract_metadata_from_comment(content)
    ticket_label = f"{issue.get('project_detail', {}).get('identifier', 'OMNIFY')}-{issue.get('sequence_id')}" if "sequence_id" in issue else args.issue
    if not meta:
        clean_text = re.sub(r"<[^>]+>", "", content).strip()
        meta = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "start_time": datetime.now().strftime("%H:%M"),
            "end_time": (datetime.now() + timedelta(minutes=30)).strftime("%H:%M"),
            "duration_minutes": 30,
            "capacity_bucket": "deep_work",
            "notes": clean_text[:120] if clean_text else issue.get("name", ""),
            "stoppers": [],
            "schema_version": "2.1"
        }

    worklogs, _ = load_worklogs_cache()
    entry = {
        "id": res.get("id") or f"local_{int(time.time())}",
        "ticket_id": ticket_label,
        "issue_name": issue.get("name", ""),
        "date": meta.get("date", datetime.now().strftime("%Y-%m-%d")),
        "start_time": meta.get("start_time", "09:00"),
        "end_time": meta.get("end_time", "10:00"),
        "duration_minutes": meta.get("duration_minutes", 60),
        "capacity_bucket": meta.get("capacity_bucket", "deep_work"),
        "phase": meta.get("phase", "dev"),
        "notes": meta.get("notes", issue.get("name", "")),
        "stoppers": meta.get("stoppers", []),
        "related_ticket_id": meta.get("related_ticket_id"),
        "created_at": datetime.now().isoformat()
    }
    worklogs.append(entry)
    save_worklogs_cache(worklogs)

    if getattr(args, "json", False):
        print(json.dumps({"status": "ok", "action": "comment", "issue_id": issue["id"], "sequence_id": issue.get("sequence_id"), "comment_id": res.get("id")}))
    else:
        print(f"✔ Comentario publicado exitosamente en {args.issue} (ID Comentario: {res.get('id')})")

def cmd_update(args, base_url, api_key, workspace, default_project_id):
    project_id, seq_id, uuid_ref = resolve_project_and_seq(base_url, api_key, workspace, default_project_id, args.issue)
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

def cmd_get(args, base_url, api_key, workspace, default_project_id):
    project_id, seq_id, uuid_ref = resolve_project_and_seq(base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    
    if getattr(args, "json", False):
        print(json.dumps(issue, indent=2))
    else:
        print(f"\n📌 {args.issue}: {issue.get('name')}")
        print(f"   Prioridad : {issue.get('priority')}")
        print(f"   Creado el : {issue.get('created_at')}")
        print(f"   UUID      : {issue.get('id')}\n")

def cmd_list(args, base_url, api_key, workspace, default_project_id):
    project_id = default_project_id
    if getattr(args, "project", None):
        projects_map = get_projects_map(base_url, api_key, workspace)
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
# Generador de Reportes de Actividad (cmd_report)
# ------------------------------------------------------------------------------

def format_minutes(m):
    h = m // 60
    mins = m % 60
    return f"{h}h {mins:02d}m"

def render_day_block(date_obj, entries):
    """Genera el bloque textual de un día en formato híbrido."""
    dia_nombre = DIAS_SEMANA[date_obj.weekday()]
    d_str = date_obj.strftime("%d/%m/%Y")
    lines = []

    if not entries:
        return f"ℹ Sin registros de actividad para {dia_nombre} {d_str}.\n"

    # Orden cronológico por start_time
    sorted_entries = sorted(entries, key=lambda x: x.get("start_time", ""))

    total_active = 0
    by_project = {}
    stoppers = []

    for idx, e in enumerate(sorted_entries, 1):
        t_id = e.get("ticket_id", "DESARROLLO")
        name = e.get("issue_name", "").strip()
        notas = e.get("notes", "").strip()
        s_time = e.get("start_time", "--:--")
        e_time = e.get("end_time", "--:--")
        dur = e.get("duration_minutes", 0)

        total_active += dur
        prefix = t_id.split("-")[0] if "-" in t_id else "Otros"
        by_project[prefix] = by_project.get(prefix, 0) + dur

        for st in e.get("stoppers", []):
            if st and st not in stoppers:
                stoppers.append(st)

        lines.append(f"titulo: [{t_id}] {name}")
        lines.append(f"inicio: {s_time}")
        lines.append(f"fin: {e_time}")
        lines.append(f"notas: {notas}")
        lines.append("")

    # Totales y Standbys
    proj_parts = [f"{k}: {format_minutes(v)}" for k, v in by_project.items()]
    proj_str = " | ".join(proj_parts) if proj_parts else "N/A"

    lines.append("-" * 80)
    lines.append(f"📊 Total día: {format_minutes(total_active)} activas ({proj_str})")
    if stoppers:
        lines.append(f"⏸️ Standby externo: {', '.join(stoppers)}")
    else:
        lines.append("⏸️ Standby externo: 0h 00m (Sin bloqueos reportados)")

    return "\n".join(lines)

def cmd_report(args, base_url, api_key, workspace, default_project_id):
    today = datetime.now().date()
    is_week = getattr(args, "week", False)
    custom_date = getattr(args, "date", None)
    force_sync = getattr(args, "sync", False)

    if is_week:
        # Lunes a Domingo de la semana en curso
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
        # Por defecto: hoy
        start_date = today
        end_date = today

    cached, last_synced = load_worklogs_cache()
    now = time.time()
    has_entries = any(start_date <= datetime.strptime(e.get("date", "2000-01-01"), "%Y-%m-%d").date() <= end_date for e in cached)
    needs_sync = force_sync or (not has_entries and (now - last_synced > 300))
    if needs_sync:
        cached = sync_remote_worklogs(base_url, api_key, workspace, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), filter_project=getattr(args, "project", None))

    # Filtrar registros en el rango
    filtered = []
    for e in cached:
        d_val = e.get("date")
        if not d_val:
            continue
        try:
            dt = datetime.strptime(d_val, "%Y-%m-%d").date()
            if start_date <= dt <= end_date:
                # Filtro opcional por proyecto
                if getattr(args, "project", None):
                    p_upper = args.project.upper()
                    if not e.get("ticket_id", "").upper().startswith(p_upper):
                        continue
                filtered.append(e)
        except Exception:
            pass

    if getattr(args, "json", False):
        print(json.dumps(filtered, indent=2, ensure_ascii=False))
        return

    # Renderizado en texto
    if is_week:
        num_semana = start_date.isocalendar()[1]
        print("=" * 80)
        print(f"📅 REPORTE SEMANAL - SEMANA {num_semana} ({start_date.strftime('%d/%m/%Y')} al {end_date.strftime('%d/%m/%Y')})")
        print("=" * 80 + "\n")

        total_week_active = 0
        week_by_project = {}
        all_week_stoppers = []

        cur = start_date
        # Solo mostrar hasta hoy si la semana aún está transcurriendo
        limit_day = min(end_date, today)
        while cur <= limit_day:
            day_entries = [e for e in filtered if e.get("date") == cur.strftime("%Y-%m-%d")]
            dia_nombre = DIAS_SEMANA[cur.weekday()]
            print(f"[{dia_nombre} {cur.strftime('%d/%m/%Y')}]")
            print(render_day_block(cur, day_entries))
            print("")

            for e in day_entries:
                dur = e.get("duration_minutes", 0)
                total_week_active += dur
                pref = e.get("ticket_id", "").split("-")[0] if "-" in e.get("ticket_id", "") else "Otros"
                week_by_project[pref] = week_by_project.get(pref, 0) + dur
                for st in e.get("stoppers", []):
                    if st and st not in all_week_stoppers:
                        all_week_stoppers.append(st)

            cur += timedelta(days=1)

        proj_parts = [f"{k}: {format_minutes(v)}" for k, v in week_by_project.items()]
        proj_str = " | ".join(proj_parts) if proj_parts else "N/A"

        print("=" * 80)
        print(f"🏆 TOTAL SEMANA: {format_minutes(total_week_active)} activas ({proj_str})")
        if all_week_stoppers:
            print(f"⏸️ STANDBY TOTAL: {', '.join(all_week_stoppers)}")
        print("=" * 80 + "\n")

    else:
        target = start_date
        dia_nombre = DIAS_SEMANA[target.weekday()]
        print("=" * 80)
        print(f"📋 REPORTE DE ACTIVIDAD - {dia_nombre.upper()} {target.strftime('%d/%m/%Y')}")
        print("=" * 80 + "\n")
        day_entries = [e for e in filtered if e.get("date") == target.strftime("%Y-%m-%d")]
        print(render_day_block(target, day_entries))
        print("\n" + "=" * 80)

# ------------------------------------------------------------------------------
# Entrypoint CLI
# ------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CLI de Plane CE para Agentes de IA y Reportes de Actividad (v2.3)")
    parser.add_argument("--json", action="store_true", help="Salida en formato JSON para agentes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # comment
    p_comment = subparsers.add_parser("comment", help="Publicar comentario en un ticket")
    p_comment.add_argument("issue", help="Ticket (ej: OMNIFY-162, OPS-44 o 162)")
    p_comment.add_argument("-m", "--message", help="Mensaje del comentario")
    p_comment.add_argument("-f", "--file", help="Archivo con el contenido")
    p_comment.add_argument("--json", action="store_true", help="Salida en JSON")

    # update
    p_update = subparsers.add_parser("update", help="Actualizar estado, prioridad o etiquetas de un ticket")
    p_update.add_argument("issue", help="Ticket (ej: OMNIFY-162, OPS-44 o 162)")
    p_update.add_argument("--state", help="Nuevo estado: Backlog, Pendiente, Progreso, Pruebas, Revisión, Completado, Pausado, Cancelado")
    p_update.add_argument("--priority", help="Prioridad: urgent, high, medium, low, none")
    p_update.add_argument("--labels", help="Etiquetas separadas por comas (ej: sms,backend,bug)")
    p_update.add_argument("--json", action="store_true", help="Salida en JSON")

    # get
    p_get = subparsers.add_parser("get", help="Obtener detalles de un ticket")
    p_get.add_argument("issue", help="Ticket (ej: OMNIFY-162, OPS-44 o 162)")
    p_get.add_argument("--json", action="store_true", help="Salida en JSON")

    # list
    p_list = subparsers.add_parser("list", help="Listar tickets del proyecto")
    p_list.add_argument("-p", "--project", help="Identificador del proyecto (ej: OMNIFY, OPS, OMNILEADS)")
    p_list.add_argument("--json", action="store_true", help="Salida en JSON")

    # report
    p_report = subparsers.add_parser("report", help="Generar reporte de actividades en formato híbrido")
    group_date = p_report.add_mutually_exclusive_group()
    group_date.add_argument("--today", action="store_true", help="Reporte del día actual (por defecto)")
    group_date.add_argument("--week", action="store_true", help="Reporte de la semana actual")
    group_date.add_argument("--date", help="Reporte de fecha específica (YYYY-MM-DD)")
    p_report.add_argument("-p", "--project", help="Filtrar por proyecto (ej: OMNIFY, OPS)")
    p_report.add_argument("--sync", action="store_true", help="Forzar sincronización remota con Plane")
    p_report.add_argument("--json", action="store_true", help="Salida en formato JSON")

    args = parser.parse_args()

    base_url = get_env_or_fail("PLANE_BASE_URL", "URL de Plane")
    api_key = get_env_or_fail("PLANE_API_KEY", "API Key de Plane")
    workspace = os.environ.get("PLANE_WORKSPACE_SLUG", "teamprogra")
    default_project_id = os.environ.get("PLANE_PROJECT_ID", "58371da4-cf62-4299-8fd4-99c1052b2eb3")

    if args.command == "comment":
        cmd_comment(args, base_url, api_key, workspace, default_project_id)
    elif args.command == "update":
        cmd_update(args, base_url, api_key, workspace, default_project_id)
    elif args.command == "get":
        cmd_get(args, base_url, api_key, workspace, default_project_id)
    elif args.command == "list":
        cmd_list(args, base_url, api_key, workspace, default_project_id)
    elif args.command == "report":
        cmd_report(args, base_url, api_key, workspace, default_project_id)

if __name__ == "__main__":
    main()
