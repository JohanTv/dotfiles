#!/usr/bin/env python3
"""Lanzador de pruebas: ejecuta el CLI real acortando el timeout de lectura de cada petición a 1 s.

`REQUEST_TIMEOUT` (15 s) es un valor por defecto fijado al definir `api_request`, así que no se puede parchear desde fuera
del proceso ni sin ampliar el contrato de variables de entorno. Este lanzador envuelve `api._send` (el único punto que
abre el socket) y llama al mismo `main()` que `scripts/plane.py`, de modo que el socket, la clasificación `read_timeout`
y la cola se ejercitan igual. Solo lo usan las pruebas que simulan una conexión retenida."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from plane_cli import api  # noqa: E402
from plane_cli.cli import main  # noqa: E402

_real_send = api._send
api._send = lambda url, method, payload, headers, timeout, attempt: _real_send(url, method, payload, headers, min(timeout, 1), attempt)

if __name__ == "__main__":
    sys.argv[0] = "plane.py"
    main()
