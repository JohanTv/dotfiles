#!/usr/bin/env python3
"""plane.py - CLI de Plane CE para agentes de IA y reportes de actividad.

Punto de entrada: el código vive en el paquete plane_cli/ (ver ARCHITECTURE.md). Conserva su nombre y su ruta porque
el wrapper `plane-tracker` y SKILL.md apuntan a este archivo.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from plane_cli.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
