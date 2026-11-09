"""Pruebas adversariales y de límites para plane-tracker:
1. Loop de insistencia (nagging) de outbox en stderr a través de workspaces.
2. Degradación elegante con 100% de proyectos con HTTP 403 Forbidden.
3. Normalización de URLs y filas heredadas (NULL) en SQLite outbox.
4. Fuga de aislamiento en health, outbox list y outbox drop entre workspaces.
"""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402

ISSUE1 = "10000000-0000-4000-8000-000000000001"
OFF = {"PLANE_OFFLINE": "1"}


def block(start):
    return (
        '<!-- PLANE_WORKLOG_METADATA {"date": "2026-10-21", "start_time": "%s", "duration_minutes": 20, "notes": "m", "track": "mm"} -->'
        % start
    )


class BaseAdversarial(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.fake = self.sb.fake
        self.fake.store_comments = True
        self.addCleanup(self.sb.close)

    def cli(self, *args, code=0, **kwargs):
        got, out, err = self.sb.run(list(args), **kwargs)
        self.assertNotIn("Traceback", err)
        self.assertEqual(got, code, err + out)
        return out, err

    def queue(self, text="test", start="08:00", ticket="OMNIFY-1", env_set=None):
        envs = dict(OFF)
        if env_set:
            envs.update(env_set)
        out, _ = self.cli("comment", "add", ticket, "-m", f"<p>{text}</p>{block(start)}", "--json", env_set=envs)
        data = json.loads(out)
        self.assertEqual(data["status"], "queued")
        return data["outbox_id"]

    def rows(self, query="SELECT * FROM outbox ORDER BY id"):
        return self.sb.db_dump(query)

    def sql(self, statement, *params):
        conn = sqlite3.connect(os.path.join(self.sb.home, ".cache", "plane", "worklogs.db"))
        conn.execute(statement, params)
        conn.commit()
        conn.close()


class TestAdversarialOutboxCrossWorkspace(BaseAdversarial):
    def test_outbox_nagging_loop_across_workspaces(self):
        """Vector 1: Un comentario encolado en Workspace A causa un loop infinito de avisos
        en Workspace B que 'outbox flush' no puede resolver porque omite el item."""
        # 1. Usuario en Workspace A (ej. 'other-ws') se queda sin conexión y encola un comentario
        item_id = self.queue("comentario en other-ws", start="08:00", env_set={"PLANE_WORKSPACE_SLUG": "other-ws"})
        rows = self.rows(f"SELECT * FROM outbox WHERE id = {item_id}")
        self.assertEqual(rows[0]["target_workspace"], "other-ws")
        self.assertEqual(rows[0]["state"], "pending")

        # 2. Usuario cambia de contexto al Workspace B ('ws', activo y servido por FakePlane)
        # 3. Al ejecutar comandos rutinarios en Workspace B, no debe avisar de pendientes de otros workspaces
        out, err = self.cli("labels")
        self.assertNotIn("⏳ Outbox", err, "pending_notice() no debe avisar en Workspace B para items de other-ws")

        # 4. El usuario sigue el consejo y ejecuta 'plane-tracker outbox flush' en Workspace B
        out, _ = self.cli("outbox", "flush")
        self.assertIn("omitido: pertenece a otra instancia/workspace", out)
        self.assertIn("other-ws", out)
        # El item sigue 'pending'
        self.assertEqual(self.rows(f"SELECT state FROM outbox WHERE id = {item_id}")[0]["state"], "pending")

        # 5. En el SIGUIENTE comando en Workspace B, tampoco debe avisar
        out2, err2 = self.cli("labels")
        self.assertNotIn("⏳ Outbox", err2, "Workspace B no debe quedar atrapado en bucle de avisos")

    def test_outbox_queue_duplicate_collision_cross_workspace(self):
        """Vector 1B: _enqueue() no debe rechazar agregar un worklog offline en Workspace B si coincide
        en ticket/track/fecha/inicio con un item en cola de Workspace A."""
        # 1. Encolar en Workspace A
        self.queue("item en WS_A", start="08:00", ticket="OMNIFY-1", env_set={"PLANE_WORKSPACE_SLUG": "ws_a"})

        # 2. Encolar en Workspace B con la misma clave (OMNIFY-1, 08:00): debe tener éxito
        out_b = self.queue("item en WS_B", start="08:00", ticket="OMNIFY-1", env_set={"PLANE_WORKSPACE_SLUG": "ws_b"})
        self.assertGreater(out_b, 0)


class TestAdversarialForbidden403(BaseAdversarial):
    def test_100_percent_projects_403_forbidden_json(self):
        """Vector 2A: report time --all-projects con 100% de proyectos respondiendo HTTP 403."""
        issues_p1 = r"/projects/%s/issues/$" % gs.P1
        issues_p2 = r"/projects/%s/issues/$" % gs.P2
        self.fake.add_fault("GET", issues_p1, "status", 403)
        self.fake.add_fault("GET", issues_p2, "status", 403)

        code, out, err = self.sb.run(["report", "time", "--all-projects", "--from", "2026-10-20", "--refresh", "--json"])
        self.assertEqual(code, 0, f"Debe degradar elegantemente con código 0, falló con: {err}")
        doc = json.loads(out)

        self.assertEqual(doc["coverage"]["complete"], False)
        forbidden_list = doc["coverage"]["detail"].get("forbidden", [])
        self.assertEqual(sorted(forbidden_list), sorted(["OMNIFY", "OPS"]))
        notes = [n["code"] for n in doc["notes"]]
        self.assertIn("source_forbidden", notes)

    def test_100_percent_projects_403_forbidden_text(self):
        """Vector 2B: report time --all-projects en modo texto cuando 100% de proyectos son 403."""
        issues_p1 = r"/projects/%s/issues/$" % gs.P1
        issues_p2 = r"/projects/%s/issues/$" % gs.P2
        self.fake.add_fault("GET", issues_p1, "status", 403)
        self.fake.add_fault("GET", issues_p2, "status", 403)

        code, out, err = self.sb.run(["report", "time", "--all-projects", "--from", "2026-10-20", "--refresh"])
        self.assertEqual(code, 0, f"Modo texto no debe crashear: {err}")
        self.assertIn("Sin acceso a: OMNIFY, OPS", out)

    def test_single_project_403_forbidden(self):
        """Vector 2C: report time para un único proyecto con -p cuando devuelve 403."""
        issues_p1 = r"/projects/%s/issues/$" % gs.P1
        self.fake.add_fault("GET", issues_p1, "status", 403)

        code, out, err = self.sb.run(["report", "time", "-p", "OMNIFY", "--from", "2026-10-20", "--refresh", "--json"])
        self.assertEqual(code, 0, f"Debe salir 0: {err}")
        doc = json.loads(out)
        self.assertEqual(doc["coverage"]["complete"], False)
        self.assertEqual(doc["coverage"]["detail"].get("forbidden"), ["OMNIFY"])
        notes = [n["code"] for n in doc["notes"]]
        self.assertIn("source_forbidden", notes)


class TestAdversarialUrlNormalizationAndLegacy(BaseAdversarial):
    def test_legacy_null_target_url_and_workspace(self):
        """Vector 3A: Filas heredadas con target_base_url y target_workspace NULL."""
        item_id = self.queue("legacy item")
        self.sql("UPDATE outbox SET target_base_url = NULL, target_workspace = NULL WHERE id = ?", item_id)

        # Flush en texto
        out, _ = self.cli("outbox", "flush")
        self.assertIn("1 publicado(s)", out)
        self.assertEqual(self.rows(f"SELECT state FROM outbox WHERE id = {item_id}")[0]["state"], "sent")

    def test_url_case_sensitivity_mismatch(self):
        """Vector 3B: Hostname con diferencias de mayúsculas/minúsculas no debe causar falsos mismatches."""
        item_id = self.queue("case item")
        fake_url_upper = self.fake.base_url.upper()
        self.sql("UPDATE outbox SET target_base_url = ? WHERE id = ?", fake_url_upper, item_id)

        out, _ = self.cli("outbox", "flush")
        self.assertIn("1 publicado(s)", out)
        self.assertNotIn("omitido", out)

    def test_url_trailing_slash_handling(self):
        """Vector 3C: Variación de trailing slash no debe causar falso mismatch."""
        item_id = self.queue("trailing slash item")
        fake_url_slash = self.fake.base_url.rstrip("/") + "/"
        self.sql("UPDATE outbox SET target_base_url = ? WHERE id = ?", fake_url_slash, item_id)

        out, _ = self.cli("outbox", "flush")
        self.assertIn("1 publicado(s)", out)

    def test_health_reports_only_active_workspace_pending(self):
        """Vector 4A: health solo reporta items del workspace activo."""
        self.queue("item ws_a", env_set={"PLANE_WORKSPACE_SLUG": "ws_a"})

        out, _ = self.cli("health", "--json", env_set={"PLANE_WORKSPACE_SLUG": "ws_b"})
        data = json.loads(out)
        self.assertEqual(data["outbox"]["pending"], 0)

    def test_report_time_leaks_pending_unpublished_from_other_workspace(self):
        """Vector 4D: count_open() en report time no cuenta items de otros workspaces."""
        # Encolamos un item en 'other-ws' para OMNIFY-1 en 2026-10-21
        self.queue("item en other-ws", ticket="OMNIFY-1", start="08:00", env_set={"PLANE_WORKSPACE_SLUG": "other-ws"})

        # En el workspace activo 'ws', ejecutamos report time para el periodo que incluye 2026-10-21
        out, _ = self.cli("report", "time", "-p", "OMNIFY", "--from", "2026-10-20", "--to", "2026-10-22", "--json")
        doc = json.loads(out)
        note_codes = [n["code"] for n in doc["notes"]]
        self.assertNotIn("pending_unpublished", note_codes)
        self.assertTrue(doc["coverage"]["complete"])


if __name__ == "__main__":
    unittest.main()
