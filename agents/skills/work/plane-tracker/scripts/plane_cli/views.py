"""Registro de vistas de lectura: cada vista es una tupla de metadatos y funciones, sin jerarquía.

Expone: View, VIEWS, LIST_LIMIT.
No hace: orquestar la lectura (eso lo hace el comando: catálogos, resolve_scope, freshness, query, envelope, output). De este registro salen los flags de cada
comando, la matriz del árbol de comandos y las pruebas de arquitectura (F2: los flags de un comando son los de sus dims y controls más `extra_flags`).
La firma de `query` depende de la vista (cada una consulta una fuente distinta); `render` siempre recibe el sobre.
"""

from dataclasses import dataclass, field
from typing import Callable

from plane_cli import (query_agenda, query_catalogs, query_check, query_flow, query_get, query_issues, query_misc, query_time, render_agenda, render_catalogs, render_check, render_flow, render_get,
                       render_issues, render_misc, render_time)

LIST_LIMIT = 20


@dataclass(frozen=True)
class View:
    name: str
    dims: frozenset
    controls: frozenset
    query: Callable      # solo lee SQLite (o transforma lo ya adquirido): nunca toca la red
    render: Callable     # (sobre) -> texto: nunca recibe la base de datos
    defaults: dict = field(default_factory=dict)
    acquisition: str = ""  # qué refresca freshness (documentación; el código está en freshness)
    command: tuple = ()    # argv del comando que sirve la vista (para F2, F5, F6 y F7)
    extra_flags: frozenset = frozenset()  # flags del comando que no son dimensiones ni controles


NONE = frozenset()
SYNC_DAYS = 30  # ventana por defecto de `sync` (sin --from/--to/--week)
VIEWS = {
    "list": View("list", frozenset({"projects", "person", "state", "text"}), frozenset({"limit", "refresh", "offline", "brief", "verbose"}),
                 query_issues.query, render_issues.render, {"limit": LIST_LIMIT, "state": "all"},
                 "tickets de los proyectos accesibles del alcance (TTL 30 min; --refresh fuerza; --offline no toca la red)", ("list",)),
    "get": View("get", NONE, NONE, query_get.query, render_get.render, {}, "el ticket por su etiqueta (1 GET) y sus comentarios; la instantánea guardada de respaldo",
                ("get",), frozenset({"--no-comments", "--last", "--full", "--no-description", "--history", "--include", "--all"})),
    "labels": View("labels", NONE, frozenset({"refresh", "offline"}), query_catalogs.labels, render_catalogs.render_labels, {},
                   "etiquetas del proyecto (TTL 1 día)", ("labels",), frozenset({"-p", "--project"})),
    "projects": View("projects", NONE, frozenset({"refresh", "offline"}), query_catalogs.projects, render_catalogs.render_projects, {},
                     "proyectos del workspace (TTL 1 día)", ("projects",)),
    "whoami": View("whoami", NONE, NONE, query_misc.whoami, render_misc.render_whoami, {}, "identidad: variables de entorno, la guardada o /members/", ("whoami",)),
    "attachment list": View("attachment list", NONE, NONE, query_misc.attachments, render_misc.render_attachments, {}, "siempre red: adjuntos del ticket",
                            ("attachment", "list")),
    "report time": View("report time", frozenset({"projects", "period"}), frozenset({"refresh", "offline", "verbose"}), query_time.query, render_time.render,
                        {"person": "hours_author", "projects": "all", "order": "date,start_time,ticket"},
                        "horas del autor en el periodo: sincronización por proyecto y periodo si falta o venció (5 min); --offline no toca la red", ("report", "time"),
                        frozenset({"--track", "--worker-type", "--plan", "--markdown"})),
    "report flow": View("report flow", frozenset({"projects", "period"}), frozenset({"refresh", "offline", "verbose"}), query_flow.query, render_flow.render,
                        {"projects": "all", "order": "ticket"}, "tickets del alcance y las transiciones de los tickets del periodo que falten o hayan cambiado (1 GET por ticket)",
                        ("report", "flow"),
                        frozenset({"--markdown"})),
    "worklog check": View("worklog check", frozenset({"projects", "period"}), NONE, query_check.query, render_check.render, {"projects": "all", "order": "ticket,date,start_time"},
                          "siempre red: auditoría de los comentarios de cada ticket con registros locales", ("worklog", "check")),
    # `sync` no es una vista de lectura (escribe en la base local), pero comparte alcance y flags con ellas: sin consulta ni render propios (la salida de las escrituras es de la fase 8)
    "sync": View("sync", frozenset({"projects", "period"}), NONE, None, None, {"period_days": SYNC_DAYS}, "tickets del alcance y horas del periodo, o con --history el historial de asignación y las transiciones",
                 ("sync",), frozenset({"--history", "--budget", "--deep"})),
    "outbox list": View("outbox list", NONE, NONE, query_misc.outbox, render_misc.render_outbox, {"state": "open"}, "solo la cola local", ("outbox", "list"),
                        frozenset({"--all"})),
    "agenda": View("agenda", frozenset({"projects"}), frozenset({"refresh", "offline", "brief", "verbose"}), query_agenda.query, render_agenda.render,
                   {"projects": "all", "order": "role_rank,priority,-plane_updated_at"},
                   "tickets de los proyectos accesibles del alcance (TTL 30 min; --refresh fuerza; --offline no toca la red)", ("agenda",),
                   frozenset({"--wip-limit", "--stalled-days", "--markdown"})),
}
