"""Comandos que escriben en el work item: `create`, `update` y `link`.

Expone: register(), cmd_create(), cmd_update(), cmd_link().
No hace: comentarios ni adjuntos sueltos.
"""

import json
import re
import sys
import urllib.error
from datetime import datetime

from plane_cli.api import api_request
from plane_cli.attachments import upload_attachment, validate_attachment_paths
from plane_cli.mdhtml import markdown_to_html
from plane_cli.resolve import get_labels_map, get_projects_map, get_states_map, resolve_issue, resolve_project_and_seq


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


def register_link(sub):
    p_link = sub.add_parser("link", help="Adjuntar un enlace (PR, doc) al work item")
    p_link.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-205)")
    p_link.add_argument("url", help="URL del enlace (https://...)")
    p_link.add_argument("--title", help="Texto visible del enlace (por defecto: la URL)")
    p_link.set_defaults(handler=cmd_link)


def register_update(sub):
    p_update = sub.add_parser("update", help="Actualizar estado, prioridad o etiquetas de un ticket")
    p_update.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-162, OPS-44 o auto-detectado de Git)")
    p_update.add_argument("--state", help="Nuevo estado: Backlog, Pendiente, Progreso, Pruebas, Revisión, Completado, Pausado, Cancelado")
    p_update.add_argument("--priority", help="Prioridad: urgent, high, medium, low, none")
    p_update.add_argument("--labels", help="Etiquetas separadas por comas (ej: sms,backend,bug)")
    p_update.add_argument("--start-date", help="Fecha de inicio YYYY-MM-DD")
    p_update.add_argument("--due-date", help="Fecha de vencimiento YYYY-MM-DD")
    p_update.add_argument("--json", action="store_true", help="Salida en JSON")
    p_update.set_defaults(handler=cmd_update)


def register_create(sub):
    p_create = sub.add_parser("create", help="Crear un nuevo ticket / work item en Plane")
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
    p_create.set_defaults(handler=cmd_create)
