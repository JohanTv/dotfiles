"""Frescura de las lecturas: carga de catálogos y adquisición de datos; única vía a la red de las vistas, y solo con GET.

Expone: Env, Catalogs, TicketSource, AuditData, catalogs(), ensure(), ensure_get(), ensure_catalog(), fetch_attachments(), resolve_identity(), ensure_hours(), ensure_flow(),
audit_worklogs(), SyncReport, run_sync().
No hace: consultar filas para el usuario (query_*), imprimir ni escribir en Plane. Cada vista declara qué refresca (modelo de consulta, contrato de adquisición):
`list` sincroniza los tickets de los proyectos accesibles del alcance con TTL de 30 min (`--refresh` fuerza, `--offline` no toca la red). Cada proyecto se trata por
separado: uno caído o sin acceso (403) no aborta el resto y queda en la cobertura (`unavailable`, `forbidden`); sin ningún dato disponible, error `no_cache`.
Lo que ya va en la cobertura no se repite por stderr: los avisos de datos vencidos de las capas bajas se silencian aquí.
"""

import contextlib, io, os, sys
from collections import namedtuple
from dataclasses import dataclass, replace
from typing import Callable
import urllib.error

from plane_cli import cache, clock, store_transitions, store_worklogs
from plane_cli.api import PlaneUnavailable, api_request
from plane_cli.assignments import sweep_history
from plane_cli.cache import fail_no_cache, offline_issue, save_snapshot
from plane_cli.coverage import Coverage
from plane_cli.errors import CliError
from plane_cli.flow import build_ticket_flow, fetch_transitions, flow_to_json, transitions_fresh
from plane_cli.outbox import open_keys
from plane_cli.resolve import (PROJECTS_TTL, get_actor_uuid, get_labels_map, get_members_map, get_projects_map, get_states_map, known_actor,
                               resolve_issue, resolve_issue_by_label, resolve_project_and_seq)
from plane_cli.scope import ProjectRef
from plane_cli.timeutil import iso_z
from plane_cli.vocabulary import GET_INCLUDES_COVERED
from plane_cli.worklog import check_worklogs, extract_metadata_from_comment, find_metadata_block
from plane_cli.worklog_sync import REPORT_SYNC_TIMEOUT, SYNC_COOLDOWN, sync_remote_worklogs

Env = namedtuple("Env", "base_url api_key workspace default_project_id")


@dataclass(frozen=True)
class Catalogs:
    projects: tuple          # ProjectRef de los proyectos accesibles (miembro y no archivado)
    default: str | None      # identificador del proyecto por defecto
    actor: str | None        # UUID de quien usa la herramienta, si se necesitó y se sabe
    member_names: Callable   # () -> {UUID: nombre}, perezoso y memoizado: solo se pide si hay asignados que mostrar
    stale: bool = False      # el catálogo de proyectos se sirvió vencido
    today: str = ""          # hoy en el calendario local (YYYY-MM-DD), para los periodos por defecto
    tz: str = ""             # desplazamiento de la zona local con que se interpretan los periodos (+HH:MM)
    workspace: str = ""      # slug del workspace activo


def _quiet(fn, *args, **kwargs):
    """Silencia el stderr de las capas bajas (los avisos de datos vencidos ya van en la cobertura), pero no un error que termina el programa."""
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stderr(buffer):
            return fn(*args, **kwargs)
    except SystemExit:
        sys.stderr.write(buffer.getvalue())
        raise


def _actor(conn, env):
    actor = known_actor(conn, env.workspace)
    if actor:
        return actor
    try:
        return _quiet(get_actor_uuid, env.base_url, env.api_key, env.workspace, conn)
    except PlaneUnavailable:
        return None


def _local_projects(conn):
    """Proyectos que se pueden inferir de lo almacenado (horas y tickets) cuando no hay catálogo: solo identificadores, sin UUID."""
    idents = {r[0] for r in conn.execute("SELECT DISTINCT project_id FROM worklogs")}
    idents |= {r[0].rsplit("-", 1)[0] for r in conn.execute("SELECT DISTINCT ticket_id FROM issues_cache")}
    return {i: {"id": "", "name": "", "identifier": i, "accessible": True} for i in sorted(idents) if i and i != "GENERAL"}


def catalogs(conn, env, need_actor=False, local_fallback=False):
    """Catálogos de la lectura: proyectos accesibles, proyecto por defecto, actor (solo con `need_actor`) y nombres de miembros (perezosos).

    Con `local_fallback` (reportes), sin red ni catálogo de proyectos se usan los que se infieren de lo almacenado en vez de fallar: se lee lo local y la cobertura lo dice."""
    try:
        projects = _quiet(get_projects_map, conn, env.base_url, env.api_key, env.workspace)
    except PlaneUnavailable:
        if not local_fallback:
            raise
        projects = _local_projects(conn)
    oldest = conn.execute("SELECT MIN(updated_at) FROM projects WHERE workspace = ?", (env.workspace,)).fetchone()[0]
    accessible = tuple(ProjectRef(ident, p["id"], p["name"]) for ident, p in sorted(projects.items()) if p.get("accessible", True))
    default = next((p.ident for p in accessible if p.uuid == env.default_project_id), None)
    memo = {}

    def member_names():
        if "names" not in memo:
            memo["names"] = _quiet(get_members_map, conn, env.base_url, env.api_key, env.workspace)
        return memo["names"]

    offset = clock.now().astimezone().strftime("%z")
    return Catalogs(accessible, default, _actor(conn, env) if need_actor else None, member_names,
                    stale=bool(oldest) and clock.timestamp() - oldest >= PROJECTS_TTL, today=clock.local_today().isoformat(), tz=f"{offset[:3]}:{offset[3:]}",
                    workspace=env.workspace)


def _outdated(conn, project_id):
    """Una caché anterior al modelo (sin asignados o sin recuento del servidor) se renueva aunque no haya vencido."""
    return bool(conn.execute("SELECT 1 FROM issues_cache WHERE project_id = ? AND assignees_json IS NULL LIMIT 1", (project_id,)).fetchone()) \
        or not conn.execute("SELECT 1 FROM issue_sync WHERE project_id = ?", (project_id,)).fetchone()


def _refresh_labels(conn, env, project_id):
    """Las etiquetas van antes que los tickets para que `labels_csv` lleve sus nombres; sin ellas se sincroniza igual."""
    try:
        _quiet(get_labels_map, conn, env.base_url, env.api_key, env.workspace, project_id, raise_http=True)
    except Exception:
        pass


def _ensure_issues(conn, env, scope, deep=False):
    statuses = {}
    for project in scope.projects:
        force = scope.refresh or _outdated(conn, project.uuid) or deep
        if not scope.offline and cache.needs_sync(conn, project.uuid, force) and cache._budget_ok():  # sin presupuesto no se pide ni lo accesorio
            _refresh_labels(conn, env, project.uuid)
        statuses[project.ident] = cache.sync_project_issues(conn, env.base_url, env.api_key, env.workspace, project.uuid, project.ident,
                                                            force_refresh=force, offline=scope.offline, deep=deep)
    return statuses


def ensure(conn, env, view_name, scope, cats):
    """Cobertura de adquisición de la vista tras refrescar lo que su contrato declara (hoy solo `list`)."""
    if view_name != "list":
        raise ValueError(f"adquisición no definida para la vista {view_name}")
    statuses = _ensure_issues(conn, env, scope)
    usable = {i for i, (st, as_of) in statuses.items() if as_of is not None and st != "forbidden"}
    unavailable = sorted(i for i, (st, _) in statuses.items() if st != "forbidden" and i not in usable)
    forbidden = sorted(i for i, (st, _) in statuses.items() if st == "forbidden")
    if statuses and not usable and unavailable:
        raise CliError("no_cache", f"Plane no responde y no hay caché local de los tickets de {', '.join(unavailable)}.", "Conéctate y usa --refresh.")
    rate = any(st == "rate_limited" for st, _ in statuses.values())
    as_ofs = [as_of for i, (_, as_of) in statuses.items() if i in usable]
    oldest = min(as_ofs) if as_ofs else None
    detail = {k: v for k, v in {"forbidden": forbidden, "rate_budget_exhausted": rate}.items() if v}
    return Coverage(source="cache", as_of=iso_z(oldest) if oldest else None, age_s=int(clock.timestamp() - oldest) if oldest else None,
                    stale=cats.stale or any(st in ("stale", "rate_limited") for st, _ in statuses.values()), unavailable=tuple(unavailable), detail=detail)


# --- get: un ticket y sus comentarios (API por diseño, con la última lectura guardada como respaldo) -------------------------------------
@dataclass(frozen=True)
class TicketSource:
    issue: dict               # el ticket tal como lo devolvió Plane (o la instantánea)
    comments: list | None     # None: no se pidieron (--no-comments) o no se pudieron leer
    comments_read: bool       # los comentarios se leyeron completos de la API
    issue_ref: str            # PRJ-12
    project_id: str
    coverage: Coverage        # source api | snapshot; sin `complete` (lo calcula la consulta)
    metadata_only: bool = False   # solo había los metadatos del listado: sin descripción ni comentarios
    state_name: str | None = None
    flow: dict | None = None      # con --history: métricas de flujo y transiciones con nombres de estado
    attachments: list | None = None  # con --include attachments: lo que devolvió la API (None: no se pidió o no se pudo leer)
    links: list | None = None
    include: tuple = ()           # incluibles pedidos que `get` cubre (attachments, links)
    not_covered: tuple = ()       # incluibles pedidos que aún no se implementan (relations, children)


def _fetch_comments(env, project_id, issue):
    """Comentarios del ticket, o None si no se pudieron traer (el ticket se muestra igual)."""
    url = f"{env.base_url.rstrip('/')}/api/v1/workspaces/{env.workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
    try:
        return api_request(url, env.api_key).get("results", [])
    except Exception:
        return None


def _names_for(conn, env, project_id, issue):
    """Estados, miembros y etiquetas del proyecto en la caché local (con su TTL), para dar nombres; si al ticket le falta alguna etiqueta en la caché, se refresca una vez."""
    def fetch_all():
        for fetch in (lambda: get_states_map(conn, env.base_url, env.api_key, env.workspace, project_id),
                      lambda: get_members_map(conn, env.base_url, env.api_key, env.workspace),
                      lambda: get_labels_map(conn, env.base_url, env.api_key, env.workspace, project_id)):
            try:
                _quiet(fetch)
            except (PlaneUnavailable, urllib.error.URLError, OSError):
                pass
    fetch_all()
    wanted = {i.get("id") if isinstance(i, dict) else i for i in issue.get("labels") or []}
    known = {r["id"] for r in conn.execute("SELECT id FROM labels WHERE project_id = ?", (project_id,))}
    if wanted - known:  # una etiqueta creada después de la última sincronización: 1 GET para ponerla al día
        try:
            _quiet(get_labels_map, conn, env.base_url, env.api_key, env.workspace, project_id, force_refresh=True)
        except (PlaneUnavailable, urllib.error.URLError, OSError):
            pass


def _flow_json(conn, env, project_id, issue, issue_ref):
    flow, transitions, states = build_ticket_flow(conn, env.base_url, env.api_key, env.workspace, project_id, issue, issue_ref)
    if flow is None:
        return None
    out = flow_to_json(flow)
    out["transitions"] = [{"at": t["at"].isoformat(), "from": states.get(t["from_id"], {}).get("name", "?"), "to": states.get(t["to_id"], {}).get("name", "?")}
                          for t in transitions]
    return out


def _get_pages(url, api_key, limit_pages=10):
    """Todos los elementos de una lectura que puede ser una lista plana (adjuntos) o paginada (enlaces); None si no se pudo leer."""
    items, cursor = [], None
    try:
        for _ in range(limit_pages):
            data = api_request(url + (f"?cursor={cursor}" if cursor else ""), api_key)
            if isinstance(data, list):
                return data
            items += data.get("results", [])
            cursor = data.get("next_cursor")
            if not data.get("next_page_results") or not cursor:
                return items
    except (PlaneUnavailable, urllib.error.URLError, OSError):
        return None
    return None  # más páginas de las que se siguen: no se afirma que esté completo


def _read_includes(env, project_id, issue, include):
    """{incluible: elementos | None} de los incluibles cubiertos que se pidieron; cada uno cuesta 1 GET."""
    root = f"{env.base_url.rstrip('/')}/api/v1/workspaces/{env.workspace}/projects/{project_id}/issues/{issue['id']}"
    paths = {"attachments": "issue-attachments/", "links": "links/"}
    return {name: _get_pages(f"{root}/{paths[name]}", env.api_key) for name in include}


def ensure_get(conn, env, issue_arg, skip_comments=False, history=False, include=()):
    """Pide el ticket (1 GET por su etiqueta) y sus comentarios, guarda la instantánea y devuelve la fuente; sin red usa la última lectura guardada.

    `include` (de GET_INCLUDES) pide además adjuntos y/o enlaces (1 GET cada uno, solo en línea); `relations` y `children` no se implementan: se anotan en `not_covered`.
    """
    not_covered = tuple(i for i in include if i not in GET_INCLUDES_COVERED)
    include = tuple(i for i in include if i in GET_INCLUDES_COVERED)
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, env.base_url, env.api_key, env.workspace, env.default_project_id, issue_arg)
    now = clock.timestamp()
    try:
        if uuid_ref:
            issue = resolve_issue(env.base_url, env.api_key, env.workspace, project_id, None, uuid_ref)
        else:
            issue = resolve_issue_by_label(env.base_url, env.api_key, env.workspace, issue_ref,
                                           lambda: resolve_issue(env.base_url, env.api_key, env.workspace, project_id, seq_id, None))
        comments = None if skip_comments else _fetch_comments(env, project_id, issue)
        save_snapshot(conn, issue, issue_ref, comments)
        extra = _read_includes(env, project_id, issue, include)
        source = TicketSource(issue, comments, comments is not None, issue_ref, project_id, Coverage(source="api", as_of=iso_z(now), age_s=0),
                              attachments=extra.get("attachments"), links=extra.get("links"), include=include, not_covered=not_covered)
        _names_for(conn, env, project_id, issue)
    except PlaneUnavailable:
        local = offline_issue(conn, project_id, seq_id, uuid_ref, issue_ref) or fail_no_cache(issue_ref)
        coverage = Coverage(source="snapshot", as_of=iso_z(local["fetched_at"]), age_s=int(now - local["fetched_at"]), stale=True)
        source = TicketSource(local["issue"], local["comments"] if not skip_comments else None, False, issue_ref, project_id, coverage,
                              metadata_only=local["metadata_only"], state_name=local["state_name"], include=include, not_covered=not_covered)
    if history:
        source = replace(source, flow=_flow_json(conn, env, project_id, source.issue, issue_ref))
    return source


# --- catálogos de un solo proyecto o del workspace (labels, projects) -------------------------------------------------------------------
def ensure_catalog(conn, env, kind, project=None, refresh=False):
    """Refresca (con TTL de un día) las etiquetas de `project` o los proyectos del workspace y devuelve su cobertura: vencido (red caída o --offline) => stale y complete null."""
    if kind == "projects":
        _quiet(get_projects_map, conn, env.base_url, env.api_key, env.workspace, force_refresh=refresh)
        oldest = conn.execute("SELECT MIN(updated_at) FROM projects WHERE workspace = ?", (env.workspace,)).fetchone()[0]
    else:
        _quiet(get_labels_map, conn, env.base_url, env.api_key, env.workspace, project.uuid, force_refresh=refresh)
        oldest = conn.execute("SELECT MIN(updated_at) FROM labels WHERE project_id = ?", (project.uuid,)).fetchone()[0]
    stale = bool(oldest) and clock.timestamp() - oldest >= PROJECTS_TTL
    return Coverage(source="cache", as_of=iso_z(oldest) if oldest else None, age_s=int(clock.timestamp() - oldest) if oldest else None, stale=stale,
                    complete=None if stale or not oldest else True)


# --- attachment list: una lectura de red (GET) ------------------------------------------------------------------------------------------
def fetch_attachments(conn, env, issue_arg):
    """(etiqueta del ticket, adjuntos crudos, Coverage de la API). `complete` solo es true si Plane no anuncia más páginas."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, env.base_url, env.api_key, env.workspace, env.default_project_id, issue_arg)
    issue = resolve_issue(env.base_url, env.api_key, env.workspace, project_id, seq_id, uuid_ref, issue_ref=issue_ref)
    data = api_request(f"{env.base_url.rstrip('/')}/api/v1/workspaces/{env.workspace}/projects/{project_id}/issues/{issue['id']}/issue-attachments/", env.api_key)
    items = data if isinstance(data, list) else data.get("results", [])
    more = isinstance(data, dict) and bool(data.get("next_page_results"))
    return issue_ref, items, Coverage(source="api", as_of=iso_z(clock.timestamp()), age_s=0, complete=None if more else True)


# --- whoami: de dónde sale la identidad ----------------------------------------------------------------------------------------------------
def resolve_identity(conn, env):
    """(fila `whoami`, Coverage): `actor_env` y la identidad ya guardada son locales; resolver `PLANE_USERNAME` con /members/ es una lectura de la API."""
    username = os.environ.get("PLANE_USERNAME", "").strip()
    explicit = os.environ.get("PLANE_ACTOR_UUID", "").strip()
    row = {"workspace": env.workspace, "base_url": env.base_url, "actor": None, "username": username or None, "source": "unset", "status": "unset"}
    if explicit:
        return {**row, "actor": explicit, "source": "actor_env", "status": "ok"}, Coverage(source="local", complete=True)
    if not username:
        return row, Coverage(source="local")
    cached = known_actor(conn, env.workspace)
    actor = cached or _quiet(get_actor_uuid, env.base_url, env.api_key, env.workspace)
    row.update(actor=actor, source="username", status="ok" if actor else "unresolved")
    return row, Coverage(source="local" if cached else "api", complete=True if actor else None)


# --- report time: horas del autor, sincronizadas por proyecto y periodo (defecto 0010) ---------------------------------------------------------
def _offline(scope):
    """`--offline` o PLANE_OFFLINE=1: no se intenta ninguna petición."""
    return scope.offline or os.environ.get("PLANE_OFFLINE") == "1"


def ensure_hours(conn, env, scope):
    """Sincroniza las horas si se fuerza o si algún proyecto del alcance no tiene una sincronización completa y reciente que cubra el periodo; `--offline` no toca la red. Con red lenta degrada a local (timeout 3s).

    Cobertura: `cache` si se sincronizó ahora, si no `local`; `hours_verified` dice si cada proyecto está verificado para todo el periodo y `hours_scope` es `local` si no lo está
    (nota `hours_local_only`). Datos verificados pero más viejos que el enfriamiento, servidos porque no hubo red, constan como vencidos (`stale`).
    """
    idents, period = [p.ident for p in scope.projects], scope.period
    status = store_worklogs.hours_status(conn, idents, period["from"], period["to"])
    now, synced, failed, forbidden = clock.timestamp(), False, False, []
    offline = _offline(scope)
    need_sync = scope.refresh or not (status.verified and now - status.as_of <= SYNC_COOLDOWN)
    if not offline and need_sync:
        try:
            res = sync_remote_worklogs(conn, env.base_url, env.api_key, env.workspace, period["from"], period["to"],
                                       filter_project=idents[0] if len(idents) == 1 else None, force=scope.refresh,
                                       timeout=REPORT_SYNC_TIMEOUT)
            failed, synced = bool(res.unavailable), not res.unavailable
            if res.forbidden:
                forbidden = sorted(res.forbidden)
        except PlaneUnavailable:
            failed = True
        status = store_worklogs.hours_status(conn, idents, period["from"], period["to"])
    old = status.as_of is not None and clock.timestamp() - status.as_of > SYNC_COOLDOWN
    detail = {"hours_verified": status.verified, "hours_scope": "synced" if status.verified else "local"}
    if forbidden:
        detail["forbidden"] = forbidden
    return Coverage(source="cache" if synced else "local", as_of=iso_z(status.as_of) if status.as_of else None,
                    age_s=int(clock.timestamp() - status.as_of) if status.as_of else None, stale=old and (failed or offline),
                    detail=detail)


# --- report flow: tickets del periodo y sus transiciones (mixto: tickets + actividades; viable sin conexión sobre lo almacenado) --------------------
def ensure_flow(conn, env, scope, cats):
    """Sincroniza los tickets del alcance (como `list`) y trae las transiciones de los tickets del periodo que falten o hayan cambiado (1 GET por ticket); se detiene
    antes de agotar el presupuesto de tasa. Con `--offline` no pide nada. La cobertura es `mixed`; el recuento de transiciones al día lo añade la consulta."""
    try:
        base = ensure(conn, env, "list", scope, cats)
    except CliError as exc:  # sin tickets en caché ni red: el flujo sale vacío y la cobertura lo dice (`source_unavailable`)
        if exc.code != "no_cache":
            raise
        base = Coverage(source="cache", unavailable=tuple(p.ident for p in scope.projects))
    labels = store_transitions.flow_tickets(conn, [p.ident for p in scope.projects], scope.period["from"], scope.period["to"], scope.period["tz"])
    rows, rate = store_transitions.issue_rows(conn, labels), False
    offline = _offline(scope)
    if scope.refresh and not offline:
        with conn:
            conn.executemany("DELETE FROM flow_fetch WHERE issue_id = ?", [(r["id"],) for r in rows.values()])
    for label in () if offline else labels:
        row = rows.get(label)
        issue = {"id": row["id"], "updated_at": row["plane_updated_at"], "completed_at": row["completed_at"]} if row else None
        if issue is None or transitions_fresh(conn, issue):
            continue
        if not cache._budget_ok():
            rate = True
            break
        try:
            fetch_transitions(conn, env.base_url, env.api_key, env.workspace, row["project_id"], issue, label, strict=True)
        except (PlaneUnavailable, urllib.error.URLError, OSError):
            return replace(base, source="mixed", stale=True)
    detail = dict(base.detail, **({"rate_budget_exhausted": True} if rate else {}))
    return replace(base, source="mixed", stale=base.stale or rate, detail=detail)


# --- worklog check: auditoría contra Plane (siempre red, solo GET) ------------------------------------------------------------------------------
@dataclass(frozen=True)
class AuditData:
    checked: list   # [{ticket, worklogs}] de los tickets con registros locales en el periodo
    issues: list    # {code, ticket, comment_id, detail}


def audit_worklogs(conn, env, scope):
    """Compara los registros locales del periodo con los comentarios de cada ticket en Plane. (AuditData, Coverage de la API); un ticket que no responde queda `unreachable`."""
    idents, period = [p.ident for p in scope.projects], scope.period
    by_ticket = {}
    for r in store_worklogs.rows(conn, idents, period["from"], period["to"]):
        by_ticket.setdefault(r["ticket_id"], []).append(dict(r))
    issues, checked, pending = [], [], open_keys(conn)
    for label, t_rows in sorted(by_ticket.items()):
        try:
            project_id, seq_id, uuid_ref, _ref = resolve_project_and_seq(conn, env.base_url, env.api_key, env.workspace, env.default_project_id, label)
            issue = resolve_issue(env.base_url, env.api_key, env.workspace, project_id, seq_id, uuid_ref, issue_ref=_ref)
            raw = api_request(f"{env.base_url.rstrip('/')}/api/v1/workspaces/{env.workspace}/projects/{project_id}/issues/{issue['id']}/comments/", env.api_key,
                              raise_on_error=True).get("results", [])
        except (SystemExit, urllib.error.URLError, OSError):
            issues.append({"code": "unreachable", "ticket": label, "comment_id": None, "detail": "no se pudo consultar el ticket en Plane"})
            continue
        comments = {}
        for c in raw:
            html = c.get("comment_html") or ""
            has_block = bool(find_metadata_block(html))
            comments[c["id"]] = {"has_block": has_block, "meta": extract_metadata_from_comment(html) if has_block else None}
        issues += check_worklogs(t_rows, comments, period["from"], period["to"], pending)
        checked.append({"ticket": label, "worklogs": len(t_rows)})
    unreachable = sum(1 for i in issues if i["code"] == "unreachable")
    return AuditData(checked, issues), Coverage(source="api", as_of=iso_z(clock.timestamp()), age_s=0, complete=unreachable == 0)


# --- sync: mantenimiento con coste en peticiones (solo GET; escribe únicamente la base local) ------------------------------------------------------
@dataclass(frozen=True)
class SyncReport:
    issues: dict      # proyecto -> estado de la sincronización de tickets (synced, fresh, stale, rate_limited, forbidden, unavailable)
    hours: object     # SyncResult de las horas, o None (con --history o si Plane no respondió)
    history: tuple    # (tickets traídos, interrumpido, pendientes, por presupuesto de tasa) del barrido de historial, o None
    complete: bool    # todo lo pedido quedó al día; si no, repetir el comando continúa donde quedó


def _sweep(conn, env, project_ids, budget):
    """Historial de asignación y transiciones de hasta `budget` tickets pendientes del alcance (1 GET por ticket), reanudable; para al agotar el presupuesto de tasa."""
    rows = conn.execute(f"SELECT * FROM issues_cache WHERE project_id IN ({','.join('?' for _ in project_ids)})", list(project_ids)).fetchall() if project_ids else []
    state = {"rate": False}

    def fetch(row):
        if not cache._budget_ok():
            state["rate"] = True
            raise OSError("presupuesto de tasa")
        issue = {"id": row["id"], "updated_at": row["plane_updated_at"], "completed_at": row["completed_at"]}
        return fetch_transitions(conn, env.base_url, env.api_key, env.workspace, row["project_id"], issue, row["ticket_id"], strict=True)

    done, interrupted, left = sweep_history(conn, env.base_url, env.api_key, env.workspace, rows, budget, fetch)
    return done, interrupted, left, state["rate"]


def run_sync(conn, env, scope, history=False, budget=25, target="all", deep=False):
    """Sincroniza los recursos del alcance según target ('all', 'tickets', 'hours', 'catalogs') con delta sync (RFC 0027)."""
    issues = {}
    hours, swept = None, None
    if target in ("all", "tickets"):
        issues = {ident: status for ident, (status, _as_of) in _ensure_issues(conn, env, replace(scope, refresh=not history), deep=deep).items()}
    if target == "catalogs":
        for project in scope.projects:
            _refresh_labels(conn, env, project.uuid)
    if history and target in ("all", "tickets"):
        swept = _sweep(conn, env, [p.uuid for p in scope.projects], budget)
    elif target in ("all", "hours") and not history:
        idents, period = [p.ident for p in scope.projects], scope.period
        try:
            hours = sync_remote_worklogs(conn, env.base_url, env.api_key, env.workspace, period["from"], period["to"],
                                         filter_project=idents[0] if len(idents) == 1 else None, force=deep)
        except PlaneUnavailable:
            hours = None
    complete = (not issues or all(s in ("synced", "fresh") for s in issues.values())) \
        and (swept is None or (swept[2] == 0 and not swept[1])) \
        and (history or hours is None or (not hours.unavailable and not hours.incomplete))
    return SyncReport(issues, hours, swept, complete)
