"""Pruebas de la Fase 3 (RFC 0006 Cuantitativo): medición de standby real en report flow desde transiciones de estado."""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import flow_metrics as fm  # noqa: E402
import golden_support as gs  # noqa: E402
from plane_cli import envelope  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
NOW = T0 + timedelta(days=20)
STATES = {
    "bk": {"name": "Backlog", "group": "backlog"},
    "pe": {"name": "Pendiente", "group": "unstarted"},
    "pr": {"name": "Progreso", "group": "started"},
    "pa": {"name": "Pausado", "group": "started"},
    "bl": {"name": "Bloqueado", "group": "started"},
    "co": {"name": "Completado", "group": "completed"},
    "ca": {"name": "Cancelado", "group": "cancelled"},
}


def h(hours):
    return T0 + timedelta(hours=hours)


def tr(hours, a, b):
    return {"at": h(hours), "from_id": a, "to_id": b}


def issue(state, completed=None, name="[FEAT] x", created=None):
    return {"name": name, "created_at": created or T0, "completed_at": completed, "state": state}


class TestFlowStandbyMetrics(unittest.TestCase):
    def test_compute_flow_measures_standby_from_paused_transitions(self):
        # 2h en progreso, 10h en pausado, 3h en progreso -> total 15h gross, 5h active, 10h standby
        trs = [tr(0, "bk", "pr"), tr(2, "pr", "pa"), tr(12, "pa", "pr"), tr(15, "pr", "co")]
        f = fm.compute_flow(issue("co", h(15)), trs, STATES, [], NOW)
        self.assertEqual(f["cycle_active_minutes"], 5 * 60)
        self.assertEqual(f["cycle_gross_minutes"], 15 * 60)
        self.assertEqual(f["standby_minutes"], 10 * 60)
        self.assertEqual(f["outcome"], "completed")

    def test_compute_flow_handles_bloqueado_synonym(self):
        # 1h progreso, 4h bloqueado, 1h progreso
        trs = [tr(0, "bk", "pr"), tr(1, "pr", "bl"), tr(5, "bl", "pr"), tr(6, "pr", "co")]
        f = fm.compute_flow(issue("co", h(6)), trs, STATES, [], NOW)
        self.assertEqual(f["cycle_active_minutes"], 2 * 60)
        self.assertEqual(f["standby_minutes"], 4 * 60)

    def test_compute_flow_zero_standby_when_never_paused(self):
        trs = [tr(0, "bk", "pr"), tr(8, "pr", "co")]
        f = fm.compute_flow(issue("co", h(8)), trs, STATES, [], NOW)
        self.assertEqual(f["cycle_active_minutes"], 8 * 60)
        self.assertEqual(f["standby_minutes"], 0.0)

    def test_aggregate_computes_standby_summary_metrics(self):
        trs1 = [tr(0, "bk", "pr"), tr(2, "pr", "pa"), tr(12, "pa", "pr"), tr(15, "pr", "co")]
        f1 = fm.compute_flow(issue("co", h(15)), trs1, STATES, [], NOW)  # 600m standby

        trs2 = [tr(0, "bk", "pr"), tr(4, "pr", "pa"), tr(8, "pa", "pr"), tr(10, "pr", "co")]
        f2 = fm.compute_flow(issue("co", h(10)), trs2, STATES, [], NOW)  # 240m standby

        trs3 = [tr(0, "bk", "pr"), tr(5, "pr", "co")]
        f3 = fm.compute_flow(issue("co", h(5)), trs3, STATES, [], NOW)   # 0m standby

        agg = fm.aggregate([f1, f2, f3])
        self.assertEqual(agg["tickets"], 3)
        self.assertEqual(agg["completed"], 3)
        self.assertEqual(agg["tickets_with_standby"], 2)
        self.assertEqual(agg["total_standby_minutes"], 840.0)
        self.assertEqual(agg["median_standby_minutes"], 420.0)


class TestReportFlowCliStandby(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)
        self.fake = self.sb.fake

    def test_cli_report_flow_renders_standby_in_text_and_json(self):
        # Primero sincronizamos worklogs y flujo inicial para OMNIFY-2
        code, out, err = self.sb.run(["report", "time", "--from", "2026-10-14", "--refresh"])
        self.assertEqual(code, 0, err)
        code, out, err = self.sb.run(["report", "flow", "--from", "2026-10-14", "--refresh"])
        self.assertEqual(code, 0, err)

        # Inyectamos una transición a Pausado para OMNIFY-2 en SQLite
        # issue_id de OMNIFY-2: 10000000-0000-4000-8000-000000000002
        import sqlite3
        conn = sqlite3.connect(os.path.join(self.sb.home, ".cache", "plane", "worklogs.db"))
        s_prog = "10000000-0000-4000-8000-111111111111"
        s_paus = gs.state_id(gs.P1, "Pausado")
        s_comp = gs.state_id(gs.P1, "Completado")
        conn.execute("INSERT OR REPLACE INTO state_transitions VALUES (?,?,?,?,?,?,?,?)",
                     ("tr-p1", "10000000-0000-4000-8000-000000000002", "OMNIFY-2", "2026-10-11T12:00:00Z", s_prog, s_paus, "Progreso", "Pausado"))
        conn.execute("INSERT OR REPLACE INTO state_transitions VALUES (?,?,?,?,?,?,?,?)",
                     ("tr-p2", "10000000-0000-4000-8000-000000000002", "OMNIFY-2", "2026-10-13T12:00:00Z", s_paus, s_prog, "Pausado", "Progreso"))
        conn.execute("INSERT OR REPLACE INTO state_transitions VALUES (?,?,?,?,?,?,?,?)",
                     ("tr-p3", "10000000-0000-4000-8000-000000000002", "OMNIFY-2", "2026-10-15T12:00:00Z", s_prog, s_comp, "Progreso", "Completado"))
        conn.commit()
        conn.close()

        # Ejecutamos report flow con --json
        code, out, err = self.sb.run(["report", "flow", "--from", "2026-10-14", "--offline", "--json"])
        self.assertEqual(code, 0, err)
        doc = json.loads(out)
        self.assertEqual(doc["schema"], "plane-tracker/1")
        self.assertEqual(envelope.validate(doc), [])

        item = doc["results"][0]
        self.assertGreater(item.get("standby_minutes", 0), 0)
        self.assertEqual(doc["summary"]["tickets_with_standby"], 1)
        self.assertGreater(doc["summary"]["total_standby_minutes"], 0)

        # Ejecutamos report flow en texto
        code, out_txt, err = self.sb.run(["report", "flow", "--from", "2026-10-14", "--offline"])
        self.assertEqual(code, 0, err)
        self.assertIn("⏸ Pausado", out_txt)
        self.assertIn("standby acumulado", out_txt)


if __name__ == "__main__":
    unittest.main()
