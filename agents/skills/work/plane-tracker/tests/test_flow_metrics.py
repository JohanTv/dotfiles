import os
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import flow_metrics as fm  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
NOW = T0 + timedelta(days=30)
STATES = {
    "bk": {"name": "Backlog", "group": "backlog"},
    "pe": {"name": "Pendiente", "group": "unstarted"},
    "pr": {"name": "Progreso", "group": "started"},
    "pa": {"name": "Pausado", "group": "started"},
    "co": {"name": "Completado", "group": "completed"},
    "ca": {"name": "Cancelado", "group": "cancelled"},
}


def h(hours):
    return T0 + timedelta(hours=hours)


def tr(hours, a, b):
    return {"at": h(hours), "from_id": a, "to_id": b}


def issue(state, completed=None, name="[FEAT] x", created=None):
    return {"name": name, "created_at": created or T0, "completed_at": completed, "state": state}


def flow(iss, transitions, worklogs=()):
    return fm.compute_flow(iss, transitions, STATES, list(worklogs), NOW)


class Timeline(unittest.TestCase):
    def test_1_simple(self):
        f = flow(issue("co", h(10)), [tr(2, "bk", "pr"), tr(10, "pr", "co")])
        self.assertEqual(f["lead_minutes"], 600)
        self.assertEqual(f["cycle_active_minutes"], 480)
        self.assertEqual(f["by_state_minutes"], {"Backlog": 120, "Progreso": 480})
        self.assertEqual(f["outcome"], "completed")

    def test_2_reopen(self):
        trs = [tr(1, "bk", "pr"), tr(3, "pr", "co"), tr(5, "co", "pr"), tr(9, "pr", "co")]
        f = flow(issue("co", h(9)), trs)
        self.assertEqual(f["cycle_active_minutes"], (2 + 4) * 60)
        self.assertEqual(f["lead_minutes"], 9 * 60)
        self.assertEqual(f["by_state_minutes"]["Completado"], 120)

    def test_2b_reopened_is_open(self):
        f = flow(issue("pr", None), [tr(1, "bk", "pr"), tr(3, "pr", "co"), tr(5, "co", "pr")])
        self.assertEqual(f["outcome"], "open")
        self.assertEqual(f["lead_minutes"], (NOW - T0).total_seconds() / 60)

    def test_3_paused_excluded_from_active(self):
        trs = [tr(0, "bk", "pr"), tr(3, "pr", "pa"), tr(27, "pa", "pr"), tr(30, "pr", "co")]
        f = flow(issue("co", h(30)), trs)
        self.assertEqual(f["cycle_active_minutes"], 6 * 60)
        self.assertEqual(f["cycle_gross_minutes"], 30 * 60)

    def test_4_jump_backlog_to_completed(self):
        f = flow(issue("co", h(0.01)), [tr(0.01, "bk", "co")])
        self.assertIsNone(f["cycle_active_minutes"])
        self.assertIn("sin_started", f["flags"])
        self.assertIn("cierre_instantaneo", f["flags"])

    def test_5_no_transitions_open(self):
        f = flow(issue("pr"), [])
        self.assertEqual(f["outcome"], "open")
        self.assertIn("sin_transicion", f["flags"])
        self.assertEqual(f["by_state_minutes"], {"Progreso": 30 * 24 * 60})

    def test_6_created_completed_without_transition(self):
        f = flow(issue("co", h(2)), [])
        self.assertEqual(f["lead_minutes"], 120)
        self.assertIn("sin_transicion", f["flags"])

    def test_7_cancelled_has_no_completed_at(self):
        f = flow(issue("ca", None), [tr(1, "bk", "pr"), tr(4, "pr", "pa"), tr(20, "pa", "ca")])
        self.assertEqual(f["outcome"], "cancelled")
        self.assertEqual(f["closed"], h(20))
        self.assertEqual(f["lead_minutes"], 20 * 60)

    def test_8_state_identity_by_id_not_name(self):
        renamed = dict(STATES, pr={"name": "En curso", "group": "started"})
        f = fm.compute_flow(issue("co", h(5)), [tr(1, "bk", "pr"), tr(5, "pr", "co")], renamed, [], NOW)
        self.assertEqual(f["by_state_minutes"]["En curso"], 240)

    def test_unknown_state_is_flagged(self):
        f = flow(issue("co", h(5)), [tr(1, "zz", "pr"), tr(5, "pr", "co")])
        self.assertIn("estado_desconocido", f["flags"])

    def test_12_umbrella_flag(self):
        f = flow(issue("pr", name="Tareas Rápidas y Soporte - W44"), [])
        self.assertIn("paraguas", f["flags"])


class Effort(unittest.TestCase):
    def setUp(self):
        self._tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/Lima"
        time.tzset()

    def tearDown(self):
        if self._tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._tz
        time.tzset()

    def test_9_late_local_worklog_is_next_day_utc(self):
        wl = {"date": "2026-10-05", "start_time": "23:00", "end_time": "23:30", "duration_minutes": 30}
        start, _ = fm._worklog_interval(wl)
        self.assertEqual(start, datetime(2026, 10, 6, 4, 0, tzinfo=UTC))

    def test_10_outside_window(self):
        before = {"date": "2026-09-30", "start_time": "08:00", "end_time": "09:00", "duration_minutes": 60}
        after = {"date": "2026-10-20", "start_time": "08:00", "end_time": "09:00", "duration_minutes": 60}
        f = flow(issue("co", h(48)), [tr(1, "bk", "pr"), tr(48, "pr", "co")], [before, after])
        self.assertEqual((f["worklogs_before_created"], f["worklogs_after_closed"]), (1, 1))
        self.assertEqual(f["effort_compute_minutes"], 120)

    def test_11_overlap_compute_vs_clock(self):
        a = {"date": "2026-10-05", "start_time": "10:00", "end_time": "10:30", "duration_minutes": 30}
        b = {"date": "2026-10-05", "start_time": "10:00", "end_time": "10:30", "duration_minutes": 30}
        f = flow(issue("pr"), [], [a, b])
        self.assertEqual(f["effort_compute_minutes"], 60)
        self.assertEqual(f["effort_clock_minutes"], 30)

    def test_midnight_crossing_worklog(self):
        wl = {"date": "2026-10-05", "start_time": "23:30", "end_time": "00:30", "duration_minutes": 60}
        start, end = fm._worklog_interval(wl)
        self.assertEqual(end - start, timedelta(hours=1))


class Aggregate(unittest.TestCase):
    def test_medians_exclude_noise(self):
        good1 = flow(issue("co", h(10)), [tr(2, "bk", "pr"), tr(10, "pr", "co")])
        good2 = flow(issue("co", h(30)), [tr(2, "bk", "pr"), tr(30, "pr", "co")])
        noise = flow(issue("co", h(0.01)), [tr(0.01, "bk", "co")])
        umb = flow(issue("co", h(100), name="Reuniones - W44"), [tr(1, "bk", "pr"), tr(100, "pr", "co")])
        agg = fm.aggregate([good1, good2, noise, umb])
        self.assertEqual(agg["n_lead"], 2)
        self.assertEqual(agg["median_lead_minutes"], (600 + 1800) / 2)
        self.assertEqual(agg["excluded"], 2)


if __name__ == "__main__":
    unittest.main()
