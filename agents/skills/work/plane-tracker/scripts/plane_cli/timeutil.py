"""Aritmética de horarios y fusión de intervalos (medida de Klee) para los reportes de actividad.

Expone: time_to_minutes(), minutes_to_time(), calculate_klee_union_minutes(), expand_segments(),
merge_daily_worklogs(), format_minutes(), render_day_block(), DIAS_SEMANA.
No hace: red ni acceso a la base de datos.
"""

import json


DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def time_to_minutes(t_str):
    try:
        h, m = map(int, t_str.split(":"))
        return h * 60 + m
    except Exception:
        return 0


def minutes_to_time(m):
    h = (m // 60) % 24
    mins = m % 60
    return f"{h:02d}:{mins:02d}"


def calculate_klee_union_minutes(intervals):
    """Calcula la longitud de la unión de intervalos sin duplicar solapamientos (Medida de Lebesgue en 1D)."""
    if not intervals:
        return 0
    sorted_int = sorted(intervals, key=lambda x: x[0])
    union_mins = 0
    cur_start, cur_end = sorted_int[0]

    for s, e in sorted_int[1:]:
        if s <= cur_end:
            cur_end = max(cur_end, e)
        else:
            union_mins += (cur_end - cur_start)
            cur_start, cur_end = s, e
    union_mins += (cur_end - cur_start)
    return union_mins


def expand_segments(rows):
    """Un worklog con segmentos (actividad intercalada entre tickets) se reporta como un bloque por segmento."""
    out = []
    for row in rows:
        entry = dict(row)
        try:
            segments = json.loads(entry.get("raw_payload") or "{}").get("segments")
        except ValueError:
            segments = None
        if not segments:
            out.append(entry)
            continue
        for idx, seg in enumerate(segments):
            part = dict(entry, start_time=seg["start"], end_time=seg["end"], duration_minutes=seg["minutes"])
            if idx:
                part["notes"] = "(continuación)"
            out.append(part)
    return out


def merge_daily_worklogs(rows):
    """
    Agrupa y fusiona registros para el formato ejecutivo:
    titulo / inicio / fin / notas
    
    1. Registros del mismo ticket con solapamiento temporal se unifican en un único bloque continuo.
    2. Registros de distintos tickets preservan su horario real.
    3. El total día se calcula mediante la unión de Lebesgue (Klee's Measure) para tiempo reloj real.
    """
    if not rows:
        return [], 0, 0

    tickets_map = {}
    for r in rows:
        tid = r["ticket_id"]
        tickets_map.setdefault(tid, []).append(r)

    consolidated = []
    all_raw_intervals = []
    total_compute_minutes = 0

    for tid, t_entries in tickets_map.items():
        sorted_t = sorted(t_entries, key=lambda x: time_to_minutes(x["start_time"]))
        merged_blocks = []

        for e in sorted_t:
            s_m = time_to_minutes(e["start_time"])
            e_m = time_to_minutes(e["end_time"])
            dur = e["duration_minutes"]
            total_compute_minutes += dur
            all_raw_intervals.append((s_m, e_m))

            track_name = e["track"]
            worker = e["worker_type"]
            actor_tag = " [Subagente]" if "subagent" in worker.lower() else ""
            track_tag = f"Track: {track_name}" if track_name != "main" else "General"
            note_content = f"[{track_tag}{actor_tag} ({e['start_time']}-{e['end_time']})]: {e['notes']}"

            try:
                stoppers_list = json.loads(e["stoppers_json"])
            except Exception:
                stoppers_list = []

            if not merged_blocks:
                merged_blocks.append({
                    "ticket_id": tid,
                    "issue_name": e["issue_name"],
                    "start_min": s_m,
                    "end_min": e_m,
                    "active_mins": dur,
                    "notes_list": [note_content],
                    "stoppers": stoppers_list,
                    "workers": {worker}
                })
            else:
                last = merged_blocks[-1]
                # Solapamiento o contigüidad (<= 5 min)
                if s_m <= last["end_min"] + 5:
                    last["end_min"] = max(last["end_min"], e_m)
                    last["active_mins"] += dur
                    last["notes_list"].append(note_content)
                    last["stoppers"].extend(stoppers_list)
                    last["workers"].add(worker)
                else:
                    merged_blocks.append({
                        "ticket_id": tid,
                        "issue_name": e["issue_name"],
                        "start_min": s_m,
                        "end_min": e_m,
                        "active_mins": dur,
                        "notes_list": [note_content],
                        "stoppers": stoppers_list,
                        "workers": {worker}
                    })

        for b in merged_blocks:
            wall_m = b["end_min"] - b["start_min"]
            leverage = round(b["active_mins"] / wall_m, 2) if wall_m > 0 else 1.0
            combined_notes = " | ".join(b["notes_list"])
            if len(b["notes_list"]) > 1 or leverage > 1.0:
                combined_notes += f" (Consolidado: {b['active_mins']}m esfuerzo en {wall_m}m reloj | AI Leverage: {leverage}x)"

            consolidated.append({
                "ticket_id": b["ticket_id"],
                "issue_name": b["issue_name"],
                "start_time": minutes_to_time(b["start_min"]),
                "end_time": minutes_to_time(b["end_min"]),
                "start_min": b["start_min"],
                "wall_minutes": wall_m,
                "active_minutes": b["active_mins"],
                "notes": combined_notes,
                "stoppers": list(set(b["stoppers"])),
                "workers": list(b["workers"])
            })

    consolidated.sort(key=lambda x: x["start_min"])
    day_wall_clock_minutes = calculate_klee_union_minutes(all_raw_intervals)

    return consolidated, day_wall_clock_minutes, total_compute_minutes


def format_minutes(m):
    h = m // 60
    mins = m % 60
    return f"{h}h {mins:02d}m"


def render_day_block(date_obj, rows):
    """Renderiza el bloque de un día usando Interval Merging de Klee."""
    dia_nombre = DIAS_SEMANA[date_obj.weekday()]
    d_str = date_obj.strftime("%d/%m/%Y")
    lines = []

    if not rows:
        return f"ℹ Sin registros de actividad para {dia_nombre} {d_str}.\n"

    merged_entries, wall_clock_mins, total_compute_mins = merge_daily_worklogs(expand_segments(rows))

    by_project = {}
    all_stoppers = []

    for e in merged_entries:
        lines.append(f"titulo: [{e['ticket_id']}] {e['issue_name']}")
        lines.append(f"inicio: {e['start_time']}")
        lines.append(f"fin: {e['end_time']}")
        lines.append(f"notas: {e['notes']}")
        lines.append("")

        pref = e["ticket_id"].split("-")[0] if "-" in e["ticket_id"] else "Otros"
        by_project[pref] = by_project.get(pref, 0) + e["wall_minutes"]
        for st in e["stoppers"]:
            if st and st not in all_stoppers:
                all_stoppers.append(st)

    proj_parts = [f"{k}: {format_minutes(v)}" for k, v in by_project.items()]
    proj_str = " | ".join(proj_parts) if proj_parts else "N/A"

    lines.append("-" * 80)
    lines.append(f"📊 Total día: {format_minutes(wall_clock_mins)} reloj activa ({proj_str})")
    
    if total_compute_mins > wall_clock_mins:
        leverage = round(total_compute_mins / wall_clock_mins, 2) if wall_clock_mins > 0 else 1.0
        lines.append(f"🚀 AI Leverage Multiplier: {leverage}x ({format_minutes(total_compute_mins)} de esfuerzo entregado en {format_minutes(wall_clock_mins)} reloj)")

    if all_stoppers:
        lines.append(f"⏸️ Standby externo: {', '.join(all_stoppers)}")
    else:
        lines.append("⏸️ Standby externo: 0h 00m (Sin bloqueos reportados)")

    return "\n".join(lines)
