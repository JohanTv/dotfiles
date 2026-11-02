"""Alcance de una lectura: qué proyectos, qué persona, qué estado y qué texto, validado una vez contra catálogos ya cargados.

Expone: Scope, ProjectRef, resolve_scope().
No hace: red, SQLite ni imprimir. `resolve_scope` es puro: valida contra los catálogos que recibe (freshness.catalogs los carga antes) y lanza CliError
(`unknown_project`, `actor_unknown`) con la pista de corrección. Ningún comando valida por su cuenta.
Una vista declara `dims` (dimensiones que acepta), `controls` y `defaults`; el alcance solo lleva lo que la vista acepta.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

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
        if "period" in view.dims and self.period:
            doc["period"] = dict(self.period)
        if view.defaults.get("person") == "hours_author" and self.hours_author:
            doc["hours_author"] = self.hours_author
        for name in ("track", "worker_type"):
            if getattr(self, name):
                doc[name] = getattr(self, name)
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
    if getattr(args, "all_projects", False) or (view and view.defaults.get("projects") == "all" and not getattr(args, "project", None)):
        return tuple(catalogs.projects)
    asked = getattr(args, "project", None)
    if asked:
        ident = asked.upper()
        if ident not in by_ident:
            raise CliError("unknown_project", f"Proyecto '{asked}' no encontrado.", f"Opciones: {', '.join(by_ident)}. Usa -p {next(iter(by_ident), 'PRJ')}.")
        return (by_ident[ident],)
    default = by_ident.get(catalogs.default)
    return (default,) if default else ()


def _day(text, flag):
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise CliError("bad_date", f"Fecha inválida en {flag}: '{text}'.", "Usa YYYY-MM-DD.") from None


def _period(args, catalogs, view_days=None):
    """{from, to, tz} (fechas inclusivas del calendario local): `--week` es la semana ISO en curso; `--from` solo es ese día; `--to` sin `--from` es un error; sin nada, hoy."""
    first, last, week = getattr(args, "date_from", None), getattr(args, "date_to", None), getattr(args, "week", False)
    today = date.fromisoformat(catalogs.today)
    if week and (first or last):
        raise CliError("bad_period", "--week no se combina con --from ni --to.", "Usa --week o un rango con --from/--to.")
    if last and not first and not week:
        raise CliError("bad_period", "--to necesita --from.", "Usa --from <fecha> --to <fecha>, o --from <fecha> solo para un día.")
    if week:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif not first and view_days:
        start, end = today - timedelta(days=view_days), today  # el mantenimiento (`sync`) cubre una ventana de días, no solo hoy
    else:
        start = _day(first, "--from") if first else today
        end = _day(last, "--to") if last else start
    if end < start:
        raise CliError("bad_period", f"El periodo está invertido: {start} es posterior a {end}.", "Usa --from <fecha anterior> --to <fecha posterior>.")
    return {"from": start.isoformat(), "to": end.isoformat(), "tz": catalogs.tz}


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
    hours_author = None
    if view.defaults.get("person") == "hours_author":  # las vistas de horas son personales: el autor es quien las pide, sin flag para ver a otros
        hours_author = catalogs.actor
        if not hours_author:
            raise CliError("actor_unknown", "No sé quién eres.", "Define PLANE_ACTOR_UUID o PLANE_USERNAME (`plane-tracker whoami` lo comprueba).")
    return Scope(projects=_projects(args, catalogs, view) if "projects" in view.dims else (),
                 ticket_person={"relation": person, "actor": catalogs.actor} if person else None,
                 state="open" if getattr(args, "open", False) else view.defaults.get("state", "all"), text=text,
                 period=_period(args, catalogs, view.defaults.get("period_days")) if "period" in view.dims else None, hours_author=hours_author,
                 track=getattr(args, "track", None), worker_type=getattr(args, "worker_type", None),
                 order=view.defaults["order"] if "order" in view.defaults else ORDER_TEXT if text else ORDER_RECENT, limit=limit, offline=bool(getattr(args, "offline", False)),
                 refresh=bool(getattr(args, "refresh", False)), brief=bool(getattr(args, "brief", False)))
