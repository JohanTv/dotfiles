"""Comando `report`: reporte de actividad (día/semana) y comprobación de consistencia (`--check`).

Expone: register_report(), cmd_report(), cmd_report_check().
No hace: el reporte de flujo (vive en flow.py).
"""

import json
import sys
import time
import urllib.error
from datetime import datetime, timedelta

from plane_cli.api import api_request
from plane_cli.config import add_json_flag
from plane_cli.flow import cmd_report_flow
from plane_cli.resolve import resolve_issue, resolve_project_and_seq
from plane_cli.sync import sync_remote_worklogs
from plane_cli.timeutil import (
    DIAS_SEMANA,
    calculate_klee_union_minutes,
    expand_segments,
    format_minutes,
    render_day_block,
    time_to_minutes,
)
from plane_cli.worklog import CHECK_ERRORS, check_worklogs, extract_metadata_from_comment, find_metadata_block


SYNC_COOLDOWN = 300   # 5 minutos


def cmd_report_check(args, conn, base_url, api_key, workspace, default_project_id, s_str, e_str):
    """Solo lectura: detecta duplicados, huérfanos, diferencias y filas sin telemetría en el periodo."""
    proj = getattr(args, "project", None)
    like = f"{proj.upper()}-%" if proj else "%"
    rows = [dict(r) for r in conn.execute("SELECT * FROM worklogs WHERE date >= ? AND date <= ? AND ticket_id LIKE ? ORDER BY ticket_id, date, start_time",
                                          (s_str, e_str, like))]
    by_ticket = {}
    for r in rows:
        by_ticket.setdefault(r["ticket_id"], []).append(r)
    results, issues = {}, []
    for label, t_rows in sorted(by_ticket.items()):
        try:
            project_id, seq_id, uuid_ref, issue_ref = resolve_project_and_seq(conn, base_url, api_key, workspace, default_project_id, label)
            issue = resolve_issue(base_url, api_key, workspace, project_id, seq_id, uuid_ref)
            c_url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
            raw = api_request(c_url, api_key, raise_on_error=True).get("results", [])
        except (SystemExit, urllib.error.URLError, OSError):
            issues.append({"code": "unreachable", "ticket": label, "comment_id": None, "detail": "no se pudo consultar el ticket en Plane"})
            continue
        comments = {}
        for c in raw:
            html = c.get("comment_html") or ""
            has_block = bool(find_metadata_block(html))
            comments[c["id"]] = {"has_block": has_block, "meta": extract_metadata_from_comment(html) if has_block else None}
        found = check_worklogs(t_rows, comments, s_str, e_str)
        results[label] = (len(t_rows), found)
        issues += found
    errors = [i for i in issues if i["code"] in CHECK_ERRORS]
    if getattr(args, "json", False):
        print(json.dumps({"period": [s_str, e_str], "issues": issues, "ok": not errors}, indent=2, ensure_ascii=False))
    else:
        print(f"\n🔎 Consistencia worklogs ↔ comentarios · {s_str} → {e_str}")
        if not by_ticket:
            print("   (no hay worklogs locales en el periodo)")
        for label, (count, found) in results.items():
            print(f"   {'✔' if not [i for i in found if i['code'] in CHECK_ERRORS] else '✖'} {label}: {count} worklog(s)")
            for i in found:
                print(f"      [{i['code']}] {i['detail']}" + (f"  ({i['comment_id'][:8]})" if i["comment_id"] else ""))
        for i in issues:
            if i["code"] == "unreachable":
                print(f"   ? {i['ticket']}: {i['detail']}")
        print(f"\n   Resumen: {len(errors)} inconsistencia(s), {len(issues) - len(errors)} aviso(s). Solo lectura: corrige con comment-edit o report --sync.\n")
    sys.exit(1 if errors else 0)


def cmd_report(args, conn, base_url, api_key, workspace, default_project_id):
    today = datetime.now().date()
    is_week = getattr(args, "week", False)
    custom_date = getattr(args, "date", None)
    force_sync = getattr(args, "sync", False)

    if is_week:
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif custom_date:
        try:
            target = datetime.strptime(custom_date, "%Y-%m-%d").date()
            start_date = target
            end_date = target
        except ValueError:
            sys.stderr.write(f"Error: Formato de fecha inválido '{custom_date}'. Usa YYYY-MM-DD.\n")
            sys.exit(1)
    else:
        start_date = today
        end_date = today

    s_str = start_date.strftime("%Y-%m-%d")
    e_str = end_date.strftime("%Y-%m-%d")

    if getattr(args, "check", False):
        return cmd_report_check(args, conn, base_url, api_key, workspace, default_project_id, s_str, e_str)
    if getattr(args, "flow", False):
        return cmd_report_flow(args, conn, base_url, api_key, workspace, default_project_id, s_str, e_str)

    # Verificar si necesitamos sincronizar remotamente
    sync_meta = conn.execute("SELECT updated_at FROM sync_metadata WHERE key = ?", (f"sync:{workspace}",)).fetchone()
    last_synced = sync_meta["updated_at"] if sync_meta else 0
    now = time.time()

    # Contar registros existentes en el rango
    count_row = conn.execute("SELECT COUNT(*) as cnt FROM worklogs WHERE date >= ? AND date <= ?", (s_str, e_str)).fetchone()
    has_entries = count_row["cnt"] > 0

    needs_sync = force_sync or (not has_entries and (now - last_synced > SYNC_COOLDOWN))
    if needs_sync:
        sync_remote_worklogs(conn, base_url, api_key, workspace, s_str, e_str, filter_project=getattr(args, "project", None))

    # Construir query SQL indexada con filtros opcionales
    query = "SELECT * FROM worklogs WHERE date >= ? AND date <= ?"
    params = [s_str, e_str]

    if getattr(args, "project", None):
        query += " AND project_id = ?"
        params.append(args.project.upper())

    if getattr(args, "track", None):
        query += " AND track = ?"
        params.append(args.track)

    if getattr(args, "worker_type", None):
        query += " AND worker_type = ?"
        params.append(args.worker_type)

    query += " ORDER BY date ASC, start_time ASC"
    rows = conn.execute(query, params).fetchall()

    if getattr(args, "json", False):
        result = [dict(r) for r in rows]
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # Renderizado en texto
    if is_week:
        num_semana = start_date.isocalendar()[1]
        print("=" * 80)
        print(f"📅 REPORTE SEMANAL - SEMANA {num_semana} ({start_date.strftime('%d/%m/%Y')} al {end_date.strftime('%d/%m/%Y')})")
        print("=" * 80 + "\n")

        all_week_intervals = []
        total_week_compute = 0
        week_by_project = {}
        all_week_stoppers = []

        cur = start_date
        limit_day = min(end_date, today)
        while cur <= limit_day:
            cur_s = cur.strftime("%Y-%m-%d")
            day_rows = [r for r in rows if r["date"] == cur_s]
            dia_nombre = DIAS_SEMANA[cur.weekday()]
            print(f"[{dia_nombre} {cur.strftime('%d/%m/%Y')}]")
            print(render_day_block(cur, day_rows))
            print("")

            for r in expand_segments(day_rows):
                s_m = time_to_minutes(r["start_time"])
                e_m = time_to_minutes(r["end_time"])
                dur = r["duration_minutes"]
                all_week_intervals.append((s_m, e_m))
                total_week_compute += dur
                pref = r["ticket_id"].split("-")[0] if "-" in r["ticket_id"] else "Otros"
                week_by_project[pref] = week_by_project.get(pref, 0) + dur
                try:
                    for st in json.loads(r["stoppers_json"]):
                        if st and st not in all_week_stoppers:
                            all_week_stoppers.append(st)
                except Exception:
                    pass

            cur += timedelta(days=1)

        week_wall_clock = calculate_klee_union_minutes(all_week_intervals)
        proj_parts = [f"{k}: {format_minutes(v)}" for k, v in week_by_project.items()]
        proj_str = " | ".join(proj_parts) if proj_parts else "N/A"

        print("=" * 80)
        print(f"🏆 TOTAL SEMANA: {format_minutes(week_wall_clock)} reloj activa ({proj_str})")
        if total_week_compute > week_wall_clock:
            leverage = round(total_week_compute / week_wall_clock, 2) if week_wall_clock > 0 else 1.0
            print(f"🚀 AI Leverage Multiplier: {leverage}x ({format_minutes(total_week_compute)} de esfuerzo total entregado)")
        if all_week_stoppers:
            print(f"⏸️ STANDBY TOTAL: {', '.join(all_week_stoppers)}")
        print("=" * 80 + "\n")

    else:
        target = start_date
        dia_nombre = DIAS_SEMANA[target.weekday()]
        print("=" * 80)
        print(f"📋 REPORTE DE ACTIVIDAD - {dia_nombre.upper()} {target.strftime('%d/%m/%Y')}")
        print("=" * 80 + "\n")
        print(render_day_block(target, rows))
        print("\n" + "=" * 80)


def register_report(sub):
    p_report = sub.add_parser("report", help="Generar reporte de actividades en formato híbrido con Interval Merging")
    group_date = p_report.add_mutually_exclusive_group()
    group_date.add_argument("--today", action="store_true", help="Reporte del día actual (por defecto)")
    group_date.add_argument("--week", action="store_true", help="Reporte de la semana actual")
    group_date.add_argument("--date", help="Reporte de fecha específica (YYYY-MM-DD)")
    p_report.add_argument("-p", "--project", help="Filtrar por proyecto (ej: OMNIFY, OPS)")
    p_report.add_argument("--track", help="Filtrar por track (ej: main, subagent)")
    p_report.add_argument("--worker-type", help="Filtrar por tipo de trabajador (human, subagent)")
    p_report.add_argument("--sync", action="store_true", help="Forzar sincronización remota con Plane")
    p_report.add_argument("--check", action="store_true", help="Solo lectura: compara los worklogs locales con sus comentarios en Plane (duplicados, huérfanos, diferencias)")
    p_report.add_argument("--flow", action="store_true", help="Flujo por ticket del periodo: lead/cycle time, tiempo por estado y esfuerzo")
    add_json_flag(p_report, help="Salida en formato JSON")
    p_report.set_defaults(handler=cmd_report)
