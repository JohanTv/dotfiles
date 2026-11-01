"""El reloj central (`plane_cli.clock`): una sola primitiva de la que se derivan las demás, equivalencia con la biblioteca estándar,
zona horaria local, compatibilidad con el lanzador que congela la hora y uso por atributo (para poder sustituirlo en las pruebas)."""
import ast
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import clock_support  # noqa: E402
import golden_support as gs  # noqa: E402
from plane_cli import clock  # noqa: E402

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
PACKAGE = os.path.join(SCRIPTS, "plane_cli")


class Derivation(unittest.TestCase):
    def test_everything_derives_from_timestamp(self):
        controlled = clock_support.Clock(1_800_000_000.0)  # 2027-01-15 08:00:00 UTC
        with controlled.patch():
            self.assertEqual(clock.timestamp(), 1_800_000_000.0)
            self.assertEqual(clock.now(), datetime(2027, 1, 15, 8, 0, 0, tzinfo=timezone.utc))
            self.assertEqual(clock.local_now(), datetime.fromtimestamp(1_800_000_000.0))
            self.assertEqual(clock.local_today(), datetime.fromtimestamp(1_800_000_000.0).date())
            controlled.advance(90)
            self.assertEqual(clock.now(), datetime(2027, 1, 15, 8, 1, 30, tzinfo=timezone.utc))

    def test_now_is_aware_utc_and_local_now_is_naive(self):
        self.assertEqual(clock.now().utcoffset(), timedelta(0))
        self.assertIsNone(clock.local_now().tzinfo)

    def test_local_time_follows_the_process_time_zone(self):
        saved = os.environ.get("TZ")
        self.addCleanup(lambda: (os.environ.pop("TZ", None) if saved is None else os.environ.__setitem__("TZ", saved), time.tzset()))
        os.environ["TZ"] = "America/Lima"  # UTC-5 sin horario de verano
        time.tzset()
        with clock_support.Clock(1_800_000_000.0).patch():
            self.assertEqual(clock.local_now(), datetime(2027, 1, 15, 3, 0, 0))
            self.assertEqual(clock.now().hour, 8)

    def test_it_matches_the_standard_library_at_real_time(self):
        self.assertLess(abs(clock.timestamp() - time.time()), 1)
        self.assertLess(abs(clock.now() - datetime.now(timezone.utc)), timedelta(seconds=1))
        self.assertLess(abs(clock.local_now() - datetime.now()), timedelta(seconds=1))


class FrozenByTheLauncher(unittest.TestCase):
    def test_the_launcher_freezes_the_central_clock_without_touching_it(self):
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as handle:
            handle.write(textwrap.dedent(f"""
                import sys
                sys.path.insert(0, {SCRIPTS!r})
                from plane_cli import clock
                print(clock.timestamp(), clock.now().isoformat(), clock.local_now().isoformat(), clock.local_today())
            """))
        self.addCleanup(os.unlink, handle.name)
        with tempfile.TemporaryDirectory() as home:
            env = {"PATH": os.environ.get("PATH", ""), "HOME": home, "TZ": "UTC", "LC_ALL": "C.UTF-8"}
            proc = subprocess.run([sys.executable, gs.CLOCK_PY, "2028-02-29T00:05:00+00:00", handle.name], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "1835395500.0 2028-02-29T00:05:00+00:00 2028-02-29T00:05:00 2028-02-29")


class Usage(unittest.TestCase):
    def test_the_clock_module_depends_only_on_the_standard_library(self):
        with open(os.path.join(PACKAGE, "clock.py"), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        modules = {n.module for n in tree.body if isinstance(n, ast.ImportFrom)} | {a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names}
        self.assertEqual(modules, {"time", "datetime"})

    def test_modules_use_the_clock_by_attribute_so_tests_can_replace_it(self):
        for name in sorted(os.listdir(PACKAGE)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(PACKAGE, name), encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "plane_cli.clock":
                    self.fail(f"{name}: usa `from plane_cli import clock` y llama a clock.now(); importar las funciones por nombre impediría sustituirlas")


if __name__ == "__main__":
    unittest.main()
