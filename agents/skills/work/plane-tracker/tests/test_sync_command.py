"""Comando `sync` (fase 6): alcance, periodo por defecto, `--history` con presupuesto y reanudable, identidad y solo GET."""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402
from test_worklog_sync import add_issue, full  # noqa: E402


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

    def sync(self, *args, code=0, **kwargs):
        return json.loads(self.run_cli("sync", *args, "--json", code=code, **kwargs)[0])

    def rows(self, sql):
        return self.sb.db_dump(sql)

    def paths(self, mark=0):
        return [p for _m, p, _b in self.fake.requests[mark:]]


class Scope(Base):
    def test_by_default_it_syncs_the_default_project_tickets_and_the_last_30_days_of_hours(self):
        doc = self.sync()
        self.assertEqual((doc["action"], doc["status"], doc["projects"], doc["issues"], doc["complete"]), ("sync", "ok", ["OMNIFY"], {"OMNIFY": "synced"}, True))
        self.assertEqual({r["ticket_id"].split("-")[0] for r in self.rows("SELECT ticket_id FROM issues_cache")}, {"OMNIFY"}, "solo el proyecto por defecto")
        marks = self.rows("SELECT * FROM worklog_sync")
        self.assertEqual([(m["project_ident"], m["date_from"], m["date_to"], m["complete"]) for m in marks], [("OMNIFY", "2026-10-03", "2026-11-02", 1)])
        self.assertEqual(doc["hours"]["period"], {"from": "2026-10-03", "to": "2026-11-02"})
        self.assertGreaterEqual(doc["hours"]["synced"], 1)

    def test_all_projects_a_named_project_and_an_explicit_period(self):
        self.assertEqual(self.sync("--all-projects")["projects"], ["OMNIFY", "OPS"])
        doc = self.sync("-p", "OPS", "--from", "2026-10-19", "--to", "2026-10-25")
        self.assertEqual((doc["projects"], doc["hours"]["period"]), (["OPS"], {"from": "2026-10-19", "to": "2026-10-25"}))
        self.assertEqual(self.sync("--week")["hours"]["period"], {"from": "2026-11-02", "to": "2026-11-08"})

    def test_text_summary_and_errors(self):
        out, _ = self.run_cli("sync")
        self.assertIn("sync · OMNIFY", out)
        self.assertIn("tickets OMNIFY: synced", out)
        self.assertIn("✔ Al día.", out)
        for argv, code, expected in ((["sync", "-p", "NOPE", "--json"], 1, "unknown_project"), (["sync", "--budget", "3", "--json"], 2, "usage"),
                                     (["sync", "--to", "2026-10-20", "--json"], 1, "bad_period")):
            got, out, err = self.sb.run(argv)
            self.assertEqual((got, json.loads(out)["code"]), (code, expected), argv)

    def test_a_read_never_syncs_by_itself_any_more_the_costly_part_is_sync(self):
        self.run_cli("list", "--offline", env_set={"PLANE_OFFLINE": "1"}, code=3)
        mark = len(self.fake.requests)
        self.run_cli("sync")
        self.assertTrue([p for p in self.paths(mark) if "/comments/" in p or "/issues/?" in p])


class Identity(Base):
    def test_without_an_identity_the_hours_are_not_mixed_but_the_history_does_not_need_one(self):
        doc = json.loads(self.run_cli("sync", "--json", env_drop=("PLANE_ACTOR_UUID",), code=1)[0])
        self.assertEqual(doc["code"], "actor_unknown")
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM worklog_sync")[0]["n"], 0)
        self.assertEqual(self.sync("--history", env_drop=("PLANE_ACTOR_UUID",))["action"], "sync")


class History(Base):
    def test_history_is_done_with_a_budget_and_resumes_where_it_stopped(self):
        first = self.sync("--history", "--budget", "1")
        self.assertEqual((first["history"]["fetched"], first["history"]["left"], first["complete"]), (1, 2, False))
        self.assertNotIn("hours", first, "con --history solo van tickets e historial")
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM worklog_sync")[0]["n"], 0)
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM flow_fetch")[0]["n"], 1)
        second = self.sync("--history", "--budget", "5")
        self.assertEqual((second["history"]["fetched"], second["history"]["left"], second["complete"]), (2, 0, True), "continúa donde quedó, sin repetir")
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM flow_fetch")[0]["n"], 3)
        third = self.sync("--history")
        self.assertEqual((third["history"]["fetched"], third["complete"]), (0, True))

    def test_the_rate_budget_stops_the_history_and_the_next_run_continues(self):
        self.sync("--all-projects")  # tickets en caché
        self.fake.rate_budget = 5  # con la reserva, 2 peticiones por ventana
        self.fake.new_window()
        doc = self.sync("--history", "--all-projects")
        self.assertTrue(doc["history"]["rate_limited"] and doc["history"]["left"] > 0 and not doc["complete"])
        fetched = [self.rows("SELECT COUNT(*) AS n FROM flow_fetch")[0]["n"]]
        for _ in range(6):
            self.fake.new_window()
            doc = self.sync("--history", "--all-projects")
            fetched.append(self.rows("SELECT COUNT(*) AS n FROM flow_fetch")[0]["n"])
            if doc["complete"]:
                break
        self.assertTrue(doc["complete"], fetched)
        self.assertEqual(fetched, sorted(fetched), "cada ejecución avanza")

    def test_after_the_history_a_list_involved_has_it_verified(self):
        self.run_cli("list", "--involved", "--json")
        self.sync("--history", "--budget", "10")
        doc = json.loads(self.run_cli("list", "--involved", "--json")[0])
        self.assertEqual(doc["coverage"]["detail"]["history"], {"total": 3, "verified": 3})
        self.assertNotIn("history_partial", [n["code"] for n in doc["notes"]])

    def test_sync_targets_granular(self):
        # 1. sync tickets: solo tickets, sin horas
        doc_tickets = self.sync("tickets")
        self.assertEqual(doc_tickets["issues"], {"OMNIFY": "synced"})
        self.assertNotIn("hours", doc_tickets)
        wms = self.rows("SELECT * FROM sync_watermarks WHERE domain = 'tickets'")
        self.assertGreaterEqual(len(wms), 1)

        # 2. sync hours: solo horas, sin tickets
        doc_hours = self.sync("hours")
        self.assertEqual(doc_hours["issues"], {})
        self.assertIn("hours", doc_hours)

        # 3. sync catalogs
        doc_cats = self.sync("catalogs")
        self.assertTrue(doc_cats["complete"])

    def test_the_retired_list_flags_point_to_sync(self):
        got, out, err = self.sb.run(["list", "--involved", "--refresh-history", "--budget", "2"])
        self.assertEqual(got, 2)
        self.assertIn("plane-tracker sync --history --budget 2", err)


if __name__ == "__main__":
    unittest.main()
