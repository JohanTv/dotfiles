"""Comandos del grupo `outbox`: `list`, `flush` y `drop` sobre la cola de comentarios pendientes de publicar.

Expone: register_outbox_list/flush/drop(), cmd_outbox_list/flush/drop().
No hace: la lógica de la cola (outbox.py y outbox_flush.py); aquí solo se interpretan los argumentos y se imprime.
Códigos de `flush`: 0 sin nada fallido ni cortado, 1 si hay registros fallidos o Plane rechazó la clave (401), 3 si Plane no responde.
"""

import json
import sys

from plane_cli.config import add_json_flag, positive_int
from plane_cli.outbox import drop_item, list_items
from plane_cli.outbox_flush import DEFAULT_LIMIT, OUTBOX_MAX_AGE_DAYS, flush_items

HOW = {"exists": " (ya existía en Plane)", "found": " (ya estaba publicado; no se reenvió)"}


def cmd_outbox_list(args, conn, base_url, api_key, workspace, default_project_id):
    items = list_items(conn, include_all=args.all)
    if getattr(args, "json", False):
        print(json.dumps(items, indent=2, ensure_ascii=False))
        return
    if not items:
        print("La cola está vacía." if not args.all else "No hay registros en la cola.")
        return
    for it in items:
        flag = " · pudo enviarse" if it["maybe_delivered"] and it["state"] != "sent" else ""
        print(f"#{it['id']} [{it['state']}] {it['ticket']} · {it['track']} · {it['date']} {it['start_time']} · {it['duration_minutes'] or '?'} min · "
              f"{it['attempts']} intento(s){flag}")
        print(f"   {it['preview']}")
        if it["last_error"]:
            print(f"   último error: {it['last_error']}")


def _print_flush(result):
    for sent in result["sent"]:
        print(f"✔ #{sent['id']} {sent['ticket']} publicado (comentario {sent['comment_id']}){HOW.get(sent['how'], '')}")
    for failed in result["failed"]:
        print(f"✖ #{failed['id']} {failed['ticket']} falló: {failed['error']}")
    parts = [f"{len(result['sent'])} publicado(s)", f"{result['failed_total']} fallido(s)", f"{result['pending']} pendiente(s)"]
    if result["skipped_old"]:
        parts.append(f"{result['skipped_old']} de más de {OUTBOX_MAX_AGE_DAYS} días omitido(s) (usa --include-old)")
    print("Resumen: " + ", ".join(parts) + ".")
    if result["failed_total"]:
        print("Los fallidos siguen en la cola: revísalos con 'outbox list', reintenta con 'outbox flush --retry-failed' o descártalos con 'outbox drop'.")


def cmd_outbox_flush(args, conn, base_url, api_key, workspace, default_project_id):
    result = flush_items(conn, base_url, api_key, workspace, default_project_id, limit=args.limit, include_old=args.include_old,
                         retry_failed=args.retry_failed)
    if getattr(args, "json", False):
        shown = {k: v for k, v in result.items() if k != "unavailable"}
        shown["unavailable"] = result["unavailable"].cause if result["unavailable"] else None
        print(json.dumps(shown, indent=2, ensure_ascii=False))
    else:
        _print_flush(result)
    if result["stopped"] == "unauthorized":
        sys.stderr.write("Error: Plane rechazó las credenciales (HTTP 401); revisa PLANE_API_KEY. El flush se detuvo.\n")
        sys.exit(1)
    if result["stopped"] == "unavailable":
        raise result["unavailable"]
    if result["failed_total"]:
        sys.exit(1)


def cmd_outbox_drop(args, conn, base_url, api_key, workspace, default_project_id):
    item = drop_item(conn, args.id, force=args.force, keep_worklog=args.keep_worklog)
    if getattr(args, "json", False):
        print(json.dumps({"status": "ok", "action": "outbox drop", "outbox_id": item["id"], "client_id": item["client_id"], "kept_worklog": args.keep_worklog}))
    else:
        print(f"✔ Registro #{item['id']} descartado" + (" (se conservó el worklog local)." if args.keep_worklog else " y su worklog provisional eliminado."))


def register_outbox_list(sub):
    p = sub.add_parser("list", help="Listar los registros pendientes de publicar",
                       description="Registros abiertos de la cola (pendientes, en envío y fallidos) con una vista previa; --all incluye los ya publicados y descartados.")
    p.add_argument("--all", action="store_true", help="Incluir publicados y descartados")
    add_json_flag(p)
    p.set_defaults(handler=cmd_outbox_list)


def register_outbox_flush(sub):
    p = sub.add_parser("flush", help="Publicar en Plane los registros en cola",
                       description="Publica la cola en orden de creación y se detiene ante el primer fallo de disponibilidad. Sondea Plane aunque el circuito esté en enfriamiento.")
    p.add_argument("--limit", type=positive_int, default=DEFAULT_LIMIT, metavar="N", help=f"Máximo de registros por ejecución (por defecto {DEFAULT_LIMIT})")
    p.add_argument("--include-old", action="store_true", help=f"Incluir los de más de {OUTBOX_MAX_AGE_DAYS} días (se omiten por defecto)")
    p.add_argument("--retry-failed", action="store_true", help="Devolver los fallidos a pendientes antes de publicar")
    add_json_flag(p)
    p.set_defaults(handler=cmd_outbox_flush)


def register_outbox_drop(sub):
    p = sub.add_parser("drop", help="Descartar un registro de la cola",
                       description="Descarta un registro abierto y borra su worklog provisional. Si pudo haberse enviado exige --force.")
    p.add_argument("id", type=positive_int, help="Número del registro (ver `outbox list`)")
    p.add_argument("--force", action="store_true", help="Descartar aunque pueda estar ya publicado en Plane")
    p.add_argument("--keep-worklog", action="store_true", help="Conservar la fila local de worklogs")
    add_json_flag(p)
    p.set_defaults(handler=cmd_outbox_drop)
