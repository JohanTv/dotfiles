"""Punto de entrada de la CLI: parser raíz, árbol de comandos y despacho.

Expone: COMMANDS, add_group(), command_tree(), build_parser(), main().
No hace: lógica de comandos (vive en cmd_*.py).
COMMANDS define el árbol y el orden de `--help`: cada entrada es un registrador (comando raíz) o una tupla
(nombre, ayuda, registradores) que declara un grupo `<sustantivo> <verbo>`. El arranque es: parsear argumentos,
validar el entorno y solo entonces abrir la base de datos (así `--help` funciona sin credenciales).
"""

import argparse
import os

from plane_cli import attachments, cmd_comment, cmd_comment_ops, cmd_ops, cmd_read, cmd_report, cmd_tickets_write
from plane_cli.config import add_json_flag, get_env_or_fail
from plane_cli.db import get_db, init_db

COMMANDS = (
    cmd_read.register_search,
    cmd_read.register_get,
    cmd_read.register_list,
    cmd_tickets_write.register_create,
    cmd_tickets_write.register_update,
    ("comment", "Comentarios: add | edit | delete",
     (cmd_comment.register_comment_add, cmd_comment_ops.register_comment_edit, cmd_comment_ops.register_comment_delete)),
    ("attachment", "Adjuntos: add | list | delete | replace",
     (attachments.register_attachment_add, attachments.register_attachment_list, attachments.register_attachment_delete,
      attachments.register_attachment_replace)),
    ("link", "Enlaces: add", (cmd_tickets_write.register_link_add,)),
    ("focus", "Foco de la sesión: set | clear | status",
     (cmd_ops.register_focus_set, cmd_ops.register_focus_clear, cmd_ops.register_focus_status)),
    ("worklog", "Tiempos: propose | check", (cmd_comment_ops.register_worklog_propose, cmd_report.register_worklog_check)),
    cmd_report.register_report,
    cmd_ops.register_handoff,
    cmd_read.register_labels,
    cmd_read.register_projects,
    cmd_read.register_whoami,
    cmd_ops.register_health,
)


def add_group(sub, name, help, registrars):
    """Grupo `<name> <verbo>`: el verbo es obligatorio y `--json` se acepta antes de él."""
    group = sub.add_parser(name, help=help, description=help)
    add_json_flag(group, hidden=True)
    verbs = group.add_subparsers(dest="verb", required=True)
    for register in registrars:
        register(verbs)
    verbs.metavar = "{" + ",".join(verbs.choices) + "}"
    return group


def _subparsers_of(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def command_tree(parser):
    """{comando: (verbos...)} del parser; los comandos raíz sin verbos llevan una tupla vacía."""
    root = _subparsers_of(parser)
    tree = {}
    for name, child in (root.choices if root else {}).items():
        verbs = _subparsers_of(child)
        tree[name] = tuple(verbs.choices) if verbs else ()
    return tree


def build_parser():
    parser = argparse.ArgumentParser(description="CLI de Plane CE para Agentes de IA y Reportes de Actividad (v2.3 SQLite3)")
    add_json_flag(parser, help="Salida en formato JSON para agentes")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<comando>")
    for entry in COMMANDS:
        if callable(entry):
            entry(subparsers)
        else:
            add_group(subparsers, *entry)
    return parser


def main():
    args = build_parser().parse_args()

    base_url = get_env_or_fail("PLANE_BASE_URL", "URL de Plane")
    api_key = get_env_or_fail("PLANE_API_KEY", "API Key de Plane")
    workspace = os.environ.get("PLANE_WORKSPACE_SLUG", "teamprogra")
    default_project_id = os.environ.get("PLANE_PROJECT_ID", "58371da4-cf62-4299-8fd4-99c1052b2eb3")

    conn = get_db()
    init_db(conn)

    try:
        args.handler(args, conn, base_url, api_key, workspace, default_project_id)
    finally:
        conn.close()
