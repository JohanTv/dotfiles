"""Frescura de las lecturas: carga de catálogos y adquisición de datos; única vía a la red de las vistas, y solo con GET.

Expone: Env, Catalogs, TicketSource, catalogs(), ensure(), ensure_get(), ensure_catalog(), fetch_attachments(), resolve_identity().
No hace: consultar filas para el usuario (query_*), imprimir ni escribir en Plane. Cada vista declara qué refresca (modelo de consulta, contrato de adquisición):
`list` sincroniza los tickets de los proyectos accesibles del alcance con TTL de 30 min (`--refresh` fuerza, `--offline` no toca la red). Cada proyecto se trata por
separado: uno caído o sin acceso (403) no aborta el resto y queda en la cobertura (`unavailable`, `forbidden`); sin ningún dato disponible, error `no_cache`.
Lo que ya va en la cobertura no se repite por stderr: los avisos de datos vencidos de las capas bajas se silencian aquí.
"""

import contextlib
import io
import os
import sys
from collections import namedtuple
from dataclasses import dataclass, replace
from typing import Callable

import urllib.error

from plane_cli import cache, clock
from plane_cli.api import PlaneUnavailable, api_request
from plane_cli.cache import fail_no_cache, offline_issue, save_snapshot
from plane_cli.coverage import Coverage
from plane_cli.errors import CliError
from plane_cli.flow import build_ticket_flow, flow_to_json
from plane_cli.resolve import (PROJECTS_TTL, get_actor_uuid, get_labels_map, get_members_map, get_projects_map, get_states_map, known_actor,
                               resolve_issue, resolve_issue_by_label, resolve_project_and_seq)
from plane_cli.scope import ProjectRef
from plane_cli.timeutil import iso_z

Env = namedtuple("Env", "base_url api_key workspace default_project_id")


@dataclass(frozen=True)
class Catalogs:
    projects: tuple          # ProjectRef de los proyectos accesibles (miembro y no archivado)
    default: str | None      # identificador del proyecto por defecto
    actor: str | None        # UUID de quien usa la herramienta, si se necesitó y se sabe
    member_names: Callable   # () -> {UUID: nombre}, perezoso y memoizado: solo se pide si hay asignados que mostrar
    stale: bool = False      # el catálogo de proyectos se sirvió vencido


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


def catalogs(conn, env, need_actor=False):
    """Catálogos de la lectura: proyectos accesibles, proyecto por defecto, actor (solo con `need_actor`) y nombres de miembros (perezosos)."""
    projects = _quiet(get_projects_map, conn, env.base_url, env.api_key, env.workspace)
    oldest = conn.execute("SELECT MIN(updated_at) FROM projects WHERE workspace = ?", (env.workspace,)).fetchone()[0]
    accessible = tuple(ProjectRef(ident, p["id"], p["name"]) for ident, p in sorted(projects.items()) if p.get("accessible", True))
    default = next((p.ident for p in accessible if p.uuid == env.default_project_id), None)
    memo = {}

    def member_names():
        if "names" not in memo:
            memo["names"] = _quiet(get_members_map, conn, env.base_url, env.api_key, env.workspace)
        return memo["names"]

    return Catalogs(accessible, default, _actor(conn, env) if need_actor else None, member_names,
                    stale=bool(oldest) and clock.timestamp() - oldest >= PROJECTS_TTL)


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


def _ensure_issues(conn, env, scope):
    statuses = {}
    for project in scope.projects:
        force = scope.refresh or _outdated(conn, project.uuid)
        if not scope.offline and cache.needs_sync(conn, project.uuid, force):
            _refresh_labels(conn, env, project.uuid)
        statuses[project.ident] = cache.sync_project_issues(conn, env.base_url, env.api_key, env.workspace, project.uuid, project.ident,
                                                            force_refresh=force, offline=scope.offline)
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


def _fetch_comments(env, project_id, issue):
    """Comentarios del ticket, o None si no se pudieron traer (el ticket se muestra igual)."""
    url = f"{env.base_url.rstrip('/')}/api/v1/workspaces/{env.workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
    try:
        return api_request(url, env.api_key).get("results", [])
    except Exception:
        return None


def _names_for(conn, env, project_id):
    """Estados, miembros y etiquetas del proyecto en la caché local, para dar nombres; lo que no se pueda traer se omite sin aviso."""
    for fetch in (lambda: get_states_map(conn, env.base_url, env.api_key, env.workspace, project_id),
                  lambda: get_members_map(conn, env.base_url, env.api_key, env.workspace),
                  lambda: get_labels_map(conn, env.base_url, env.api_key, env.workspace, project_id)):
        try:
            _quiet(fetch)
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


def ensure_get(conn, env, issue_arg, skip_comments=False, history=False):
    """Pide el ticket (1 GET por su etiqueta) y sus comentarios, guarda la instantánea y devuelve la fuente; sin red usa la última lectura guardada."""
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
        source = TicketSource(issue, comments, comments is not None, issue_ref, project_id, Coverage(source="api", as_of=iso_z(now), age_s=0))
        _names_for(conn, env, project_id)
    except PlaneUnavailable:
        local = offline_issue(conn, project_id, seq_id, uuid_ref, issue_ref) or fail_no_cache(issue_ref)
        coverage = Coverage(source="snapshot", as_of=iso_z(local["fetched_at"]), age_s=int(now - local["fetched_at"]), stale=True)
        source = TicketSource(local["issue"], local["comments"] if not skip_comments else None, False, issue_ref, project_id, coverage,
                              metadata_only=local["metadata_only"], state_name=local["state_name"])
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
    issue = resolve_issue(env.base_url, env.api_key, env.workspace, project_id, seq_id, uuid_ref)
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
