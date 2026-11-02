"""Alcance de una lectura: qué proyectos, qué persona, qué estado y qué texto, validado una vez contra catálogos ya cargados.

Expone: Scope, ProjectRef, resolve_scope().
No hace: red, SQLite ni imprimir. `resolve_scope` es puro: valida contra los catálogos que recibe (freshness.catalogs los carga antes) y lanza CliError
(`unknown_project`, `actor_unknown`) con la pista de corrección. Ningún comando valida por su cuenta.
Una vista declara `dims` (dimensiones que acepta), `controls` y `defaults`; el alcance solo lleva lo que la vista acepta.
"""

from dataclasses import dataclass

from plane_cli.errors import CliError

PERSON_FLAGS = (("mine", "assigned"), ("created", "created"), ("involved", "involved"))
ORDER_TEXT, ORDER_RECENT = "rank,-sequence", "-updated,project,-sequence"


@dataclass(frozen=True)
class ProjectRef:
    ident: str
    uuid: str
    name: str = ""


@dataclass(frozen=True)
class Scope:
    projects: tuple = ()
    ticket_person: dict | None = None  # {"relation": assigned | created | involved, "actor": uuid}
    hours_author: str | None = None
    period: dict | None = None
    state: str = "all"
    text: str | None = None
    order: str = ORDER_RECENT
    limit: int | None = None
    offline: bool = False
    refresh: bool = False
    brief: bool = False
    track: str | None = None
    worker_type: str | None = None

    def to_dict(self, view):
        """El `scope` del sobre: solo las dimensiones de la vista, ya resueltas (`order` y `limit` siempre que la vista pagina)."""
        doc = {}
        if "projects" in view.dims:
            doc["projects"] = [p.ident for p in self.projects]
        if "person" in view.dims and self.ticket_person:
            doc["ticket_person"] = dict(self.ticket_person)
        if "state" in view.dims:
            doc["state"] = self.state
        if "text" in view.dims and self.text:
            doc["text"] = self.text
        doc["order"] = self.order
        if self.limit is not None:
            doc["limit"] = self.limit
        return doc


def _projects(args, catalogs, view):
    by_ident = {p.ident: p for p in catalogs.projects}
    if getattr(args, "all_projects", False):
        return tuple(catalogs.projects)
    asked = getattr(args, "project", None)
    if asked:
        ident = asked.upper()
        if ident not in by_ident:
            raise CliError("unknown_project", f"Proyecto '{asked}' no encontrado.", f"Opciones: {', '.join(by_ident)}. Usa -p {next(iter(by_ident), 'PRJ')}.")
        return (by_ident[ident],)
    default = by_ident.get(catalogs.default)
    return (default,) if default else ()


def single_project(args, catalogs):
    """El proyecto de `-p` (o el de por defecto) para las vistas de catálogo de un solo proyecto; unknown_project con la lista de opciones."""
    projects = _projects(args, catalogs, None)
    if not projects:
        raise CliError("unknown_project", "No hay proyecto por defecto accesible.", f"Opciones: {', '.join(p.ident for p in catalogs.projects)}. Usa -p PRJ.")
    return projects[0]


def resolve_scope(args, catalogs, view):
    """Scope validado de `args` para `view` (View con dims, controls y defaults) frente a `catalogs` (proyectos accesibles, proyecto por defecto y actor)."""
    person = next((relation for flag, relation in PERSON_FLAGS if getattr(args, flag, False)), None) if "person" in view.dims else None
    if person and not catalogs.actor:
        raise CliError("actor_unknown", "No sé quién eres.", "Define PLANE_ACTOR_UUID o PLANE_USERNAME (`plane-tracker whoami` lo comprueba).")
    text = (getattr(args, "text", None) or "").strip() or None
    limit = getattr(args, "limit", None) or view.defaults.get("limit")
    return Scope(projects=_projects(args, catalogs, view) if "projects" in view.dims else (),
                 ticket_person={"relation": person, "actor": catalogs.actor} if person else None,
                 state="open" if getattr(args, "open", False) else view.defaults.get("state", "all"), text=text,
                 order=ORDER_TEXT if text else ORDER_RECENT, limit=limit, offline=bool(getattr(args, "offline", False)),
                 refresh=bool(getattr(args, "refresh", False)), brief=bool(getattr(args, "brief", False)))
