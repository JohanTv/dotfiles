"""Declaración de los flags compartidos de las vistas de lectura: cada vista solo tiene los flags de las dimensiones y controles que acepta.

Expone: add_scope_args(), flags_for(), DIMENSION_FLAGS, CONTROL_FLAGS.
No hace: validar valores (eso es scope.resolve_scope) ni leer el entorno. Lo que una vista no acepta no tiene flag y argparse lo rechaza (código 2).
"""

from plane_cli.config import positive_int

DIMENSION_FLAGS = {"projects": ("-p", "--project", "--all-projects"), "person": ("--mine", "--created", "--involved"), "state": ("--open",),
                   "text": ("--text",), "period": ()}
CONTROL_FLAGS = {"limit": ("--limit",), "refresh": ("--refresh",), "offline": ("--offline",), "brief": ("--brief",), "verbose": ("--verbose",)}


def flags_for(dims, controls):
    """Conjunto de opciones que una vista con estas dimensiones y controles puede declarar."""
    return {flag for dim in dims for flag in DIMENSION_FLAGS[dim]} | {flag for ctl in controls for flag in CONTROL_FLAGS[ctl]}


def add_scope_args(parser, dims, controls, default_limit=None):
    if "projects" in dims:
        parser.add_argument("-p", "--project", help="Identificador del proyecto (ej: OMNIFY, OPS)")
        parser.add_argument("--all-projects", action="store_true", help="Todos los proyectos accesibles del workspace")
    if "person" in dims:
        who = parser.add_mutually_exclusive_group()
        who.add_argument("--mine", action="store_true", help="Solo los asignados a ti (según la última sincronización)")
        who.add_argument("--created", action="store_true", help="Solo los creados por ti")
        who.add_argument("--involved", action="store_true", help="Asignados, creados, con horas tuyas o asignados alguna vez, con la razón de cada uno")
    if "state" in dims:
        parser.add_argument("--open", action="store_true", help="Sin completados, cancelados ni archivados")
    if "text" in dims:
        parser.add_argument("--text", metavar="TEXTO", help="Buscar en título y etiquetas (ordena por relevancia)")
    if "limit" in controls:
        parser.add_argument("--limit", type=positive_int, metavar="N", help=f"Máximo de tickets (por defecto {default_limit})")
    if "refresh" in controls:
        parser.add_argument("--refresh", action="store_true", help="Forzar la sincronización con Plane")
    if "offline" in controls:
        parser.add_argument("--offline", action="store_true", help="No consultar Plane: solo lo local")
    if "brief" in controls:
        parser.add_argument("--brief", action="store_true", help="Filas breves: ticket, title, state, state_group y project")
    if "verbose" in controls:
        parser.add_argument("--verbose", action="store_true", help="Incluir las notas informativas")
