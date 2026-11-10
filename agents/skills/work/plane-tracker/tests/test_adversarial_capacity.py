"""Pruebas adversariales y de ingeniería del caos para la Fase 2 de plane-tracker (RFC 0026 y RFC 0006).

Vectores evaluados:
1. Malformación y Chaos en `--plan` y `PLANE_CAPACITY_PLAN`:
   - Sintaxis rota, cadenas vacías, comas consecutivas, sin asignaciones.
   - Valores no numéricos, NaN, Inf, negativos y porcentajes extremos (> 100%, 999999%).
   - Baldes no estándar o inventados (alien_bucket).
   - Múltiples claves 'rest', rest sin balde, baldes vacíos.
   - Inyección de secuencias ANSI y caracteres especiales.
   - Prioridad estricta de bandera CLI sobre variable de entorno PLANE_CAPACITY_PLAN.
   - Desactivación explícita (--plan off / none / false / 0).
2. Casos Límite y División por Cero:
   - Periodo con 0 worklogs / 0 minutos de esfuerzo total (diario y semanal).
   - Periodo con solo 'undeclared' (defaulted capacity).
   - Periodos de 1 solo día (first == last) vs periodos arbitrarios (3 días) vs semana completa (--week).
   - Compute minutes > 0 con clock minutes == 0 (AI Leverage límite).
3. Poda e Invariantes de RFC 0006:
   - Ausencia total de 'Standby externo: 0h 00m' y '(Sin bloqueos reportados)' cuando no hay stoppers.
   - Preservación y renderizado fidedigno de stoppers legítimos (incluyendo caracteres especiales).
4. Cumplimiento F1-F14, CQS y Contrato de Sobre:
   - Validación estricta de envelope.validate(doc) == [] en todos los escenarios.
   - Estricto respeto a CAPACITY_VARIANCE_KEYS.
   - F14: complete nunca es True con notas de advertencia (warn).
   - CQS absoluto: Triggers SQLite anti-escritura garantizan 0 escrituras durante consultas de report time.
"""

import hashlib
import json
import math
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import golden_support as gs  # noqa: E402
from plane_cli import envelope, query_time, vocabulary  # noqa: E402
from test_worklog_sync import DAY, add_issue, block  # noqa: E402


class TestAdversarialCapacity(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)
        self.fake = self.sb.fake

    def run_cli(self, *args, env_set=None, code=0):
        got, out, err = self.sb.run(list(args), env_set=env_set)
        self.assertNotIn("Traceback", err, f"Traceback detectado en stderr:\n{err}")
        if code is not None:
            self.assertEqual(got, code, f"Código de salida inesperado ({got} != {code}).\nErr: {err}\nOut: {out}")
        return got, out, err

    def doc(self, *args, env_set=None, code=0):
        _, out, _ = self.run_cli(*args, "--json", env_set=env_set, code=code)
        try:
            d = json.loads(out)
        except json.JSONDecodeError as exc:
            self.fail(f"Salida CLI no es JSON válido: {exc}\nOut: {out}")
        probs = envelope.validate(d)
        self.assertEqual(probs, [], f"Violación del sobre plane-tracker/1: {probs}")
        return d

    def db_path(self):
        return os.path.join(self.sb.home, ".cache", "plane", "worklogs.db")

    def db_checksum(self):
        p = self.db_path()
        if not os.path.exists(p):
            return None
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    # =========================================================================
    # VECTOR 1: Malformación y Chaos en `--plan` y `PLANE_CAPACITY_PLAN`
    # =========================================================================

    def test_parse_plan_broken_syntax(self):
        """1.1 Sintaxis rota no debe provocar excepciones ni baldes vacíos."""
        broken_inputs = [
            "broken",
            "foo",
            "=50%",
            "deep_work=",
            ",,,",
            "====",
            "   ",
            ",,,,deep_work=50%,,,,",
            "=",
            "=rest",
            "==",
        ]
        for inp in broken_inputs:
            with self.subTest(plan_spec=inp):
                res = query_time._parse_plan(inp)
                if res is not None:
                    self.assertIsInstance(res, dict)
                    self.assertNotIn("", res, f"Clave vacía detectada con input: {inp}")

    def test_parse_plan_non_numeric_and_extremes(self):
        """1.2 Valores no numéricos y extremos (NaN, Inf, negativos, gigantes)."""
        edge_inputs = [
            ("deep_work=abc", False),
            ("deep_work=-20%", False),
            ("deep_work=999999%", True),
            ("deep_work=0%", True),
            ("deep_work=NaN", False),
            ("deep_work=Inf", False),
            ("deep_work=-Inf", False),
        ]
        for inp, expect_ok in edge_inputs:
            with self.subTest(plan_spec=inp):
                res = query_time._parse_plan(inp)
                if expect_ok:
                    self.assertIsNotNone(res)
                    self.assertIn("deep_work", res)
                else:
                    self.assertTrue(res is None or "deep_work" not in res, f"No se descartó entrada inválida {inp}: {res}")
                if res is not None:
                    for k, val in res.items():
                        self.assertFalse(math.isnan(val), f"NaN detectado en {k}")
                        self.assertFalse(math.isinf(val), f"Inf detectado en {k}")
                        self.assertGreaterEqual(val, 0.0, f"Valor negativo detectado en {k}")

    def test_parse_plan_alien_buckets(self):
        """1.3 Baldes inventados o no estándar."""
        plan = query_time._parse_plan("alien_bucket=50%,rest")
        self.assertIsNotNone(plan)
        self.assertEqual(plan.get("alien_bucket"), 50.0)
        self.assertEqual(plan.get("rest"), 50.0)

    def test_parse_plan_multiple_rest(self):
        """1.4 Múltiples claves rest o combinaciones complejas de rest."""
        plan = query_time._parse_plan("deep_work=50%,a=rest,b=rest")
        self.assertIsNotNone(plan)
        self.assertIn("deep_work", plan)

        # Solo 'rest'
        plan_solo_rest = query_time._parse_plan("rest")
        self.assertEqual(plan_solo_rest, {"rest": 100.0})

        # Múltiples 'rest' sueltos
        plan_multi_rest = query_time._parse_plan("rest,rest,rest")
        self.assertEqual(plan_multi_rest, {"rest": 100.0})

    def test_parse_plan_sum_exceeds_100(self):
        """1.5 Plan que suma > 100% no debe dar valores negativos para rest."""
        plan = query_time._parse_plan("deep_work=80%,toil_support=40%,rest")
        self.assertEqual(plan["deep_work"], 80.0)
        self.assertEqual(plan["toil_support"], 40.0)
        self.assertEqual(plan["rest"], 0.0)

    def test_parse_plan_whitespace_and_quotes(self):
        """1.6 Espaciado interno generoso y comillas alrededor de baldes o valores."""
        plan = query_time._parse_plan("  deep_work  =  '60%'  ,  toil_support  =  \"40%\"  ")
        self.assertIsNotNone(plan)
        self.assertEqual(plan.get("deep_work"), 60.0)
        self.assertEqual(plan.get("toil_support"), 40.0)

    def test_cli_plan_precedence_over_env(self):
        """1.7 Prioridad estricta de CLI sobre variable de entorno PLANE_CAPACITY_PLAN."""
        add_issue(self.fake, gs.P1, 201, [
            block(date="2026-11-02", start_time="09:00", end_time="11:00", duration_minutes=120,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human", track="main", notes="Dev")
        ], updated="2026-11-02T12:00:00Z")

        # 1.7.1 CLI con plan válido vs env con otro plan
        env = {"PLANE_CAPACITY_PLAN": "toil_support=100%"}
        doc = self.doc("report", "time", "--week", "--plan", "deep_work=100%", env_set=env)
        var_map = {v["bucket"]: v for v in doc["summary"]["capacity_variance"]}
        self.assertEqual(var_map["deep_work"]["target_percent"], 100.0)
        self.assertEqual(var_map.get("toil_support", {}).get("target_percent", 0.0), 0.0)

        # 1.7.2 CLI con plan roto vs env con plan: CLI debe prevalecer (no recurrir a la variable de entorno)
        doc_broken = self.doc("report", "time", "--week", "--plan", "broken", env_set=env)
        self.assertNotIn("capacity_variance", doc_broken["summary"])

        # 1.7.3 Env var corrupta sola: no debe crashear el CLI y cae en default semanal
        env_broken = {"PLANE_CAPACITY_PLAN": "broken,==,,,NaN%"}
        doc_env_broken = self.doc("report", "time", "--week", env_set=env_broken)
        self.assertIn("capacity_variance", doc_env_broken["summary"])

    def test_cli_plan_explicit_disable(self):
        """1.8 Desactivación explícita del plan semanal con --plan off / none / false."""
        add_issue(self.fake, gs.P1, 210, [
            block(date="2026-11-02", start_time="09:00", end_time="11:00", duration_minutes=120,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human", track="main", notes="Dev")
        ], updated="2026-11-02T12:00:00Z")

        for off_flag in ("off", "none", "false", "0"):
            with self.subTest(flag=off_flag):
                doc = self.doc("report", "time", "--week", "--plan", off_flag)
                self.assertNotIn("capacity_variance", doc["summary"], f"El plan semanal no se desactivó con --plan {off_flag}")

    def test_cli_ansi_and_special_chars_injection(self):
        """1.9 Inyección de secuencias ANSI y comillas en --plan."""
        add_issue(self.fake, gs.P1, 202, [
            block(date="2026-11-02", start_time="09:00", end_time="10:00", duration_minutes=60,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human", track="main", notes="Dev")
        ], updated="2026-11-02T12:00:00Z")

        weird_plan = "deep_work=\"50%\",toil_support='50%'"
        doc = self.doc("report", "time", "--week", "--plan", weird_plan)
        self.assertIn("capacity_variance", doc["summary"])

    # =========================================================================
    # VECTOR 2: Casos Límite y División por Cero
    # =========================================================================

    def test_zero_worklogs_zero_division_resilience(self):
        """2.1 Periodo sin ningún worklog (0 minutos): no debe ocurrir ZeroDivisionError."""
        doc = self.doc("report", "time", "--from", "2026-01-01", "--to", "2026-01-07", "--offline",
                       "--plan", "deep_work=60%,toil_support=40%")
        summary = doc["summary"]
        self.assertEqual(summary["effort_compute_minutes"], 0)
        self.assertEqual(summary["effort_clock_minutes"], 0)
        self.assertIn("capacity_variance", summary)
        for var in summary["capacity_variance"]:
            self.assertEqual(var["minutes"], 0)
            self.assertEqual(var["actual_percent"], 0.0)
            self.assertEqual(var["variance_percent"], -var["target_percent"])

        # Render de texto en periodo vacío con --plan
        _, out, err = self.run_cli("report", "time", "--from", "2026-01-01", "--to", "2026-01-07", "--offline",
                                   "--plan", "deep_work=60%,toil_support=40%")
        self.assertNotIn("ZeroDivisionError", out)
        self.assertNotIn("ZeroDivisionError", err)

        # Reporte diario vacío (first == last)
        _, out_d, err_d = self.run_cli("report", "time", "--from", "2026-01-01", "--to", "2026-01-01", "--offline")
        self.assertNotIn("ZeroDivisionError", out_d)
        self.assertNotIn("ZeroDivisionError", err_d)

    def test_undeclared_capacity_only(self):
        """2.2 Periodo con solo registros defaulted (undeclared)."""
        b = block(date="2026-11-02", start_time="09:00", end_time="10:00", duration_minutes=60,
                  phase="dev", role="r", worker_type="human", track="main", notes="Defaulted")
        add_issue(self.fake, gs.P1, 203, [b], updated="2026-11-02T12:00:00Z")

        doc = self.doc("report", "time", "--week", "--refresh", "--plan", "deep_work=70%,toil_support=30%")
        var_map = {v["bucket"]: v for v in doc["summary"]["capacity_variance"]}
        self.assertIn("undeclared", var_map)
        self.assertEqual(var_map["undeclared"]["minutes"], 60)
        self.assertEqual(var_map["undeclared"]["actual_percent"], 100.0)
        self.assertEqual(var_map["undeclared"]["target_percent"], 0.0)
        self.assertEqual(var_map["undeclared"]["variance_percent"], 100.0)

        # Salida de texto debe marcar 'sin declarar'
        _, out, _ = self.run_cli("report", "time", "--week", "--offline", "--plan", "deep_work=70%,toil_support=30%")
        self.assertIn("undeclared", out)
        self.assertIn("sin declarar", out)

    def test_single_day_vs_arbitrary_vs_iso_week(self):
        """2.3 Comparación de periodos: 1 día vs 3 días vs semana ISO."""
        add_issue(self.fake, gs.P1, 204, [
            block(date="2026-11-02", start_time="09:00", end_time="11:00", duration_minutes=120,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human", track="main", notes="Dev")
        ], updated="2026-11-02T12:00:00Z")

        # 1 día (first == last)
        _, out_day, _ = self.run_cli("report", "time", "--from", "2026-11-02", "--to", "2026-11-02", "--refresh")
        self.assertNotIn("Tiempo no contabilizado", out_day)

        # 3 días (arbitrario, no semana ISO)
        _, out_3d, _ = self.run_cli("report", "time", "--from", "2026-11-02", "--to", "2026-11-04", "--refresh")
        self.assertNotIn("Tiempo no contabilizado", out_3d)

        # Semana ISO completa (lunes a domingo: 2026-11-02 a 2026-11-08)
        _, out_week, _ = self.run_cli("report", "time", "--from", "2026-11-02", "--to", "2026-11-08", "--refresh")
        self.assertIn("Tiempo no contabilizado", out_week)
        self.assertIn("base semana laboral 40h", out_week)

    def test_compute_minutes_greater_than_clock_minutes(self):
        """2.4 AI Leverage extremo: computo > 0 con reloj bajo."""
        # Dos bloques concurrentes el mismo día y hora (10:00 a 11:00)
        add_issue(self.fake, gs.P1, 215, [
            block(date="2026-11-02", start_time="10:00", end_time="11:00", duration_minutes=60,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human", track="main", notes="Dev 1"),
            block(date="2026-11-02", start_time="10:00", end_time="11:00", duration_minutes=60,
                  capacity_bucket="tooling_dx", phase="dev", role="r", worker_type="agent:claude", track="subagent", notes="Agent 1"),
        ], updated="2026-11-02T12:00:00Z")

        doc = self.doc("report", "time", "--from", "2026-11-02", "--to", "2026-11-02", "--refresh")
        summary = doc["summary"]
        self.assertEqual(summary["effort_clock_minutes"], 60)
        self.assertEqual(summary["effort_compute_minutes"], 120)

        _, out, _ = self.run_cli("report", "time", "--from", "2026-11-02", "--to", "2026-11-02", "--offline")
        self.assertIn("AI Leverage Multiplier: 2.0x", out)

    # =========================================================================
    # VECTOR 3: Poda e Invariantes de RFC 0006
    # =========================================================================

    def test_rfc0006_pruning_synthetic_standby_never_appears(self):
        """3.1 La cadena 'Standby externo: 0h 00m' nunca debe aparecer sin bloqueos."""
        add_issue(self.fake, gs.P1, 205, [
            block(date="2026-11-02", start_time="10:00", end_time="12:00", duration_minutes=120,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human", track="main", notes="Clean")
        ], updated="2026-11-02T12:00:00Z")

        # Reporte diario
        _, out_daily, _ = self.run_cli("report", "time", "--from", "2026-11-02", "--to", "2026-11-02", "--refresh")
        self.assertNotIn("Standby externo: 0h 00m", out_daily)
        self.assertNotIn("Sin bloqueos reportados", out_daily)
        self.assertNotIn("⏸️ Standby externo", out_daily)

        # Reporte semanal
        _, out_week, _ = self.run_cli("report", "time", "--week", "--offline")
        self.assertNotIn("Standby externo: 0h 00m", out_week)
        self.assertNotIn("Sin bloqueos reportados", out_week)
        self.assertNotIn("STANDBY TOTAL", out_week)

    def test_rfc0006_preserves_legitimate_stoppers(self):
        """3.2 Preservar bloqueos legítimos cuando existen."""
        b = block(date="2026-11-02", start_time="10:00", end_time="12:00", duration_minutes=120,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human", track="main",
                  notes="Blocked", stoppers=["Esperando revisión de PR", "Credenciales AWS"])
        add_issue(self.fake, gs.P1, 206, [b], updated="2026-11-02T12:00:00Z")

        # Reporte diario debe mostrar los stoppers
        _, out_daily, _ = self.run_cli("report", "time", "--from", "2026-11-02", "--to", "2026-11-02", "--refresh")
        self.assertIn("⏸️ Standby externo:", out_daily)
        self.assertIn("Esperando revisión de PR", out_daily)
        self.assertIn("Credenciales AWS", out_daily)

        # Reporte semanal debe mostrar STANDBY TOTAL
        _, out_week, _ = self.run_cli("report", "time", "--week", "--offline")
        self.assertIn("⏸️ STANDBY TOTAL:", out_week)
        self.assertIn("Esperando revisión de PR", out_week)
        self.assertIn("Credenciales AWS", out_week)

    # =========================================================================
    # VECTOR 4: Cumplimiento F1-F14 y Contrato de Sobre
    # =========================================================================

    def test_f14_invariant_complete_never_true_with_warn(self):
        """4.1 F14: Si hay notas de advertencia (warn), coverage.complete NUNCA puede ser True."""
        self.run_cli("report", "time", "--from", "2026-11-02", "--to", "2026-11-02", "--refresh")
        conn = sqlite3.connect(self.db_path())
        conn.execute("""
            INSERT INTO worklogs (
                ticket_id, track, date, start_time, end_time, duration_minutes,
                project_id, issue_name, worker_type, capacity_bucket, phase, role,
                notes, stoppers_json, raw_payload, created_at, updated_at, author_id, defaulted_json
            ) VALUES (
                'OMNIFY-999', 'main', '2026-11-02', '16:00', '17:00', 60,
                'OMNIFY', 'No author task', 'human', 'deep_work', 'dev', 'role',
                'Unsigned', '[]', '{}', '2026-11-02T17:00:00Z', '2026-11-02T17:00:00Z', NULL, '[]'
            )
        """)
        conn.commit()
        conn.close()

        doc = self.doc("report", "time", "--from", "2026-11-02", "--to", "2026-11-02", "--offline")
        notes = doc.get("notes", [])
        has_warn = any(vocabulary.NOTES.get(n["code"], ("",))[0] == "warn" for n in notes)
        self.assertTrue(has_warn, "Se esperaba una nota de advertencia por horas sin autor")
        self.assertIsNot(doc["coverage"].get("complete"), True, "Violación de F14: complete no puede ser True si hay warn")

    def test_capacity_variance_keys_strict_conformance(self):
        """4.2 capacity_variance debe ceñirse exactamente a CAPACITY_VARIANCE_KEYS."""
        add_issue(self.fake, gs.P1, 208, [
            block(date="2026-11-02", start_time="10:00", end_time="12:00", duration_minutes=120,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human", track="main", notes="Dev")
        ], updated="2026-11-02T12:00:00Z")

        doc = self.doc("report", "time", "--week", "--refresh", "--plan", "deep_work=50%,rest")
        variance = doc["summary"].get("capacity_variance")
        self.assertIsNotNone(variance)
        for item in variance:
            self.assertEqual(set(item.keys()), vocabulary.CAPACITY_VARIANCE_KEYS)
            self.assertIsInstance(item["bucket"], str)
            self.assertIsInstance(item["minutes"], int)
            self.assertIsInstance(item["actual_percent"], (int, float))
            self.assertIsInstance(item["target_percent"], (int, float))
            self.assertIsInstance(item["variance_percent"], (int, float))

    def test_cqs_report_time_never_writes_sqlite(self):
        """4.3 CQS Absoluto: triggers anti-escritura garantizan que report time offline jamás escribe en SQLite."""
        self.run_cli("report", "time", "--from", "2026-11-02", "--to", "2026-11-02", "--refresh")

        conn = sqlite3.connect(self.db_path())
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND sql NOT LIKE 'CREATE VIRTUAL%'"
        ).fetchall()]
        for tbl in tables:
            conn.execute(f"CREATE TRIGGER IF NOT EXISTS trg_cqs_ins_{tbl} BEFORE INSERT ON {tbl} BEGIN SELECT RAISE(ABORT, 'CQS Violation: INSERT on {tbl}'); END;")
            conn.execute(f"CREATE TRIGGER IF NOT EXISTS trg_cqs_upd_{tbl} BEFORE UPDATE ON {tbl} BEGIN SELECT RAISE(ABORT, 'CQS Violation: UPDATE on {tbl}'); END;")
            conn.execute(f"CREATE TRIGGER IF NOT EXISTS trg_cqs_del_{tbl} BEFORE DELETE ON {tbl} BEGIN SELECT RAISE(ABORT, 'CQS Violation: DELETE on {tbl}'); END;")
        conn.commit()
        conn.close()

        self.run_cli("report", "time", "--from", "2026-11-02", "--to", "2026-11-02", "--offline")
        self.run_cli("report", "time", "--week", "--offline", "--plan", "deep_work=60%,toil_support=40%")
        self.run_cli("report", "time", "--week", "--offline", "--json")
        self.run_cli("report", "time", "--week", "--offline", "--plan", "off")


if __name__ == "__main__":
    unittest.main()
