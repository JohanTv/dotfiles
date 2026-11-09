"""Degradación ante Plane caído (sin caché): sync tolerante, report --refresh, worklog check y report flow."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import golden_support as gs  # noqa: E402

ISSUES = r"/projects/%s/issues/$" % gs.P1


class Degrade(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)

    def run_cli(self, *args, **kwargs):
        code, out, err = self.sb.run(list(args), **kwargs)
        self.assertNotIn("Traceback", err)
        return code, out, err

    def test_report_refresh_with_502_on_issues(self):
        self.sb.fake.add_fault("GET", ISSUES, "status", 502)
        code, out, err = self.run_cli("report", "time", "--from", "2026-10-20", "--refresh")
        self.assertEqual(code, 0, err)
        self.assertIn("Sincronización incompleta: Plane no responde (HTTP 502)", err)
        self.assertEqual(self.sb.db_dump("SELECT COUNT(*) AS n FROM worklog_sync")[0]["n"], 0)

    def test_report_refresh_without_plane_exits_zero(self):
        code, out, err = self.run_cli("report", "time", "--from", "2026-10-20", "--refresh", env_set={"PLANE_OFFLINE": "1"})
        self.assertEqual(code, 0, err)
        self.assertIn("Las horas salen solo de la base local de esta máquina", out, "sin Plane el reporte lo dice en sus notas, no en stderr")
        self.assertEqual(err, "")
        self.assertEqual(self.sb.fake.requests, [])
        code, out, err = self.run_cli("report", "time", "--from", "2026-10-20", "--offline", "--json")
        doc = json.loads(out)
        self.assertEqual((code, doc["coverage"]["complete"], doc["coverage"]["detail"]["hours_scope"], doc["coverage"]["source"]), (0, None, "local", "local"))
        self.assertEqual(self.sb.fake.requests, [])

    def test_report_refresh_with_502_on_comments_keeps_the_watermark_unset(self):
        self.sb.fake.add_fault("GET", r"/comments/$", "status", 503)
        code, out, err = self.run_cli("report", "time", "--from", "2026-10-20", "--refresh")
        self.assertEqual(code, 0, err)
        self.assertIn("Sincronización incompleta", err)

    def seed_worklogs(self):
        self.assertEqual(self.sb.run(["report", "time", "--from", "2026-10-20", "--refresh"])[0], 0)

    def test_worklog_check_with_unreachable_tickets_exits_3(self):
        self.seed_worklogs()
        self.sb.fake.add_fault("*", r"/comments/$", "status", 503)
        code, out, err = self.run_cli("worklog", "check", "--from", "2026-10-20", "--json")
        self.assertEqual(code, 3, err)
        data = json.loads(out)
        self.assertGreaterEqual(data["summary"]["unreachable"], 1)
        self.assertTrue(data["summary"]["ok"])
        self.assertIs(data["coverage"]["complete"], False, "con tickets sin comprobar el resultado está incompleto")
        text = self.run_cli("worklog", "check", "--from", "2026-10-20")[1]
        self.assertIn("no se pudo consultar el ticket en Plane", text)

    def test_worklog_check_healthy_keeps_exit_zero(self):
        self.seed_worklogs()
        code, out, err = self.run_cli("worklog", "check", "--from", "2026-10-20", "--json")
        doc = json.loads(out)
        self.assertEqual((doc["summary"]["unreachable"], doc["coverage"]["complete"]), (0, True))

    def test_report_flow_skips_unreachable_tickets(self):
        self.seed_worklogs()
        self.sb.fake.close()
        code, out, err = self.run_cli("report", "flow", "--from", "2026-10-20", "--json")
        self.assertEqual(code, 0, err)
        doc = json.loads(out)
        self.assertEqual((doc["total"], doc["coverage"]["source"], doc["coverage"]["complete"]), (0, "mixed", False))
        self.assertIn("source_unavailable", [n["code"] for n in doc["notes"]], "sin tickets en caché ni red el flujo sale vacío y lo dice")

    def test_report_time_with_403_on_one_project_records_forbidden(self):
        issues_ops = r"/projects/%s/issues/$" % gs.P2
        self.sb.fake.add_fault("GET", issues_ops, "status", 403)
        code, out, err = self.run_cli("report", "time", "--all-projects", "--from", "2026-10-20", "--refresh", "--json")
        self.assertEqual(code, 0, err)
        doc = json.loads(out)
        self.assertEqual(doc["coverage"]["complete"], False)
        self.assertEqual(doc["coverage"]["detail"].get("forbidden"), ["OPS"])
        notes = [n["code"] for n in doc["notes"]]
        self.assertIn("source_forbidden", notes)


if __name__ == "__main__":
    unittest.main()
