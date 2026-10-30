"""Comandos operativos: `health`, `focus set|clear|status` y `handoff`.

Expone: register_health(), register_focus_set/clear/status(), register_handoff(), cmd_health(), cmd_focus_set/clear/status(),
cmd_handoff(), summarize_requests(), handoff_facts(), format_handoff(), sanitize_remote(), HandoffError.
No hace: escribir en Plane.
"""

import json
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

import flow_metrics
import session_clock

from plane_cli import circuit, config
from plane_cli.config import add_json_flag, positive_int
from plane_cli.outbox import pending_counts
from plane_cli.proposals import FOCUS_KEEP_DAYS, focus_intervals
from plane_cli.resolve import detect_ticket_from_git, local_ticket_label
from plane_cli.worklog import PLACEHOLDER


def summarize_requests(records, since):
    """Agrega el registro de llamadas posteriores a `since` (datetime UTC)."""
    recent = []
    for r in records:
        ts = session_clock.parse_time(r.get("ts"))
        if ts and ts >= since:
            recent.append((ts, r))
    lat = sorted(r["ms"] for _, r in recent if r.get("status"))
    failures = [(ts, r) for ts, r in recent if not r.get("status") or r["status"] >= 400]
    by_error = {}
    for _, r in failures:
        key = r.get("error") or f"HTTP {r.get('status')}"
        by_error[key] = by_error.get(key, 0) + 1
    pct = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None
    return {"requests": len(recent), "failures": len(failures), "retried": sum(1 for _, r in recent if r.get("attempt", 1) > 1),
            "p50_ms": pct(0.5), "p95_ms": pct(0.95), "max_ms": lat[-1] if lat else None,
            "errors": by_error, "last_failures": [dict(r, ts=ts.astimezone().strftime("%Y-%m-%d %H:%M:%S")) for ts, r in failures[-5:]]}


def cmd_health(args, conn, base_url, api_key, workspace, default_project_id):
    """Latencia y errores de las últimas llamadas a Plane (caídas, timeouts, lentitud)."""
    records = []
    for path in (config.request_log() + ".1", config.request_log()):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        records.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            continue
    summary = summarize_requests(records, datetime.now(timezone.utc) - timedelta(hours=args.hours))
    state = circuit.describe()
    queue = pending_counts(conn)
    if getattr(args, "json", False):
        print(json.dumps({**summary, "circuit": state, "outbox": {"pending": queue[0], "failed": queue[1]}}, indent=2, ensure_ascii=False))
        return
    print(f"\n🩺 Plane · últimas {args.hours} h: {summary['requests']} llamadas, {summary['failures']} fallidas, {summary['retried']} con reintento")
    print(f"   • Latencia: p50 {summary['p50_ms']} ms · p95 {summary['p95_ms']} ms · máx {summary['max_ms']} ms")
    if state["state"] == "open":
        print(f"   • Circuito: abierto desde las {state['since']} ({state['cause']}); próximo sondeo en {state['next_probe_in']} s")
    else:
        print("   • Circuito: cerrado")
    print(f"   • Cola de salida: {queue[0]} pendiente(s), {queue[1]} fallido(s)")
    for key, count in sorted(summary["errors"].items(), key=lambda kv: -kv[1]):
        print(f"   • {count} × {key}")
    for f in summary["last_failures"]:
        print(f"     {f['ts']}  {f['method']} {f['path'][-60:]}  → {f.get('error') or 'HTTP ' + str(f.get('status'))} ({f['ms']} ms)")
    print("")


def _focus_context(args, conn):
    """(agente, sesión, ahora, marcas abiertas) de esta sesión; purga las marcas antiguas y termina si no resuelve la sesión."""
    agent = getattr(args, "agent", None) or session_clock.detect_agent()
    if not agent:
        sys.stderr.write("Error: no se pudo determinar el agente (usa --agent claude|opencode|agy).\n")
        sys.exit(1)
    session_id, origin, cands = session_clock.resolve_session(agent, os.getcwd(), getattr(args, "session", None))
    if not session_id:
        sys.stderr.write(f"Error: no se pudo determinar la sesión de {agent}: {origin}. Indica --session <id>.\n")
        for sid, ts in cands:
            sys.stderr.write(f"   • {sid}  (última actividad {ts.astimezone().strftime('%Y-%m-%d %H:%M')})\n")
        sys.exit(1)
    now = config.now()
    with conn:  # las marcas son útiles solo el día en curso: se purgan las antiguas
        conn.execute("DELETE FROM session_marks WHERE COALESCE(ended_at, started_at) < ?", ((now - timedelta(days=FOCUS_KEEP_DAYS)).isoformat(timespec="seconds"),))
    current = conn.execute("SELECT id, ticket FROM session_marks WHERE session_id = ? AND ended_at IS NULL", (session_id,)).fetchall()
    return agent, session_id, now, current


def cmd_focus_status(args, conn, base_url, api_key, workspace, default_project_id):
    """Tiempo atribuido hoy a cada ticket por las marcas de foco de la sesión."""
    agent, session_id, now, current = _focus_context(args, conn)
    stamps = session_clock.timestamps(agent, session_id)
    midnight = config.local_midnight_utc(now)
    runs = session_clock.active_runs(stamps, midnight, now)
    marks = focus_intervals(conn, session_id, midnight, now)
    per_ticket = {t: session_clock.total_minutes(session_clock.intersect(runs, ivs)) for t, ivs in marks.items()}
    unattributed = session_clock.total_minutes(session_clock.subtract(runs, [iv for ivs in marks.values() for iv in ivs]))
    result = {"session": session_id, "agent": agent, "current": current[0]["ticket"] if current else None,
              "tickets": {t: round(m, 1) for t, m in per_ticket.items()}, "unattributed_minutes": round(unattributed, 1)}
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    print(f"\n🎯 Foco de la sesión {session_id} ({agent}) · hoy")
    print(f"   • Ahora: {result['current'] or '— (sin foco)'}")
    for t, m in sorted(result["tickets"].items(), key=lambda kv: -kv[1]):
        print(f"   • {t:<10} {m:.0f} min atribuidos")
    print(f"   • Sin foco : {unattributed:.0f} min (no se atribuyen solos)\n")


def cmd_focus_clear(args, conn, base_url, api_key, workspace, default_project_id):
    """Cierra la marca de foco abierta de esta sesión."""
    agent, session_id, now, current = _focus_context(args, conn)
    with conn:
        conn.execute("UPDATE session_marks SET ended_at = ? WHERE session_id = ? AND ended_at IS NULL", (now.isoformat(timespec="seconds"), session_id))
    print("✔ Foco cerrado" + (f" (era {current[0]['ticket']})" if current else " (no había foco abierto)"))


def cmd_focus_set(args, conn, base_url, api_key, workspace, default_project_id):
    """Marca en qué ticket trabaja esta sesión (solo local); `worklog propose` atribuye a cada ticket solo sus intervalos. Avisa de un estado terminal solo si la caché local lo conoce."""
    agent, session_id, now, current = _focus_context(args, conn)
    ticket = local_ticket_label(args.issue).upper()
    state = conn.execute("SELECT state_group FROM issues_cache WHERE ticket_id = ?", (ticket,)).fetchone()
    if state and state["state_group"] in flow_metrics.TERMINAL_GROUPS:
        sys.stderr.write(f"⚠ {ticket} está en un estado terminal ({state['state_group']}); la marca se crea igual.\n")
    if any(row["ticket"] == ticket for row in current):
        print(f"✔ El foco ya está en {ticket}")
        return
    iso = now.isoformat(timespec="seconds")
    with conn:
        conn.execute("UPDATE session_marks SET ended_at = ? WHERE session_id = ? AND ended_at IS NULL", (iso, session_id))
        conn.execute("INSERT INTO session_marks (session_id, agent, ticket, started_at) VALUES (?,?,?,?)", (session_id, agent, ticket, iso))
    previous = f" (antes {current[0]['ticket']})" if current else ""
    print(f"✔ Foco en {ticket}{previous} · sesión {session_id} ({agent})")


class HandoffError(Exception):
    pass


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=15)


def sanitize_remote(url):
    """'owner/repo' de un remoto ssh o https de GitHub, sin credenciales; None si no se reconoce."""
    url = (url or "").strip()
    match = re.match(r"^(?:ssh://)?git@github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url)
    if not match:
        parsed = urllib.parse.urlparse(url)
        match = re.match(r"^/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", parsed.path) if parsed.hostname == "github.com" else None
    return f"{match.group(1)}/{match.group(2)}" if match else None


def handoff_facts(base=None):
    """Hechos del repo del directorio actual (solo git local, sin red). Lanza HandoffError si el relevo no sería útil."""
    if _git("rev-parse", "--show-toplevel").returncode != 0:
        raise HandoffError("No estás dentro de un repositorio git.")
    branch = _git("symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    if not branch:
        raise HandoffError("HEAD desacoplado: cambia a una rama antes del relevo.")
    sha = _git("rev-parse", "HEAD").stdout.strip()
    remotes = _git("remote").stdout.split()
    if not remotes:
        raise HandoffError("El repositorio no tiene remoto: otra persona no podría retomar el trabajo.")
    unpushed = int(_git("rev-list", "--count", "HEAD", "--not", "--remotes").stdout.strip() or 0)
    if unpushed:
        raise HandoffError(f"{unpushed} commit(s) sin pushear (según el último fetch local); haz push antes del relevo.")
    containing = [r for r in _git("for-each-ref", "--contains", "HEAD", "refs/remotes", "--format=%(refname:short)").stdout.split() if not r.endswith("/HEAD")]
    preferred = [r for r in containing if r.endswith("/" + branch)]
    where = (preferred or containing or ["?"])[0]
    remote_name = "origin" if "origin" in remotes else remotes[0]
    repo = sanitize_remote(_git("remote", "get-url", remote_name).stdout)
    dirty = len([line for line in _git("status", "--porcelain").stdout.splitlines() if line.strip()])
    facts = {"branch": branch.replace("`", ""), "sha": sha, "where": where.replace("`", ""), "repo": repo, "dirty": dirty,
             "base": None, "ahead_of_base": None}
    if base:
        if not re.match(r"^[A-Za-z0-9._/-]+$", base) or base.startswith("-"):
            raise HandoffError(f"Nombre de base inválido: {base!r}.")
        if _git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{base}").returncode != 0:
            raise HandoffError(f"No existe origin/{base} localmente (¿falta un fetch?).")
        facts["base"] = base
        facts["ahead_of_base"] = int(_git("rev-list", "--count", f"origin/{base}..HEAD").stdout.strip() or 0)
    return facts


def format_handoff(facts):
    lines = [
        "### 🔄 Relevo de Tarea (Handoff Snapshot)",
        f"- **Avance realizado:** {PLACEHOLDER}",
        f"- **Rama Git / Commit:** `{facts['branch']}` @ `{facts['sha']}` (en {facts['where']}, según el último fetch local)",
    ]
    detail = [f"Repo: {facts['repo'] or 'remoto no reconocido'}"]
    if facts["base"]:
        detail.append(f"Base: {facts['base']} ({facts['ahead_of_base']} commit(s) sobre origin/{facts['base']})")
    detail.append("working tree limpio" if not facts["dirty"] else f"⚠ {facts['dirty']} archivo(s) sin commitear")
    lines.append("  " + " · ".join(detail))
    lines += [f"- **Estado actual:** {PLACEHOLDER}", f"- **Stoppers / Próximo paso:** {PLACEHOLDER}"]
    return "\n".join(lines)


def cmd_handoff(args, conn, base_url, api_key, workspace, default_project_id):
    """Imprime el borrador del relevo (no publica). Avance, estado y próximos pasos los completa quien trabajó."""
    try:
        facts = handoff_facts(getattr(args, "base", None))
    except HandoffError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        sys.exit(1)
    print(format_handoff(facts))
    ticket = args.issue or detect_ticket_from_git() or "<TICKET>"
    sys.stderr.write(f"\nCompleta los {PLACEHOLDER}, guarda el texto en un archivo y publícalo con:\n"
                     f"  plane-tracker comment add {ticket} -f relevo.md --duration <min>   (o --accept-proposal)\n")


def register_health(sub):
    p_health = sub.add_parser("health", help="Latencia y errores recientes de la API")
    p_health.add_argument("--hours", type=positive_int, default=24, help="Ventana en horas (por defecto 24)")
    add_json_flag(p_health)
    p_health.set_defaults(handler=cmd_health)


def register_handoff(sub):
    p_handoff = sub.add_parser("handoff", help="Borrador del relevo con los hechos de git",
                                  description="Imprime el borrador del relevo (Handoff Snapshot) con los hechos de git del directorio actual; no publica.")
    p_handoff.add_argument("issue", nargs="?", default=None, help="Ticket (solo para la sugerencia de publicación)")
    p_handoff.add_argument("--base", metavar="BRANCH", help="Rama base para contar 'N commits sobre origin/BRANCH' (nunca se asume)")
    p_handoff.set_defaults(handler=cmd_handoff)


def _add_session_args(parser):
    parser.add_argument("--agent", choices=list(session_clock.AGENTS), help="Agente de la sesión (por defecto: según el entorno)")
    parser.add_argument("--session", metavar="ID", help="ID de la sesión del agente")


def register_focus_set(sub):
    p_set = sub.add_parser("set", help="Marcar el ticket en el que trabaja la sesión",
                             description="Marca en qué ticket trabaja esta sesión; `worklog propose` reparte el tiempo medido entre los tickets marcados.")
    p_set.add_argument("issue", help="Ticket en el que empiezas a trabajar")
    _add_session_args(p_set)
    p_set.set_defaults(handler=cmd_focus_set)


def register_focus_clear(sub):
    p_clear = sub.add_parser("clear", help="Cerrar la marca de foco abierta")
    _add_session_args(p_clear)
    p_clear.set_defaults(handler=cmd_focus_clear)


def register_focus_status(sub):
    p_status = sub.add_parser("status", help="Ver el tiempo atribuido hoy por ticket")
    _add_session_args(p_status)
    add_json_flag(p_status)
    p_status.set_defaults(handler=cmd_focus_status)
