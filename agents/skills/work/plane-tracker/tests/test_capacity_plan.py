"""Pruebas de la Fase 2 (RFC 0026 y RFC 0006): plan de capacidad, varianza y poda de standby sintético."""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402
from plane_cli import envelope, query_time  # noqa: E402
from test_worklog_sync import DAY, add_issue, block  # noqa: E402


class TestCapacityPlan(unittest.TestCase):
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

    def test_parse_plan_helper(self):
        plan = query_time._parse_plan("deep_work=50%,toil_support=20%,rest")
        self.assertEqual(plan["deep_work"], 50.0)
        self.assertEqual(plan["toil_support"], 20.0)
        self.assertEqual(plan["rest"], 30.0)

        plan_no_rest = query_time._parse_plan("deep_work=60%,toil_support=40%")
        self.assertEqual(plan_no_rest, {"deep_work": 60.0, "toil_support": 40.0})

        self.assertIsNone(query_time._parse_plan(""))
        self.assertIsNone(query_time._parse_plan(None))

    def test_calculate_variance_helper(self):
        by_cap = [{"key": "deep_work", "minutes": 60}, {"key": "toil_support", "minutes": 40}]
        plan = {"deep_work": 50.0, "toil_support": 50.0}
        var = query_time._calculate_variance(by_cap, 100, plan)
        var_map = {v["bucket"]: v for v in var}
        self.assertEqual(var_map["deep_work"]["actual_percent"], 60.0)
        self.assertEqual(var_map["deep_work"]["variance_percent"], 10.0)
        self.assertEqual(var_map["toil_support"]["actual_percent"], 40.0)
        self.assertEqual(var_map["toil_support"]["variance_percent"], -10.0)

    def test_synthetic_standby_pruned_from_daily_and_weekly_reports(self):
        # Insertamos un registro sin stoppers
        add_issue(self.fake, gs.P1, 99, [block(date=DAY, start_time="10:00", end_time="11:00", duration_minutes=60,
                                               capacity_bucket="deep_work", phase="dev", role="r", worker_type="human",
                                               track="main", notes="Test task")])
        out, _ = self.run_cli("report", "time", "--from", DAY, "--refresh")
        self.assertNotIn("0h 00m (Sin bloqueos reportados)", out)
        self.assertNotIn("Standby externo: 0h 00m", out)

        # En reporte semanal tampoco debe haber standby sintético
        out_week, _ = self.run_cli("report", "time", "--week", "--offline")
        self.assertNotIn("0h 00m (Sin bloqueos reportados)", out_week)

    def test_report_time_weekly_renders_capacity_distribution_and_plan(self):
        add_issue(self.fake, gs.P1, 101, [
            block(date="2026-11-02", start_time="10:00", end_time="12:00", duration_minutes=120, capacity_bucket="deep_work",
                  phase="dev", role="r", worker_type="human", track="main", notes="Feature"),
            block(date="2026-11-02", start_time="14:00", end_time="15:00", duration_minutes=60, capacity_bucket="toil_support",
                  phase="dev", role="r", worker_type="human", track="main", notes="Support"),
        ], updated="2026-11-02T15:00:00Z")
        doc = self.doc("report", "time", "--week", "--plan", "deep_work=60%,toil_support=40%")
        summary = doc["summary"]
        self.assertIn("capacity_variance", summary)
        self.assertIsNotNone(summary["capacity_variance"])
        probs = envelope.validate(doc)
        self.assertEqual(probs, [], f"Sobre inválido: {probs}")

        out, _ = self.run_cli("report", "time", "--week", "--plan", "deep_work=60%,toil_support=40%")
        self.assertIn("🎯 DISTRIBUCIÓN POR CAPACIDAD:", out)
        self.assertIn("deep_work", out)
        self.assertIn("toil_support", out)
        self.assertIn("meta 60.0%", out)
        self.assertIn("meta 40.0%", out)
        self.assertIn("Tiempo no contabilizado", out)


if __name__ == "__main__":
    unittest.main()
