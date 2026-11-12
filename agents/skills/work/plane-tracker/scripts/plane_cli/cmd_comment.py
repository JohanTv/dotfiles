"""Comando `comment add`: publicar un comentario con su worklog.

Expone: register_comment_add(), cmd_comment().
No hace: editar ni borrar comentarios, ni la entrega a Plane (outbox.publish_comment guarda, publica o encola).
"""

import json
import os
import sys
from datetime import datetime

import session_clock

from plane_cli.cache import issue_stub
from plane_cli.circuit import PlaneUnavailable
from plane_cli.config import add_json_flag
from plane_cli.errors import CliError
from plane_cli.mdhtml import markdown_to_html
from plane_cli.outbox import Draft, publish_comment
from plane_cli.proposal_store import consume_proposal, load_recent_proposal, save_proposal
from plane_cli.proposals import NO_PROPOSAL_BUCKETS, build_proposal, current_session_id, print_proposal
from plane_cli.resolve import get_project_identifier, known_actor, local_ticket_label, resolve_issue, resolve_project_and_seq
from plane_cli.worklog import derived_start, extract_metadata_from_comment, note_from, parse_date, recalculate_window_duration, reject_long_comment, reject_placeholders, requested_date, resolve_window, strip_metadata_block
from plane_cli import clock, envelope, vocabulary


def _resolve_duration(args, conn, meta, issue_ref, implied=None):
    """Duración en minutos y propuesta aceptada (si la hay); termina el proceso si falta o es inválida."""
    # --- Duración explícita (NUNCA estimar por defecto) ---------------------------------
    # Se valida ANTES de publicar: no puede quedar un comentario en Plane sin su worklog.
    # Fuentes válidas: el intervalo --since/--until (implícito), la bandera --duration N o la
    # metadata dual-layer (duration_minutes / duration_net_minutes); el intervalo manda.
    meta_duration = None
    if meta:
        meta_duration = meta.get("duration_minutes") or meta.get("duration_net_minutes")
    duration = implied or getattr(args, "duration", None) or meta_duration

    proposal = None
    if not duration:
        capacity_hint = getattr(args, "capacity_bucket", None) or (meta.get("capacity_bucket") if meta else None) or "deep_work"
        worker_hint = getattr(args, "worker_type", None) or (meta.get("worker_type") if meta else None)
        proposal_key = issue_ref.upper()
        if getattr(args, "accept_proposal", False):
            if capacity_hint in NO_PROPOSAL_BUCKETS:
                raise CliError("invalid_input", f"el balde '{capacity_hint}' (soporte/reuniones) no admite propuesta medida; usa --duration.")
            proposal = load_recent_proposal(proposal_key, current_session_id(args, worker_hint))
            if not proposal:
                raise CliError("not_found", f"no hay una propuesta reciente (<30 min) de esta sesión para {proposal_key}.",
                               hint="Repite sin --accept-proposal para generarla.")
            duration = proposal["minutes"]
        else:
            pending = load_recent_proposal(proposal_key, current_session_id(args, worker_hint))
            result = pending if pending and pending.get("split") else build_proposal(conn, args, capacity_hint, worker_hint, proposal_key)
            print_proposal(result, proposal_key, sys.stderr)
            if result["ok"]:
                if result.get("split"):
                    sys.stderr.write(f"   (parte del reparto pendiente {result['split']['group']})\n")
                else:
                    save_proposal(proposal_key, result)
                sys.stderr.write("   Para registrarla tal cual: repite el comando con --accept-proposal; para ajustarla usa --duration N.\n")
            else:
                sys.stderr.write("Usa --duration <minutos> o incluye el bloque PLANE_WORKLOG_METADATA con 'duration_minutes'.\n")
            return None, None

    try:
        duration = int(duration)
    except (TypeError, ValueError):
        raise CliError("invalid_input", "la duración debe ser un entero de minutos (ej: --duration 5).")

    if duration < 1 or duration > 24 * 60:
        raise CliError("invalid_input", f"duración fuera de rango ({duration} min). Debe estar entre 1 y 1440 minutos.")
    return duration, proposal


def _record_measurement(meta, args, proposal, worker_type):
    """Anota en la metadata cómo se obtuvo la duración: propuesta medida o declarada por quien registra."""
    if proposal:
        meta["date"] = proposal["date"]
        meta["start_time"] = proposal["start_time"]
        meta["end_time"] = proposal["end_time"]
        meta["segments"] = proposal["segments"]
        meta["measured_by"] = {
            "kind": "proposal_split" if proposal.get("split") else "proposal", "adapter": proposal["agent"],
            "confidence": proposal["confidence"], "session": proposal["session_id"], "gross_minutes": proposal["gross_minutes"],
            "attribution": proposal["attribution"],
        }
        if proposal.get("split"):
            meta["measured_by"]["split"] = proposal["split"]
        if proposal.get("window_override"):
            meta["measured_by"]["window_override"] = proposal["window_override"]
    else:
        # Duración declarada (no medida): se audita aparte; la sesión (si se resuelve sin ambigüedad) evita doble conteo.
        declared = {"kind": "declared", "worker_type": worker_type}
        declared_agent = getattr(args, "agent", None) or session_clock.agent_from_worker_type(worker_type) or session_clock.detect_agent()
        if declared_agent:
            declared_session = session_clock.resolve_session(declared_agent, os.getcwd(), getattr(args, "session", None))[0]
            if declared_session:
                declared["session"] = declared_session
        meta["measured_by"] = declared


def _print_result(args, result, issue, ticket_label, duration):
    """Salida de `comment add`: publicado (idéntica con o sin cola) o en cola."""
    as_json = getattr(args, "json", False)
    if result.note:
        sys.stderr.write(f"ℹ {result.note}\n")
    if result.state == "sent":
        if as_json:
            doc = {
                "schema": vocabulary.SCHEMA,
                "status": "ok",
                "action": "comment",
                "ticket": ticket_label,
                "uuid": issue["id"] if issue else None,
                "comment_id": result.comment_id,
            }
            print(envelope.dumps(doc))
        else:
            print(f"✔ Comentario publicado exitosamente en {args.issue} (ID Comentario: {result.comment_id})")
    elif as_json:
        doc = {
            "schema": vocabulary.SCHEMA,
            "status": "queued",
            "action": "comment",
            "ticket": ticket_label,
            "uuid": issue.get("id") if issue else None,
            "outbox_id": result.outbox_id,
            "client_id": result.client_id,
            "issue": ticket_label,
            "reason": result.reason,
        }
        if duration is not None:
            doc["duration_minutes"] = duration
        else:
            doc["worklog"] = False
        print(envelope.dumps(doc))
    else:
        if duration is not None:
            print(f"⏳ En cola (#{result.outbox_id}): comentario para {ticket_label}, {duration} min. Plane no responde; el tiempo ya cuenta como registrado. "
                  "Publícalo con: plane-tracker outbox flush")
        else:
            print(f"⏳ En cola (#{result.outbox_id}): comentario para {ticket_label}. Plane no responde; el comentario quedó en cola. "
                  "Publícalo con: plane-tracker outbox flush")


def _check_no_worklog_conflicts(args):
    conflicts = [flag for flag, val in (
        ("--date", getattr(args, "date", None)),
        ("--duration", getattr(args, "duration", None)),
        ("--since", getattr(args, "since", None)),
        ("--until", getattr(args, "until", None)),
        ("--capacity", getattr(args, "capacity_bucket", None)),
        ("--track", getattr(args, "track", None)),
        ("--worker-type", getattr(args, "worker_type", None)),
        ("--accept-proposal", getattr(args, "accept_proposal", False)),
    ) if val]
    if conflicts:
        raise CliError("invalid_input", f"--no-worklog no se puede combinar con banderas de tiempo o capacidad ({', '.join(conflicts)}).")


def _build_entry(ticket_label, track, issue, meta, now, duration, worker_type, capacity_bucket, conn, workspace):
    return {
        "id": None,
        "ticket_id": ticket_label,
        "track": track,
        "issue_name": issue.get("name", ""),
        "date": meta.get("date", now.strftime("%Y-%m-%d")),
        "start_time": meta.get("start_time", derived_start(now, duration)),
        "end_time": meta.get("end_time", now.strftime("%H:%M")),
        "duration_minutes": duration,
        "worker_type": worker_type,
        "capacity_bucket": capacity_bucket,
        "phase": meta.get("phase", "dev"),
        "role": meta.get("role", "backend_engineer"),
        "notes": meta.get("notes", issue.get("name", "")),
        "stoppers": meta.get("stoppers", []),
        "defaulted": [f for f in ("phase", "role", "notes") if f not in meta],
        "plane_comment_id": None,
        "created_at": now.isoformat(),
        "author_id": known_actor(conn, workspace),
        "raw_payload": meta
    }


def cmd_comment(args, conn, base_url, api_key, workspace, default_project_id):
    unavailable = None
    try:
        project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    except PlaneUnavailable as exc:
        unavailable, project_id, seq_id, uuid_ref = exc, None, None, None
        issue_ref = local_ticket_label(args.issue)
    args.issue = issue_ref
    content = ""
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    elif args.message:
        content = args.message
    else:
        content = sys.stdin.read()

    if not content.strip():
        raise CliError("invalid_input", "El comentario está vacío.")
    reject_placeholders(content)
    reject_long_comment(content, getattr(args, "long", False))

    if unavailable is None:
        try:
            issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref, issue_ref=issue_ref)
        except PlaneUnavailable as exc:
            unavailable = exc
    if unavailable is not None:
        issue = issue_stub(conn, project_id, seq_id, uuid_ref, issue_ref)

    no_worklog = getattr(args, "no_worklog", False)
    if no_worklog:
        _check_no_worklog_conflicts(args)
        duration = None
        proposal = None
    else:
        meta = extract_metadata_from_comment(content)
        # Ventana real del trabajo: --date/--since/--until mandan sobre la hora de publicación (defecto 0001).
        if getattr(args, "date", None):
            day = requested_date(args.date)
        else:
            day = (parse_date(meta.get("date")) if meta else None) or clock.local_today()
        since, until = getattr(args, "since", None), getattr(args, "until", None)
        declared = getattr(args, "duration", None) or (meta.get("duration_minutes") or meta.get("duration_net_minutes") if meta else None)
        win = resolve_window(since, until, declared, day)
        duration, proposal = _resolve_duration(args, conn, meta, issue_ref, win[2] if win else None)
        if duration is None:
            return 1

        # Defecto 0031: en días pasados se exige ventana explícita si la duración es manual (sin propuesta)
        if day < clock.local_today() and win is None and not proposal:
            if not (meta and (meta.get("start_time") or meta.get("end_time"))):
                raise CliError("invalid_input",
                               f"Para registrar trabajo de un día anterior ({day}) debes indicar la ventana horaria con --since o --until.",
                               hint=f"Ej: --date {day} --since 10:00 --duration {duration}")

    # Convertir Markdown → HTML si el contenido no viene ya como HTML. El bloque oculto se quita antes: el conversor
    # lo escaparía y quedaría visible; publish_comment inserta el real.
    if content.strip().startswith("<") and ">" in content:
        comment_html = content
    else:
        comment_html = markdown_to_html(strip_metadata_block(content))

    now = clock.local_now()
    if unavailable is None:
        # Etiqueta real del ticket: identifier del proyecto resuelto (OPS-13, nunca OMNIFY-13 por defecto)
        proj_ident = get_project_identifier(conn, base_url, api_key, workspace, project_id)
        if not proj_ident and issue_ref and "-" in issue_ref:
            proj_ident = issue_ref.split("-")[0].upper()
        seq_label = issue.get("sequence_id") or seq_id
        ticket_label = f"{proj_ident}-{seq_label}" if proj_ident and seq_label else args.issue
    else:
        ticket_label = issue.get("ticket_id") or issue_ref

    if no_worklog:
        meta = {"schema_version": "2.2", "worklog": False}
        entry = None
        draft = Draft(base_url, api_key, workspace, project_id, issue, ticket_label, comment_html, meta, entry, unavailable, has_worklog=False)
        result = publish_comment(conn, draft)
        _print_result(args, result, issue, ticket_label, None)
        return

    # Determinar track, worker_type y capacity_bucket (prioridad: flags de CLI -> metadata -> default)
    track = getattr(args, "track", None) or (meta.get("track") if meta else None) or "main"
    worker_type = getattr(args, "worker_type", None) or (meta.get("worker_type") if meta else None) or "human"
    capacity_bucket = getattr(args, "capacity_bucket", None) or (meta.get("capacity_bucket") if meta else None) or "deep_work"

    if not meta:
        meta = {
            "schema_version": "2.2",
            "date": now.strftime("%Y-%m-%d"),
            "start_time": derived_start(now, duration),
            "end_time": now.strftime("%H:%M"),
            "duration_minutes": duration,
            "track": track,
            "worker_type": worker_type,
            "capacity_bucket": capacity_bucket,
            "notes": note_from(content, issue.get("name", "")),
            "stoppers": [],
            "phase": "dev"
        }
    else:
        meta["track"] = track
        meta["worker_type"] = worker_type
        meta["capacity_bucket"] = capacity_bucket
        meta["duration_minutes"] = duration
        # Horarios honestos: si la metadata no los trae, se derivan de la duración reportada
        meta.setdefault("date", now.strftime("%Y-%m-%d"))
        if meta.get("start_time") and not meta.get("end_time"):
            meta["end_time"] = recalculate_window_duration(meta["start_time"], duration, day)
        else:
            meta.setdefault("end_time", now.strftime("%H:%M"))
            if not meta.get("start_time"):
                end_t = datetime.strptime(meta["end_time"], "%H:%M")
                meta["start_time"] = derived_start(end_t, duration)

    _record_measurement(meta, args, proposal, worker_type)
    # La ventana declarada manda sobre la hora de publicación y sobre la del bloque de metadata.
    if win:
        meta["start_time"], meta["end_time"], meta["duration_minutes"] = win[0], win[1], win[2]
        duration = win[2]
    if getattr(args, "date", None):
        meta["date"] = args.date

    # El comentario viaja con su propia telemetría (bloque HTML oculto que Plane conserva): así las horas
    # sobreviven a la pérdida de la caché local y se pueden reconstruir con `report time --refresh`.
    entry = _build_entry(ticket_label, track, issue, meta, now, duration, worker_type, capacity_bucket, conn, workspace)
    draft = Draft(base_url, api_key, workspace, project_id, issue, ticket_label, comment_html, meta, entry, unavailable)
    result = publish_comment(conn, draft)
    if proposal:
        consume_proposal(issue_ref.upper(), proposal["session_id"])
    _print_result(args, result, issue, ticket_label, duration)


def register_comment_add(sub):
    p_comment = sub.add_parser("add", help="Publicar un comentario con su worklog")
    p_comment.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    p_comment.add_argument("-m", "--message", help="Mensaje del comentario")
    p_comment.add_argument("-f", "--file", help="Archivo con el contenido")
    p_comment.add_argument("--no-worklog", action="store_true",
                           help="Publicar el comentario sin registrar telemetría ni imputar tiempo")
    p_comment.add_argument("--track", help="Frente de trabajo (ej: main, subagent, review, datepicker)")
    p_comment.add_argument("--capacity", "--capacity-bucket", dest="capacity_bucket",
                           choices=["deep_work", "toil_support", "coordination", "tooling_dx", "research_rd", "tech_debt_paydown"],
                           help="Balde de capacidad de la sesión")
    p_comment.add_argument("--worker-type", choices=["human", "subagent", "agent:agy", "agent:claude", "agent:opencode"], help="Tipo de ejecutor")
    p_comment.add_argument("--duration", type=int, metavar="MIN",
                           help="Duración neta de la sesión en minutos (requerido si el contenido no lleva metadata telemétrica). Ej: --duration 5")
    p_comment.add_argument("--date", metavar="YYYY-MM-DD", help="Fecha del trabajo registrada (por defecto: hoy, nunca futura)")
    p_comment.add_argument("--since", metavar="HH:MM", help="Inicio real del trabajo; con --until fija el intervalo")
    p_comment.add_argument("--until", metavar="HH:MM", help="Fin real del trabajo; con --since fija el intervalo")
    p_comment.add_argument("--accept-proposal", action="store_true",
                           help="Registrar la duración propuesta (solo vale si se mostró hace menos de 30 min para este ticket)")
    p_comment.add_argument("--long", action="store_true",
                           help="Permite más de 700 caracteres visibles (solo relevos o informes que el usuario pidió)")
    p_comment.add_argument("--agent", choices=list(session_clock.AGENTS), help="Agente cuya sesión se mide (por defecto: según --worker-type o el entorno)")
    p_comment.add_argument("--session", metavar="ID", help="ID de la sesión del agente (por defecto: variable de entorno o directorio de trabajo)")
    add_json_flag(p_comment)
    p_comment.set_defaults(handler=cmd_comment)
