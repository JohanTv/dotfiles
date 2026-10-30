"""Medición de la sesión del agente y construcción de propuestas de duración (también repartidas entre tickets).

Expone: build_proposal(), build_split(), print_proposal(), print_split(), focus_intervals(), current_session_id(),
reserved_runs(), session_coverage().
No hace: registrar worklogs ni llamar a Plane.
"""

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

import session_clock

from plane_cli import config
from plane_cli.proposal_store import proposal_store


# Reuniones y soporte no dejan huella en un transcript: ahí siempre se pregunta.
NO_PROPOSAL_BUCKETS = ("toil_support", "coordination")
MAX_PROPOSAL_WARN_MINUTES = 8 * 60
FOCUS_KEEP_DAYS = 3


def _hhmm_utc(day, hhmm):
    return datetime.strptime(f"{day} {hhmm}", "%Y-%m-%d %H:%M").astimezone(timezone.utc)


def current_session_id(args, worker_type):
    """Id de la sesión de ESTA terminal (env var, --session o directorio sin ambigüedad), o None."""
    agent = getattr(args, "agent", None) or session_clock.agent_from_worker_type(worker_type) or session_clock.detect_agent()
    if not agent:
        return None
    return session_clock.resolve_session(agent, os.getcwd(), getattr(args, "session", None))[0]


def _proposal_runs(proposal):
    return [(session_clock.parse_time(seg["start_utc"]), session_clock.parse_time(seg["end_utc"])) for seg in proposal.get("segments", [])]


def reserved_runs(session_id, exclude_tickets):
    """Intervalos de propuestas pendientes de ESTA sesión para otros tickets (se reservan hasta aceptarse o caducar)."""
    out = []
    with proposal_store() as data:
        pending = [(e["ticket"], e["proposal"]) for e in data["proposals"].values()]
        for group in data["groups"].values():
            pending += list(group["parts"].items())
    for ticket, proposal in pending:
        if ticket not in exclude_tickets and proposal.get("session_id") == session_id:
            out += _proposal_runs(proposal)
    return out


def session_coverage(conn, session_id, today):
    """Intervalos de hoy ya registrados como worklog de esta sesión (propuestos o declarados)."""
    out = []
    rows = conn.execute("SELECT start_time, end_time, raw_payload FROM worklogs WHERE date = ? AND raw_payload LIKE ?", (today, f"%{session_id}%")).fetchall()
    for row in rows:
        try:
            meta = json.loads(row["raw_payload"])
        except ValueError:
            continue
        if (meta.get("measured_by") or {}).get("session") != session_id:
            continue
        try:
            if meta.get("segments"):
                for seg in meta["segments"]:
                    start = session_clock.parse_time(seg.get("start_utc")) or _hhmm_utc(today, seg["start"])
                    end = session_clock.parse_time(seg.get("end_utc")) or _hhmm_utc(today, seg["end"])
                    out.append((start, end))
            else:
                out.append((_hhmm_utc(today, row["start_time"]), _hhmm_utc(today, row["end_time"])))
        except (KeyError, ValueError):
            continue
    return out


def focus_intervals(conn, session_id, day_start, now):
    """{ticket: [(inicio, fin)]} de las marcas de foco de la sesión recortadas a [day_start, now]."""
    out = {}
    rows = conn.execute("SELECT ticket, started_at, ended_at FROM session_marks WHERE session_id = ? ORDER BY started_at", (session_id,)).fetchall()
    for row in rows:
        start = max(session_clock.parse_time(row["started_at"]), day_start)
        end = min(session_clock.parse_time(row["ended_at"]) if row["ended_at"] else now, now)
        if end > start:
            out.setdefault(row["ticket"], []).append((start, end))
    return out


def _parse_clock(text, day_start):
    """'HH:MM' (hora local del día pedido) o ISO-8601 -> datetime UTC."""
    text = text.strip()
    if re.match(r"^\d{1,2}:\d{2}$", text):
        hour, minute = (int(x) for x in text.split(":"))
        return day_start.astimezone().replace(hour=hour, minute=minute, second=0, microsecond=0).astimezone(timezone.utc)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"Hora inválida '{text}': usa HH:MM o ISO-8601.")
    return (parsed.astimezone() if parsed.tzinfo is None else parsed).astimezone(timezone.utc)


def _resolve_window(args, now):
    """Día medido (hoy o --date) y ventana dentro de él: el día completo (hasta ahora si es hoy) o --since/--until."""
    date_arg = getattr(args, "date", None)
    if date_arg:
        try:
            day = datetime.strptime(date_arg, "%Y-%m-%d")
        except ValueError:
            raise ValueError("--date debe tener el formato YYYY-MM-DD.")
        day_start = day.astimezone(timezone.utc)
        day_str = date_arg
    else:
        day_start = config.local_midnight_utc(now)
        day_str = now.astimezone().strftime("%Y-%m-%d")
    if day_start > now:
        raise ValueError("--date no puede ser una fecha futura.")
    day_end = min((day_start.astimezone() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc), now)
    start, end, notes, override = day_start, day_end, [], None
    since, until = getattr(args, "since", None), getattr(args, "until", None)
    if since or until:
        if since:
            start = _parse_clock(since, day_start)
        if until:
            end = _parse_clock(until, day_start)
        if end > day_end:
            end = day_end
            notes.append("--until quedaba fuera del día o en el futuro: se recorta.")
        if start < day_start or end < day_start:
            raise ValueError("La ventana debe estar dentro de un único día (cruzaría la medianoche): registra cada día por separado.")
        if start >= end:
            raise ValueError("--since debe ser anterior a --until.")
        override = {"since": start.isoformat(), "until": end.isoformat()}
    return {"day": day_str, "day_start": day_start, "day_end": day_end, "start": start, "end": end, "notes": notes, "override": override}


def _runs_to_segments(runs, minutes):
    """Segmentos para guardar en el worklog: minutos enteros que suman exactamente `minutes`."""
    weights = [max((e - s).total_seconds(), 1.0) for s, e in runs]
    shares = session_clock.largest_remainder(minutes, weights)
    segs = []
    for (start, end), share in zip(runs, shares):
        if share < 1:
            continue
        segs.append({"start": start.astimezone().strftime("%H:%M"), "end": end.astimezone().strftime("%H:%M"), "minutes": share,
                     "start_utc": start.isoformat(), "end_utc": end.isoformat()})
    return segs


def _proposal_from_runs(ctx, runs, extras):
    minutes = int(round(session_clock.total_minutes(runs)))
    segs = _runs_to_segments(runs, minutes)
    first, last = runs[0][0].astimezone(), runs[-1][1].astimezone()
    gross = (runs[-1][1] - runs[0][0]).total_seconds() / 60.0
    warnings = list(extras.get("notes", []))
    if minutes > MAX_PROPOSAL_WARN_MINUTES:
        warnings.append(f"La propuesta supera {MAX_PROPOSAL_WARN_MINUTES // 60} h: revisa si la sesión cubre varios tickets.")
    if len(runs) > 1:
        warnings.append(f"Hay {len(runs) - 1} pausa(s) de más de 10 min descontadas (pueden ser lectura humana, no inactividad).")
    if ctx["agent"] == "agy":
        warnings.append("agy solo expone hitos de la conversación: la medición es aproximada.")
    if extras.get("excluded", 0) >= 1:
        warnings.append(f"Se excluyeron {extras['excluded']:.0f} min ya registrados o reservados para esta sesión.")
    if extras.get("unattributed", 0) >= 1:
        warnings.append(f"{extras['unattributed']:.0f} min de la sesión no tienen foco asignado (no se reparten solos).")
    return {
        "ok": True, "agent": ctx["agent"], "session_id": ctx["session_id"], "origin": ctx["origin"],
        "confidence": session_clock.CONFIDENCE[ctx["agent"]], "attribution": extras["attribution"],
        "minutes": minutes, "net_minutes": round(session_clock.total_minutes(runs), 1), "gross_minutes": round(gross, 1),
        "pauses": max(len(runs) - 1, 0), "events": ctx["events"],
        "date": first.strftime("%Y-%m-%d"), "start_time": first.strftime("%H:%M"), "end_time": last.strftime("%H:%M"),
        "segments": segs, "window": extras["window"], "window_override": extras.get("override"),
        "excluded_minutes": round(extras.get("excluded", 0), 1), "unattributed_minutes": round(extras.get("unattributed", 0), 1),
        "warnings": warnings,
    }


def _measure(conn, args, worker_type, exclude_tickets, ticket, use_focus):
    """Tramos de actividad medibles (ya restados los registrados/reservados). Devuelve (ctx, runs, extras) o un dict de error."""
    agent = getattr(args, "agent", None) or session_clock.agent_from_worker_type(worker_type) or session_clock.detect_agent()
    if not agent:
        return {"ok": False, "reason": "No se pudo determinar el agente (usa --agent claude|opencode|agy o --worker-type agent:<x>)."}
    session_id, origin, cands = session_clock.resolve_session(agent, os.getcwd(), getattr(args, "session", None))
    if not session_id:
        listed = [{"id": sid, "last_activity": ts.astimezone().strftime("%Y-%m-%d %H:%M")} for sid, ts in cands]
        return {"ok": False, "agent": agent, "candidates": listed,
                "reason": f"No se pudo determinar la sesión de {agent}: {origin}. Indica --session <id>."}
    stamps = session_clock.timestamps(agent, session_id)
    if not stamps:
        return {"ok": False, "agent": agent, "session_id": session_id, "reason": f"Sin evidencia de tiempos para la sesión {session_id} ({agent})."}

    now = config.now()
    try:
        win = _resolve_window(args, now)
    except ValueError as exc:
        return {"ok": False, "agent": agent, "session_id": session_id, "reason": str(exc)}
    w_start, w_end, notes, override = win["start"], win["end"], win["notes"], win["override"]
    inside = [t for t in stamps if w_start <= t <= w_end]
    if agent == "agy":
        runs = [(inside[0], inside[-1])] if len(inside) >= 2 else []
    else:
        runs = session_clock.active_runs(stamps, w_start, w_end)

    extras = {"attribution": "session", "notes": notes, "override": override,
              "window": f"{w_start.astimezone().strftime('%H:%M')}–{'24:00' if w_end.astimezone().strftime('%H:%M') == '00:00' and w_end > w_start else w_end.astimezone().strftime('%H:%M')}"}
    marks = focus_intervals(conn, session_id, win["day_start"], win["day_end"]) if use_focus else {}
    if marks:
        all_marked = [iv for ivs in marks.values() for iv in ivs]
        extras["unattributed"] = session_clock.total_minutes(session_clock.subtract(runs, all_marked))
        mine = marks.get(ticket)
        if not mine:
            return {"ok": False, "agent": agent, "session_id": session_id,
                    "reason": f"Hay marcas de foco hoy ({', '.join(sorted(marks))}) pero ninguna para {ticket}: usa `plane-tracker focus {ticket}` o registra con --duration."}
        runs = session_clock.intersect(runs, mine)
        extras["attribution"] = "focus"

    covered = session_coverage(conn, session_id, win["day"]) + reserved_runs(session_id, exclude_tickets)
    before = session_clock.total_minutes(runs)
    runs = session_clock.subtract(runs, covered)
    extras["excluded"] = before - session_clock.total_minutes(runs)
    ctx = {"agent": agent, "session_id": session_id, "origin": origin, "events": len(inside)}
    return ctx, runs, extras


def build_proposal(conn, args, capacity_bucket, worker_type, ticket):
    """Mide la sesión (solo tiempos) y devuelve un dict; 'ok' False significa preguntar."""
    if capacity_bucket in NO_PROPOSAL_BUCKETS:
        return {"ok": False, "reason": f"El balde '{capacity_bucket}' (soporte/reuniones) no deja huella en un transcript: pregunta la duración."}
    measured = _measure(conn, args, worker_type, {ticket}, ticket, use_focus=True)
    if isinstance(measured, dict):
        return measured
    ctx, runs, extras = measured
    if int(round(session_clock.total_minutes(runs))) < 1:
        return {"ok": False, "agent": ctx["agent"], "session_id": ctx["session_id"],
                "reason": "No hay actividad medible en la ventana (o ya está registrada/reservada para esta sesión)."}
    return _proposal_from_runs(ctx, runs, extras)


def build_split(conn, args, spec, worker_type):
    """Reparte la actividad medible entre varios tickets: {ticket: propuesta} contiguas y sin solape."""
    tickets = [part.split("=")[0].strip().upper() for part in spec.split(",") if "=" in part]
    measured = _measure(conn, args, worker_type, set(tickets), None, use_focus=False)
    if isinstance(measured, dict):
        return measured
    ctx, runs, extras = measured
    total = int(round(session_clock.total_minutes(runs)))
    try:
        shares = session_clock.parse_split(spec, total)
    except ValueError as exc:
        return {"ok": False, "agent": ctx["agent"], "session_id": ctx["session_id"], "reason": str(exc)}
    pieces = session_clock.cut_runs(runs, [m for _, m in shares])
    group = uuid.uuid4().hex[:8]
    parts = {}
    for (ticket, minutes), piece in zip(shares, pieces):
        if not piece:
            return {"ok": False, "agent": ctx["agent"], "session_id": ctx["session_id"], "reason": f"{ticket} se queda sin actividad con ese reparto."}
        proposal = _proposal_from_runs(ctx, piece, dict(extras, attribution="split"))
        proposal["split"] = {"group": group, "of": total, "share": minutes}
        parts[ticket] = proposal
    return {"ok": True, "group": group, "total": total, "parts": parts}


def print_proposal(proposal, ticket, stream):
    if not proposal["ok"]:
        stream.write(f"✖ Sin propuesta para {ticket}: {proposal['reason']}\n")
        for c in proposal.get("candidates", []):
            stream.write(f"   • {c['id']}  (última actividad {c['last_activity']})\n")
        stream.write("   Pregunta cuánto demoró; no se infiere ni se inventa.\n")
        return
    stream.write(f"⏱  Propuesta para {ticket}: {proposal['minutes']} min ({proposal['start_time']}–{proposal['end_time']}, {proposal['date']})\n")
    stream.write(f"   • Fuente   : {proposal['agent']} · sesión {proposal['session_id']} ({proposal['origin']}) · confianza {proposal['confidence']}\n")
    stream.write(f"   • Medición : neta {proposal['net_minutes']} min · bruta {proposal['gross_minutes']} min · {len(proposal['segments'])} tramo(s) · atribución {proposal['attribution']}\n")
    stream.write(f"   • Ventana  : {proposal['window']}\n")
    if proposal.get("split"):
        stream.write(f"   • Reparto  : parte de {proposal['split']['of']} min medidos (grupo {proposal['split']['group']}); no se recalcula mientras esté vigente\n")
    for w in proposal["warnings"]:
        stream.write(f"   ⚠ {w}\n")


def print_split(result, stream):
    stream.write(f"⏱  Reparto de {result['total']} min medidos (grupo {result['group']}):\n")
    for ticket, proposal in result["parts"].items():
        stream.write(f"   • {ticket:<10} {proposal['minutes']:>4} min  ({proposal['start_time']}–{proposal['end_time']})\n")
    first = next(iter(result["parts"].values()))
    stream.write(f"   • Fuente: {first['agent']} · sesión {first['session_id']} · confianza {first['confidence']} · ventana {first['window']}\n")
    for w in first["warnings"]:
        stream.write(f"   ⚠ {w}\n")
