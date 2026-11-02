"""Comandos `report time`, `report flow` y `worklog check`: cada uno orquesta alcance, frescura, consulta, sobre y salida; el cálculo vive en query_* y el texto en render_*.

Expone: register_report_time(), register_report_flow(), register_worklog_check(), cmd_report_time(), cmd_report_flow(), cmd_worklog_check().
No hace: lógica de reportes. `report` es un grupo con vista obligatoria (`report` a secas lo rechaza `renamed.py` con código 2). El periodo es `--from/--to/--week` (sin `--date` ni `--today`).
`worklog check` sale con 1 si hay inconsistencias y con 3 si algún ticket no se pudo comprobar y no hay inconsistencias.
"""

import os
import sys

from plane_cli import vocabulary
from plane_cli.config import add_json_flag
from plane_cli.envelope import build
from plane_cli.freshness import Env, audit_worklogs, catalogs, ensure_flow, ensure_hours
from plane_cli.output import emit
from plane_cli.scope import resolve_scope
from plane_cli.scope_flags import add_scope_args
from plane_cli.views import VIEWS


def _scope(args, conn, base_url, api_key, workspace, default_project_id, view, personal, local_fallback=True):
    env = Env(base_url, api_key, workspace, default_project_id)
    if getattr(args, "offline", False):
        os.environ["PLANE_OFFLINE"] = "1"  # --offline corta toda la red del proceso
    cats = catalogs(conn, env, need_actor=personal, local_fallback=local_fallback)
    return env, cats, resolve_scope(args, cats, view)


def cmd_report_time(args, conn, base_url, api_key, workspace, default_project_id):
    """`report time`: las horas del autor en el periodo (sincroniza por proyecto y periodo si hace falta); el texto es un render del mismo sobre que el JSON."""
    view = VIEWS["report time"]
    env, _cats, scope = _scope(args, conn, base_url, api_key, workspace, default_project_id, view, personal=True)
    doc = build(view.name, scope.to_dict(view), view.query(conn, scope, ensure_hours(conn, env, scope)), verbose=args.verbose)
    emit(view, doc, getattr(args, "json", False))


def cmd_report_flow(args, conn, base_url, api_key, workspace, default_project_id):
    """`report flow`: lead/cycle time y esfuerzo por ticket del periodo; con `--offline` se calcula con lo almacenado."""
    view = VIEWS["report flow"]
    env, cats, scope = _scope(args, conn, base_url, api_key, workspace, default_project_id, view, personal=False)
    doc = build(view.name, scope.to_dict(view), view.query(conn, scope, ensure_flow(conn, env, scope, cats)), verbose=args.verbose)
    emit(view, doc, getattr(args, "json", False))


def cmd_worklog_check(args, conn, base_url, api_key, workspace, default_project_id):
    """`worklog check`: auditoría contra Plane (solo lectura); sale con 1 si hay inconsistencias y con 3 si faltó comprobar algún ticket."""
    view = VIEWS["worklog check"]
    env, _cats, scope = _scope(args, conn, base_url, api_key, workspace, default_project_id, view, personal=False, local_fallback=False)
    audit, coverage = audit_worklogs(conn, env, scope)
    doc = build(view.name, scope.to_dict(view), view.query(audit, coverage))
    emit(view, doc, getattr(args, "json", False))
    errors = [i for i in audit.issues if i["code"] in vocabulary.CHECK_ERROR_CODES]
    if errors or doc["summary"]["unreachable"]:
        sys.exit(1 if errors else 3)


def register_report_time(sub):
    view = VIEWS["report time"]
    p = sub.add_parser("time", help="Horas registradas por día y ticket",
                       description="Horas del autor en el periodo (por defecto hoy) con Interval Merging; sincroniza con Plane por proyecto y periodo si falta o venció (5 min). "
                                   "Sin conexión usa lo local y lo dice (--offline). Con --json, sobre plane-tracker/1 con resumen por día, proyecto y balde.")
    add_scope_args(p, view.dims, view.controls)
    p.add_argument("--track", help="Filtrar por track (ej: main, subagent)")
    p.add_argument("--worker-type", help="Filtrar por tipo de trabajador (human, subagent)")
    add_json_flag(p)
    p.set_defaults(handler=cmd_report_time)


def register_report_flow(sub):
    view = VIEWS["report flow"]
    p = sub.add_parser("flow", help="Flujo por ticket del periodo",
                       description="Lead/cycle time, tiempo por estado y esfuerzo de los tickets con horas en el periodo o cerrados en él. Se calcula con lo almacenado: "
                                   "--refresh trae las transiciones que falten (1 GET por ticket) y --offline no consulta Plane.")
    add_scope_args(p, view.dims, view.controls)
    add_json_flag(p)
    p.set_defaults(handler=cmd_report_flow)


def register_worklog_check(sub):
    view = VIEWS["worklog check"]
    p = sub.add_parser("check", help="Comparar los worklogs locales con Plane",
                       description="Solo lectura: compara los worklogs locales con sus comentarios en Plane (duplicados, huérfanos, diferencias). Sale con código 1 si hay inconsistencias "
                                   "y con 3 si algún ticket no se pudo comprobar.")
    add_scope_args(p, view.dims, view.controls)
    add_json_flag(p)
    p.set_defaults(handler=cmd_worklog_check)
