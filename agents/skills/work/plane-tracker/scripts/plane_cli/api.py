"""Cliente HTTP de la API de Plane con reintento ante 429 y registro de latencia.

Expone: api_request(), log_request().
No hace: interpretar los datos de la API ni tocar SQLite.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from plane_cli import config


REQUEST_LOG_MAX_BYTES = 1_000_000


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


def api_request(url, api_key, method="GET", data=None, timeout=10, max_retries=3, raise_on_error=False):
    """Ejecuta peticiones HTTP a la API de Plane con tolerancia a 429 (Rate Limit) y registro de latencia."""
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                log_request(method, url, resp.status, (time.monotonic() - started) * 1000, attempt + 1)
                if resp.status == 204:
                    return {}
                content = resp.read().decode("utf-8")
                return json.loads(content) if content else {}
        except urllib.error.HTTPError as e:
            log_request(method, url, e.code, (time.monotonic() - started) * 1000, attempt + 1)
            if e.code == 429 and attempt < max_retries - 1:
                retry_after = int(e.headers.get("Retry-After", 1))
                time.sleep(retry_after + 0.5)
                continue
            if raise_on_error:
                raise e
            err_msg = e.read().decode("utf-8")
            sys.stderr.write(f"Error HTTP {e.code} en {url}: {err_msg}\n")
            sys.exit(1)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            reason = str(getattr(e, "reason", e))[:80]
            log_request(method, url, None, (time.monotonic() - started) * 1000, attempt + 1, error=f"{type(e).__name__}: {reason}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            if raise_on_error:
                raise e
            sys.stderr.write(f"Error de red/conexión con Plane ({url}): {e}\n")
            sys.exit(1)
