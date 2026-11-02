"""Consultas de las vistas de catálogo `labels` y `projects`: filas de SQLite ordenadas por nombre o identificador.

Expone: labels(), projects().
No hace: red ni escribir (el refresco con TTL es freshness.ensure_catalog).
"""

from dataclasses import replace

from plane_cli.coverage import Result


def labels(conn, project, coverage):
    rows = conn.execute("SELECT id, name, color FROM labels WHERE project_id = ? ORDER BY name ASC, id", (project.uuid,)).fetchall()
    return Result(rows=[{"id": r["id"], "name": r["name"], "color": r["color"]} for r in rows], total=len(rows), coverage=replace(coverage))


def projects(conn, workspace, coverage):
    rows = conn.execute("SELECT project_id, identifier, name FROM projects WHERE workspace = ? ORDER BY identifier", (workspace,)).fetchall()
    return Result(rows=[{"id": r["project_id"], "identifier": r["identifier"], "name": r["name"]} for r in rows], total=len(rows), coverage=replace(coverage))
