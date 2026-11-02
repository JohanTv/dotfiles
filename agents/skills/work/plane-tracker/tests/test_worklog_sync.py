"""Sincronización de horas (defectos 0017, 0010 y 0022): proyectos accesibles, paginación, presupuesto de tasa, marcas por proyecto y periodo, y nada inventado."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402

P3, P4 = "33333333-3333-4333-8333-333333333333", "44444444-4444-4444-8444-444444444444"
DAY = "2026-10-20"
OFFLINE = {"PLANE_OFFLINE": "1"}


def block(**meta):
    return "<!-- PLANE_WORKLOG_METADATA " + json.dumps(meta, sort_keys=True) + " -->"


def add_project(fake, pid, ident, **extra):
    fake.data["projects"].append({"id": pid, "identifier": ident, "name": ident.title(), **extra})
    fake.data["states"][pid] = list(fake.data["states"][gs.P1])
    fake.data["labels"][pid] = []
    fake.data["issues"][pid] = []


def add_issue(fake, pid, seq, comments, updated="2026-10-20T15:00:00Z", state=None):
    iid = f"{pid[:2]}0000{seq:02d}-0000-4000-8000-{pid[:12]}"
    fake.data["issues"][pid].append({"id": iid, "sequence_id": seq, "name": f"Ticket {seq}", "priority": "low", "state": state or fake.data["states"][pid][0]["id"],
                                     "created_at": "2026-10-01T10:00:00Z", "updated_at": updated, "completed_at": None, "start_date": None, "target_date": None,
                                     "description_html": "", "labels": [], "assignees": [], "created_by": gs.ME, "updated_by": None})
    fake.data["comments"][iid] = [{"id": f"c{pid[:2]}{seq:05d}-0000-4000-8000-{k:012d}", "actor": gs.ME, "created_by": gs.ME, "created_at": "2026-10-20T16:00:00Z",
                                   "comment_html": "<p>x</p>" + html} for k, html in enumerate(comments)]
    return iid


def full(start, **extra):
    return block(date=DAY, start_time=start, end_time=f"{int(start[:2]) + 1:02d}:00", duration_minutes=60, notes="n", track="main", phase="dev", role="backend_engineer",
                 capacity_bucket="deep_work", worker_type="human", **extra)


class Base(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)
        self.fake = self.sb.fake

    def cli(self, *args, code=0, **kwargs):
        got, out, err = self.sb.run(list(args), **kwargs)
        self.assertNotIn("Traceback", err)
        self.assertEqual(got, code, err + out)
        return out, err

    def rows(self, sql):
        return self.sb.db_dump(sql)

    def paths(self, mark=0):
        return [p for _m, p, _b in self.fake.requests[mark:]]


class Coverage(Base):
    """0017: todos los proyectos accesibles, paginación real (la API ignora `limit`) y presupuesto de tasa."""

    def test_more_than_15_tickets_and_a_project_outside_the_old_fixed_list_are_rebuilt_in_full(self):
        for seq in range(10, 32):  # 22 tickets con registros: el listado antiguo (limit=15) no habría llegado
            add_issue(self.fake, gs.P1, seq, [full(f"{8 + seq % 10:02d}:{seq % 6 * 10:02d}", client=str(seq))])
        add_project(self.fake, P3, "LAB")
        add_issue(self.fake, P3, 1, [full("07:00")])
        self.fake.data["issues_page_size"] = 7  # fuerza varias páginas por proyecto
        mark = len(self.fake.requests)
        self.cli("report", "time", "--from", DAY, "--refresh")
        tickets = {r["ticket_id"] for r in self.rows("SELECT ticket_id FROM worklogs")}
        self.assertTrue({f"OMNIFY-{n}" for n in range(10, 32)} <= tickets, "los 22 tickets se sincronizaron, no solo los 15 más recientes")
        self.assertIn("LAB-1", tickets, "un proyecto fuera de la lista fija se sincroniza igual")
        issue_urls = [p for p in self.paths(mark) if p.split("?")[0].endswith("/issues/")]
        self.assertTrue(all("per_page=100" in p and "order_by=-updated_at" in p and "limit=" not in p for p in issue_urls))
        self.assertGreater(len([p for p in issue_urls if "cursor=" in p]), 2, "se siguieron las páginas")
        self.assertEqual({(r["project_ident"], r["complete"]) for r in self.rows("SELECT * FROM worklog_sync")}, {("OMNIFY", 1), ("OPS", 1), ("LAB", 1)})

    def test_inaccessible_projects_are_not_queried(self):
        add_project(self.fake, P3, "HID", is_member=False)
        add_project(self.fake, P4, "OLD", archived_at="2026-01-01T00:00:00Z")
        self.cli("report", "time", "--from", DAY, "--refresh")
        self.assertFalse([p for p in self.paths() if P3 in p or P4 in p])
        self.assertEqual({r["project_ident"] for r in self.rows("SELECT project_ident FROM worklog_sync")}, {"OMNIFY", "OPS"})

    def test_a_project_filter_must_be_an_accessible_project(self):
        out, err = self.cli("report", "time", "--from", DAY, "-p", "NOPE", "--json", code=1)
        self.assertEqual(json.loads(out)["code"], "unknown_project")

    def test_the_rate_budget_stops_the_sync_and_marks_it_incomplete(self):
        self.fake.extra_headers = {"X-RateLimit-Remaining": "2", "X-RateLimit-Reset": "1793620800"}
        out, err = self.cli("report", "time", "--from", DAY, "--refresh", "--json")
        self.assertIn("Sincronización parcial", err)
        doc = json.loads(out)
        self.assertEqual((doc["coverage"]["complete"], doc["coverage"]["detail"]["hours_verified"]), (False, False), "el reporte no se presenta como completo")
        self.assertIn("hours_local_only", [n["code"] for n in doc["notes"]])
        self.assertFalse([p for p in self.paths() if "/comments/" in p], "no se gastó el presupuesto en comentarios")
        self.assertEqual({r["complete"] for r in self.rows("SELECT complete FROM worklog_sync")}, {0})

    def test_a_sync_cut_by_the_budget_advances_on_every_run_and_converges(self):
        for seq in range(10, 22):  # 12 tickets nuevos + los 2 del servidor con actividad = 14 lecturas de comentarios
            add_issue(self.fake, gs.P1, seq, [full(f"{8 + seq % 10:02d}:00", client=str(seq))])
        self.fake.rate_budget = 12  # con la reserva, unas 6 lecturas de comentarios por ventana
        runs, seen = 0, []
        while True:
            runs += 1
            self.fake.new_window()
            self.cli("report", "time", "--from", DAY)
            marks = {r["project_ident"]: r["complete"] for r in self.rows("SELECT * FROM worklog_sync")}
            seen.append(len(self.rows("SELECT 1 FROM worklog_issue_sync")))
            if marks and all(marks.values()):
                break
            self.assertLess(runs, 8, "no converge")
        self.assertGreater(runs, 1, "el presupuesto no alcanzaba en una sola ejecución")
        self.assertEqual(seen, sorted(seen), "cada ejecución avanza, no vuelve a empezar")
        self.assertEqual(len({r["ticket_id"] for r in self.rows("SELECT ticket_id FROM worklogs WHERE ticket_id LIKE 'OMNIFY-1_' OR ticket_id LIKE 'OMNIFY-2_'")}), 12)

    def test_only_what_changed_is_read_again_and_refresh_reads_everything(self):
        add_issue(self.fake, gs.P1, 10, [full("08:00")])
        self.cli("report", "time", "--from", DAY)
        self.sb.advance(10 * 60)
        mark = len(self.fake.requests)
        self.cli("report", "time", "--from", DAY)
        self.assertFalse([p for p in self.paths(mark) if "/comments/" in p], "los tickets sin cambios no se vuelven a pedir")
        issue = self.fake.data["issues"][gs.P1][-1]
        issue["updated_at"] = "2026-10-21T09:00:00Z"
        self.sb.advance(10 * 60)
        mark = len(self.fake.requests)
        self.cli("report", "time", "--from", DAY)
        self.assertEqual([p for p in self.paths(mark) if "/comments/" in p], [f"/api/v1/workspaces/ws/projects/{gs.P1}/issues/{issue['id']}/comments/"])
        mark = len(self.fake.requests)
        self.cli("report", "time", "--from", DAY, "--refresh")
        self.assertGreater(len([p for p in self.paths(mark) if "/comments/" in p]), 1, "--refresh vuelve a leerlo todo")

    def test_a_failed_comment_read_leaves_that_project_incomplete(self):
        self.fake.fail = [("GET", r"/issues/%s/comments/$" % "10000000-0000-4000-8000-000000000001", 404, {"detail": "no"})]
        self.cli("report", "time", "--from", DAY, "--refresh")
        marks = {r["project_ident"]: r["complete"] for r in self.rows("SELECT * FROM worklog_sync")}
        self.assertEqual((marks["OMNIFY"], marks["OPS"]), (0, 1))


class Freshness(Base):
    """0010: se sincroniza por proyecto y periodo, no porque falte algún registro local."""

    def test_one_local_record_does_not_hide_the_remote_ones_of_the_week(self):
        self.cli("comment", "add", "OMNIFY-1", "-m", "<p>local</p>" + block(date=DAY, start_time="18:00", end_time="19:00", duration_minutes=60, notes="local", track="loc"),
                 env_set=OFFLINE)
        self.assertEqual(len(self.rows("SELECT 1 FROM worklogs")), 1)
        out, err = self.cli("report", "time", "--from", DAY)  # sin --refresh
        self.assertGreater(len(self.rows("SELECT 1 FROM worklogs")), 1, "los registros remotos aparecen sin necesidad de --refresh")
        self.assertIn("Avance del formulario", out)

    def test_a_fresh_complete_sync_is_not_repeated_until_the_cooldown_expires(self):
        self.cli("report", "time", "--from", DAY)
        mark = len(self.fake.requests)
        out, err = self.cli("report", "time", "--from", DAY)
        self.assertEqual(self.fake.requests[mark:], [], "dentro del enfriamiento no hay red")
        self.assertNotIn("⚠", err)
        self.sb.advance(10 * 60)
        self.cli("report", "time", "--from", DAY)
        self.assertTrue([p for p in self.paths(mark) if "/issues/?" in p], "pasado el enfriamiento se vuelve a comparar con Plane (listado de tickets)")
        self.assertFalse([p for p in self.paths(mark) if "/comments/" in p], "pero los comentarios de lo que no cambió no se releen")

    def test_without_plane_the_report_says_the_period_was_never_synced(self):
        out, err = self.cli("report", "time", "--from", DAY, env_set=OFFLINE)
        self.assertEqual(err, "")
        self.assertIn("Las horas salen solo de la base local de esta máquina", out)
        self.cli("projects")  # con el catálogo local pero sin sincronizar las horas
        out, err = self.cli("report", "time", "--from", DAY, "--json", env_set=OFFLINE)
        doc = json.loads(out)
        self.assertEqual((doc["scope"]["projects"], doc["coverage"]["complete"], doc["coverage"]["detail"]["hours_scope"]), (["OMNIFY", "OPS"], False, "local"))
        self.assertEqual(self.fake.requests[-1][0] if self.fake.requests else "GET", "GET")

    def test_after_a_sync_without_plane_the_age_of_the_data_is_shown(self):
        self.cli("report", "time", "--from", DAY)
        self.sb.advance(3 * 3600)
        out, err = self.cli("report", "time", "--from", DAY, "--json", env_set=OFFLINE)
        doc = json.loads(out)
        self.assertEqual((doc["coverage"]["stale"], doc["coverage"]["age_s"] >= 3 * 3600, doc["coverage"]["complete"]), (True, True, None))
        self.assertIn("cache_stale", [n["code"] for n in doc["notes"]], "los datos vencidos que se sirven sin red lo dicen en las notas")

    def test_a_wider_period_is_not_covered_by_a_narrower_sync(self):
        self.cli("report", "time", "--from", "2026-11-02")  # el lunes de la semana en curso (el reloj de las pruebas está congelado ahí)
        mark = len(self.fake.requests)
        self.cli("report", "time", "--week")
        self.assertTrue([p for p in self.paths(mark) if "/issues/?" in p], "la semana no estaba cubierta por la sincronización del día")


class Provenance(Base):
    """0022: nada de lo no medido se presenta como medido, y dos sincronizaciones dan filas idénticas."""

    def test_partial_telemetry_is_stored_with_its_provenance_and_never_with_an_invented_time(self):
        add_issue(self.fake, gs.P1, 40, [block(date=DAY, start_time="09:00", duration_minutes=30),          # sin fin, balde, fase, rol, notas
                                         block(date=DAY, notes="sin hora", duration_minutes=30),           # con fecha pero sin hora de inicio: no se puede ubicar
                                         "<p>**Sesión** | 14:00 - 14:30</p>"])                             # formato de tabla sin fecha: no se toma la del reloj
        out, err = self.cli("report", "time", "--from", DAY, "--refresh")
        self.assertIn("2 comentario(s) con telemetría sin fecha u hora no se sincronizaron", err)
        rows = self.rows("SELECT * FROM worklogs WHERE ticket_id = 'OMNIFY-40'")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["date"], row["start_time"], row["end_time"], row["duration_minutes"]), (DAY, "09:00", "09:30", 30), "el fin sale del inicio medido y la duración")
        self.assertEqual(row["notes"], "", "las notas no se rellenan con el título del ticket")
        self.assertEqual(json.loads(row["defaulted_json"]), ["capacity_bucket", "notes", "phase", "role", "track", "worker_type"])
        self.assertEqual(self.rows("SELECT unmeasured FROM worklog_sync WHERE project_ident = 'OMNIFY'")[0]["unmeasured"], 2)

    def test_a_fully_declared_comment_has_nothing_defaulted(self):
        add_issue(self.fake, gs.P1, 43, [full("11:00")])
        self.cli("report", "time", "--from", DAY, "--refresh")
        self.assertEqual({r["defaulted_json"] for r in self.rows("SELECT defaulted_json FROM worklogs WHERE ticket_id = 'OMNIFY-43'")}, {"[]"})
        self.assertEqual(json.loads(self.rows("SELECT defaulted_json FROM worklogs WHERE ticket_id = 'OMNIFY-1' LIMIT 1")[0]["defaulted_json"]), ["role"],
                         "el comentario de ejemplo no declara el rol: consta como no medido")

    def test_two_syncs_at_different_instants_give_identical_rows(self):
        add_issue(self.fake, gs.P1, 41, [block(date=DAY, start_time="10:00", duration_minutes=45)])
        columns = "ticket_id, track, date, start_time, end_time, duration_minutes, worker_type, capacity_bucket, phase, role, notes, created_at, author_id, defaulted_json"
        self.cli("report", "time", "--from", DAY, "--refresh")
        first = self.rows(f"SELECT {columns} FROM worklogs ORDER BY ticket_id, track, date, start_time")
        self.sb.advance(5 * 3600)
        self.cli("report", "time", "--from", DAY, "--refresh")
        self.assertEqual(self.rows(f"SELECT {columns} FROM worklogs ORDER BY ticket_id, track, date, start_time"), first)

    def test_comment_add_records_what_it_defaulted(self):
        self.cli("comment", "add", "OMNIFY-1", "-m", "hola", "--duration", "5", env_set=OFFLINE)
        row = self.rows("SELECT defaulted_json FROM worklogs")[0]
        self.assertIn("role", json.loads(row["defaulted_json"]))

    def test_an_unknown_state_is_shown_as_unknown_not_as_pending(self):
        add_issue(self.fake, gs.P1, 42, [], state="99999999-0000-4000-8000-000000000000")
        out, err = self.cli("list", "--json", "--brief", "--text", "Ticket", "-p", "OMNIFY")
        row = json.loads(out)["results"][0]
        self.assertEqual((row["state"], row["state_group"]), ("unknown", "unknown"))


if __name__ == "__main__":
    unittest.main()
