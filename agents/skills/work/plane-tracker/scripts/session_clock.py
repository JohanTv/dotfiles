"""Mide la actividad de una sesión de agente leyendo SOLO tiempos, tipos e ids.

Nunca se lee ni se devuelve contenido de conversaciones (prompts, respuestas, títulos,
resúmenes). Agentes soportados: Claude Code, OpenCode y Antigravity CLI (agy).
"""

import glob
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone

AGENTS = ("claude", "opencode", "agy")
SESSION_ENV = {"claude": "CLAUDE_CODE_SESSION_ID", "opencode": "OPENCODE_SESSION_ID"}

CLAUDE_PROJECTS = os.path.expanduser("~/.claude/projects")
OPENCODE_DB = os.path.expanduser("~/.local/share/opencode/opencode.db")
AGY_DB = os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")

# Confianza de cada adaptador: Claude y OpenCode traen un evento por mensaje; agy solo hitos.
CONFIDENCE = {"claude": "media", "opencode": "alta", "agy": "baja"}

# Sesiones candidatas cuya última actividad dista menos de esto se consideran ambiguas.
AMBIGUITY_WINDOW = timedelta(minutes=30)

_UUID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def parse_time(value):
    """ISO-8601 (con 'Z' y hasta nanosegundos) o epoch (s/ms) -> datetime UTC, o None."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000.0 if value > 1e11 else float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    text = re.sub(r"(\.\d{6})\d+", r"\1", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def valid_session_id(session_id):
    return bool(session_id) and bool(_UUID.match(session_id))


def agent_from_worker_type(worker_type):
    """'agent:claude' -> 'claude'; cualquier otro valor -> None."""
    if worker_type and worker_type.startswith("agent:"):
        name = worker_type.split(":", 1)[1]
        return {"agy": "agy", "claude": "claude", "opencode": "opencode"}.get(name)
    return None


def detect_agent(env=None):
    """Agente actual según las variables de entorno de sesión."""
    env = os.environ if env is None else env
    for agent, var in SESSION_ENV.items():
        if env.get(var):
            return agent
    return None


# ------------------------------------------------------------------------------
# Adaptadores: id de sesión -> timestamps UTC ordenados
# ------------------------------------------------------------------------------

def claude_timestamps(session_id, projects_dir=None):
    """Solo el campo `timestamp` de cada línea. Ordena, descarta líneas sin tiempo o rotas."""
    if not valid_session_id(session_id):
        return []
    root = projects_dir or CLAUDE_PROJECTS
    # Solo el transcript principal: los subagentes viven en <id>/subagents/ y solapan al padre.
    paths = glob.glob(os.path.join(glob.escape(root), "*", f"{session_id}.jsonl"))
    found = []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        ts = parse_time(json.loads(line).get("timestamp"))
                    except (ValueError, AttributeError):
                        continue
                    if ts:
                        found.append(ts)
        except OSError:
            continue
    return sorted(set(found))


def _ro_connect(path):
    uri = "file:" + path + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def opencode_timestamps(session_id, db_path=None):
    """`time_created` de session_message (epoch ms). No se lee la columna `data`."""
    path = db_path or OPENCODE_DB
    if not valid_session_id(session_id) or not os.path.exists(path):
        return []
    try:
        conn = _ro_connect(path)
        try:
            rows = conn.execute(
                "SELECT time_created FROM session_message WHERE session_id = ? ORDER BY time_created",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []
    return sorted({ts for ts in (parse_time(r[0]) for r in rows) if ts})


def agy_timestamps(session_id, db_path=None):
    """Solo hitos (último input del usuario y última modificación); agy no expone cada mensaje."""
    path = db_path or AGY_DB
    if not valid_session_id(session_id) or not os.path.exists(path):
        return []
    try:
        conn = _ro_connect(path)
        try:
            row = conn.execute(
                "SELECT last_user_input_time, last_modified_time FROM conversation_summaries "
                "WHERE conversation_id = ?",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return []
    if not row:
        return []
    return sorted({ts for ts in (parse_time(v) for v in row) if ts})


def timestamps(agent, session_id, **paths):
    if agent == "claude":
        return claude_timestamps(session_id, paths.get("projects_dir"))
    if agent == "opencode":
        return opencode_timestamps(session_id, paths.get("opencode_db"))
    if agent == "agy":
        return agy_timestamps(session_id, paths.get("agy_db"))
    return []


# ------------------------------------------------------------------------------
# Resolución de sesión: env var -> --session -> candidatas por directorio (sin adivinar)
# ------------------------------------------------------------------------------

def _claude_candidates(cwd, projects_dir=None):
    slug = re.sub(r"[^A-Za-z0-9]", "-", cwd)
    folder = os.path.join(projects_dir or CLAUDE_PROJECTS, slug)
    files = sorted(glob.glob(os.path.join(glob.escape(folder), "*.jsonl")), key=os.path.getmtime, reverse=True)
    out = []
    for path in files[:5]:
        sid = os.path.basename(path)[: -len(".jsonl")]
        stamps = claude_timestamps(sid, projects_dir)
        if stamps:
            out.append((sid, stamps[-1]))
    return out


def _opencode_candidates(cwd, db_path=None):
    path = db_path or OPENCODE_DB
    if not os.path.exists(path):
        return []
    try:
        conn = _ro_connect(path)
        try:
            rows = conn.execute(
                "SELECT id, time_updated FROM session_v2 WHERE directory = ? AND parent_id IS NULL "
                "ORDER BY time_updated DESC LIMIT 5",
                (cwd,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []
    return [(r[0], parse_time(r[1])) for r in rows if parse_time(r[1])]


def _agy_candidates(cwd, db_path=None):
    path = db_path or AGY_DB
    if not os.path.exists(path):
        return []
    try:
        conn = _ro_connect(path)
        try:
            rows = conn.execute(
                "SELECT conversation_id, last_modified_time FROM conversation_summaries "
                "WHERE workspace_uris LIKE ? AND COALESCE(parent_conversation_id, '') = '' "
                "ORDER BY last_modified_time DESC LIMIT 5",
                ("%" + cwd + "%",),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []
    return [(r[0], parse_time(r[1])) for r in rows if parse_time(r[1])]


def resolve_session(agent, cwd, explicit=None, env=None, **paths):
    """Devuelve (session_id, origen, candidatas).

    session_id es None si no hay forma segura de elegir; `candidatas` lista ids (con su
    última actividad) para que el usuario indique --session. Nunca se adivina entre varias.
    """
    env = os.environ if env is None else env
    if explicit:
        return (explicit, "--session", []) if valid_session_id(explicit) else (None, "id inválido", [])
    var = SESSION_ENV.get(agent)
    if var and env.get(var):
        return env[var], f"${var}", []

    finder = {"claude": _claude_candidates, "opencode": _opencode_candidates, "agy": _agy_candidates}.get(agent)
    if not finder:
        return None, "agente desconocido", []
    key = {"claude": "projects_dir", "opencode": "opencode_db", "agy": "agy_db"}[agent]
    cands = finder(cwd, paths.get(key))
    if not cands:
        return None, "sin sesiones para este directorio", []
    cands.sort(key=lambda c: c[1], reverse=True)
    top = cands[0]
    rivals = [c for c in cands[1:] if top[1] - c[1] <= AMBIGUITY_WINDOW]
    if rivals:
        return None, "ambigua (varias sesiones recientes en el directorio)", cands
    return top[0], "directorio de trabajo", []


# ------------------------------------------------------------------------------
# Medición
# ------------------------------------------------------------------------------

def measure(stamps, window_start, window_end, gap_minutes=10):
    """Actividad dentro de la ventana [window_start, window_end] (datetimes UTC).

    bruta = primer -> último evento; neta = suma de los intervalos entre eventos
    consecutivos que no superan `gap_minutes` (las pausas largas se descuentan).
    """
    inside = [t for t in stamps if window_start <= t <= window_end]
    if not inside:
        return {"events": 0, "start": None, "end": None, "gross_minutes": 0.0, "net_minutes": 0.0, "pauses": 0}
    gap = timedelta(minutes=gap_minutes)
    net = timedelta()
    pauses = 0
    for prev, cur in zip(inside, inside[1:]):
        delta = cur - prev
        if delta <= gap:
            net += delta
        else:
            pauses += 1
    return {
        "events": len(inside),
        "start": inside[0],
        "end": inside[-1],
        "gross_minutes": (inside[-1] - inside[0]).total_seconds() / 60.0,
        "net_minutes": net.total_seconds() / 60.0,
        "pauses": pauses,
    }
