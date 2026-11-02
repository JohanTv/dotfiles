"""Adjuntos del work item: subida por almacenamiento firmado, borrado y listado.

Expone: upload_attachment(), validate_attachment_paths(), build_multipart(), attachment_id(), cmd_attachment_add(),
cmd_attachment_list(), cmd_attachment_delete(), cmd_attachment_replace(), register_attachment_add/list/delete/replace().
No hace: crear tickets.
"""

import argparse
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid

import session_clock

from plane_cli import vocabulary
from plane_cli.api import api_request, fail_http, http_detail
from plane_cli.config import add_json_flag
from plane_cli.envelope import build, dumps
from plane_cli.errors import CliError
from plane_cli.freshness import Env, fetch_attachments
from plane_cli.output import emit
from plane_cli.resolve import resolve_issue, resolve_project_and_seq
from plane_cli.views import VIEWS


ATTACH_MAX_BYTES = 50 * 1024 * 1024
UNSUPPORTED_ATTACH_EXTENSIONS = frozenset({".sql"})


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
    try:
        created = api_request(
            attachments_url,
            api_key,
            method="POST",
            data={"name": name, "type": content_type, "size": len(data)},
            raise_on_error=True,
        )
    except urllib.error.HTTPError as exc:
        detail = http_detail(exc)
        exc.close()
        if exc.code == 400 and any(msg in detail.lower() for msg in ("invalid file type", "file type not allowed", "unsupported file type")):
            raise CliError(
                "invalid_input",
                f"Plane rechazó '{name}': tipo de archivo no permitido.",
                hint="Convierte o renombra el archivo a .txt o .md para subirlo como adjunto.",
            ) from exc
        fail_http(attachments_url, exc.code, detail)
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
            raise CliError("not_found", f"'{path}' no es un archivo.")
        if os.path.getsize(path) > ATTACH_MAX_BYTES:
            raise CliError("invalid_input", f"'{path}' supera {ATTACH_MAX_BYTES // (1024 * 1024)} MB.")
        _, ext = os.path.splitext(path)
        if ext.lower() in UNSUPPORTED_ATTACH_EXTENSIONS:
            raise CliError(
                "invalid_input",
                f"'{path}' tiene una extensión no admitida por Plane ({ext.lower()}).",
                hint="Plane no admite archivos de este tipo como adjuntos. Convierte o renombra el archivo a .txt o .md para subirlo.",
            )


def delete_attachment(base_url, api_key, workspace, project_id, issue_id, attachment_id):
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue_id}/issue-attachments/{attachment_id}/"
    api_request(url, api_key, method="DELETE")


def attachment_id(value):
    """Tipo argparse: UUID de adjunto; se rechaza antes de tocar la red."""
    try:
        uuid.UUID(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' no es un UUID de adjunto (ver `attachment list`)")
    return value


def _upload_files(args, conn, base_url, api_key, workspace, default_project_id, files):
    """Resuelve el ticket, valida los archivos y los sube; devuelve (project_id, issue, issue_ref, uploaded)."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    validate_attachment_paths(files)
    uploaded = []
    as_json = getattr(args, "json", False)
    for path in files:
        try:
            name, size = upload_attachment(base_url, api_key, workspace, project_id, issue["id"], path)
        except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError) as exc:
            raise CliError("http_error", f"Error subiendo '{path}': {exc}")
        uploaded.append({"name": name, "size": size})
        if not as_json:
            print(f"✔ Adjunto subido a {issue_ref}: {name} ({size / 1024:.1f} KB)")
    return project_id, issue, issue_ref, uploaded


def cmd_attachment_add(args, conn, base_url, api_key, workspace, default_project_id):
    """Sube archivos al work item."""
    project_id, issue, issue_ref, uploaded = _upload_files(args, conn, base_url, api_key, workspace, default_project_id, args.files)
    if getattr(args, "json", False):
        doc = {
            "schema": vocabulary.SCHEMA,
            "status": "ok",
            "action": "attachment add",
            "ticket": issue_ref,
            "uuid": issue["id"],
            "attachments": uploaded,
        }
        print(dumps(doc))


def cmd_attachment_replace(args, conn, base_url, api_key, workspace, default_project_id):
    """Sustituye un adjunto: sube el nuevo y, si salió bien, borra el anterior."""
    project_id, issue, issue_ref, uploaded = _upload_files(args, conn, base_url, api_key, workspace, default_project_id, [args.file])
    delete_attachment(base_url, api_key, workspace, project_id, issue["id"], args.id)
    if getattr(args, "json", False):
        doc = {
            "schema": vocabulary.SCHEMA,
            "status": "ok",
            "action": "attachment replace",
            "ticket": issue_ref,
            "uuid": issue["id"],
            "attachment_id": args.id,
            "name": uploaded[0]["name"] if uploaded else None,
            "size": uploaded[0]["size"] if uploaded else None,
        }
        print(dumps(doc))
    else:
        print(f"✔ Adjunto anterior {args.id} eliminado (reemplazado)")


def cmd_attachment_delete(args, conn, base_url, api_key, workspace, default_project_id):
    """Elimina un adjunto del work item."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    delete_attachment(base_url, api_key, workspace, project_id, issue["id"], args.id)
    if getattr(args, "json", False):
        doc = {
            "schema": vocabulary.SCHEMA,
            "status": "ok",
            "action": "attachment delete",
            "ticket": issue_ref,
            "uuid": issue["id"],
            "attachment_id": args.id,
        }
        print(dumps(doc))
    else:
        print(f"✔ Adjunto {args.id} eliminado de {issue_ref}")


def cmd_attachment_list(args, conn, base_url, api_key, workspace, default_project_id):
    """Lista los adjuntos del work item."""
    view = VIEWS["attachment list"]
    issue_ref, items, coverage = fetch_attachments(conn, Env(base_url, api_key, workspace, default_project_id), args.issue)
    emit(view, build(view.name, None, view.query(issue_ref, items, coverage)), getattr(args, "json", False))


def register_attachment_add(sub):
    p_add = sub.add_parser("add", help="Subir archivos al ticket")
    p_add.add_argument("issue", help="Ticket (ej: OMNIFY-205)")
    p_add.add_argument("files", nargs="+", help="Archivo(s) a adjuntar (máx. 50 MB cada uno)")
    add_json_flag(p_add)
    p_add.set_defaults(handler=cmd_attachment_add)


def register_attachment_list(sub):
    p_list = sub.add_parser("list", help="Listar los adjuntos del ticket")
    p_list.add_argument("issue", nargs="?", default=None, help="Ticket (ej: OMNIFY-205)")
    add_json_flag(p_list)
    p_list.set_defaults(handler=cmd_attachment_list)


def register_attachment_delete(sub):
    p_delete = sub.add_parser("delete", help="Eliminar un adjunto del ticket")
    p_delete.add_argument("issue", help="Ticket (ej: OMNIFY-205)")
    p_delete.add_argument("id", type=attachment_id, help="UUID del adjunto (ver `attachment list`)")
    add_json_flag(p_delete)
    p_delete.set_defaults(handler=cmd_attachment_delete)


def register_attachment_replace(sub):
    p_replace = sub.add_parser("replace", help="Sustituir un adjunto por otro archivo",
                                 description="Sube el archivo nuevo y, si salió bien, borra el adjunto anterior.")
    p_replace.add_argument("issue", help="Ticket (ej: OMNIFY-205)")
    p_replace.add_argument("id", type=attachment_id, help="UUID del adjunto a sustituir (ver `attachment list`)")
    p_replace.add_argument("file", help="Archivo nuevo (máx. 50 MB)")
    add_json_flag(p_replace)
    p_replace.set_defaults(handler=cmd_attachment_replace)
