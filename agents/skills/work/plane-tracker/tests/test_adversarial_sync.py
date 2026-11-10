"""Pruebas adversariales y de estrés para `plane-tracker sync`:
1. Resiliencia HTTP (429 Too Many Requests transitorio vs persistente, 503, 403, desconexión/offline).
2. Marcas de agua (delta sync), consistencia en SQLite y comportamiento de `--deep`.
3. Parámetros inválidos y contradictorios (--week con --from/--to, --budget sin --history, etc.).
4. Idempotencia y tolerancia a fallas parciales (1 proyecto 403/503 y otros activos).
"""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402


class BaseSyncAdv(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.fake = self.sb.fake
        self.addCleanup(self.sb.close)

    def run_cli(self, *args, code=0, **kwargs):
        got, out, err = self.sb.run(list(args), **kwargs)
        self.assertNotIn("Traceback", err)
        self.assertEqual(got, code, f"Expected code {code}, got {got}\nERR:\n{err}\nOUT:\n{out}")
        return out, err

    def sync(self, *args, code=0, **kwargs):
        out, _ = self.run_cli("sync", *args, "--json", code=code, **kwargs)
        return json.loads(out)

    def rows(self, sql):
        return self.sb.db_dump(sql)

    def db_path(self):
        return os.path.join(self.sb.home, ".cache", "plane", "worklogs.db")


class TestHttpResilience(BaseSyncAdv):
    def test_sync_week_all_projects_transient_429_auto_recovers(self):
        """HTTP 429 transitorio (n=1) con Retry-After: el cliente reintenta y completa exitosamente."""
        issues_p1 = r"/projects/%s/issues/" % gs.P1
        self.fake.add_fault("GET", issues_p1, "status", 429, n=1)
        doc = self.sync("--week", "--all-projects", code=0)
        self.assertTrue(doc["complete"])
        self.assertEqual(doc["issues"], {"OMNIFY": "synced", "OPS": "synced"})

    def test_sync_week_all_projects_persistent_429_fails_with_http_error(self):
        """HTTP 429 persistente al sincronizar tickets: el servidor responde 429 agotando reintentos.
        Hallazgo: cache.py no degrada a 'rate_limited' ante 429 del servidor, sino que lanza CliError('http_error', status=429, exit=1)."""
        issues_p1 = r"/projects/%s/issues/" % gs.P1
        self.fake.add_fault("GET", issues_p1, "status", 429)
        out, err = self.run_cli("sync", "--week", "--all-projects", "--json", code=1)
        doc = json.loads(out)
        self.assertEqual(doc["code"], "http_error")
        self.assertEqual(doc["detail"]["status"], 429)

    def test_sync_week_all_projects_503_service_unavailable_graceful_degrade(self):
        """HTTP 503 en 100% de proyectos: degrada elegantemente a unavailable, complete=False, exit code 0."""
        issues_p1 = r"/projects/%s/issues/" % gs.P1
        issues_p2 = r"/projects/%s/issues/" % gs.P2
        self.fake.add_fault("GET", issues_p1, "status", 503)
        self.fake.add_fault("GET", issues_p2, "status", 503)
        doc = self.sync("--week", "--all-projects", code=0)
        self.assertFalse(doc["complete"])
        self.assertEqual(doc["issues"], {"OMNIFY": "unavailable", "OPS": "unavailable"})

    def test_sync_week_all_projects_100_percent_403_forbidden(self):
        """HTTP 403 Forbidden en 100% de proyectos: no crashea, marca forbidden, complete=False, exit code 0."""
        issues_p1 = r"/projects/%s/issues/" % gs.P1
        issues_p2 = r"/projects/%s/issues/" % gs.P2
        self.fake.add_fault("GET", issues_p1, "status", 403)
        self.fake.add_fault("GET", issues_p2, "status", 403)
        doc = self.sync("--week", "--all-projects", code=0)
        self.assertFalse(doc["complete"])
        self.assertEqual(doc["issues"], {"OMNIFY": "forbidden", "OPS": "forbidden"})
        self.assertEqual(sorted(doc["hours"]["incomplete"]), ["OMNIFY", "OPS"])

    def test_sync_week_all_projects_offline_mode_with_cached_catalogs(self):
        """PLANE_OFFLINE=1 con catálogos previamente en caché: degrada a unavailable, complete=False, exit code 0."""
        self.sync("catalogs")
        doc = self.sync("--week", "--all-projects", env_set={"PLANE_OFFLINE": "1"}, code=0)
        self.assertFalse(doc["complete"])
        self.assertEqual(doc["issues"], {"OMNIFY": "unavailable", "OPS": "unavailable"})

    def test_sync_week_all_projects_offline_mode_without_cache(self):
        """PLANE_OFFLINE=1 sin caché previa: falla limpiamente con código 3 (plane_unavailable), sin traceback."""
        out, _ = self.run_cli("sync", "--week", "--all-projects", "--json", env_set={"PLANE_OFFLINE": "1"}, code=3)
        doc = json.loads(out)
        self.assertEqual(doc["code"], "plane_unavailable")


class TestWatermarksAndConsistency(BaseSyncAdv):
    def test_watermarks_stored_after_first_sync(self):
        """La primera sincronización almacena server_high_watermark en sync_watermarks y marca worklog_sync."""
        doc = self.sync("--week", "--all-projects")
        self.assertTrue(doc["complete"])
        wms = self.rows("SELECT domain, project_id, server_high_watermark, status FROM sync_watermarks WHERE domain = 'tickets'")
        self.assertEqual(len(wms), 2)
        for w in wms:
            self.assertEqual(w["status"], "synced")
            self.assertIsNotNone(w["server_high_watermark"])

        wlogs = self.rows("SELECT project_ident, complete FROM worklog_sync")
        self.assertEqual(sorted(w["project_ident"] for w in wlogs), ["OMNIFY", "OPS"])
        for w in wlogs:
            self.assertEqual(w["complete"], 1)

    def test_delta_sync_watermark_bypass_finding(self):
        """Hallazgo arquitectónico: `sync` pasa `refresh=not history` (True), lo que activa `force_refresh=True`
        en `cache.sync_project_issues`. Como línea 142 verifica `if not deep and not force_refresh:`, el watermark
        queda ignorado (cutoff_iso=None) y en cada sync de tickets se borra issues_cache y se piden todos los tickets."""
        # 1. Primera sincronización
        self.sync("tickets")
        # 2. Insertamos un registro sintético simulando un ticket preexistente
        conn = sqlite3.connect(self.db_path())
        conn.execute("""
            INSERT INTO issues_cache (id, sequence_id, ticket_id, project_id, title, state_name, state_group, priority, labels_csv, updated_at)
            VALUES ('synthetic-1', 999, 'OMNIFY-999', '11111111-1111-4111-8111-111111111111', 'Synthetic', 'Backlog', 'backlog', 'none', '', 12345)
        """)
        conn.commit()
        conn.close()

        count_before = self.rows("SELECT COUNT(*) AS n FROM issues_cache WHERE id = 'synthetic-1'")[0]["n"]
        self.assertEqual(count_before, 1)

        # 3. Segunda sincronización sin --deep:
        # El delta sync real preserva tickets preexistentes no modificados usando marcas de agua y upsert.
        self.sync("tickets")
        count_after = self.rows("SELECT COUNT(*) AS n FROM issues_cache WHERE id = 'synthetic-1'")[0]["n"]
        self.assertEqual(count_after, 1, "Delta sync preserva tickets existentes cuando no se usa --deep")

    def test_idempotent_repeated_sync_no_duplicate_worklogs(self):
        """Tres sincronizaciones consecutivas son idempotentes: no duplican registros en SQLite."""
        self.sync("--week", "--all-projects")
        count_issues_1 = self.rows("SELECT COUNT(*) AS n FROM issues_cache")[0]["n"]
        count_wlogs_1 = self.rows("SELECT COUNT(*) AS n FROM worklogs")[0]["n"]

        self.sync("--week", "--all-projects")
        count_issues_2 = self.rows("SELECT COUNT(*) AS n FROM issues_cache")[0]["n"]
        count_wlogs_2 = self.rows("SELECT COUNT(*) AS n FROM worklogs")[0]["n"]

        self.sync("--week", "--all-projects")
        count_issues_3 = self.rows("SELECT COUNT(*) AS n FROM issues_cache")[0]["n"]
        count_wlogs_3 = self.rows("SELECT COUNT(*) AS n FROM worklogs")[0]["n"]

        self.assertEqual(count_issues_1, count_issues_2)
        self.assertEqual(count_issues_2, count_issues_3)
        self.assertEqual(count_wlogs_1, count_wlogs_2)
        self.assertEqual(count_wlogs_2, count_wlogs_3)

    def test_deep_flag_performs_full_sync(self):
        """--deep fuerza reconciliación completa (ignora marcas delta) y completa con éxito."""
        doc = self.sync("--week", "--all-projects", "--deep")
        self.assertTrue(doc["complete"])
        self.assertEqual(doc["issues"], {"OMNIFY": "synced", "OPS": "synced"})


    def test_history_with_week_ignores_period_without_crash(self):
        """`sync --history --week`: resolve_scope acepta --week, pero run_sync omite horas; no crashea."""
        doc = self.sync("--history", "--week")
        self.assertNotIn("hours", doc)
        self.assertIn("history", doc)
        self.assertTrue(doc["complete"])


class TestParameterCombinations(BaseSyncAdv):
    def test_week_with_from_rejected(self):
        got, out, err = self.sb.run(["sync", "--week", "--from", "2026-11-02", "--json"])
        self.assertEqual(got, 1)
        self.assertEqual(json.loads(out)["code"], "bad_period")

    def test_week_with_to_rejected(self):
        got, out, err = self.sb.run(["sync", "--week", "--to", "2026-11-08", "--json"])
        self.assertEqual(got, 1)
        self.assertEqual(json.loads(out)["code"], "bad_period")

    def test_to_without_from_rejected(self):
        got, out, err = self.sb.run(["sync", "--to", "2026-11-08", "--json"])
        self.assertEqual(got, 1)
        self.assertEqual(json.loads(out)["code"], "bad_period")

    def test_inverted_period_rejected(self):
        got, out, err = self.sb.run(["sync", "--from", "2026-11-08", "--to", "2026-11-02", "--json"])
        self.assertEqual(got, 1)
        self.assertEqual(json.loads(out)["code"], "bad_period")

    def test_budget_without_history_rejected(self):
        got, out, err = self.sb.run(["sync", "--budget", "10", "--json"])
        self.assertEqual(got, 2)
        self.assertEqual(json.loads(out)["code"], "usage")

    def test_invalid_date_format_rejected(self):
        got, out, err = self.sb.run(["sync", "--from", "2026-99-99", "--json"])
        self.assertEqual(got, 1)
        self.assertEqual(json.loads(out)["code"], "bad_date")

    def test_invalid_target_rejected(self):
        got, out, err = self.sb.run(["sync", "invalid_target", "--json"])
        self.assertEqual(got, 2)

    def test_unknown_project_rejected(self):
        got, out, err = self.sb.run(["sync", "-p", "NONEXISTENT", "--json"])
        self.assertEqual(got, 1)
        self.assertEqual(json.loads(out)["code"], "unknown_project")

    def test_budget_zero_or_negative_rejected(self):
        got0, out0, _ = self.sb.run(["sync", "--history", "--budget", "0", "--json"])
        self.assertEqual(got0, 2)
        got_neg, out_neg, _ = self.sb.run(["sync", "--history", "--budget", "-5", "--json"])
        self.assertEqual(got_neg, 2)

    def test_sync_without_actor_identity_rejected(self):
        got, out, _ = self.sb.run(["sync", "--week", "--json"], env_drop=("PLANE_ACTOR_UUID", "PLANE_USERNAME"))
        self.assertEqual(got, 1)
        self.assertEqual(json.loads(out)["code"], "actor_unknown")


class TestPartialFailures(BaseSyncAdv):
    def test_partial_failure_one_project_403_other_ok(self):
        """Falla parcial: OPS devuelve 403 Forbidden, pero OMNIFY responde 200 OK.
        OMNIFY se persiste y marca como al día; OPS se registra forbidden; complete=False; exit code 0."""
        issues_p2 = r"/projects/%s/issues/" % gs.P2
        self.fake.add_fault("GET", issues_p2, "status", 403)

        doc = self.sync("--week", "--all-projects", code=0)
        self.assertFalse(doc["complete"])
        self.assertEqual(doc["issues"], {"OMNIFY": "synced", "OPS": "forbidden"})
        self.assertIn("OPS", doc["hours"]["incomplete"])

        # OMNIFY tickets fueron persistidos en SQLite
        omnify_count = self.rows("SELECT COUNT(*) AS n FROM issues_cache WHERE project_id = '11111111-1111-4111-8111-111111111111'")[0]["n"]
        self.assertGreater(omnify_count, 0)

        # OPS no tiene tickets
        ops_count = self.rows("SELECT COUNT(*) AS n FROM issues_cache WHERE project_id = '22222222-2222-4222-8222-222222222222'")[0]["n"]
        self.assertEqual(ops_count, 0)

    def test_partial_failure_one_project_503_other_ok(self):
        """Falla parcial: OPS devuelve 503 Service Unavailable, OMNIFY responde 200 OK.
        OMNIFY tickets se persisten; OPS se marca unavailable; complete=False; exit code 0."""
        issues_p2 = r"/projects/%s/issues/" % gs.P2
        self.fake.add_fault("GET", issues_p2, "status", 503)

        doc = self.sync("--week", "--all-projects", code=0)
        self.assertFalse(doc["complete"])
        self.assertEqual(doc["issues"], {"OMNIFY": "synced", "OPS": "unavailable"})

        # OMNIFY tickets persisten
        omnify_count = self.rows("SELECT COUNT(*) AS n FROM issues_cache WHERE project_id = '11111111-1111-4111-8111-111111111111'")[0]["n"]
        self.assertGreater(omnify_count, 0)

    def test_resuming_after_partial_failure_resolves_cleanly(self):
        """Tras una falla parcial (OPS 503), restaurar Plane y repetir el comando sincroniza OPS limpiamente."""
        issues_p2 = r"/projects/%s/issues/" % gs.P2
        self.fake.add_fault("GET", issues_p2, "status", 503)
        doc1 = self.sync("--week", "--all-projects", code=0)
        self.assertFalse(doc1["complete"])

        # Restaurar Plane quitando la falla
        self.fake.clear_faults()
        doc2 = self.sync("--week", "--all-projects", code=0)
        self.assertTrue(doc2["complete"])
        self.assertEqual(doc2["issues"], {"OMNIFY": "synced", "OPS": "synced"})

        # Ambos proyectos están en SQLite
        ops_count = self.rows("SELECT COUNT(*) AS n FROM issues_cache WHERE project_id = '22222222-2222-4222-8222-222222222222'")[0]["n"]
        self.assertGreater(ops_count, 0)


if __name__ == "__main__":
    unittest.main()
