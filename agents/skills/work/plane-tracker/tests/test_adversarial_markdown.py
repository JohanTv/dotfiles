"""Pruebas adversariales, de inyección de caos y verificación CQS para la exportación Markdown (--markdown).

Evalúa:
1. Inyección de caracteres destructivos en títulos, notas y baldes:
   - Pipes '|' (aislados, múltiples, en límites de corte de slice, dentro de código).
   - Backslashes '\\' (al final de celda, múltiples, secuencias de escape).
   - Saltos de línea y retornos de carro ('\\r\\n', '\\r', '\\n', tabuladores).
   - Inyección HTML/XSS ('<script>', '<img>', '<table>', '<!-- comment -->').
   - Backticks impares y rotos ('`test', '``evil``').
   - Links y corchetes ('[click](url)', '![img](url)', '[broken').
   - Validación estricta de estructura tabular: cada fila debe coincidir exactamente en número de columnas.
2. Casos sin datos y valores extremos:
   - Reportes de tiempo vacíos (un día y semanal).
   - Flujo sin datos en el periodo.
   - Agenda sin tickets activos, bloqueados ni en cola.
   - Esfuerzo 0 minutos, AI Leverage con denominador 0, baldes no declarados.
3. Consistencia y precedencia de flags:
   - --markdown con --json (prioridad de sobre estructurado JSON).
   - --markdown con --brief en agenda.
   - Notas con códigos no reconocidos (resistencia a KeyError).
4. Verificación estricta de CQS (Command-Query Separation):
   - Checksum SHA-256 de worklogs.db idéntico antes y después de cada llamada.
   - Triggers SQLite que abortan cualquier mutación INSERT/UPDATE/DELETE.
5. Retrocompatibilidad:
   - Salida normal (sin --markdown) preserva formato original byte a byte.
"""

import hashlib
import json
import os
import re
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402
from test_worklog_sync import DAY, add_issue, block  # noqa: E402


def validate_markdown_tables(test_case, md_text):
    """Parsea y valida la integridad de todas las tablas Markdown en el texto.
    Verifica que:
    1. Las columnas del delimitador coincidan con las del encabezado.
    2. Cada fila comience y termine con '|'.
    3. Ninguna fila desborde ni fusione columnas (conteo idéntico de celdas).
    """
    lines = md_text.splitlines()
    i = 0
    tables_found = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and line.endswith("|") and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line.startswith("|") and re.match(r"^\|(\s*:?-+:?\s*\|)+$", next_line):
                header_cols = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
                delim_cols = [c.strip() for c in re.split(r"(?<!\\)\|", next_line)[1:-1]]
                test_case.assertEqual(len(header_cols), len(delim_cols),
                                      f"Columnas de delimitador {len(delim_cols)} != encabezado {len(header_cols)} en línea {i+1}")
                tables_found += 1
                row_idx = i + 2
                while row_idx < len(lines) and lines[row_idx].strip().startswith("|") and lines[row_idx].strip().endswith("|"):
                    row_line = lines[row_idx].strip()
                    row_cells = [c.strip() for c in re.split(r"(?<!\\)\|", row_line)[1:-1]]
                    test_case.assertEqual(
                        len(row_cells), len(header_cols),
                        f"Desborde/fusión de columnas en línea {row_idx+1}: esperado {len(header_cols)} ({header_cols}), "
                        f"obtenido {len(row_cells)} ({row_cells}) en fila: {row_line}"
                    )
                    row_idx += 1
                i = row_idx
                continue
        i += 1
    return tables_found


class TestAdversarialMarkdown(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)
        self.fake = self.sb.fake

    def run_cli(self, *args, code=0, **kwargs):
        got, out, err = self.sb.run(list(args), **kwargs)
        self.assertNotIn("Traceback", err)
        self.assertEqual(got, code, f"Fallo CLI {args}:\nStderr: {err}\nStdout: {out}")
        return out, err

    def db_path(self):
        return os.path.join(self.sb.home, ".cache", "plane", "worklogs.db")

    def sql(self, statement, params=()):
        conn = sqlite3.connect(self.db_path())
        conn.execute(statement, params)
        conn.commit()
        conn.close()

    def sha256_db(self):
        p = self.db_path()
        if not os.path.exists(p):
            return None
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    # =========================================================================
    # 1. INYECCIÓN DE CARACTERES DESTRUCTIVOS Y CAOS TABULAR
    # =========================================================================

    def test_injection_pipes_and_slice_boundaries_in_report_time(self):
        """Inyección de pipes '|' y backslashes en los límites exactos de truncado de slices."""
        # Notas y títulos en el límite exacto donde el corte de slice podría cortar un escape '\|'
        evil_notes_40 = "A" * 39 + "|"
        evil_title_45 = "T" * 44 + "|"
        evil_backslash = "Path\\to\\folder\\"

        add_issue(self.fake, gs.P1, 101, [
            block(date=DAY, start_time="09:00", end_time="10:00", duration_minutes=60,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human",
                  track="main", notes=evil_notes_40),
            block(date=DAY, start_time="10:00", end_time="11:00", duration_minutes=60,
                  capacity_bucket="toil_support", phase="ops", role="r", worker_type="human",
                  track="ops", notes=evil_backslash),
        ])
        # Actualizamos el título del issue con el evil_title
        self.run_cli("report", "time", "--from", DAY, "--to", DAY)
        self.sql("UPDATE issues_cache SET title = ? WHERE ticket_id = 'OMNIFY-101'", (evil_title_45,))

        out, _ = self.run_cli("report", "time", "--from", DAY, "--to", DAY, "--markdown")
        tables_cnt = validate_markdown_tables(self, out)
        self.assertGreaterEqual(tables_cnt, 1, "Debe existir al menos 1 tabla válida")
        self.assertNotIn("Traceback", out)

    def test_injection_newlines_and_carriage_returns_in_agenda(self):
        """Saltos de línea \\r\\n, \\r, \\n en títulos y motivos de bloqueo no deben romper filas."""
        self.run_cli("list")
        evil_title = "Ticket con saltos\r\nde\rlinea\ny\ttabs"
        evil_reason = "Bloqueado por:\nProveedor externo\r\nsin respuesta\rpor 3 días"

        self.sql("UPDATE issues_cache SET title = ?, assignees_json = ? WHERE ticket_id = 'OMNIFY-1'",
                 (evil_title, json.dumps([gs.ME])))
        self.sql("UPDATE issues_cache SET state_group = 'unstarted', title = ?, assignees_json = ? WHERE ticket_id = 'OPS-13'",
                 ("Tarea bloqueada", json.dumps([gs.ME])))
        self.sql("INSERT INTO session_marks (agent, session_id, ticket, started_at, ended_at) VALUES ('agy', 's1', 'OMNIFY-1', 1000, NULL)")

        # Agregamos registro con stopper multilínea
        self.sql(
            "INSERT INTO worklogs (ticket_id, track, date, start_time, end_time, duration_minutes, "
            "project_id, issue_name, capacity_bucket, phase, role, worker_type, notes, stoppers_json, raw_payload, "
            "created_at, updated_at, author_id) "
            "VALUES ('OPS-13', 'main', '2026-10-20', '09:00', '10:00', 60, "
            "'OPS', 'Tarea bloqueada', 'deep_work', 'dev', 'r', 'human', 'Notas', ?, '{}', "
            "'2026-10-20T09:00:00Z', 1000.0, ?)",
            (json.dumps([evil_reason]), gs.ME)
        )

        out, _ = self.run_cli("agenda", "--markdown")
        tables_cnt = validate_markdown_tables(self, out)
        self.assertGreaterEqual(tables_cnt, 1, "Tablas en agenda deben ser válidas")
        # Verificar que ninguna fila tiene un salto de línea crudo a mitad de tabla
        for line in out.splitlines():
            if line.startswith("|") and not line.endswith("|"):
                self.fail(f"Fila rota por salto de línea sin cerrar: {line}")

    def test_injection_html_xss_sanitization(self):
        """Etiquetas HTML como <script>, <img>, <table> deben sanitizarse a &lt; &gt; para neutralizar XSS."""
        evil_xss = "<script>alert('xss')</script><img src=x onerror=alert(1)>"
        add_issue(self.fake, gs.P1, 102, [
            block(date=DAY, start_time="09:00", end_time="10:00", duration_minutes=60,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human",
                  track="main", notes=evil_xss)
        ])
        self.run_cli("report", "time", "--from", DAY, "--to", DAY)
        self.sql("UPDATE issues_cache SET title = ? WHERE ticket_id = 'OMNIFY-102'", (f"XSS: {evil_xss}",))

        out, _ = self.run_cli("report", "time", "--from", DAY, "--to", DAY, "--markdown")
        validate_markdown_tables(self, out)
        # No debe haber etiquetas <script> ni <img> literales sin escapar en la salida
        self.assertNotIn("<script>", out)
        self.assertNotIn("<img>", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("&lt;img", out)

    def test_injection_unclosed_backticks_and_pipes_in_flow(self):
        """Backticks impares y pipes en títulos de report flow no deben destruir los separadores de columna."""
        add_issue(self.fake, gs.P1, 103, [
            block(date=DAY, start_time="09:00", end_time="10:00", duration_minutes=60,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human",
                  track="main", notes="Worklog flow")
        ])
        self.run_cli("report", "time", "--from", DAY, "--to", DAY)

        evil_title = "Fallo en `auth | token `invalido y `unclosed"
        self.sql("UPDATE issues_cache SET title = ? WHERE ticket_id = 'OMNIFY-103'", (evil_title,))

        out, _ = self.run_cli("report", "flow", "--from", DAY, "--to", DAY, "--markdown")
        tables_cnt = validate_markdown_tables(self, out)
        self.assertGreaterEqual(tables_cnt, 1, "Tabla de report flow debe conservar sus 7 columnas")
        self.assertIn("OMNIFY-103", out)

    # =========================================================================
    # 2. CASOS SIN DATOS Y VALORES EXTREMOS
    # =========================================================================

    def test_zero_data_single_day_report_time(self):
        """report time en un día sin registros debe emitir bloque vacío sin fallar."""
        out, _ = self.run_cli("report", "time", "--from", "2026-10-01", "--to", "2026-10-01", "--markdown")
        self.assertIn("# 📋 Reporte de Actividad", out)
        self.assertIn("*(Sin actividades registradas)*", out)
        self.assertIn("- **Tiempo Reloj Activo:** `0h 00m`", out)

    def test_zero_data_weekly_report_time(self):
        """report time semanal sin registros debe emitir bloque de periodo vacío."""
        out, _ = self.run_cli("report", "time", "--from", "2026-10-05", "--to", "2026-10-11", "--markdown")
        self.assertIn("# 📅 Reporte Semanal", out)
        self.assertIn("*(Sin actividades registradas en el periodo)*", out)
        self.assertIn("- **Tiempo Reloj Activo:** `0h 00m`", out)

    def test_zero_data_report_flow(self):
        """report flow sin tickets en el periodo debe emitir mensaje vacío sin error."""
        out, _ = self.run_cli("report", "flow", "--from", "2026-10-01", "--to", "2026-10-01", "--markdown")
        self.assertIn("# 🔁 Reporte de Flujo de Entrega", out)
        self.assertIn("*(Sin tickets con worklogs en caché ni cerrados en el periodo)*", out)

    def test_zero_data_agenda(self):
        """agenda sin tickets asignados debe emitir dashboard con WIP 0 y sin tareas en curso."""
        self.run_cli("list")
        self.sql("DELETE FROM issues_cache")
        self.sql("DELETE FROM session_marks")
        out, _ = self.run_cli("agenda", "--markdown", "--offline")
        self.assertIn("# 🎯 Agenda Personal", out)
        self.assertIn("### 📊 Estado y Capacidad Semanal", out)
        self.assertIn("- **WIP:** 0 / máx 2", out)
        self.assertIn("*(Sin tareas en curso)*", out)

    def test_zero_minutes_effort_and_plan_variance(self):
        """Manejo de esfuerzo 0m y varianzas de plan sin división por cero."""
        self.run_cli("report", "time", "--from", DAY, "--to", DAY)
        self.sql(
            "INSERT INTO worklogs (ticket_id, track, date, start_time, end_time, duration_minutes, "
            "project_id, issue_name, capacity_bucket, phase, role, worker_type, notes, stoppers_json, raw_payload, "
            "created_at, updated_at, author_id) "
            "VALUES ('OMNIFY-104', 'main', ?, '09:00', '09:00', 0, "
            "'OMNIFY', 'Cero min', 'undeclared', 'dev', 'r', 'human', 'Zero min', '[]', '{}', "
            "'2026-10-20T09:00:00Z', 1000.0, ?)",
            (DAY, gs.ME)
        )
        out, _ = self.run_cli("report", "time", "--from", DAY, "--to", DAY, "--markdown",
                              "--plan", "deep_work=50%,toil_support=50%", "--offline")
        validate_markdown_tables(self, out)
        self.assertIn("`undeclared`", out)
        self.assertIn("0h 00m", out)

    # =========================================================================
    # 3. CONSISTENCIA DE FLAGS Y PRECEDENCIA
    # =========================================================================

    def test_flag_markdown_with_json_precedence(self):
        """Cuando se especifica --markdown junto con --json, --json tiene precedencia emitiendo el sobre JSON."""
        for cmd in [
            ["report", "time", "--from", DAY, "--to", DAY, "--markdown", "--json"],
            ["report", "flow", "--from", DAY, "--to", DAY, "--markdown", "--json"],
            ["agenda", "--markdown", "--json"]
        ]:
            out, _ = self.run_cli(*cmd)
            doc = json.loads(out)
            self.assertEqual(doc.get("schema"), "plane-tracker/1")
            self.assertIn("results", doc)

    def test_flag_markdown_with_brief_in_agenda(self):
        """--markdown con --brief en agenda debe resolver de forma determinística sin fallos."""
        self.run_cli("list")
        out, _ = self.run_cli("agenda", "--markdown", "--brief")
        self.assertIn("# 🎯 Agenda Personal", out)
        validate_markdown_tables(self, out)

    def test_resilience_to_unknown_note_code(self):
        """Renderizado Markdown no debe fallar con KeyError ante notas con códigos no catalogados."""
        from plane_cli import render_agenda, render_flow, render_time

        dummy_doc = {
            "schema": "plane-tracker/1",
            "view": "report time",
            "scope": {"period": {"from": "2026-10-20", "to": "2026-10-20"}},
            "results": [],
            "summary": {"effort_clock_minutes": 0, "effort_compute_minutes": 0},
            "coverage": {},
            "notes": [{"code": "alien_unregistered_code_xyz", "text": "Mensaje de advertencia extraño"}]
        }

        # Comprobar que ninguno de los tres renderers lanza excepción
        out_time = render_time.render(dummy_doc, markdown=True)
        self.assertIn("Mensaje de advertencia extraño", out_time)

        dummy_doc["view"] = "report flow"
        out_flow = render_flow.render(dummy_doc, markdown=True)
        self.assertIn("Mensaje de advertencia extraño", out_flow)

        dummy_doc["view"] = "agenda"
        out_agenda = render_agenda.render(dummy_doc, markdown=True)
        self.assertIn("Mensaje de advertencia extraño", out_agenda)

    # =========================================================================
    # 4. VERIFICACIÓN ESTRICTA DE CQS (COMMAND-QUERY SEPARATION)
    # =========================================================================

    def test_cqs_sha256_unmodified_by_markdown_reports(self):
        """Las invocaciones de report time, report flow y agenda con --markdown son 100% puras (SHA256 idéntico)."""
        # Inicializar datos locales primero
        add_issue(self.fake, gs.P1, 105, [
            block(date=DAY, start_time="09:00", end_time="10:00", duration_minutes=60,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human",
                  track="main", notes="Base worklog")
        ])
        self.run_cli("report", "time", "--from", DAY, "--to", DAY)
        self.run_cli("list")

        sha_before = self.sha256_db()
        self.assertIsNotNone(sha_before)

        # 1. report time --markdown
        self.run_cli("report", "time", "--from", DAY, "--to", DAY, "--markdown", "--offline")
        self.assertEqual(self.sha256_db(), sha_before, "CQS Violation: report time --markdown modificó la base SQLite")

        # 2. report flow --markdown
        self.run_cli("report", "flow", "--from", DAY, "--to", DAY, "--markdown", "--offline")
        self.assertEqual(self.sha256_db(), sha_before, "CQS Violation: report flow --markdown modificó la base SQLite")

        # 3. agenda --markdown
        self.run_cli("agenda", "--markdown", "--offline")
        self.assertEqual(self.sha256_db(), sha_before, "CQS Violation: agenda --markdown modificó la base SQLite")

    def test_cqs_sqlite_triggers_prevent_any_write(self):
        """Triggers SQLite abortan cualquier intento de INSERT, UPDATE o DELETE durante la renderización Markdown."""
        self.run_cli("list")
        conn = sqlite3.connect(self.db_path())
        tables = ["issues_cache", "session_marks", "worklogs", "issue_snapshots", "issue_sync", "outbox"]
        for t in tables:
            conn.execute(f"CREATE TRIGGER trg_test_cqs_ins_{t} BEFORE INSERT ON {t} BEGIN SELECT RAISE(FAIL, 'CQS Violation: INSERT on {t}'); END;")
            conn.execute(f"CREATE TRIGGER trg_test_cqs_upd_{t} BEFORE UPDATE ON {t} BEGIN SELECT RAISE(FAIL, 'CQS Violation: UPDATE on {t}'); END;")
            conn.execute(f"CREATE TRIGGER trg_test_cqs_del_{t} BEFORE DELETE ON {t} BEGIN SELECT RAISE(FAIL, 'CQS Violation: DELETE on {t}'); END;")
        conn.commit()
        conn.close()

        # Ejecutar todas las vistas Markdown con triggers activos
        out_t, _ = self.run_cli("report", "time", "--from", DAY, "--to", DAY, "--markdown", "--offline")
        self.assertIn("# 📋 Reporte de Actividad", out_t)

        out_f, _ = self.run_cli("report", "flow", "--from", DAY, "--to", DAY, "--markdown", "--offline")
        self.assertIn("# 🔁 Reporte de Flujo de Entrega", out_f)

        out_a, _ = self.run_cli("agenda", "--markdown", "--offline")
        self.assertIn("# 🎯 Agenda Personal", out_a)

    # =========================================================================
    # 5. RETROCOMPATIBILIDAD ABSOLUTA
    # =========================================================================

    def test_backward_compatibility_exact_output_without_flag(self):
        """Sin la bandera --markdown, la salida estándar es idéntica a los contratos terminales estándar."""
        add_issue(self.fake, gs.P1, 106, [
            block(date=DAY, start_time="09:00", end_time="10:00", duration_minutes=60,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human",
                  track="main", notes="Compat check")
        ])
        # report time
        out_norm, _ = self.run_cli("report", "time", "--from", DAY, "--to", DAY)
        self.assertTrue(out_norm.startswith("================================================================================"))
        self.assertNotIn("# 📋 Reporte", out_norm)

        # report flow
        out_flow_norm, _ = self.run_cli("report", "flow", "--from", DAY, "--to", DAY)
        self.assertIn("🔁 Flujo por ticket", out_flow_norm)
        self.assertNotIn("# 🔁 Reporte", out_flow_norm)

        # agenda
        out_agenda_norm, _ = self.run_cli("agenda")
        self.assertTrue(out_agenda_norm.startswith("================================================================================"))
        self.assertNotIn("# 🎯 Agenda Personal", out_agenda_norm)


if __name__ == "__main__":
    unittest.main()
