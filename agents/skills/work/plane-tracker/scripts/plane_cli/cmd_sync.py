"""Comando `sync`: mantenimiento con coste en peticiones, nunca implícito en una lectura (RFC 0021, fase 6).

Expone: register_sync(), cmd_sync().
No hace: la sincronización en sí (freshness.run_sync, worklog_sync, cache). Solo emite GET y escribe únicamente la base local; no toca Plane. Sin `--history` renueva los tickets del alcance (ignora el TTL) y sincroniza las horas del
periodo (por defecto los últimos 30 días); con `--history`, tickets (con su TTL) y después el historial de asignación y las transiciones pendientes, con presupuesto (`--budget`) y reanudable. El alcance es el proyecto
por defecto (`-p P` otro, `--all-projects` todos los accesibles). Repetir el comando continúa donde quedó.
"""

import json

from plane_cli import vocabulary
from plane_cli.config import add_json_flag, positive_int
from plane_cli.errors import CliError
from plane_cli.freshness import Env, catalogs, run_sync
from plane_cli.scope import resolve_scope
from plane_cli.scope_flags import add_scope_args
from plane_cli.views import VIEWS

DEFAULT_BUDGET = 25


def _summary(scope, history, report):
    doc = {"schema": vocabulary.SCHEMA, "status": "ok", "action": "sync", "complete": report.complete, "projects": [p.ident for p in scope.projects], "issues": report.issues}
    if report.hours is not None:
        h = report.hours
        doc["hours"] = {"period": {"from": scope.period["from"], "to": scope.period["to"]}, "synced": h.synced, "unchanged": h.unchanged, "unmeasured": h.unmeasured,
                        "incomplete": sorted(h.incomplete)}
    if report.history is not None:
        done, interrupted, left, rate = report.history
        doc["history"] = {"fetched": done, "left": left, "interrupted": interrupted, "rate_limited": rate}
    return doc


def _text(doc):
    lines = [f"\n🔄 sync · {', '.join(doc['projects'])}"]
    if doc.get("issues"):
        lines += [f"   tickets {ident}: {status}" for ident, status in doc["issues"].items()]
    if "hours" in doc:
        h = doc["hours"]
        lines.append(f"   horas {h['period']['from']} → {h['period']['to']}: {h['synced']} registro(s) nuevos o actualizados, {h['unchanged']} ticket(s) sin cambios"
                     + (f"; incompleto en {', '.join(h['incomplete'])}" if h["incomplete"] else ""))
    if "history" in doc:
        h = doc["history"]
        lines.append(f"   historial: {h['fetched']} ticket(s) traído(s), {h['left']} pendiente(s)" + ("; se detuvo por el límite de peticiones" if h["rate_limited"] else "; interrumpido" if h["interrupted"] else ""))
    lines.append("   ✔ Al día." if doc["complete"] else "   ⚠ Quedó a medias: repite `plane-tracker sync` (continúa donde quedó).")
    return "\n".join(lines) + "\n"


def cmd_sync(args, conn, base_url, api_key, workspace, default_project_id):
    """`sync`: tickets del alcance y horas del periodo, o con `--history` el historial pendiente; solo GET."""
    if args.budget is not None and not args.history:
        raise CliError("usage", "--budget solo aplica con --history.", "Usa `plane-tracker sync --history --budget N`.")
    target = getattr(args, "target", "all") or "all"
    deep = getattr(args, "deep", False)
    env = Env(base_url, api_key, workspace, default_project_id)
    need_actor = (target in ("all", "hours")) and not args.history
    cats = catalogs(conn, env, need_actor=need_actor)
    scope = resolve_scope(args, cats, VIEWS["sync"])
    if not scope.projects:
        raise CliError("unknown_project", "No hay proyecto por defecto accesible.", f"Usa -p PRJ ({', '.join(p.ident for p in cats.projects)}) o --all-projects.")
    if need_actor and not cats.actor:  # decisión 6: sin identidad no se mezclan horas ajenas
        raise CliError("actor_unknown", "No sé quién eres.", "Define PLANE_ACTOR_UUID o PLANE_USERNAME (`plane-tracker whoami` lo comprueba).")
    doc = _summary(scope, args.history, run_sync(conn, env, scope, history=args.history, budget=args.budget or DEFAULT_BUDGET, target=target, deep=deep))
    print(json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if getattr(args, "json", False) else _text(doc), end="\n" if getattr(args, "json", False) else "")


def register_sync(sub):
    view = VIEWS["sync"]
    p = sub.add_parser("sync", help="Sincronizar con Plane: --history",
                       description="Mantenimiento con coste en peticiones (solo GET; escribe solo la base local). Sin flags: tickets del proyecto por defecto y sus horas de los últimos 30 días "
                                   "(-p otro proyecto, --all-projects todos, --from/--to/--week otro periodo). Con target opcional: 'tickets' (solo tickets), 'hours' (solo horas), "
                                   "'catalogs' (proyectos/etiquetas) o 'all' (por defecto). Con --history: tickets y después el historial de asignación.")
    p.add_argument("target", nargs="?", default="all", choices=["all", "tickets", "hours", "catalogs"],
                   help="Qué sincronizar: tickets, hours, catalogs o all (por defecto)")
    add_scope_args(p, view.dims, view.controls)
    p.add_argument("--deep", action="store_true", help="Reconciliación completa (ignora marcas de agua delta)")
    p.add_argument("--history", action="store_true", help="Traer el historial de asignación y las transiciones de los tickets pendientes (1 petición por ticket; reanuda donde quedó)")
    p.add_argument("--budget", type=positive_int, metavar="N", help=f"Máximo de tickets por ejecución de --history (por defecto {DEFAULT_BUDGET})")
    add_json_flag(p)
    p.set_defaults(handler=cmd_sync)
