"""Reloj controlado para las pruebas en proceso: sustituye `clock.timestamp`, del que se derivan `now`, `local_now` y `local_today`,
así que fijar esa única función deja coherentes las tres lecturas. Para las pruebas que ejecutan el CLI como subproceso, el reloj
se congela con `plane_clock.py` (ver golden_support.Sandbox)."""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from plane_cli import clock  # noqa: E402

DEFAULT_START = 1_800_000_000.0  # 2027-01-15 08:00 UTC: posterior a cualquier fecha de los fixtures


class Clock:
    """Reloj que solo avanza cuando la prueba lo dice: `c.advance(30)`; `c.patch()` devuelve un parche de `clock.timestamp`."""

    def __init__(self, start=DEFAULT_START):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds

    def patch(self):
        return mock.patch.object(clock, "timestamp", self)
