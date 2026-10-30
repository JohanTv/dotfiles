"""Base local: permisos restrictivos de la caché y restricciones del esquema de la cola de salida."""
import os
import sqlite3
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402
from plane_cli import config, db  # noqa: E402


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


class Permissions(unittest.TestCase):
    def test_cli_creates_cache_private(self):
        sb = gs.Sandbox()
        self.addCleanup(sb.close)
        self.assertEqual(sb.run(["health"])[0], 0)
        cache = os.path.join(sb.home, ".cache", "plane")
        self.assertEqual(mode(cache), 0o700)
        self.assertEqual(mode(os.path.join(cache, "worklogs.db")), 0o600)
        for name in ("worklogs.db-wal", "worklogs.db-shm"):
            if os.path.exists(os.path.join(cache, name)):
                self.assertEqual(mode(os.path.join(cache, name)) & 0o077, 0, name)

    def test_existing_loose_permissions_are_tightened(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cache = os.path.join(tmp.name, "plane")
        os.makedirs(cache)
        os.chmod(cache, 0o755)
        path = os.path.join(cache, "worklogs.db")
        sqlite3.connect(path).close()
        os.chmod(path, 0o644)
        with mock.patch.object(config, "CACHE_DIR", cache):
            db.get_db().close()
        self.assertEqual((mode(cache), mode(path)), (0o700, 0o600))


class OutboxSchema(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)
        db.init_db(self.conn)
        db.init_db(self.conn)

    def add(self, client_id, state="pending", track="main"):
        self.conn.execute(
            "INSERT INTO outbox (client_id, ticket_ref, payload_json, wl_ticket_id, wl_track, wl_date, wl_start_time, state, created_at, updated_at) "
            "VALUES (?, 'OPS-1', '{}', 'OPS-1', ?, '2026-10-30', '10:00', ?, 'x', 'x')", (client_id, track, state))

    def test_open_worklog_key_is_unique(self):
        self.add("pt-1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.add("pt-2")
        self.add("pt-3", track="otro")

    def test_closed_items_free_the_key(self):
        self.add("pt-1", state="sent")
        self.add("pt-2", state="dropped")
        self.add("pt-3")

    def test_state_and_client_id_are_constrained(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.add("pt-1", state="bogus")
        self.add("pt-2", state="sent")
        with self.assertRaises(sqlite3.IntegrityError):
            self.add("pt-2", state="sent", track="otro")


if __name__ == "__main__":
    unittest.main()
