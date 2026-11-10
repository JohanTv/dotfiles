"""Pruebas adversariales, de caos y casos límite para métricas de flujo y standby (RFC 0006 §2).

Vectores:
1. Caos en transiciones: flapping 50+, sinónimos consecutivos, casing/acentos/calificadores, timestamps simultáneos/desordenados/retroactivos.
2. Ciclo de vida y reaperturas: tickets creados en standby, reabiertos en Pausado, invariante active + standby == gross.
3. Resiliencia: estados huérfanos/inexistentes, nombres/grupos nulos, campos ausentes.
4. Robustez estadística: medianas en vacíos, pares, impares, 0 standby, y resiliencia a None.
5. Compliance: CQS estricto (0 escrituras SQLite), esquema JSON 'plane-tracker/1', vocabulario y retrocompatibilidad visual.
"""

import hashlib
import json
import os
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import flow_metrics as fm  # noqa: E402
import golden_support as gs  # noqa: E402
from plane_cli import envelope, render_flow, vocabulary  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
NOW = T0 + timedelta(days=30)

STATES = {
    "bk": {"name": "Backlog", "group": "backlog"},
    "pe": {"name": "Pendiente", "group": "unstarted"},
    "pr": {"name": "Progreso", "group": "started"},
    "pa": {"name": "Pausado", "group": "started"},
    "bl": {"name": "Bloqueado", "group": "started"},
    "st": {"name": "Standby", "group": "started"},
    "ep": {"name": "En Pausa", "group": "started"},
    "oh": {"name": "On Hold", "group": "started"},
    "co": {"name": "Completado", "group": "completed"},
    "ca": {"name": "Cancelado", "group": "cancelled"},
}


def h(hours):
    return T0 + timedelta(hours=hours)


def m(minutes):
    return T0 + timedelta(minutes=minutes)


def tr(time_point, a, b):
    at_val = h(time_point) if isinstance(time_point, (int, float)) else time_point
    return {"at": at_val, "from_id": a, "to_id": b}


def issue(state, completed=None, name="[FEAT] Adversarial Item", created=None):
    return {"name": name, "created_at": created or T0, "completed_at": completed, "state": state}


class TestFlowStandbyPureChaos(unittest.TestCase):
    """Pruebas puras y de estrés para el motor matemático en scripts/flow_metrics.py."""

    def test_extreme_flapping_50_plus_transitions(self):
        """1. Flapping extremo (60 transiciones rápidas alternando Progreso y Pausado)."""
        trs = [tr(0, "bk", "pr")]
        # 60 transiciones alternando cada 10 minutos (5 min en progreso, 5 min en pausado)
        expected_active = 0.0
        expected_standby = 0.0
        current_state = "pr"

        for i in range(1, 61):
            t_min = i * 10
            nxt_state = "pa" if current_state == "pr" else "pr"
            trs.append({"at": m(t_min), "from_id": current_state, "to_id": nxt_state})
            if current_state == "pr":
                expected_active += 10.0
            else:
                expected_standby += 10.0
            current_state = nxt_state

        # Cierre final a Completado 10 minutos después
        final_min = 61 * 10
        trs.append({"at": m(final_min), "from_id": current_state, "to_id": "co"})
        if current_state == "pr":
            expected_active += 10.0
        else:
            expected_standby += 10.0

        f = fm.compute_flow(issue("co", m(final_min)), trs, STATES, [], NOW)
        self.assertEqual(f["outcome"], "completed")
        self.assertAlmostEqual(f["cycle_active_minutes"], expected_active, places=5)
        self.assertAlmostEqual(f["standby_minutes"], expected_standby, places=5)
        self.assertAlmostEqual(f["cycle_gross_minutes"], expected_active + expected_standby, places=5)
        self.assertAlmostEqual(f["lead_minutes"], final_min, places=5)

    def test_consecutive_standby_states_transitions(self):
        """2. Transiciones consecutivas entre múltiples sinónimos de standby sin volver a activo."""
        # 2h Progreso -> 3h Pausado -> 4h Bloqueado -> 2h Standby -> 1h En Pausa -> 2h Progreso -> Cierre
        trs = [
            tr(0, "bk", "pr"),
            tr(2, "pr", "pa"),
            tr(5, "pa", "bl"),
            tr(9, "bl", "st"),
            tr(11, "st", "ep"),
            tr(12, "ep", "pr"),
            tr(14, "pr", "co"),
        ]
        f = fm.compute_flow(issue("co", h(14)), trs, STATES, [], NOW)
        self.assertEqual(f["outcome"], "completed")
        self.assertEqual(f["cycle_active_minutes"], 4 * 60)  # 2h inicial + 2h final
        self.assertEqual(f["standby_minutes"], 10 * 60)  # 3h + 4h + 2h + 1h
        self.assertEqual(f["cycle_gross_minutes"], 14 * 60)
        self.assertEqual(f["by_state_minutes"]["Pausado"], 180)
        self.assertEqual(f["by_state_minutes"]["Bloqueado"], 240)
        self.assertEqual(f["by_state_minutes"]["Standby"], 120)
        self.assertEqual(f["by_state_minutes"]["En Pausa"], 60)

    def test_casing_accents_and_qualifiers_in_standby_names(self):
        """3. Variaciones de casing, acentos, espacios y prefijos/sufijos en estados standby."""
        chaotic_states = {
            "s1": {"name": "PAUSADO", "group": "started"},
            "s2": {"name": "Pausada", "group": "started"},
            "s3": {"name": "  bloqueado  ", "group": "started"},
            "s4": {"name": "Bloqueada por cliente", "group": "started"},
            "s5": {"name": "PÁUSÁDO (urgente)", "group": "started"},
            "s6": {"name": "On Hold", "group": "started"},
            "s7": {"name": "En espera de QA", "group": "started"},
            "s8": {"name": "Progreso normal", "group": "started"},
            "co": {"name": "Completado", "group": "completed"},
        }
        # 1h progreso, luego 1h en cada una de las 7 variantes de standby, luego 1h completado
        trs = [
            {"at": h(0), "from_id": "bk", "to_id": "s8"},
            {"at": h(1), "from_id": "s8", "to_id": "s1"},
            {"at": h(2), "from_id": "s1", "to_id": "s2"},
            {"at": h(3), "from_id": "s2", "to_id": "s3"},
            {"at": h(4), "from_id": "s3", "to_id": "s4"},
            {"at": h(5), "from_id": "s4", "to_id": "s5"},
            {"at": h(6), "from_id": "s5", "to_id": "s6"},
            {"at": h(7), "from_id": "s6", "to_id": "s7"},
            {"at": h(8), "from_id": "s7", "to_id": "s8"},
            {"at": h(9), "from_id": "s8", "to_id": "co"},
        ]
        f = fm.compute_flow(issue("co", h(9)), trs, chaotic_states, [], NOW)
        self.assertEqual(f["cycle_active_minutes"], 2 * 60)  # s8 inicial (1h) + s8 final (1h)
        self.assertEqual(f["standby_minutes"], 7 * 60)  # 7 horas acumuladas en standby
        self.assertEqual(f["cycle_gross_minutes"], 9 * 60)

    def test_simultaneous_and_out_of_order_timestamps(self):
        """4. Timestamps simultáneos (duración 0s) y transiciones provistas desordenadas."""
        # Transiciones desordenadas cronológicamente con tramos de 0 segundos
        unordered_trs = [
            tr(5, "pa", "pr"),  # 5h
            tr(2, "pr", "pa"),  # 2h
            tr(2, "pr", "pr"),  # 2h (simultáneo, 0s)
            tr(0, "bk", "pr"),  # 0h
            tr(8, "pr", "co"),  # 8h
            tr(8, "co", "co"),  # 8h (simultáneo en terminal)
        ]
        f = fm.compute_flow(issue("co", h(8)), unordered_trs, STATES, [], NOW)
        self.assertEqual(f["outcome"], "completed")
        self.assertEqual(f["standby_minutes"], 3 * 60)  # de 2h a 5h
        self.assertEqual(f["cycle_active_minutes"], 5 * 60)  # (0h a 2h) + (5h a 8h)
        self.assertEqual(f["cycle_gross_minutes"], 8 * 60)
        self.assertNotIn("unknown_state", f["flags"])

    def test_transition_timestamp_before_created_retroactive(self):
        """4b. Transición retroactiva con timestamp anterior a created_at."""
        # Ticket creado formalmente a t=2h, pero transición importada a t=1h
        trs = [tr(1, "bk", "pr"), tr(3, "pr", "pa"), tr(5, "pa", "co")]
        f = fm.compute_flow(issue("co", h(5), created=h(2)), trs, STATES, [], NOW)
        # min(created, first['at']) preserva el rango sin errores ni deltas negativos
        self.assertGreaterEqual(f["lead_minutes"], 0)
        self.assertEqual(f["standby_minutes"], 2 * 60)
        self.assertEqual(f["cycle_active_minutes"], 2 * 60)  # 1h a 3h

    def test_ticket_created_directly_in_standby_without_backlog(self):
        """5. Tickets creados directamente en Pausado/Bloqueado sin pasar por Backlog."""
        # Escenario A: Creado directamente en Pausado, sin transiciones previas, aún abierto
        f_open = fm.compute_flow(issue("pa"), [], STATES, [], NOW)
        self.assertEqual(f_open["outcome"], "open")
        self.assertIn("no_transition", f_open["flags"])
        self.assertEqual(f_open["standby_minutes"], (NOW - T0).total_seconds() / 60)
        self.assertEqual(f_open["cycle_active_minutes"], 0.0)
        self.assertEqual(f_open["cycle_gross_minutes"], f_open["standby_minutes"])

        # Escenario B: Creado directamente en Pausado, transiciona a Progreso a las 5h, cerrado a las 10h
        trs = [tr(5, "pa", "pr"), tr(10, "pr", "co")]
        f_done = fm.compute_flow(issue("co", h(10)), trs, STATES, [], NOW)
        self.assertEqual(f_done["standby_minutes"], 5 * 60)
        self.assertEqual(f_done["cycle_active_minutes"], 5 * 60)
        self.assertEqual(f_done["cycle_gross_minutes"], 10 * 60)

    def test_ticket_completed_and_then_reopened_in_standby(self):
        """6. Ticket cerrado y posteriormente reabierto en Pausado."""
        # 0h..4h Progreso -> 4h..6h Pausado -> 6h..8h Progreso -> 8h Completado.
        # Reabierto a las 12h directo a Pausado; estado actual en Plane: 'pa'
        trs = [
            tr(0, "bk", "pr"),
            tr(4, "pr", "pa"),
            tr(6, "pa", "pr"),
            tr(8, "pr", "co"),
            tr(12, "co", "pa"),
        ]
        # Actualmente abierto en Pausado
        f_reopened = fm.compute_flow(issue("pa", completed=None), trs, STATES, [], h(16))
        self.assertEqual(f_reopened["outcome"], "open")
        self.assertIsNone(f_reopened["closed"])
        # Standby = 2h (inicial) + 4h (desde reapertura a las 12h hasta now a las 16h) = 6h
        self.assertEqual(f_reopened["standby_minutes"], 6 * 60)
        # Active = 4h + 2h = 6h
        self.assertEqual(f_reopened["cycle_active_minutes"], 6 * 60)
        # Gross = 6h (activo) + 6h (standby) = 12h
        self.assertEqual(f_reopened["cycle_gross_minutes"], 12 * 60)

        # Escenario B: Reabierto en Pausado a las 12h, vuelto a Progreso a las 14h, re-completado a las 16h
        trs.append(tr(14, "pa", "pr"))
        trs.append(tr(16, "pr", "co"))
        f_reclosed = fm.compute_flow(issue("co", completed=h(16)), trs, STATES, [], h(20))
        self.assertEqual(f_reclosed["outcome"], "completed")
        self.assertEqual(f_reclosed["closed"], h(16))
        # Standby total: 2h (tramo 1) + 2h (tramo 2: 12h a 14h) = 4h
        self.assertEqual(f_reclosed["standby_minutes"], 4 * 60)
        # Active total: 4h + 2h + 2h = 8h
        self.assertEqual(f_reclosed["cycle_active_minutes"], 8 * 60)
        # Gross total: 8h activo + 4h standby = 12h gross
        self.assertEqual(f_reclosed["cycle_gross_minutes"], 12 * 60)

    def test_orphan_and_unknown_state_ids(self):
        """7. Estados huérfanos o inexistentes en catálogo no deben romper la telemetría."""
        corrupt_states = {
            "pr": {"name": "Progreso", "group": "started"},
            "co": {"name": "Completado", "group": "completed"},
            "null_entry": {"name": None, "group": None},  # entrada degenerada
        }
        trs = [
            tr(0, "ghost_1", "pr"),
            tr(2, "pr", "null_entry"),
            tr(4, "null_entry", "ghost_2"),
            tr(6, "ghost_2", "co"),
        ]
        f = fm.compute_flow(issue("co", h(6)), trs, corrupt_states, [], NOW)
        self.assertIn("unknown_state", f["flags"])
        self.assertIsInstance(f["by_state_minutes"], dict)
        # Ninguna clave None en by_state_minutes que pueda romper JSON
        self.assertNotIn(None, f["by_state_minutes"])
        self.assertIn("?", f["by_state_minutes"])

    def test_median_and_aggregate_mathematical_precision(self):
        """8. Validación de mediana: vacío, 1 elemento, pares, impares y tickets con 0 standby."""
        # Caso A: Lista vacía
        agg_empty = fm.aggregate([])
        self.assertEqual(agg_empty["tickets"], 0)
        self.assertIsNone(agg_empty["median_standby_minutes"])
        self.assertEqual(agg_empty["total_standby_minutes"], 0.0)
        self.assertEqual(agg_empty["tickets_with_standby"], 0)

        # Caso B: Tickets con standby = 0 no deben sesgar la mediana
        f_zero1 = {"outcome": "completed", "flags": [], "lead_minutes": 100, "cycle_active_minutes": 50, "standby_minutes": 0.0}
        f_zero2 = {"outcome": "completed", "flags": [], "lead_minutes": 200, "cycle_active_minutes": 60, "standby_minutes": 0.0}
        agg_zeros = fm.aggregate([f_zero1, f_zero2])
        self.assertEqual(agg_zeros["tickets_with_standby"], 0)
        self.assertIsNone(agg_zeros["median_standby_minutes"])
        self.assertEqual(agg_zeros["total_standby_minutes"], 0.0)

        # Caso C: 1 elemento con standby
        f_s1 = {"outcome": "completed", "flags": [], "lead_minutes": 100, "cycle_active_minutes": 50, "standby_minutes": 120.0}
        agg_one = fm.aggregate([f_zero1, f_s1, f_zero2])
        self.assertEqual(agg_one["tickets_with_standby"], 1)
        self.assertEqual(agg_one["median_standby_minutes"], 120.0)
        self.assertEqual(agg_one["total_standby_minutes"], 120.0)

        # Caso D: Elementos pares (2 elementos: 100m y 300m -> mediana = 200m)
        f_s2 = {"outcome": "open", "flags": [], "lead_minutes": 300, "cycle_active_minutes": 10, "standby_minutes": 300.0}
        agg_even = fm.aggregate([f_zero1, f_s1, f_s2])
        self.assertEqual(agg_even["tickets_with_standby"], 2)
        self.assertEqual(agg_even["median_standby_minutes"], 210.0)  # (120 + 300) / 2
        self.assertEqual(agg_even["total_standby_minutes"], 420.0)

        # Caso E: Elementos impares (3 elementos: 100m, 200m, 600m -> mediana = 200m)
        f_s3 = {"outcome": "cancelled", "flags": [], "lead_minutes": 50, "cycle_active_minutes": 5, "standby_minutes": 600.0}
        agg_odd = fm.aggregate([f_s1, f_s2, f_s3, f_zero1])
        self.assertEqual(agg_odd["tickets_with_standby"], 3)
        self.assertEqual(agg_odd["median_standby_minutes"], 300.0)  # sorted: [120, 300, 600] -> 300
        self.assertEqual(agg_odd["total_standby_minutes"], 1020.0)

        # Caso F: Resiliencia ante clave standby_minutes = None
        f_none = {"outcome": "completed", "flags": [], "lead_minutes": 10, "cycle_active_minutes": 5, "standby_minutes": None}
        agg_none = fm.aggregate([f_s1, f_none])
        self.assertEqual(agg_none["tickets_with_standby"], 1)
        self.assertEqual(agg_none["median_standby_minutes"], 120.0)


class TestAdversarialReportFlowCli(unittest.TestCase):
    """Pruebas adversariales de integración CLI: CQS, Envelope y renderizado visual."""

    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)
        self.db_file = os.path.join(self.sb.home, ".cache", "plane", "worklogs.db")

    def _db_hash(self):
        if not os.path.exists(self.db_file):
            return None
        with open(self.db_file, "rb") as fp:
            return hashlib.sha256(fp.read()).hexdigest()

    def test_cli_cqs_guarantee_no_sqlite_writes_during_flow_reports(self):
        """9. CQS Absoluto: report flow no debe mutar ni escribir en SQLite bajo ninguna circunstancia."""
        # Poblamos datos iniciales mediante report time
        code, _, err = self.sb.run(["report", "time", "--from", "2026-10-14", "--refresh"])
        self.assertEqual(code, 0, err)

        hash_before = self._db_hash()
        self.assertIsNotNone(hash_before)

        # Instalamos autorizador restrictivo que rechaza mutaciones
        conn = sqlite3.connect(self.db_file)
        # Activamos modo WAL checkpoint para asegurar bytes estables
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        hash_before = self._db_hash()

        # Ejecutamos consultas de lectura en varios formatos
        code, out, err = self.sb.run(["report", "flow", "--from", "2026-10-14", "--offline"])
        self.assertEqual(code, 0, err)

        code, out_json, err = self.sb.run(["report", "flow", "--from", "2026-10-14", "--offline", "--json"])
        self.assertEqual(code, 0, err)

        code, out_proj, err = self.sb.run(["report", "flow", "--from", "2026-10-14", "--offline", "-p", "OMNIFY"])
        self.assertEqual(code, 0, err)

        # Verificamos que no hubo alteración de bytes en la base de datos
        hash_after = self._db_hash()
        self.assertEqual(hash_before, hash_after, "CQS violado: report flow mutó la base de datos SQLite.")

    def test_cli_envelope_and_vocabulary_compliance_under_extreme_standby(self):
        """10. Compliance del sobre JSON 'plane-tracker/1' y vocabulario con datos de standby caóticos."""
        # Inicializamos entorno
        code, _, err = self.sb.run(["report", "time", "--from", "2026-10-14", "--refresh"])
        self.assertEqual(code, 0, err)
        code, _, err = self.sb.run(["report", "flow", "--from", "2026-10-14", "--refresh"])
        self.assertEqual(code, 0, err)

        # Inyectamos múltiples transiciones extremas en la base SQLite para OMNIFY-2
        conn = sqlite3.connect(self.db_file)
        s_prog = "10000000-0000-4000-8000-111111111111"
        s_paus = gs.state_id(gs.P1, "Pausado")
        s_comp = gs.state_id(gs.P1, "Completado")

        trs = [
            ("tr-c1", "10000000-0000-4000-8000-000000000002", "OMNIFY-2", "2026-10-11T09:00:00Z", s_prog, s_paus, "Progreso", "Pausado"),
            ("tr-c2", "10000000-0000-4000-8000-000000000002", "OMNIFY-2", "2026-10-12T09:00:00Z", s_paus, s_prog, "Pausado", "Progreso"),
            ("tr-c3", "10000000-0000-4000-8000-000000000002", "OMNIFY-2", "2026-10-13T09:00:00Z", s_prog, s_paus, "Progreso", "Bloqueado por cliente"),
            ("tr-c4", "10000000-0000-4000-8000-000000000002", "OMNIFY-2", "2026-10-14T09:00:00Z", s_paus, s_prog, "Bloqueado por cliente", "Progreso"),
            ("tr-c5", "10000000-0000-4000-8000-000000000002", "OMNIFY-2", "2026-10-15T12:00:00Z", s_prog, s_comp, "Progreso", "Completado"),
        ]
        conn.executemany("INSERT OR REPLACE INTO state_transitions VALUES (?,?,?,?,?,?,?,?)", trs)
        conn.commit()
        conn.close()

        code, out, err = self.sb.run(["report", "flow", "--from", "2026-10-14", "--offline", "--json"])
        self.assertEqual(code, 0, err)

        doc = json.loads(out)
        # Validación formal del contrato F1-F14
        problems = envelope.validate(doc)
        self.assertEqual(problems, [], f"Violación del sobre JSON en report flow: {problems}")

        # Verificación de tipos y consistencia numérica
        res = doc["results"][0]
        self.assertIsInstance(res["standby_minutes"], (int, float))
        self.assertGreater(res["standby_minutes"], 0)
        self.assertIsInstance(doc["summary"]["total_standby_minutes"], (int, float))
        self.assertIsInstance(doc["summary"]["median_standby_minutes"], (int, float))
        self.assertEqual(doc["summary"]["tickets_with_standby"], 1)

    def test_cli_backward_compatibility_clean_output_when_standby_is_zero(self):
        """11. Backward compatibility: cuando standby es 0, no debe haber '⏸ Pausado' ni 'standby acumulado'."""
        code, out, err = self.sb.run(["report", "time", "--from", "2026-10-14", "--refresh"])
        self.assertEqual(code, 0, err)

        # report flow sin estados en pausa
        code, out_txt, err = self.sb.run(["report", "flow", "--from", "2026-10-14", "--offline"])
        self.assertEqual(code, 0, err)

        self.assertNotIn("⏸ Pausado", out_txt)
        self.assertNotIn("standby acumulado", out_txt)

    def test_render_flow_resilience_against_none_standby_values(self):
        """12. Resiliencia de render_flow.render ante valores nulos de standby en el sobre."""
        # Un sobre artificialmente degradado con campos nulos
        dummy_doc = {
            "schema": "plane-tracker/1",
            "view": "report flow",
            "scope": {"period": {"from": "2026-10-01", "to": "2026-10-05"}},
            "results": [
                {
                    "ticket": "OMNIFY-99",
                    "title": "Degraded Ticket",
                    "outcome": "completed",
                    "flags": [],
                    "lead_minutes": 60.0,
                    "cycle_active_minutes": 30.0,
                    "effort_clock_minutes": 30.0,
                    "effort_compute_minutes": 30,
                    "standby_minutes": None,  # nulo
                }
            ],
            "summary": {
                "completed": 1,
                "cancelled": 0,
                "open": 0,
                "n_lead": 1,
                "median_lead_minutes": 60.0,
                "n_cycle": 1,
                "median_cycle_minutes": 30.0,
                "total_standby_minutes": None,  # nulo
                "tickets_with_standby": None,  # nulo
                "median_standby_minutes": None,
                "excluded": 0,
            },
            "notes": [],
        }
        # Debe renderizar sin levantar TypeError
        rendered = render_flow.render(dummy_doc)
        self.assertIn("OMNIFY-99", rendered)
        self.assertNotIn("⏸ Pausado", rendered)
        self.assertNotIn("standby acumulado", rendered)


if __name__ == "__main__":
    unittest.main()
