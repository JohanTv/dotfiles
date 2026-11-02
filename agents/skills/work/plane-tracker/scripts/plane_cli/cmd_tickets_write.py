"""Comandos que escriben en el work item: `create`, `update` y `link add`.

Expone: register_create(), register_update(), register_link_add(), cmd_create(), cmd_update(), cmd_link().
No hace: comentarios ni adjuntos sueltos.
"""

import json
import re
import sys
import urllib.error
from datetime import datetime

from plane_cli import create_guard, envelope, vocabulary
from plane_cli.api import PlaneUnavailable, api_request
from plane_cli.config import add_json_flag
from plane_cli.attachments import upload_attachment, validate_attachment_paths
from plane_cli.errors import CliError
from plane_cli.mdhtml import markdown_to_html
from plane_cli.resolve import get_labels_map, get_projects_map, get_states_map, resolve_issue, resolve_project_and_seq


def cmd_link(args, conn, base_url, api_key, workspace, default_project_id):
    """Adjunta un enlace (PR, doc) al work item: aparece en su panel de enlaces, sin notificar como comentario."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    if not re.match(r"^https?://", args.url):
        raise CliError("invalid_input", "la URL debe empezar por http:// o https://")
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/links/"
    existing = api_request(url, api_key).get("results", [])
    already = any(l.get("url") == args.url for l in existing)
    if not already:
        api_request(url, api_key, method="POST", data={"url": args.url, "title": args.title or args.url})
    if getattr(args, "json", False):
        doc = {
            "schema": vocabulary.SCHEMA,
            "status": "ok",
            "action": "link add",
            "ticket": issue_ref,
            "uuid": issue["id"],
            "title": args.title or args.url,
            "url": args.url,
            "already_exists": already,
        }
        print(envelope.dumps(doc))
    else:
        if already:
            print(f"✔ {issue_ref} ya tiene ese enlace")
        else:
            print(f"✔ Enlace añadido a {issue_ref}: {args.title or args.url}")


def _description_html(text):
    """Convierte la descripción a HTML: si ya empieza como HTML se respeta, si no se trata como Markdown."""
    desc = text.strip()
    if desc.startswith("<") and ">" in desc:
        return desc
    return markdown_to_html(desc)


def _read_description(args):
    """Lee la descripción de `-d/--description` o `-f/--description-file`; None si no se indicó ninguna."""
    if getattr(args, "description", None) and getattr(args, "description_file", None):
        raise CliError("invalid_input", "usa --description o --description-file, no ambos.")
    if getattr(args, "description_file", None):
        try:
            with open(args.description_file, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            raise CliError("invalid_input", f"no se pudo leer '{args.description_file}': {exc}")
    else:
        text = getattr(args, "description", None)
    if text is None:
        return None
    if not text.strip():
        raise CliError("invalid_input", "La descripción no puede estar vacía.")
    return text


def cmd_update(args, conn, base_url, api_key, workspace, default_project_id):
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    args.issue = issue_ref
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    patch_data = {}

    if args.title is not None:
        title = args.title.strip()
        if not title:
            raise CliError("invalid_input", "El título no puede estar vacío.")
        patch_data["name"] = title

    description = _read_description(args)
    if description is not None:
        patch_data["description_html"] = _description_html(description)

    if args.state:
        states_map = get_states_map(conn, base_url, api_key, workspace, project_id)
        target_state = args.state.lower().strip().replace("ó", "o").replace("é", "e").replace("á", "a")
        if target_state not in states_map:
            raise CliError("unknown_state", f"Estado desconocido '{args.state}'.",
                           hint=f"Estados válidos en proyecto: {', '.join(states_map.keys())}")
        patch_data["state"] = states_map[target_state]

    if args.priority:
        prio = args.priority.lower().strip()
        if prio not in ("urgent", "high", "medium", "low", "none"):
            raise CliError("invalid_input", f"Prioridad desconocida '{args.priority}'.",
                           hint="Opciones: urgent, high, medium, low, none.")
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
                raise CliError("bad_date", f"Fecha inválida '{val}'. Formato: YYYY-MM-DD.")
            patch_data[field] = val

    if not patch_data:
        sys.stderr.write("Advertencia: No se indicaron cambios para actualizar (--title, --description, --state, --priority, --labels, --start-date o --due-date).\n")
        return

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/"
    res = api_request(url, api_key, method="PATCH", data=patch_data)
    
    if getattr(args, "json", False):
        doc = {
            "schema": vocabulary.SCHEMA,
            "status": "ok",
            "action": "update",
            "ticket": issue_ref,
            "uuid": issue["id"],
            "patched": patch_data,
        }
        print(envelope.dumps(doc))
    else:
        changes = []
        if "name" in patch_data: changes.append(f"Título ➔ {patch_data['name']}")
        if "description_html" in patch_data: changes.append("Descripción ➔ actualizada")
        if "state" in patch_data: changes.append(f"Estado ➔ {args.state}")
        if "priority" in patch_data: changes.append(f"Prioridad ➔ {args.priority}")
        if "labels" in patch_data: changes.append(f"Etiquetas ➔ {args.labels}")
        if "start_date" in patch_data: changes.append(f"Inicio ➔ {patch_data['start_date']}")
        if "target_date" in patch_data: changes.append(f"Vence ➔ {patch_data['target_date']}")
        print(f"✔ Ticket {args.issue} actualizado con éxito: [{', '.join(changes)}]")


def _submit_issue(args, conn, base_url, api_key, workspace, project_id, project_ident, payload):
    """Envía la creación evitando duplicados: compara el título con los tickets recientes y marca el envío hasta confirmarlo."""
    title = payload["name"]
    if not getattr(args, "allow_duplicate", False):
        duplicates = create_guard.recent_duplicates(conn, base_url, api_key, workspace, project_id, project_ident, title)
        if duplicates:
            ticket, age = duplicates[0]
            raise CliError("duplicate", f"ya existe un ticket con ese título en {project_ident}: {ticket} (creado hace {age}).",
                           hint="Si es un reintento tras un error de red no lo repitas; para crear otro igual usa --allow-duplicate.")

    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/"
    create_guard.mark_unconfirmed(conn, project_id, title)
    try:
        res = api_request(url, api_key, method="POST", data=payload)
    except PlaneUnavailable as exc:
        if exc.delivered == "no":
            create_guard.clear_mark(conn, project_id, title)
        raise
    except (SystemExit, CliError):
        create_guard.clear_mark(conn, project_id, title)
        raise
    create_guard.clear_mark(conn, project_id, title)
    return res


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
                raise CliError("unknown_project", f"Proyecto '{args.project}' no encontrado.",
                               hint=f"Opciones: {', '.join(projects_map.keys())}")
    else:
        for k, v in projects_map.items():
            if v["id"] == project_id:
                project_ident = k
                break

    payload = {
        "name": args.title.strip()
    }

    if getattr(args, "description", None):
        payload["description_html"] = _description_html(args.description)

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
            raise CliError("unknown_state", f"Estado desconocido '{args.state}'.",
                           hint=f"Estados válidos: {', '.join(states_map.keys())}")

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

    res = _submit_issue(args, conn, base_url, api_key, workspace, project_id, project_ident, payload)

    # Plane no admite adjuntos en la creación: se suben justo después (el ticket ya existe si alguno falla).
    attached, attach_errors = [], []
    for path in attach_paths:
        try:
            name, _ = upload_attachment(base_url, api_key, workspace, project_id, res["id"], path)
            attached.append(name)
        except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError, SystemExit, CliError) as exc:
            err_msg = exc.render() if isinstance(exc, CliError) else str(exc)
            attach_errors.append(f"{path}: {err_msg}")

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
        doc = {
            "schema": vocabulary.SCHEMA,
            "status": "ok",
            "action": "create",
            "ticket": ticket_ref,
            "uuid": res.get("id"),
            "name": res.get("name"),
            "branch_suggestion": branch_sugg,
            "url": web_url,
            "attachments": attached,
            "attachment_errors": attach_errors,
        }
        print(envelope.dumps(doc))
    else:
        print(f"\n🎉 Ticket creado exitosamente: {ticket_ref}")
        print(f"   • Título: {res.get('name')}")
        print(f"   • Prioridad: {res.get('priority', 'none').upper()}")
        print(f"   • Enlace: {web_url}")
        print(f"   • Sugerencia de rama Git: {branch_sugg}")
        if attached:
            print(f"   • Adjuntos: {', '.join(attached)}")
        for err in attach_errors:
            sys.stderr.write(f"   ⚠ No se pudo adjuntar {err} (el ticket sí se creó; usa plane-tracker attachment add {ticket_ref} <archivo>)\n")
        print("")


def register_link_add(sub):
    p_link = sub.add_parser("add", help="Adjuntar un enlace al ticket",
                             description="Adjunta un enlace (PR, documento) al work item.")
    p_link.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-205)")
    p_link.add_argument("url", help="URL del enlace (https://...)")
    p_link.add_argument("--title", help="Texto visible del enlace (por defecto: la URL)")
    add_json_flag(p_link)
    p_link.set_defaults(handler=cmd_link)


def register_update(sub):
    p_update = sub.add_parser("update", help="Editar título, descripción, estado y demás campos")
    p_update.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    p_update.add_argument("--title", help="Nuevo título del ticket")
    p_update.add_argument("-d", "--description", help="Nueva descripción (Markdown o HTML); reemplaza la actual")
    p_update.add_argument("-f", "--description-file", help="Archivo con la nueva descripción (Markdown o HTML); reemplaza la actual")
    p_update.add_argument("--state", help="Nuevo estado: Backlog, Pendiente, Progreso, Pruebas, Revisión, Completado, Pausado, Cancelado")
    p_update.add_argument("--priority", help="Prioridad: urgent, high, medium, low, none")
    p_update.add_argument("--labels", help="Etiquetas separadas por comas (ej: sms,backend,bug)")
    p_update.add_argument("--start-date", help="Fecha de inicio YYYY-MM-DD")
    p_update.add_argument("--due-date", help="Fecha de vencimiento YYYY-MM-DD")
    add_json_flag(p_update)
    p_update.set_defaults(handler=cmd_update)


def register_create(sub):
    p_create = sub.add_parser("create", help="Crear un ticket")
    p_create.add_argument("title", help="Título del ticket")
    p_create.add_argument("-d", "--description", help="Descripción o notas del ticket")
    p_create.add_argument("-p", "--project", help="Identificador del proyecto (por defecto OMNIFY)")
    p_create.add_argument("--priority", choices=["urgent", "high", "medium", "low", "none"], default="none", help="Prioridad del ticket")
    p_create.add_argument("--state", help="Estado inicial (por defecto Backlog)")
    p_create.add_argument("--labels", help="Etiquetas separadas por comas (ej: backend,bug,spike)")
    p_create.add_argument("--start-date", help="Fecha de inicio YYYY-MM-DD")
    p_create.add_argument("--due-date", help="Fecha de vencimiento YYYY-MM-DD")
    p_create.add_argument("--allow-duplicate", action="store_true", help="Crear aunque haya un ticket reciente con el mismo título")
    p_create.add_argument("--attach", nargs="+", metavar="FILE", help="Archivo(s) a adjuntar al crear el ticket (máx. 50 MB cada uno)")
    add_json_flag(p_create)
    p_create.set_defaults(handler=cmd_create)
