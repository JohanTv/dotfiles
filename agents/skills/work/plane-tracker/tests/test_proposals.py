import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import flow_metrics as fm  # noqa: E402
import plane  # noqa: E402
from plane_cli import config  # noqa: E402
import session_clock as sc  # noqa: E402

UTC = timezone.utc
SID = "11111111-2222-3333-4444-555555555555"
NOW = datetime(2026, 10, 29, 17, 0, tzinfo=UTC)  # 12:00 en Lima (UTC-5)


def local(hour, minute=0):
    return datetime(2026, 10, 29, hour, minute).astimezone(UTC)


def every_two_minutes(start, end):
    out, cur = [], start
    while cur <= end:
        out.append(cur)
        cur += timedelta(minutes=2)
    return out


# 09:00-10:00 y 10:40-11:00 (pausa de 40 min en medio) -> 80 min de actividad
STAMPS = every_two_minutes(local(9), local(10)) + every_two_minutes(local(10, 40), local(11))


class Base(unittest.TestCase):
    def setUp(self):
        self._tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/Lima"
        time.tzset()
        self.tmp = tempfile.TemporaryDirectory()
        self._saved = (config.CACHE_DIR, config.now, sc.timestamps, sc.resolve_session)
        config.CACHE_DIR = self.tmp.name
        config.now = lambda: NOW
        sc.timestamps = lambda agent, sid, **kw: STAMPS
        sc.resolve_session = lambda agent, cwd, explicit=None, env=None, **kw: (SID, "test", [])
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        plane.init_db(self.conn)

    def tearDown(self):
        config.CACHE_DIR, config.now, sc.timestamps, sc.resolve_session = self._saved
        self.tmp.cleanup()
        if self._tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._tz
        time.tzset()

    def args(self, **kw):
        return Namespace(**{"agent": "claude", "session": None, "since": None, "until": None, **kw})

    def propose(self, ticket="OMNIFY-1", **kw):
        return plane.build_proposal(self.conn, self.args(**kw), "deep_work", "agent:claude", ticket)

    def mark(self, ticket, start, end=None):
        self.conn.execute("INSERT INTO session_marks (session_id, agent, ticket, started_at, ended_at) VALUES (?,?,?,?,?)",
                          (SID, "claude", ticket, start.isoformat(), end.isoformat() if end else None))

    def register(self, ticket, proposal):
        meta = {"date": proposal["date"], "start_time": proposal["start_time"], "end_time": proposal["end_time"],
                "segments": proposal["segments"], "measured_by": {"kind": "proposal", "session": SID}}
        plane.upsert_worklog(self.conn, {"ticket_id": ticket, "track": "main", "date": proposal["date"], "start_time": proposal["start_time"],
                                         "end_time": proposal["end_time"], "duration_minutes": proposal["minutes"], "raw_payload": meta})


class Measurement(Base):
    def test_net_minutes_exclude_the_pause(self):
        p = self.propose()
        self.assertTrue(p["ok"])
        self.assertEqual(p["minutes"], 80)
        self.assertEqual(len(p["segments"]), 2)
        self.assertEqual(sum(s["minutes"] for s in p["segments"]), 80)
        self.assertEqual((p["start_time"], p["end_time"]), ("09:00", "11:00"))

    def test_registered_time_is_not_counted_twice(self):
        first = self.propose("OMNIFY-1")
        self.register("OMNIFY-1", first)
        again = self.propose("OMNIFY-2")
        self.assertFalse(again["ok"])

    def test_declared_worklog_covers_only_its_own_interval(self):
        meta = {"measured_by": {"kind": "declared", "session": SID}}
        plane.upsert_worklog(self.conn, {"ticket_id": "OMNIFY-1", "track": "main", "date": "2026-10-29", "start_time": "09:00",
                                         "end_time": "09:30", "duration_minutes": 30, "raw_payload": meta})
        p = self.propose("OMNIFY-2")
        self.assertEqual(p["minutes"], 50)  # 80 - 30, no "hasta ahora"

    def test_pending_proposal_of_another_ticket_is_reserved(self):
        plane.save_proposal("OMNIFY-1", self.propose("OMNIFY-1"))
        self.assertFalse(self.propose("OMNIFY-2")["ok"])

    def test_buckets_without_footprint_never_get_a_proposal(self):
        p = plane.build_proposal(self.conn, self.args(), "coordination", "agent:claude", "OPS-1")
        self.assertFalse(p["ok"])


class Window(Base):
    def test_explicit_window(self):
        p = self.propose(since="09:30", until="10:00")
        self.assertEqual(p["minutes"], 30)
        self.assertEqual(p["window_override"]["since"], local(9, 30).isoformat())

    def test_invalid_windows(self):
        self.assertIn("anterior", self.propose(since="10:00", until="09:00")["reason"])
        self.assertIn("medianoche", self.propose(since="2026-10-28T22:00:00-05:00", until="09:00")["reason"])
        self.assertIn("inválida", self.propose(since="mañana")["reason"])

    def test_future_until_is_clipped(self):
        p = self.propose(since="10:40", until="23:59")
        self.assertTrue(p["ok"])
        self.assertTrue(any("futuro" in w for w in p["warnings"]))

    def test_window_without_events(self):
        self.assertFalse(self.propose(since="06:00", until="07:00")["ok"])

    def test_since_inside_registered_time_only_counts_the_remainder(self):
        self.register("OMNIFY-1", self.propose(since="09:00", until="09:30"))
        p = self.propose("OMNIFY-2", since="09:15", until="10:00")
        self.assertEqual(p["minutes"], 30)  # 09:30-10:00; lo de 09:15-09:30 ya estaba registrado
        self.assertTrue(any("excluyeron" in w for w in p["warnings"]))


class PastDays(Base):
    def test_date_measures_a_previous_day(self):
        past = [t - timedelta(days=1) for t in STAMPS]
        sc.timestamps = lambda agent, sid, **kw: past
        p = self.propose(date="2026-10-28")
        self.assertTrue(p["ok"])
        self.assertEqual((p["minutes"], p["date"]), (80, "2026-10-28"))
        self.assertFalse(self.propose().get("ok") and self.propose()["minutes"] == 80)  # hoy no ve lo de ayer

    def test_previous_day_has_its_own_coverage(self):
        past = [t - timedelta(days=1) for t in STAMPS]
        sc.timestamps = lambda agent, sid, **kw: past
        first = self.propose(date="2026-10-28")
        self.register("OMNIFY-1", first)
        self.assertFalse(self.propose("OMNIFY-2", date="2026-10-28")["ok"])

    def test_since_until_are_relative_to_the_requested_day(self):
        past = [t - timedelta(days=1) for t in STAMPS]
        sc.timestamps = lambda agent, sid, **kw: past
        p = self.propose(date="2026-10-28", since="09:30", until="10:00")
        self.assertEqual((p["minutes"], p["date"]), (30, "2026-10-28"))

    def test_invalid_and_future_dates(self):
        self.assertIn("YYYY-MM-DD", self.propose(date="28/10/2026")["reason"])
        self.assertIn("futura", self.propose(date="2026-10-30")["reason"])

    def test_focus_marks_of_a_past_day(self):
        past = [t - timedelta(days=1) for t in STAMPS]
        sc.timestamps = lambda agent, sid, **kw: past
        self.mark("OMNIFY-1", local(9) - timedelta(days=1), local(9, 30) - timedelta(days=1))
        self.assertEqual(self.propose("OMNIFY-1", date="2026-10-28")["minutes"], 30)


class Focus(Base):
    def test_each_ticket_gets_only_its_own_intervals(self):
        self.mark("OMNIFY-1", local(9), local(9, 30))
        self.mark("OMNIFY-2", local(9, 30), local(10))
        self.assertEqual(self.propose("OMNIFY-1")["minutes"], 30)
        self.assertEqual(self.propose("OMNIFY-2")["minutes"], 30)
        self.assertEqual(self.propose("OMNIFY-1")["attribution"], "focus")

    def test_ticket_without_focus_is_refused_when_marks_exist(self):
        self.mark("OMNIFY-1", local(9), local(10))
        p = self.propose("OMNIFY-3")
        self.assertFalse(p["ok"])
        self.assertIn("focus", p["reason"])

    def test_unattributed_time_is_reported_not_distributed(self):
        self.mark("OMNIFY-1", local(9), local(9, 30))
        p = self.propose("OMNIFY-1")
        self.assertEqual(p["minutes"], 30)
        self.assertGreaterEqual(p["unattributed_minutes"], 50)

    def test_interleaved_a_b_a_keeps_clock_per_ticket(self):
        self.mark("OMNIFY-1", local(9), local(9, 20))
        self.mark("OMNIFY-2", local(9, 20), local(9, 40))
        self.mark("OMNIFY-1", local(9, 40), local(10))
        a = self.propose("OMNIFY-1")
        self.assertEqual(a["minutes"], 40)
        self.assertEqual(len(a["segments"]), 2)  # dos tramos: no un rango 09:00-10:00 que pise a B
        self.register("OMNIFY-1", a)
        b = self.propose("OMNIFY-2")
        self.assertEqual(b["minutes"], 20)

    def test_open_mark_runs_until_now(self):
        self.mark("OMNIFY-1", local(10, 40))
        self.assertEqual(self.propose("OMNIFY-1")["minutes"], 20)


class Split(Base):
    def args_(self):
        return self.args()

    def test_split_is_exact_contiguous_and_disjoint(self):
        result = plane.build_split(self.conn, self.args_(), "OMNIFY-1=50%,OMNIFY-2=rest", "agent:claude")
        self.assertTrue(result["ok"])
        a, b = result["parts"]["OMNIFY-1"], result["parts"]["OMNIFY-2"]
        self.assertEqual((a["minutes"], b["minutes"]), (40, 40))
        runs_a, runs_b = plane._proposal_runs(a), plane._proposal_runs(b)
        self.assertEqual(sc.intersect(runs_a, runs_b), [])
        self.assertEqual(runs_a[-1][1], runs_b[0][0])

    def test_any_acceptance_order_does_not_double_count(self):
        result = plane.build_split(self.conn, self.args_(), "OMNIFY-1=25%,OMNIFY-2=rest", "agent:claude")
        plane.save_group(result["group"], result["parts"])
        self.register("OMNIFY-2", result["parts"]["OMNIFY-2"])  # B primero
        plane.consume_proposal("OMNIFY-2", SID)
        self.assertEqual(plane.load_recent_proposal("OMNIFY-1")["minutes"], 20)  # A sigue disponible
        self.register("OMNIFY-1", plane.load_recent_proposal("OMNIFY-1"))
        self.assertFalse(self.propose("OMNIFY-3")["ok"])  # todo quedó asignado

    def test_split_errors(self):
        for spec in ("OMNIFY-1=70%,OMNIFY-2=50%", "OMNIFY-1=100%,OMNIFY-2=rest", "OMNIFY-1=10m,OMNIFY-1=rest"):
            self.assertFalse(plane.build_split(self.conn, self.args_(), spec, "agent:claude")["ok"], spec)

    def test_new_proposal_for_a_pending_split_ticket_is_not_recomputed(self):
        result = plane.build_split(self.conn, self.args_(), "OMNIFY-1=50%,OMNIFY-2=rest", "agent:claude")
        plane.save_group(result["group"], result["parts"])
        pending = plane.load_recent_proposal("OMNIFY-1")
        self.assertEqual(pending["split"]["group"], result["group"])

    def test_store_consume_and_ttl(self):
        plane.save_proposal("OMNIFY-1", {"ok": True, "session_id": SID, "segments": []})
        self.assertIsNotNone(plane.load_recent_proposal("OMNIFY-1"))
        plane.consume_proposal("OMNIFY-1", SID)
        self.assertIsNone(plane.load_recent_proposal("OMNIFY-1"))
        plane.save_proposal("OMNIFY-1", {"ok": True, "session_id": SID, "segments": []})
        with open(config.proposal_file()) as f:
            data = json.load(f)
        for entry in data["proposals"].values():
            entry["ts"] -= plane.PROPOSAL_TTL_SECONDS + 5
        with open(config.proposal_file(), "w") as f:
            json.dump(data, f)
        self.assertIsNone(plane.load_recent_proposal("OMNIFY-1"))


class Terminals(Base):
    def test_two_sessions_do_not_clobber_each_other(self):
        plane.save_proposal("OMNIFY-1", {"ok": True, "session_id": "SESSION-X", "minutes": 30, "segments": []})
        plane.save_proposal("OMNIFY-1", {"ok": True, "session_id": "SESSION-Y", "minutes": 99, "segments": []})
        self.assertEqual(plane.load_recent_proposal("OMNIFY-1", "SESSION-X")["minutes"], 30)
        self.assertEqual(plane.load_recent_proposal("OMNIFY-1", "SESSION-Y")["minutes"], 99)
        self.assertIsNone(plane.load_recent_proposal("OMNIFY-1"))  # sin saber quién eres no se adivina
        plane.consume_proposal("OMNIFY-1", "SESSION-X")
        self.assertIsNone(plane.load_recent_proposal("OMNIFY-1", "SESSION-X"))
        self.assertEqual(plane.load_recent_proposal("OMNIFY-1", "SESSION-Y")["minutes"], 99)

    def test_pending_of_another_session_is_not_reserved(self):
        other = dict(self.propose("OMNIFY-1"), session_id="SESSION-OTHER")
        plane.save_proposal("OMNIFY-1", other)
        self.assertTrue(self.propose("OMNIFY-2")["ok"])


class Corrections(Base):
    OLD = {"date": "2026-10-29", "start_time": "09:00", "end_time": "11:00", "duration_minutes": 80, "track": "main",
           "worker_type": "agent:claude", "capacity_bucket": "deep_work", "notes": "n",
           "segments": [{"start": "09:00", "end": "10:00", "minutes": 60}, {"start": "10:40", "end": "11:00", "minutes": 20}],
           "measured_by": {"kind": "proposal", "session": SID}}

    def test_block_is_replaced_not_duplicated_and_visible_text_is_kept(self):
        html = "<p>texto visible</p>\n" + plane.worklog_metadata_block(self.OLD)
        new_meta = plane.corrected_metadata(self.OLD, 80, track="review")
        out = plane.replace_metadata_block(html, new_meta)
        self.assertEqual(out.count("PLANE_WORKLOG_METADATA"), 1)
        self.assertTrue(out.startswith("<p>texto visible</p>"))
        self.assertEqual(plane.extract_metadata_from_comment(out)["track"], "review")

    def test_correction_keeps_session_and_leaves_a_trail(self):
        meta = plane.corrected_metadata(self.OLD, 80, capacity_bucket="tooling_dx", edited_at="2026-10-29T20:00:00+00:00")
        self.assertEqual(meta["measured_by"]["session"], SID)
        self.assertEqual((meta["measured_by"]["kind"], meta["measured_by"]["was"]), ("corrected", "proposal"))
        self.assertEqual((meta["previous_duration_minutes"], meta["capacity_bucket"]), (80, "tooling_dx"))
        self.assertEqual(meta["segments"], self.OLD["segments"])

    def test_changing_duration_needs_force_when_segments_exist(self):
        with self.assertRaises(ValueError):
            plane.corrected_metadata(self.OLD, 50)
        meta = plane.corrected_metadata(self.OLD, 50, force=True)
        self.assertNotIn("segments", meta)
        self.assertEqual(meta["duration_minutes"], 50)
        # sin tramos, el bounding start-end sigue cubriendo la sesión (no se vuelve a contar)
        self.conn.execute("DELETE FROM worklogs")
        plane.upsert_worklog(self.conn, {"ticket_id": "OMNIFY-1", "track": "main", "date": "2026-10-29", "start_time": meta["start_time"],
                                         "end_time": meta["end_time"], "duration_minutes": 50, "raw_payload": meta})
        self.assertFalse(self.propose("OMNIFY-2")["ok"])

    def test_sync_after_a_correction_leaves_one_row_per_comment(self):
        plane.upsert_worklog(self.conn, {"ticket_id": "OMNIFY-1", "track": "main", "date": "2026-10-29", "start_time": "09:00", "end_time": "11:00",
                                         "duration_minutes": 80, "plane_comment_id": "c1", "raw_payload": self.OLD})
        meta = plane.corrected_metadata(self.OLD, 80, track="review")
        with self.conn:
            self.conn.execute("DELETE FROM worklogs WHERE plane_comment_id = ?", ("c1",))
        plane.upsert_worklog(self.conn, {"ticket_id": "OMNIFY-1", "track": "review", "date": meta["date"], "start_time": meta["start_time"],
                                         "end_time": meta["end_time"], "duration_minutes": 80, "plane_comment_id": "c1", "raw_payload": meta})
        # el sync re-importa el bloque ya corregido: misma clave -> una sola fila
        parsed = plane.extract_metadata_from_comment(plane.worklog_metadata_block(meta))
        plane.upsert_worklog(self.conn, {"ticket_id": "OMNIFY-1", "track": parsed["track"], "date": parsed["date"], "start_time": parsed["start_time"],
                                         "end_time": parsed["end_time"], "duration_minutes": parsed["duration_minutes"], "plane_comment_id": "c1", "raw_payload": parsed})
        rows = self.conn.execute("SELECT track FROM worklogs WHERE plane_comment_id = 'c1'").fetchall()
        self.assertEqual([r["track"] for r in rows], ["review"])


class Reporting(Base):
    def test_expand_segments_and_flow_clock(self):
        p = self.propose()
        meta = {"segments": p["segments"], "measured_by": {"session": SID}}
        row = {"raw_payload": json.dumps(meta), "start_time": p["start_time"], "end_time": p["end_time"], "duration_minutes": p["minutes"], "notes": "x"}
        expanded = plane.expand_segments([row])
        self.assertEqual(len(expanded), 2)
        self.assertEqual(sum(r["duration_minutes"] for r in expanded), 80)
        entry = {"date": p["date"], "start_time": p["start_time"], "end_time": p["end_time"], "duration_minutes": 80, "segments": p["segments"]}
        flow = fm.compute_flow({"name": "x", "created_at": local(8), "completed_at": None, "state": "s"}, [],
                               {"s": {"name": "Progreso", "group": "started"}}, [entry], NOW)
        self.assertAlmostEqual(flow["effort_clock_minutes"], 80, delta=1)  # no 120 (rango envolvente)


if __name__ == "__main__":
    unittest.main()
