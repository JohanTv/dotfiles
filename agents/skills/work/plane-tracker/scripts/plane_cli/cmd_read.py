"""Comandos de lectura: `get`, `list`, `search`, `labels`, `projects` y `whoami`.

Expone: register_get(), register_list(), register_search(), register_labels(), register_projects(), register_whoami(),
y los cmd_* correspondientes.
No hace: escribir en Plane.
"""

import json
import os
import re
import sys
import time

from plane_cli.api import PlaneUnavailable, api_request
from plane_cli.config import add_json_flag, positive_int
from plane_cli.flow import build_ticket_flow, flow_to_json, format_lifecycle, print_flow
from plane_cli.resolve import (
    get_actor_uuid,
    get_labels_map,
    get_projects_map,
    get_states_map,
    resolve_issue,
    resolve_project_and_seq,
)


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


def cmd_projects(args, conn, base_url, api_key, workspace, default_project_id):
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
    except PlaneUnavailable as exc:
        if not conn.execute("SELECT 1 FROM issues_cache WHERE project_id = ? LIMIT 1", (project_id,)).fetchone():
            raise
        sys.stderr.write(f"⚠ Plane no responde ({exc.cause}); consultando la caché local.\n")

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


def cmd_whoami(args, conn, base_url, api_key, workspace, default_project_id):
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


def register_get(sub):
    p_get = sub.add_parser("get", help="Ver un ticket con sus comentarios")
    p_get.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    add_json_flag(p_get)
    p_get.add_argument("--no-comments", action="store_true", help="No traer ni mostrar comentarios (ahorra tokens)")
    p_get.add_argument("--last", type=positive_int, metavar="N", help="Mostrar solo los últimos N comentarios (por defecto: todos)")
    p_get.add_argument("--full", action="store_true", help="Sin truncar descripción ni comentarios (por defecto 300 caracteres)")
    p_get.add_argument("--no-description", action="store_true", help="Omitir la descripción")
    p_get.add_argument("--history", action="store_true", help="Añadir flujo: lead/cycle time, tiempo por estado, esfuerzo y transiciones")
    p_get.set_defaults(handler=cmd_get)


def register_list(sub):
    p_list = sub.add_parser("list", help="Listar los tickets del proyecto")
    p_list.add_argument("-p", "--project", help="Identificador del proyecto (ej: OMNIFY, OPS, OMNILEADS)")
    add_json_flag(p_list)
    p_list.set_defaults(handler=cmd_list)


def register_search(sub):
    p_search = sub.add_parser("search", help="Buscar tickets por texto (caché local)",
                                description="Búsqueda FTS5 (< 2 ms) sobre la caché local de tickets; úsala antes de crear uno nuevo.")
    p_search.add_argument("query", help="Texto de búsqueda (ej: 'validaciones formulario', 'webhook sms')")
    p_search.add_argument("-p", "--project", help="Identificador del proyecto (por defecto OMNIFY)")
    p_search.add_argument("--refresh", action="store_true", help="Forzar sincronización remota con Plane")
    add_json_flag(p_search)
    p_search.set_defaults(handler=cmd_search)


def register_labels(sub):
    p_labels = sub.add_parser("labels", help="Listar las etiquetas del proyecto",
                                 description="Etiquetas disponibles en un proyecto, desde la caché local (--refresh la actualiza).")
    p_labels.add_argument("-p", "--project", help="Identificador del proyecto (por defecto OMNIFY)")
    p_labels.add_argument("--refresh", action="store_true", help="Forzar sincronización remota con la API de Plane")
    add_json_flag(p_labels)
    p_labels.set_defaults(handler=cmd_labels)


def register_projects(sub):
    p_proj = sub.add_parser("projects", help="Listar los proyectos de Plane",
                               description="Proyectos disponibles en Plane, desde la caché local (--refresh la actualiza).")
    p_proj.add_argument("--refresh", action="store_true", help="Forzar sincronización remota con la API de Plane")
    add_json_flag(p_proj)
    p_proj.set_defaults(handler=cmd_projects)


def register_whoami(sub):
    p_whoami = sub.add_parser("whoami", help="Mostrar workspace, usuario y UUID activos",
                                description="Verifica la configuración activa: workspace, usuario y UUID resuelto.")
    p_whoami.set_defaults(handler=cmd_whoami)
