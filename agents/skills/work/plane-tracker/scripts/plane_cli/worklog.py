"""Telemetría de worklogs: bloque oculto de metadata en los comentarios, persistencia local y verificación.

Expone: extract_metadata_from_comment(), worklog_metadata_block(), find_metadata_block(), replace_metadata_block(),
corrected_metadata(), derived_start(), upsert_worklog(), check_worklogs(), reject_placeholders(), PLACEHOLDER.
No hace: llamadas a Plane.
"""

import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone


def extract_metadata_from_comment(comment_html):
    """Extrae metadata telemétrica oculta (<!-- PLANE_WORKLOG_METADATA ... -->) o deduce de tabla."""
    if not comment_html:
        return None

    # 1. Bloque JSON telemétrico oficial v2.1 / v2.2
    meta_match = re.search(r"<!--\s*PLANE_WORKLOG_METADATA\s*([\s\S]*?)\s*-->", comment_html)
    if meta_match:
        try:
            data = json.loads(meta_match.group(1).strip())
            if "date" in data and ("start_time" in data or "notes" in data):
                return data
        except Exception:
            pass

    # 2. Inferencia desde tabla markdown
    date_match = re.search(r"\*\*Fecha\*\*\s*\|\s*(\d{4}-\d{2}-\d{2})", comment_html)
    session_match = re.search(r"\*\*Sesión\*\*\s*\|\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", comment_html)
    notes_match = re.search(r"\*\*(?:Resumen|Notas|Detalle)\*\*\s*\|\s*([^|\n<]+)", comment_html)
    bucket_match = re.search(r"\*\*Capacidad\*\*\s*\|\s*`?([a-z_]+)`?", comment_html)
    track_match = re.search(r"\*\*Track\*\*\s*\|\s*`?([a-zA-Z0-9_-]+)`?", comment_html)

    if session_match:
        s_time = session_match.group(1)
        e_time = session_match.group(2)
        try:
            t1 = datetime.strptime(s_time, "%H:%M")
            t2 = datetime.strptime(e_time, "%H:%M")
            dur = int((t2 - t1).total_seconds() / 60)
            if dur < 0:
                dur += 24 * 60
        except Exception:
            dur = 60

        d_str = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")
        notes_str = notes_match.group(1).strip() if notes_match else ""
        bucket_str = bucket_match.group(1).strip() if bucket_match else "deep_work"
        track_str = track_match.group(1).strip() if track_match else "main"

        return {
            "schema_version": "2.2",
            "date": d_str,
            "start_time": s_time,
            "end_time": e_time,
            "duration_minutes": dur,
            "track": track_str,
            "worker_type": "human",
            "capacity_bucket": bucket_str,
            "notes": notes_str,
            "stoppers": [],
            "phase": "dev"
        }

    return None


def upsert_worklog(conn, entry):
    """Inserta o actualiza un registro de trabajo en SQLite3 de forma idempotente."""
    now = time.time()
    t_id = entry.get("ticket_id", "GENERAL")
    track = entry.get("track", "main")
    d_str = entry.get("date", datetime.now().strftime("%Y-%m-%d"))
    s_time = entry.get("start_time", "09:00")
    e_time = entry.get("end_time", "10:00")
    dur = entry.get("duration_minutes", 60)
    p_id = t_id.split("-")[0] if "-" in t_id else "GENERAL"
    i_name = entry.get("issue_name", "")
    w_type = entry.get("worker_type", "human")
    bucket = entry.get("capacity_bucket", "deep_work")
    phase = entry.get("phase", "dev")
    role = entry.get("role", "backend_engineer")
    notes = entry.get("notes", "")
    stoppers = json.dumps(entry.get("stoppers", []), ensure_ascii=False)
    comment_id = entry.get("plane_comment_id") or entry.get("id")
    raw_payload = json.dumps(entry.get("raw_payload", entry), ensure_ascii=False)
    created_at = entry.get("created_at", datetime.now().isoformat())

    with conn:
        conn.execute("""
            INSERT INTO worklogs (
                ticket_id, track, date, start_time, end_time, duration_minutes,
                plane_comment_id, project_id, issue_name, worker_type,
                capacity_bucket, phase, role, notes, stoppers_json, raw_payload,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticket_id, track, date, start_time) DO UPDATE SET
                end_time = excluded.end_time,
                duration_minutes = excluded.duration_minutes,
                plane_comment_id = COALESCE(excluded.plane_comment_id, worklogs.plane_comment_id),
                issue_name = CASE WHEN excluded.issue_name != '' THEN excluded.issue_name ELSE worklogs.issue_name END,
                worker_type = excluded.worker_type,
                capacity_bucket = excluded.capacity_bucket,
                phase = excluded.phase,
                role = excluded.role,
                notes = excluded.notes,
                stoppers_json = excluded.stoppers_json,
                raw_payload = excluded.raw_payload,
                updated_at = excluded.updated_at;
        """, (
            t_id, track, d_str, s_time, e_time, dur,
            comment_id, p_id, i_name, w_type,
            bucket, phase, role, notes, stoppers, raw_payload,
            created_at, now
        ))


def worklog_metadata_block(meta):
    """Comentario HTML oculto con la telemetría del worklog (los '--' se escapan para no cerrarlo)."""
    payload = json.dumps(meta, ensure_ascii=False, sort_keys=True).replace("--", "\\u002d\\u002d")
    return f"<!-- PLANE_WORKLOG_METADATA {payload} -->"


_BLOCK_RE = re.compile(r"<!--\s*PLANE_WORKLOG_METADATA[\s\S]*?-->")


def find_metadata_block(html):
    match = _BLOCK_RE.search(html or "")
    return match.group(0) if match else None


def replace_metadata_block(html, meta):
    """Sustituye el bloque oculto (o lo añade si no existe) sin tocar el texto visible."""
    block = worklog_metadata_block(meta)
    if _BLOCK_RE.search(html or ""):
        return _BLOCK_RE.sub(lambda _m: block, html, count=1)
    return (html or "") + "\n" + block


def corrected_metadata(old, duration, track=None, capacity_bucket=None, worker_type=None, force=False, edited_at=None):
    """Metadata corregida de un worklog existente: conserva sesión, tramos y demás, y deja rastro de la corrección."""
    meta = dict(old)
    segments = meta.get("segments")
    if segments and duration != sum(seg.get("minutes", 0) for seg in segments):
        if not force:
            raise ValueError("El worklog tiene tramos medidos que suman otra duración; usa --force para descartar los tramos y fijar la duración.")
        meta.pop("segments", None)
    meta["previous_duration_minutes"] = old.get("duration_minutes")
    meta["duration_minutes"] = duration
    for key, value in (("track", track), ("capacity_bucket", capacity_bucket), ("worker_type", worker_type)):
        if value:
            meta[key] = value
    measured_by = dict(meta.get("measured_by") or {})
    measured_by["was"] = measured_by.get("kind")
    measured_by["kind"] = "corrected"
    meta["measured_by"] = measured_by
    meta["edited_at"] = edited_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return meta


def derived_start(end_dt, duration):
    """HH:MM de inicio derivado de la duración; nunca antes de las 00:00 del día del fin."""
    start = end_dt - timedelta(minutes=duration)
    if start.date() != end_dt.date():
        sys.stderr.write("⚠ La duración cruza la medianoche: el inicio se limita a 00:00 del día del registro.\n")
        return "00:00"
    return start.strftime("%H:%M")


PLACEHOLDER = "[COMPLETAR]"


def reject_placeholders(text):
    """Un texto con marcadores sin completar (fuera del bloque oculto) nunca se publica."""
    if PLACEHOLDER in re.sub(r"<!--[\s\S]*?-->", "", text or ""):
        sys.stderr.write(f"Error: el texto aún tiene marcadores {PLACEHOLDER}; complétalos antes de publicar.\n")
        sys.exit(1)


CHECK_FIELDS = ("date", "start_time", "end_time", "duration_minutes", "track", "capacity_bucket", "worker_type")


CHECK_ERRORS = ("duplicate", "orphan", "mismatch", "missing_local")


def check_worklogs(local_rows, comments, s_str, e_str):
    """Compara filas locales con sus comentarios. comments: {id: {'meta': dict|None, 'has_block': bool}}."""
    issues = []
    by_cid = {}
    for row in local_rows:
        cid = row.get("plane_comment_id")
        if not cid:
            issues.append({"code": "unlinked", "ticket": row["ticket_id"], "comment_id": None, "detail": f"{row['date']} {row['start_time']} sin comentario asociado"})
            continue
        by_cid.setdefault(cid, []).append(row)
    for cid, rows in by_cid.items():
        ticket = rows[0]["ticket_id"]
        if len(rows) > 1:
            issues.append({"code": "duplicate", "ticket": ticket, "comment_id": cid, "detail": f"{len(rows)} filas locales para el mismo comentario"})
        comment = comments.get(cid)
        if comment is None:
            issues.append({"code": "orphan", "ticket": ticket, "comment_id": cid, "detail": "el comentario ya no existe en Plane"})
            continue
        if not comment["has_block"]:
            issues.append({"code": "no_block", "ticket": ticket, "comment_id": cid, "detail": "el comentario no lleva telemetría: no se reconstruiría con --sync"})
            continue
        for row in rows:
            diffs = [f"{f}: local {row.get(f)!r} ≠ Plane {comment['meta'].get(f)!r}" for f in CHECK_FIELDS
                     if comment["meta"].get(f) is not None and str(comment["meta"].get(f)) != str(row.get(f))]
            if diffs:
                issues.append({"code": "mismatch", "ticket": ticket, "comment_id": cid, "detail": "; ".join(diffs)})
    tickets = {r["ticket_id"] for r in local_rows}
    for cid, comment in comments.items():
        meta = comment.get("meta") or {}
        if comment["has_block"] and cid not in by_cid and meta.get("duration_minutes") and s_str <= str(meta.get("date", "")) <= e_str:
            issues.append({"code": "missing_local", "ticket": next(iter(tickets), "?"), "comment_id": cid,
                           "detail": f"comentario con telemetría ({meta.get('date')} {meta.get('start_time')}, {meta.get('duration_minutes')} min) sin fila local; usa report --sync"})
    return issues
