"""Autor de las horas: se guarda, no se pisa con un valor desconocido, y decide qué es "tuyo" en `list --involved` y en `delete`."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from test_assignments import memory_db, put_issue  # noqa: E402
from plane_cli import cmd_delete, list_filtered, resolve, worklog  # noqa: E402

ME, OTHER = "me-uuid", "other-uuid"


def entry(start, minutes=30, author=None, comment_id=None):
    return {"ticket_id": "X-1", "track": "t", "date": "2026-10-20", "start_time": start, "end_time": "11:00", "duration_minutes": minutes,
            "plane_comment_id": comment_id, "author_id": author, "raw_payload": {}}


class Upsert(unittest.TestCase):
    def test_author_is_stored_and_not_erased_by_an_unknown_one(self):
        conn = memory_db()
        worklog.upsert_worklog(conn, entry("10:00", author=ME))
        worklog.upsert_worklog(conn, entry("10:00", minutes=45, author=None))
        row = conn.execute("SELECT author_id, duration_minutes FROM worklogs").fetchone()
        self.assertEqual((row["author_id"], row["duration_minutes"]), (ME, 45))

    def test_a_known_author_fills_an_unsigned_row(self):
        conn = memory_db()
        worklog.upsert_worklog(conn, entry("10:00", author=None))
        worklog.upsert_worklog(conn, entry("10:00", author=OTHER))
        self.assertEqual(conn.execute("SELECT author_id FROM worklogs").fetchone()[0], OTHER)


class KnownActor(unittest.TestCase):
    def test_environment_cached_username_and_nothing(self):
        conn = memory_db()
        with mock.patch.dict(os.environ, {"PLANE_ACTOR_UUID": " u1 "}, clear=True):
            self.assertEqual(resolve.known_actor(conn, "ws"), "u1")
        with mock.patch.dict(os.environ, {"PLANE_USERNAME": "Ana"}, clear=True):
            self.assertIsNone(resolve.known_actor(conn, "ws"))
            resolve._remember_actor(conn, "actor:ws:ana", "u2")
            self.assertEqual(resolve.known_actor(conn, "ws"), "u2")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(resolve.known_actor(conn, "ws"))


class Involvement(unittest.TestCase):
    def reasons(self, rows):
        conn = memory_db()
        put_issue(conn, 1)
        for i, (minutes, author) in enumerate(rows):
            worklog.upsert_worklog(conn, entry(f"1{i}:00", minutes=minutes, author=author))
        items, _ = list_filtered._select(conn, ["p"], "involved", ME, False)
        return [r for i in items for r in i["reasons"]]

    def test_only_my_hours_count_as_mine(self):
        self.assertEqual(self.reasons([(30, ME), (20, ME), (90, OTHER)]), ["horas tuyas (50 min)"])

    def test_unsigned_hours_are_labelled_not_claimed(self):
        self.assertEqual(self.reasons([(25, None)]), ["horas sin autor registrado (25 min)"])

    def test_someone_elses_hours_alone_do_not_involve_me(self):
        self.assertEqual(self.reasons([(90, OTHER)]), [])


class DeleteAssessment(unittest.TestCase):
    def plan(self, author):
        conn = memory_db()
        worklog.upsert_worklog(conn, entry("10:00", author=author))
        return cmd_delete._assess(conn, "X-1", [], ME)

    def test_local_only_hours_by_me_or_unsigned_are_own(self):
        for author in (ME, None):
            plan = self.plan(author)
            self.assertEqual((plan["hours_own"], plan["hours_foreign"]), (1, 0))

    def test_local_only_hours_by_someone_else_block_the_delete(self):
        plan = self.plan(OTHER)
        self.assertEqual((plan["hours_own"], plan["hours_foreign"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
