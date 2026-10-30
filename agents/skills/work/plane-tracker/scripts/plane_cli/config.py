"""Entorno compartido: directorio de caché y sus rutas, reloj, medianoche local y variables de entorno.

Expone: CACHE_DIR, db_file(), request_log(), proposal_file(), now(), local_midnight_utc(), positive_int(),
add_json_flag(), load_zshrc_local_if_needed(), get_env_or_fail().
No hace: acceso a red ni a SQLite. Las rutas y el reloj se leen en cada llamada (por atributo del módulo) para que
los tests puedan sustituirlos.
"""
import argparse
import os
import sys
from datetime import datetime, timezone

CACHE_DIR = os.path.expanduser("~/.cache/plane")


def db_file():
    return os.path.join(CACHE_DIR, "worklogs.db")


def request_log():
    return os.path.join(CACHE_DIR, "requests.log")


def proposal_file():
    return os.path.join(CACHE_DIR, "last_proposal.json")


def now():
    """Instante actual en UTC."""
    return datetime.now(timezone.utc)


def local_midnight_utc(moment_utc):
    local = moment_utc.astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def positive_int(value):
    """Tipo argparse: entero >= 1."""
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("debe ser un entero >= 1")
    return n


def add_json_flag(parser, hidden=False, help="Salida en JSON"):
    """Añade `--json` sin valor por defecto: así el flag vale en cualquier nivel del parser y el último no lo pisa.

    Los handlers lo leen con getattr(args, "json", False).
    """
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS if hidden else help)


def load_zshrc_local_if_needed():
    """Carga variables desde ~/.zshrc.local si no están en el entorno."""
    local_env = os.path.expanduser("~/.zshrc.local")
    if os.path.isfile(local_env):
        try:
            with open(local_env, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("export "):
                        line = line[7:].strip()
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k not in os.environ and v:
                                os.environ[k] = v
        except Exception:
            pass


def get_env_or_fail(var_name, description):
    load_zshrc_local_if_needed()
    val = os.environ.get(var_name)
    if not val:
        sys.stderr.write(f"Error: Variable de entorno '{var_name}' ({description}) no configurada.\n")
        sys.stderr.write("Defínela en ~/.zshrc.local o en tu entorno antes de ejecutar este script.\n")
        sys.exit(1)
    return val
