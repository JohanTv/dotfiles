"""Registro de vistas de lectura: cada vista es una tupla de metadatos y funciones, sin jerarquía.

Expone: View, VIEWS.
No hace: orquestar la lectura (eso lo hace el comando: catálogos, resolve_scope, freshness.ensure, query, envelope). De este registro salen los flags de cada comando,
la matriz del árbol de comandos y las pruebas de arquitectura (F2).
"""

from dataclasses import dataclass, field
from typing import Callable

from plane_cli import query_issues, render_issues

LIST_LIMIT = 20


@dataclass(frozen=True)
class View:
    name: str
    dims: frozenset
    controls: frozenset
    query: Callable      # (conn, scope, catalogs, acquisition coverage) -> Result: solo lee SQLite
    render: Callable     # (sobre) -> texto: nunca recibe la base de datos
    defaults: dict = field(default_factory=dict)
    acquisition: str = ""  # qué refresca freshness (documentación; el código está en freshness.ensure)


VIEWS = {
    "list": View("list", frozenset({"projects", "person", "state", "text"}), frozenset({"limit", "refresh", "offline", "brief", "verbose"}),
                 query_issues.query, render_issues.render, {"limit": LIST_LIMIT, "state": "all"},
                 "tickets de los proyectos accesibles del alcance (TTL 30 min; --refresh fuerza; --offline no toca la red)"),
}
