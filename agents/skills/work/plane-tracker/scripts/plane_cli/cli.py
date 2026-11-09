"""Punto de entrada de la CLI: parser raíz, árbol de comandos y despacho.

Expone: COMMANDS, add_group(), command_tree(), build_parser(), main().
No hace: lógica de comandos (vive en cmd_*.py).
Códigos de salida: 0 éxito (o comentario encolado); 1 error definitivo o de validación; 2 uso; 3 Plane no disponible (PlaneUnavailable).
Al terminar cualquier comando salvo `outbox *`, main() avisa por stderr si hay registros sin publicar.
Antes de parsear, main() consulta renamed.suggestion(): un nombre retirado o un verbo ausente termina con código 2.
COMMANDS define el árbol y el orden de `--help`: cada entrada es un registrador (comando raíz) o una tupla
(nombre, ayuda, registradores) que declara un grupo `<sustantivo> <verbo>`. El arranque es: parsear argumentos,
validar el entorno y solo entonces abrir la base de datos (así `--help` funciona sin credenciales).
"""

import argparse
import os
import sqlite3
import sys

from plane_cli import attachments, cmd_comment, cmd_comment_ops, cmd_delete, cmd_ops, cmd_outbox, cmd_read, cmd_report, cmd_sync, cmd_tickets_write, renamed
from plane_cli.circuit import PlaneUnavailable, format_unavailable
from plane_cli.config import add_json_flag, get_env_or_fail
from plane_cli.db import get_db, init_db
from plane_cli.envelope import dumps
from plane_cli.errors import CliError
from plane_cli.outbox import pending_notice

COMMANDS = (
    cmd_read.register_get,
    cmd_read.register_list,
    cmd_tickets_write.register_create,
    cmd_tickets_write.register_update,
    cmd_delete.register_delete,
    ("comment", "Comentarios: add | edit | delete",
     (cmd_comment.register_comment_add, cmd_comment_ops.register_comment_edit, cmd_comment_ops.register_comment_delete)),
    ("attachment", "Adjuntos: add | list | delete | replace",
     (attachments.register_attachment_add, attachments.register_attachment_list, attachments.register_attachment_delete,
      attachments.register_attachment_replace)),
    ("link", "Enlaces: add", (cmd_tickets_write.register_link_add,)),
    ("outbox", "Cola de salida: list | flush | drop",
     (cmd_outbox.register_outbox_list, cmd_outbox.register_outbox_flush, cmd_outbox.register_outbox_drop)),
    ("focus", "Foco de la sesión: set | clear | status",
     (cmd_ops.register_focus_set, cmd_ops.register_focus_clear, cmd_ops.register_focus_status)),
    ("worklog", "Tiempos: propose | check", (cmd_comment_ops.register_worklog_propose, cmd_report.register_worklog_check)),
    ("report", "Reportes: time | flow", (cmd_report.register_report_time, cmd_report.register_report_flow)),
    cmd_sync.register_sync,
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


class PlaneParser(argparse.ArgumentParser):
    _json_mode = False

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)

    def error(self, message):
        if self._json_mode:
            raise CliError("usage", message, exit_code=2)
        super().error(message)


def build_parser():
    parser = PlaneParser(description="CLI de Plane CE para agentes de IA")
    add_json_flag(parser)
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<comando>")
    for entry in COMMANDS:
        if callable(entry):
            entry(subparsers)
        else:
            add_group(subparsers, *entry)
    return parser


def is_json_mode(argv):
    """Detecta --json en argv para saber si los errores tempranos deben salir en JSON."""
    return "--json" in argv


def _warn_pending(args, conn, base_url=None, workspace=None):
    """Aviso único por stderr de lo que sigue sin publicarse; los comandos `outbox` ya lo muestran."""
    if args is None or getattr(args, "command", None) == "outbox" or conn is None:
        return
    try:
        notice = pending_notice(conn, base_url=base_url, workspace=workspace)
    except sqlite3.Error:
        return
    if notice:
        sys.stderr.write(notice + "\n")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    json_mode = is_json_mode(argv)
    PlaneParser._json_mode = json_mode
    parser = build_parser()
    conn = None
    args = None
    base_url = None
    workspace = None
    try:
        hint = renamed.suggestion(argv, command_tree(parser))
        if hint:
            raise CliError("usage", hint, exit_code=2)
        args = parser.parse_args(argv)

        base_url = get_env_or_fail("PLANE_BASE_URL", "URL de Plane")
        if not base_url:
            raise CliError("env_missing", "Variable de entorno 'PLANE_BASE_URL' (URL de Plane) no configurada.",
                           hint="Defínela en ~/.zshrc.local o en tu entorno antes de ejecutar este script.")
        api_key = get_env_or_fail("PLANE_API_KEY", "API Key de Plane")
        if not api_key:
            raise CliError("env_missing", "Variable de entorno 'PLANE_API_KEY' (API Key de Plane) no configurada.",
                           hint="Defínela en ~/.zshrc.local o en tu entorno antes de ejecutar este script.")
        workspace = os.environ.get("PLANE_WORKSPACE_SLUG", "teamprogra")
        default_project_id = os.environ.get("PLANE_PROJECT_ID", "58371da4-cf62-4299-8fd4-99c1052b2eb3")

        conn = get_db()
        init_db(conn)

        ret = args.handler(args, conn, base_url, api_key, workspace, default_project_id)
        if isinstance(ret, int) and ret != 0:
            sys.exit(ret)
    except PlaneUnavailable as exc:
        if json_mode or (args is not None and getattr(args, "json", False)):
            print(dumps(CliError("plane_unavailable", format_unavailable(exc).strip()).to_dict()))
        else:
            sys.stderr.write(format_unavailable(exc))
        sys.exit(3)
    except CliError as exc:
        if json_mode or (args is not None and getattr(args, "json", False)):
            print(dumps(exc.to_dict()))
        else:
            if exc.code == "usage":
                sys.stderr.write(f"plane-tracker: error: {exc.render()}\n")
            elif exc.message.startswith("Error:") or exc.message.startswith("Error "):
                sys.stderr.write(f"{exc.render()}\n")
            elif exc.code == "duplicate" and "Ya hay un registro" in exc.message:
                sys.stderr.write(f"{exc.render()}\n")
            else:
                sys.stderr.write(f"Error: {exc.render()}\n")
        sys.exit(exc.exit_code)
    finally:
        if conn is not None:
            if args is not None:
                _warn_pending(args, conn, base_url=base_url, workspace=workspace)
            conn.close()
