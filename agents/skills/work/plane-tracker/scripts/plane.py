#!/usr/bin/env python3
"""
plane.py - CLI Integral para interactuar con Plane CE v1.2.3 desde agentes de IA y terminal.
Soporta:
  - Publicar comentarios dual-layer (humano + metadata)
  - Actualizar estados (Backlog, Pendiente, Progreso, Pruebas, Revisión, Completado, Pausado)
  - Gestionar prioridades (urgent, high, medium, low, none)
  - Asignar etiquetas humanas (sms, backend, frontend, bd, infra, deuda-tecnica, etc.)
  - Consultar y listar tickets asignados
"""

import sys
import os
import json
import urllib.request
import urllib.error
import re
import argparse

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

def api_request(url, api_key, method="GET", data=None):
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 204:
                return {}
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        sys.stderr.write(f"Error HTTP {e.code} en {url}: {err_msg}\n")
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write(f"Error de conexión con Plane ({url}): {e}\n")
        sys.exit(1)

def resolve_issue(base_url, api_key, workspace, project_id, issue_ref):
    """Resuelve un número de secuencia (ej. '162' o 'OMNIFY-162') o UUID al issue completo."""
    if re.match(r"^[0-9a-fA-F-]{36}$", issue_ref):
        url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue_ref}/"
        return api_request(url, api_key)

    seq_match = re.search(r"\d+", issue_ref)
    if not seq_match:
        sys.stderr.write(f"Error: Referencia de ticket inválida '{issue_ref}'.\n")
        sys.exit(1)
    seq_id = int(seq_match.group())

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/"
    data = api_request(url, api_key)
    for iss in data.get("results", []):
        if iss.get("sequence_id") == seq_id:
            return iss

    sys.stderr.write(f"Error: No se encontró el ticket OMNIFY-{seq_id} en el proyecto.\n")
    sys.exit(1)

def get_states_map(base_url, api_key, workspace, project_id):
    """Mapea nombres y slugs de estados a su UUID."""
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/states/"
    data = api_request(url, api_key)
    mapping = {}
    for st in data.get("results", []):
        name_clean = st["name"].lower()
        slug_clean = st["slug"].lower()
        mapping[name_clean] = st["id"]
        mapping[slug_clean] = st["id"]
        # Mapeos sin tilde
        mapping[name_clean.replace("ó", "o").replace("é", "e").replace("á", "a")] = st["id"]
    return mapping

def get_labels_map(base_url, api_key, workspace, project_id):
    """Mapea nombres de etiquetas a su UUID."""
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/labels/"
    data = api_request(url, api_key)
    mapping = {}
    for lb in data.get("results", []):
        mapping[lb["name"].lower()] = lb["id"]
    return mapping

# ------------------------------------------------------------------------------
# Subcomandos
# ------------------------------------------------------------------------------

def cmd_comment(args, base_url, api_key, workspace, project_id):
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

    issue = resolve_issue(base_url, api_key, workspace, project_id, args.issue)
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
    res = api_request(url, api_key, method="POST", data={"comment_html": content})
    print(f"✔ Comentario publicado exitosamente en OMNIFY-{issue.get('sequence_id')} (ID: {res.get('id')})")

def cmd_update(args, base_url, api_key, workspace, project_id):
    issue = resolve_issue(base_url, api_key, workspace, project_id, args.issue)
    patch_data = {}

    if args.state:
        states_map = get_states_map(base_url, api_key, workspace, project_id)
        target_state = args.state.lower().replace("ó", "o").replace("é", "e").replace("á", "a")
        if target_state not in states_map:
            sys.stderr.write(f"Error: Estado desconocido '{args.state}'. Estados válidos: Backlog, Pendiente, Progreso, Pruebas, Revisión, Completado, Pausado, Cancelado.\n")
            sys.exit(1)
        patch_data["state"] = states_map[target_state]

    if args.priority:
        prio = args.priority.lower()
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
    changes = []
    if "state" in patch_data:
        changes.append(f"Estado ➔ {args.state}")
    if "priority" in patch_data:
        changes.append(f"Prioridad ➔ {args.priority}")
    if "labels" in patch_data:
        changes.append(f"Etiquetas ➔ {args.labels}")

    print(f"✔ Ticket OMNIFY-{issue.get('sequence_id')} actualizado con éxito: [{', '.join(changes)}]")

def cmd_get(args, base_url, api_key, workspace, project_id):
    issue = resolve_issue(base_url, api_key, workspace, project_id, args.issue)
    print(f"\n📌 OMNIFY-{issue.get('sequence_id')}: {issue.get('name')}")
    print(f"   Prioridad : {issue.get('priority')}")
    print(f"   Creado el : {issue.get('created_at')}")
    print(f"   UUID      : {issue.get('id')}\n")

def cmd_list(args, base_url, api_key, workspace, project_id):
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/?limit=50"
    data = api_request(url, api_key)
    results = data.get("results", [])

    print(f"\n📋 Tickets recientes en Omnify ({len(results)} obtenidos):")
    for iss in results[:15]:
        prio = f"[{iss.get('priority', 'none').upper()}]"
        print(f"  • OMNIFY-{iss.get('sequence_id'):<4} {prio:<9} {iss.get('name')[:65]}")
    print("")

def main():
    parser = argparse.ArgumentParser(description="CLI de Plane CE para Agentes de IA")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcomando: comment
    p_comment = subparsers.add_parser("comment", help="Publicar comentario en un ticket")
    p_comment.add_argument("issue", help="Ticket (ej: OMNIFY-162, 162 o UUID)")
    p_comment.add_argument("-m", "--message", help="Mensaje del comentario")
    p_comment.add_argument("-f", "--file", help="Archivo con el contenido")

    # Subcomando: update
    p_update = subparsers.add_parser("update", help="Actualizar estado, prioridad o etiquetas de un ticket")
    p_update.add_argument("issue", help="Ticket (ej: OMNIFY-162, 162 o UUID)")
    p_update.add_argument("--state", help="Nuevo estado: Backlog, Pendiente, Progreso, Pruebas, Revisión, Completado, Pausado, Cancelado")
    p_update.add_argument("--priority", help="Prioridad: urgent, high, medium, low, none")
    p_update.add_argument("--labels", help="Etiquetas separadas por comas (ej: sms,backend,bug)")

    # Subcomando: get
    p_get = subparsers.add_parser("get", help="Obtener detalles de un ticket")
    p_get.add_argument("issue", help="Ticket (ej: OMNIFY-162, 162 o UUID)")

    # Subcomando: list
    p_list = subparsers.add_parser("list", help="Listar tickets del proyecto")
    p_list.add_argument("--mine", action="store_true", help="Filtrar por mis tickets")

    args = parser.parse_args()

    base_url = get_env_or_fail("PLANE_BASE_URL", "URL de Plane")
    api_key = get_env_or_fail("PLANE_API_KEY", "API Key de Plane")
    workspace = os.environ.get("PLANE_WORKSPACE_SLUG", "teamprogra")
    project_id = os.environ.get("PLANE_PROJECT_ID", "58371da4-cf62-4299-8fd4-99c1052b2eb3")

    if args.command == "comment":
        cmd_comment(args, base_url, api_key, workspace, project_id)
    elif args.command == "update":
        cmd_update(args, base_url, api_key, workspace, project_id)
    elif args.command == "get":
        cmd_get(args, base_url, api_key, workspace, project_id)
    elif args.command == "list":
        cmd_list(args, base_url, api_key, workspace, project_id)

if __name__ == "__main__":
    main()
