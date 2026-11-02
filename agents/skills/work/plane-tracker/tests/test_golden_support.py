"""El reloj de las pruebas golden: el lanzador `plane_clock.py` congela la hora real del CLI, el `Sandbox` la controla y ninguna
prueba depende de la fecha del día en que corre (el 2026-11-01 una fecha futura de un fixture coincidió con "hoy" y rompió tres
golden solo ese día)."""
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import golden_support as gs  # noqa: E402
import run_parallel as rp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PLANE = os.path.join(HERE, "..", "scripts", "plane.py")
INSTANT = "2026-11-02T12:00:00+00:00"


def run_launcher(*args, env_extra=None):
    with tempfile.TemporaryDirectory() as home:
        env = {"PATH": os.environ.get("PATH", ""), "HOME": home, "TZ": "UTC", "LC_ALL": "C.UTF-8", "PYTHONIOENCODING": "utf-8", **(env_extra or {})}
        return subprocess.run([sys.executable, gs.CLOCK_PY, *args], env=env, capture_output=True, text=True, timeout=60)


class ClockLauncher(unittest.TestCase):
    def probe(self, body):
        handle = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
        handle.write(textwrap.dedent(body))
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_every_way_of_reading_the_clock_sees_the_frozen_instant(self):
        script = self.probe("""
            import time
            from datetime import datetime, timedelta, timezone
            print(datetime.now().isoformat(), datetime.now(timezone.utc).isoformat(), datetime.today().isoformat(), time.time())
            print(datetime.now().date(), (datetime.now() - timedelta(minutes=15)).strftime("%H:%M"))
        """)
        proc = run_launcher("2026-11-02T12:00:00+00:00", script)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines(), ["2026-11-02T12:00:00 2026-11-02T12:00:00+00:00 2026-11-02T12:00:00 1793620800.0", "2026-11-02 11:45"])

    def test_repeated_reads_are_identical_and_other_instants_work(self):
        script = self.probe("""
            from datetime import datetime
            a = datetime.now(); b = datetime.now()
            print(a == b, a.isoformat())
        """)
        self.assertEqual(run_launcher("2028-02-29T00:05:00+00:00", script).stdout.strip(), "True 2028-02-29T00:05:00")

    def test_exit_code_and_script_name_pass_through(self):
        script = self.probe("""
            import os, sys
            print(os.path.basename(sys.argv[0]), sys.argv[1:])
            sys.exit(7)
        """)
        proc = run_launcher(INSTANT, script, "uno", "dos")
        self.assertEqual(proc.returncode, 7)
        self.assertEqual(proc.stdout.strip(), f"{os.path.basename(script)} ['uno', 'dos']")

    def test_instant_without_timezone_is_rejected(self):
        proc = run_launcher("2026-11-02T12:00:00", PLANE)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("zona horaria", proc.stderr)

    def test_help_is_identical_with_and_without_the_launcher(self):
        with tempfile.TemporaryDirectory() as home:
            env = {"PATH": os.environ.get("PATH", ""), "HOME": home, "TZ": "UTC", "LC_ALL": "C.UTF-8", "PYTHONIOENCODING": "utf-8"}
            plain = subprocess.run([sys.executable, PLANE, "--help"], env=env, capture_output=True, text=True, timeout=60)
        launched = run_launcher(INSTANT, PLANE, "--help")
        self.assertEqual((launched.returncode, launched.stdout, launched.stderr), (plain.returncode, plain.stdout, plain.stderr))


    def test_module_mode_freezes_the_whole_process(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "probe_mod.py"), "w", encoding="utf-8") as handle:
                handle.write("import sys, time\nfrom datetime import datetime\nprint(datetime.now().isoformat(), time.time(), sys.argv[1:])\n")
            proc = run_launcher("2031-12-31T23:59:30+00:00", "-m", "probe_mod", "a", env_extra={"PYTHONPATH": folder})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "2031-12-31T23:59:30 1956527970.0 ['a']")

    def test_module_mode_requires_a_module(self):
        proc = run_launcher(INSTANT, "-m")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("falta el módulo", proc.stderr)


class ParallelRunnerFreeze(unittest.TestCase):
    def command_for(self, freeze):
        with mock.patch.object(rp.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")) as run:
            rp.run_job(["test_clock"], freeze)
        return run.call_args[0][0]

    def test_without_freeze_the_job_is_plain_unittest(self):
        self.assertEqual(self.command_for(None)[1:], ["-m", "unittest", "test_clock"])

    def test_freeze_runs_each_job_through_the_launcher(self):
        command = self.command_for("2031-12-31T23:59:30+00:00")
        self.assertEqual(command[1], gs.CLOCK_PY)
        self.assertEqual(command[2:], ["2031-12-31T23:59:30+00:00", "-m", "unittest", "test_clock"])


class SandboxClock(unittest.TestCase):
    def test_the_clock_is_frozen_by_default_and_advances_only_when_asked(self):
        sb = gs.Sandbox()
        self.addCleanup(sb.close)
        start = sb.now
        sb.advance(90)
        self.assertEqual(sb.now, start + 90)

    def test_a_sandbox_can_opt_out_to_the_real_clock(self):
        sb = gs.Sandbox(clock=None)
        self.addCleanup(sb.close)
        self.assertIsNone(sb.now)
        with self.assertRaises(AssertionError):
            sb.advance(1)

    def test_the_cli_sees_the_sandbox_instant(self):
        sb = gs.Sandbox()
        self.addCleanup(sb.close)
        code, out, _ = sb.run(["report", "time"], env_set={"PLANE_OFFLINE": "1"})
        self.assertEqual(code, 0)
        self.assertIn(datetime.fromisoformat(gs.FROZEN_NOW).strftime("%d/%m/%Y"), out)


class NoRealClockInTheHarness(unittest.TestCase):
    """Las pruebas golden no deben leer la hora real: el reloj lo controla el Sandbox."""

    def read(self, name):
        with open(os.path.join(HERE, name), encoding="utf-8") as handle:
            return handle.read()

    def test_fixture_and_scenario_dates_are_before_the_frozen_instant(self):
        frozen_day = gs.FROZEN_NOW[:10]
        for name in ("golden_support.py", "test_golden.py"):
            for date in sorted(set(re.findall(r"\b(20\d\d-\d\d-\d\d)\b", self.read(name)))):
                if date != "2026-11-02":  # el propio valor por defecto del instante congelado
                    self.assertLess(date, frozen_day, f"{name}: la fecha {date} no es anterior al instante congelado {frozen_day}")

    def test_golden_files_do_not_use_date_placeholders(self):
        for name in sorted(os.listdir(gs.GOLDEN_DIR)):
            with open(os.path.join(gs.GOLDEN_DIR, name), encoding="utf-8") as handle:
                text = handle.read()
            for marker in ("<HOY>", "<TS>", "<HH:MM>"):
                self.assertNotIn(marker, text, f"{name}: el golden enmascara la hora con {marker}; el reloj congelado la hace determinista")

    def test_the_harness_reads_the_real_clock_only_as_the_documented_fallback(self):
        self.assertEqual(len(re.findall(r"datetime\.now\(|date\.today\(", self.read("golden_support.py"))), 0)
        self.assertEqual(len(re.findall(r"datetime\.now\(|date\.today\(|time\.time\(", self.read("test_golden.py"))), 0)
        self.assertEqual(len(re.findall(r"\btime\.time\(", self.read("golden_support.py"))), 1, "solo write_circuit con clock=None puede leer time.time()")


if __name__ == "__main__":
    unittest.main()
