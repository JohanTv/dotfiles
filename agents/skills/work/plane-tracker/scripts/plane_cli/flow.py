"""Flujo por work item: lead/cycle time, tiempo por estado y esfuerzo, y el reporte `report flow`.

Expone: build_ticket_flow(), flow_to_json(), print_flow(), format_lifecycle(), format_span(), cmd_report_flow().
No hace: escribir en Plane.
"""

import json
import sys
import time
import urllib.error
import urllib.parse
from datetime import datetime, timezone

import flow_metrics
import session_clock

from plane_cli.api import PlaneUnavailable, api_request
from plane_cli.resolve import get_states_map, resolve_issue, resolve_project_and_seq
from plane_cli.timeutil import format_minutes, time_to_minutes
from plane_cli.worklog import extract_metadata_from_comment


def format_lifecycle(issue):
    """'completado' con su lead time, o 'abierto desde hace …' (calendario, UTC)."""
    created = session_clock.parse_time(issue.get("created_at"))
    if not created:
        return "Ciclo     : ?"
    completed = session_clock.parse_time(issue.get("completed_at"))
    end = completed or datetime.now(timezone.utc)
    days = (end - created).total_seconds() / 86400.0
    span = f"{days:.1f} días" if days >= 1 else format_minutes(int((end - created).total_seconds() // 60))
    if completed:
        return f"Ciclo     : completado {completed.astimezone().strftime('%Y-%m-%d %H:%M')} (lead time {span})"
    return f"Ciclo     : abierto desde hace {span}"


FLOW_TTL_SECONDS = 3600
FLOW_MAX_PAGES = 20


def format_span(minutes):
    if minutes is None:
        return "—"
    return f"{minutes / 1440:.1f} d" if minutes >= 1440 else format_minutes(int(round(minutes)))


def load_states_by_id(conn, base_url, api_key, workspace, project_id):
    get_states_map(conn, base_url, api_key, workspace, project_id)
    rows = conn.execute("SELECT id, name, group_name FROM states WHERE project_id = ?", (project_id,)).fetchall()
    return {r["id"]: {"name": r["name"], "group": r["group_name"]} for r in rows}


def fetch_transitions(conn, base_url, api_key, workspace, project_id, issue, ticket_label):
    """Transiciones de estado del issue (Plane no tiene endpoint por proyecto: una llamada por ticket).

    Incremental: un ticket cuyo updated_at no cambió no se vuelve a pedir (los abiertos expiran a la hora).
    """
    now = time.time()
    cached = conn.execute("SELECT fetched_at, issue_updated_at FROM flow_fetch WHERE issue_id = ?", (issue["id"],)).fetchone()
    fresh = bool(
        cached and cached["issue_updated_at"] == issue.get("updated_at")
        and (issue.get("completed_at") or now - cached["fetched_at"] < FLOW_TTL_SECONDS)
    )
    if not fresh:
        found, cursor = [], None
        try:
            for _ in range(FLOW_MAX_PAGES):
                url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/activities/?per_page=100"
                if cursor:
                    url += f"&cursor={urllib.parse.quote(cursor)}"
                data = api_request(url, api_key, raise_on_error=True)
                for a in data.get("results", []):
                    if a.get("field") == "state" and a.get("new_identifier") and a.get("created_at"):
                        found.append((a["id"], issue["id"], ticket_label, a["created_at"], a.get("old_identifier"),
                                      a["new_identifier"], a.get("old_value"), a.get("new_value")))
                if not data.get("next_page_results"):
                    break
                cursor = data.get("next_cursor")
            with conn:
                conn.executemany("INSERT OR REPLACE INTO state_transitions VALUES (?,?,?,?,?,?,?,?)", found)
                conn.execute("INSERT OR REPLACE INTO flow_fetch VALUES (?,?,?)", (issue["id"], now, issue.get("updated_at")))
        except (urllib.error.URLError, OSError) as exc:
            sys.stderr.write(f"⚠ Sin conexión con Plane para {ticket_label} ({exc}): se usan las transiciones almacenadas.\n")
    rows = conn.execute("SELECT at_utc, from_id, to_id FROM state_transitions WHERE issue_id = ? ORDER BY at_utc", (issue["id"],)).fetchall()
    return [{"at": session_clock.parse_time(r["at_utc"]), "from_id": r["from_id"], "to_id": r["to_id"]} for r in rows]


def worklogs_from_comments(comments):
    """Worklogs de TODOS los comentarios del ticket (complementa la caché local, que puede no tenerlos)."""
    out, seen = [], set()
    for c in comments:
        if c.get("id") in seen:
            continue
        seen.add(c.get("id"))
        meta = extract_metadata_from_comment(c.get("comment_html", ""))
        if not meta:
            continue
        dur = meta.get("duration_minutes") or meta.get("duration_net_minutes")
        if not dur and meta.get("start_time") and meta.get("end_time"):
            dur = time_to_minutes(meta["end_time"]) - time_to_minutes(meta["start_time"])
            if dur < 0:
                dur += 24 * 60
        if not dur or dur < 1:
            continue
        out.append({"date": meta.get("date"), "start_time": meta.get("start_time"), "end_time": meta.get("end_time"),
                    "duration_minutes": dur, "worker_type": meta.get("worker_type", "human"), "plane_comment_id": c.get("id"),
                    "segments": meta.get("segments")})
    return out


def build_ticket_flow(conn, base_url, api_key, workspace, project_id, issue, ticket_label):
    states = load_states_by_id(conn, base_url, api_key, workspace, project_id)
    transitions = fetch_transitions(conn, base_url, api_key, workspace, project_id, issue, ticket_label)
    # Esfuerzo = worklogs locales (los registrados con --duration no viajan en el comentario) ∪ los que
    # traen metadata en los comentarios de Plane, sin duplicar por id de comentario.
    wls = [dict(r) for r in conn.execute(
        "SELECT date, start_time, end_time, duration_minutes, worker_type, plane_comment_id, raw_payload FROM worklogs WHERE ticket_id = ?", (ticket_label,))]
    for w in wls:
        try:
            w["segments"] = json.loads(w.pop("raw_payload") or "{}").get("segments")
        except ValueError:
            w["segments"] = None
    known = {w["plane_comment_id"] for w in wls if w["plane_comment_id"]}
    try:
        c_url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
        wls += [w for w in worklogs_from_comments(api_request(c_url, api_key, raise_on_error=True).get("results", []))
                if w["plane_comment_id"] not in known]
    except (urllib.error.URLError, OSError):
        sys.stderr.write(f"⚠ Sin acceso a los comentarios de {ticket_label}: esfuerzo solo de la caché local.\n")
    created = session_clock.parse_time(issue.get("created_at"))
    if not created:
        return None, transitions, states
    flow = flow_metrics.compute_flow(
        {"name": issue.get("name"), "created_at": created, "completed_at": session_clock.parse_time(issue.get("completed_at")), "state": issue.get("state")},
        transitions, states, wls, datetime.now(timezone.utc))
    return flow, transitions, states


def flow_to_json(flow):
    out = dict(flow)
    for key in ("created", "closed"):
        out[key] = out[key].isoformat() if out.get(key) else None
    return out


def print_flow(flow, transitions, states, stream=None):
    out = stream or sys.stdout
    outcome = {"completed": "completado", "cancelled": "cancelado", "open": "abierto"}[flow["outcome"]]
    out.write("\n🔁 Flujo (calendario; esfuerzo = worklogs locales + metadata en comentarios)\n")
    out.write(f"   • Resultado : {outcome}\n")
    out.write(f"   • Lead time : {format_span(flow['lead_minutes'])}{' (hasta hoy)' if flow['outcome'] == 'open' else ''}\n")
    out.write(f"   • Cycle     : {format_span(flow['cycle_active_minutes'])} activo · {format_span(flow['cycle_gross_minutes'])} bruto (Pausado excluido del activo)\n")
    out.write(f"   • Esfuerzo  : {format_span(flow['effort_clock_minutes'])} reloj · {format_span(flow['effort_compute_minutes'])} cómputo ({flow['worklogs']} worklogs)\n")
    if flow["effort_clock_over_cycle"] is not None:
        out.write(f"   • Reloj/cycle: {flow['effort_clock_over_cycle']:.2f} (señal secundaria: espera de terceros y paralelismo la distorsionan)\n")
    if flow["by_state_minutes"]:
        out.write("   • Estados   : " + " · ".join(f"{k} {format_span(v)}" for k, v in flow["by_state_minutes"].items()) + "\n")
    if flow["worklogs_before_created"] or flow["worklogs_after_closed"]:
        out.write(f"   • Fuera de ventana: {flow['worklogs_before_created']} antes de crear · {flow['worklogs_after_closed']} después de cerrar\n")
    if flow["flags"]:
        out.write("   • Flags     : " + ", ".join(flow["flags"]) + "\n")
    for t in transitions:
        a = states.get(t["from_id"], {}).get("name", "?")
        b = states.get(t["to_id"], {}).get("name", "?")
        out.write(f"   {t['at'].astimezone().strftime('%Y-%m-%d %H:%M')}  {a} → {b}\n")
    out.write("\n")


def cmd_report_flow(args, conn, base_url, api_key, workspace, default_project_id, s_str, e_str):
    """Flujo por ticket del periodo: los que tienen worklogs en caché o se cerraron en él."""
    proj = getattr(args, "project", None)
    like = f"{proj.upper()}-%" if proj else "%"
    labels = {r["ticket_id"] for r in conn.execute(
        "SELECT DISTINCT ticket_id FROM worklogs WHERE date >= ? AND date <= ? AND ticket_id LIKE ?", (s_str, e_str, like))}
    labels |= {r["ticket_id"] for r in conn.execute(
        "SELECT ticket_id FROM issues_cache WHERE completed_at IS NOT NULL AND substr(completed_at, 1, 10) >= ? "
        "AND substr(completed_at, 1, 10) <= ? AND ticket_id LIKE ?", (s_str, e_str, like))}
    rows, flows = [], []
    for label in sorted(labels):
        try:
            project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, label)
            issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
            flow, transitions, states = build_ticket_flow(conn, base_url, api_key, workspace, project_id, issue, label)
        except PlaneUnavailable as exc:
            sys.stderr.write(f"⚠ {label}: Plane no responde ({exc.cause}); se omite.\n")
            continue
        except SystemExit:
            sys.stderr.write(f"⚠ {label}: no se pudo consultar en Plane (¿eliminado?); se omite.\n")
            continue
        if flow:
            flows.append(flow)
            rows.append((label, issue.get("name", ""), flow))
    agg = flow_metrics.aggregate(flows)

    if getattr(args, "json", False):
        print(json.dumps({"period": [s_str, e_str], "tickets": [{"ticket": l, "title": n, **flow_to_json(f)} for l, n, f in rows], "summary": agg},
                         indent=2, ensure_ascii=False))
        return
    print(f"\n🔁 Flujo por ticket · {s_str} → {e_str} (calendario; lead/cycle en UTC)")
    if not rows:
        print("   (sin tickets con worklogs en caché ni cerrados en el periodo; `report --refresh` trae a la caché los worklogs de Plane)\n")
        return
    for label, title, f in rows:
        outcome = {"completed": "✔", "cancelled": "✖", "open": "…"}[f["outcome"]]
        flags = f" [{', '.join(f['flags'])}]" if f["flags"] else ""
        print(f"  {outcome} {label:<10} lead {format_span(f['lead_minutes']):<8} cycle {format_span(f['cycle_active_minutes']):<8} "
              f"esfuerzo {format_span(f['effort_clock_minutes'])} reloj / {format_span(f['effort_compute_minutes'])} cómputo{flags}")
        print(f"      {title[:70]}")
    print(f"\n   Resumen: {agg['completed']} completados · {agg['cancelled']} cancelados · {agg['open']} abiertos")
    print(f"   Mediana lead {format_span(agg['median_lead_minutes'])} (n={agg['n_lead']}) · cycle {format_span(agg['median_cycle_minutes'])} (n={agg['n_cycle']}); "
          f"{agg['excluded']} excluidos (umbrella, instant_close, no_transition)")
    print("   Nota: el esfuerzo sale de los worklogs de la caché local y de la metadata en los comentarios; lo no registrado no aparece.\n")
