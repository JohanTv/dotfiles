#!/usr/bin/env python3
"""
plane.py - CLI Integral y Resiliente para Plane CE v1.2.3 con Persistencia SQLite3 (v2.3).
Soporta:
  - Base de datos local SQLite3 con WAL Mode (Zero-Lock, concurrencia segura para subagentes)
  - Descubrimiento dinámico de proyectos (OMNIFY, OPS, OMNILEADS, CDP) en base de datos
  - Bitácoras dual-layer (humano + metadata oculta v2.2 con soporte de tracks y worker_type)
  - Fusión matemática de intervalos (Klee's Measure) para reportes sin horas duplicadas
  - Transiciones de estado seguras y asignación de prioridades y etiquetas
  - Tolerancia a fallos de red y backoff defensivo ante HTTP 429
  - Salida formateada y soporte `--json` para agentes de IA y dashboards
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import session_clock
import flow_metrics

from plane_cli import attachments, cmd_comment, cmd_comment_ops, cmd_ops, cmd_read, cmd_report, cmd_tickets_write
from plane_cli.config import get_env_or_fail
from plane_cli.db import get_db, init_db

# ------------------------------------------------------------------------------
# Conversor Markdown → HTML (stdlib, sin dependencias externas)
# Soporta el subconjunto que Plane CE/Tiptap renderiza correctamente:
#   ## Headings, **bold**, `code`, ```blocks```, listas -, tablas |, párrafos
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Conexión y Gestión de Base de Datos SQLite3 (WAL Mode)
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Entorno y Red
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Gestión de Proyectos con Caché en SQLite3
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Telemetría y Metadata (v2.2)
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Sincronización Remota con Plane API
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Algoritmo de Fusión de Intervalos de Klee (Interval Merging)
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Propuesta de duración medida (nunca se registra sola)
#   - Se mide con "tramos de actividad" de la sesión del agente (solo timestamps).
#   - Lo ya registrado y lo reservado por otras propuestas pendientes se RESTA: nada se cuenta dos veces,
#     sin importar el orden en que se acepten.
#   - Con marcas `focus`, cada ticket recibe solo el tiempo de sus propios intervalos.
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Comandos CLI
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Flujo por work item: lead time, cycle time, tiempo por estado y esfuerzo
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Adjuntos del work item (flujo de Plane: crear -> subir a almacenamiento -> confirmar)
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Salud de la conexión con Plane (a partir del registro de llamadas)
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Relevo (Handoff Snapshot): la herramienta solo junta hechos de git local; el criterio lo pone quien trabajó
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Consistencia entre la caché local y los comentarios de Plane (report --check)
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Generador de Reportes de Actividad en Formato Híbrido (cmd_report)
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Comando: whoami — Verificación de setup inicial
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Entrypoint CLI
# ------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CLI de Plane CE para Agentes de IA y Reportes de Actividad (v2.3 SQLite3)")
    parser.add_argument("--json", action="store_true", help="Salida en formato JSON para agentes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    cmd_comment.register_comment(subparsers)

    cmd_tickets_write.register_link(subparsers)

    attachments.register_attach(subparsers)
    attachments.register_attachments(subparsers)

    cmd_ops.register_health(subparsers)

    cmd_ops.register_handoff(subparsers)

    cmd_ops.register_focus(subparsers)

    cmd_comment_ops.register_propose_duration(subparsers)

    cmd_tickets_write.register_create(subparsers)

    cmd_comment_ops.register_comment_delete(subparsers)
    cmd_comment_ops.register_comment_edit(subparsers)

    cmd_tickets_write.register_update(subparsers)

    cmd_read.register_get(subparsers)

    cmd_read.register_list(subparsers)

    cmd_read.register_search(subparsers)

    cmd_read.register_labels(subparsers)

    cmd_read.register_projects(subparsers)

    cmd_read.register_whoami(subparsers)

    cmd_report.register_report(subparsers)

    args = parser.parse_args()

    base_url = get_env_or_fail("PLANE_BASE_URL", "URL de Plane")
    api_key = get_env_or_fail("PLANE_API_KEY", "API Key de Plane")
    workspace = os.environ.get("PLANE_WORKSPACE_SLUG", "teamprogra")
    default_project_id = os.environ.get("PLANE_PROJECT_ID", "58371da4-cf62-4299-8fd4-99c1052b2eb3")

    conn = get_db()
    init_db(conn)

    try:
        if getattr(args, "handler", None):
            args.handler(args, conn, base_url, api_key, workspace, default_project_id)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
