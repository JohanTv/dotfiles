"""Resolución de proyectos, tickets, estados, etiquetas y usuario activo contra Plane, con caché SQLite.

Expone: get_projects_map(), get_project_identifier(), resolve_project_and_seq(), local_ticket_label(), resolve_issue(),
get_states_map(), get_labels_map(), get_actor_uuid(), detect_ticket_from_git().
No hace: imprimir resultados ni escribir en Plane. Ante PlaneUnavailable, proyectos, estados y etiquetas se sirven de la
caché local aunque haya vencido (con aviso), y sin caché lanzan PlaneUnavailable (código 3 en el CLI).
"""

import os
import re
import subprocess
import sys
import time
import urllib.parse

from plane_cli.api import PlaneUnavailable, api_request
from plane_cli.cache import serve_stale


PROJECTS_TTL = 86400  # 24 horas


def get_projects_map(conn, base_url, api_key, workspace, force_refresh=False):
    """Obtiene el mapa de identifier -> UUID de proyectos desde SQLite o Plane API."""
    now = time.time()
    rows = conn.execute("SELECT identifier, project_id, name, updated_at FROM projects WHERE workspace = ?", (workspace,)).fetchall()
    as_map = lambda items: {r["identifier"]: {"id": r["project_id"], "name": r["name"], "identifier": r["identifier"]} for r in items}
    if rows and not force_refresh and all((now - r["updated_at"]) < PROJECTS_TTL for r in rows):
        return as_map(rows)

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/"
    try:
        data = api_request(url, api_key)
    except PlaneUnavailable:
        return as_map(serve_stale(rows, "proyectos"))
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


def _ref_or_git(issue_ref):
    """El ticket pedido o, si falta (o es '@', '.', 'current'...), el de la rama de git; termina con error si no hay ninguno."""
    if not issue_ref or issue_ref in ("@", ".", "current", "--current", "this"):
        git_ticket = detect_ticket_from_git()
        if git_ticket:
            sys.stderr.write(f"ℹ Ticket auto-detectado desde la rama actual de Git: {git_ticket}\n")
            issue_ref = git_ticket
        else:
            sys.stderr.write("Error: No se especificó ticket y no se detectó identificador en la rama actual de Git.\n")
            sys.stderr.write("Usa: 'plane-tracker comment add OMNIFY-162' o cámbiate a una rama como 'feature/OMNIFY-162'.\n")
            sys.exit(1)
    return issue_ref


def local_ticket_label(issue_ref):
    """'PREFIJO-N' de un ticket sin consultar Plane (el UUID se devuelve tal cual); termina con error si el formato no se reconoce."""
    issue_ref = _ref_or_git(issue_ref)
    match = re.match(r"^([A-Za-z0-9_]+)-(\d+)$", issue_ref.strip())
    if re.match(r"^[0-9a-fA-F-]{36}$", issue_ref):
        return issue_ref
    if match:
        return f"{match.group(1).upper()}-{int(match.group(2))}"
    if re.match(r"^\d+$", issue_ref.strip()):
        return f"OMNIFY-{issue_ref.strip()}"
    sys.stderr.write(f"Error: Formato de ticket no reconocido: '{issue_ref}'. Usa 'OMNIFY-162', 'OPS-44' o solo '162'.\n")
    sys.exit(1)


def resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, issue_ref=None):
    """
    Deduce el proyecto y número de secuencia a partir del issue_ref o rama de Git.
    Soporta: 'OMNIFY-162', 'OPS-44', '162', UUID o None/@ (autodetección de Git).
    """
    issue_ref = _ref_or_git(issue_ref)
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


def _states_mapping(items):
    """{nombre, slug y nombre sin tildes -> UUID} a partir de filas locales o resultados de la API (ambos indexan id, name y slug)."""
    mapping = {}
    for st in items:
        name_clean = st["name"].lower().strip()
        slug_clean = st["slug"].lower().strip()
        mapping[name_clean] = st["id"]
        mapping[slug_clean] = st["id"]
        mapping[name_clean.replace("ó", "o").replace("é", "e").replace("á", "a").replace("í", "i").replace("ú", "u")] = st["id"]
    return mapping


def get_states_map(conn, base_url, api_key, workspace, project_id, force_refresh=False):
    """Mapea nombres y slugs de estados a su UUID usando caché SQLite3 con TTL."""
    now = time.time()
    rows = conn.execute("SELECT id, name, slug, group_name, is_default, updated_at FROM states WHERE project_id = ?", (project_id,)).fetchall() if conn else []
    if rows and not force_refresh and all((now - r["updated_at"]) < PROJECTS_TTL for r in rows):
        return _states_mapping(rows)

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/states/"
    try:
        data = api_request(url, api_key)
    except PlaneUnavailable:
        return _states_mapping(serve_stale(rows, "estados"))
    if conn:
        with conn:
            for st in data.get("results", []):
                conn.execute("""
                    INSERT INTO states (id, project_id, name, slug, group_name, is_default, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        slug = excluded.slug,
                        group_name = excluded.group_name,
                        is_default = excluded.is_default,
                        updated_at = excluded.updated_at;
                """, (st["id"], project_id, st["name"], st["slug"], st.get("group", ""), 1 if st.get("default") else 0, now))
    return _states_mapping(data.get("results", []))


def get_labels_map(conn, base_url, api_key, workspace, project_id, force_refresh=False):
    """Mapea nombres de etiquetas a su UUID con paginación y caché SQLite3 con TTL."""
    now = time.time()
    rows = conn.execute("SELECT id, name, color, updated_at FROM labels WHERE project_id = ?", (project_id,)).fetchall() if conn else []
    if rows and not force_refresh and all((now - r["updated_at"]) < PROJECTS_TTL for r in rows):
        return {r["name"].lower().strip(): r["id"] for r in rows}

    mapping = {}
    cursor = None
    all_labels = []
    while True:
        url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/labels/"
        if cursor:
            url += f"?cursor={urllib.parse.quote(cursor)}"

        try:
            data = api_request(url, api_key)
        except PlaneUnavailable:
            return {r["name"].lower().strip(): r["id"] for r in serve_stale(rows, "etiquetas")}
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
