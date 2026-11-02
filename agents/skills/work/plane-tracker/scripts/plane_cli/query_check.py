"""Consulta de la vista `worklog check`: transforma lo que la auditoría contra Plane trajo (freshness.audit_worklogs) en el sobre; no toca la red ni SQLite.

Expone: query().
`summary.ok` es falso si hay alguna inconsistencia (códigos de vocabulary.CHECK_ERROR_CODES); `unreachable` cuenta los tickets que no se pudieron comprobar. Es una auditoría de red por diseño:
queda fuera de F5.
"""

from plane_cli import vocabulary
from plane_cli.coverage import Result


def query(audit, coverage):
    errors = [i for i in audit.issues if i["code"] in vocabulary.CHECK_ERROR_CODES]
    unreachable = sum(1 for i in audit.issues if i["code"] == "unreachable")
    return Result(rows=audit.issues, total=len(audit.issues), coverage=coverage,
                  summary={"ok": not errors, "unreachable": unreachable, "checked": audit.checked})
