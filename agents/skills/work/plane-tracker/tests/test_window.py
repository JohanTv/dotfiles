"""Ventana real del trabajo (defecto 0001): `--date`, `--since` y `--until` en `comment add` y `comment edit`.

La suite congela el reloj central: ninguna prueba depende de la fecha ni de la hora reales.
"""
import os
import sys
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from plane_cli import clock  # noqa: E402
from plane_cli.errors import CliError  # noqa: E402
from plane_cli.worklog import parse_date, recalculate_window_duration, requested_date, resolve_window  # noqa: E402

AHORA = datetime(2026, 11, 2, 12, 0)  # lunes al mediodía: toda ventana pasada es válida y toda futura, no


class Window(unittest.TestCase):
    def setUp(self):
        for target, value in (("local_now", AHORA), ("local_today", AHORA.date())):
            patcher = mock.patch.object(clock, target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    # --- ventana válida --------------------------------------------------------
    def test_both_bounds_define_the_duration(self):
        self.assertEqual(resolve_window("09:00", "10:00"), ("09:00", "10:00", 60))

    def test_duration_must_match_the_interval(self):
        self.assertEqual(resolve_window("09:00", "10:00", 60), ("09:00", "10:00", 60))
        with self.assertRaisesRegex(CliError, "no coincide con el intervalo"):
            resolve_window("09:00", "10:00", 90)

    def test_single_bound_completes_with_the_duration(self):
        self.assertEqual(resolve_window("10:30", None, 45), ("10:30", "11:15", 45))
        self.assertEqual(resolve_window(None, "10:00", 30), ("09:30", "10:00", 30))

    def test_without_flags_there_is_no_window(self):
        self.assertIsNone(resolve_window(None, None, 60))

    def test_a_past_date_carries_a_long_retroactive_window(self):
        self.assertEqual(resolve_window("14:40", "18:20", None, datetime(2026, 10, 30).date()),
                         ("14:40", "18:20", 220))

    # --- banderas inválidas ---------------------------------------------------
    def test_one_bound_without_duration_is_rejected(self):
        with self.assertRaisesRegex(CliError, "hace falta la duración"):
            resolve_window("09:00", None)

    def test_until_before_since_is_rejected(self):
        with self.assertRaisesRegex(CliError, "posterior a --since"):
            resolve_window("10:00", "09:00")

    def test_malformed_clock_is_rejected(self):
        with self.assertRaisesRegex(CliError, "formato HH:MM"):
            resolve_window("9am", None, 30)

    def test_window_crossing_midnight_is_rejected(self):
        with self.assertRaisesRegex(CliError, "cruza la medianoche"):
            resolve_window("23:30", None, 60)

    def test_future_window_is_rejected(self):
        with self.assertRaisesRegex(CliError, "termina en el futuro"):
            resolve_window("23:00", "23:59")

    def test_duration_must_be_an_integer(self):
        with self.assertRaisesRegex(CliError, "entero de minutos"):
            resolve_window("09:00", None, "abc")

    # --- fecha ----------------------------------------------------------------
    def test_requested_date_defaults_to_today_and_refuses_the_future(self):
        self.assertEqual(requested_date(None), AHORA.date())
        self.assertEqual(requested_date("2026-10-30"), datetime(2026, 10, 30).date())
        with self.assertRaisesRegex(CliError, "no puede ser futuro"):
            requested_date("2999-01-01")
        with self.assertRaisesRegex(CliError, "YYYY-MM-DD"):
            requested_date("01/11/2026")

    def test_parse_date_returns_none_when_it_is_not_a_date(self):
        self.assertEqual(parse_date("2026-11-02"), datetime(2026, 11, 2).date())
        self.assertIsNone(parse_date("hoy"))
        self.assertIsNone(parse_date(None))

    # --- recálculo de ventana (defecto 0032) -----------------------------------
    def test_recalculate_window_duration_advances_end_time(self):
        self.assertEqual(recalculate_window_duration("10:00", 45, datetime(2026, 10, 20).date()), "10:45")
        self.assertEqual(recalculate_window_duration("09:00", 90, datetime(2026, 10, 20).date()), "10:30")

    def test_recalculate_window_duration_crossing_midnight_is_rejected(self):
        with self.assertRaisesRegex(CliError, "cruza la medianoche"):
            recalculate_window_duration("23:30", 45, datetime(2026, 10, 20).date())

    def test_recalculate_window_duration_into_future_is_rejected(self):
        # AHORA es 2026-11-02 12:00
        with self.assertRaisesRegex(CliError, "termina en el futuro"):
            recalculate_window_duration("11:30", 45, AHORA.date())


if __name__ == "__main__":
    unittest.main()
