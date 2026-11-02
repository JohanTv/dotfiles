"""Comandos de lectura: `get`, `list`, `labels`, `projects` y `whoami`.

Expone: register_get(), register_list(), register_labels(), register_projects(), register_whoami(),
y los cmd_* correspondientes.
No hace: escribir en Plane.
"""

import argparse
import os
import sys

from plane_cli.config import add_json_flag, positive_int
from plane_cli.envelope import build
from plane_cli.freshness import Env, catalogs, ensure, ensure_catalog, ensure_get, resolve_identity
from plane_cli.output import emit
from plane_cli.scope import PERSON_FLAGS, resolve_scope, single_project
from plane_cli.scope_flags import add_scope_args
from plane_cli.views import LIST_LIMIT, VIEWS
from plane_cli.vocabulary import GET_INCLUDES, GET_INCLUDES_COVERED


def _include_list(value):
    """`--include a,b`: valores separados por comas; uno desconocido es un error de uso con las opciones."""
    items = [v.strip() for v in value.split(",") if v.strip()]
    bad = [v for v in items if v not in GET_INCLUDES]
    if bad or not items:
        raise argparse.ArgumentTypeError(f"valor no válido: {', '.join(bad) or value!r} (opciones: {', '.join(GET_INCLUDES)})")
    return items


def cmd_get(args, conn, base_url, api_key, workspace, default_project_id):
    """`get`: el ticket (1 GET) y sus comentarios -> sobre sin `scope`; con red caída, la última lectura guardada. El texto es un render del mismo sobre."""
    view = VIEWS["get"]
    asked = [i for group in args.include for i in group] + (list(GET_INCLUDES) if args.all else [])
    include = tuple(dict.fromkeys(asked))
    source = ensure_get(conn, Env(base_url, api_key, workspace, default_project_id), args.issue, skip_comments=args.no_comments, history=args.history, include=include)
    doc = build(view.name, None, view.query(conn, source, last=args.last, no_description=args.no_description))
    emit(view, doc, getattr(args, "json", False), **({} if getattr(args, "json", False) else {"full": args.full}))


def cmd_list(args, conn, base_url, api_key, workspace, default_project_id):
    """`list`: catálogos -> alcance -> frescura -> consulta -> sobre; el texto es un render del mismo sobre que el JSON."""
    view = VIEWS["list"]
    env = Env(base_url, api_key, workspace, default_project_id)
    if args.offline:
        os.environ["PLANE_OFFLINE"] = "1"  # --offline corta toda la red del proceso
    cats = catalogs(conn, env, need_actor=any(getattr(args, flag, False) for flag, _ in PERSON_FLAGS))
    scope = resolve_scope(args, cats, view)
    acquisition = ensure(conn, env, view.name, scope, cats)
    doc = build(view.name, scope.to_dict(view), view.query(conn, scope, cats, acquisition), verbose=args.verbose)
    emit(view, doc, getattr(args, "json", False))


def _cache_only(args):
    if args.offline:
        os.environ["PLANE_OFFLINE"] = "1"  # --offline corta toda la red del proceso


def cmd_labels(args, conn, base_url, api_key, workspace, default_project_id):
    """`labels`: las etiquetas de un proyecto desde la caché (TTL de un día; --refresh la renueva)."""
    view, env = VIEWS["labels"], Env(base_url, api_key, workspace, default_project_id)
    _cache_only(args)
    project = single_project(args, catalogs(conn, env))
    coverage = ensure_catalog(conn, env, "labels", project, refresh=args.refresh)
    emit(view, build(view.name, {"projects": [project.ident], "order": "name"}, view.query(conn, project, coverage)), getattr(args, "json", False))


def cmd_projects(args, conn, base_url, api_key, workspace, default_project_id):
    """`projects`: los proyectos del workspace desde la caché (TTL de un día; --refresh la renueva)."""
    view, env = VIEWS["projects"], Env(base_url, api_key, workspace, default_project_id)
    _cache_only(args)
    coverage = ensure_catalog(conn, env, "projects", refresh=args.refresh)
    emit(view, build(view.name, {"order": "identifier"}, view.query(conn, workspace, coverage)), getattr(args, "json", False))


def cmd_whoami(args, conn, base_url, api_key, workspace, default_project_id):
    """`whoami`: la configuración activa y si la identidad se resuelve; sale con 1 si `PLANE_USERNAME` no coincide con ningún miembro."""
    view = VIEWS["whoami"]
    identity, coverage = resolve_identity(conn, Env(base_url, api_key, workspace, default_project_id))
    emit(view, build(view.name, None, view.query(identity, coverage)), getattr(args, "json", False))
    if identity["status"] == "unresolved":
        sys.exit(1)


def register_get(sub):
    p_get = sub.add_parser("get", help="Ver un ticket con sus comentarios")
    p_get.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    add_json_flag(p_get)
    p_get.add_argument("--no-comments", action="store_true", help="No traer ni mostrar comentarios (ahorra tokens)")
    p_get.add_argument("--last", type=positive_int, metavar="N", help="Mostrar solo los últimos N comentarios (por defecto: todos)")
    p_get.add_argument("--full", action="store_true", help="Sin truncar descripción ni comentarios en el texto (por defecto 300 caracteres)")
    p_get.add_argument("--no-description", action="store_true", help="Omitir la descripción")
    p_get.add_argument("--history", action="store_true", help="Añadir flujo: lead/cycle time, tiempo por estado, esfuerzo y transiciones")
    p_get.add_argument("--include", type=_include_list, action="append", default=[], metavar="LISTA",
                       help=f"Añadir {', '.join(GET_INCLUDES_COVERED)} (1 GET cada uno); también relations y children, que aún no se implementan")
    p_get.add_argument("--all", action="store_true", help="Todo lo incluible (--include con todos los valores)")
    p_get.set_defaults(handler=cmd_get)


def register_list(sub):
    view = VIEWS["list"]
    p_list = sub.add_parser("list", help="Listar y buscar tickets (caché)",
                            description="Tickets de la caché local, refrescada por TTL (30 min) con solo GET. Combina -p/--all-projects, --mine|--created|--involved, "
                                        "--open y --text (título y etiquetas, por relevancia). Con --json, sobre plane-tracker/1 con alcance, cobertura y notas.")
    add_scope_args(p_list, view.dims, view.controls, LIST_LIMIT)
    add_json_flag(p_list)
    p_list.set_defaults(handler=cmd_list)


def register_labels(sub):
    view = VIEWS["labels"]
    p_labels = sub.add_parser("labels", help="Listar las etiquetas del proyecto",
                              description="Etiquetas disponibles en un proyecto, desde la caché local (--refresh la actualiza; --offline no consulta Plane).")
    p_labels.add_argument("-p", "--project", help="Identificador del proyecto (por defecto, el del entorno)")
    add_scope_args(p_labels, view.dims, view.controls)
    add_json_flag(p_labels)
    p_labels.set_defaults(handler=cmd_labels)


def register_projects(sub):
    view = VIEWS["projects"]
    p_proj = sub.add_parser("projects", help="Listar los proyectos de Plane",
                            description="Proyectos disponibles en Plane, desde la caché local (--refresh la actualiza; --offline no consulta Plane).")
    add_scope_args(p_proj, view.dims, view.controls)
    add_json_flag(p_proj)
    p_proj.set_defaults(handler=cmd_projects)


def register_whoami(sub):
    p_whoami = sub.add_parser("whoami", help="Mostrar workspace, usuario y UUID activos",
                              description="Verifica la configuración activa: workspace, usuario y UUID resuelto.")
    add_json_flag(p_whoami)
    p_whoami.set_defaults(handler=cmd_whoami)
