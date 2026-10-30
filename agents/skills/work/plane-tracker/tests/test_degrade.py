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
        code, out, err = self.run_cli("report", "--date", "2026-10-20", "--refresh")
        self.assertEqual(code, 0, err)
        self.assertIn("Sincronización incompleta: Plane no responde (HTTP 502)", err)
        self.assertEqual(self.sb.db_dump("SELECT COUNT(*) AS n FROM sync_metadata WHERE key LIKE 'sync:%'")[0]["n"], 0)

    def test_report_refresh_without_plane_exits_zero(self):
        code, out, err = self.run_cli("report", "--date", "2026-10-20", "--refresh", env_set={"PLANE_OFFLINE": "1"})
        self.assertEqual(code, 0, err)
        self.assertIn("se omite la sincronización", err)
        self.assertEqual(self.sb.fake.requests, [])

    def test_report_refresh_with_502_on_comments_keeps_the_watermark_unset(self):
        self.sb.fake.add_fault("GET", r"/comments/$", "status", 503)
        code, out, err = self.run_cli("report", "--date", "2026-10-20", "--refresh")
        self.assertEqual(code, 0, err)
        self.assertIn("Sincronización incompleta", err)

    def seed_worklogs(self):
        self.assertEqual(self.sb.run(["report", "--date", "2026-10-20", "--refresh"])[0], 0)

    def test_worklog_check_with_unreachable_tickets_exits_3(self):
        self.seed_worklogs()
        self.sb.fake.add_fault("*", r"/comments/$", "status", 503)
        code, out, err = self.run_cli("worklog", "check", "--date", "2026-10-20", "--json")
        self.assertEqual(code, 3, err)
        data = json.loads(out)
        self.assertGreaterEqual(data["unreachable"], 1)
        self.assertTrue(data["ok"])
        self.assertIn("no se pudieron comprobar", err)

    def test_worklog_check_healthy_keeps_exit_zero(self):
        self.seed_worklogs()
        code, out, err = self.run_cli("worklog", "check", "--date", "2026-10-20", "--json")
        self.assertEqual(json.loads(out)["unreachable"], 0)

    def test_report_flow_skips_unreachable_tickets(self):
        self.seed_worklogs()
        self.sb.fake.close()
        code, out, err = self.run_cli("report", "flow", "--date", "2026-10-20")
        self.assertEqual(code, 0, err)
        self.assertIn("Plane no responde", err)


if __name__ == "__main__":
    unittest.main()
