"""Historial de asignación: parseo del evento, cobertura, barrido con presupuesto y limpieza al eliminar un ticket."""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from plane_cli import assignments, cache, cmd_delete, db  # noqa: E402
from plane_cli.circuit import PlaneUnavailable  # noqa: E402


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def put_issue(conn, n, updated="2026-10-20T10:00:00Z"):
    with conn:
        conn.execute("INSERT INTO issues_cache (id, sequence_id, ticket_id, project_id, title, state_name, state_group, priority, updated_at, plane_updated_at, assignees_json) "
                     "VALUES (?, ?, ?, 'p', 't', 'Progreso', 'started', 'none', 0, ?, '[]')", (f"i{n}", n, f"X-{n}", updated))
    return conn.execute("SELECT * FROM issues_cache WHERE id = ?", (f"i{n}",)).fetchone()


class Parsing(unittest.TestCase):
    def test_add_remove_and_both(self):
        add = {"id": "a1", "field": "assignees", "created_at": "t1", "new_identifier": "u1", "new_value": "Ana"}
        rem = {"id": "a2", "field": "assignees", "created_at": "t2", "old_identifier": "u1", "old_value": "Ana"}
        both = {"id": "a3", "field": "assignees", "created_at": "t3", "old_identifier": "u1", "new_identifier": "u2"}
        self.assertEqual([r[4:6] for r in assignments.assignment_rows(add, "i", "X-1")], [("added", "u1")])
        self.assertEqual([r[4:6] for r in assignments.assignment_rows(rem, "i", "X-1")], [("removed", "u1")])
        self.assertEqual(sorted(r[4:6] for r in assignments.assignment_rows(both, "i", "X-1")), [("added", "u2"), ("removed", "u1")])

    def test_other_fields_and_incomplete_activities_are_ignored(self):
        self.assertEqual(assignments.assignment_rows({"id": "a", "field": "state", "created_at": "t", "new_identifier": "s"}, "i", "X-1"), [])
        self.assertEqual(assignments.assignment_rows({"id": "a", "field": "assignees", "new_identifier": "u"}, "i", "X-1"), [])

    def test_assignee_ids_accepts_strings_and_objects(self):
        self.assertEqual(cache.assignee_ids({"assignees": ["u1", {"id": "u2"}, None, {}]}), ["u1", "u2"])
        self.assertEqual(cache.assignee_ids({}), [])
        self.assertEqual(cache.assignee_ids({"assignees": None}), [])


class Sweep(unittest.TestCase):
    def setUp(self):
        self.conn = memory_db()
        self.rows = [put_issue(self.conn, n, f"2026-10-{10 + n}T10:00:00Z") for n in (1, 2, 3)]

    def fetcher(self, fail_on=None):
        calls = []

        def fetch(row):
            if row["id"] == fail_on:
                raise PlaneUnavailable("rate", "no")
            calls.append(row["id"])
            with self.conn:
                self.conn.execute("INSERT OR REPLACE INTO flow_fetch (issue_id, fetched_at, issue_updated_at, assignments_fetched) VALUES (?, 0, ?, 1)",
                                  (row["id"], row["plane_updated_at"]))
        return fetch, calls

    def test_budget_most_recent_first_and_resume(self):
        fetch, calls = self.fetcher()
        self.assertEqual(assignments.sweep_history(self.conn, "", "", "", self.rows, 2, fetch), (2, False, 1))
        self.assertEqual(calls, ["i3", "i2"])
        self.assertEqual(assignments.history_coverage(self.conn, ["i1", "i2", "i3"]), (2, 3))
        self.assertEqual(assignments.sweep_history(self.conn, "", "", "", self.rows, 5, fetch), (1, False, 0))
        self.assertEqual(calls, ["i3", "i2", "i1"])

    def test_interruption_keeps_what_was_saved(self):
        fetch, calls = self.fetcher(fail_on="i2")
        self.assertEqual(assignments.sweep_history(self.conn, "", "", "", self.rows, 5, fetch), (1, True, 2))
        self.assertEqual(calls, ["i3"])
        self.assertEqual(assignments.history_coverage(self.conn, ["i1", "i2", "i3"]), (1, 3))

    def test_a_ticket_changed_in_plane_is_pending_again(self):
        fetch, _ = self.fetcher()
        assignments.sweep_history(self.conn, "", "", "", self.rows, 5, fetch)
        with self.conn:
            self.conn.execute("UPDATE issues_cache SET plane_updated_at = '2026-11-01T00:00:00Z' WHERE id = 'i1'")
        self.assertEqual(assignments.history_coverage(self.conn, ["i1", "i2", "i3"]), (2, 3))


class DeleteCleanup(unittest.TestCase):
    def test_forgetting_a_ticket_removes_its_assignment_events(self):
        conn = memory_db()
        put_issue(conn, 1)
        assignments.record_assignments(conn, [("a:added", "i1", "X-1", "t", "added", "u1", "Ana")])
        cmd_delete._forget_locally(conn, "i1", "X-1")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM assignment_events").fetchone()[0], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM issues_cache").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
