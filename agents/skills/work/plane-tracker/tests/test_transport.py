"""Transporte: clasificación de fallos, reintentos, timeouts, PLANE_OFFLINE y circuito de punta a punta (servidor falso con fallos)."""
import http.client
import io
import os
import socket
import sys
import tempfile
import time
import types
import unittest
import urllib.error
from contextlib import redirect_stderr
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402
from plane_cli import api, circuit, config  # noqa: E402

PROJECTS = "/api/v1/workspaces/ws/projects/"


class Classify(unittest.TestCase):
    def test_taxonomy(self):
        cases = [
            (urllib.error.HTTPError("u", 502, "x", {}, None), ("http_502", "unknown")),
            (urllib.error.HTTPError("u", 504, "x", {}, None), ("http_504", "unknown")),
            (urllib.error.HTTPError("u", 500, "x", {}, None), None),
            (urllib.error.HTTPError("u", 429, "x", {}, None), None),
            (urllib.error.HTTPError("u", 400, "x", {}, None), None),
            (urllib.error.URLError(ConnectionRefusedError()), ("refused", "no")),
            (urllib.error.URLError(socket.gaierror()), ("dns", "no")),
            (urllib.error.URLError(TimeoutError("timed out")), ("timeout", "no")),
            (urllib.error.URLError(ConnectionResetError()), ("reset", "unknown")),
            (TimeoutError("timed out"), ("read_timeout", "unknown")),
            (http.client.RemoteDisconnected("x"), ("reset", "unknown")),
            (http.client.IncompleteRead(b"a"), ("reset", "unknown")),
            (http.client.BadStatusLine("x"), ("bad_response", "unknown")),
            (ValueError("json"), ("bad_response", "unknown")),
        ]
        for exc, expected in cases:
            self.assertEqual(api.classify(exc), expected, repr(exc))
            if isinstance(exc, urllib.error.HTTPError):
                exc.close()

    def test_cause_messages(self):
        for kind, text in (("timeout", "tiempo de espera agotado"), ("read_timeout", "tiempo de espera agotado"), ("refused", "conexión rechazada"),
                           ("dns", "DNS no resuelve"), ("http_502", "HTTP 502"), ("reset", "conexión cortada"),
                           ("bad_response", "respuesta no válida"), ("offline", "modo sin conexión (PLANE_OFFLINE=1)")):
            self.assertEqual(circuit.PlaneUnavailable(kind, "no").cause, text)
        self.assertEqual(circuit.PlaneUnavailable("circuit_open", "no", cause_kind="dns").cause, "DNS no resuelve")


class Transport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake = gs.FakePlane()
        self.sleeps = []
        for patcher in (mock.patch.object(config, "CACHE_DIR", self.tmp.name), mock.patch.object(api, "time", types.SimpleNamespace(sleep=self.sleeps.append, monotonic=time.monotonic))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.fake.close)
        self.url = self.fake.base_url + PROJECTS

    def call(self, method="GET", **kwargs):
        return api.api_request(self.url, "k", method=method, data=({"x": 1} if method != "GET" else None), **kwargs)

    def unavailable(self, method="GET", **kwargs):
        with self.assertRaises(circuit.PlaneUnavailable) as ctx:
            self.call(method, **kwargs)
        return ctx.exception

    def hits(self, method=None):
        return [r for r in self.fake.requests if method in (None, r[0])]

    def test_get_502_retries_once(self):
        self.fake.add_fault("GET", "/projects/$", "status", 502)
        exc = self.unavailable()
        self.assertEqual((exc.kind, exc.delivered), ("http_502", "unknown"))
        self.assertEqual(len(self.hits()), 2)
        self.assertEqual(self.sleeps, [api.RETRY_PAUSE])

    def test_get_recovers_on_retry(self):
        self.fake.add_fault("GET", "/projects/$", "status", 503, n=1)
        self.assertIn("results", self.call())
        self.assertEqual(len(self.hits()), 2)

    def test_500_is_definitive_and_not_retried(self):
        self.fake.add_fault("GET", "/projects/$", "status", 500)
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            self.call()
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn(f"Error HTTP 500 en {self.url}: ", err.getvalue())
        self.assertEqual(len(self.hits()), 1)
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.call(raise_on_error=True)
        raised.exception.close()
        self.assertEqual(circuit.describe()["consec"], 0)

    def test_400_on_post_is_definitive(self):
        self.fake.add_fault("POST", "/projects/$", "status", 400)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            self.call("POST")
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(len(self.hits("POST")), 1)

    def test_writes_are_never_retried(self):
        self.fake.add_fault("POST", "/projects/$", "status", 502)
        exc = self.unavailable("POST")
        self.assertEqual((exc.kind, exc.delivered), ("http_502", "unknown"))
        self.assertEqual(len(self.hits("POST")), 1)
        self.assertEqual(self.sleeps, [])

    def test_read_timeout_on_post_is_unknown_and_not_retried(self):
        self.fake.add_fault("POST", "/projects/$", "hang", 2)
        exc = self.unavailable("POST", timeout=0.4)
        self.assertEqual((exc.kind, exc.delivered), ("read_timeout", "unknown"))
        self.assertEqual(len(self.hits("POST")), 1)

    def test_get_timeout_is_not_retried(self):
        self.fake.add_fault("GET", "/projects/$", "hang", 2)
        self.assertEqual(self.unavailable(timeout=0.4).kind, "read_timeout")
        self.assertEqual(len(self.hits()), 1)

    def test_refused_post_was_not_sent(self):
        self.fake.close()
        exc = self.unavailable("POST")
        self.assertEqual((exc.kind, exc.delivered), ("refused", "no"))

    def test_commit_drop_is_unknown(self):
        self.fake.store_comments = True
        self.fake.add_fault("POST", "/comments/$", "commit_drop")
        url = f"{self.fake.base_url}{PROJECTS}{gs.P1}/issues/{gs.P1}/comments/"
        with self.assertRaises(circuit.PlaneUnavailable) as ctx:
            api.api_request(url, "k", method="POST", data={"comment_html": "x"})
        self.assertEqual((ctx.exception.kind, ctx.exception.delivered), ("reset", "unknown"))
        self.assertEqual(len(self.fake.committed), 1)

    def test_broken_responses_never_traceback(self):
        raw = {
            "BadStatusLine": (b"garbage\r\n\r\n", "bad_response"),
            "IncompleteRead": (b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n{\"a\":", "reset"),
            "HTML 200": (b"HTTP/1.1 200 OK\r\nContent-Length: 15\r\n\r\n<html>proxy</h>", "bad_response"),
        }
        for label, (payload, kind) in raw.items():
            with self.subTest(label):
                self.fake.clear_faults()
                circuit.record(True)
                self.fake.add_fault("*", "/projects/$", "raw", payload)
                self.assertEqual(self.unavailable("POST").kind, kind)

    def test_offline_makes_no_request(self):
        with mock.patch.dict(os.environ, {"PLANE_OFFLINE": "1"}):
            exc = self.unavailable()
        self.assertEqual((exc.kind, exc.delivered), ("offline", "no"))
        self.assertEqual(self.hits(), [])

    def test_429_is_retried_for_every_method_and_does_not_count(self):
        self.fake.add_fault("POST", "/projects/$", "status", 429)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.call("POST")
        self.assertEqual(len(self.hits("POST")), 3)
        self.assertEqual(self.sleeps, [1.5, 1.5])
        self.assertEqual(circuit.describe()["consec"], 0)

    def test_circuit_opens_after_two_failed_calls_then_fails_fast(self):
        self.fake.add_fault("GET", "/projects/$", "status", 503)
        self.unavailable()
        self.unavailable()
        before = len(self.hits())
        exc = self.unavailable()
        self.assertEqual(exc.kind, "circuit_open")
        self.assertEqual(len(self.hits()), before)
        self.assertEqual(self.unavailable("POST").kind, "circuit_open")
        self.assertEqual(len(self.hits()), before)

    def test_probe_after_cooldown_is_a_single_request(self):
        self.fake.close()
        self.unavailable()
        self.unavailable()
        self.fake.reopen()
        self.fake.add_fault("*", "/users/me/", "status", 503)
        past = config.now().timestamp() + circuit.COOLDOWNS[0] + 1
        with mock.patch.object(config, "now", lambda: __import__("datetime").datetime.fromtimestamp(past, __import__("datetime").timezone.utc)):
            exc = self.unavailable()
            self.assertEqual(exc.kind, "http_503")
            self.assertEqual(self.hits(), [("GET", "/api/v1/users/me/", "")])
            self.assertEqual(circuit.describe()["level"], 1)
        self.fake.clear_faults()
        past += circuit.COOLDOWNS[1] + 1
        with mock.patch.object(config, "now", lambda: __import__("datetime").datetime.fromtimestamp(past, __import__("datetime").timezone.utc)):
            self.assertIn("results", self.call())
            self.assertEqual([p for _, p, _ in self.hits()], ["/api/v1/users/me/", "/api/v1/users/me/", PROJECTS])
            self.assertEqual(circuit.describe()["state"], "closed")


ISSUE = "10000000-0000-4000-8000-000000000001"
READ = ["attachment", "list", ISSUE]  # no tiene caché de respaldo: el fallo llega tal cual al usuario


class Cli(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)

    def test_open_circuit_fails_fast_without_touching_the_server(self):
        self.sb.write_circuit(opened_ago=5)
        code, out, err = self.sb.run(READ)
        self.assertEqual(code, 3)
        self.assertLess(self.sb.last_elapsed, 2)
        self.assertIn("Plane no responde desde las", err)
        self.assertIn("(conexión rechazada). No se envió nada; reintenta en 25 s.", err)
        self.assertEqual(self.sb.fake.requests, [])

    def test_offline_env_makes_no_request(self):
        code, out, err = self.sb.run(READ, env_set={"PLANE_OFFLINE": "1"})
        self.assertEqual(code, 3)
        self.assertIn("PLANE_OFFLINE=1", err)
        self.assertEqual(self.sb.fake.requests, [])

    def test_expired_cooldown_probes_once(self):
        self.sb.fake.add_fault("*", "/users/me/", "status", 503)
        self.sb.write_circuit(opened_ago=40)
        code, out, err = self.sb.run(READ)
        self.assertEqual(code, 3)
        self.assertEqual([p for _, p, _ in self.sb.fake.requests], ["/api/v1/users/me/"])
        self.assertEqual(self.sb.circuit_state()["level"], 1)
        self.sb.fake.clear_faults()
        self.sb.write_circuit(opened_ago=40)
        code, out, err = self.sb.run(READ)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sb.circuit_state()["opened_at"], None)

    def test_health_reports_open_circuit(self):
        self.sb.write_circuit(opened_ago=5, last_error="dns")
        code, out, err = self.sb.run(["health"])
        self.assertEqual(code, 0)
        self.assertIn("Circuito: abierto desde las", out)
        self.assertIn("DNS no resuelve", out)


if __name__ == "__main__":
    unittest.main()
