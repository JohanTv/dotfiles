"""Pruebas adversariales y de ingeniería del caos para `plane-tracker agenda`.

Vectores evaluados:
1. Data Chaos en SQLite:
   - Base de datos vacía / sin tablas / caché vacía.
   - assignees_json corrupto, no-JSON, o no-lista (ej: '{broken', '123', 'null').
   - worklogs.raw_payload corrupto, entero ('123'), o dict malformado ('{"segments": "bad"}').
   - Fechas corruptas o atípicas en plane_updated_at y updated_at ("invalid", "", "9999-99-99").
   - Snapshots corruptos (issue_json y comments_json truncados o malformados).
2. Validación CLI y Límites de Argumentos:
   - --wip-limit 0, -5, abc.
   - --stalled-days 0, -1, 999999.
   - Banderas incompatibles: --brief --json.
3. Escala y Sobrecarga (WIP & Queue Stress):
   - 0 tareas (agenda completamente vacía).
   - 100 tareas en progreso (sobrecarga extrema de WIP).
   - Inyección de saltos de línea (newlines) y secuencias en títulos de tickets.
   - DoD masivo (10,000 checkboxes).
4. Foco y Concurrencia de Estado:
   - Marca de foco (session_marks) apuntando a ticket inexistente o cerrado.
   - Múltiples marcas de foco abiertas simultáneas (ended_at IS NULL).
   - Detección de rama Git con ticket cerrado o asignado a otro usuario.
5. Invariantes CQS y Red:
   - CQS absoluto: verificación mediante SQLite triggers de que agenda NUNCA escribe en la DB.
   - Aislamiento de red: 0 peticiones HTTP en modo --offline.
   - Cumplimiento estricto del sobre plane-tracker/1 y F14 (complete no puede ser True con warns).
"""

import json
import os
import sqlite3
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import golden_support as gs  # noqa: E402
from plane_cli import envelope  # noqa: E402


class TestAdversarialAgenda(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)

    def agenda(self, *args, env_set=None):
        code, out, err = self.sb.run(["agenda", *args], env_set=env_set)
        parsed = None
        if "--json" in args and out.strip():
            try:
                parsed = json.loads(out)
            except Exception:
                pass
        return code, parsed, out, err

    def db_path(self):
        return os.path.join(self.sb.home, ".cache", "plane", "worklogs.db")

    def sql(self, statement, params=()):
        conn = sqlite3.connect(self.db_path())
        conn.execute(statement, params)
        conn.commit()
        conn.close()

    # =========================================================================
    # VECTOR 1: Data Chaos en SQLite (Corrupción y Malformación)
    # =========================================================================

    def test_chaos_empty_db(self):
        """1.1 Base de datos completamente vacía y offline debe responder limpiamente."""
        code, doc, out, err = self.agenda("--json", "--offline")
        # Con caché vacía y sin red, debe devolver un error controlado, nunca Traceback
        self.assertNotIn("Traceback", err)
        self.assertIn(code, (0, 3))
        if doc and "schema" in doc:
            if doc.get("status") == "error":
                self.assertEqual(envelope.validate_error(doc), [])
            else:
                self.assertEqual(envelope.validate(doc), [])

    def test_chaos_corrupted_assignees_json(self):
        """1.2 assignees_json corrupto no debe causar Traceback ni caída de la CLI."""
        # Poblar caché
        self.agenda("--json")

        corruptions = [
            "{invalid json",
            "123",
            "null",
            '"just-a-string"',
            "true",
        ]
        for val in corruptions:
            self.sql("UPDATE issues_cache SET assignees_json = ? WHERE ticket_id = 'OPS-13'", (val,))
            code, doc, out, err = self.agenda("--json", "--offline")
            self.assertNotIn("Traceback", err, f"Falló con assignees_json={val!r}")
            self.assertEqual(code, 0, f"Error exit code con assignees_json={val!r}")
            self.assertIsNotNone(doc)
            self.assertEqual(envelope.validate(doc), [])

    def test_chaos_corrupted_worklogs_raw_payload(self):
        """1.3 worklogs.raw_payload malformado (entero, string, segmentos inválidos) no debe romper _week_minutes."""
        self.agenda("--json")
        # Insertar worklogs con payloads adversariales en la semana activa (2026-11-02)
        payloads = [
            "123",
            '"a-string"',
            '{"segments": "not-a-list"}',
            '{"segments": [123]}',
            '{"segments": [{"start": "bad", "end": "worse", "minutes": "no"}]}',
        ]
        for idx, payload in enumerate(payloads):
            self.sql(
                "INSERT INTO worklogs (ticket_id, track, date, start_time, end_time, duration_minutes, project_id, author_id, raw_payload, created_at, updated_at) "
                "VALUES (?, 'main', '2026-11-02', '09:00', '10:00', 60, ?, ?, ?, '2026-11-02T09:00:00Z', 1700000000.0)",
                (f"OPS-{idx + 100}", gs.P2, gs.ME, payload)
            )
            code, doc, out, err = self.agenda("--json", "--offline")
            self.assertNotIn("Traceback", err, f"Falló con raw_payload={payload!r}")
            self.assertEqual(code, 0)
            self.assertIsNotNone(doc)
            self.assertEqual(envelope.validate(doc), [])

    def test_chaos_corrupted_timestamps_and_dates(self):
        """1.4 plane_updated_at y updated_at con strings inválidos o fechas futuristas."""
        self.agenda("--json")
        bad_dates = ["invalid-date", "", "9999-99-99", "2026/11/02", "None"]
        for bad in bad_dates:
            self.sql("UPDATE issues_cache SET plane_updated_at = ?, updated_at = ? WHERE ticket_id = 'OPS-13'", (bad, bad))
            code, doc, out, err = self.agenda("--json", "--offline")
            self.assertNotIn("Traceback", err)
            self.assertEqual(code, 0)
            self.assertEqual(envelope.validate(doc), [])

    def test_chaos_corrupted_snapshots_json(self):
        """1.5 issue_snapshots con JSON truncado no debe abortar DoD ni blockers."""
        self.agenda("--json")
        self.sql("UPDATE issues_cache SET state_name = 'Pausado' WHERE ticket_id = 'OPS-13'")
        self.sql(
            "INSERT OR REPLACE INTO issue_snapshots (ticket_id, issue_json, comments_json, fetched_at) "
            "VALUES ('OPS-13', '{\"description\": \"broken', '[{\"text\": \"trunc', 1700000000.0)"
        )
        code, doc, out, err = self.agenda("--offline")
        self.assertNotIn("Traceback", err)
        self.assertEqual(code, 0)
        self.assertIn("OPS-13", out)

    # =========================================================================
    # VECTOR 2: Validación CLI y Límites de Argumentos
    # =========================================================================

    def test_cli_argument_limits(self):
        """2.1 Parámetros inválidos como --wip-limit 0 o negativos deben rechazarse limpiamente."""
        self.agenda("--json")
        invalid_args = [
            (["--wip-limit", "0"], 2),
            (["--wip-limit", "-5"], 2),
            (["--wip-limit", "abc"], 2),
            (["--stalled-days", "0"], 2),
            (["--stalled-days", "-1"], 2),
            (["--stalled-days", "xyz"], 2),
        ]
        for args, expected_code in invalid_args:
            code, _, _, err = self.agenda(*args, "--offline")
            self.assertEqual(code, expected_code, f"Args {args} no devolvieron código {expected_code}")
            self.assertNotIn("Traceback", err)

    def test_cli_extreme_values(self):
        """2.2 Valores astronómicos como --stalled-days 999999 deben procesarse sin desbordamiento."""
        self.agenda("--json")
        code, doc, out, err = self.agenda("--json", "--stalled-days", "999999", "--offline")
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", err)
        self.assertEqual(doc["summary"]["stalled_count"], 0)

    def test_cli_brief_and_json_combination(self):
        """2.3 Banderas combinadas --brief y --json deben producir JSON válido sin romper el esquema."""
        self.agenda("--json")
        code, doc, out, err = self.agenda("--brief", "--json", "--offline")
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", err)
        self.assertIsNotNone(doc)
        self.assertEqual(envelope.validate(doc), [])

    # =========================================================================
    # VECTOR 3: Escala y Sobrecarga (WIP & Queue Stress)
    # =========================================================================

    def test_stress_zero_tasks(self):
        """3.1 Agenda con 0 tareas debe devolver sobre válido y render legible."""
        self.agenda("--json")
        # Eliminar todos los tickets asignados a ME o en progreso
        self.sql("DELETE FROM issues_cache")
        code, doc, out, err = self.agenda("--json", "--offline")
        self.assertEqual(code, 0)
        self.assertEqual(doc["summary"]["wip_count"], 0)
        self.assertEqual(envelope.validate(doc), [])

        code_txt, _, txt, _ = self.agenda("--offline")
        self.assertEqual(code_txt, 0)
        self.assertIn("(sin tareas en curso)", txt)
        self.assertIn("(sin bloqueos activos)", txt)
        self.assertIn("(cola vacía)", txt)

    def test_stress_hyper_wip(self):
        """3.2 100 tareas en estado 'Progreso' deben disparar alerta de sobrecarga sin degradar rendimiento."""
        self.agenda("--json")
        # Insertar 100 tickets en Progreso
        for i in range(100):
            ticket_id = f"OMNIFY-{i + 1000}"
            self.sql(
                "INSERT OR REPLACE INTO issues_cache "
                "(id, sequence_id, ticket_id, project_id, title, state_name, state_group, priority, assignees_json, updated_at, plane_updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'Progreso', 'started', 'medium', ?, 1700000000.0, '2026-11-01T12:00:00Z')",
                (f"uuid-{i}", i + 1000, ticket_id, gs.P1, f"Task {i}", json.dumps([gs.ME]))
            )

        code, doc, out, err = self.agenda("--json", "--wip-limit", "3", "--offline")
        self.assertEqual(code, 0)
        self.assertGreaterEqual(doc["summary"]["wip_count"], 100)
        self.assertTrue(doc["summary"]["wip_exceeded"])
        self.assertEqual(envelope.validate(doc), [])

    def test_stress_title_with_newlines_and_ansi(self):
        """3.3 Títulos con saltos de línea inyectados no deben desarmar el renderizado brief."""
        self.agenda("--json")
        malicious_title = "Titulo Inyectado\nLinea 2 Fantasma\x1b[31;1mROJO\x1b[0m"
        self.sql("UPDATE issues_cache SET title = ? WHERE ticket_id = 'OPS-13'", (malicious_title,))

        # Modo brief no debe emitir múltiples líneas para el mismo ticket
        code, _, brief_text, _ = self.agenda("--brief", "--offline")
        self.assertEqual(code, 0)
        lines = [line.strip() for line in brief_text.splitlines() if line.strip()]
        # Cada línea de ticket en brief debe empezar con el glifo ▶, ⏸ o •
        ticket_lines = [l for l in lines if not l.startswith("🎯")]
        for tl in ticket_lines:
            self.assertTrue(tl.startswith("▶") or tl.startswith("⏸") or tl.startswith("•"),
                            f"Línea de ticket rota por salto de línea inyectado: {tl!r}")

    def test_stress_massive_dod(self):
        """3.4 DoD checklist masivo (10,000 checkboxes) debe procesarse eficientemente sin timeout."""
        self.agenda("--json")
        big_desc = "\n".join(f"- [x] item done {i}" for i in range(5000)) + "\n" + "\n".join(f"- [ ] item pend {i}" for i in range(5000))
        self.sql(
            "INSERT OR REPLACE INTO issue_snapshots (ticket_id, issue_json, fetched_at) VALUES ('OPS-13', ?, 1700000000.0)",
            (json.dumps({"description": big_desc}),)
        )
        code, doc, _, _ = self.agenda("--json", "--offline")
        self.assertEqual(code, 0)
        ops = next(r for r in doc["results"] if r["ticket"] == "OPS-13")
        self.assertEqual(ops["dod_completed"], 5000)
        self.assertEqual(ops["dod_total"], 10000)

    # =========================================================================
    # VECTOR 4: Foco y Concurrencia de Estado
    # =========================================================================

    def test_focus_pointing_to_closed_or_nonexistent_ticket(self):
        """4.1 Marca de foco apuntando a ticket inexistente o cerrado debe manejarse coherentemente."""
        self.agenda("--json")
        # 4.1.a Ticket inexistente
        self.sql("INSERT INTO session_marks (agent, session_id, ticket, started_at, ended_at) VALUES ('agy', 's1', 'NONEXISTENT-99', 1000, NULL)")
        code, doc, _, _ = self.agenda("--json", "--offline")
        self.assertEqual(code, 0)
        self.assertEqual(envelope.validate(doc), [])
        # Invariante: Ningún ticket en results debe tener is_focus=True si el foco es inexistente
        self.assertFalse(any(r["is_focus"] for r in doc["results"]))

        # 4.1.b Ticket completado
        self.sql("UPDATE issues_cache SET state_group = 'completed', state_name = 'Completado' WHERE ticket_id = 'OPS-13'")
        self.sql("INSERT INTO session_marks (agent, session_id, ticket, started_at, ended_at) VALUES ('agy', 's2', 'OPS-13', 2000, NULL)")
        code, doc, _, _ = self.agenda("--json", "--offline")
        self.assertEqual(code, 0)
        self.assertEqual(envelope.validate(doc), [])
        self.assertFalse(any(r["is_focus"] for r in doc["results"]))

    def test_focus_multiple_concurrent_open_marks(self):
        """4.2 Múltiples marcas abiertas en session_marks escoge determinísticamente la más reciente."""
        self.agenda("--json")
        self.sql("UPDATE issues_cache SET assignees_json = ? WHERE ticket_id = 'OMNIFY-1'", (json.dumps([gs.ME]),))
        self.sql("UPDATE issues_cache SET assignees_json = ? WHERE ticket_id = 'OPS-13'", (json.dumps([gs.ME]),))
        self.sql("INSERT INTO session_marks (agent, session_id, ticket, started_at, ended_at) VALUES ('agy', 's1', 'OMNIFY-1', 1000, NULL)")
        self.sql("INSERT INTO session_marks (agent, session_id, ticket, started_at, ended_at) VALUES ('agy', 's2', 'OPS-13', 2000, NULL)")

        code, doc, _, _ = self.agenda("--json", "--offline")
        self.assertEqual(code, 0)
        self.assertEqual(doc["summary"]["active_focus_ticket"], "OPS-13")
        foc = next(r for r in doc["results"] if r["ticket"] == "OPS-13")
        self.assertTrue(foc["is_focus"])

    def test_focus_git_branch_detection(self):
        """4.3 Rama de Git actual debe inferir el ticket en foco si no hay session_marks activa."""
        self.agenda("--json")
        # Inicializar repo git en el sandbox work dir y cambiar de rama
        subprocess.run(["git", "init"], cwd=self.sb.work, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feat/OPS-13-adversarial"], cwd=self.sb.work, check=True, capture_output=True)

        code, doc, _, err = self.agenda("--json", "--offline")
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", err)
        self.assertEqual(doc["summary"]["active_focus_ticket"], "OPS-13")
        ops = next(r for r in doc["results"] if r["ticket"] == "OPS-13")
        self.assertTrue(ops["is_focus"])
        self.assertEqual(ops["focus_source"], "git_branch")

    # =========================================================================
    # VECTOR 5: Invariantes CQS y Red (Command-Query Separation)
    # =========================================================================

    def test_cqs_no_sqlite_writes(self):
        """5.1 Invariante CQS: 'agenda' NUNCA debe realizar escrituras (INSERT/UPDATE/DELETE) en la base SQLite."""
        self.agenda("--json")
        conn = sqlite3.connect(self.db_path())
        # Instalar triggers destructivos que lanzan abort en cualquier escritura
        tables = ["issues_cache", "session_marks", "worklogs", "issue_snapshots", "issue_sync", "outbox"]
        for t in tables:
            conn.execute(f"CREATE TRIGGER trg_test_cqs_ins_{t} BEFORE INSERT ON {t} BEGIN SELECT RAISE(FAIL, 'CQS Violation: INSERT on {t}'); END;")
            conn.execute(f"CREATE TRIGGER trg_test_cqs_upd_{t} BEFORE UPDATE ON {t} BEGIN SELECT RAISE(FAIL, 'CQS Violation: UPDATE on {t}'); END;")
            conn.execute(f"CREATE TRIGGER trg_test_cqs_del_{t} BEFORE DELETE ON {t} BEGIN SELECT RAISE(FAIL, 'CQS Violation: DELETE on {t}'); END;")
        conn.commit()
        conn.close()

        # Ejecutar agenda en modo normal y en modo brief
        code, doc, out, err = self.agenda("--json", "--offline")
        self.assertEqual(code, 0, f"Violación de CQS o fallo con triggers: {err}")
        self.assertNotIn("CQS Violation", err)

        code_txt, _, _, err_txt = self.agenda("--brief", "--offline")
        self.assertEqual(code_txt, 0, f"Violación de CQS en brief: {err_txt}")
        self.assertNotIn("CQS Violation", err_txt)

    def test_network_isolation_offline(self):
        """5.2 Invariante de Red: con --offline NO debe haber ni una sola petición HTTP."""
        self.agenda("--json")
        requests_before = len(self.sb.fake.requests)

        code, _, _, err = self.agenda("--offline")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.sb.fake.requests), requests_before, "Violación de aislamiento: se realizaron peticiones de red con --offline")

    def test_f14_complete_cannot_be_true_with_warnings(self):
        """5.3 Invariante F14: Si el sobre tiene notas de advertencia (warn), coverage.complete NUNCA puede ser True."""
        self.agenda("--json")
        # Forzar un ticket estancado y wip excedido
        self.sql("UPDATE issues_cache SET assignees_json = ? WHERE ticket_id = 'OMNIFY-1'", (json.dumps([gs.ME]),))
        self.sql("UPDATE issues_cache SET assignees_json = ? WHERE ticket_id = 'OPS-13'", (json.dumps([gs.ME]),))
        old_time = "2026-10-10T10:00:00Z"
        self.sql("UPDATE issues_cache SET plane_updated_at = ?, updated_at = ? WHERE ticket_id = 'OPS-13'", (old_time, old_time))

        code, doc, out, err = self.agenda("--json", "--wip-limit", "1", "--stalled-days", "2", "--offline")
        self.assertEqual(code, 0)
        self.assertIsNotNone(doc)
        has_warns = any(n["code"] in ("wip_exceeded", "ticket_stalled") for n in doc.get("notes") or [])
        self.assertTrue(has_warns, "Deben existir notas de advertencia")
        self.assertIsNot(doc["coverage"].get("complete"), True, "Violación de F14: complete no puede ser True si hay notas de tipo warn")
        self.assertEqual(envelope.validate(doc), [])


if __name__ == "__main__":
    unittest.main()
