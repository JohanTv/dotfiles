"""Soporte de los tests de caracterización (golden) del CLI.

Responsabilidad: servidor Plane falso (http.server en 127.0.0.1), ejecución aislada del CLI por subproceso
(HOME temporal, TZ=UTC, sin credenciales reales) y comparación de la salida normalizada contra tests/golden/.
Expone: FakePlane, Sandbox, run_scenario(). No toca el HOME real ni el Plane real.

Inyección de fallos (FakePlane):
  fake.add_fault(method, path_regex, kind, arg=None, n=None)   method "*" = cualquiera; n = nº de veces (None = siempre)
    kind "status"      responde con el código `arg` y {"detail": "injected"}
         "hang"        retiene la conexión `arg` segundos y la cierra sin responder (timeout de lectura del cliente)
         "drop"        cierra la conexión sin responder
         "commit_drop" aplica la escritura (comentarios) y corta la respuesta: el cliente no sabe si se guardó
         "delay"       espera `arg` segundos y luego responde con normalidad
         "flap"        alterna cíclicamente una lista de (kind, arg), p. ej. [("status", 502), ("ok", None)]; "ok" = respuesta normal
         "raw"         `arg` = bytes enviados tal cual como respuesta (BadStatusLine, 200 con HTML, cuerpo truncado...)
  fake.clear_faults()          fake.fail = [(método, regex, estado, cuerpo)] sigue disponible para errores simples.
  fake.store_comments = True   los POST de comentarios se guardan (con external_id/external_source) y devuelven el comentario;
                               fake.ext_id = False desactiva el 409 por external_id duplicado (el servidor lo ignora).
  fake.committed               ids de los comentarios guardados; fake.requests, todas las peticiones recibidas.
  fake.close() / fake.reopen() cierra el socket (conexión rechazada) y lo reabre en el mismo puerto.
Sandbox(fake=FakePlane(...)) usa ese servidor; sb.dead_url es una URL de puerto cerrado; sb.write_circuit(...) y
sb.circuit_state() fijan/leen <HOME>/.cache/plane/circuit.json; sb.run(..., timeout=s) y sb.last_elapsed miden el subproceso.

La ruta del script bajo prueba sale de PLANE_PY (por defecto scripts/plane.py); GOLDEN_UPDATE=1 reescribe los golden.
"""
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import socket
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
PLANE_PY = os.environ.get("PLANE_PY") or os.path.join(SKILL, "scripts", "plane.py")
GOLDEN_DIR = os.path.join(HERE, "golden")

P1 = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"
WS = "ws"
ME = "aaaaaaaa-0000-4000-8000-000000000001"
OTHER = "bbbbbbbb-0000-4000-8000-000000000002"
SESSION = "sess-golden-0001"

STATE_DEFS = [("Backlog", "backlog", True), ("Pendiente", "unstarted", False), ("Progreso", "started", False),
              ("Pausado", "started", False), ("Pruebas", "started", False), ("Revisión", "started", False),
              ("Completado", "completed", False), ("Cancelado", "cancelled", False)]


def state_id(pid, name):
    return f"{pid[:2]}{abs(hash_name(name)) % 10**6:06d}-0000-4000-8000-{pid[:12]}"


def hash_name(name):
    return sum((i + 1) * ord(c) for i, c in enumerate(name))


def meta_block(**fields):
    meta = {"schema_version": "2.2", "stoppers": [], "phase": "dev", "capacity_bucket": "deep_work", "worker_type": "human",
            "track": "main", **fields}
    return "<!-- PLANE_WORKLOG_METADATA " + json.dumps(meta, sort_keys=True) + " -->"


def build_data():
    states = {pid: [{"id": state_id(pid, n), "name": n, "slug": n.lower(), "group": g, "default": d} for n, g, d in STATE_DEFS]
              for pid in (P1, P2)}
    s = lambda pid, name: state_id(pid, name)
    issues = {
        P1: [
            {"id": "10000000-0000-4000-8000-000000000001", "sequence_id": 1, "name": "Validaciones de formulario SMS", "priority": "high",
             "state": s(P1, "Progreso"), "created_at": "2026-10-01T10:00:00Z", "updated_at": "2026-10-20T15:00:00Z", "completed_at": None,
             "start_date": "2026-10-01", "target_date": "2026-11-01", "description_html": "<p>Validar <b>formulario</b> de campañas.</p>", "labels": []},
            {"id": "10000000-0000-4000-8000-000000000002", "sequence_id": 2, "name": "Acortador de enlaces", "priority": "medium",
             "state": s(P1, "Completado"), "created_at": "2026-10-10T09:00:00Z", "updated_at": "2026-10-15T12:00:00Z",
             "completed_at": "2026-10-15T12:00:00Z", "start_date": None, "target_date": None, "description_html": "", "labels": []},
            {"id": "10000000-0000-4000-8000-000000000003", "sequence_id": 3, "name": "Webhook SMS duplicado", "priority": "low",
             "state": s(P1, "Cancelado"), "created_at": "2026-10-05T09:00:00Z", "updated_at": "2026-10-06T12:00:00Z",
             "completed_at": None, "start_date": None, "target_date": None, "description_html": "<p>Sin alcance.</p>", "labels": []},
        ],
        P2: [
            {"id": "20000000-0000-4000-8000-000000000013", "sequence_id": 13, "name": "Tareas Rápidas y Soporte - W43", "priority": "none",
             "state": s(P2, "Progreso"), "created_at": "2026-10-19T09:00:00Z", "updated_at": "2026-10-20T16:00:00Z", "completed_at": None,
             "start_date": "2026-10-19", "target_date": "2026-10-25", "description_html": "", "labels": []},
        ],
    }
    c = lambda cid, actor, created, html: {"id": cid, "actor": actor, "created_by": actor, "created_at": created, "comment_html": html}
    comments = {
        "10000000-0000-4000-8000-000000000001": [
            c("c1000000-0000-4000-8000-000000000001", ME, "2026-10-20T11:05:00Z",
              "<p>Avance del formulario.</p>" + meta_block(date="2026-10-20", start_time="10:00", end_time="11:00", duration_minutes=60,
                                                           notes="Avance del formulario", track="main")),
            c("c1000000-0000-4000-8000-000000000002", ME, "2026-10-20T11:35:00Z",
              "<p>Revisión por subagente.</p>" + meta_block(date="2026-10-20", start_time="10:30", end_time="11:30", duration_minutes=60,
                                                            notes="Revisión", track="subagent", worker_type="agent:claude",
                                                            stoppers=["Esperando credenciales"])),
            c("c1000000-0000-4000-8000-000000000003", OTHER, "2026-10-20T12:05:00Z",
              "<p>Comentario ajeno.</p>" + meta_block(date="2026-10-20", start_time="12:00", end_time="13:00", duration_minutes=60, notes="Ajeno")),
            c("c1000000-0000-4000-8000-000000000004", ME, "2026-10-20T14:00:00Z", "<p>Solo texto, sin telemetría.</p>"),
        ],
        "10000000-0000-4000-8000-000000000002": [
            c("c2000000-0000-4000-8000-000000000005", ME, "2026-10-14T16:05:00Z",
              "<p>Cierre del acortador.</p>" + meta_block(date="2026-10-14", start_time="15:00", end_time="16:00", duration_minutes=60,
                                                          notes="Cierre del acortador", track="main")),
        ],
        "20000000-0000-4000-8000-000000000013": [
            c("c3000000-0000-4000-8000-000000000006", ME, "2026-10-20T10:20:00Z",
              "<p>Soporte.</p>" + meta_block(date="2026-10-20", start_time="09:30", end_time="10:15", duration_minutes=45, notes="Soporte a usuarios",
                                             track="support", capacity_bucket="toil_support")),
        ],
    }
    activities = {
        "10000000-0000-4000-8000-000000000002": [
            {"id": "a0000000-0000-4000-8000-000000000001", "field": "state", "created_at": "2026-10-10T09:00:30Z", "old_identifier": None,
             "new_identifier": s(P1, "Backlog"), "old_value": None, "new_value": "Backlog"},
            {"id": "a0000000-0000-4000-8000-000000000002", "field": "state", "created_at": "2026-10-12T09:00:00Z", "old_identifier": s(P1, "Backlog"),
             "new_identifier": s(P1, "Progreso"), "old_value": "Backlog", "new_value": "Progreso"},
            {"id": "a0000000-0000-4000-8000-000000000003", "field": "state", "created_at": "2026-10-15T12:00:00Z", "old_identifier": s(P1, "Progreso"),
             "new_identifier": s(P1, "Completado"), "old_value": "Progreso", "new_value": "Completado"},
        ],
        "10000000-0000-4000-8000-000000000003": [
            {"id": "a0000000-0000-4000-8000-000000000004", "field": "state", "created_at": "2026-10-06T12:00:00Z", "old_identifier": s(P1, "Backlog"),
             "new_identifier": s(P1, "Cancelado"), "old_value": "Backlog", "new_value": "Cancelado"},
        ],
    }
    labels = {pid: [{"id": f"1b{i}00000-0000-4000-8000-{pid[:12]}", "name": n, "color": col}
                    for i, (n, col) in enumerate([("backend", "#111111"), ("bug", "#d00000"), ("sms", ""), ("frontend", "#00aa55")])]
              for pid in (P1, P2)}
    projects = [{"id": P1, "identifier": "OMNIFY", "name": "Omnify"}, {"id": P2, "identifier": "OPS", "name": "Operaciones"}]
    members = [{"id": ME, "display_name": "tester", "email": "tester@example.com", "first_name": "Test"},
               {"id": OTHER, "display_name": "otro", "email": "otro@example.com", "first_name": "Otro"}]
    attachments = [{"id": "d0000000-0000-4000-8000-000000000001", "created_at": "2026-10-16T10:00:00Z",
                    "attributes": {"name": "informe.pdf", "size": 2048}}]
    return {"projects": projects, "states": states, "issues": issues, "comments": comments, "activities": activities, "labels": labels,
            "members": members, "attachments": attachments, "links": []}


class _NullHandler:
    """Handler mudo: ejecuta la ruta de una escritura sin responder al cliente (commit_drop)."""

    def __init__(self):
        self.wfile = io.BytesIO()

    def send_response(self, status):
        pass

    def send_header(self, *args):
        pass

    def end_headers(self):
        pass


class FakePlane:
    """Servidor Plane mínimo con datos enlatados; registra cada petición recibida."""

    def __init__(self):
        self.data = build_data()
        self.requests = []
        self.fail = []  # [(método, regex de ruta, estado, cuerpo)]
        self.faults = []
        self.store_comments = False
        self.ext_id = True
        self.committed = []
        self.counter = 0
        self.lock = threading.Lock()
        self.closed = False
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def handle_any(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                fake.dispatch(self, raw)

            do_GET = do_POST = do_PATCH = do_DELETE = handle_any

        self.handler_class = Handler
        self.port = 0
        self._listen()

    def _listen(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), self.handler_class)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.closed = False

    def close(self):
        if not self.closed:
            self.server.shutdown()
            self.server.server_close()
            self.closed = True

    def reopen(self):
        if self.closed:
            self._listen()

    def add_fault(self, method, path, kind, arg=None, n=None):
        self.faults.append({"method": method, "path": path, "kind": kind, "arg": arg, "n": n, "hits": 0})

    def clear_faults(self):
        self.faults.clear()

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.port}"

    # ----------------------------------------------------------------------------
    def reply(self, handler, status, payload):
        body = b"" if payload is None else (payload if isinstance(payload, bytes) else json.dumps(payload).encode())
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        if body:
            handler.wfile.write(body)

    def dispatch(self, handler, raw):
        method, path = handler.command, handler.path
        bare = path.split("?")[0]
        is_upload = bare.startswith("/upload")
        text = "<multipart>" if is_upload else raw.decode("utf-8", "replace")
        with self.lock:
            self.requests.append((method, path, text))
        if self._apply_fault(handler, method, bare, text):
            return
        for f_method, f_regex, status, body in self.fail:
            if f_method == method and re.search(f_regex, bare):
                return self.reply(handler, status, body)
        if is_upload:
            return self.reply(handler, 204, None)
        base = f"/api/v1/workspaces/{WS}/"
        if bare == "/api/v1/users/me/":
            return self.reply(handler, 200, {"id": ME})
        if not bare.startswith(base):
            return self.reply(handler, 404, {"detail": "no"})
        rest = bare[len(base):].strip("/").split("/")
        body = json.loads(text) if text and text.startswith("{") else {}
        return self.route(handler, method, rest, body)

    def _apply_fault(self, handler, method, bare, text):
        """True si una regla de fallo atendió la petición (el cliente ya recibió su respuesta o su corte)."""
        for rule in self.faults:
            if rule["method"] not in (method, "*") or not re.search(rule["path"], bare) or (rule["n"] is not None and rule["hits"] >= rule["n"]):
                continue
            rule["hits"] += 1
            kind, arg = rule["kind"], rule["arg"]
            if kind == "flap":
                kind, arg = arg[(rule["hits"] - 1) % len(arg)]
            if kind == "ok":
                return False
            if kind == "status":
                self.reply(handler, arg, {"detail": "injected"})
            elif kind == "raw":
                handler.wfile.write(arg)
                handler.close_connection = True
            elif kind == "hang":
                time.sleep(arg)
                handler.close_connection = True
            elif kind == "drop":
                handler.close_connection = True
                handler.connection.close()
            elif kind == "commit_drop":
                rest = bare[len(f"/api/v1/workspaces/{WS}/"):].strip("/").split("/")
                self.route(_NullHandler(), method, rest, json.loads(text) if text.startswith("{") else {})
                handler.close_connection = True
                handler.connection.close()
            elif kind == "delay":
                time.sleep(arg)
                return False
            else:
                raise ValueError(f"kind de fallo desconocido: {kind}")
            return True
        return False

    def route(self, handler, method, rest, body):
        d = self.data
        if rest == ["projects"]:
            return self.reply(handler, 200, {"results": d["projects"]})
        if rest == ["members"]:
            return self.reply(handler, 200, d["members"])
        if len(rest) < 2 or rest[0] != "projects":
            return self.reply(handler, 404, {"detail": "no"})
        pid, tail = rest[1], rest[2:]
        if tail == ["states"]:
            return self.reply(handler, 200, {"results": d["states"].get(pid, [])})
        if tail == ["labels"]:
            return self.reply(handler, 200, {"results": d["labels"].get(pid, [])})
        if tail == ["issues"]:
            if method == "POST":
                self.counter += 1
                new = {"id": f"99000000-0000-4000-8000-{self.counter:012d}", "sequence_id": 100 + self.counter, "name": body.get("name"),
                       "priority": body.get("priority", "none")}
                return self.reply(handler, 201, new)
            return self.reply(handler, 200, {"results": d["issues"].get(pid, []), "next_page_results": False})
        if len(tail) >= 2 and tail[0] == "issues":
            iid, sub = tail[1], tail[2:]
            issue = next((i for i in d["issues"].get(pid, []) if i["id"] == iid), None)
            if not sub:
                if issue is None:
                    return self.reply(handler, 404, {"detail": "not found"})
                return self.reply(handler, 200, {**issue, **body} if method == "PATCH" else issue)
            return self.issue_child(handler, method, iid, sub, body)
        return self.reply(handler, 404, {"detail": "no"})

    def _post_comment(self, handler, iid, body):
        stored = self.data["comments"].setdefault(iid, [])
        ext = body.get("external_id")
        if self.store_comments and self.ext_id and ext:
            for c in stored:
                if c.get("external_id") == ext and c.get("external_source") == body.get("external_source"):
                    return self.reply(handler, 409, {"error": "same external id", "id": c["id"]})
        self.counter += 1
        new_id = f"c9000000-0000-4000-8000-{self.counter:012d}"
        if not self.store_comments:
            return self.reply(handler, 201, {"id": new_id})
        comment = {"id": new_id, "actor": ME, "created_by": ME, "created_at": "2026-10-30T12:00:00Z", "comment_html": body.get("comment_html", ""),
                   "external_id": ext, "external_source": body.get("external_source")}
        stored.append(comment)
        self.committed.append(new_id)
        return self.reply(handler, 201, comment)

    def issue_child(self, handler, method, iid, sub, body):
        d = self.data
        if sub == ["comments"]:
            if method == "POST":
                return self._post_comment(handler, iid, body)
            return self.reply(handler, 200, {"results": d["comments"].get(iid, [])})
        if len(sub) == 2 and sub[0] == "comments":
            if method == "DELETE":
                return self.reply(handler, 204, None)
            found = next((c for c in d["comments"].get(iid, []) if c["id"] == sub[1]), None)
            if found is None:
                found = {"id": sub[1], "actor": ME, "created_at": "2026-10-20T13:05:00Z", "comment_html": "<p>Comentario sin telemetría.</p>"}
            return self.reply(handler, 200, {**found, **body} if method == "PATCH" else found)
        if sub == ["activities"]:
            return self.reply(handler, 200, {"results": d["activities"].get(iid, []), "next_page_results": False})
        if sub == ["links"]:
            if method == "POST":
                d["links"].append({"url": body.get("url")})
                return self.reply(handler, 201, {"id": "l1"})
            return self.reply(handler, 200, {"results": d["links"]})
        if sub[0] == "issue-attachments":
            if method == "POST" and len(sub) == 1:
                self.counter += 1
                return self.reply(handler, 200, {"asset_id": f"e0000000-0000-4000-8000-{self.counter:012d}",
                                                 "upload_data": {"url": f"{self.base_url}/upload/bucket", "fields": {"key": "k1", "policy": "p1"}}})
            if method == "GET":
                return self.reply(handler, 200, {"results": d["attachments"]})
            return self.reply(handler, 204, None)
        return self.reply(handler, 404, {"detail": "no"})


# ------------------------------------------------------------------------------
# Ejecución aislada
# ------------------------------------------------------------------------------

class Sandbox:
    """HOME temporal + repo git temporal + servidor falso: nada sale de /tmp ni toca el Plane real."""

    def __init__(self, extra_env=None, with_repo=False, with_session=False, fake=None):
        self.tmp = tempfile.TemporaryDirectory(prefix="plane-golden-")
        self.home = os.path.join(self.tmp.name, "home")
        self.work = os.path.join(self.tmp.name, "work")
        os.makedirs(self.home)
        os.makedirs(self.work)
        self.fake = fake or FakePlane()
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        self.dead_port = probe.getsockname()[1]
        probe.close()
        self.dead_url = f"http://127.0.0.1:{self.dead_port}"
        self.last_elapsed = 0.0
        self.env = {"PATH": os.environ.get("PATH", ""), "HOME": self.home, "TZ": "UTC", "LC_ALL": "C.UTF-8", "PYTHONIOENCODING": "utf-8",
                    "PYTHONDONTWRITEBYTECODE": "1", "PLANE_BASE_URL": self.fake.base_url, "PLANE_API_KEY": "dummy",
                    "PLANE_WORKSPACE_SLUG": WS, "PLANE_PROJECT_ID": P1, "PLANE_ACTOR_UUID": ME,
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.path.join(self.tmp.name, "gitconfig")}
        self.env.update(extra_env or {})
        self.env = {k: v for k, v in self.env.items() if v is not None}
        if with_repo:
            self.make_repo()
        if with_session:
            self.make_session()

    def make_repo(self):
        def git(*a):
            subprocess.run(["git", *a], cwd=self.work, env=self.env, check=True, capture_output=True)
        git("init", "-q", "-b", "feat/OMNIFY-1-validaciones")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "Tester")
        with open(os.path.join(self.work, "a.txt"), "w") as handle:
            handle.write("a\n")
        git("add", "a.txt")
        git("commit", "-q", "-m", "init")
        git("remote", "add", "origin", "https://user:secret@github.com/Org/repo.git")
        git("update-ref", "refs/remotes/origin/feat/OMNIFY-1-validaciones", "HEAD")
        git("update-ref", "refs/remotes/origin/main", "HEAD")

    def make_session(self):
        folder = os.path.join(self.home, ".claude", "projects", "-golden")
        os.makedirs(folder)
        stamps = [f"2026-10-20T10:{m:02d}:00.000Z" for m in range(0, 31, 3)] + [f"2026-10-20T14:{m:02d}:00.000Z" for m in range(0, 16, 3)]
        with open(os.path.join(folder, SESSION + ".jsonl"), "w") as handle:
            for stamp in stamps:
                handle.write(json.dumps({"timestamp": stamp, "type": "x"}) + "\n")

    def run(self, args, env_drop=(), env_set=None, stdin="", cwd=None, timeout=60):
        env = {k: v for k, v in self.env.items() if k not in env_drop}
        env.update({k: v.replace("{DEAD}", self.dead_url) for k, v in (env_set or {}).items()})
        started = time.monotonic()
        proc = subprocess.run([sys.executable, PLANE_PY, *args], env=env, cwd=cwd or self.work, input=stdin, capture_output=True,
                              text=True, timeout=timeout)
        self.last_elapsed = time.monotonic() - started
        return proc.returncode, proc.stdout, proc.stderr

    def circuit_path(self):
        return os.path.join(self.home, ".cache", "plane", "circuit.json")

    def write_circuit(self, opened_ago=5, level=0, last_error="refused", since_ago=60, consec=2, **extra):
        """Deja el circuito abierto (opened_ago segundos atrás) o, con opened_ago=None, cerrado con `consec` fallos."""
        now = time.time()
        state = {"consec": consec, "opened_at": None if opened_ago is None else now - opened_ago, "level": level, "probing_until": 0,
                 "last_error": last_error, "since": now - since_ago, "last_ok": None, "skipped": 0, **extra}
        os.makedirs(os.path.dirname(self.circuit_path()), exist_ok=True)
        with open(self.circuit_path(), "w", encoding="utf-8") as handle:
            json.dump(state, handle)

    def circuit_state(self):
        try:
            with open(self.circuit_path(), "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def db_dump(self, query):
        path = os.path.join(self.home, ".cache", "plane", "worklogs.db")
        if not os.path.exists(path):
            return []
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(query)]
        finally:
            conn.close()

    def close(self):
        self.fake.close()
        self.tmp.cleanup()


# ------------------------------------------------------------------------------
# Normalización y golden
# ------------------------------------------------------------------------------

VOLATILE_KEYS = ("date", "start_time", "end_time", "created_at", "updated_at", "edited_at", "ts", "ms", "p50_ms", "p95_ms", "max_ms")
_META_RE = re.compile(r"<!-- PLANE_WORKLOG_METADATA (.*?) -->", re.S)


def _scrub(obj, keys):
    if isinstance(obj, dict):
        return {k: ("<VOLATIL>" if k in keys and v is not None else _scrub(v, keys)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v, keys) for v in obj]
    return obj


def _scrub_body(text, keys):
    """Normaliza los campos no deterministas dentro de un cuerpo JSON y de su bloque de metadata incrustado."""
    try:
        parsed = json.loads(text)
    except ValueError:
        return text

    def fix_html(value):
        def sub(match):
            try:
                meta = _scrub(json.loads(match.group(1)), keys)
            except ValueError:
                return match.group(0)
            return "<!-- PLANE_WORKLOG_METADATA " + json.dumps(meta, sort_keys=True, ensure_ascii=False) + " -->"
        return _META_RE.sub(sub, value)

    if isinstance(parsed, dict) and isinstance(parsed.get("comment_html"), str):
        parsed["comment_html"] = fix_html(parsed["comment_html"])
    return json.dumps(parsed, sort_keys=True, ensure_ascii=False)


def normalize(text, sandbox, scrub=()):
    text = text.replace(str(sandbox.fake.port), "PORT").replace(str(sandbox.dead_port), "DEADPORT").replace(sandbox.tmp.name, "<TMP>")
    text = re.sub(r"\b[0-9a-f]{40}\b", "<SHA>", text)
    text = re.sub(r"\b(group\W+|grupo |pendiente )[0-9a-f]{8}\b", r"\1<GRP>", text)
    if scrub:
        # Las marcas completas de tiempo se limpian ANTES de sustituir la fecha de hoy: si no, según la hora
        # del día la fecha local coincide con la UTC y la marca queda como "<HOY> hh:mm:ss".
        text = re.sub(r"\b20\d\d-\d\d-\d\d \d\d:\d\d:\d\d\b", "<TS>", text)
    now = datetime.now()
    text = text.replace(now.strftime("%Y-%m-%d"), "<HOY>").replace(now.strftime("%d/%m/%Y"), "<HOY>")
    text = re.sub(r"desde las \d\d:\d\d", "desde las <HH:MM>", text)
    text = re.sub(r"abierto desde hace [\d.]+ (días|min|h)", "abierto desde hace <N> \\1", text)
    if scrub:
        text = re.sub(r'(\d+) ms\b', "<N> ms", text)
        text = re.sub(r'"(%s)": (?:"[^"]*"|[\d.]+)' % "|".join(scrub), r'"\1": "<VOLATIL>"', text)
    return text


def run_scenario(name, steps, *, sandbox_kwargs=None, scrub=(), sort_requests=False, db_queries=(), setup=None, files=None):
    """steps: lista de dicts {args, env_drop, stdin, cwd}. Devuelve el texto golden normalizado."""
    sb = Sandbox(**(sandbox_kwargs or {}))
    try:
        for rel, content in (files or {}).items():
            with open(os.path.join(sb.work, rel), "w", encoding="utf-8") as handle:
                handle.write(content)
        if setup:
            setup(sb)
        out = []
        for step in steps:
            step = {"args": step} if isinstance(step, (list, tuple)) else step
            code, stdout, stderr = sb.run(step["args"], env_drop=step.get("env_drop", ()), env_set=step.get("env_set"),
                                          stdin=step.get("stdin", ""), cwd=step.get("cwd"))
            out += [f"$ plane.py {' '.join(step['args'])}" + (f"   [sin {','.join(step['env_drop'])}]" if step.get("env_drop") else ""),
                    f"[exit {code}]", "--- stdout ---", stdout.rstrip("\n"), "--- stderr ---", stderr.rstrip("\n"), ""]
        reqs = [f"{m} {p} {_scrub_body(b, scrub) if b else ''}".rstrip() for m, p, b in sb.fake.requests]
        if sort_requests:
            reqs.sort()
        out += ["=== peticiones al servidor ===", *reqs]
        for label, query, cols in db_queries:
            out += ["", f"=== {label} ==="]
            for row in sb.db_dump(query):
                row = {k: v for k, v in row.items() if k in cols} if cols else row
                if "raw_payload" in row and row["raw_payload"]:
                    row["raw_payload"] = _scrub(json.loads(row["raw_payload"]), scrub)
                out.append(json.dumps(_scrub(row, scrub), sort_keys=True, ensure_ascii=False))
        return normalize("\n".join(out) + "\n", sb, scrub)
    finally:
        sb.close()


def check_golden(testcase, name, actual):
    path = os.path.join(GOLDEN_DIR, name + ".txt")
    if os.environ.get("GOLDEN_UPDATE") == "1":
        os.makedirs(GOLDEN_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(actual)
        return
    if not os.path.exists(path):
        testcase.fail(f"falta el golden {path} (genéralo con GOLDEN_UPDATE=1 contra la línea base)")
    with open(path, "r", encoding="utf-8") as handle:
        expected = handle.read()
    testcase.assertEqual(actual, expected, f"la salida de '{name}' difiere del golden")
