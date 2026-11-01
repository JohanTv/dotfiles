"""La normalización de la fecha de hoy debe ser simétrica: una fecha fija del fixture que coincida con el día en que corre
la suite no puede hacer fallar los golden (ocurrió el 2026-11-01, día de una fecha del fixture)."""
import os
import re
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


class FixtureDates(unittest.TestCase):
    """Una fecha fija de fixture que sea de hoy o futura es una bomba: el día que "hoy" la alcance, la suite fallará solo ese día
    (ocurrió el 2026-11-01 con una fecha escrita pocos días antes). Las fechas de los fixtures y de los escenarios deben ser pasadas."""

    FILES = ("golden_support.py", "test_golden.py")

    def test_fixture_and_scenario_dates_are_in_the_past(self):
        today = datetime.now().strftime("%Y-%m-%d")
        for name in self.FILES:
            with open(os.path.join(os.path.dirname(__file__), name), encoding="utf-8") as handle:
                text = handle.read()
            for date in sorted(set(re.findall(r"\b(20\d\d-\d\d-\d\d)\b", text))):
                self.assertLess(date, today, f"{name}: la fecha {date} es de hoy o futura; usa una fecha pasada (si no, un día cualquiera coincidirá con 'hoy')")


if __name__ == "__main__":
    unittest.main()
