#!/usr/bin/env python3
"""Lanzador de pruebas: congela la hora real y ejecuta otro script (plane.py, o plane_fast.py) en el mismo proceso.

Uso: plane_clock.py <ISO-8601 con zona, p. ej. 2026-11-02T12:00:00+00:00> <script> [args...]

Sustituye `datetime.datetime` por una subclase cuyo `now()`, `utcnow()` y `today()` devuelven el instante fijado, y `time.time`,
ANTES de que el script importe `plane_cli`: así `from datetime import datetime` y `import time` ya ven el reloj fijo y la
producción no necesita ninguna bandera ni variable de entorno (un reloj configurable por entorno permitiría falsificar las
marcas de tiempo del worklog). No toca `time.monotonic` ni `time.sleep`: los timeouts de socket, `hang` y `delay` siguen en
tiempo real. El reloj está congelado, no avanza: una prueba que necesite que pase el tiempo lo hace explícito (`Sandbox.advance`).
"""
import datetime as _dt
import runpy
import sys
import time


def freeze(instant):
    """Fija la hora real en `instant` (datetime con zona) para el resto del proceso."""
    stamp = instant.timestamp()
    real = _dt.datetime

    class FrozenDatetime(real):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(stamp, tz)

        @classmethod
        def today(cls):
            return cls.fromtimestamp(stamp)

        @classmethod
        def utcnow(cls):
            return cls.fromtimestamp(stamp, _dt.timezone.utc).replace(tzinfo=None)

    _dt.datetime = FrozenDatetime
    time.time = lambda: stamp
    return stamp


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("uso: plane_clock.py <ISO-8601> <script> [args...]\n")
        return 2
    instant = _dt.datetime.fromisoformat(argv[0])
    if instant.tzinfo is None:
        sys.stderr.write("plane_clock.py: el instante debe llevar zona horaria (por ejemplo +00:00)\n")
        return 2
    freeze(instant)
    target = argv[1]
    sys.argv = [target, *argv[2:]]
    runpy.run_path(target, run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
