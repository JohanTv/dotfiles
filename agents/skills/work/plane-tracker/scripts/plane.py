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

import sys
import os
import json
import urllib.error
import re
import time
import argparse
from datetime import datetime, timedelta, date, timezone

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import session_clock
import flow_metrics

from plane_cli import attachments, cmd_ops, cmd_read, cmd_report, worklog
from plane_cli.api import api_request
from plane_cli.attachments import upload_attachment, validate_attachment_paths
from plane_cli.config import get_env_or_fail
from plane_cli.db import get_db, init_db
from plane_cli.mdhtml import markdown_to_html
from plane_cli.proposal_store import consume_proposal, load_recent_proposal, save_group, save_proposal
from plane_cli.proposals import (
    NO_PROPOSAL_BUCKETS,
    build_proposal,
    build_split,
    current_session_id,
    print_proposal,
    print_split,
)
from plane_cli.resolve import (
    get_actor_uuid,
    get_labels_map,
    get_project_identifier,
    get_projects_map,
    get_states_map,
    resolve_issue,
    resolve_project_and_seq,
)
from plane_cli.worklog import (
    corrected_metadata,
    derived_start,
    extract_metadata_from_comment,
    find_metadata_block,
    reject_placeholders,
    replace_metadata_block,
    upsert_worklog,
    worklog_metadata_block,
)

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

def cmd_comment(args, conn, base_url, api_key, workspace, default_project_id):
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
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
        sys.stderr.write("Error: El comentario está vacío.\n")
        sys.exit(1)
    reject_placeholders(content)

    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)

    # --- Duración explícita (NUNCA estimar por defecto) ---------------------------------
    # Se valida ANTES de publicar: no puede quedar un comentario en Plane sin su worklog.
    # Fuentes válidas: metadata dual-layer (duration_minutes / duration_net_minutes) o --duration N.
    meta = extract_metadata_from_comment(content)
    meta_duration = None
    if meta:
        meta_duration = meta.get("duration_minutes") or meta.get("duration_net_minutes")
    duration = getattr(args, "duration", None) or meta_duration

    proposal = None
    if not duration:
        capacity_hint = getattr(args, "capacity_bucket", None) or (meta.get("capacity_bucket") if meta else None) or "deep_work"
        worker_hint = getattr(args, "worker_type", None) or (meta.get("worker_type") if meta else None)
        proposal_key = issue_ref.upper()
        if getattr(args, "accept_proposal", False):
            if capacity_hint in NO_PROPOSAL_BUCKETS:
                sys.stderr.write(f"Error: el balde '{capacity_hint}' (soporte/reuniones) no admite propuesta medida; usa --duration.\n")
                sys.exit(1)
            proposal = load_recent_proposal(proposal_key, current_session_id(args, worker_hint))
            if not proposal:
                sys.stderr.write(f"Error: no hay una propuesta reciente (<30 min) de esta sesión para {proposal_key}. Repite sin --accept-proposal para generarla.\n")
                sys.exit(1)
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
            sys.exit(1)

    try:
        duration = int(duration)
    except (TypeError, ValueError):
        sys.stderr.write("Error: la duración debe ser un entero de minutos (ej: --duration 5).\n")
        sys.exit(1)

    if duration < 1 or duration > 24 * 60:
        sys.stderr.write(f"Error: duración fuera de rango ({duration} min). Debe estar entre 1 y 1440 minutos.\n")
        sys.exit(1)

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
    # Convertir Markdown → HTML si el contenido no viene ya como HTML
    if content.strip().startswith("<") and ">" in content:
        comment_html = content
    else:
        comment_html = markdown_to_html(content)

    # Caching atómico en SQLite3
    now = datetime.now()
    # Etiqueta real del ticket: identifier del proyecto resuelto (OPS-13, nunca OMNIFY-13 por defecto)
    proj_ident = get_project_identifier(conn, base_url, api_key, workspace, project_id)
    if not proj_ident and issue_ref and "-" in issue_ref:
        proj_ident = issue_ref.split("-")[0].upper()
    seq_label = issue.get("sequence_id") or seq_id
    ticket_label = f"{proj_ident}-{seq_label}" if proj_ident and seq_label else args.issue
    
    # Determinar track, worker_type y capacity_bucket (prioridad: flags de CLI -> metadata -> default)
    track = getattr(args, "track", None) or (meta.get("track") if meta else None) or "main"
    worker_type = getattr(args, "worker_type", None) or (meta.get("worker_type") if meta else None) or "human"
    capacity_bucket = getattr(args, "capacity_bucket", None) or (meta.get("capacity_bucket") if meta else None) or "deep_work"

    if not meta:
        clean_text = re.sub(r"<[^>]+>", "", content).strip()
        meta = {
            "schema_version": "2.2",
            "date": now.strftime("%Y-%m-%d"),
            "start_time": derived_start(now, duration),
            "end_time": now.strftime("%H:%M"),
            "duration_minutes": duration,
            "track": track,
            "worker_type": worker_type,
            "capacity_bucket": capacity_bucket,
            "notes": clean_text[:120] if clean_text else issue.get("name", ""),
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
        meta.setdefault("end_time", now.strftime("%H:%M"))
        if not meta.get("start_time"):
            end_t = datetime.strptime(meta["end_time"], "%H:%M")
            meta["start_time"] = derived_start(end_t, duration)

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

    # El comentario viaja con su propia telemetría (bloque HTML oculto que Plane conserva): así las horas
    # sobreviven a la pérdida de la caché local y se pueden reconstruir con `report --sync`.
    if "PLANE_WORKLOG_METADATA" not in comment_html:
        comment_html += "\n" + worklog_metadata_block(meta)
    res = api_request(url, api_key, method="POST", data={"comment_html": comment_html})

    entry = {
        "id": res.get("id"),
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
        "plane_comment_id": res.get("id"),
        "created_at": datetime.now().isoformat(),
        "raw_payload": meta
    }
    clash = conn.execute(
        "SELECT 1 FROM worklogs WHERE ticket_id = ? AND track = ? AND date = ? AND start_time = ?",
        (entry["ticket_id"], entry["track"], entry["date"], entry["start_time"]),
    ).fetchone()
    if clash:
        sys.stderr.write("⚠ Ya existía un worklog local con el mismo ticket/track/fecha/inicio: se sobrescribe (el comentario anterior sigue en Plane).\n")
    upsert_worklog(conn, entry)
    if proposal:
        consume_proposal(issue_ref.upper(), proposal["session_id"])

    if getattr(args, "json", False):
        print(json.dumps({"status": "ok", "action": "comment", "issue_id": issue["id"], "sequence_id": issue.get("sequence_id"), "comment_id": res.get("id")}))
    else:
        print(f"✔ Comentario publicado exitosamente en {args.issue} (ID Comentario: {res.get('id')})")

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
            print("   Registra cada parte con: plane-tracker comment <TICKET> -m \"...\" --accept-proposal")
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


def cmd_link(args, conn, base_url, api_key, workspace, default_project_id):
    """Adjunta un enlace (PR, doc) al work item: aparece en su panel de enlaces, sin notificar como comentario."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    if not re.match(r"^https?://", args.url):
        sys.stderr.write("Error: la URL debe empezar por http:// o https://\n")
        sys.exit(1)
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/links/"
    existing = api_request(url, api_key).get("results", [])
    if any(l.get("url") == args.url for l in existing):
        print(f"✔ {issue_ref} ya tiene ese enlace")
        return
    api_request(url, api_key, method="POST", data={"url": args.url, "title": args.title or args.url})
    print(f"✔ Enlace añadido a {issue_ref}: {args.title or args.url}")

def cmd_update(args, conn, base_url, api_key, workspace, default_project_id):
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    args.issue = issue_ref
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    patch_data = {}

    if args.state:
        states_map = get_states_map(conn, base_url, api_key, workspace, project_id)
        target_state = args.state.lower().strip().replace("ó", "o").replace("é", "e").replace("á", "a")
        if target_state not in states_map:
            sys.stderr.write(f"Error: Estado desconocido '{args.state}'. Estados válidos en proyecto: {', '.join(states_map.keys())}\n")
            sys.exit(1)
        patch_data["state"] = states_map[target_state]

    if args.priority:
        prio = args.priority.lower().strip()
        if prio not in ("urgent", "high", "medium", "low", "none"):
            sys.stderr.write(f"Error: Prioridad desconocida '{args.priority}'. Opciones: urgent, high, medium, low, none.\n")
            sys.exit(1)
        patch_data["priority"] = prio

    if args.labels:
        labels_map = get_labels_map(conn, base_url, api_key, workspace, project_id)
        label_ids = []
        for raw_l in args.labels.split(","):
            l = raw_l.strip().lower()
            if l:
                if l in labels_map:
                    label_ids.append(labels_map[l])
                else:
                    sys.stderr.write(f"Advertencia: Etiqueta '{l}' no existe en el proyecto. Ignorada.\n")
        patch_data["labels"] = label_ids

    for arg, field in (("start_date", "start_date"), ("due_date", "target_date")):
        val = getattr(args, arg, None)
        if val:
            try:
                datetime.strptime(val, "%Y-%m-%d")
            except ValueError:
                sys.stderr.write(f"Error: Fecha inválida '{val}'. Formato: YYYY-MM-DD.\n")
                sys.exit(1)
            patch_data[field] = val

    if not patch_data:
        sys.stderr.write("Advertencia: No se indicaron cambios para actualizar (--state, --priority, --labels, --start-date o --due-date).\n")
        return

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/"
    res = api_request(url, api_key, method="PATCH", data=patch_data)
    
    if getattr(args, "json", False):
        print(json.dumps({"status": "ok", "action": "update", "issue_id": issue["id"], "sequence_id": issue.get("sequence_id"), "patched": patch_data}))
    else:
        changes = []
        if "state" in patch_data: changes.append(f"Estado ➔ {args.state}")
        if "priority" in patch_data: changes.append(f"Prioridad ➔ {args.priority}")
        if "labels" in patch_data: changes.append(f"Etiquetas ➔ {args.labels}")
        if "start_date" in patch_data: changes.append(f"Inicio ➔ {patch_data['start_date']}")
        if "target_date" in patch_data: changes.append(f"Vence ➔ {patch_data['target_date']}")
        print(f"✔ Ticket {args.issue} actualizado con éxito: [{', '.join(changes)}]")

def cmd_create(args, conn, base_url, api_key, workspace, default_project_id):
    """Crea un nuevo ticket en Plane y devuelve su identificador para ramas Git."""
    project_id = default_project_id
    project_ident = "OMNIFY"

    projects_map = get_projects_map(conn, base_url, api_key, workspace)
    if getattr(args, "project", None):
        p_upper = args.project.upper()
        if p_upper in projects_map:
            project_id = projects_map[p_upper]["id"]
            project_ident = p_upper
        else:
            projects_map = get_projects_map(conn, base_url, api_key, workspace, force_refresh=True)
            if p_upper in projects_map:
                project_id = projects_map[p_upper]["id"]
                project_ident = p_upper
            else:
                sys.stderr.write(f"Error: Proyecto '{args.project}' no encontrado. Opciones: {', '.join(projects_map.keys())}\n")
                sys.exit(1)
    else:
        for k, v in projects_map.items():
            if v["id"] == project_id:
                project_ident = k
                break

    payload = {
        "name": args.title.strip()
    }

    if getattr(args, "description", None):
        desc = args.description.strip()
        if desc.startswith("<") and ">" in desc:
            # Ya viene como HTML explícito
            payload["description_html"] = desc
        else:
            # Markdown → HTML
            payload["description_html"] = markdown_to_html(desc)

    if getattr(args, "priority", None):
        payload["priority"] = args.priority.lower()

    if getattr(args, "start_date", None):
        payload["start_date"] = args.start_date
    if getattr(args, "due_date", None):
        payload["target_date"] = args.due_date

    if getattr(args, "state", None):
        states_map = get_states_map(conn, base_url, api_key, workspace, project_id)
        norm_state = args.state.lower().strip().replace("ó", "o").replace("é", "e").replace("á", "a")
        if norm_state in states_map:
            payload["state"] = states_map[norm_state]
        else:
            sys.stderr.write(f"Error: Estado desconocido '{args.state}'. Estados válidos: {', '.join(states_map.keys())}\n")
            sys.exit(1)

    if getattr(args, "labels", None):
        labels_map = get_labels_map(conn, base_url, api_key, workspace, project_id)
        label_ids = []
        for l in args.labels.split(","):
            l_clean = l.strip().lower()
            if l_clean:
                if l_clean in labels_map:
                    label_ids.append(labels_map[l_clean])
                else:
                    sys.stderr.write(f"Advertencia: Etiqueta '{l_clean}' no encontrada en el proyecto. Se omitirá.\n")
        if label_ids:
            payload["labels"] = label_ids

    attach_paths = getattr(args, "attach", None) or []
    validate_attachment_paths(attach_paths)

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/"
    res = api_request(url, api_key, method="POST", data=payload)

    # Plane no admite adjuntos en la creación: se suben justo después (el ticket ya existe si alguno falla).
    attached, attach_errors = [], []
    for path in attach_paths:
        try:
            name, _ = upload_attachment(base_url, api_key, workspace, project_id, res["id"], path)
            attached.append(name)
        except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError, SystemExit) as exc:
            attach_errors.append(f"{path}: {exc}")

    seq_id = res.get("sequence_id")
    ticket_ref = f"{project_ident}-{seq_id}" if seq_id else res.get("id")
    web_url = f"{base_url.rstrip('/')}/{workspace}/projects/{project_id}/issues/{res.get('id')}"

    # Generar sugerencia de rama inteligente según prefijo [FASE]
    branch_type = "feat"
    clean_title = args.title.strip()
    phase_match = re.match(r"^\[([A-Za-z]+)\]\s*(.*)$", clean_title)
    if phase_match:
        f_prefix = phase_match.group(1).lower()
        clean_title = phase_match.group(2)
        type_map = {
            "spike": "spike",
            "rfc": "spike",
            "fix": "fix",
            "feat": "feat",
            "infra": "infra",
            "qa": "test",
            "test": "test",
            "refactor": "refactor"
        }
        branch_type = type_map.get(f_prefix, "feat")

    clean_desc = re.sub(r"[^a-zA-Z0-9]+", "-", clean_title.lower()).strip("-")
    if len(clean_desc) > 35:
        clean_desc = clean_desc[:35].rstrip("-")
    branch_sugg = f"{branch_type}/{ticket_ref}-{clean_desc}"

    if getattr(args, "json", False):
        print(json.dumps({
            "status": "ok",
            "action": "create",
            "ticket": ticket_ref,
            "id": res.get("id"),
            "sequence_id": seq_id,
            "name": res.get("name"),
            "branch_suggestion": branch_sugg,
            "url": web_url,
            "attachments": attached,
            "attachment_errors": attach_errors,
            "raw": res
        }, indent=2))
    else:
        print(f"\n🎉 Ticket creado exitosamente: {ticket_ref}")
        print(f"   • Título: {res.get('name')}")
        print(f"   • Prioridad: {res.get('priority', 'none').upper()}")
        print(f"   • Enlace: {web_url}")
        print(f"   • Sugerencia de rama Git: {branch_sugg}")
        if attached:
            print(f"   • Adjuntos: {', '.join(attached)}")
        for err in attach_errors:
            sys.stderr.write(f"   ⚠ No se pudo adjuntar {err} (el ticket sí se creó; usa plane-tracker attach {ticket_ref} <archivo>)\n")
        print("")


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

    # comment
    p_comment = subparsers.add_parser("comment", help="Publicar comentario en un ticket")
    p_comment.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    p_comment.add_argument("-m", "--message", help="Mensaje del comentario")
    p_comment.add_argument("-f", "--file", help="Archivo con el contenido")
    p_comment.add_argument("--track", help="Frente de trabajo (ej: main, subagent, review, datepicker)")
    p_comment.add_argument("--capacity", "--capacity-bucket", dest="capacity_bucket",
                           choices=["deep_work", "toil_support", "coordination", "tooling_dx", "research_rd", "tech_debt_paydown"],
                           help="Balde de capacidad de la sesión")
    p_comment.add_argument("--worker-type", choices=["human", "subagent", "agent:agy", "agent:claude", "agent:opencode"], help="Tipo de ejecutor")
    p_comment.add_argument("--duration", type=int, metavar="MIN",
                           help="Duración neta de la sesión en minutos (requerido si el contenido no lleva metadata telemétrica). Ej: --duration 5")
    p_comment.add_argument("--accept-proposal", action="store_true",
                           help="Registrar la duración propuesta (solo vale si se mostró hace menos de 30 min para este ticket)")
    p_comment.add_argument("--agent", choices=list(session_clock.AGENTS), help="Agente cuya sesión se mide (por defecto: según --worker-type o el entorno)")
    p_comment.add_argument("--session", metavar="ID", help="ID de la sesión del agente (por defecto: variable de entorno o directorio de trabajo)")
    p_comment.add_argument("--json", action="store_true", help="Salida en JSON")

    # link
    p_link = subparsers.add_parser("link", help="Adjuntar un enlace (PR, doc) al work item")
    p_link.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-205)")
    p_link.add_argument("url", help="URL del enlace (https://...)")
    p_link.add_argument("--title", help="Texto visible del enlace (por defecto: la URL)")

    attachments.register_attach(subparsers)
    attachments.register_attachments(subparsers)

    cmd_ops.register_health(subparsers)

    cmd_ops.register_handoff(subparsers)

    cmd_ops.register_focus(subparsers)

    # propose-duration
    p_prop = subparsers.add_parser("propose-duration", help="Medir la sesión del agente y proponer una duración (no registra nada)")
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
    p_prop.add_argument("--json", action="store_true", help="Salida en JSON")

    # create
    p_create = subparsers.add_parser("create", help="Crear un nuevo ticket / work item en Plane")
    p_create.add_argument("title", help="Título del ticket")
    p_create.add_argument("-d", "--description", help="Descripción o notas del ticket")
    p_create.add_argument("-p", "--project", help="Identificador del proyecto (por defecto OMNIFY)")
    p_create.add_argument("--priority", choices=["urgent", "high", "medium", "low", "none"], default="none", help="Prioridad del ticket")
    p_create.add_argument("--state", help="Estado inicial (por defecto Backlog)")
    p_create.add_argument("--labels", help="Etiquetas separadas por comas (ej: backend,bug,spike)")
    p_create.add_argument("--start-date", help="Fecha de inicio YYYY-MM-DD")
    p_create.add_argument("--due-date", help="Fecha de vencimiento YYYY-MM-DD")
    p_create.add_argument("--attach", nargs="+", metavar="FILE", help="Archivo(s) a adjuntar al crear el ticket (máx. 50 MB cada uno)")
    p_create.add_argument("--json", action="store_true", help="Salida en JSON")

    # comment-delete / comment-edit
    p_cdel = subparsers.add_parser("comment-delete", help="Eliminar un comentario (por defecto el último propio) y su worklog local")
    p_cdel.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OPS-13)")
    p_cdel.add_argument("--comment-id", help="UUID del comentario (por defecto: último comentario propio)")
    p_cedit = subparsers.add_parser("comment-edit", help="Editar un comentario y/o vincularle su worklog local sin publicar otro")
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

    # update
    p_update = subparsers.add_parser("update", help="Actualizar estado, prioridad o etiquetas de un ticket")
    p_update.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    p_update.add_argument("--state", help="Nuevo estado: Backlog, Pendiente, Progreso, Pruebas, Revisión, Completado, Pausado, Cancelado")
    p_update.add_argument("--priority", help="Prioridad: urgent, high, medium, low, none")
    p_update.add_argument("--labels", help="Etiquetas separadas por comas (ej: sms,backend,bug)")
    p_update.add_argument("--start-date", help="Fecha de inicio YYYY-MM-DD")
    p_update.add_argument("--due-date", help="Fecha de vencimiento YYYY-MM-DD")
    p_update.add_argument("--json", action="store_true", help="Salida en JSON")

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
        elif args.command == "comment":
            cmd_comment(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "link":
            cmd_link(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "propose-duration":
            cmd_propose_duration(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "comment-delete":
            cmd_comment_delete(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "comment-edit":
            cmd_comment_edit(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "create":
            cmd_create(args, conn, base_url, api_key, workspace, default_project_id)
        elif args.command == "update":
            cmd_update(args, conn, base_url, api_key, workspace, default_project_id)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
