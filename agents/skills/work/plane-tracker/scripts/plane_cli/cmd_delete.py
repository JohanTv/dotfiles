"""Comando `delete`: elimina un work item en Plane y lo que la herramienta guardó de él en local.

Expone: register_delete(), cmd_delete().
No hace: encolar (sin conexión no se elimina nada) ni borrar en bloque. Los worklogs viven como comentarios del ticket, así que borrarlo
destruye horas: la decisión sale de lo que Plane tiene ahora (todos los comentarios, paginados) unido a lo que hay en la base local, y
falla cerrado (ante un dato dudoso no elimina). Horas de otros o de autor no confirmado: siempre se rechaza; horas propias: exigen
`--discard-worklogs`. Sin `--yes` solo muestra el alcance.
"""

import json
import re
import sys
import urllib.error
import urllib.parse

from plane_cli.api import api_request
from plane_cli.config import add_json_flag
from plane_cli.resolve import get_actor_uuid, get_project_identifier, resolve_issue, resolve_project_and_seq
from plane_cli.timeutil import time_to_minutes
from plane_cli.worklog import extract_metadata_from_comment

MAX_COMMENT_PAGES = 50
_REF_RE = re.compile(r"^(?:[A-Za-z0-9_]+-\d+|[0-9a-fA-F-]{36})$")
_MARKER = "PLANE_WORKLOG_METADATA"


def _stop(args, reason, message, **extra):
    """Termina con código 1 sin tocar nada: en --json el motivo va por stdout; si no, el texto por stderr."""
    if getattr(args, "json", False):
        print(json.dumps({"status": "refused", "action": "delete", "reason": reason, **extra}))
    else:
        sys.stderr.write(message + "\n")
    sys.exit(1)


def _read_comments(args, url, api_key):
    """Todos los comentarios del ticket (con cursor). Una lectura fallida o incompleta aborta: nunca se asume que no hay horas."""
    comments, cursor = [], None
    for _ in range(MAX_COMMENT_PAGES):
        try:
            data = api_request(url + (f"?cursor={urllib.parse.quote(cursor)}" if cursor else ""), api_key, raise_on_error=True)
        except urllib.error.HTTPError as exc:
            _stop(args, "unreadable", f"Error: no se pudieron leer los comentarios (HTTP {exc.code}); no se elimina nada.")
        comments += data.get("results", [])
        cursor = data.get("next_cursor")
        if not data.get("next_page_results") or not cursor:
            return comments
    _stop(args, "too_many_comments", "Error: el ticket tiene demasiados comentarios para verificar sus horas; no se elimina nada.")


def _minutes(meta):
    """Minutos que declara una metadata (0 si no se pueden leer: el registro cuenta igual como horas, solo sin cifra)."""
    dur = (meta or {}).get("duration_minutes") or (meta or {}).get("duration_net_minutes")
    if not dur and meta and meta.get("start_time") and meta.get("end_time"):
        dur = (time_to_minutes(meta["end_time"]) - time_to_minutes(meta["start_time"])) % (24 * 60)
    return dur if isinstance(dur, (int, float)) and dur > 0 else 0


def _hour_comments(comments):
    """Comentarios que parecen un worklog: metadata legible, tabla heredada o el bloque oculto aunque esté dañado (p. ej. escapado)."""
    found = []
    for c in comments:
        html = c.get("comment_html") or ""
        meta = extract_metadata_from_comment(html)
        if meta is not None or _MARKER in html:
            found.append({"id": c.get("id"), "minutes": _minutes(meta), "author": c.get("created_by") or c.get("actor")})
    return found


def _assess(conn, label, found, actor):
    """Horas en juego: remotas por autor (propias solo si el actor está confirmado) más las filas locales sin comentario en Plane."""
    remote_ids = {f["id"] for f in found}
    mine = [f for f in found if actor and f["author"] == actor]
    rows = conn.execute("SELECT plane_comment_id, duration_minutes, author_id FROM worklogs WHERE ticket_id = ?", (label,)).fetchall()
    local_only = [r for r in rows if r["plane_comment_id"] not in remote_ids]
    # Una fila local sin autor registrado se trata como propia (se creó en esta máquina); con autor, solo si es el actor confirmado.
    own_local = [r for r in local_only if r["author_id"] is None or (actor and r["author_id"] == actor)]
    return {"hours_foreign": len(found) - len(mine) + len(local_only) - len(own_local), "hours_own": len(mine) + len(own_local),
            "hours_local_only": len(local_only), "own_minutes": sum(f["minutes"] for f in mine) + sum(r["duration_minutes"] for r in own_local),
            "actor_known": bool(actor)}


def _has_signed_local_hours(conn, label):
    return bool(conn.execute("SELECT 1 FROM worklogs WHERE ticket_id = ? AND author_id IS NOT NULL LIMIT 1", (label,)).fetchone())


def _identify(conn, base_url, api_key, workspace, project_id, issue, issue_ref):
    """(etiqueta PREFIJO-N, UUID) del ticket; con el ticket ya inexistente en Plane, lo que la caché local recuerde de él."""
    if issue:
        ident = get_project_identifier(conn, base_url, api_key, workspace, project_id)
        return (f"{ident}-{issue['sequence_id']}" if ident and issue.get("sequence_id") else issue_ref), issue["id"]
    is_uuid = bool(re.match(r"^[0-9a-fA-F-]{36}$", issue_ref))
    row = conn.execute(f"SELECT id, ticket_id FROM issues_cache WHERE {'id' if is_uuid else 'ticket_id'} = ?", (issue_ref,)).fetchone()
    return (row["ticket_id"] if row else (None if is_uuid else issue_ref)), (row["id"] if row else None)


def _forget_locally(conn, issue_id, label):
    """Borra de la base local todo rastro del ticket eliminado (Plane es la fuente de verdad y ya no lo tiene)."""
    with conn:
        conn.execute("DELETE FROM worklogs WHERE ticket_id = ?", (label,))
        conn.execute("DELETE FROM outbox WHERE wl_ticket_id = ? AND state IN ('sent', 'dropped')", (label,))
        conn.execute("DELETE FROM issues_fts WHERE ticket_id = ?", (label,))
        conn.execute("DELETE FROM issues_cache WHERE ticket_id = ? OR id = ?", (label, issue_id or ""))
        conn.execute("DELETE FROM assignment_events WHERE ticket_id = ? OR issue_id = ?", (label, issue_id or ""))
        for table in ("issue_snapshots", "state_transitions", "flow_fetch"):
            conn.execute(f"DELETE FROM {table} WHERE issue_id = ?", (issue_id or "",))


def _refuse_if_hours(args, label, plan, summary):
    if plan["hours_foreign"]:
        hint = "" if plan["actor_known"] else " (sin PLANE_USERNAME ni PLANE_ACTOR_UUID no se puede confirmar quién las registró)"
        _stop(args, "foreign_hours", f"Error: {label} tiene {plan['hours_foreign']} registro(s) de horas que no son tuyos o de autor no confirmado{hint}; "
              f"eliminar el ticket los destruiría. Conserva el ticket: plane-tracker update {label} --state Cancelado", **summary)
    if plan["hours_own"] and not args.discard_worklogs:
        _stop(args, "needs_discard", f"Error: {label} tiene {plan['hours_own']} registro(s) de horas tuyas ({plan['own_minutes']} min); eliminar el ticket las "
              f"destruiría y las horas son trabajo real. Conserva el ticket: plane-tracker update {label} --state Cancelado. "
              f"Si de verdad quieres perderlas: plane-tracker delete {label} --yes --discard-worklogs", **summary)


def cmd_delete(args, conn, base_url, api_key, workspace, default_project_id):
    """Elimina un work item. Irreversible: sin `--yes` muestra el alcance y termina sin tocar nada."""
    ref = (args.issue or "").strip()
    if not _REF_RE.match(ref):
        _stop(args, "bad_ref", "Error: delete exige el ticket completo (PREFIJO-N o UUID); no acepta '@', '.', números sueltos ni la rama de Git.")
    project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, ref)
    issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref, missing_ok=True)
    label, issue_id = _identify(conn, base_url, api_key, workspace, project_id, issue, issue_ref)
    traces = label and conn.execute("SELECT 1 FROM worklogs WHERE ticket_id = ? UNION ALL SELECT 1 FROM issues_cache WHERE ticket_id = ?", (label, label)).fetchone()
    if not issue and not traces:
        _stop(args, "not_found", f"Error: {ref} no existe en Plane y no hay nada local que limpiar.")

    base = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue_id}/"
    comments = _read_comments(args, base + "comments/", api_key) if issue else []
    found = _hour_comments(comments)
    plan = _assess(conn, label, found, get_actor_uuid(base_url, api_key, workspace, conn) if found or _has_signed_local_hours(conn, label) else None)
    summary = {"ticket": label, "title": issue.get("name") if issue else None, "comments": len(comments), "already_gone": not issue,
               **{k: plan[k] for k in ("hours_own", "hours_foreign", "hours_local_only", "own_minutes")}}

    pending = conn.execute("SELECT COUNT(*) FROM outbox WHERE (ticket_ref = ? OR wl_ticket_id = ?) AND state IN ('pending', 'sending', 'failed')", (label, label)).fetchone()[0]
    if pending:
        _stop(args, "pending_outbox", f"Error: {label} tiene {pending} comentario(s) sin publicar en la cola de salida; "
              "publícalos (outbox flush) o descártalos (outbox drop) antes de eliminarlo.", **summary)
    _refuse_if_hours(args, label, plan, summary)

    if not args.yes:
        if getattr(args, "json", False):
            print(json.dumps({"status": "needs_confirmation", "action": "delete", **summary}))
        else:
            what = (f"se pierden sus {len(comments)} comentario(s) en Plane y {plan['hours_own']} registro(s) de horas tuyas ({plan['own_minutes']} min)"
                    if issue else "ya no existe en Plane: solo se limpiaría lo local")
            print(f"⚠ Eliminar {label} «{summary['title'] or '—'}» es irreversible: {what}.")
            print("  También se pierden adjuntos, enlaces, subtareas e historial (no se han consultado).")
            print(f"  Para conservarlo sin eliminar: plane-tracker update {label} --state Cancelado")
            print(f"  Para eliminarlo:               plane-tracker delete {label} --yes" + (" --discard-worklogs" if plan["hours_own"] else ""))
        sys.exit(1)

    if issue:
        api_request(base, api_key, method="DELETE")
    _forget_locally(conn, issue_id, label)
    if getattr(args, "json", False):
        print(json.dumps({"status": "ok", "action": "delete", **summary}))
    else:
        print(f"✔ Ticket {label} " + ("eliminado de Plane" if issue else "ya no existía en Plane; lo local se limpió")
              + f" ({plan['hours_own']} registro(s) de horas descartado(s))")


def register_delete(sub):
    p_delete = sub.add_parser("delete", help="Eliminar ticket (irreversible)",
                              description="Elimina un work item de Plane con sus comentarios, adjuntos y enlaces, y borra sus datos locales. Sin --yes solo "
                                          "muestra el alcance. Con horas propias exige --discard-worklogs; con horas de otros se niega. "
                                          "Para conservarlo, `update --state Cancelado`.")
    p_delete.add_argument("issue", help="Ticket completo (ej: OPS-13); no se deduce de la rama de Git")
    p_delete.add_argument("--yes", action="store_true", help="Confirma la eliminación")
    p_delete.add_argument("--discard-worklogs", action="store_true", help="Acepta perder las horas propias registradas en el ticket")
    add_json_flag(p_delete)
    p_delete.set_defaults(handler=cmd_delete)
