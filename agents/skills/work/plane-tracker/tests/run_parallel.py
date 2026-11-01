#!/usr/bin/env python3
"""Ejecuta la suite en paralelo: un proceso por trabajo, cada uno con su propio HOME/TMPDIR temporal y sin variables PLANE_*.

Los módulos pesados (golden, outbox...) se reparten por método para que el tiempo total tienda a la prueba más lenta; los
ligeros van por módulo. Los trabajos corren con prioridad baja (--nice) para no restar fluidez al resto de la máquina.

Uso: python3 tests/run_parallel.py [-j N] [--nice N] [--freeze ISO] [texto ...]   (los textos filtran módulos por nombre)
--freeze ISO congela además la hora real del propio proceso de pruebas (con plane_clock.py): ninguna prueba debe depender de la fecha real,
así que toda la suite debe pasar con cualquier instante; sirve para comprobarlo.
Salida: 0 si todo pasa, 1 si algún trabajo falla. No regenera los golden: para eso, GOLDEN_UPDATE=1 con unittest normal."""
import argparse
import compileall
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
HEAVY = ("test_golden", "test_outbox", "test_outbox_flush", "test_outbox_sync", "test_transport", "test_offline_reads", "test_degrade")
JOB_TIMEOUT = 300


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item.id()


def build_jobs(filters):
    modules = sorted(n[:-3] for n in os.listdir(HERE) if n.startswith("test_") and n.endswith(".py"))
    modules = [m for m in modules if not filters or any(f in m for f in filters)]
    sys.path.insert(0, HERE)
    jobs = []
    for module in sorted(modules, key=lambda m: m not in HEAVY):
        if module in HEAVY:
            jobs += [[test_id] for test_id in flatten(unittest.defaultTestLoader.loadTestsFromName(module))]
        else:
            jobs.append([module])
    return jobs


def run_job(args, freeze=None):
    home = tempfile.mkdtemp(prefix="plane-par-")
    # Se descartan las variables PLANE_* (credenciales, instancia) salvo PLANE_TEST_NOW, que solo lee el harness de pruebas para fijar el reloj
    env = {k: v for k, v in os.environ.items() if not k.startswith("PLANE_") or k == "PLANE_TEST_NOW"}
    env.update(HOME=home, TMPDIR=home)
    started = time.monotonic()
    try:
        command = [sys.executable, "-m", "unittest", *args]
        if freeze:
            command = [sys.executable, os.path.join(HERE, "plane_clock.py"), freeze, "-m", "unittest", *args]
        proc = subprocess.run(command, cwd=HERE, env=env, capture_output=True, text=True, timeout=JOB_TIMEOUT)
        code, output = proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        code, output = 124, f"TIMEOUT: más de {JOB_TIMEOUT} s"
    finally:
        shutil.rmtree(home, ignore_errors=True)
    return args[0], code, output, time.monotonic() - started


def main(argv):
    parser = argparse.ArgumentParser(description="Ejecuta la suite de plane-tracker en paralelo")
    parser.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 4, help="procesos simultáneos (por defecto, los hilos de la CPU)")
    parser.add_argument("--nice", type=int, default=10, help="aumento de 'nice' de los trabajos; 0 lo desactiva (por defecto 10)")
    parser.add_argument("--freeze", metavar="ISO", help="congela la hora real del proceso de pruebas en este instante (ISO-8601 con zona)")
    parser.add_argument("filtro", nargs="*", help="solo módulos cuyo nombre contenga alguno de estos textos")
    opts = parser.parse_args(argv)
    if opts.nice > 0 and hasattr(os, "nice"):
        os.nice(opts.nice)
    compileall.compile_dir(SCRIPTS, quiet=2)  # sin bytecode previo cada subproceso del CLI recompila todo (0,6 s frente a 0,13 s)
    jobs = build_jobs(opts.filtro)
    if not jobs:
        sys.stderr.write("Ningún módulo coincide con el filtro.\n")
        return 1
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, opts.jobs)) as pool:
        results = list(pool.map(lambda job: run_job(job, opts.freeze), jobs))
    wall = time.monotonic() - started
    failed = [r for r in results if r[1] != 0]
    for name, code, output, _secs in failed:
        print(f"\n{'=' * 70}\nFALLO ({code}): {name}\n{'=' * 70}\n{output.rstrip()}")
    tests = sum(int(m.group(1)) for _n, _c, out, _s in results for m in [re.search(r"^Ran (\d+) tests?", out, re.M)] if m)
    busy = sum(r[3] for r in results)
    print(f"\n{tests} pruebas en {len(results)} trabajos, {len(failed)} con fallos; {wall:.1f} s (suma de trabajos: {busy:.0f} s, -j {opts.jobs}, nice +{max(opts.nice, 0)})")
    print("Más lentos: " + ", ".join(f"{n.split('.')[-1] if '.' in n else n} {s:.1f}s" for n, _c, _o, s in sorted(results, key=lambda r: -r[3])[:3]))
    return 1 if failed or not tests else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
