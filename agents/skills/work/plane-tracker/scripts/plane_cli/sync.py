"""Sincronización de los worklogs registrados en los comentarios de Plane hacia SQLite (defectos 0017, 0010 y 0022 del RFC 0021).

Expone: sync_remote_worklogs(), SyncResult, SYNC_COOLDOWN.
No hace: imprimir reportes. Cubre los proyectos ACCESIBLES (no una lista fija), pagina con `per_page` y `cursor` y corta localmente por fecha (la API ignora `limit` y los
filtros de fecha), lee los comentarios solo de los tickets con actividad en el periodo y se detiene antes de agotar el presupuesto de tasa dejando la sincronización marcada como
incompleta. La marca de sincronización es por proyecto y periodo (tabla `worklog_sync`). Nada se inventa: sin fecha u hora medidas el comentario no entra (se cuenta); balde, fase,
rol, tipo de trabajador, pista y notas que no vengan en el comentario se guardan con su procedencia (`defaulted_json`). Dos sincronizaciones del mismo comentario dan filas idénticas.
La lectura de comentarios es incremental por ticket (`worklog_issue_sync`): un ticket cuyo `updated_at` no cambió desde la última lectura completa de sus comentarios no se vuelve a pedir, así
una sincronización cortada por el presupuesto de tasa AVANZA en la siguiente y converge; `force=True` (`report time --refresh`) relee todo. Una fila que coincide con un registro en cola se vincula si el comentario es el propio (mismo client_id) y se omite si es otro. Si Plane deja de responder a mitad del sync lo termina
con un aviso y sin marcarlo.
"""

import sys
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from plane_cli import api, clock
from plane_cli.api import PlaneUnavailable, api_request
from plane_cli.cache import RATE_RESERVE
from plane_cli.errors import CliError
from plane_cli.outbox import mark_sent, owner_of
from plane_cli.resolve import get_actor_uuid, get_projects_map
from plane_cli.timeutil import minutes_to_time, time_to_minutes
from plane_cli.worklog import extract_metadata_from_comment, upsert_worklog

SYNC_COOLDOWN = 300   # 5 minutos: una sincronización completa más reciente que esto no se repite
MAX_PAGES = 20
ISSUE_FIELDS = "id,sequence_id,name,updated_at"
# Campos de la fila que pueden no venir en el comentario: si faltan se guardan con un valor por defecto y constan como no medidos.
DEFAULTS = {"worker_type": "human", "capacity_bucket": "deep_work", "phase": "dev", "role": "backend_engineer", "track": "main", "notes": ""}


@dataclass
class SyncResult:
    synced: int = 0
    foreign: int = 0
    no_duration: int = 0
    unmeasured: int = 0          # con duración pero sin fecha u hora medidas: no entran (no se derivan del reloj)
    unmeasured_by: dict = field(default_factory=dict)  # lo mismo por proyecto
    pending: int = 0
    unchanged: int = 0           # tickets cuyos comentarios no se releyeron porque no cambiaron desde la última lectura
    unavailable: list = field(default_factory=list)   # PlaneUnavailable que cortaron la sincronización
    incomplete: set = field(default_factory=set)      # proyectos que quedaron a medias (presupuesto de tasa, 403, error de lectura)
    marked: dict = field(default_factory=dict)        # proyecto -> complete


def _targets(conn, base_url, api_key, workspace, filter_project):
    """[(identificador, UUID)] de los proyectos a sincronizar: los accesibles, o solo `filter_project` (que debe serlo: unknown_project con las opciones)."""
    accessible = {i: p["id"] for i, p in sorted(get_projects_map(conn, base_url, api_key, workspace).items()) if p.get("accessible", True)}
    if filter_project:
        ident = filter_project.upper()
        if ident not in accessible:
            raise CliError("unknown_project", f"Proyecto '{filter_project}' no encontrado.", f"Opciones: {', '.join(accessible)}. Usa -p {next(iter(accessible), 'PRJ')}.")
        return [(ident, accessible[ident])]
    return list(accessible.items())


def _budget_left():
    """False si el presupuesto de tasa anunciado por Plane llegó a la reserva: hay que parar antes de agotarlo."""
    limit = api.rate_limit()
    return not (limit and limit["remaining"] is not None and limit["remaining"] <= RATE_RESERVE)


def _is_old(issue, cutoff):
    try:
        return datetime.fromisoformat(issue["updated_at"].replace("Z", "+00:00")).date() < cutoff
    except (KeyError, AttributeError, ValueError):
        return False  # sin fecha legible no se descarta: es candidato


def _candidates(base_url, api_key, workspace, project_id, cutoff):
    """(tickets con actividad desde `cutoff`, estado): ok | rate | forbidden | error | unavailable (con la excepción). Orden `-updated_at`: se corta al llegar a una página toda anterior."""
    found, cursor = [], None
    for _ in range(MAX_PAGES):
        if not _budget_left():
            return found, "rate"
        url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/?order_by=-updated_at&per_page=100&fields={ISSUE_FIELDS}"
        if cursor:
            url += f"&cursor={urllib.parse.quote(cursor)}"
        try:
            page = api_request(url, api_key, raise_on_error=True)
        except PlaneUnavailable as exc:
            return found, ("unavailable", exc)
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            return found, "forbidden" if code in (401, 403) else "error"
        results = page.get("results", [])
        found += [i for i in results if not _is_old(i, cutoff)]
        cursor = page.get("next_cursor")
        if not page.get("next_page_results") or not cursor or (results and all(_is_old(i, cutoff) for i in results)):
            return found, "ok"
    return found, "rate"  # más páginas de las que se siguen: no se afirma que esté completo


def _comments(base_url, api_key, workspace, project_id, issue):
    """(comentarios, estado): ok | rate | error | unavailable (con la excepción)."""
    if not _budget_left():
        return [], "rate"
    url = f"{base_url.rstrip('/')}/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue['id']}/comments/"
    try:
        return api_request(url, api_key, raise_on_error=True).get("results", []), "ok"
    except PlaneUnavailable as exc:
        return [], ("unavailable", exc)
    except urllib.error.HTTPError as exc:
        exc.close()
        return [], "error"


def _entry(ident, issue, comment, meta):
    """(fila de worklogs, motivo): la fila con la procedencia de cada campo, o None y `no_duration` / `unmeasured` si el comentario no permite una fila medida."""
    dur = meta.get("duration_minutes") or meta.get("duration_net_minutes")  # duración explícita (nunca inventar 60 min): metadata o rango start/end
    if not dur and meta.get("start_time") and meta.get("end_time"):
        dur = time_to_minutes(meta["end_time"]) - time_to_minutes(meta["start_time"])
        if dur < 0:
            dur += 24 * 60
    if not dur or dur < 1:
        return None, "no_duration"
    if not meta.get("date") or not meta.get("start_time"):
        return None, "unmeasured"  # la fecha y la hora de inicio no se derivan del reloj de la sincronización
    end = meta.get("end_time") or minutes_to_time((time_to_minutes(meta["start_time"]) + dur) % (24 * 60))
    values = {name: meta.get(name, default) for name, default in DEFAULTS.items()}
    return {"ticket_id": f"{ident}-{issue.get('sequence_id')}", "issue_name": issue.get("name", ""), "date": meta["date"], "start_time": meta["start_time"],
            "end_time": end, "duration_minutes": dur, **values, "defaulted": sorted(name for name in DEFAULTS if name not in meta),
            "stoppers": meta.get("stoppers", []), "plane_comment_id": comment.get("id"), "created_at": comment.get("created_at") or "",
            "author_id": comment.get("created_by") or comment.get("actor"), "raw_payload": meta}, None


def _ingest(conn, ident, issue, comments, actor_uuid, result):
    for comment in comments:
        author = comment.get("created_by") or comment.get("actor")
        if actor_uuid and author and author != actor_uuid:  # los tickets compartidos no deben contaminar mi reporte
            result.foreign += 1
            continue
        meta = extract_metadata_from_comment(comment.get("comment_html", ""))
        if not meta:
            continue
        entry, reason = _entry(ident, issue, comment, meta)
        if entry is None:
            setattr(result, reason, getattr(result, reason) + 1)
            if reason == "unmeasured":
                result.unmeasured_by[ident] = result.unmeasured_by.get(ident, 0) + 1
            continue
        owner = owner_of(conn, entry["ticket_id"], entry["track"], entry["date"], entry["start_time"])
        if owner and meta.get("client_id") == owner["client_id"]:
            mark_sent(conn, owner, comment.get("id"))
        elif owner:
            result.pending += 1
            continue
        upsert_worklog(conn, entry)
        result.synced += 1


def _unchanged(conn, tasks):
    """Índices de `tasks` cuyo ticket no cambió desde la última lectura completa de sus comentarios."""
    known = {r["issue_id"]: r["issue_updated_at"] for r in conn.execute("SELECT issue_id, issue_updated_at FROM worklog_issue_sync")}
    return {n for n, (_ident, _pid, issue) in enumerate(tasks) if issue.get("updated_at") and known.get(issue["id"]) == issue["updated_at"]}


def _remember_read(conn, issue):
    with conn:
        conn.execute("INSERT INTO worklog_issue_sync (issue_id, issue_updated_at, as_of) VALUES (?, ?, ?) "
                     "ON CONFLICT(issue_id) DO UPDATE SET issue_updated_at = excluded.issue_updated_at, as_of = excluded.as_of", (issue["id"], issue.get("updated_at"), clock.timestamp()))


def _record_marks(conn, targets, date_from, date_to, result):
    """Una marca por proyecto y periodo; `complete` solo si ese proyecto se leyó entero. Sin red no se marca nada."""
    now = clock.timestamp()
    with conn:
        for ident, _project_id in targets:
            complete = ident not in result.incomplete
            result.marked[ident] = complete
            conn.execute("""
                INSERT INTO worklog_sync (project_ident, date_from, date_to, as_of, complete, unmeasured) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_ident, date_from, date_to) DO UPDATE SET as_of = excluded.as_of, complete = excluded.complete, unmeasured = excluded.unmeasured
            """, (ident, date_from, date_to, now, int(complete), result.unmeasured_by.get(ident, 0)))


def _report(result):
    if result.pending:
        sys.stderr.write(f"⚠ {result.pending} comentario(s) de Plane no se sincronizaron: coinciden con un registro en cola (outbox list).\n")
    if result.unmeasured:
        sys.stderr.write(f"ℹ {result.unmeasured} comentario(s) con telemetría sin fecha u hora no se sincronizaron: no se derivan del reloj.\n")
    if result.incomplete:
        sys.stderr.write(f"⚠ Sincronización parcial de {', '.join(sorted(result.incomplete))} (límite de peticiones o fallo de lectura): el reporte puede estar incompleto; reintenta con `report time --refresh`.\n")
    elif result.synced:
        sys.stderr.write(f"✔ Se sincronizaron {result.synced} registros telemétricos en SQLite3.\n")
    else:
        sys.stderr.write("ℹ Sincronización completa: sin nuevos registros telemétricos.\n")


def sync_remote_worklogs(conn, base_url, api_key, workspace, date_from_str, date_to_str, filter_project=None, force=False):
    """Sincroniza los comentarios de Plane de los tickets con actividad en el periodo y los persiste en SQLite; devuelve el SyncResult. `force` relee también los tickets sin cambios."""
    sys.stderr.write("🔄 Sincronizando registros de actividad desde Plane API...\n")
    targets = _targets(conn, base_url, api_key, workspace, filter_project)
    actor_uuid = get_actor_uuid(base_url, api_key, workspace, conn)  # solo mis comentarios alimentan mi reporte
    if not actor_uuid:
        sys.stderr.write("⚠ Sin PLANE_USERNAME/PLANE_ACTOR_UUID: el sync mezclará horas de compañeros en tickets compartidos.\n")
    try:
        cutoff = datetime.strptime(date_from_str, "%Y-%m-%d").date() - timedelta(days=1)
    except ValueError:
        cutoff = clock.local_today() - timedelta(days=7)

    result, tasks = SyncResult(), []
    for ident, project_id in targets:
        issues, state = _candidates(base_url, api_key, workspace, project_id, cutoff)
        if isinstance(state, tuple):
            result.unavailable.append(state[1])
            break
        if state != "ok":
            result.incomplete.add(ident)
        tasks += [(ident, project_id, issue) for issue in issues]

    skip = set() if force else _unchanged(conn, tasks)
    result.unchanged = len(skip)
    pending_tasks = [t for n, t in enumerate(tasks) if n not in skip]
    if not result.unavailable and pending_tasks:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_comments, base_url, api_key, workspace, pid, issue): (ident, issue) for ident, pid, issue in pending_tasks}
            for future in as_completed(futures):
                ident, issue = futures[future]
                comments, state = future.result()
                if isinstance(state, tuple):
                    result.unavailable.append(state[1])
                elif state != "ok":
                    result.incomplete.add(ident)
                _ingest(conn, ident, issue, comments, actor_uuid, result)
                if state == "ok":
                    _remember_read(conn, issue)

    if result.unavailable:
        sys.stderr.write(f"⚠ Sincronización incompleta: Plane no responde ({result.unavailable[0].cause}); se usan los datos locales.\n")
        return result
    _record_marks(conn, targets, date_from_str, date_to_str, result)
    _report(result)
    return result
