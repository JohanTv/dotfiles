#!/usr/bin/env python3
"""
plane_post.py - Script ejecutor para publicar comentarios dual-layer en Plane CE v1.2.3.
Lee credenciales y configuración desde variables de entorno (planeadas en ~/.zshrc.local).
"""

import sys
import os
import json
import urllib.request
import urllib.error
import re
import argparse

def get_env_or_fail(var_name, description):
    val = os.environ.get(var_name)
    if not val:
        sys.stderr.write(f"Error: Variable de entorno '{var_name}' ({description}) no configurada.\n")
        sys.stderr.write("Defínela en ~/.zshrc.local o en tu entorno antes de ejecutar este script.\n")
        sys.exit(1)
    return val

def resolve_issue_id(base_url, api_key, workspace, project_id, issue_ref):
    """Resuelve un número de secuencia (ej. '162' o 'OMNIFY-162') o UUID a issue_id."""
    # Si ya parece un UUID
    if re.match(r"^[0-9a-fA-F-]{36}$", issue_ref):
        return issue_ref

    # Extraer dígitos
    seq_match = re.search(r"\d+", issue_ref)
    if not seq_match:
        sys.stderr.write(f"Error: Referencia de ticket inválida '{issue_ref}'.\n")
        sys.exit(1)
    seq_id = int(seq_match.group())

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/"
    req = urllib.request.Request(url, headers={"x-api-key": api_key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            for iss in data.get("results", []):
                if iss.get("sequence_id") == seq_id:
                    return iss["id"]
    except urllib.error.URLError as e:
        sys.stderr.write(f"Error al consultar issues en Plane: {e}\n")
        sys.exit(1)

    sys.stderr.write(f"Error: No se encontró el ticket OMNIFY-{seq_id} en el proyecto.\n")
    sys.exit(1)

def post_comment(base_url, api_key, workspace, project_id, issue_id, comment_html):
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue_id}/comments/"
    payload = json.dumps({"comment_html": comment_html}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }, method="POST")

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return data
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"Error HTTP {e.code} al publicar comentario: {e.read().decode()}\n")
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write(f"Error de conexión con Plane: {e}\n")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Publicar comentario en ticket de Plane CE")
    parser.add_argument("issue", help="Ticket de Plane (ej: OMNIFY-162, 162 o UUID)")
    parser.add_argument("--file", "-f", help="Archivo con el contenido HTML/Markdown del comentario")
    parser.add_argument("--message", "-m", help="Mensaje directo del comentario")
    args = parser.parse_args()

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

    base_url = get_env_or_fail("PLANE_BASE_URL", "URL de Plane")
    api_key = get_env_or_fail("PLANE_API_KEY", "API Key de Plane")
    workspace = os.environ.get("PLANE_WORKSPACE_SLUG", "teamprogra")
    project_id = os.environ.get("PLANE_PROJECT_ID", "58371da4-cf62-4299-8fd4-99c1052b2eb3")

    issue_id = resolve_issue_id(base_url, api_key, workspace, project_id, args.issue)
    res = post_comment(base_url, api_key, workspace, project_id, issue_id, content)
    print(f"✔ Comentario publicado exitosamente en {args.issue} (ID Comentario: {res.get('id')})")

if __name__ == "__main__":
    main()
