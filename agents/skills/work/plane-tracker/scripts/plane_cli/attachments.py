"""Adjuntos del work item: subida por almacenamiento firmado, borrado y listado.

Expone: upload_attachment(), validate_attachment_paths(), build_multipart(), cmd_attach(), cmd_attachments(),
register_attach(), register_attachments().
No hace: crear tickets.
"""

import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid

import session_clock

from plane_cli.api import api_request
from plane_cli.config import add_json_flag
from plane_cli.resolve import resolve_issue, resolve_project_and_seq


ATTACH_MAX_BYTES = 50 * 1024 * 1024


def build_multipart(fields, filename, content_type, data):
    """multipart/form-data para el POST firmado de almacenamiento (el archivo debe ir al final)."""
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8") for k, v in fields.items()]
    safe_name = filename.replace('"', "_")
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe_name}"\r\nContent-Type: {content_type}\r\n\r\n'.encode("utf-8") + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def upload_attachment(base_url, api_key, workspace, project_id, issue_id, path):
    attachments_url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue_id}/issue-attachments/"
    name = os.path.basename(path)
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    with open(path, "rb") as handle:
        data = handle.read()
    created = api_request(attachments_url, api_key, method="POST", data={"name": name, "type": content_type, "size": len(data)})
    asset_id, upload = created["asset_id"], created["upload_data"]
    body, header = build_multipart(upload["fields"], name, content_type, data)
    try:
        req = urllib.request.Request(upload["url"], data=body, headers={"Content-Type": header}, method="POST")
        with urllib.request.urlopen(req, timeout=60):
            pass
        api_request(f"{attachments_url}{asset_id}/", api_key, method="PATCH", data={"is_uploaded": True})
    except BaseException:
        # No dejar un adjunto "pendiente" huérfano si falla la subida o la confirmación.
        try:
            api_request(f"{attachments_url}{asset_id}/", api_key, method="DELETE", raise_on_error=True)
        except Exception:
            pass
        raise
    return name, len(data)


def local_stamp(value):
    moment = session_clock.parse_time(value)
    return moment.astimezone().strftime("%Y-%m-%d %H:%M") if moment else ""


def validate_attachment_paths(paths):
    """Valida antes de tocar Plane: así un ticket no queda creado a medias por un archivo inválido."""
    for path in paths:
        if not os.path.isfile(path):
            sys.stderr.write(f"Error: '{path}' no es un archivo.\n")
            sys.exit(1)
        if os.path.getsize(path) > ATTACH_MAX_BYTES:
            sys.stderr.write(f"Error: '{path}' supera {ATTACH_MAX_BYTES // (1024 * 1024)} MB.\n")
            sys.exit(1)


def delete_attachment(base_url, api_key, workspace, project_id, issue_id, attachment_id):
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue_id}/issue-attachments/{attachment_id}/"
    api_request(url, api_key, method="DELETE")


def cmd_attach(args, conn, base_url, api_key, workspace, default_project_id):
    """Sube archivos al work item; con --replace ID sustituye un adjunto (sube el nuevo y luego borra el viejo)."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    validate_attachment_paths(args.files)
    if args.replace and len(args.files) != 1:
        sys.stderr.write("Error: --replace admite exactamente un archivo.\n")
        sys.exit(1)
    for path in args.files:
        try:
            name, size = upload_attachment(base_url, api_key, workspace, project_id, issue["id"], path)
        except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError) as exc:
            sys.stderr.write(f"Error subiendo '{path}': {exc}\n")
            sys.exit(1)
        print(f"✔ Adjunto subido a {issue_ref}: {name} ({size / 1024:.1f} KB)")
        if args.replace:
            delete_attachment(base_url, api_key, workspace, project_id, issue["id"], args.replace)
            print(f"✔ Adjunto anterior {args.replace} eliminado (reemplazado)")


def cmd_attachments(args, conn, base_url, api_key, workspace, default_project_id):
    """Lista los adjuntos del work item."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/issue-attachments/"
    if getattr(args, "delete", None):
        delete_attachment(base_url, api_key, workspace, project_id, issue["id"], args.delete)
        print(f"✔ Adjunto {args.delete} eliminado de {issue_ref}")
        return
    data = api_request(url, api_key)
    items = data if isinstance(data, list) else data.get("results", [])
    rows = [{"id": a.get("id"), "name": (a.get("attributes") or {}).get("name"), "size": (a.get("attributes") or {}).get("size") or a.get("size"),
             "created_at": a.get("created_at")} for a in items]
    if getattr(args, "json", False):
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    print(f"\n📎 Adjuntos de {issue_ref} ({len(rows)}):")
    for r in rows:
        print(f"   • {r['name']}  ({(r['size'] or 0) / 1024:.1f} KB)  {local_stamp(r['created_at'])}  {r['id']}")
    print("")


def register_attach(sub):
    p_attach = sub.add_parser("attach", help="Subir archivos al work item")
    p_attach.add_argument("issue", help="Ticket (ej: OMNIFY-205)")
    p_attach.add_argument("files", nargs="+", help="Archivo(s) a adjuntar (máx. 50 MB cada uno)")
    p_attach.add_argument("--replace", metavar="ID", help="Id de un adjunto a sustituir: sube el nuevo y, si salió bien, borra el anterior")
    p_attach.set_defaults(handler=cmd_attach)


def register_attachments(sub):
    p_attachments = sub.add_parser("attachments", help="Listar los adjuntos del work item")
    p_attachments.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-205)")
    add_json_flag(p_attachments)
    p_attachments.add_argument("--delete", metavar="ID", help="Eliminar el adjunto con ese id")
    p_attachments.set_defaults(handler=cmd_attachments)
