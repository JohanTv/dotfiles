"""Barrido del historial de asignación de `list --refresh-history` (se retira en la fase 6 a favor de `sync --history`).

Expone: sweep().
No hace: consultar tickets para el usuario. Una petición de actividades por ticket pendiente, con presupuesto, reanudable y sin perder lo ya guardado.
"""

import sys

from plane_cli.assignments import sweep_history
from plane_cli.flow import fetch_transitions


def sweep(conn, env, project_ids, budget):
    marks = ",".join("?" for _ in project_ids)
    rows = conn.execute(f"SELECT * FROM issues_cache WHERE project_id IN ({marks})", project_ids).fetchall()
    fetch = lambda r: fetch_transitions(conn, env.base_url, env.api_key, env.workspace, r["project_id"],
                                        {"id": r["id"], "updated_at": r["plane_updated_at"], "completed_at": r["completed_at"]}, r["ticket_id"], strict=True)
    done, interrupted, left = sweep_history(conn, env.base_url, env.api_key, env.workspace, rows, budget, fetch)
    note = f"🔄 Historial de asignación: {done} ticket(s) traído(s)"
    if interrupted:
        note += "; interrumpido (Plane limitó o no responde), se reanuda en la próxima ejecución"
    if left:
        note += f"; quedan {left} pendiente(s)"
    sys.stderr.write(note + "\n")
