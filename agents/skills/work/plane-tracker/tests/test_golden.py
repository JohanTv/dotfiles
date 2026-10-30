"""Caracterización del CLI: la salida (stdout/stderr), el código de salida, las peticiones enviadas y las filas
locales deben coincidir con los golden generados contra la línea base. Todo corre contra un Plane falso con HOME
temporal; ver golden_support.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import golden_support as gs  # noqa: E402

ROOT_COMMANDS = ["search", "get", "list", "create", "update", "report", "handoff", "labels", "projects", "whoami", "health"]
GROUPS = {"comment": ("add", "edit", "delete"), "attachment": ("add", "list", "delete", "replace"), "link": ("add",), "outbox": ("list", "flush", "drop"),
          "focus": ("set", "clear", "status"), "worklog": ("propose", "check")}
HELP_PATHS = ([[c] for c in ROOT_COMMANDS] + [[g] for g in GROUPS] + [[g, v] for g, verbs in GROUPS.items() for v in verbs])
NO_ENV = ("PLANE_BASE_URL", "PLANE_API_KEY", "PLANE_WORKSPACE_SLUG", "PLANE_PROJECT_ID", "PLANE_ACTOR_UUID")
WORKLOG_COLS = ("ticket_id", "track", "date", "start_time", "end_time", "duration_minutes", "plane_comment_id", "project_id", "issue_name",
                "worker_type", "capacity_bucket", "phase", "role", "notes", "stoppers_json", "raw_payload", "created_at")
WORKLOGS = ("worklogs", "SELECT * FROM worklogs ORDER BY ticket_id, track, duration_minutes, notes, date", WORKLOG_COLS)
NOW_FIELDS = ("date", "start_time", "end_time", "created_at", "edited_at", "updated_at", "client_id", "external_id")
STAMPS = ("created_at", "edited_at", "updated_at")
SESS = ["--agent", "claude", "--session", gs.SESSION]
CID1 = "c1000000-0000-4000-8000-000000000001"
CID4 = "c1000000-0000-4000-8000-000000000004"
ATT = "d0000000-0000-4000-8000-000000000001"
OFFLINE = {"PLANE_OFFLINE": "1"}


class Golden(unittest.TestCase):
    def golden(self, name, steps, **kwargs):
        check = gs.run_scenario(name, steps, **kwargs)
        gs.check_golden(self, name, check)

    # --- ayuda y errores ------------------------------------------------------
    def test_help(self):
        steps = [{"args": ["--help"], "env_drop": NO_ENV}] + [{"args": [*path, "--help"], "env_drop": NO_ENV} for path in HELP_PATHS]
        self.golden("help", steps)

    def test_errors_env_and_parser(self):
        steps = [
            {"args": ["list"], "env_drop": ("PLANE_BASE_URL",)},
            {"args": ["list"], "env_drop": ("PLANE_API_KEY",)},
            {"args": ["health"], "env_drop": ("PLANE_BASE_URL", "PLANE_API_KEY")},
            {"args": ["bogus"]},
            {"args": []},
            {"args": ["get", "--last", "0", "OMNIFY-1"]},
            {"args": ["health", "--hours", "x"]},
            {"args": ["comment", "add", "OMNIFY-1", "--capacity", "nada"]},
            {"args": ["report", "--today", "--week"]},
            {"args": ["get", "X1"]},
            {"args": ["get", "OTRO-5"]},
            {"args": ["list"], "env_set": {"PLANE_BASE_URL": "{DEAD}"}},
            {"args": ["attachment", "list", "10000000-0000-4000-8000-000000000001"], "env_set": {"PLANE_BASE_URL": "{DEAD}"}},
            {"args": ["attachment", "list", "10000000-0000-4000-8000-000000000001"], "env_set": {"PLANE_OFFLINE": "1"}},
            {"args": ["comment", "OMNIFY-1", "-m", "x"], "env_drop": NO_ENV},
            {"args": ["comment-edit", "OMNIFY-1", "-m", "x"], "env_drop": NO_ENV},
            {"args": ["--json", "attachments", "OMNIFY-1"], "env_drop": NO_ENV},
            {"args": ["attach", "OMNIFY-1", "adj.txt", "--replace", "x"], "env_drop": NO_ENV},
            {"args": ["focus", "--agent", "claude", "--off"], "env_drop": NO_ENV},
            {"args": ["report", "--flow", "--sync"], "env_drop": NO_ENV},
            {"args": ["comment", "rm", "OMNIFY-1"], "env_drop": NO_ENV},
            {"args": ["atachment", "list", "OMNIFY-1"], "env_drop": NO_ENV},
            {"args": ["outbox"], "env_drop": NO_ENV},
            {"args": ["outbox", "sync"], "env_drop": NO_ENV},
            {"args": ["outbox", "drop", "x"], "env_drop": NO_ENV},
        ]
        self.golden("errors_env_and_parser", steps)

    def test_errors_http(self):
        def setup(sb):
            sb.fake.fail = [("GET", r"/projects/%s/issues/$" % gs.P1, 500, {"detail": "boom"}),
                            ("GET", r"/projects/%s/labels/$" % gs.P1, 404, {"detail": "nada"}),
                            ("POST", r"/comments/$", 400, {"detail": "malo"}),
                            ("GET", r"/projects/%s/states/$" % gs.P2, 403, {"detail": "prohibido"})]
        steps = [["list"], ["labels"], ["search", "formulario"], ["get", "OMNIFY-1"], ["get", "OPS-13"],
                 ["comment", "add", "OPS-13", "-m", "hola", "--duration", "5"]]
        self.golden("errors_http", steps, setup=setup, scrub=NOW_FIELDS)

    # --- lectura --------------------------------------------------------------
    def test_get(self):
        steps = [["get", "OMNIFY-1"], ["get", "OMNIFY-1", "--json"], ["--json", "get", "OMNIFY-1"], ["get", "OMNIFY-1", "--no-comments", "--no-description"],
                 ["get", "OMNIFY-1", "--last", "2", "--full"], ["get", "OMNIFY-2", "--history"], ["get", "OMNIFY-3", "--history", "--json"],
                 ["get", "1"], ["get", "OPS-13"], ["get", "OMNIFY-999"], ["get", "10000000-0000-4000-8000-000000000002", "--json"],
                 ["get"], ["get", "@"]]
        self.golden("get", steps, sandbox_kwargs={"with_repo": True})

    def test_get_outside_repo(self):
        self.golden("get_no_ticket", [{"args": ["get"], "cwd": "/"}])

    def test_list_search_labels_projects(self):
        steps = [["list"], ["list", "--json"], ["--json", "list"], ["list", "-p", "OPS"], ["list", "-p", "nope"],
                 ["search", "formulario"], ["search", "3"], ["search", "OMNIFY-2"], ["search", "zzz"], ["search", "validaciones", "--json", "-p", "OMNIFY"],
                 ["search", "x", "-p", "NOPE"], ["search", "de la", "--refresh"], ["search", "soporte", "-p", "OPS"],
                 ["labels"], ["labels", "--json", "-p", "OPS", "--refresh"], ["labels", "-p", "NOPE"],
                 ["projects"], ["projects", "--json", "--refresh"]]
        self.golden("read_list_search_labels_projects", steps)

    def test_whoami(self):
        steps = [["whoami"],
                 {"args": ["whoami"], "env_drop": ("PLANE_ACTOR_UUID",)},
                 {"args": ["whoami"], "env_drop": ("PLANE_ACTOR_UUID",), "env_set": {"PLANE_USERNAME": "tester"}},
                 {"args": ["whoami"], "env_drop": ("PLANE_ACTOR_UUID",), "env_set": {"PLANE_USERNAME": "nadie"}}]
        self.golden("whoami", steps)

    # --- reportes -------------------------------------------------------------
    def test_report(self):
        steps = [["report", "--date", "2026-10-20"], ["report", "--date", "2026-10-20", "--json"], ["--json", "report", "--date", "2026-10-20"],
                 ["report", "--date", "2026-10-20", "--track", "subagent"], ["report", "--date", "2026-10-20", "--worker-type", "human"],
                 ["report", "--date", "2026-10-20", "-p", "OPS"], ["report", "--date", "2026-10-20", "-p", "OPS", "--json"],
                 ["report", "--date", "bad"], ["worklog", "check", "--date", "2026-10-20"], ["worklog", "check", "--date", "2026-10-20", "--json"],
                 ["report", "--date", "2026-01-01"], ["report", "--date", "2026-10-20", "--refresh"]]
        self.golden("report", steps, scrub=("updated_at",), sort_requests=True, db_queries=[WORKLOGS])

    def test_report_week_header(self):
        self.golden("report_noactor", [{"args": ["report", "--date", "2026-10-20"], "env_drop": ("PLANE_ACTOR_UUID",)}],
                    scrub=("updated_at",), sort_requests=True, db_queries=[WORKLOGS])

    def test_report_flow(self):
        steps = [["report", "--date", "2026-10-14", "--refresh"], ["report", "flow", "--date", "2026-10-14"],
                 ["report", "flow", "--date", "2026-10-14", "--json"], ["worklog", "check", "--date", "2026-10-14"],
                 ["report", "flow", "--date", "2026-10-14", "-p", "OPS"], ["report", "flow", "--date", "2026-10-14", "--refresh"]]
        self.golden("report_flow", steps, scrub=("updated_at",), sort_requests=True)

    # --- escritura ------------------------------------------------------------
    def test_comment(self):
        steps = [["comment", "add", "OMNIFY-1", "-m", "**Hola** mundo\n\n- uno\n- dos", "--duration", "15", "--track", "t1", "--capacity", "tooling_dx"],
                 ["comment", "add", "OMNIFY-1", "-m", "mismo minuto", "--duration", "15", "--track", "t1", "--capacity", "tooling_dx", "--json"],
                 ["comment", "add", "OPS-13", "-f", "cuerpo.md", "--duration", "5", "--worker-type", "agent:claude", "--session", gs.SESSION, "--json"],
                 {"args": ["comment", "add", "OMNIFY-2", "--duration", "7"], "stdin": "Desde stdin"},
                 ["comment", "add", "OMNIFY-1", "-m", "<p>Ya es <b>HTML</b></p>", "--duration", "3"],
                 ["comment", "add", "OMNIFY-1", "-m", "Con metadata\n<!-- PLANE_WORKLOG_METADATA {\"date\": \"2026-10-21\", \"start_time\": \"08:00\", "
                  "\"duration_minutes\": 20, \"notes\": \"meta\", \"track\": \"mm\"} -->"],
                 ["comment", "add", "OMNIFY-1", "-m", "x", "--duration", "0"], ["comment", "add", "OMNIFY-1", "-m", "x", "--duration", "9999"],
                 ["comment", "add", "OMNIFY-1", "-m", "   "], ["comment", "add", "OMNIFY-1", "-m", "Pendiente [COMPLETAR]", "--duration", "5"],
                 ["comment", "add", "OMNIFY-1", "-m", "sin duración", "--capacity", "toil_support", *SESS],
                 ["comment", "add", "OMNIFY-1", "-m", "sin duración", "--accept-proposal", *SESS],
                 ["comment", "add", "OMNIFY-1", "-m", "sin duración", "--capacity", "coordination", "--accept-proposal"],
                 ["comment", "add", "OMNIFY-1", "-m", "sin duración", *SESS],
                 ["comment", "add", "OMNIFY-999", "-m", "x", "--duration", "5"]]
        self.golden("comment", steps, files={"cuerpo.md": "# Título\n\nTexto con `código` y [enlace](https://x.example)\n"},
                    scrub=NOW_FIELDS, db_queries=[WORKLOGS], sandbox_kwargs={"with_session": True})

    def test_outbox(self):
        def setup(sb):
            sb.fake.store_comments = True
            sb.fake.add_fault("POST", r"/comments/$", "commit_drop", n=1)
        block = '<!-- PLANE_WORKLOG_METADATA {"date": "2026-10-21", "start_time": "%s", "duration_minutes": 20, "notes": "n", "track": "mm"} -->'
        add = lambda text, start, *extra: {"args": ["comment", "add", "OMNIFY-1", "-m", f"<p>{text}</p>" + block % start, *extra], "env_set": OFFLINE}
        steps = [["projects"], add("Primero", "08:00"), add("Segundo", "08:30", "--json"), add("Duplicado", "08:00"),
                 ["outbox", "list"], ["outbox", "list", "--json"], ["labels"],
                 ["outbox", "drop", "1"], ["outbox", "drop", "1"], ["outbox", "drop", "42"],
                 {"args": ["outbox", "flush"], "env_set": OFFLINE},
                 ["outbox", "flush", "--json"], ["outbox", "drop", "2"], ["outbox", "flush"],
                 add("Tercero", "09:00"), ["outbox", "drop", "3", "--keep-worklog", "--json"], add("Cuarto", "09:30"), ["outbox", "flush"],
                 ["outbox", "list", "--all"], ["outbox", "flush"],
                 ["outbox", "drop"], ["outbox"], ["health"]]
        queue = ("outbox", "SELECT * FROM outbox ORDER BY id", ("id", "client_id", "ticket_ref", "state", "attempts", "maybe_delivered", "last_error",
                                                                   "plane_comment_id", "wl_ticket_id", "wl_track", "wl_date", "wl_start_time"))
        self.golden("outbox", steps, setup=setup, scrub=NOW_FIELDS, db_queries=[queue, WORKLOGS])

    def test_proposals(self):
        steps = [["worklog", "propose", "OMNIFY-1", *SESS, "--date", "2026-10-20"],
                 ["worklog", "propose", "OMNIFY-1", *SESS, "--date", "2026-10-20", "--json"],
                 ["worklog", "propose", "OMNIFY-1", *SESS, "--date", "2026-10-20", "--since", "10:00", "--until", "10:20"],
                 ["worklog", "propose", "OMNIFY-1", *SESS, "--date", "2026-10-20", "--since", "25:00"],
                 ["worklog", "propose", "OPS-13", "--capacity", "toil_support", *SESS],
                 ["worklog", "propose", "OMNIFY-1", *SESS, "--date", "2999-01-01"],
                 ["worklog", "propose", "OMNIFY-1", *SESS, "--date", "mal"],
                 ["worklog", "propose", "OMNIFY-1", "--agent", "claude", "--session", "no-existe", "--date", "2026-10-20"],
                 ["worklog", "propose", "OMNIFY-1", *SESS, "--date", "2026-10-20"],
                 ["comment", "add", "OMNIFY-1", "-m", "Aceptada", "--accept-proposal", *SESS],
                 ["comment", "add", "OMNIFY-1", "-m", "Otra vez", "--accept-proposal", *SESS],
                 ["comment", "add", "OMNIFY-1", "-m", "Se propone", *SESS]]
        self.golden("proposals", steps, scrub=STAMPS, db_queries=[WORKLOGS], sandbox_kwargs={"with_session": True})

    def test_split(self):
        steps = [["worklog", "propose", "--split", "OMNIFY-1=50%,OPS-13=rest", *SESS, "--date", "2026-10-20"],
                 ["worklog", "propose", "--split", "OMNIFY-1=50%,OPS-13=rest", *SESS, "--date", "2026-10-20", "--json"],
                 ["worklog", "propose", "--split", "OMNIFY-1=10m,OPS-999=rest", *SESS, "--date", "2026-10-20"],
                 ["worklog", "propose", "--split", "A=hola", *SESS, "--date", "2026-10-20"],
                 ["worklog", "propose", "--split", "OMNIFY-1=50%,OPS-13=rest", *SESS, "--date", "2026-10-20"],
                 ["comment", "add", "OMNIFY-1", "-m", "Parte uno", "--accept-proposal", *SESS],
                 ["comment", "add", "OPS-13", "-m", "Parte dos", "--accept-proposal", *SESS],
                 ["comment", "add", "OPS-13", "-m", "Sin reparto", *SESS]]
        self.golden("split", steps, scrub=STAMPS, db_queries=[WORKLOGS], sandbox_kwargs={"with_session": True})

    def test_comment_edit_delete(self):
        steps = [["comment", "delete", "OMNIFY-1", "--comment-id", CID1],
                 ["comment", "delete", "OMNIFY-1"],
                 ["comment", "delete", "OMNIFY-3"],
                 ["comment", "edit", "OMNIFY-1", "--comment-id", CID1, "-m", "Texto **nuevo**"],
                 ["comment", "edit", "OMNIFY-1", "--comment-id", CID4, "-m", "<p>HTML nuevo</p>"],
                 ["comment", "edit", "OMNIFY-1", "--comment-id", CID4, "-m", "Pendiente [COMPLETAR]"],
                 ["comment", "edit", "OMNIFY-1", "--comment-id", CID4, "--duration", "30", "--track", "rev", "--capacity", "research_rd", "--worker-type", "subagent"],
                 ["comment", "edit", "OMNIFY-1", "--comment-id", CID4, "--embed-metadata"],
                 ["comment", "edit", "OMNIFY-1", "--comment-id", CID1, "--embed-metadata"],
                 ["comment", "edit", "OMNIFY-1", "--comment-id", CID1, "--duration", "45", "--track", "otro"],
                 ["comment", "edit", "OMNIFY-1", "--comment-id", "c1000000-0000-4000-8000-0000000000ff", "--embed-metadata"],
                 ["comment", "edit", "OMNIFY-1", "--comment-id", CID4],
                 ["comment", "edit", "OMNIFY-1", "--duration", "10"],
                 ["comment", "delete", "OMNIFY-1", "--comment-id", CID4]]
        self.golden("comment_edit_delete", steps, scrub=STAMPS, db_queries=[WORKLOGS])

    def test_update_create_link(self):
        steps = [["update", "OMNIFY-1", "--state", "Revisión", "--priority", "HIGH", "--labels", "backend,nope,BUG", "--start-date", "2026-10-01", "--due-date", "2026-11-01"],
                 ["update", "OMNIFY-1", "--state", "completado", "--json"],
                 ["update", "OMNIFY-1", "--state", "inexistente"], ["update", "OMNIFY-1", "--priority", "enorme"],
                 ["update", "OMNIFY-1", "--due-date", "31/12/2026"], ["update", "OMNIFY-1"],
                 ["update", "1", "--labels", "sms"],
                 ["create", "[FIX] Corregir validación del campo teléfono en formularios de campaña", "-d", "Texto **md**\n\n1. uno\n2. dos",
                  "-p", "OPS", "--priority", "urgent", "--state", "Pendiente", "--labels", "backend,bug,zzz", "--start-date", "2026-10-26", "--due-date", "2026-11-01"],
                 ["create", "[QA] Probar flujo", "--json", "--attach", "adj.txt"],
                 ["create", "Sin fase", "-d", "<p>ya html</p>"],
                 ["create", "[RFC] Algo", "-p", "nope"], ["create", "[FEAT] Algo", "--state", "nope"], ["create", "[FEAT] Algo", "--attach", "no-existe.txt"],
                 ["link", "add", "OMNIFY-1", "https://example.com/pr/1", "--title", "PR 1"], ["link", "add", "OMNIFY-1", "https://example.com/pr/1"],
                 ["link", "add", "OMNIFY-1", "ftp://mal"], ["link", "add", "OMNIFY-1", "https://example.com/doc"]]
        self.golden("update_create_link", steps, files={"adj.txt": "hola adjunto\n"}, sort_requests=False)

    def test_attachments(self):
        steps = [["attachment", "add", "OMNIFY-1", "adj.txt"], ["attachment", "add", "OMNIFY-1", "adj.txt", "adj.txt"],
                 ["attachment", "add", "OMNIFY-1", "no-existe.bin"],
                 ["attachment", "replace", "OMNIFY-1", ATT, "adj.txt"], ["attachment", "replace", "OMNIFY-1", "x", "adj.txt"],
                 ["attachment", "replace", "OMNIFY-1", ATT, "no-existe.bin"],
                 ["attachment", "list", "OMNIFY-1"], ["attachment", "list", "OMNIFY-1", "--json"], ["--json", "attachment", "list", "OMNIFY-1"],
                 ["attachment", "delete", "OMNIFY-1", ATT], ["attachment", "delete", "OMNIFY-1", "no-es-uuid"], ["attachment", "delete", "OMNIFY-1"],
                 ["attachment"]]
        self.golden("attachments", steps, files={"adj.txt": "hola adjunto\n"})

    # --- operación ------------------------------------------------------------
    def test_health(self):
        def setup(sb):
            sb.fake.fail = [("GET", r"/projects/%s/issues/$" % gs.P2, 503, {"detail": "caído"})]
        steps = [["projects"], ["list"], ["list", "-p", "OPS"], ["health"], ["health", "--json"], ["health", "--hours", "1"]]
        self.golden("health", steps, setup=setup, scrub=("ts", "ms", "p50_ms", "p95_ms", "max_ms", "last_ok"))

    def test_handoff(self):
        steps = [["handoff"], ["handoff", "OMNIFY-9", "--base", "main"], ["handoff", "--base", "nope"], ["handoff", "--base", "--evil"],
                 {"args": ["handoff"], "cwd": "/"}]
        self.golden("handoff", steps, sandbox_kwargs={"with_repo": True})

    def test_handoff_states(self):
        def setup(sb):
            with open(os.path.join(sb.work, "sucio.txt"), "w") as handle:
                handle.write("x")
        self.golden("handoff_dirty", [["handoff", "--base", "main"]], sandbox_kwargs={"with_repo": True}, setup=setup)

    def test_focus(self):
        steps = [["focus", "status", *SESS], ["focus", "status", "--json", *SESS], ["--json", "focus", "status", *SESS],
                 ["focus", "clear", *SESS],
                 ["focus", "set", "OMNIFY-1", *SESS], ["focus", "set", "OMNIFY-1", *SESS], ["focus", "set", "OPS-13", *SESS],
                 ["focus", "set", "OMNIFY-2", *SESS],
                 ["focus", "clear", *SESS], ["focus", "clear", *SESS],
                 ["focus", "set", *SESS], ["focus", "set", "OMNIFY-1"], ["focus", "set", "OMNIFY-1", "--agent", "claude", "--session", "no-existe"],
                 ["focus", "clear", "--agent", "claude", "--session", "no-existe"], ["focus", "status", "--agent", "claude", "--session", "no-existe"],
                 ["focus"]]
        # Una marca abierta y cerrada en segundos distintos deja un intervalo de 1 s sin actividad de sesión: aparece como
        # "0 min atribuidos" según el reloj de pared, así que esa línea no se compara.
        self.golden("focus", steps, sandbox_kwargs={"with_session": True}, drop=(r"^   • \S+\s+0 min atribuidos\n",))


if __name__ == "__main__":
    unittest.main()
