"""Texto de la vista `report time`: un render del sobre `plane-tracker/1`, nunca de la base de datos.

Expone: render().
No hace: consultar ni leer el reloj. "Hoy" es la fecha de `as_of + age_s` de la cobertura (o el fin del periodo si nunca se sincronizó): una semana en curso solo muestra hasta hoy.
El periodo de un solo día sale como el bloque del día; uno más largo, como el reporte semanal con el total reconstruido desde el resumen. Las notas van al final.
"""

import json
from datetime import date, datetime, timedelta

from plane_cli import vocabulary
from plane_cli.timeutil import DIAS_SEMANA, calculate_klee_union_minutes, expand_segments, format_minutes, render_day_block, time_to_minutes


def _legacy(row):
    """Fila del contrato -> la que espera el bloque del día (merge de intervalos, notas, standby)."""
    return {"ticket_id": row["ticket"], "issue_name": row.get("title") or "", "date": row["date"], "start_time": row["start_time"], "end_time": row["end_time"],
            "duration_minutes": row["minutes"], "track": row.get("track") or "main", "worker_type": row.get("worker_type") or "human", "notes": row.get("notes") or "",
            "stoppers_json": json.dumps(row.get("stoppers") or []), "raw_payload": json.dumps({"segments": row.get("segments")})}


def _today(cov, last):
    if not cov.get("as_of"):
        return last
    return (datetime.fromisoformat(cov["as_of"].replace("Z", "+00:00")) + timedelta(seconds=cov.get("age_s") or 0)).date()


def _notes(doc):
    return [f"  {'⚠' if vocabulary.NOTES.get(n['code'], ('warn',))[0] == 'warn' else 'ℹ'} {n['text']}" + (f" → {n['hint']}" if n.get("hint") else "") for n in doc["notes"]]


def _week(doc, rows, first, last):
    is_iso_week = first.weekday() == 0 and (last - first).days == 6
    title = f"📅 REPORTE SEMANAL - SEMANA {first.isocalendar()[1]} ({first.strftime('%d/%m/%Y')} al {last.strftime('%d/%m/%Y')})" if is_iso_week \
        else f"📅 REPORTE DE ACTIVIDAD ({first.strftime('%d/%m/%Y')} al {last.strftime('%d/%m/%Y')})"
    lines, stoppers = ["=" * 80, title, "=" * 80 + "\n"], []
    day, shown_until = first, min(last, _today(doc["coverage"], last))
    by_project = {}
    while day <= shown_until:
        day_rows = [r for r in rows if r["date"] == day.isoformat()]
        lines += [f"[{DIAS_SEMANA[day.weekday()]} {day.strftime('%d/%m/%Y')}]", render_day_block(day, day_rows), ""]
        for r in expand_segments(day_rows):
            pref = r["ticket_id"].split("-")[0] if "-" in r["ticket_id"] else "Otros"
            by_project[pref] = by_project.get(pref, 0) + r["duration_minutes"]
            stoppers += [s for s in json.loads(r["stoppers_json"]) if s and s not in stoppers]
        day += timedelta(days=1)
    summary = doc["summary"]
    clock_minutes, compute = summary["effort_clock_minutes"], summary["effort_compute_minutes"]
    projects = " | ".join(f"{k}: {format_minutes(v)}" for k, v in by_project.items()) or "N/A"
    lines += ["=" * 80, f"🏆 TOTAL SEMANA: {format_minutes(clock_minutes)} reloj activa ({projects})"]
    if compute > clock_minutes:
        lines.append(f"🚀 AI Leverage Multiplier: {round(compute / clock_minutes, 2) if clock_minutes > 0 else 1.0}x ({format_minutes(compute)} de esfuerzo total entregado)")

    by_cap = summary.get("by_capacity") or []
    if by_cap:
        lines.append("\n🎯 DISTRIBUCIÓN POR CAPACIDAD:")
        total_cap = sum(c["minutes"] for c in by_cap)
        var_by_bucket = {v["bucket"]: v for v in summary.get("capacity_variance") or []}
        for c in by_cap:
            b_name = c["key"]
            b_mins = c["minutes"]
            pct = (b_mins / total_cap * 100.0) if total_cap > 0 else 0.0
            plan_info = ""
            if b_name == "undeclared":
                if b_name in var_by_bucket:
                    v = var_by_bucket[b_name]
                    diff = v["variance_percent"]
                    diff_str = f"+{diff:.1f}%" if diff >= 0 else f"{diff:.1f}%"
                    plan_info = f" ⚠️ sin declarar [meta {v['target_percent']:.1f}% · {diff_str}]"
                else:
                    plan_info = " ⚠️ sin declarar"
            elif b_name in var_by_bucket:
                v = var_by_bucket[b_name]
                diff = v["variance_percent"]
                diff_str = f"+{diff:.1f}%" if diff >= 0 else f"{diff:.1f}%"
                plan_info = f" [meta {v['target_percent']:.1f}% · {diff_str}]"
            lines.append(f"  • {b_name:<18} {format_minutes(b_mins):>7} ({pct:5.1f}%){plan_info}")

    if is_iso_week:
        untracked = max(0, 2400 - clock_minutes)
        if untracked > 0:
            lines.append(f"\nℹ Tiempo no contabilizado: {format_minutes(untracked)} (base semana laboral 40h)")

    if stoppers:
        lines.append(f"⏸️ STANDBY TOTAL: {', '.join(stoppers)}")
    lines.append("=" * 80 + "\n")
    return lines


def _md_cell(text, max_len=None):
    if text is None:
        return ""
    s = str(text).replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()
    if max_len is not None and len(s) > max_len:
        s = s[:max_len].rstrip()
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace("\\", "\\\\").replace("|", "\\|")
    if s.count("`") % 2 != 0:
        s = s.replace("`", "'")
    return s


def _md_code(text):
    if text is None:
        return "—"
    s = str(text).replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()
    s = s.replace("<", "&lt;").replace(">", "&gt;").replace("\\", "\\\\").replace("|", "\\|").replace("`", "'")
    return f"`{s}`"


def _render_time_markdown(doc):
    period = doc["scope"]["period"]
    first, last = date.fromisoformat(period["from"]), date.fromisoformat(period["to"])
    rows = [_legacy(r) for r in doc["results"]]
    summary = doc.get("summary") or {}
    clock_minutes = summary.get("effort_clock_minutes", 0)
    compute = summary.get("effort_compute_minutes", 0)
    is_iso_week = first.weekday() == 0 and (last - first).days == 6

    lines = []
    if first == last:
        lines.append(f"# 📋 Reporte de Actividad — {DIAS_SEMANA[first.weekday()]} {first.strftime('%d/%m/%Y')}\n")
    elif is_iso_week:
        lines.append(f"# 📅 Reporte Semanal — Semana {first.isocalendar()[1]} ({first.strftime('%d/%m/%Y')} al {last.strftime('%d/%m/%Y')})\n")
    else:
        lines.append(f"# 📅 Reporte de Actividad ({first.strftime('%d/%m/%Y')} al {last.strftime('%d/%m/%Y')})\n")

    lines.append("### 📊 Resumen Ejecutivo\n")
    lines.append(f"- **Tiempo Reloj Activo:** `{format_minutes(clock_minutes)}`")
    lines.append(f"- **Esfuerzo Entregado (Cómputo):** `{format_minutes(compute)}`")
    if compute > clock_minutes:
        mult = round(compute / clock_minutes, 2) if clock_minutes > 0 else 1.0
        lines.append(f"- **🚀 AI Leverage Multiplier:** `{mult}x`")
    if is_iso_week:
        untracked = max(0, 2400 - clock_minutes)
        if untracked > 0:
            lines.append(f"- **Tiempo no contabilizado (base 40h):** `{format_minutes(untracked)}`")
    lines.append("")

    by_cap = summary.get("by_capacity") or []
    if by_cap:
        lines.append("### 🎯 Distribución por Capacidad\n")
        lines.append("| Balde / Capacidad | Tiempo Reloj | % Real | Meta | Varianza |")
        lines.append("| :--- | :---: | :---: | :---: | :---: |")
        total_cap = sum(c["minutes"] for c in by_cap)
        var_by_bucket = {v["bucket"]: v for v in summary.get("capacity_variance") or []}
        for c in by_cap:
            b_name = c["key"]
            b_mins = c["minutes"]
            pct = (b_mins / total_cap * 100.0) if total_cap > 0 else 0.0
            meta_str = "—"
            diff_str = "—"
            if b_name in var_by_bucket:
                v = var_by_bucket[b_name]
                meta_str = f"{v['target_percent']:.1f}%"
                diff = v["variance_percent"]
                diff_str = f"+{diff:.1f}%" if diff >= 0 else f"{diff:.1f}%"
            elif b_name == "undeclared":
                meta_str = "0.0%"
                diff_str = "⚠️ sin declarar"
            lines.append(f"| {_md_code(b_name)} | {format_minutes(b_mins)} | {pct:5.1f}% | {meta_str} | {diff_str} |")
        lines.append("")

    day, shown_until = first, min(last, _today(doc["coverage"], last))
    by_project = {}
    stoppers = []

    if first == last:
        day_rows = [r for r in rows if r["date"] == first.isoformat()]
        lines.append("### 📝 Actividades Realizadas\n")
        if not day_rows:
            lines.append("*(Sin actividades registradas)*\n")
        else:
            lines.append("| Ticket | Título | Horario | Duración | Balde | Notas |")
            lines.append("| :--- | :--- | :---: | :---: | :--- | :--- |")
            for r in expand_segments(day_rows):
                pref = r["ticket_id"].split("-")[0] if "-" in r["ticket_id"] else "Otros"
                by_project[pref] = by_project.get(pref, 0) + r["duration_minutes"]
                stoppers += [s for s in json.loads(r["stoppers_json"]) if s and s not in stoppers]
                horario = f"{r['start_time']} - {r['end_time']}" if r.get("start_time") and r.get("end_time") else "—"
                dur = format_minutes(r["duration_minutes"])
                raw_payload = json.loads(r.get("raw_payload") or "{}")
                b_name = raw_payload.get("capacity") or r.get("track") or "—"
                t_title = _md_cell(r.get("issue_name") or "", 45)
                notes = _md_cell(r.get("notes") or "", 40)
                lines.append(f"| {_md_code(r['ticket_id'])} | {t_title} | {horario} | {dur} | {_md_code(b_name)} | {notes} |")
            lines.append("")
    else:
        lines.append("### 📅 Desglose Diario de Actividades\n")
        has_days = False
        while day <= shown_until:
            day_rows = [r for r in rows if r["date"] == day.isoformat()]
            if day_rows:
                has_days = True
                intervals = [(time_to_minutes(r["start_time"]), time_to_minutes(r["end_time"])) for r in day_rows if r.get("start_time") and r.get("end_time")]
                day_clock = calculate_klee_union_minutes(intervals) if intervals else sum(r["duration_minutes"] for r in day_rows)
                lines.append(f"#### {DIAS_SEMANA[day.weekday()]} {day.strftime('%d/%m/%Y')} ({format_minutes(day_clock)})\n")
                lines.append("| Ticket | Título | Horario | Duración | Balde |")
                lines.append("| :--- | :--- | :---: | :---: | :--- |")
                for r in expand_segments(day_rows):
                    pref = r["ticket_id"].split("-")[0] if "-" in r["ticket_id"] else "Otros"
                    by_project[pref] = by_project.get(pref, 0) + r["duration_minutes"]
                    stoppers += [s for s in json.loads(r["stoppers_json"]) if s and s not in stoppers]
                    horario = f"{r['start_time']} - {r['end_time']}" if r.get("start_time") and r.get("end_time") else "—"
                    dur = format_minutes(r["duration_minutes"])
                    raw_payload = json.loads(r.get("raw_payload") or "{}")
                    b_name = raw_payload.get("capacity") or r.get("track") or "—"
                    t_title = _md_cell(r.get("issue_name") or "", 50)
                    lines.append(f"| {_md_code(r['ticket_id'])} | {t_title} | {horario} | {dur} | {_md_code(b_name)} |")
                lines.append("")
            day += timedelta(days=1)
        if not has_days:
            lines.append("*(Sin actividades registradas en el periodo)*\n")

    if by_project:
        lines.append("### 📁 Distribución por Proyecto\n")
        lines.append("| Proyecto | Tiempo Reloj |")
        lines.append("| :--- | :---: |")
        for k, v in by_project.items():
            lines.append(f"| {_md_code(k)} | {format_minutes(v)} |")
        lines.append("")

    if stoppers:
        lines.append(f"> ⏸️ **Standby reportado:** {', '.join(_md_cell(s) for s in stoppers)}\n")

    notes_list = _notes(doc)
    if notes_list:
        lines.append("### ℹ️ Observaciones\n")
        for n in notes_list:
            lines.append(f"> {n.strip()}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render(doc, markdown=False):
    if markdown:
        return _render_time_markdown(doc)
    period = doc["scope"]["period"]
    first, last = date.fromisoformat(period["from"]), date.fromisoformat(period["to"])
    rows = [_legacy(r) for r in doc["results"]]
    if first == last:
        lines = ["=" * 80, f"📋 REPORTE DE ACTIVIDAD - {DIAS_SEMANA[first.weekday()].upper()} {first.strftime('%d/%m/%Y')}", "=" * 80 + "\n", render_day_block(first, rows), "\n" + "=" * 80]
    else:
        lines = _week(doc, rows, first, last)
    return "\n".join(lines + _notes(doc)) + "\n"
