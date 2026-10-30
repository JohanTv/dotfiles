"""Punto de entrada de la CLI: parser raíz, registro ordenado de subcomandos y despacho.

Expone: COMMAND_REGISTRARS, build_parser(), main().
No hace: lógica de comandos (vive en cmd_*.py).
El orden de COMMAND_REGISTRARS es el orden de los subcomandos en `--help`. El arranque es: parsear argumentos, validar
el entorno y solo entonces abrir la base de datos (así `--help` funciona sin credenciales).
"""

import argparse
import os

from plane_cli import attachments, cmd_comment, cmd_comment_ops, cmd_ops, cmd_read, cmd_report, cmd_tickets_write
from plane_cli.config import get_env_or_fail
from plane_cli.db import get_db, init_db

COMMAND_REGISTRARS = (
    cmd_comment.register_comment,
    cmd_tickets_write.register_link,
    attachments.register_attach,
    attachments.register_attachments,
    cmd_ops.register_health,
    cmd_ops.register_handoff,
    cmd_ops.register_focus,
    cmd_comment_ops.register_propose_duration,
    cmd_tickets_write.register_create,
    cmd_comment_ops.register_comment_delete,
    cmd_comment_ops.register_comment_edit,
    cmd_tickets_write.register_update,
    cmd_read.register_get,
    cmd_read.register_list,
    cmd_read.register_search,
    cmd_read.register_labels,
    cmd_read.register_projects,
    cmd_read.register_whoami,
    cmd_report.register_report,
)


def build_parser():
    parser = argparse.ArgumentParser(description="CLI de Plane CE para Agentes de IA y Reportes de Actividad (v2.3 SQLite3)")
    parser.add_argument("--json", action="store_true", help="Salida en formato JSON para agentes")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for register in COMMAND_REGISTRARS:
        register(subparsers)
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
