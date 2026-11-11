"""Pruebas de la exportación Markdown (--markdown) en `report time`, `report flow` y `agenda`.

Verifica tablas, encabezados, métricas y retrocompatibilidad limpia.
"""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402
from test_worklog_sync import DAY, add_issue, block  # noqa: E402


class TestReportMarkdown(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)
        self.fake = self.sb.fake

    def run_cli(self, *args, code=0, **kwargs):
        got, out, err = self.sb.run(list(args), **kwargs)
        self.assertNotIn("Traceback", err)
        self.assertEqual(got, code, err + out)
        return out, err

    def sql(self, statement, params=()):
        conn = sqlite3.connect(os.path.join(self.sb.home, ".cache", "plane", "worklogs.db"))
        conn.execute(statement, params)
        conn.commit()
        conn.close()

    def test_report_time_single_day_markdown(self):
        add_issue(self.fake, gs.P1, 10, [
            block(date=DAY, start_time="09:00", end_time="11:30", duration_minutes=150,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human",
                  track="main", notes="Implement auth refactor")
        ])
        out, _ = self.run_cli("report", "time", "--from", DAY, "--to", DAY, "--markdown")
        self.assertIn("# 📋 Reporte de Actividad —", out)
        self.assertIn("### 📊 Resumen Ejecutivo", out)
        self.assertIn("- **Tiempo Reloj Activo:** `2h 30m`", out)
        self.assertIn("- **Esfuerzo Entregado (Cómputo):**", out)
        self.assertIn("### 📝 Actividades Realizadas", out)
        self.assertIn("| Ticket | Título | Horario | Duración | Balde | Notas |", out)
        self.assertIn("`OMNIFY-10`", out)
        self.assertIn("09:00 - 11:30", out)
        self.assertIn("Implement auth refactor", out)
        self.assertIn("### 📁 Distribución por Proyecto", out)
        self.assertIn("`OMNIFY`", out)

    def test_report_time_weekly_markdown_with_plan(self):
        other = "2026-10-21"
        add_issue(self.fake, gs.P1, 11, [
            block(date=DAY, start_time="09:00", end_time="11:00", duration_minutes=120,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human",
                  track="main", notes="Feature core"),
            block(date=other, start_time="10:00", end_time="11:00", duration_minutes=60,
                  capacity_bucket="toil_support", phase="ops", role="r", worker_type="human",
                  track="ops", notes="Support call"),
        ])
        out, _ = self.run_cli("report", "time", "--from", DAY, "--to", other, "--markdown",
                              "--plan", "deep_work=60%,toil_support=40%")
        self.assertIn("# 📅 Reporte", out)
        self.assertIn("### 📊 Resumen Ejecutivo", out)
        self.assertIn("- **Tiempo Reloj Activo:**", out)
        self.assertIn("### 🎯 Distribución por Capacidad", out)
        self.assertIn("| Balde / Capacidad | Tiempo Reloj | % Real | Meta | Varianza |", out)
        self.assertIn("`deep_work`", out)
        self.assertIn("60.0%", out)
        self.assertIn("### 📅 Desglose Diario de Actividades", out)
        self.assertIn("`OMNIFY-11`", out)

    def test_report_flow_markdown(self):
        # Primero poblamos datos en caché para report flow
        add_issue(self.fake, gs.P1, 12, [
            block(date=DAY, start_time="09:00", end_time="10:00", duration_minutes=60,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human",
                  track="main", notes="Task flow")
        ])
        self.run_cli("report", "time", "--from", DAY, "--to", DAY)

        out, _ = self.run_cli("report", "flow", "--from", DAY, "--to", DAY, "--markdown")
        self.assertIn("# 🔁 Reporte de Flujo de Entrega (Lead & Cycle Time)", out)
        self.assertIn(f"**Período:** `{DAY}` → `{DAY}`", out)
        self.assertIn("### 📋 Detalle de Tickets", out)
        self.assertIn("| Estado | Ticket | Título | Lead Time | Cycle Activo | Standby | Esfuerzo (Reloj / Cómputo) |", out)
        self.assertIn("`OMNIFY-12`", out)
        self.assertIn("### 📊 Resumen Métrico de Flujo", out)
        self.assertIn("- **Mediana Lead Time:**", out)
        self.assertIn("- **Mediana Cycle Time (Activo):**", out)

    def test_agenda_markdown(self):
        self.run_cli("list")
        self.sql("INSERT INTO session_marks (agent, session_id, ticket, started_at, ended_at) VALUES ('agy', 'sess-1', 'OPS-13', 1000, NULL)")
        out, _ = self.run_cli("agenda", "--markdown")
        self.assertIn("# 🎯 Agenda Personal", out)
        self.assertIn("### 📊 Estado y Capacidad Semanal", out)
        self.assertIn("- **WIP:**", out)
        self.assertIn("### 🔥 En Curso", out)
        self.assertIn("| Foco | Ticket | Prioridad | Título | Estado / Progreso |", out)
        self.assertIn("`OPS-13`", out)
        self.assertIn("▶", out)

    def test_markdown_cell_pipe_escaping(self):
        add_issue(self.fake, gs.P1, 13, [
            block(date=DAY, start_time="09:00", end_time="10:00", duration_minutes=60,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human",
                  track="main", notes="Pipe test: a | b | c")
        ])
        out, _ = self.run_cli("report", "time", "--from", DAY, "--to", DAY, "--markdown")
        self.assertIn("a \\| b \\| c", out)

    def test_backward_compatibility_without_markdown_flag(self):
        add_issue(self.fake, gs.P1, 14, [
            block(date=DAY, start_time="09:00", end_time="10:00", duration_minutes=60,
                  capacity_bucket="deep_work", phase="dev", role="r", worker_type="human",
                  track="main", notes="Compat test")
        ])
        out_normal, _ = self.run_cli("report", "time", "--from", DAY, "--to", DAY)
        self.assertNotIn("# 📋 Reporte de Actividad", out_normal)
        self.assertIn("================================================================================", out_normal)


if __name__ == "__main__":
    unittest.main()
