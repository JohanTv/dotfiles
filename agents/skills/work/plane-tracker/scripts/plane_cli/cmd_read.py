"""Comandos de lectura: `get`, `list`, `labels`, `projects` y `whoami`.

Expone: register_get(), register_list(), register_labels(), register_projects(), register_whoami(),
y los cmd_* correspondientes.
No hace: escribir en Plane.
"""

import json
import os
import re
import sys

from plane_cli.api import PlaneUnavailable, api_request
from plane_cli.cache import fail_no_cache, offline_issue, save_snapshot
from plane_cli.envelope import build, dumps
from plane_cli.freshness import Env, catalogs, ensure
from plane_cli.history_sweep import sweep
from plane_cli.timeutil import age_text, iso_utc
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
from plane_cli import clock
from plane_cli.scope import PERSON_FLAGS, resolve_scope
from plane_cli.scope_flags import add_scope_args
from plane_cli.views import LIST_LIMIT, VIEWS


def _fetch_comments(base_url, api_key, workspace, project_id, issue):
    """Comentarios del ticket, o None si no se pudieron traer (el ticket se muestra igual)."""
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
    try:
        return api_request(url, api_key).get("results", [])
    except PlaneUnavailable:
        sys.stderr.write("⚠ No se pudieron traer los comentarios: Plane no responde.\n")
    except Exception:
        pass
    return None


def cmd_get(args, conn, base_url, api_key, workspace, default_project_id):
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    args.issue = issue_ref
    skip_comments = getattr(args, "no_comments", False)
    offline = None
    comments = None if skip_comments else []
    try:
        issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
        if not skip_comments:
            comments = _fetch_comments(base_url, api_key, workspace, project_id, issue)
        save_snapshot(conn, issue, issue_ref, comments)
    except PlaneUnavailable:
        offline = offline_issue(conn, project_id, seq_id, uuid_ref, issue_ref) or fail_no_cache(f"{issue_ref}")
        issue, comments = offline["issue"], offline["comments"]
    total_comments = len(comments or [])
    skip_comments = comments is None
    comments = comments or []
    last = getattr(args, "last", None)
    if last:
        comments = comments[-last:]
    first_idx = total_comments - len(comments) + 1
    limit = None if getattr(args, "full", False) else 300

    if offline:
        state_name = offline["state_name"] or "?"
    else:
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
        if offline:
            issue_copy.update(stale=True, fetched_at=iso_utc(offline["fetched_at"]), **({"metadata_only": True} if offline["metadata_only"] else {}))
        if getattr(args, "no_description", False):
            issue_copy.pop("description_html", None)
            issue_copy.pop("description", None)
        print(json.dumps(issue_copy, indent=2))
        return

    if offline:
        print(f"\n⚠ Datos locales de hace {age_text(clock.timestamp() - offline['fetched_at'])}; Plane no responde."
              + (" Solo metadatos del listado: sin descripción ni comentarios." if offline["metadata_only"]
                 else " Esta copia no incluye comentarios." if skip_comments else ""), end="")
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
    """`list`: catálogos -> alcance -> frescura -> consulta -> sobre; el texto es un render del mismo sobre que el JSON."""
    view = VIEWS["list"]
    env = Env(base_url, api_key, workspace, default_project_id)
    if args.offline:
        os.environ["PLANE_OFFLINE"] = "1"  # --offline corta toda la red del proceso
    cats = catalogs(conn, env, need_actor=any(getattr(args, flag, False) for flag, _ in PERSON_FLAGS))
    scope = resolve_scope(args, cats, view)
    acquisition = ensure(conn, env, view.name, scope, cats)
    if args.refresh_history:
        sweep(conn, env, [p.uuid for p in scope.projects], args.budget)
    doc = build(view.name, scope.to_dict(view), view.query(conn, scope, cats, acquisition), verbose=args.verbose)
    print(dumps(doc) if getattr(args, "json", False) else view.render(doc), end="\n" if getattr(args, "json", False) else "")


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
        print(json.dumps([{k: p[k] for k in ("id", "name", "identifier")} for p in projects_map.values()], indent=2))
        return

    print(f"\n📂 Proyectos en el workspace '{workspace}':")
    for ident, data in sorted(projects_map.items()):
        print(f"  • {ident:<14} ➔  {data['name']}")
    print(f"\n💡 Proyecto principal por defecto: OMNIFY (ej: OMNIFY-175 o solo '175').")
    print(f"   Usa 'plane-tracker projects --refresh' para forzar sincronización con el servidor Plane.\n")


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
    view = VIEWS["list"]
    p_list = sub.add_parser("list", help="Listar y buscar tickets (caché)",
                            description="Tickets de la caché local, refrescada por TTL (30 min) con solo GET. Combina -p/--all-projects, --mine|--created|--involved, "
                                        "--open y --text (título y etiquetas, por relevancia). Con --json, sobre plane-tracker/1 con alcance, cobertura y notas.")
    add_scope_args(p_list, view.dims, view.controls, LIST_LIMIT)
    p_list.add_argument("--refresh-history", action="store_true",
                        help="Traer el historial de asignación de los tickets pendientes (una petición por ticket; reanuda donde quedó)")
    p_list.add_argument("--budget", type=positive_int, default=25, metavar="N", help="Máximo de tickets por ejecución de --refresh-history (por defecto 25)")
    add_json_flag(p_list)
    p_list.set_defaults(handler=cmd_list)


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
