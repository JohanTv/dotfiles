import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import plane  # noqa: E402
import session_clock as sc  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
SID = "11111111-2222-3333-4444-555555555555"


def iso(minutes):
    return (T0 + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class ParseTime(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(sc.parse_time("2026-10-29T12:00:00.123456789Z"), T0.replace(microsecond=123456))
        self.assertEqual(sc.parse_time(int(T0.timestamp() * 1000)), T0)
        self.assertEqual(sc.parse_time(int(T0.timestamp())), T0)
        self.assertIsNone(sc.parse_time("basura"))
        self.assertIsNone(sc.parse_time(None))


class Measure(unittest.TestCase):
    def test_gross_net_and_pauses(self):
        stamps = [T0, T0 + timedelta(minutes=5), T0 + timedelta(minutes=40), T0 + timedelta(minutes=45)]
        m = sc.measure(stamps, T0, T0 + timedelta(hours=2))
        self.assertEqual(m["gross_minutes"], 45)
        self.assertEqual(m["net_minutes"], 10)
        self.assertEqual(m["pauses"], 1)

    def test_window_clips_events(self):
        stamps = [T0, T0 + timedelta(minutes=5), T0 + timedelta(minutes=9)]
        m = sc.measure(stamps, T0 + timedelta(minutes=4), T0 + timedelta(hours=1))
        self.assertEqual(m["events"], 2)
        self.assertEqual(m["net_minutes"], 4)

    def test_empty(self):
        self.assertEqual(sc.measure([], T0, T0 + timedelta(hours=1))["events"], 0)


class ClaudeAdapter(unittest.TestCase):
    def test_unordered_missing_and_broken_lines(self):
        with tempfile.TemporaryDirectory() as root:
            folder = os.path.join(root, "-proj")
            os.makedirs(os.path.join(folder, SID, "subagents"))
            lines = [
                json.dumps({"timestamp": iso(10), "message": "secreto"}),
                json.dumps({"type": "mode"}),
                "{no es json",
                json.dumps({"timestamp": iso(0)}),
                json.dumps({"timestamp": iso(5)}),
            ]
            with open(os.path.join(folder, f"{SID}.jsonl"), "w") as f:
                f.write("\n".join(lines))
            with open(os.path.join(folder, SID, "subagents", "agent-x.jsonl"), "w") as f:
                f.write(json.dumps({"timestamp": iso(500)}))
            got = sc.claude_timestamps(SID, root)
            self.assertEqual(got, [T0, T0 + timedelta(minutes=5), T0 + timedelta(minutes=10)])

    def test_invalid_id_and_missing_file(self):
        self.assertEqual(sc.claude_timestamps("../../etc", "/tmp"), [])
        self.assertEqual(sc.claude_timestamps(SID, "/no/existe"), [])


def make_opencode(path, sessions, messages):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE session_v2 (id TEXT PRIMARY KEY, directory TEXT, parent_id TEXT, time_updated INTEGER)")
    conn.execute("CREATE TABLE session_message (id TEXT PRIMARY KEY, session_id TEXT, type TEXT, time_created INTEGER, data TEXT)")
    conn.executemany("INSERT INTO session_v2 VALUES (?,?,?,?)", sessions)
    conn.executemany("INSERT INTO session_message VALUES (?,?,?,?,?)", messages)
    conn.commit()
    conn.close()


def ms(minutes):
    return int((T0 + timedelta(minutes=minutes)).timestamp() * 1000)


class OpencodeAdapter(unittest.TestCase):
    def test_timestamps_and_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "oc.db")
            make_opencode(
                db,
                [("ses_aaaaaaaa", "/w", None, ms(30)), ("ses_bbbbbbbb", "/w", None, ms(200)), ("ses_cccccccc", "/w", "ses_aaaaaaaa", ms(31))],
                [("m1", "ses_aaaaaaaa", "user", ms(0), "x"), ("m2", "ses_aaaaaaaa", "assistant", ms(3), "x")],
            )
            self.assertEqual(sc.opencode_timestamps("ses_aaaaaaaa", db), [T0, T0 + timedelta(minutes=3)])
            # ses_bbbbbbbb está lejos de ses_aaaaaaaa (>30 min) y ses_cccccccc es hija: no hay ambigüedad
            sid, origin, cands = sc.resolve_session("opencode", "/w", env={}, opencode_db=db)
            self.assertEqual((sid, cands), ("ses_bbbbbbbb", []))

    def test_ambiguous_sessions_are_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "oc.db")
            make_opencode(db, [("ses_aaaaaaaa", "/w", None, ms(10)), ("ses_bbbbbbbb", "/w", None, ms(20))], [])
            sid, origin, cands = sc.resolve_session("opencode", "/w", env={}, opencode_db=db)
            self.assertIsNone(sid)
            self.assertEqual(len(cands), 2)

    def test_env_and_explicit_win(self):
        self.assertEqual(sc.resolve_session("claude", "/w", env={"CLAUDE_CODE_SESSION_ID": SID})[0], SID)
        self.assertEqual(sc.resolve_session("claude", "/w", explicit=SID, env={})[0], SID)
        self.assertIsNone(sc.resolve_session("claude", "/w", explicit="a b", env={})[0])


class AgyAdapter(unittest.TestCase):
    def test_milestones(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "agy.db")
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE conversation_summaries (conversation_id TEXT, last_modified_time TEXT, "
                "last_user_input_time TEXT, workspace_uris TEXT, parent_conversation_id TEXT)"
            )
            conn.execute(
                "INSERT INTO conversation_summaries VALUES (?,?,?,?,?)",
                (SID, "2026-10-29T12:30:00.123456789Z", "2026-10-29T12:10:00Z", "file:///w", None),
            )
            conn.commit()
            conn.close()
            got = sc.agy_timestamps(SID, db)
            self.assertEqual(len(got), 2)
            self.assertEqual(sc.resolve_session("agy", "/w", env={}, agy_db=db)[0], SID)


class PlaneIntegration(unittest.TestCase):
    def test_derived_start_never_crosses_midnight(self):
        end = datetime(2026, 10, 29, 0, 20)
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(plane.derived_start(end, 60), "00:00")
        self.assertIn("medianoche", err.getvalue())
        self.assertEqual(plane.derived_start(datetime(2026, 10, 29, 10, 0), 30), "09:30")

    def test_worklog_metadata_block_roundtrip(self):
        meta = {"date": "2026-10-29", "start_time": "10:00", "notes": "a -- b --> c", "duration_minutes": 5}
        block = plane.worklog_metadata_block(meta)
        self.assertEqual(block.count("-->"), 1)
        self.assertEqual(plane.extract_metadata_from_comment("<p>x</p>" + block), meta)

    def test_umbrella_buckets_get_no_proposal(self):
        class Args:
            agent = "claude"
            session = None

        result = plane.build_proposal(None, Args, "toil_support", "agent:claude")
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
