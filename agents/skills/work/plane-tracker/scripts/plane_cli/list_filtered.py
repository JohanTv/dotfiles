"""`list` con filtros de persona y estado, resuelto sobre la caché local de tickets.

Expone: add_list_filter_flags(), wants_filtered(), cmd_list_filtered().
No hace: escribir en Plane. Sin filtros `list` sigue pidiendo a la API (cmd_read.cmd_list); aquí solo entra la vista filtrada.
Qué significa cada modo (ver docs/decisions/0019):
  --mine      asignado ahora (según la última sincronización de la caché);
  --created   creador del ticket;
  --involved  la unión de asignado, creador, con horas tuyas (autor registrado en la base local) y asignado alguna vez (historial medido), con la razón de cada uno.
Nunca se afirma lo que no se midió: el aviso de cobertura dice cuántos tickets tienen el historial verificado y que las horas salen solo de la base local.
"""

import json
import sys

import flow_metrics

from plane_cli import clock
from plane_cli.assignments import assignment_events_for, history_coverage, sweep_history
from plane_cli.cache import fail_no_cache
from plane_cli.timeutil import age_text, iso_utc
from plane_cli.config import add_json_flag, positive_int
from plane_cli.flow import fetch_transitions
from plane_cli.resolve import get_members_map, get_projects_map, require_actor, sync_issues
from plane_cli.api import PlaneUnavailable

DEFAULT_LIMIT = 30
DEFAULT_BUDGET = 25
_MODES = (("mine", "asignados a ti"), ("created", "creados por ti"), ("involved", "en los que estás involucrado"))


def add_list_filter_flags(parser):
    who = parser.add_mutually_exclusive_group()
    who.add_argument("--mine", action="store_true", help="Solo los asignados a ti (según la última sincronización)")
    who.add_argument("--created", action="store_true", help="Solo los creados por ti")
    who.add_argument("--involved", action="store_true", help="Asignados, creados, con horas tuyas o asignados alguna vez, con la razón de cada uno")
    parser.add_argument("--open", action="store_true", help="Sin completados, cancelados ni archivados")
    parser.add_argument("--all-projects", action="store_true", help="Todos los proyectos del workspace")
    parser.add_argument("--limit", type=positive_int, default=DEFAULT_LIMIT, metavar="N", help=f"Máximo de tickets a mostrar (por defecto {DEFAULT_LIMIT})")
    parser.add_argument("--refresh", action="store_true", help="Forzar la sincronización de tickets con Plane")
    parser.add_argument("--refresh-history", action="store_true",
                        help="Traer el historial de asignación de los tickets pendientes (una petición por ticket; reanuda donde quedó)")
    parser.add_argument("--budget", type=positive_int, default=DEFAULT_BUDGET, metavar="N",
                        help=f"Máximo de tickets por ejecución de --refresh-history (por defecto {DEFAULT_BUDGET})")


def wants_filtered(args):
    return any(getattr(args, name, False) for name in ("mine", "created", "involved", "open", "all_projects", "refresh_history", "refresh"))


def _mode(args):
    return next((name for name, _ in _MODES if getattr(args, name, False)), None)


def _scope(args, conn, base_url, api_key, workspace, default_project_id):
    """[(identificador, UUID)] de los proyectos a consultar."""
    projects = get_projects_map(conn, base_url, api_key, workspace)
    if getattr(args, "all_projects", False):
        return [(ident, p["id"]) for ident, p in projects.items()]
    if getattr(args, "project", None):
        ident = args.project.upper()
        if ident not in projects:
            sys.stderr.write(f"Error: Proyecto '{args.project}' no encontrado. Opciones: {', '.join(projects)}\n")
            sys.exit(1)
        return [(ident, projects[ident]["id"])]
    return [(next((i for i, p in projects.items() if p["id"] == default_project_id), "?"), default_project_id)]


def _sync(conn, base_url, api_key, workspace, scope, refresh):
    """Sincroniza cada proyecto del alcance. Con varios, uno que no responda ni tenga caché no aborta el resto: se devuelve su identificador."""
    missing = []
    for ident, project_id in scope:
        # Una caché anterior a esta función no guarda asignados: se renueva aunque no haya vencido.
        outdated = conn.execute("SELECT 1 FROM issues_cache WHERE project_id = ? AND assignees_json IS NULL LIMIT 1", (project_id,)).fetchone()
        try:
            sync_issues(conn, base_url, api_key, workspace, project_id, ident, force_refresh=refresh or bool(outdated))
        except PlaneUnavailable:
            if len(scope) == 1:
                raise
            missing.append(ident)
    return missing


def _select(conn, project_ids, mode, actor, open_only):
    """(tickets que cumplen el modo, cuántos se saltaron por no tener datos de asignación). Cada uno con sus razones."""
    marks = ",".join("?" for _ in project_ids)
    rows = conn.execute(f"SELECT * FROM issues_cache WHERE project_id IN ({marks}) ORDER BY sequence_id DESC", project_ids).fetchall()
    mine_min, unsigned_min = {}, {}
    for r in conn.execute("SELECT ticket_id, author_id, SUM(duration_minutes) AS m FROM worklogs GROUP BY ticket_id, author_id"):
        if r["author_id"] is None:
            unsigned_min[r["ticket_id"]] = r["m"]
        elif r["author_id"] == actor:
            mine_min[r["ticket_id"]] = r["m"]
    ever = {r["issue_id"] for r in conn.execute("SELECT DISTINCT issue_id FROM assignment_events WHERE user_id = ? AND kind = 'added'", (actor,))} if actor else set()
    out, unknown = [], 0
    for row in rows:
        if open_only and (row["state_group"] in flow_metrics.TERMINAL_GROUPS or row["archived_at"]):
            continue
        if mode and row["assignees_json"] is None:
            unknown += 1
            continue
        assignees = json.loads(row["assignees_json"] or "[]")
        reasons = []
        if actor and actor in assignees:
            reasons.append("asignado")
        if actor and row["created_by"] == actor:
            reasons.append("creador")
        if mode == "involved":
            if mine_min.get(row["ticket_id"]):
                reasons.append(f"horas tuyas ({mine_min[row['ticket_id']]} min)")
            elif unsigned_min.get(row["ticket_id"]):
                reasons.append(f"horas sin autor registrado ({unsigned_min[row['ticket_id']]} min)")
            if row["id"] in ever and "asignado" not in reasons:
                reasons.append("fue asignado")
        keep = {None: True, "mine": "asignado" in reasons, "created": "creador" in reasons, "involved": bool(reasons)}[mode]
        if keep:
            out.append({"row": row, "assignees": assignees, "reasons": reasons})
    return out, unknown


def _run_sweep(conn, base_url, api_key, workspace, project_ids, budget):
    marks = ",".join("?" for _ in project_ids)
    rows = conn.execute(f"SELECT * FROM issues_cache WHERE project_id IN ({marks})", project_ids).fetchall()
    fetch = lambda r: fetch_transitions(conn, base_url, api_key, workspace, r["project_id"],
                                        {"id": r["id"], "updated_at": r["plane_updated_at"], "completed_at": r["completed_at"]}, r["ticket_id"], strict=True)
    done, interrupted, left = sweep_history(conn, base_url, api_key, workspace, rows, budget, fetch)
    note = f"🔄 Historial de asignación: {done} ticket(s) traído(s)"
    if interrupted:
        note += "; interrumpido (Plane limitó o no responde), se reanuda en la próxima ejecución"
    if left:
        note += f"; quedan {left} pendiente(s)"
    sys.stderr.write(note + "\n")


def _entry(item, names, conn, mode):
    row = item["row"]
    entry = {"ticket": row["ticket_id"], "title": row["title"], "state": row["state_name"], "priority": row["priority"],
             "assignees": [{"id": a, "name": names.get(a) or a[:8]} for a in item["assignees"]], "created_by": row["created_by"],
             "reasons": item["reasons"], "plane_updated_at": row["plane_updated_at"]}
    if mode == "involved":
        entry["assignment_events"] = assignment_events_for(conn, row["id"])
    return entry


def _print(entries, total, mode, where, head, notes):
    label = dict(_MODES).get(mode)
    shown = f"{len(entries)} de {total}" if len(entries) < total else str(total)
    print(f"\n📋 Tickets {label + ' ' if label else ''}en {where} ({shown}){head}:")
    for e in entries:
        prio = f"[{e['priority'].upper()}]"
        print(f"  • {e['ticket']:<12} {e['state']:<12} {prio:<9} {e['title'][:60]}")
        who = ", ".join(a["name"] for a in e["assignees"]) or "sin asignar"
        print(f"      ↳ asignados: {who}" + (f" · razones: {', '.join(e['reasons'])}" if e["reasons"] else ""))
    for note in notes:
        print(f"  ℹ {note}")
    print("")


def cmd_list_filtered(args, conn, base_url, api_key, workspace, default_project_id):
    mode = _mode(args)
    actor = require_actor(conn, base_url, api_key, workspace) if mode else None
    scope = _scope(args, conn, base_url, api_key, workspace, default_project_id)
    missing = _sync(conn, base_url, api_key, workspace, scope, getattr(args, "refresh", False))
    project_ids = [pid for ident, pid in scope if ident not in missing]
    if not project_ids:
        fail_no_cache("los tickets de los proyectos")
    if getattr(args, "refresh_history", False):
        _run_sweep(conn, base_url, api_key, workspace, project_ids, args.budget)

    items, unknown = _select(conn, project_ids, mode, actor, getattr(args, "open", False))
    names = get_members_map(conn, base_url, api_key, workspace) if items else {}
    entries = [_entry(i, names, conn, mode) for i in items[:args.limit]]
    oldest = conn.execute(f"SELECT MIN(updated_at) FROM issues_cache WHERE project_id IN ({','.join('?' for _ in project_ids)})", project_ids).fetchone()[0]

    notes = []
    if missing:
        notes.append(f"Sin datos de {', '.join(missing)}: Plane no responde y no hay caché local.")
    if unknown:
        notes.append(f"{unknown} ticket(s) sin datos de asignación (caché anterior): conéctate con Plane para actualizarla.")
    if mode:
        notes.append("La asignación es la de la última sincronización de la caché.")
    coverage = None
    if mode == "involved":
        covered, total = history_coverage(conn, [r["id"] for r in conn.execute(
            f"SELECT id FROM issues_cache WHERE project_id IN ({','.join('?' for _ in project_ids)})", project_ids)])
        coverage = {"verified": covered, "total": total}
        notes.append(f"Historial de asignación verificado en {covered} de {total} tickets" + ("; `--refresh-history` lo amplía." if covered < total else "."))
        notes.append("Las horas salen solo de la base local de esta máquina y pueden faltar (defecto 0017).")
        unsigned = conn.execute("SELECT COUNT(*) FROM worklogs WHERE author_id IS NULL").fetchone()[0]
        if unsigned:
            notes.append(f"{unsigned} registro(s) de horas sin autor registrado (anteriores a esta versión o sin identidad); `report --refresh` los completa si están en Plane.")

    if getattr(args, "json", False):
        print(json.dumps({"mode": mode, "scope": [i for i, _ in scope], "count": len(entries), "total": len(items), "cached_at": iso_utc(oldest) if oldest else None,
                          "history_coverage": coverage, "notes": notes, "results": entries}, indent=2, ensure_ascii=False))
        return
    head = f" · caché de hace {age_text(clock.timestamp() - oldest)}" if oldest else ""
    where = "todos los proyectos" if getattr(args, "all_projects", False) else scope[0][0]
    if len(scope) == 1 and not getattr(args, "all_projects", False):
        notes.append("Solo este proyecto; `--all-projects` incluye los demás.")
    _print(entries, len(items), mode, where, head, notes)
