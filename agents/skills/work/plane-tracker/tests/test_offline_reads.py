"""Lecturas sin conexión: stale-while-error, snapshots de `get`, `list` desde caché y `focus set` local."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import clock_support  # noqa: E402
import golden_support as gs  # noqa: E402
from plane_cli import cache, db, timeutil  # noqa: E402

OFF = {"PLANE_OFFLINE": "1"}


class Offline(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)

    def cli(self, *args, offline=False, ok=True):
        code, out, err = self.sb.run(list(args), env_set=OFF if offline else None)
        self.assertNotIn("Traceback", err)
        if ok:
            self.assertEqual(code, 0, err)
        return code, out, err

    def age(self, table, seconds):
        path = os.path.join(self.sb.home, ".cache", "plane", "worklogs.db")
        conn = sqlite3.connect(path)
        conn.execute(f"UPDATE {table} SET updated_at = updated_at - ?" if table != "issue_snapshots" else "UPDATE issue_snapshots SET fetched_at = fetched_at - ?", (seconds,))
        if table == "issues_cache":
            conn.execute("UPDATE issue_sync SET as_of = as_of - ?", (seconds,))
        conn.commit()
        conn.close()

    def mark(self):
        return len(self.sb.fake.requests)

    # --- list --------------------------------------------------------------
    def test_list_text_with_open_circuit_serves_the_stale_cache_and_says_so_in_the_output(self):
        self.cli("list", "--text", "formulario")
        self.age("issues_cache", 2 * 3600)
        before = self.mark()
        self.sb.write_circuit(opened_ago=5)
        code, out, err = self.cli("list", "--text", "formulario")
        self.assertIn("OMNIFY-1", out)
        self.assertIn("Datos locales de hace 2 h; Plane no respondió.", out)
        self.assertEqual(err, "")
        self.assertEqual(self.mark(), before)

    def test_list_text_without_cache_exits_3(self):
        self.cli("projects")
        code, out, err = self.cli("list", "--text", "formulario", offline=True, ok=False)
        self.assertEqual(code, 3)
        self.assertIn("Plane no responde y no hay caché local de los tickets de OMNIFY.", err)

    def test_fresh_cache_never_warns(self):
        self.cli("list", "--text", "formulario")
        code, out, err = self.cli("list", "--text", "formulario", offline=True)
        self.assertEqual(err, "")

    def test_list_offline_from_cache(self):
        self.cli("list")
        self.age("issues_cache", 90 * 60)
        before = self.mark()
        code, out, err = self.cli("list", "--json", offline=True)
        doc = json.loads(out)
        self.assertEqual([r["ticket"] for r in doc["results"]], ["OMNIFY-1", "OMNIFY-2", "OMNIFY-3"])
        self.assertEqual(doc["coverage"]["source"], "cache")
        self.assertEqual((doc["coverage"]["stale"], doc["coverage"]["complete"], doc["coverage"]["age_s"]), (True, None, 5400))
        self.assertIn("cache_stale", [n["code"] for n in doc["notes"]])
        self.assertEqual(err, "", "lo que va en notes y coverage no se repite por stderr")
        code, out, err = self.cli("list", offline=True)
        self.assertIn("OMNIFY-1", out)
        self.assertIn("caché de hace 1 h", out)
        self.assertEqual(self.mark(), before)

    def test_list_without_cache_exits_3(self):
        self.cli("projects")
        code, out, err = self.cli("list", offline=True, ok=False)
        self.assertEqual(code, 3)
        self.assertIn("Plane no responde y no hay caché local de los tickets de OMNIFY.", err)
        code, out, err = self.cli("list", "--json", offline=True, ok=False)
        self.assertEqual((code, json.loads(out)["code"], err), (3, "no_cache", ""))

    # --- catálogos ------------------------------------------------------------
    def test_catalogs_stale_while_error(self):
        self.cli("projects")
        self.cli("labels")
        for table in ("projects", "labels"):
            self.age(table, 3 * 86400)
        code, out, err = self.cli("projects", offline=True)
        self.assertIn("OMNIFY", out)
        self.assertIn("Datos locales de hace 3 d; Plane no respondió.", out)
        self.assertEqual(err, "")
        code, out, err = self.cli("labels", "--refresh", offline=True)
        self.assertIn("backend", out)
        self.assertIn("Datos locales de hace 3 d", out)
        code, out, err = self.cli("labels", "--json", offline=True)
        doc = json.loads(out)
        self.assertEqual((doc["coverage"]["source"], doc["coverage"]["stale"], doc["coverage"]["complete"]), ("cache", True, None))

    def test_catalog_without_cache_exits_3(self):
        code, out, err = self.cli("projects", offline=True, ok=False)
        self.assertEqual((code, err), (3, "Plane no responde y no hay caché local de proyectos.\n"))

    # --- get ------------------------------------------------------------------
    def test_get_offline_from_snapshot(self):
        _, online, _ = self.cli("get", "OMNIFY-1", "--json")
        self.age("issue_snapshots", 125 * 60)
        before = self.mark()
        code, out, err = self.cli("get", "OMNIFY-1", offline=True)
        self.assertIn("Datos locales de hace 2 h; Plane no respondió.", out)
        self.assertIn("Avance del formulario", out)
        self.assertEqual(self.mark(), before)
        code, out, err = self.cli("get", "OMNIFY-1", "--json", offline=True)
        data = json.loads(out)
        self.assertEqual((data["coverage"]["source"], data["coverage"]["stale"], data["coverage"]["complete"], data["coverage"]["age_s"]), ("snapshot", True, None, 7500))
        fresh = json.loads(online)
        self.assertEqual((fresh["coverage"]["source"], fresh["coverage"]["complete"], "scope" in fresh), ("api", True, False))
        self.assertEqual(data["results"], fresh["results"], "la instantánea reproduce la fila de la lectura en línea")

    def test_get_snapshot_without_comments(self):
        self.cli("get", "OMNIFY-1", "--no-comments")
        code, out, err = self.cli("get", "OMNIFY-1", "--no-comments", offline=True)
        self.assertIn("Esta copia no incluye comentarios", out)
        code, out, err = self.cli("get", "OMNIFY-1", "--json", offline=True)
        self.assertNotIn("comments", json.loads(out)["results"][0])

    def test_no_comments_read_keeps_previous_comments(self):
        self.cli("get", "OMNIFY-1")
        self.cli("get", "OMNIFY-1", "--no-comments")
        code, out, err = self.cli("get", "OMNIFY-1", offline=True)
        self.assertIn("Avance del formulario", out)

    def test_get_falls_back_to_issue_metadata(self):
        self.cli("list")
        code, out, err = self.cli("get", "OMNIFY-2", offline=True)
        self.assertIn("Solo metadatos del listado", out)
        self.assertIn("Acortador de enlaces", out)
        self.assertIn("Completado", out)
        code, out, err = self.cli("get", "OMNIFY-2", "--json", offline=True)
        data = json.loads(out)
        self.assertTrue(data["coverage"]["stale"] and data["coverage"]["detail"]["metadata_only"])
        self.assertIs(data["coverage"]["complete"], None)

    def test_get_with_nothing_local_exits_3(self):
        self.cli("projects")
        code, out, err = self.cli("get", "OMNIFY-3", offline=True, ok=False)
        self.assertEqual((code, err), (3, "Plane no responde y no hay caché local de OMNIFY-3.\n"))

    def test_get_by_uuid_offline(self):
        uuid = "10000000-0000-4000-8000-000000000001"
        self.cli("get", uuid)
        code, out, err = self.cli("get", uuid, offline=True)
        self.assertIn("Validaciones de formulario SMS", out)

    # --- focus ----------------------------------------------------------------
    def test_focus_set_is_fully_local(self):
        sb = gs.Sandbox(with_session=True)
        self.addCleanup(sb.close)
        sess = ["--agent", "claude", "--session", gs.SESSION]
        code, out, err = sb.run(["focus", "set", "OMNIFY-2", *sess], env_set=OFF)
        self.assertEqual(code, 0, err)
        self.assertNotIn("terminal", err)
        self.assertEqual(sb.fake.requests, [])
        self.assertEqual(sb.run(["list", "--text", "x"])[0], 0)
        code, out, err = sb.run(["focus", "set", "OPS-13", *sess], env_set=OFF)
        code, out, err = sb.run(["focus", "set", "OMNIFY-2", *sess], env_set=OFF)
        self.assertEqual(code, 0, err)
        code, out, err = sb.run(["focus", "set", "OMNIFY-3", *sess], env_set=OFF)
        self.assertIn("estado terminal (cancelled)", err)


class Units(unittest.TestCase):
    def test_age_text(self):
        for seconds, text in ((5, "1 min"), (59 * 60, "59 min"), (3600, "1 h"), (23 * 3600 + 59 * 60, "23 h"), (86400, "1 d"), (5 * 86400, "5 d")):
            self.assertEqual(timeutil.age_text(seconds), text)

    def test_snapshot_pruning_and_partial_update(self):
        controlled = clock_support.Clock()  # la poda usa la edad de cada instantánea: el reloj es controlado
        with controlled.patch(), tempfile.TemporaryDirectory() as tmp:
            conn = sqlite3.connect(os.path.join(tmp, "t.db"))
            conn.row_factory = sqlite3.Row
            db.init_db(conn)
            now = controlled.t
            for i in range(cache.SNAPSHOT_MAX_ROWS + 5):
                cache.save_snapshot(conn, {"id": f"i{i}"}, f"OMNIFY-{i}", [])
                conn.execute("UPDATE issue_snapshots SET fetched_at = ? WHERE issue_id = ?", (now - 1000 + i, f"i{i}"))
            conn.commit()
            cache.save_snapshot(conn, {"id": "old"}, "OMNIFY-9999", [])
            conn.execute("UPDATE issue_snapshots SET fetched_at = ? WHERE issue_id = 'old'", (now - 91 * 86400,))
            conn.commit()
            cache.save_snapshot(conn, {"id": "new"}, "OMNIFY-10000", [{"id": "c"}])
            count = conn.execute("SELECT COUNT(*) FROM issue_snapshots").fetchone()[0]
            self.assertEqual(count, cache.SNAPSHOT_MAX_ROWS)
            self.assertIsNone(conn.execute("SELECT 1 FROM issue_snapshots WHERE issue_id = 'old'").fetchone())
            cache.save_snapshot(conn, {"id": "new", "name": "v2"}, "OMNIFY-10000", None)
            row = conn.execute("SELECT * FROM issue_snapshots WHERE issue_id = 'new'").fetchone()
            self.assertEqual(json.loads(row["comments_json"]), [{"id": "c"}])
            self.assertEqual(json.loads(row["issue_json"])["name"], "v2")
            conn.close()


if __name__ == "__main__":
    unittest.main()
