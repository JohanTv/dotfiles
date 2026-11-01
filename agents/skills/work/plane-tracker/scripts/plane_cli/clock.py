"""Reloj central del CLI: la única fuente de la hora real.

Expone: timestamp(), now(), local_now(), local_today().
No hace: lectura de variables de entorno ni modo de pruebas (un reloj configurable permitiría falsificar las marcas de tiempo del
worklog), ni tiempos transcurridos (`time.monotonic`) ni esperas (`time.sleep`): no son "la hora".

Todo el código que necesite saber qué hora es llama a este módulo por atributo (`clock.now()`, nunca `from plane_cli.clock import
now`), para que una prueba en proceso pueda sustituir un punto con `mock.patch.object(clock, "timestamp", ...)`. `now()`,
`local_now()` y `local_today()` se derivan de `timestamp()`, de modo que sustituir esa sola función fija las tres lecturas y las
mantiene coherentes entre sí. Las pruebas golden congelan la hora desde fuera del proceso (tests/plane_clock.py), sin tocar este módulo.
`tests/test_structure.py` impide leer la hora real en cualquier otro archivo.
"""
import time
from datetime import datetime, timezone


def timestamp():
    """Segundos desde la época (equivale a time.time())."""
    return time.time()


def now():
    """Instante actual con zona UTC (equivale a datetime.now(timezone.utc))."""
    return datetime.fromtimestamp(timestamp(), timezone.utc)


def local_now():
    """Hora local actual sin zona (equivale a datetime.now()); para las fechas y horas que ve y registra la persona."""
    return datetime.fromtimestamp(timestamp())


def local_today():
    """Fecha local de hoy (equivale a datetime.now().date())."""
    return local_now().date()
