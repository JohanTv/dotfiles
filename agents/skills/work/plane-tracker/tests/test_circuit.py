"""Circuito de fallo rápido: apertura, enfriamiento escalonado, sonda única entre procesos, reset por éxito y 429."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from plane_cli import circuit, config  # noqa: E402

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return datetime.fromtimestamp(self.t, timezone.utc)


class CircuitCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        for patcher in (mock.patch.object(config, "CACHE_DIR", self.tmp.name), mock.patch.object(config, "now", self.clock)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.probes = []

    def probe_with(self, ok, kind=None):
        def run():
            self.probes.append(self.clock.t)
            return ok, kind
        return run

    def fail(self, kind="refused", times=1):
        for _ in range(times):
            circuit.record(False, kind)

    def state(self):
        with open(os.path.join(self.tmp.name, "circuit.json"), encoding="utf-8") as handle:
            return json.load(handle)


class Opening(CircuitCase):
    def test_opens_after_two_consecutive_failures_only(self):
        self.fail()
        circuit.gate(self.probe_with(True))
        self.assertEqual(circuit.describe()["state"], "closed")
        self.fail()
        self.assertEqual(circuit.describe()["state"], "open")
        with self.assertRaises(circuit.PlaneUnavailable) as ctx:
            circuit.gate(self.probe_with(True))
        self.assertEqual((ctx.exception.kind, ctx.exception.delivered), ("circuit_open", "no"))
        self.assertEqual(ctx.exception.cause, "conexión rechazada")
        self.assertEqual(self.probes, [])

    def test_success_resets_the_streak(self):
        self.fail()
        circuit.record(True)
        self.fail()
        self.assertEqual(circuit.describe()["state"], "closed")
        self.assertEqual(self.state()["consec"], 1)

    def test_failures_outside_the_window_do_not_add_up(self):
        self.fail()
        self.clock.t += circuit.WINDOW + 1
        self.fail()
        self.assertEqual(circuit.describe()["state"], "closed")

    def test_state_file_is_private(self):
        self.fail(times=2)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.tmp.name, "circuit.json")).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.tmp.name, "circuit.json.lock")).st_mode), 0o600)

    def test_since_is_the_first_failure_of_the_episode(self):
        self.fail()
        first = self.state()["since"]
        self.clock.t += 20
        self.fail()
        self.assertEqual(self.state()["since"], first)
        self.assertEqual(circuit.describe()["since"], circuit.hhmm(first))


class Cooldown(CircuitCase):
    def open(self):
        self.fail(times=2)

    def test_escalating_cooldowns_and_ceiling(self):
        self.open()
        for expected in (30, 60, 120, 300, 300):
            level = min(self.state()["level"], 3)
            self.assertEqual(circuit.COOLDOWNS[level], expected)
            self.clock.t += expected - 1
            with self.assertRaises(circuit.PlaneUnavailable):
                circuit.gate(self.probe_with(False, "timeout"))
            self.assertEqual(self.probes, [], "no se sondea antes de vencer el enfriamiento")
            self.clock.t += 1
            with self.assertRaises(circuit.PlaneUnavailable) as ctx:
                circuit.gate(self.probe_with(False, "timeout"))
            self.assertEqual(ctx.exception.kind, "timeout")
            self.probes.clear()

    def test_successful_probe_closes_and_resets(self):
        self.open()
        self.clock.t += 31
        circuit.gate(self.probe_with(True))
        self.assertEqual(len(self.probes), 1)
        state = self.state()
        self.assertEqual((state["consec"], state["opened_at"], state["level"]), (0, None, 0))
        circuit.gate(self.probe_with(True))
        self.assertEqual(len(self.probes), 1)

    def test_probe_lease_blocks_other_callers(self):
        self.open()
        self.clock.t += 31
        outcome = []

        def slow_probe():
            with self.assertRaises(circuit.PlaneUnavailable) as ctx:
                circuit.gate(self.probe_with(True))
            outcome.append(ctx.exception.kind)
            return True, None
        circuit.gate(slow_probe)
        self.assertEqual(outcome, ["circuit_open"])
        self.assertEqual(self.probes, [])

    def test_explicit_probe(self):
        self.assertIsNone(circuit.probe(self.probe_with(True)))
        self.open()
        self.assertIsNone(circuit.probe(self.probe_with(True)), "en enfriamiento no sondea sin force")
        self.assertTrue(circuit.probe(self.probe_with(True), force=True))
        self.assertEqual(circuit.describe()["state"], "closed")
        self.open()
        self.assertFalse(circuit.probe(self.probe_with(False, "dns"), force=True))
        self.assertEqual(self.state()["level"], 1)

    def test_retry_in_and_describe(self):
        self.open()
        self.clock.t += 10
        info = circuit.describe()
        self.assertEqual((info["state"], info["next_probe_in"], info["cause"]), ("open", 20, "conexión rechazada"))
        self.assertEqual(circuit.retry_in(), 20)


class Processes(unittest.TestCase):
    def test_single_probe_across_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "circuit.json"), "w", encoding="utf-8") as handle:
                json.dump({"consec": 2, "opened_at": 1.0, "level": 0, "probing_until": 0, "last_error": "refused", "since": 1.0,
                           "last_ok": None, "skipped": 0}, handle)
            script = (
                "import sys, time\n"
                f"sys.path.insert(0, {SCRIPTS!r})\n"
                "from plane_cli import circuit, config\n"
                f"config.CACHE_DIR = {tmp!r}\n"
                "def run():\n"
                f"    open({os.path.join(tmp, 'probes')!r}, 'a').write('x\\n'); time.sleep(0.6); return True, None\n"
                "try:\n    circuit.gate(run)\nexcept circuit.PlaneUnavailable:\n    pass\n")
            procs = [subprocess.Popen([sys.executable, "-c", script]) for _ in range(5)]
            for proc in procs:
                self.assertEqual(proc.wait(timeout=30), 0)
            with open(os.path.join(tmp, "probes"), encoding="utf-8") as handle:
                self.assertEqual(len(handle.read().split()), 1)


if __name__ == "__main__":
    unittest.main()
