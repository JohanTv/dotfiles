"""Guarda de duplicados en `create`: caché local, marca de envío sin confirmar y refresco solo cuando hace falta."""
import io
import os
import sqlite3
import sys
import time
import unittest
from argparse import Namespace
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from plane_cli import cmd_tickets_write as ctw  # noqa: E402
from plane_cli import create_guard as cg  # noqa: E402
from plane_cli import db  # noqa: E402
from plane_cli.api import PlaneUnavailable  # noqa: E402

PROJECT = "proj-1"


def iso(hours_ago):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


class Base(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        db.init_db(self.conn)
        self.refreshes = 0
        self.refresh_effect = lambda: None
        self._sync = cg.sync_issues_cache
        cg.sync_issues_cache = self._fake_sync

    def tearDown(self):
        cg.sync_issues_cache = self._sync
        self.conn.close()

    def _fake_sync(self, *args, **kwargs):
        self.refreshes += 1
        self.refresh_effect()

    def add_issue(self, title, hours_ago, ticket="OMNIFY-1", project=PROJECT):
        with self.conn:
            self.conn.execute(
                "INSERT INTO issues_cache (id, sequence_id, ticket_id, project_id, title, state_name, state_group, priority, labels_csv, updated_at, created_at) "
                "VALUES (?, 1, ?, ?, ?, 'Backlog', 'backlog', 'none', '', ?, ?)", (ticket + project, ticket, project, title, time.time(), iso(hours_ago)))

    def duplicates(self, title):
        return cg.recent_duplicates(self.conn, "http://x", "k", "ws", PROJECT, "OMNIFY", title)


class RecentDuplicates(Base):
    def test_matches_normalized_title_inside_the_window_without_network(self):
        self.add_issue("[FEAT] Algo   nuevo", 2)
        found = self.duplicates("  [feat] algo nuevo ")
        self.assertEqual([t for t, _ in found], ["OMNIFY-1"])
        self.assertEqual(self.refreshes, 0)  # sin marca pendiente no hay llamada a Plane

    def test_ignores_old_other_project_and_other_title(self):
        self.add_issue("Viejo", 30, ticket="OMNIFY-2")
        self.add_issue("Otro proyecto", 1, ticket="OPS-3", project="proj-2")
        self.add_issue("Distinto", 1, ticket="OMNIFY-4")
        self.assertEqual(self.duplicates("Viejo"), [])
        self.assertEqual(self.duplicates("Otro proyecto"), [])
        self.assertEqual(self.duplicates("Nuevo"), [])

    def test_unconfirmed_mark_forces_a_refresh_that_can_reveal_the_ticket(self):
        cg.mark_unconfirmed(self.conn, PROJECT, "Crear algo")
        self.refresh_effect = lambda: self.add_issue("Crear algo", 0)
        found = self.duplicates("Crear algo")
        self.assertEqual((self.refreshes, [t for t, _ in found]), (1, ["OMNIFY-1"]))
        self.assertTrue(cg._has_open_mark(self.conn, PROJECT, "Crear algo"))  # no se limpia: sigue bloqueado

    def test_refresh_without_match_clears_the_mark_so_a_retry_is_allowed(self):
        cg.mark_unconfirmed(self.conn, PROJECT, "Crear algo")
        self.assertEqual(self.duplicates("Crear algo"), [])
        self.assertFalse(cg._has_open_mark(self.conn, PROJECT, "Crear algo"))

    def test_refresh_failure_keeps_the_mark(self):
        cg.mark_unconfirmed(self.conn, PROJECT, "Crear algo")

        def down():
            raise PlaneUnavailable("timeout", "no")

        self.refresh_effect = down
        self.assertEqual(self.duplicates("Crear algo"), [])
        self.assertTrue(cg._has_open_mark(self.conn, PROJECT, "Crear algo"))

    def test_expired_mark_is_ignored(self):
        cg.mark_unconfirmed(self.conn, PROJECT, "Crear algo")
        with self.conn:
            self.conn.execute("UPDATE sync_metadata SET updated_at = ?", (time.time() - 25 * 3600,))
        self.duplicates("Crear algo")
        self.assertEqual(self.refreshes, 0)


class SubmitIssue(Base):
    def setUp(self):
        super().setUp()
        self.posts = []
        self.post_result = {"id": "new", "sequence_id": 9}
        self._api = ctw.api_request
        ctw.api_request = self._fake_api

    def tearDown(self):
        ctw.api_request = self._api
        super().tearDown()

    def _fake_api(self, url, key, method="GET", data=None, **kw):
        self.posts.append(data)
        if isinstance(self.post_result, BaseException):
            raise self.post_result
        return self.post_result

    def submit(self, title="Crear algo", allow=False):
        args = Namespace(allow_duplicate=allow)
        return ctw._submit_issue(args, self.conn, "http://x", "k", "ws", PROJECT, "OMNIFY", {"name": title})

    def test_success_posts_once_and_leaves_no_mark(self):
        self.assertEqual(self.submit()["id"], "new")
        self.assertEqual(len(self.posts), 1)
        self.assertFalse(cg._has_open_mark(self.conn, PROJECT, "Crear algo"))

    def test_duplicate_in_cache_is_refused_without_posting(self):
        self.add_issue("Crear algo", 1, ticket="OMNIFY-8")
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            self.submit()
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("OMNIFY-8", err.getvalue())
        self.assertIn("--allow-duplicate", err.getvalue())
        self.assertEqual(self.posts, [])

    def test_allow_duplicate_skips_the_check(self):
        self.add_issue("Crear algo", 1)
        self.assertEqual(self.submit(allow=True)["id"], "new")

    def test_unconfirmed_post_blocks_the_retry_when_the_ticket_exists(self):
        self.post_result = PlaneUnavailable("read_timeout", "unknown")
        with self.assertRaises(PlaneUnavailable):
            self.submit()
        self.assertTrue(cg._has_open_mark(self.conn, PROJECT, "Crear algo"))
        self.refresh_effect = lambda: self.add_issue("Crear algo", 0, ticket="OMNIFY-9")  # Plane sí lo aplicó
        self.post_result = {"id": "otro"}
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.submit()
        self.assertEqual(len(self.posts), 1)  # el reintento no llegó a enviarse

    def test_unconfirmed_post_allows_the_retry_when_the_ticket_does_not_exist(self):
        self.post_result = PlaneUnavailable("read_timeout", "unknown")
        with self.assertRaises(PlaneUnavailable):
            self.submit()
        self.post_result = {"id": "ok"}
        self.assertEqual(self.submit()["id"], "ok")
        self.assertEqual((len(self.posts), self.refreshes), (2, 1))

    def test_request_that_never_left_clears_the_mark(self):
        self.post_result = PlaneUnavailable("refused", "no")
        with self.assertRaises(PlaneUnavailable):
            self.submit()
        self.assertFalse(cg._has_open_mark(self.conn, PROJECT, "Crear algo"))

    def test_definitive_error_clears_the_mark(self):
        self.post_result = SystemExit(1)
        with self.assertRaises(SystemExit):
            self.submit()
        self.assertFalse(cg._has_open_mark(self.conn, PROJECT, "Crear algo"))


if __name__ == "__main__":
    unittest.main()
