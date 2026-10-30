"""Comandos `comment edit`, `comment delete` y `worklog propose`.

Expone: register_comment_edit(), register_comment_delete(), register_worklog_propose(), cmd_comment_edit(),
cmd_comment_delete(), cmd_propose_duration().
No hace: publicar comentarios nuevos.
"""

import json
import re
import sys
from datetime import datetime, timedelta

import session_clock

from plane_cli.api import api_request
from plane_cli.config import add_json_flag
from plane_cli.mdhtml import markdown_to_html
from plane_cli.proposal_store import load_recent_proposal, save_group, save_proposal
from plane_cli.proposals import build_proposal, build_split, current_session_id, print_proposal, print_split
from plane_cli.resolve import get_actor_uuid, get_project_identifier, resolve_issue, resolve_project_and_seq
from plane_cli.worklog import (
    corrected_metadata,
    extract_metadata_from_comment,
    find_metadata_block,
    reject_placeholders,
    replace_metadata_block,
    upsert_worklog,
    worklog_metadata_block,
)


def cmd_propose_duration(args, conn, base_url, api_key, workspace, default_project_id):
    """Solo lectura: mide la sesión y muestra la propuesta (o el reparto --split) sin registrar nada."""
    capacity = getattr(args, "capacity_bucket", None) or "deep_work"
    worker_type = getattr(args, "worker_type", None)
    if getattr(args, "split", None):
        result = build_split(conn, args, args.split, worker_type)
        if result["ok"]:
            # Validar que cada ticket exista antes de reservar el reparto.
            for ticket in result["parts"]:
                resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, ticket)
            save_group(result["group"], result["parts"])
        if getattr(args, "json", False):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif result["ok"]:
            print_split(result, sys.stdout)
            print("   Registra cada parte con: plane-tracker comment add <TICKET> -m \"...\" --accept-proposal")
        else:
            print_proposal(result, "reparto", sys.stdout)
        sys.exit(0 if result["ok"] else 1)

    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    key = issue_ref.upper()
    pending = load_recent_proposal(key, current_session_id(args, worker_type))
    explicit_window = bool(getattr(args, "since", None) or getattr(args, "until", None))
    if pending and pending.get("split") and not explicit_window:
        result = pending  # reparto vigente: no se recalcula para no solaparlo
    else:
        result = build_proposal(conn, args, capacity, worker_type, key)
        if result["ok"]:
            save_proposal(key, result)
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_proposal(result, key, sys.stdout)
    sys.exit(0 if result["ok"] else 1)


def _resolve_own_comment(args, base_url, api_key, workspace, project_id, issue):
    """ID del comentario a tocar: el indicado, o el último comentario propio del ticket."""
    if args.comment_id:
        return args.comment_id
    actor = get_actor_uuid(base_url, api_key, workspace)
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
    res = api_request(url, api_key)
    comments = res if isinstance(res, list) else res.get("results", [])
    own = [c for c in comments if not actor or c.get("actor") == actor]
    if not own:
        sys.stderr.write("Error: No hay comentarios propios en el ticket. Indica el ID con --comment-id.\n")
        sys.exit(1)
    return max(own, key=lambda c: c.get("created_at", "")).get("id")


def cmd_comment_delete(args, conn, base_url, api_key, workspace, default_project_id):
    """Elimina un comentario en Plane y su worklog en la BD local."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    cid = _resolve_own_comment(args, base_url, api_key, workspace, project_id, issue)
    api_request(f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/{cid}/", api_key, method="DELETE")
    with conn:
        n = conn.execute("DELETE FROM worklogs WHERE plane_comment_id = ?", (cid,)).rowcount
    print(f"✔ Comentario {cid} eliminado de {issue_ref} ({n} worklog local(es) borrado(s))")


def cmd_comment_edit(args, conn, base_url, api_key, workspace, default_project_id):
    """Edita el texto de un comentario y/o registra su worklog local, sin publicar otro comentario."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    cid = _resolve_own_comment(args, base_url, api_key, workspace, project_id, issue)
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/{cid}/"

    content = args.message
    if content is not None:
        reject_placeholders(content)
    row = conn.execute("SELECT raw_payload FROM worklogs WHERE plane_comment_id = ?", (cid,)).fetchone()
    local_meta = json.loads(row["raw_payload"]) if row else None
    if content is not None:
        html = content if content.strip().startswith("<") and ">" in content else markdown_to_html(content)
        if "PLANE_WORKLOG_METADATA" not in html:
            # Editar el texto no debe perder la telemetría: se conserva el bloque que ya traía el comentario.
            existing = find_metadata_block(api_request(url, api_key).get("comment_html"))
            if existing:
                html += "\n" + existing
            elif local_meta:
                html += "\n" + worklog_metadata_block(local_meta)
        api_request(url, api_key, method="PATCH", data={"comment_html": html})
        print(f"✔ Comentario {cid} actualizado en {issue_ref}")
    elif getattr(args, "embed_metadata", False):
        if not local_meta:
            sys.stderr.write("Error: no hay worklog local vinculado a ese comentario; usa --duration para registrarlo.\n")
            sys.exit(1)
        current = api_request(url, api_key).get("comment_html") or ""
        if "PLANE_WORKLOG_METADATA" in current:
            print(f"✔ El comentario {cid} ya lleva su metadata")
        else:
            api_request(url, api_key, method="PATCH", data={"comment_html": current + "\n" + worklog_metadata_block(local_meta)})
            print(f"✔ Metadata del worklog añadida al comentario {cid} (sin cambiar su texto visible)")

    if args.duration:
        c = api_request(url, api_key)
        current_html = c.get("comment_html") or ""
        proj_ident = get_project_identifier(conn, base_url, api_key, workspace, project_id)
        old_meta = extract_metadata_from_comment(current_html) if find_metadata_block(current_html) else None
        if old_meta:
            # Corrección: se parte del bloque existente (sesión, tramos, fechas) y se cambia solo lo pedido.
            try:
                meta = corrected_metadata(old_meta, args.duration, args.track, args.capacity_bucket, args.worker_type, getattr(args, "force", False))
            except ValueError as exc:
                sys.stderr.write(f"Error: {exc}\n")
                sys.exit(1)
        else:
            # Comentario sin telemetría: su hora de publicación (local) es el fin; inicio = fin - duración
            end = datetime.fromisoformat(c["created_at"].replace("Z", "+00:00")).astimezone()
            start = end - timedelta(minutes=args.duration)
            notes = re.sub(r"<[^>]+>", "", current_html).strip()[:120] or issue.get("name", "")
            meta = {"schema_version": "2.2", "date": start.strftime("%Y-%m-%d"), "start_time": start.strftime("%H:%M"),
                    "end_time": end.strftime("%H:%M"), "duration_minutes": args.duration, "track": args.track or "main",
                    "worker_type": args.worker_type or "human", "capacity_bucket": args.capacity_bucket or "deep_work",
                    "notes": notes, "stoppers": [], "phase": "dev", "measured_by": {"kind": "declared", "worker_type": args.worker_type or "human"}}
        with conn:  # un worklog por comentario: se reemplaza por id de comentario (no por clave primaria)
            conn.execute("DELETE FROM worklogs WHERE plane_comment_id = ?", (cid,))
        upsert_worklog(conn, {**meta, "ticket_id": f"{proj_ident}-{issue.get('sequence_id') or seq_id}",
                              "issue_name": issue.get("name", ""), "plane_comment_id": cid, "raw_payload": meta})
        api_request(url, api_key, method="PATCH", data={"comment_html": replace_metadata_block(current_html, meta)})
        print(f"✔ Worklog {'corregido' if old_meta else 'vinculado'} en {cid}: {meta['date']} {meta['start_time']}-{meta['end_time']} ({args.duration} min, {meta['track']}, {meta['capacity_bucket']})")
    elif content is None and not getattr(args, "embed_metadata", False):
        sys.stderr.write("Advertencia: nada que hacer (usa -m y/o --duration).\n")


def register_worklog_propose(sub):
    p_prop = sub.add_parser("propose", help="Medir la sesión y proponer una duración",
                               description="Mide la sesión del agente y propone una duración; no registra nada.")
    p_prop.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    p_prop.add_argument("--agent", choices=list(session_clock.AGENTS), help="Agente cuya sesión se mide")
    p_prop.add_argument("--session", metavar="ID", help="ID de la sesión del agente")
    p_prop.add_argument("--worker-type", choices=["human", "subagent", "agent:agy", "agent:claude", "agent:opencode"], help="Tipo de ejecutor")
    p_prop.add_argument("--capacity", "--capacity-bucket", dest="capacity_bucket",
                        choices=["deep_work", "toil_support", "coordination", "tooling_dx", "research_rd", "tech_debt_paydown"],
                        help="Balde de capacidad (toil_support y coordination no admiten propuesta)")
    p_prop.add_argument("--split", metavar="SPEC", help="Repartir lo medido entre tickets: 'A=60%%,B=rest' o 'A=40m,B=rest' (ignora las marcas de foco)")
    p_prop.add_argument("--date", metavar="YYYY-MM-DD", help="Día a medir (por defecto hoy): para sesiones de días anteriores")
    p_prop.add_argument("--since", metavar="HH:MM|ISO", help="Inicio de la ventana medida (hora local del día medido)")
    p_prop.add_argument("--until", metavar="HH:MM|ISO", help="Fin de la ventana medida (hora local del día medido)")
    add_json_flag(p_prop)
    p_prop.set_defaults(handler=cmd_propose_duration)


def register_comment_delete(sub):
    p_cdel = sub.add_parser("delete", help="Eliminar un comentario y su worklog local",
                              description="Elimina un comentario (por defecto el último propio) y su worklog local.")
    p_cdel.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OPS-13)")
    p_cdel.add_argument("--comment-id", help="UUID del comentario (por defecto: último comentario propio)")
    p_cdel.set_defaults(handler=cmd_comment_delete)


def register_comment_edit(sub):
    p_cedit = sub.add_parser("edit", help="Editar un comentario y/o su worklog",
                              description="Edita un comentario y/o le vincula su worklog local sin publicar otro.")
    p_cedit.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OPS-13)")
    p_cedit.add_argument("--comment-id", help="UUID del comentario (por defecto: último comentario propio)")
    p_cedit.add_argument("-m", "--message", help="Nuevo texto del comentario")
    p_cedit.add_argument("--track", help="Frente de trabajo")
    p_cedit.add_argument("--capacity", "--capacity-bucket", dest="capacity_bucket",
                         choices=["deep_work", "toil_support", "coordination", "tooling_dx", "research_rd", "tech_debt_paydown"])
    p_cedit.add_argument("--worker-type", choices=["human", "subagent", "agent:agy", "agent:claude", "agent:opencode"])
    p_cedit.add_argument("--duration", type=int, metavar="MIN", help="Duración en minutos: registra el worklog usando la hora de publicación como fin")
    p_cedit.add_argument("--embed-metadata", action="store_true", help="Añadir al comentario el bloque oculto de metadata de su worklog local (sin cambiar el texto visible)")
    p_cedit.add_argument("--force", action="store_true", help="Con --duration: descartar los tramos medidos del worklog cuando la nueva duración no coincide")
    p_cedit.set_defaults(handler=cmd_comment_edit)
