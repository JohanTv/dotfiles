"""Vistas `report time`, `report flow` y `worklog check` (fase 5): resumen, autor, periodos, proyecto común, flujo sin conexión y zona horaria."""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402
from test_worklog_sync import DAY, add_issue, block, full  # noqa: E402

OFFLINE = {"PLANE_OFFLINE": "1"}


class Base(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)
        self.fake = self.sb.fake

    def run_cli(self, *args, code=0, **kwargs):
        got, out, err = self.sb.run(list(args), **kwargs)
        self.assertNotIn("Traceback", err)
        self.assertEqual(got, code, err + out)
        return out, err

    def doc(self, *args, code=0, **kwargs):
        return json.loads(self.run_cli(*args, "--json", code=code, **kwargs)[0])

    def sql(self, statement, params=()):
        conn = sqlite3.connect(os.path.join(self.sb.home, ".cache", "plane", "worklogs.db"))
        conn.execute(statement, params)
        conn.commit()
        conn.close()

    def paths(self, mark=0):
        return [p for _m, p, _b in self.fake.requests[mark:]]


class Time(Base):
    def test_summary_is_per_day_project_and_capacity_and_the_week_total_does_not_merge_different_days(self):
        other = "2026-10-21"
        add_issue(self.fake, gs.P1, 60, [block(date=DAY, start_time="14:00", end_time="15:00", duration_minutes=60, capacity_bucket="tooling_dx", phase="dev", role="r",
                                              worker_type="human", track="main", notes="a"),
                                         block(date=other, start_time="09:00", end_time="10:00", duration_minutes=60, capacity_bucket="tooling_dx", phase="dev", role="r",
                                               worker_type="human", track="main", notes="b"),
                                         block(date=other, start_time="09:30", end_time="10:30", duration_minutes=60, capacity_bucket="deep_work", phase="dev", role="r",
                                               worker_type="human", track="main", notes="c")])
        doc = self.doc("report", "time", "--from", DAY, "--to", other)
        summary = doc["summary"]
        by_day = {d["key"]: d["minutes"] for d in summary["by_day"]}
        self.assertEqual(by_day[other], 90, "el reloj de un día es la unión de sus intervalos (09:00-10:30)")
        self.assertEqual(summary["effort_clock_minutes"], sum(by_day.values()), "el total es la suma de los días: dos días con el mismo horario no se funden")
        self.assertEqual(summary["effort_compute_minutes"], sum(r["minutes"] for r in doc["results"]))
        self.assertEqual({c["key"]: c["minutes"] for c in summary["by_capacity"]}["tooling_dx"], 120)
        self.assertEqual(doc["scope"]["period"], {"from": DAY, "tz": "+00:00", "to": other})
        self.assertEqual(doc["scope"]["hours_author"], gs.ME)
        self.assertEqual((doc["total"], doc["count"]), (len(doc["results"]), len(doc["results"])), "sin límite, count es total")
        self.assertEqual([(r["date"], r["start_time"]) for r in doc["results"]], sorted((r["date"], r["start_time"]) for r in doc["results"]), "orden total")

    def test_only_my_hours_count_and_unsigned_ones_are_excluded_and_warned(self):
        self.run_cli("report", "time", "--from", DAY)
        self.sql("INSERT INTO worklogs (ticket_id, track, date, start_time, end_time, duration_minutes, project_id, created_at, updated_at, author_id) "
                 "VALUES ('OMNIFY-1', 'sin', ?, '20:00', '20:30', 30, 'OMNIFY', 'x', 0, NULL)", (DAY,))
        self.sql("INSERT INTO worklogs (ticket_id, track, date, start_time, end_time, duration_minutes, project_id, created_at, updated_at, author_id) "
                 "VALUES ('OMNIFY-1', 'ajeno', ?, '21:00', '21:30', 30, 'OMNIFY', 'x', 0, ?)", (DAY, gs.OTHER))
        doc = self.doc("report", "time", "--from", DAY, "--offline")
        self.assertEqual({r["track"] for r in doc["results"]}, {"main", "subagent", "support"}, "ni las de autor nulo ni las de otros")
        self.assertTrue(all(r["author"] == gs.ME for r in doc["results"]))
        codes = [n["code"] for n in doc["notes"]]
        self.assertIn("hours_unsigned", codes)
        self.assertIsNot(doc["coverage"]["complete"], True)

    def test_from_alone_is_that_day_week_is_the_current_week_and_the_text_stops_at_today(self):
        one = self.doc("report", "time", "--from", DAY)
        self.assertEqual((one["scope"]["period"]["from"], one["scope"]["period"]["to"]), (DAY, DAY))
        week = self.doc("report", "time", "--week")
        self.assertEqual((week["scope"]["period"]["from"], week["scope"]["period"]["to"]), ("2026-11-02", "2026-11-08"))
        out, _ = self.run_cli("report", "time", "--week")
        self.assertIn("REPORTE SEMANAL - SEMANA 45 (02/11/2026 al 08/11/2026)", out)
        self.assertIn("[Lunes 02/11/2026]", out)
        self.assertNotIn("[Martes 03/11/2026]", out, "una semana en curso solo muestra hasta hoy")
        out, _ = self.run_cli("report", "time", "--from", "2026-10-19", "--to", "2026-10-21", "--offline")
        self.assertIn("REPORTE DE ACTIVIDAD (19/10/2026 al 21/10/2026)", out)
        self.assertIn("[Martes 20/10/2026]", out)

    def test_bad_periods_are_errors_with_a_hint(self):
        for args, code in ((["--from", "bad"], "bad_date"), (["--to", "2026-13-01"], "bad_date"), (["--week", "--from", DAY], "bad_period"),
                           (["--from", "2026-10-21", "--to", "2026-10-20"], "bad_period")):
            doc = self.doc("report", "time", *args, code=1)
            self.assertEqual((doc["code"], bool(doc["hint"])), (code, True), args)

    def test_a_report_without_a_view_or_with_retired_period_flags_exits_2_with_the_command_to_use(self):
        for argv, hint in ((["report"], "report time --week"), (["report", "--date", DAY], "report time --from " + DAY), (["report", "time", "--date", DAY], "report time --from " + DAY),
                           (["report", "time", "--today"], "plane-tracker report time")):
            code, out, err = self.sb.run(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn(hint, err)

    def test_offline_never_touches_the_network_and_says_what_it_is(self):
        self.run_cli("report", "time", "--from", DAY)
        mark = len(self.fake.requests)
        doc = self.doc("report", "time", "--from", DAY, "--offline")
        self.assertEqual(self.fake.requests[mark:], [])
        self.assertEqual(doc["coverage"]["source"], "local")


class Projects(Base):
    """El filtro de proyecto es el mismo en las tres vistas."""

    def setUp(self):
        super().setUp()
        self.run_cli("report", "time", "--from", DAY)  # horas y proyectos
        self.run_cli("report", "flow", "--from", DAY)  # tickets y transiciones

    def test_one_project_filters_time_flow_and_check_alike(self):
        time_doc = self.doc("report", "time", "--from", DAY, "-p", "OPS", "--offline")
        flow_doc = self.doc("report", "flow", "--from", DAY, "-p", "OPS", "--offline")
        check_doc = self.doc("worklog", "check", "--from", DAY, "-p", "OPS")
        self.assertEqual({r["project"] for r in time_doc["results"]}, {"OPS"})
        self.assertEqual({r["ticket"].split("-")[0] for r in flow_doc["results"]}, {"OPS"})
        self.assertEqual({c["ticket"].split("-")[0] for c in check_doc["summary"]["checked"]}, {"OPS"})
        for doc in (time_doc, flow_doc, check_doc):
            self.assertEqual(doc["scope"]["projects"], ["OPS"])

    def test_all_projects_is_the_default_of_the_reports(self):
        explicit = self.doc("report", "time", "--from", DAY, "--all-projects", "--offline")
        default = self.doc("report", "time", "--from", DAY, "--offline")
        self.assertEqual(explicit["results"], default["results"])
        self.assertEqual(default["scope"]["projects"], ["OMNIFY", "OPS"])

    def test_an_unknown_project_is_the_same_error_in_the_three_views(self):
        for argv in (["report", "time", "--from", DAY, "-p", "NOPE"], ["report", "flow", "--from", DAY, "-p", "NOPE"], ["worklog", "check", "--from", DAY, "-p", "NOPE"]):
            doc = self.doc(*argv, code=1)
            self.assertEqual(doc["code"], "unknown_project", argv)
            self.assertIn("OMNIFY, OPS", doc["hint"])


class Flow(Base):
    def test_the_flow_is_computed_from_what_is_stored_so_offline_gives_the_same_answer(self):
        self.run_cli("report", "time", "--from", "2026-10-14")
        online = self.doc("report", "flow", "--from", "2026-10-14")
        mark = len(self.fake.requests)
        offline = self.doc("report", "flow", "--from", "2026-10-14", "--offline")
        self.assertEqual(self.fake.requests[mark:], [], "--offline no pide nada")
        self.assertEqual(offline["results"], online["results"])
        self.assertEqual(offline["summary"], online["summary"])
        self.assertEqual((online["coverage"]["source"], online["coverage"]["detail"]["history"]), ("mixed", {"verified": 1, "total": 1}))
        self.assertTrue(online["results"] and online["results"][0]["outcome"] == "completed")

    def test_transitions_are_fetched_once_per_changed_ticket_and_refresh_fetches_them_again(self):
        self.run_cli("report", "time", "--from", "2026-10-14")
        mark = len(self.fake.requests)
        self.run_cli("report", "flow", "--from", "2026-10-14")
        first = [p for p in self.paths(mark) if "/activities/" in p]
        self.assertEqual(len(first), 1)
        mark = len(self.fake.requests)
        self.run_cli("report", "flow", "--from", "2026-10-14")
        self.assertFalse([p for p in self.paths(mark) if "/activities/" in p], "al día: no se vuelve a pedir")
        mark = len(self.fake.requests)
        self.run_cli("report", "flow", "--from", "2026-10-14", "--refresh")
        self.assertEqual(len([p for p in self.paths(mark) if "/activities/" in p]), 1)

    def test_a_ticket_without_its_transitions_makes_the_coverage_incomplete(self):
        self.run_cli("report", "time", "--from", "2026-10-14")
        doc = self.doc("report", "flow", "--from", "2026-10-14", "--offline")  # nunca se trajeron las transiciones
        self.assertEqual(doc["coverage"]["detail"]["history"], {"total": 1, "verified": 0})
        self.assertIs(doc["coverage"]["complete"], False)
        self.assertIn("history_partial", [n["code"] for n in doc["notes"]])

    def test_the_closing_date_is_compared_in_the_declared_time_zone(self):
        self.run_cli("report", "time", "--from", "2026-10-14")
        self.fake.data["issues"][gs.P1][1]["completed_at"] = "2026-10-21T02:00:00Z"  # 2026-10-20 21:00 en Lima (UTC-5)
        self.fake.data["comments"]["10000000-0000-4000-8000-000000000002"] = []
        self.sql("DELETE FROM worklogs")
        self.run_cli("list", "--refresh")  # trae el cierre a la caché de tickets
        utc = self.doc("report", "flow", "--from", "2026-10-20", "--offline", env_set={"TZ": "UTC", **OFFLINE})
        lima = self.doc("report", "flow", "--from", "2026-10-20", "--offline", env_set={"TZ": "America/Lima", **OFFLINE})
        self.assertEqual([r["ticket"] for r in utc["results"]], [], "en UTC cerró el 21")
        self.assertEqual([r["ticket"] for r in lima["results"]], ["OMNIFY-2"], "en Lima cerró el 20")
        self.assertEqual((utc["scope"]["period"]["tz"], lima["scope"]["period"]["tz"]), ("+00:00", "-05:00"))


class Check(Base):
    def test_it_is_a_network_audit_with_the_common_scope_and_envelope(self):
        self.run_cli("report", "time", "--from", DAY)
        doc = self.doc("worklog", "check", "--from", DAY, code=1)  # el comentario ajeno con telemetría del servidor falso no tiene fila local: missing_local
        self.assertEqual((doc["view"], doc["coverage"]["source"], doc["summary"]["ok"], doc["summary"]["unreachable"]), ("worklog check", "api", False, 0))
        self.assertEqual([i["code"] for i in doc["results"]], ["missing_local"])
        self.assertEqual({c["ticket"] for c in doc["summary"]["checked"]}, {"OMNIFY-1", "OPS-13"})
        self.assertEqual(doc["scope"]["period"]["from"], DAY)
        self.assertNotIn("hours_author", doc["scope"], "es una auditoría de los registros locales, no una vista personal")


if __name__ == "__main__":
    unittest.main()
