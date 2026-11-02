"""Consulta de la vista `get`: arma la fila del vocabulario `ticket_detail` a partir de la fuente adquirida y de los nombres que hay en SQLite.

Expone: query().
No hace: red ni escribir. La API se pidió en freshness.ensure_get; aquí solo se leen estados, miembros y etiquetas locales.
`complete` es true solo si el ticket vino de la API y sus comentarios se leyeron completos (con instantánea o sin comentarios, None). Las etiquetas se
omiten si alguna no se conoce y los enlaces y adjuntos no se leen en `get` (ausente = no leído): nunca se inventa un dato.
"""

import re
from dataclasses import replace

from plane_cli.coverage import Result, complete_get


def _plain(html):
    """Texto plano de un HTML de Plane, sin bloques ocultos de telemetría."""
    return " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<!--[\s\S]*?-->", "", html or "")).split())


def _uid(value):
    return value.get("id") if isinstance(value, dict) else value


def _state(conn, issue, source):
    row = conn.execute("SELECT name, group_name FROM states WHERE id = ?", (issue.get("state"),)).fetchone()
    if row:
        return row["name"], row["group_name"]
    cached = conn.execute("SELECT state_name, state_group FROM issues_cache WHERE id = ?", (issue.get("id"),)).fetchone()
    return (source.state_name or (cached["state_name"] if cached else None) or "unknown"), (cached["state_group"] if cached else "unknown")


def _labels(conn, issue, project_id):
    ids = [_uid(i) for i in issue.get("labels") or []]
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM labels WHERE project_id = ?", (project_id,))}
    return [names[i] for i in ids] if "labels" in issue and all(i in names for i in ids) else None


def _row(conn, source, no_description):
    issue = source.issue
    state, group = _state(conn, issue, source)
    row = {"ticket": source.issue_ref, "uuid": issue.get("id"), "title": issue.get("name"), "state": state, "state_group": group,
           "priority": issue.get("priority", "none"), "project": source.issue_ref.rsplit("-", 1)[0], "created_by": _uid(issue.get("created_by")),
           "start_date": issue.get("start_date"), "target_date": issue.get("target_date"), "created_at": issue.get("created_at"),
           "completed_at": issue.get("completed_at"), "plane_updated_at": issue.get("updated_at")}
    if "assignees" in issue:
        members = {r["user_id"]: r["name"] for r in conn.execute("SELECT user_id, name FROM members")}
        row["assignees"] = [{"id": u, "name": members.get(u) or u[:8]} for u in (_uid(a) for a in issue["assignees"]) if u]
    labels = _labels(conn, issue, source.project_id)
    if labels is not None:
        row["labels"] = labels
    if not no_description and not source.metadata_only:
        row["description"] = _plain(issue.get("description_html") or issue.get("description"))
    if source.flow:
        row["flow"] = source.flow
    return row


def query(conn, source, last=None, no_description=False):
    """Result de `get`: una fila, con los comentarios (`{id, author, created_at, text}`, los últimos `last`) si se leyeron."""
    row = _row(conn, source, no_description)
    detail = {}
    if source.comments is not None:
        shown = source.comments[-last:] if last else source.comments
        row["comments"] = [{"id": c.get("id"), "author": c.get("actor") or _uid(c.get("created_by")), "created_at": c.get("created_at"),
                            "text": _plain(c.get("comment_html"))} for c in shown]
        detail["comments"] = {"shown": len(shown), "total": len(source.comments)}
    if source.metadata_only:
        detail["metadata_only"] = True
    cov = replace(source.coverage, detail=detail)
    return Result(rows=[row], total=1, coverage=replace(cov, complete=complete_get(cov, source.comments_read)))
