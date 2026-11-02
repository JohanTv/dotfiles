"""Comando `delete`: elimina un work item en Plane y lo que la herramienta guardó de él en local.

Expone: register_delete(), cmd_delete().
No hace: encolar (sin conexión no se elimina nada) ni borrar en bloque. Sin `--yes` solo muestra qué se perdería.
"""

import json
import sys

from plane_cli.api import api_request
from plane_cli.config import add_json_flag
from plane_cli.resolve import get_project_identifier, resolve_issue, resolve_project_and_seq

# Tablas locales con datos del ticket: (tabla, columna que lo identifica, usa el UUID del ticket o su etiqueta PREFIJO-N).
_LOCAL_TABLES = (("worklogs", "ticket_id", "label"), ("issues_cache", "id", "uuid"), ("issue_snapshots", "issue_id", "uuid"),
                 ("state_transitions", "issue_id", "uuid"), ("flow_fetch", "issue_id", "uuid"))


def _local_footprint(conn, label):
    """Qué guarda la herramienta del ticket: minutos y cantidad de worklogs, y comentarios aún sin publicar."""
    wl = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(duration_minutes), 0) AS minutes FROM worklogs WHERE ticket_id = ?", (label,)).fetchone()
    pending = conn.execute("SELECT COUNT(*) FROM outbox WHERE ticket_ref = ? AND state IN ('pending', 'sending', 'failed')", (label,)).fetchone()[0]
    return {"worklogs": wl["n"], "minutes": wl["minutes"], "pending_outbox": pending}


def _forget_locally(conn, issue_id, label):
    """Borra de la base local todo rastro del ticket eliminado (Plane es la fuente de verdad y ya no lo tiene)."""
    with conn:
        for table, column, kind in _LOCAL_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (label if kind == "label" else issue_id,))
        conn.execute("DELETE FROM issues_fts WHERE ticket_id = ?", (label,))


def cmd_delete(args, conn, base_url, api_key, workspace, default_project_id):
    """Elimina un work item. Irreversible: sin `--yes` muestra el alcance y termina sin tocar nada."""
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, args.issue)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
    ident = get_project_identifier(conn, base_url, api_key, workspace, project_id)
    label = f"{ident}-{issue.get('sequence_id')}" if ident and issue.get("sequence_id") else issue_ref
    base = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/"
    comments = len(api_request(base + "comments/", api_key).get("results", []))
    local = _local_footprint(conn, label)

    if local["pending_outbox"]:
        sys.stderr.write(f"Error: {label} tiene {local['pending_outbox']} comentario(s) sin publicar en la cola de salida; "
                         "publícalos (outbox flush) o descártalos (outbox drop) antes de eliminarlo.\n")
        sys.exit(1)

    summary = {"ticket": label, "title": issue.get("name"), "comments": comments, "local_worklogs": local["worklogs"], "local_minutes": local["minutes"]}
    if not args.yes:
        if getattr(args, "json", False):
            print(json.dumps({"status": "needs_confirmation", "action": "delete", **summary}))
        else:
            print(f"⚠ Eliminar {label} «{issue.get('name')}» es irreversible: se pierden sus {comments} comentario(s), adjuntos y enlaces en Plane, "
                  f"y {local['worklogs']} worklog(s) local(es) ({local['minutes']} min), que viven en esos comentarios.")
            print(f"  Para conservarlo sin eliminar: plane-tracker update {label} --state Cancelado")
            print(f"  Para eliminarlo:               plane-tracker delete {label} --yes")
        sys.exit(1)

    api_request(base, api_key, method="DELETE")
    _forget_locally(conn, issue["id"], label)
    if getattr(args, "json", False):
        print(json.dumps({"status": "ok", "action": "delete", **summary}))
    else:
        print(f"✔ Ticket {label} eliminado de Plane ({comments} comentario(s)); {local['worklogs']} worklog(s) local(es) borrado(s)")


def register_delete(sub):
    p_delete = sub.add_parser("delete", help="Eliminar ticket (irreversible)",
                              description="Elimina un work item de Plane con sus comentarios, adjuntos y enlaces, y borra sus datos locales. "
                                          "Sin --yes solo muestra el alcance. Para conservarlo, `update --state Cancelado`.")
    p_delete.add_argument("issue", help="Ticket (ej: OPS-13); siempre explícito, no se deduce de la rama de Git")
    p_delete.add_argument("--yes", action="store_true", help="Confirma la eliminación")
    add_json_flag(p_delete)
    p_delete.set_defaults(handler=cmd_delete)
