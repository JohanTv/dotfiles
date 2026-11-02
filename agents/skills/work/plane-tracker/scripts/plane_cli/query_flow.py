"""Consulta de la vista `report flow`: lead/cycle time y esfuerzo por ticket del periodo, calculados SOLO con lo almacenado (por eso funciona con `--offline`).

Expone: query().
No hace: red ni escribir. Lee tickets (issues_cache), estados, transiciones (state_transitions) y las horas locales; los comentarios no se usan. La cobertura cuenta los tickets con las
transiciones al día (`detail.history`): faltar alguno la deja incompleta. Un ticket que la caché no conoce se cuenta como sin verificar y no genera fila.
"""

from dataclasses import replace

import flow_metrics
import session_clock

from plane_cli import clock, store_transitions
from plane_cli.coverage import Result, complete_flow, settle
from plane_cli.flow import flow_to_json
from plane_cli.outbox import count_open


def _flow(conn, row):
    states = store_transitions.states_of(conn, row["project_id"])
    current = next((sid for sid, s in states.items() if s["name"] == row["state_name"]), None)
    created = session_clock.parse_time(row["created_at"])
    if not created:
        return None
    issue = {"name": row["title"], "created_at": created, "completed_at": session_clock.parse_time(row["completed_at"]), "state": current}
    return flow_metrics.compute_flow(issue, store_transitions.transitions_of(conn, row["id"]), states, store_transitions.worklogs_of(conn, row["ticket_id"]), clock.now())


def query(conn, scope, acq):
    idents, period = [p.ident for p in scope.projects], scope.period
    labels = store_transitions.flow_tickets(conn, idents, period["from"], period["to"], period["tz"])
    known = store_transitions.issue_rows(conn, labels)
    rows, flows = [], []
    for label in labels:
        flow = _flow(conn, known[label]) if label in known else None
        if flow:
            flows.append(flow)
            rows.append({"ticket": label, "title": known[label]["title"], **flow_to_json(flow)})
    verified, total = store_transitions.history_coverage(conn, labels)
    cov = replace(acq, detail=dict(acq.detail, history={"verified": verified, "total": total}))  # 0 de 0 también es una comprobación: no hay nada que traer
    pending = count_open(conn, period["from"], period["to"], idents[0] if len(idents) == 1 else None, None)
    extra = ({"code": "pending_unpublished", "text": f"{pending} registro(s) de este periodo siguen sin publicarse."},) if pending else ()
    cov = settle(replace(cov, complete=complete_flow(cov)), extra)
    return Result(rows=rows, total=len(rows), coverage=cov, summary=flow_metrics.aggregate(flows), extra_notes=extra)
