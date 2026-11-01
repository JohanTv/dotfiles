"""La normalización de la fecha de hoy debe ser simétrica: una fecha fija del fixture que coincida con el día en que corre
la suite no puede hacer fallar los golden (ocurrió el 2026-11-01, día de una fecha del fixture)."""
import os
import sys
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import golden_support as gs  # noqa: E402


class TodayPlaceholder(unittest.TestCase):
    def collapse_with_today(self, text, year, month, day):
        with mock.patch.object(gs, "datetime") as fake:
            fake.now.return_value = datetime(year, month, day, 12, 0)
            return gs.today_placeholder(text)

    def test_a_fixture_date_equal_to_today_collapses_on_both_sides(self):
        actual, golden = "vence 2026-11-01 (01/11/2026)", "vence 2026-11-01 (01/11/2026)"
        self.assertEqual(self.collapse_with_today(actual, 2026, 11, 1), self.collapse_with_today(golden, 2026, 11, 1))
        self.assertEqual(self.collapse_with_today(golden, 2026, 11, 1), "vence <HOY> (<HOY>)")

    def test_other_days_leave_fixture_dates_untouched(self):
        text = "vence 2026-11-01"
        self.assertEqual(self.collapse_with_today(text, 2026, 10, 31), text)
        self.assertEqual(self.collapse_with_today(text, 2027, 3, 9), text)


if __name__ == "__main__":
    unittest.main()
