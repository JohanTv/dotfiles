"""Métricas de flujo por work item: lead time, cycle time, tiempo por estado y esfuerzo.

Todo en tiempo de calendario. Los timestamps de Plane son UTC; los worklogs guardan fecha y
hora local (naive) y se convierten antes de comparar. Funciones puras, sin red ni base de datos.
"""

import re
import statistics
import unicodedata
from datetime import datetime, timedelta, timezone

TERMINAL_GROUPS = ("completed", "cancelled")
# Un cierre más rápido que esto (cierre masivo, ticket creado ya completado) no representa flujo real.
MIN_MEANINGFUL_LEAD = timedelta(minutes=5)
_UMBRELLA = re.compile(r"-\s*W\d{2}\s*$")


STANDBY_NAMES = (
    "pausado",
    "pausada",
    "paused",
    "bloqueado",
    "bloqueada",
    "standby",
    "pausa",
    "en pausa",
    "on hold",
    "bloqueo",
    "en espera",
)


def _norm(text):
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").strip().lower()) if unicodedata.category(c) != "Mn")


def _is_standby(name):
    norm = _norm(name)
    if not norm:
        return False
    if norm in STANDBY_NAMES:
        return True
    return norm.startswith(("pausad", "bloquead", "paused", "standby", "on hold", "en pausa", "bloqueo", "en espera"))


def _minutes(delta):
    return delta.total_seconds() / 60.0


def _worklog_interval(entry):
    """(inicio, fin) en UTC desde fecha y HH:MM locales; cruza medianoche si fin < inicio."""
    start = datetime.strptime(f"{entry['date']} {entry['start_time']}", "%Y-%m-%d %H:%M").astimezone(timezone.utc)
    end = datetime.strptime(f"{entry['date']} {entry['end_time']}", "%Y-%m-%d %H:%M").astimezone(timezone.utc)
    if end < start:
        end += timedelta(days=1)
    return start, end


def _segment_interval(entry, seg):
    start = datetime.strptime(f"{entry['date']} {seg['start']}", "%Y-%m-%d %H:%M").astimezone(timezone.utc)
    end = datetime.strptime(f"{entry['date']} {seg['end']}", "%Y-%m-%d %H:%M").astimezone(timezone.utc)
    return start, (end + timedelta(days=1) if end < start else end)


def union_minutes(intervals):
    """Longitud de la unión de intervalos (sin contar dos veces el solape)."""
    if not intervals:
        return 0.0
    ordered = sorted(intervals)
    total = timedelta()
    cur_start, cur_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            total += cur_end - cur_start
            cur_start, cur_end = start, end
    total += cur_end - cur_start
    return _minutes(total)


def _sort_transitions(transitions):
    """Ordena transiciones por timestamp UTC y encadenamiento causal (from_id -> to_id)."""
    if not transitions:
        return []
    by_time = {}
    for t in transitions:
        by_time.setdefault(t["at"], []).append(t)
    ordered = []
    for at_val in sorted(by_time):
        bucket = by_time[at_val]
        if len(bucket) <= 1:
            ordered.extend(bucket)
            continue
        bucket.sort(key=lambda item: 1 if item.get("from_id") != item.get("to_id") else 0)
        to_ids = {item.get("to_id") for item in bucket if item.get("from_id") != item.get("to_id")}
        firsts = [item for item in bucket if item.get("from_id") not in to_ids]
        curr = firsts[0] if firsts else bucket[0]
        chain = [curr]
        remaining = [item for item in bucket if item is not curr]
        while remaining:
            nxt = next((item for item in remaining if item.get("from_id") == curr.get("to_id")), None)
            if not nxt:
                nxt = remaining[0]
            chain.append(nxt)
            remaining.remove(nxt)
            curr = nxt
        ordered.extend(chain)
    return ordered


def compute_flow(issue, transitions, states, worklogs, now):
    """issue: {name, created_at, completed_at, state}; transitions: [{at, from_id, to_id}] (at UTC);
    states: {id: {name, group}}; worklogs: [{date, start_time, end_time, duration_minutes}]."""
    created = issue["created_at"]
    transitions = _sort_transitions(transitions)
    current = states.get(issue.get("state"), {})
    flags = []

    group = lambda sid: states.get(sid, {}).get("group") or "?"
    name_of = lambda sid: states.get(sid, {}).get("name") or "?"

    # Segmentos (inicio, fin, state_id): el estado inicial sale del primer old_identifier.
    segments = []
    if transitions:
        first = transitions[0]
        points = [(min(created, first["at"]), first["from_id"])] + [(t["at"], t["to_id"]) for t in transitions]
        for (start, sid), nxt in zip(points, points[1:] + [(None, None)]):
            end = nxt[0]
            if end is None:
                end = start if group(sid) in TERMINAL_GROUPS else now
            segments.append((start, end, sid))
    else:
        flags.append("no_transition")
        if current.get("group") not in TERMINAL_GROUPS and issue.get("state"):
            segments.append((created, now, issue["state"]))

    if any(sid not in states for _, _, sid in segments):
        flags.append("unknown_state")

    # Resultado y cierre: el estado actual manda (un ticket reabierto vuelve a estar abierto).
    outcome = {"completed": "completed", "cancelled": "cancelled"}.get(current.get("group"), "open")
    closed = None
    if outcome == "completed":
        closed = issue.get("completed_at") or (transitions[-1]["at"] if transitions else None)
    elif outcome == "cancelled":
        closed = next((t["at"] for t in reversed(transitions) if group(t["to_id"]) == "cancelled"), None)
    lead_end = closed or now
    lead = max(lead_end - created, timedelta())

    by_state = {}
    gross = active = standby = timedelta()
    for start, end, sid in segments:
        span = max(end - start, timedelta())
        if span:
            by_state[name_of(sid)] = by_state.get(name_of(sid), timedelta()) + span
        is_standby = _is_standby(name_of(sid))
        if is_standby:
            standby += span
        if group(sid) == "started":
            gross += span
            if not is_standby:
                active += span
    has_started = any(group(sid) == "started" for _, _, sid in segments)
    if not has_started:
        flags.append("no_started")
    if _UMBRELLA.search(issue.get("name") or ""):
        flags.append("umbrella")
    if outcome != "open" and lead < MIN_MEANINGFUL_LEAD:
        flags.append("instant_close")

    intervals, compute, out_before, out_after = [], 0, 0, 0
    for entry in worklogs:
        compute += int(entry.get("duration_minutes") or 0)
        try:
            # Con segmentos (actividad intercalada entre tickets) el reloj es la unión de sus tramos, no el rango envolvente.
            spans = [_segment_interval(entry, seg) for seg in entry["segments"]] if entry.get("segments") else [_worklog_interval(entry)]
        except (KeyError, ValueError):
            continue
        intervals.extend(spans)
        if spans[0][0] < created:
            out_before += 1
        if closed and spans[0][0] > closed:
            out_after += 1
    clock = union_minutes(intervals)
    cycle_active = _minutes(active) if has_started else None

    return {
        "outcome": outcome,
        "flags": flags,
        "created": created,
        "closed": closed,
        "lead_minutes": _minutes(lead),
        "cycle_active_minutes": cycle_active,
        "cycle_gross_minutes": _minutes(gross) if has_started else None,
        "standby_minutes": _minutes(standby),
        "by_state_minutes": {k: _minutes(v) for k, v in by_state.items()},
        "effort_compute_minutes": compute,
        "effort_clock_minutes": clock,
        "worklogs": len(worklogs),
        "worklogs_before_created": out_before,
        "worklogs_after_closed": out_after,
        # Cautela: calendario y con tickets que esperan a terceros; solo señal secundaria.
        "effort_clock_over_cycle": (clock / cycle_active) if cycle_active else None,
    }


def aggregate(flows):
    """Medianas de lead/cycle de tickets completados con flujo real, WIP y cobertura."""
    def real(f):
        return f["outcome"] == "completed" and not {"umbrella", "instant_close", "no_transition"} & set(f["flags"])

    done = [f for f in flows if real(f)]
    leads = [f["lead_minutes"] for f in done]
    cycles = [f["cycle_active_minutes"] for f in done if f["cycle_active_minutes"] is not None]
    standbys = [(f.get("standby_minutes") or 0.0) for f in flows if (f.get("standby_minutes") or 0.0) > 0]
    total_standby = sum((f.get("standby_minutes") or 0.0) for f in flows)
    return {
        "tickets": len(flows),
        "completed": sum(f["outcome"] == "completed" for f in flows),
        "cancelled": sum(f["outcome"] == "cancelled" for f in flows),
        "open": sum(f["outcome"] == "open" for f in flows),
        "n_lead": len(leads),
        "median_lead_minutes": statistics.median(leads) if leads else None,
        "n_cycle": len(cycles),
        "median_cycle_minutes": statistics.median(cycles) if cycles else None,
        "total_standby_minutes": total_standby,
        "tickets_with_standby": len(standbys),
        "median_standby_minutes": statistics.median(standbys) if standbys else None,
        "excluded": len(flows) - len(done) - sum(f["outcome"] != "completed" for f in flows),
    }
