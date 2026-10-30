"""Cliente HTTP de la API de Plane: clasificación de fallos, reintentos acotados, circuito y registro de latencia.

Expone: api_request(), probe_plane(), classify(), log_request(), http_detail(), fail_http(), PlaneUnavailable.
No hace: interpretar los datos de la API ni tocar SQLite.
Un fallo transitorio (502/503/504, timeouts, conexión rechazada o cortada, DNS, fallo de handshake TLS, respuesta ilegible)
lanza PlaneUnavailable y cuenta para el circuito; los errores definitivos (4xx, 500, certificado TLS no verificable) se
imprimen y terminan con código 1 sin contar para el circuito, o se relanzan como HTTPError con raise_on_error. Solo los GET se reintentan ante un fallo transitorio, y los timeouts nunca; el 429 se
reintenta con cualquier método porque la petición no se procesó. PLANE_OFFLINE=1 impide cualquier acceso a la red.
"""

import http.client
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from plane_cli import circuit, config
from plane_cli.circuit import PlaneUnavailable


REQUEST_LOG_MAX_BYTES = 1_000_000
REQUEST_TIMEOUT = 15
PROBE_TIMEOUT = 5
RETRY_PAUSE = 0.5
RETRY_MAX_ELAPSED = 5
RATE_LIMIT_MAX_WAIT = 30
TRANSIENT_HTTP = (502, 503, 504)
TIMEOUT_KINDS = ("timeout", "read_timeout")


def log_request(method, url, status, elapsed_ms, attempt, error=None):
    """JSONL con metadatos de cada llamada (sin cuerpos ni cabeceras) para diagnosticar latencia y caídas."""
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        log_path = config.request_log()
        if os.path.exists(log_path) and os.path.getsize(log_path) > REQUEST_LOG_MAX_BYTES:
            os.replace(log_path, log_path + ".1")
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "method": method,
                  "path": urllib.parse.urlparse(url).path, "status": status, "ms": int(elapsed_ms),
                  "attempt": attempt, "error": error}
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _classify_tls(exc, handshake):
    """Clasificación de un ssl.SSLError; handshake=True si ocurrió al conectar (antes de enviar la petición)."""
    if isinstance(exc, ssl.SSLCertVerificationError):
        return None
    if isinstance(exc, (ssl.SSLEOFError, ssl.SSLZeroReturnError)):
        return "reset", "unknown"
    return ("tls", "no") if handshake else ("tls", "unknown")


def classify(exc):
    """(kind, delivered) de un fallo transitorio; None si el error es definitivo (4xx, 500).

    delivered="no": la petición no llegó a enviarse (conexión rechazada, DNS, timeout de conexión).
    delivered="unknown": pudo llegar al servidor (timeout de lectura, conexión cortada, 502/503/504, respuesta ilegible).
    TLS: un fallo de handshake (SSLError envuelto en URLError) es ("tls", "no"); un EOF o cierre TLS es ("reset", "unknown");
    un certificado no verificable es un error de configuración (None).
    """
    if isinstance(exc, urllib.error.HTTPError):
        return (f"http_{exc.code}", "unknown") if exc.code in TRANSIENT_HTTP else None
    if isinstance(exc, ssl.SSLError):
        return _classify_tls(exc, handshake=False)
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, ssl.SSLError):
            return _classify_tls(reason, handshake=True)
        if isinstance(reason, socket.gaierror):
            return "dns", "no"
        if isinstance(reason, TimeoutError):
            return "timeout", "no"
        if isinstance(reason, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            return "reset", "unknown"
        return "refused", "no"
    if isinstance(exc, TimeoutError):
        return "read_timeout", "unknown"
    if isinstance(exc, ValueError):
        return "bad_response", "unknown"
    if isinstance(exc, (ConnectionError, http.client.IncompleteRead)):
        return "reset", "unknown"
    if isinstance(exc, http.client.HTTPException):
        return "bad_response", "unknown"
    return "reset", "unknown"


def _send(url, method, payload, headers, timeout, attempt):
    """Una petición. Devuelve el JSON; lanza HTTPError (cualquier código) o _Transient (fallo de red/respuesta)."""
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    started = time.monotonic()
    elapsed = lambda: (time.monotonic() - started) * 1000
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = b"" if status == 204 else resp.read()
    except urllib.error.HTTPError as exc:
        log_request(method, url, exc.code, elapsed(), attempt)
        exc.elapsed = elapsed() / 1000
        raise
    except (OSError, http.client.HTTPException) as exc:
        found = classify(exc)
        reason = str(getattr(exc, "reason", exc))[:80]
        log_request(method, url, None, elapsed(), attempt, error=f"{type(exc).__name__}: {reason}")
        if found is None:
            raise _Definitive(str(getattr(exc, "reason", exc))) from exc
        raise _Transient(*found, elapsed() / 1000) from exc
    try:
        result = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError as exc:
        log_request(method, url, None, elapsed(), attempt, error=f"{type(exc).__name__}: respuesta no válida")
        raise _Transient("bad_response", "unknown", elapsed() / 1000) from exc
    log_request(method, url, status, elapsed(), attempt)
    return result


class _Definitive(Exception):
    """Fallo de red que no es de disponibilidad (certificado TLS no verificable): error de configuración."""


class _Transient(Exception):
    def __init__(self, kind, delivered, elapsed):
        super().__init__(kind)
        self.kind, self.delivered, self.elapsed = kind, delivered, elapsed


def _probe_runner(url, api_key):
    """Sonda GET /users/me/ (timeout corto, sin reintentos): (ok, kind). Cualquier respuesta del servidor cuenta como viva."""
    probe_url = url.split("/api/v1/")[0] + "/api/v1/users/me/"

    def run():
        try:
            _send(probe_url, "GET", None, {"x-api-key": api_key}, PROBE_TIMEOUT, 1)
        except urllib.error.HTTPError as exc:
            found = classify(exc)
            exc.close()
            return (False, found[0]) if found else (True, None)
        except _Transient as exc:
            return False, exc.kind
        except _Definitive:
            return False, "tls"
        return True, None
    return run


def probe_plane(base_url, api_key, force=False):
    """Sondeo explícito del circuito (ver circuit.probe): True/False, o None si no tocaba sondear. PLANE_OFFLINE=1: siempre False, sin red."""
    if os.environ.get("PLANE_OFFLINE") == "1":
        return False
    return circuit.probe(_probe_runner(base_url.rstrip("/") + "/api/v1/", api_key), force=force)


def http_detail(exc):
    """Cuerpo de un HTTPError como texto (vacío si no se puede leer)."""
    try:
        return exc.read().decode("utf-8")
    except (OSError, http.client.HTTPException, ValueError):
        return ""


def fail_http(url, status, detail):
    """Imprime un error HTTP definitivo y termina con código 1."""
    sys.stderr.write(f"Error HTTP {status} en {url}: {detail}\n")
    sys.exit(1)


def _rate_limit_wait(exc):
    try:
        wait = float(exc.headers.get("Retry-After", 1))
    except (TypeError, ValueError):
        wait = 1.0
    return min(wait + 0.5, RATE_LIMIT_MAX_WAIT)


def api_request(url, api_key, method="GET", data=None, timeout=REQUEST_TIMEOUT, max_retries=3, raise_on_error=False):
    """Ejecuta una petición a la API de Plane. Lanza PlaneUnavailable (con el método de la petición) ante fallos transitorios."""
    try:
        return _perform(url, api_key, method, data, timeout, max_retries, raise_on_error)
    except PlaneUnavailable as exc:
        exc.method = method
        raise


def _perform(url, api_key, method, data, timeout, max_retries, raise_on_error):
    if os.environ.get("PLANE_OFFLINE") == "1":
        raise PlaneUnavailable("offline", "no")
    circuit.gate(_probe_runner(url, api_key))
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    attempt = rate_limited = 0
    retried = False
    while True:
        attempt += 1
        try:
            result = _send(url, method, payload, headers, timeout, attempt)
        except urllib.error.HTTPError as exc:
            found = classify(exc)
            if found:
                exc.close()
                transient = _Transient(*found, exc.elapsed)
            else:
                if exc.code == 429 and rate_limited < max_retries - 1:
                    rate_limited += 1
                    exc.close()
                    time.sleep(_rate_limit_wait(exc))
                    continue
                circuit.record(True)
                if raise_on_error:
                    raise
                detail = http_detail(exc)
                exc.close()
                fail_http(url, exc.code, detail)
        except _Transient as exc:
            transient = exc
        except _Definitive as exc:
            sys.stderr.write(f"Error TLS en {url}: {exc}\n")
            sys.exit(1)
        else:
            circuit.record(True)
            return result
        if method == "GET" and not retried and transient.kind not in TIMEOUT_KINDS and transient.elapsed < RETRY_MAX_ELAPSED:
            retried = True
            time.sleep(RETRY_PAUSE)
            continue
        state = circuit.record(False, transient.kind)
        raise PlaneUnavailable(transient.kind, transient.delivered, since=circuit.hhmm(state["since"]))
