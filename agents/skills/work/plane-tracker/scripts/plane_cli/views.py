"""Registro de vistas de lectura: cada vista es una tupla de metadatos y funciones, sin jerarquía.

Expone: View, VIEWS, LIST_LIMIT.
No hace: orquestar la lectura (eso lo hace el comando: catálogos, resolve_scope, freshness, query, envelope, output). De este registro salen los flags de cada
comando, la matriz del árbol de comandos y las pruebas de arquitectura (F2: los flags de un comando son los de sus dims y controls más `extra_flags`).
La firma de `query` depende de la vista (cada una consulta una fuente distinta); `render` siempre recibe el sobre.
"""

from dataclasses import dataclass, field
from typing import Callable

from plane_cli import query_catalogs, query_get, query_issues, query_misc, render_catalogs, render_get, render_issues, render_misc

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
VIEWS = {
    "list": View("list", frozenset({"projects", "person", "state", "text"}), frozenset({"limit", "refresh", "offline", "brief", "verbose"}),
                 query_issues.query, render_issues.render, {"limit": LIST_LIMIT, "state": "all"},
                 "tickets de los proyectos accesibles del alcance (TTL 30 min; --refresh fuerza; --offline no toca la red)", ("list",),
                 frozenset({"--refresh-history", "--budget"})),
    "get": View("get", NONE, NONE, query_get.query, render_get.render, {}, "el ticket por su etiqueta (1 GET) y sus comentarios; la instantánea guardada de respaldo",
                ("get",), frozenset({"--no-comments", "--last", "--full", "--no-description", "--history"})),
    "labels": View("labels", NONE, frozenset({"refresh", "offline"}), query_catalogs.labels, render_catalogs.render_labels, {},
                   "etiquetas del proyecto (TTL 1 día)", ("labels",), frozenset({"-p", "--project"})),
    "projects": View("projects", NONE, frozenset({"refresh", "offline"}), query_catalogs.projects, render_catalogs.render_projects, {},
                     "proyectos del workspace (TTL 1 día)", ("projects",)),
    "whoami": View("whoami", NONE, NONE, query_misc.whoami, render_misc.render_whoami, {}, "identidad: variables de entorno, la guardada o /members/", ("whoami",)),
    "attachment list": View("attachment list", NONE, NONE, query_misc.attachments, render_misc.render_attachments, {}, "siempre red: adjuntos del ticket",
                            ("attachment", "list")),
    "outbox list": View("outbox list", NONE, NONE, query_misc.outbox, render_misc.render_outbox, {"state": "open"}, "solo la cola local", ("outbox", "list"),
                        frozenset({"--all"})),
}
