"""Frescura de las lecturas: carga de catálogos y adquisición de datos; única vía a la red de las vistas, y solo con GET.

Expone: Env, Catalogs, catalogs(), ensure().
No hace: consultar filas para el usuario (query_*), imprimir ni escribir en Plane. Cada vista declara qué refresca (modelo de consulta, contrato de adquisición):
`list` sincroniza los tickets de los proyectos accesibles del alcance con TTL de 30 min (`--refresh` fuerza, `--offline` no toca la red). Cada proyecto se trata por
separado: uno caído o sin acceso (403) no aborta el resto y queda en la cobertura (`unavailable`, `forbidden`); sin ningún dato disponible, error `no_cache`.
Lo que ya va en la cobertura no se repite por stderr: los avisos de datos vencidos de las capas bajas se silencian aquí.
"""

import contextlib
import io
from collections import namedtuple
from dataclasses import dataclass
from typing import Callable

from plane_cli import cache, clock
from plane_cli.api import PlaneUnavailable
from plane_cli.coverage import Coverage
from plane_cli.errors import CliError
from plane_cli.resolve import PROJECTS_TTL, get_actor_uuid, get_labels_map, get_members_map, get_projects_map, known_actor
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
    with contextlib.redirect_stderr(io.StringIO()):
        return fn(*args, **kwargs)


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
