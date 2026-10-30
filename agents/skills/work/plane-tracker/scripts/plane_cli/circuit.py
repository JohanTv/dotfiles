"""Circuito de fallo rápido hacia Plane: estado compartido entre procesos y excepción tipada.

Expone: PlaneUnavailable, cause_text(), hhmm(), gate(), probe(), record(), describe(), last_failure(), retry_in(), format_unavailable().
No hace: peticiones HTTP (la sonda la ejecuta quien llama, que pasa un callable `run_probe() -> (ok, kind)`).
El estado vive en `<CACHE_DIR>/circuit.json`, protegido con flock y reemplazo atómico. El circuito se abre tras
TRIP_AFTER llamadas fallidas consecutivas dentro de WINDOW segundos; abierto, las llamadas fallan sin tocar la red hasta
que el enfriamiento (COOLDOWNS, un nivel más por cada sonda fallida) vence. Entonces un solo proceso toma el lease y
sondea; si la sonda responde, el circuito se cierra. Cualquier respuesta del servidor resetea el contador.
"""

import contextlib
import fcntl
import json
import math
import os
import urllib.error
from datetime import datetime

from plane_cli import config

TRIP_AFTER = 2
WINDOW = 120
COOLDOWNS = (30, 60, 120, 300)
PROBE_LEASE = 10
FRESH_OK = 60

CAUSES = {
    "timeout": "tiempo de espera agotado", "read_timeout": "tiempo de espera agotado", "refused": "conexión rechazada",
    "dns": "DNS no resuelve", "http_502": "HTTP 502", "http_503": "HTTP 503", "http_504": "HTTP 504",
    "reset": "conexión cortada", "tls": "error TLS", "bad_response": "respuesta no válida", "offline": "modo sin conexión (PLANE_OFFLINE=1)", "no_cache": "sin caché local", "http_429": "límite de ritmo (HTTP 429)",
}


def cause_text(kind):
    return CAUSES.get(kind, kind or "causa desconocida")


class PlaneUnavailable(urllib.error.URLError):
    """Plane no se pudo alcanzar. `delivered` es "no" si la petición no llegó a enviarse y "unknown" si pudo procesarse.
    `method` es el método HTTP de la petición fallida (lo rellena api_request).

    Hereda de URLError para que los sitios que ya capturan fallos de red la traten igual.
    """

    def __init__(self, kind, delivered, since=None, cause_kind=None, message=None, method=None):
        super().__init__(kind)
        self.method = method
        self.kind = kind
        self.delivered = delivered
        self.since = since
        self.cause_kind = cause_kind
        self.message = message

    @property
    def cause(self):
        return cause_text(self.cause_kind if self.kind == "circuit_open" else self.kind)

    def __str__(self):
        return self.cause


def _now():
    return config.now().timestamp()


def hhmm(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M") if ts else None


def _blank():
    return {"consec": 0, "opened_at": None, "level": 0, "probing_until": 0, "last_error": None, "since": None, "last_ok": None, "skipped": 0}


def _path():
    return os.path.join(config.CACHE_DIR, "circuit.json")


def _read():
    try:
        with open(_path(), "r", encoding="utf-8") as handle:
            return {**_blank(), **json.load(handle)}
    except (OSError, ValueError, TypeError):
        return _blank()


@contextlib.contextmanager
def _locked():
    """Estado bajo flock; se persiste al salir si cambió. Sin caché escribible el circuito simplemente no actúa."""
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        fd = os.open(_path() + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
    except OSError:
        yield _blank()
        return
    try:
        state = _read()
        before = dict(state)
        try:
            yield state
        finally:
            if state != before:
                tmp = _path() + ".tmp"
                with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as handle:
                    json.dump(state, handle)
                os.replace(tmp, _path())
    finally:
        os.close(fd)


def _cooldown(state):
    return COOLDOWNS[min(state["level"], len(COOLDOWNS) - 1)]


def _unavailable(state, kind="circuit_open"):
    return PlaneUnavailable(kind, "no", since=hhmm(state["since"]), cause_kind=state["last_error"])


def _is_clean(state, now):
    return not state["consec"] and state["opened_at"] is None and bool(state["last_ok"]) and now - state["last_ok"] <= FRESH_OK


def record(ok, error=None, probe=False):
    """Registra el resultado de una llamada; devuelve una copia del estado resultante.

    ok=True resetea todo. Un fallo suma al contador (se abre al llegar a TRIP_AFTER); una sonda fallida con el circuito
    abierto sube un nivel de enfriamiento.
    """
    now = _now()
    if ok:
        if _is_clean(_read(), now):
            return _read()
        with _locked() as state:
            if not _is_clean(state, now):
                state.update(_blank(), last_ok=now)
            return dict(state)
    with _locked() as state:
        state["last_error"] = error
        if state["opened_at"] is not None:
            if probe:
                state.update(level=min(state["level"] + 1, len(COOLDOWNS) - 1), opened_at=now, probing_until=0)
            return dict(state)
        if state["consec"] and state["since"] and now - state["since"] <= WINDOW:
            state["consec"] += 1
        else:
            state.update(consec=1, since=now)
        if state["consec"] >= TRIP_AFTER:
            state.update(opened_at=now, level=0, probing_until=0)
        return dict(state)


def _run(run_probe):
    ok, kind = run_probe()
    state = record(ok, kind, probe=True)
    return ok, kind, state


def gate(run_probe):
    """Se llama antes de cada petición. Abierto y en enfriamiento (o con la sonda en manos de otro proceso): falla sin red."""
    now = _now()
    with _locked() as state:
        if state["opened_at"] is None:
            return
        if now < state["opened_at"] + _cooldown(state) or now < state["probing_until"]:
            state["skipped"] += 1
            raise _unavailable(state)
        state["probing_until"] = now + PROBE_LEASE
    ok, kind, after = _run(run_probe)
    if not ok:
        raise PlaneUnavailable(kind, "no", since=hhmm(after["since"]), cause_kind=kind)


def probe(run_probe, force=False):
    """Sondeo explícito. True si Plane respondió, False si no, None si no tocaba sondear (cerrado o en enfriamiento).

    Con force=True sondea siempre, también con el circuito cerrado o en enfriamiento.
    """
    now = _now()
    if not force:
        with _locked() as state:
            if state["opened_at"] is None or now < state["opened_at"] + _cooldown(state) or now < state["probing_until"]:
                return None
            state["probing_until"] = now + PROBE_LEASE
    return _run(run_probe)[0]


def retry_in():
    """Segundos hasta la próxima sonda (el primer escalón si el circuito sigue cerrado)."""
    state = _read()
    if state["opened_at"] is None:
        return COOLDOWNS[0]
    return max(1, math.ceil(state["opened_at"] + _cooldown(state) - _now()))


def last_failure():
    """(clase del último fallo, hora HH:MM de su inicio); (None, None) si no hay fallos registrados."""
    state = _read()
    return state["last_error"], hhmm(state["since"])


def describe():
    """Estado legible: {"state", "consec", "since", "cause", "next_probe_in", "level", "skipped", "last_ok"}."""
    state = _read()
    is_open = state["opened_at"] is not None
    return {"state": "open" if is_open else "closed", "consec": state["consec"], "level": state["level"], "skipped": state["skipped"],
            "since": hhmm(state["since"]) if is_open else None, "cause": cause_text(state["last_error"]) if is_open else None,
            "next_probe_in": retry_in() if is_open else None, "last_ok": hhmm(state["last_ok"])}


def format_unavailable(exc):
    """Mensaje de stderr para un PlaneUnavailable sin capturar."""
    if exc.message:
        return exc.message + "\n"
    if exc.kind == "offline":
        return "Modo sin conexión (PLANE_OFFLINE=1). No se envió nada.\n"
    since = exc.since or hhmm(_now())
    if exc.delivered == "unknown" and exc.method != "GET":
        return (f"Plane no responde desde las {since} ({exc.cause}). "
                "Puede que Plane haya recibido la solicitud; comprueba el estado antes de reintentar.\n")
    return f"Plane no responde desde las {since} ({exc.cause}). No se envió nada; reintenta en {retry_in()} s.\n"
