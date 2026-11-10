"""Consulta de la vista `agenda`: genera el dashboard personal con WIP, bloqueos y pull queue.

Expone: query().
No hace: red ni escribir; solo lee SQLite (store_issues, session_marks, worklogs, issue_snapshots).
"""

import json
import re
import subprocess
from dataclasses import replace
from datetime import datetime, timedelta

from plane_cli import clock, store_issues, timeutil
from plane_cli.coverage import Result, complete_list, settle

_PRIO_RANK = {"urgent": 0, "high": 1, "medium": 2, "low": 3, "none": 4}


def _priority_rank(prio):
    return _PRIO_RANK.get((prio or "").lower(), 5)


def _days_elapsed(iso_str, now_ts):
    if not iso_str:
        return 0.0
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        secs = now_ts - dt.timestamp()
        return max(0.0, round(secs / 86400.0, 1))
    except Exception:
        return 0.0


def _extract_dod(conn, ticket_id):
    row = conn.execute("SELECT issue_json FROM issue_snapshots WHERE ticket_id = ?", (ticket_id,)).fetchone()
    if not row or not row["issue_json"]:
        return None, None
    try:
        data = json.loads(row["issue_json"])
        desc = data.get("description_html") or data.get("description") or ""
        done = len(re.findall(r"\[x\]", desc, re.IGNORECASE))
        pending = len(re.findall(r"\[ \]", desc))
        total = done + pending
        return (done, total) if total > 0 else (None, None)
    except Exception:
        return None, None


def _extract_blocker(conn, ticket_id):
    snap = conn.execute("SELECT comments_json FROM issue_snapshots WHERE ticket_id = ?", (ticket_id,)).fetchone()
    if snap and snap["comments_json"]:
        try:
            comments = json.loads(snap["comments_json"])
            if comments:
                last_c = comments[-1].get("comment_html") or comments[-1].get("text") or ""
                m = re.search(r"(?:bloqueo|stopper|siguiente)[^:]*:\s*([^\n<]+)", last_c, re.IGNORECASE)
                if m:
                    return m.group(1).strip()[:100]
                clean = re.sub(r"<[^>]+>", " ", last_c).strip()
                if clean:
                    return clean.split("\n")[0][:100]
        except Exception:
            pass
    wl = conn.execute("SELECT notes FROM worklogs WHERE ticket_id = ? ORDER BY date DESC, start_time DESC LIMIT 1", (ticket_id,)).fetchone()
    if wl and wl["notes"]:
        clean = wl["notes"].strip().split("\n")[0]
        return clean[:100]
    return "En espera externa"


def _week_minutes(conn, actor_id, today_date):
    start = today_date - timedelta(days=today_date.weekday())
    end = start + timedelta(days=6)
    start_iso, end_iso = start.isoformat(), end.isoformat()
    rows = conn.execute(
        "SELECT date, start_time, end_time, duration_minutes, author_id, raw_payload FROM worklogs "
        "WHERE date >= ? AND date <= ?", (start_iso, end_iso)
    ).fetchall()

    days = {}
    compute_minutes = 0
    for r in rows:
        if actor_id and r["author_id"] and r["author_id"] != actor_id:
            continue
        compute_minutes += (r["duration_minutes"] or 0)
        payload = {}
        if r["raw_payload"]:
            try:
                parsed_p = json.loads(r["raw_payload"])
                if isinstance(parsed_p, dict):
                    payload = parsed_p
            except Exception:
                payload = {}
        for part in timeutil.expand_segments([{"date": r["date"], "start_time": r["start_time"], "end_time": r["end_time"],
                                              "duration_minutes": r["duration_minutes"], "raw_payload": json.dumps(payload)}]):
            days.setdefault(part["date"], []).append((timeutil.time_to_minutes(part["start_time"]), timeutil.time_to_minutes(part["end_time"])))

    clock_minutes = sum(timeutil.calculate_klee_union_minutes(iv) for iv in days.values())
    leverage = round(compute_minutes / clock_minutes, 1) if clock_minutes > 0 else 1.0
    return clock_minutes, compute_minutes, leverage


def _detect_git_branch_ticket():
    try:
        cmd = ["git", "branch", "--show-current"]
        branch = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        if not branch:
            cmd = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
            branch = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        match = re.search(r"([A-Za-z0-9_]+-\d+)", branch)
        if match:
            return match.group(1).upper()
    except Exception:
        pass
    return None


def query(conn, scope, catalogs, acq, wip_limit=2, stalled_days=3, focus_ticket=None):
    """Consulta los tickets en caché, calcula el estado de agenda y devuelve un Result."""
    now_ts = clock.timestamp()
    today_date = clock.local_today()
    today_iso = catalogs.today or today_date.isoformat()
    project_ids = [p.uuid for p in scope.projects]
    actor = catalogs.actor

    mark = conn.execute("SELECT ticket FROM session_marks WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1").fetchone()
    if mark and mark["ticket"]:
        focus_ticket = mark["ticket"]
        focus_source = "session_focus"
    elif focus_ticket:
        focus_source = "git_branch"
    else:
        git_t = _detect_git_branch_ticket()
        if git_t:
            focus_ticket = git_t
            focus_source = "git_branch"
        else:
            focus_ticket = None
            focus_source = None

    all_rows = store_issues.rows(conn, project_ids)
    active_focus = []
    in_progress = []
    blocked = []
    pull_queue = []

    for r in all_rows:
        if r["state_group"] in ("completed", "cancelled") or r["archived_at"]:
            continue
        raw_assignees = r["assignees_json"]
        assignees = []
        if raw_assignees:
            try:
                parsed_a = json.loads(raw_assignees)
                if isinstance(parsed_a, list):
                    assignees = parsed_a
                elif isinstance(parsed_a, (dict, set)):
                    assignees = list(parsed_a)
            except Exception:
                assignees = []
        if actor and actor not in assignees:
            continue

        days_up = _days_elapsed(r["plane_updated_at"] or r["updated_at"], now_ts)
        target = r["target_date"]
        is_overdue = bool(target and str(target) < today_iso)
        state_name = r["state_name"] or "unknown"
        state_group = r["state_group"] or "unknown"
        state_lower = state_name.lower()
        ticket_id = r["ticket_id"] or ""
        proj_ident = ticket_id.rsplit("-", 1)[0] if "-" in ticket_id else (ticket_id or "UNKNOWN")
        title = r["title"] or ""
        is_foc = bool(focus_ticket and ticket_id == focus_ticket)

        if state_lower in ("pausado", "paused", "bloqueado"):
            dod_d, dod_t = _extract_dod(conn, ticket_id)
            block_reason = _extract_blocker(conn, ticket_id)
            blocked.append({
                "ticket": ticket_id, "title": title, "state": state_name,
                "state_group": state_group, "priority": r["priority"] or "none",
                "project": proj_ident, "section": "blocked",
                "is_focus": is_foc, "focus_source": focus_source if is_foc else None,
                "days_since_update": days_up, "target_date": target,
                "is_overdue": is_overdue, "is_stalled": False,
                "dod_completed": dod_d, "dod_total": dod_t,
                "blocker_reason": block_reason, "standby_days": days_up,
                "plane_updated_at": r["plane_updated_at"],
            })
        elif state_group == "started":
            is_stalled = (days_up >= stalled_days)
            dod_d, dod_t = _extract_dod(conn, ticket_id)
            sec = "active_focus" if is_foc else "in_progress"
            item = {
                "ticket": ticket_id, "title": title, "state": state_name,
                "state_group": state_group, "priority": r["priority"] or "none",
                "project": proj_ident, "section": sec,
                "is_focus": is_foc, "focus_source": focus_source if is_foc else None,
                "days_since_update": days_up, "target_date": target,
                "is_overdue": is_overdue, "is_stalled": is_stalled,
                "dod_completed": dod_d, "dod_total": dod_t,
                "blocker_reason": None, "standby_days": None,
                "plane_updated_at": r["plane_updated_at"],
            }
            if is_foc:
                active_focus.append(item)
            else:
                in_progress.append(item)
        elif state_group == "unstarted":
            pull_queue.append({
                "ticket": ticket_id, "title": title, "state": state_name,
                "state_group": state_group, "priority": r["priority"] or "none",
                "project": proj_ident, "section": "pull_queue",
                "is_focus": is_foc, "focus_source": focus_source if is_foc else None,
                "days_since_update": days_up, "target_date": target,
                "is_overdue": is_overdue, "is_stalled": False,
                "dod_completed": None, "dod_total": None,
                "blocker_reason": None, "standby_days": None,
                "plane_updated_at": r["plane_updated_at"],
            })

    in_progress.sort(key=lambda x: (_priority_rank(x["priority"]), -(x["days_since_update"] or 0)))
    blocked.sort(key=lambda x: -(x["standby_days"] or 0))
    pull_queue.sort(key=lambda x: (_priority_rank(x["priority"]), -(x["days_since_update"] or 0)))

    results = active_focus + in_progress + blocked + pull_queue[:3]

    wip_count = len(active_focus) + len(in_progress)
    wip_exceeded = (wip_count > wip_limit)
    stalled_count = sum(1 for r in results if r["is_stalled"])
    overdue_count = sum(1 for r in results if r["is_overdue"])
    blocked_count = len(blocked)
    pull_queue_count = len(pull_queue)

    clock_m, compute_m, leverage = _week_minutes(conn, actor, today_date)

    actual_focus = focus_ticket if any(r.get("is_focus") for r in results) else None
    summary = {
        "wip_count": wip_count,
        "wip_limit": wip_limit,
        "wip_exceeded": wip_exceeded,
        "stalled_count": stalled_count,
        "overdue_count": overdue_count,
        "blocked_count": blocked_count,
        "pull_queue_count": pull_queue_count,
        "logged_clock_minutes_week": clock_m,
        "logged_compute_minutes_week": compute_m,
        "ai_leverage_multiplier": leverage,
        "active_focus_ticket": actual_focus,
    }

    notes = []
    if wip_exceeded:
        notes.append({"code": "wip_exceeded", "text": f"Límite WIP excedido ({wip_count}/{wip_limit} tareas en curso).",
                      "hint": "Concluye o pausa tareas antes de iniciar otras."})
    if stalled_count > 0:
        notes.append({"code": "ticket_stalled", "text": f"{stalled_count} ticket(s) estancado(s) (> {stalled_days}d sin actividad).",
                      "hint": "plane-tracker handoff o update --state Pausado."})

    detail = dict(acq.detail)
    detail["today"] = today_iso
    detail["wip_limit"] = wip_limit
    detail["stalled_threshold_days"] = stalled_days
    cov = replace(acq, detail={k: v for k, v in detail.items() if v is not None})
    cov_settled = settle(replace(cov, complete=complete_list(cov)), tuple(notes))
    return Result(rows=results, total=len(results), coverage=cov_settled, summary=summary, extra_notes=tuple(notes))
