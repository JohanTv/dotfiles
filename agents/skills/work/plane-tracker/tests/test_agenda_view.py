"""Pruebas de la vista `agenda`: dashboard personal de foco operativo (WIP, estancados, bloqueos, pull queue)."""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402
from plane_cli import envelope  # noqa: E402

P1 = gs.P1
P2 = gs.P2
ME = gs.ME
OTHER = gs.OTHER


class TestAgendaView(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)

    def agenda(self, *args, ok=True, env_set=None):
        code, out, err = self.sb.run(["agenda", *args], env_set=env_set)
        if ok:
            self.assertEqual(code, 0, f"Error (code {code}): {err}\nOutput: {out}")
        parsed = None
        if "--json" in args and out.strip():
            try:
                parsed = json.loads(out)
            except Exception as e:
                self.fail(f"Fallo al parsear JSON: {e}\nSalida:\n{out}")
        return code, parsed, out, err

    def sql(self, statement, params=()):
        conn = sqlite3.connect(os.path.join(self.sb.home, ".cache", "plane", "worklogs.db"))
        conn.execute(statement, params)
        conn.commit()
        conn.close()

    def test_agenda_basic_json_and_envelope(self):
        # Primero sincronizamos o dejamos que la vista consulte
        code, doc, out, err = self.agenda("--json")
        self.assertEqual(code, 0)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["schema"], "plane-tracker/1")
        self.assertEqual(doc["view"], "agenda")
        self.assertIn("summary", doc)
        problems = envelope.validate(doc)
        self.assertEqual(problems, [], f"Sobre inválido: {problems}")

    def test_wip_limit_and_warning(self):
        # OMNIFY-1 está en Progreso y OPS-13 en Progreso
        # Asignamos OMNIFY-1 también a ME en issues_cache
        self.agenda("--json")
        self.sql("UPDATE issues_cache SET assignees_json = ? WHERE ticket_id = 'OMNIFY-1'", (json.dumps([ME]),))
        self.sql("UPDATE issues_cache SET assignees_json = ? WHERE ticket_id = 'OPS-13'", (json.dumps([ME]),))

        # Con wip_limit 1, 2 tareas activas deben disparar wip_exceeded
        _, doc, _, _ = self.agenda("--json", "--wip-limit", "1", "--offline")
        self.assertTrue(doc["summary"]["wip_exceeded"])
        self.assertGreater(doc["summary"]["wip_count"], 1)
        note_codes = [n["code"] for n in doc.get("notes") or []]
        self.assertIn("wip_exceeded", note_codes)

        # En texto plano debe aparecer advertencia
        _, _, text, _ = self.agenda("--wip-limit", "1", "--offline")
        self.assertIn("LÍMITE EXCEDIDO", text)

    def test_stalled_ticket_detection(self):
        self.agenda("--json")
        self.sql("UPDATE issues_cache SET assignees_json = ? WHERE ticket_id = 'OPS-13'", (json.dumps([ME]),))
        # Hacemos que OPS-13 no tenga actividad hace 10 días
        old_time = "2026-10-10T10:00:00Z"
        self.sql("UPDATE issues_cache SET plane_updated_at = ?, updated_at = ? WHERE ticket_id = 'OPS-13'", (old_time, old_time))

        _, doc, _, _ = self.agenda("--json", "--stalled-days", "5", "--offline")
        self.assertGreater(doc["summary"]["stalled_count"], 0)
        ops_item = next(r for r in doc["results"] if r["ticket"] == "OPS-13")
        self.assertTrue(ops_item["is_stalled"])
        note_codes = [n["code"] for n in doc.get("notes") or []]
        self.assertIn("ticket_stalled", note_codes)

    def test_blocked_section_and_standby_reason(self):
        self.agenda("--json")
        # Ponemos OPS-13 en estado 'Pausado'
        self.sql("UPDATE issues_cache SET state_name = 'Pausado', assignees_json = ? WHERE ticket_id = 'OPS-13'", (json.dumps([ME]),))
        
        _, doc, _, _ = self.agenda("--json", "--offline")
        blocked = [r for r in doc["results"] if r["section"] == "blocked"]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["ticket"], "OPS-13")
        self.assertIsNotNone(blocked[0]["standby_days"])

        _, _, text, _ = self.agenda("--offline")
        self.assertIn("BLOQUEADO / STANDBY", text)
        self.assertIn("OPS-13", text)

    def test_session_focus_indicator(self):
        self.agenda("--json")
        # Insertar marca de foco de sesión para OPS-13
        self.sql("INSERT INTO session_marks (agent, session_id, ticket, started_at, ended_at) VALUES ('agy', 'sess-1', 'OPS-13', 1000, NULL)")

        _, doc, _, _ = self.agenda("--json", "--offline")
        self.assertEqual(doc["summary"]["active_focus_ticket"], "OPS-13")
        foc = next(r for r in doc["results"] if r["ticket"] == "OPS-13")
        self.assertTrue(foc["is_focus"])
        self.assertEqual(foc["focus_source"], "session_focus")

        _, _, text, _ = self.agenda("--offline")
        self.assertIn("▶ OPS-13", text)
        self.assertIn("En foco", text)

    def test_brief_rendering(self):
        self.agenda("--json")
        _, _, text, _ = self.agenda("--brief", "--offline")
        self.assertIn("🎯 AGENDA · WIP:", text)
        self.assertTrue(any("OPS-13" in line for line in text.splitlines()))

    def test_offline_read_does_not_call_network(self):
        # Primero llenamos la caché
        self.agenda("--json")
        initial_requests = len(self.sb.fake.requests)

        # Ahora corremos con --offline
        code, doc, _, _ = self.agenda("--json", "--offline")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.sb.fake.requests), initial_requests, "No debe realizar peticiones de red con --offline")


if __name__ == "__main__":
    unittest.main()
