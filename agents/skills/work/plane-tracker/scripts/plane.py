#!/usr/bin/env python3
"""
plane.py - CLI Integral y Resiliente para Plane CE v1.2.3.
Soporta:
  - Descubrimiento dinámico de proyectos (OMNIFY, OPS, OMNILEADS, CDP, etc.) con caché local
  - Paginación robusta de tickets, comentarios y etiquetas
  - Timeout de red y manejo defensivo de errores
  - Publicación de bitácoras dual-layer (humano + metadata)
  - Transiciones de estado (Backlog, Pendiente, Progreso, Pruebas, Revisión, Completado, Pausado)
  - Prioridades y etiquetas humanas dinámicas
  - Salida formateada y soporte `--json` para agentes de IA
"""

import sys
import os
import json
import urllib.request
import urllib.error
import re
import time
import argparse

CACHE_DIR = os.path.expanduser("~/.cache/plane")
CACHE_FILE = os.path.join(CACHE_DIR, "projects_cache.json")
CACHE_TTL = 86400  # 24 horas

def load_zshrc_local_if_needed():
    """Carga variables desde ~/.zshrc.local si no están en el entorno."""
    local_env = os.path.expanduser("~/.zshrc.local")
    if os.path.isfile(local_env):
        try:
            with open(local_env, "r") as f:
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

def api_request(url, api_key, method="GET", data=None, timeout=10):
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 204:
                return {}
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        sys.stderr.write(f"Error HTTP {e.code} en {url}: {err_msg}\n")
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write(f"Error de red/conexión con Plane ({url}): {e}\n")
        sys.exit(1)

def get_projects_map(base_url, api_key, workspace, force_refresh=False):
    """Obtiene el mapa de identifier -> UUID de proyectos con caché local."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    now = time.time()

    if not force_refresh and os.path.isfile(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                cache_data = json.load(f)
                if now - cache_data.get("_timestamp", 0) < CACHE_TTL:
                    return cache_data.get("projects", {})
        except Exception:
            pass

    # Consulta dinámica a la API de Plane
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
        with open(CACHE_FILE, "w") as f:
            json.dump({"_timestamp": now, "projects": projects_map}, f, indent=2)
    except Exception:
        pass

    return projects_map

def resolve_project_and_seq(base_url, api_key, workspace, default_project_id, issue_ref):
    """
    Deduce el proyecto y número de secuencia a partir del issue_ref.
    Soporta: 'OMNIFY-162', 'OPS-44', '162' o UUID.
    """
    # Si es UUID
    if re.match(r"^[0-9a-fA-F-]{36}$", issue_ref):
        return default_project_id, None, issue_ref

    match = re.match(r"^([A-Za-z0-9_]+)-(\d+)$", issue_ref.strip())
    if match:
        prefix = match.group(1).upper()
        seq_id = int(match.group(2))
        projects_map = get_projects_map(base_url, api_key, workspace)
        if prefix in projects_map:
            return projects_map[prefix]["id"], seq_id, None

        # Reintento con refresco de caché si no existe el prefijo
        projects_map = get_projects_map(base_url, api_key, workspace, force_refresh=True)
        if prefix in projects_map:
            return projects_map[prefix]["id"], seq_id, None

        sys.stderr.write(f"Error: Prefijo de proyecto '{prefix}' no encontrado en el workspace '{workspace}'.\n")
        sys.stderr.write(f"Proyectos disponibles: {', '.join(projects_map.keys())}\n")
        sys.exit(1)

    # Si solo son números (ej: 162), se asume default_project_id (Omnify)
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
        # Normalización sin acentos
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
# Comandos
# ------------------------------------------------------------------------------

def cmd_comment(args, base_url, api_key, workspace, default_project_id):
    project_id, seq_id, uuid_ref = resolve_project_and_seq(base_url, api_key, workspace, default_project_id, args.issue)
    content = ""
    if args.file:
        with open(args.file, "r") as f:
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
    # Si pasa un prefijo de proyecto (ej: OPS o OMNIFY)
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
            seq = iss.get('sequence_id', '?')
            print(f"  • #{seq:<4} {prio:<9} {iss.get('name')[:65]}")
        print("")

def main():
    parser = argparse.ArgumentParser(description="CLI de Plane CE para Agentes de IA (v2.2)")
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

if __name__ == "__main__":
    main()
