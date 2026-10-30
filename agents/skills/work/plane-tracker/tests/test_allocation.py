import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import session_clock as sc  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def m(minutes):
    return T0 + timedelta(minutes=minutes)


class ActiveRuns(unittest.TestCase):
    def test_pause_is_excluded_and_runs_are_additive(self):
        stamps = [m(0), m(5), m(40), m(45)]
        whole = sc.active_runs(stamps, m(0), m(60))
        self.assertEqual(sc.total_minutes(whole), 10)
        left = sc.active_runs(stamps, m(0), m(3))
        right = sc.active_runs(stamps, m(3), m(60))
        self.assertAlmostEqual(sc.total_minutes(left) + sc.total_minutes(right), 10)

    def test_window_clips_a_delta(self):
        runs = sc.active_runs([m(0), m(8)], m(2), m(6))
        self.assertEqual(runs, [(m(2), m(6))])

    def test_single_event_has_no_runs(self):
        self.assertEqual(sc.active_runs([m(0)], m(0), m(60)), [])


class Intervals(unittest.TestCase):
    def test_subtract_and_intersect(self):
        runs = [(m(0), m(10)), (m(20), m(30))]
        self.assertEqual(sc.subtract(runs, [(m(5), m(25))]), [(m(0), m(5)), (m(25), m(30))])
        self.assertEqual(sc.intersect(runs, [(m(5), m(25))]), [(m(5), m(10)), (m(20), m(25))])
        self.assertEqual(sc.subtract(runs, []), runs)

    def test_cut_runs_is_contiguous_and_exact(self):
        runs = [(m(0), m(10)), (m(20), m(30))]  # 20 min de actividad con una pausa en medio
        a, b = sc.cut_runs(runs, [12, 8])
        self.assertEqual(sc.total_minutes(a), 12)
        self.assertEqual(sc.total_minutes(b), 8)
        self.assertEqual(a[-1][1], b[0][0])  # el corte cae donde se acumula la cuota
        self.assertEqual(a, [(m(0), m(10)), (m(20), m(22))])


class Split(unittest.TestCase):
    def test_percent_and_rest(self):
        self.assertEqual(sc.parse_split("A=60%,B=rest", 10), [("A", 6), ("B", 4)])

    def test_largest_remainder_sums_exactly(self):
        got = sc.parse_split("A=33.34%,B=33.33%,C=33.33%", 10)
        self.assertEqual(sum(m_ for _, m_ in got), 10)
        self.assertEqual(sorted(m_ for _, m_ in got), [3, 3, 4])

    def test_minutes(self):
        self.assertEqual(sc.parse_split("A=40m,B=rest", 100), [("A", 40), ("B", 60)])

    def test_errors(self):
        bad = [
            ("A=70%,B=50%", 10),
            ("A=100%,B=rest", 10),
            ("A=50%,B=rest,C=rest", 10),
            ("A=50%,B=40m", 10),
            ("A=40m,B=rest", 35),
            ("A=50%,B=rest", 1),
            ("A=50%,A=rest", 10),
            ("A=abc", 10),
            ("A=60%", 0),
        ]
        for spec, total in bad:
            with self.assertRaises(ValueError, msg=spec):
                sc.parse_split(spec, total)

    def test_partial_without_rest_leaves_remainder(self):
        self.assertEqual(sc.parse_split("A=30%", 10), [("A", 3)])


if __name__ == "__main__":
    unittest.main()
