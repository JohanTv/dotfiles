"""`outbox list|flush|drop` y el aviso de pendientes: orden, paradas, ambigüedad, concurrencia entre procesos y límites."""
import json
import os
import sqlite3
import subprocess
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402

ISSUE1 = "10000000-0000-4000-8000-000000000001"
ISSUE_OPS = "20000000-0000-4000-8000-000000000013"
COMMENTS = r"/comments/$"
OFF = {"PLANE_OFFLINE": "1"}


def block(start):
    return ('<!-- PLANE_WORKLOG_METADATA {"date": "2026-10-21", "start_time": "%s", "duration_minutes": 20, "notes": "m", "track": "mm"} -->' % start)


class Base(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.fake = self.sb.fake
        self.fake.store_comments = True
        self.addCleanup(self.sb.close)

    def cli(self, *args, code=0, **kwargs):
        got, out, err = self.sb.run(list(args), **kwargs)
        self.assertNotIn("Traceback", err)
        self.assertEqual(got, code, err + out)
        return out, err

    def warm(self):
        self.cli("search", "formulario")
        self.cli("search", "soporte", "-p", "OPS")
        self.fake.requests.clear()

    def queue(self, text, start="08:00", ticket="OMNIFY-1"):
        out, _ = self.cli("comment", "add", ticket, "-m", f"<p>{text}</p>{block(start)}", "--json", env_set=OFF)
        self.assertEqual(json.loads(out)["status"], "queued")
        return json.loads(out)["outbox_id"]

    def rows(self, query="SELECT * FROM outbox ORDER BY id"):
        return self.sb.db_dump(query)

    def sql(self, statement, *params):
        conn = sqlite3.connect(os.path.join(self.sb.home, ".cache", "plane", "worklogs.db"))
        conn.execute(statement, params)
        conn.commit()
        conn.close()

    def stored(self, issue=ISSUE1):
        return [c for c in self.fake.data["comments"][issue] if c.get("external_id")]


class Flush(Base):
    def test_publishes_in_id_order_and_links_the_worklogs(self):
        for n, start in enumerate(("08:00", "08:30", "09:00")):
            self.queue(f"texto {n}", start)
        out, _ = self.cli("outbox", "flush")
        self.assertIn("Resumen: 3 publicado(s), 0 fallido(s), 0 pendiente(s).", out)
        self.assertGreaterEqual(self.sb.last_elapsed, 2)
        self.assertEqual([c["comment_html"].split("</p>")[0] for c in self.stored()], ["<p>texto 0", "<p>texto 1", "<p>texto 2"])
        self.assertEqual([r["state"] for r in self.rows()], ["sent"] * 3)
        self.assertEqual([r["plane_comment_id"] for r in self.rows("SELECT * FROM worklogs ORDER BY start_time")], [c["id"] for c in self.stored()])
        self.assertEqual(self.cli("outbox", "flush")[0].strip().splitlines()[0], "Resumen: 0 publicado(s), 0 fallido(s), 0 pendiente(s).")

    def test_response_lost_when_adding_is_found_by_search_not_resent(self):
        self.fake.add_fault("POST", COMMENTS, "commit_drop", n=1)
        out, _ = self.cli("comment", "add", "OMNIFY-1", "--duration", "5", "-m", f"<p>perdido</p>{block('08:00')}", "--json")
        self.assertEqual(json.loads(out)["status"], "queued")
        out, _ = self.cli("outbox", "flush")
        self.assertIn("ya estaba publicado; no se reenvió", out)
        self.assertEqual(len(self.stored()), 1)
        self.assertEqual(len([r for r in self.fake.requests if r[0] == "POST"]), 1)
        self.assertEqual(self.rows()[0]["state"], "sent")

    def test_response_lost_during_flush_is_resolved_by_the_next_flush(self):
        self.queue("uno")
        self.fake.add_fault("POST", COMMENTS, "commit_drop", n=1)
        _, err = self.cli("outbox", "flush", code=3)
        self.assertIn("Puede que Plane haya recibido la solicitud", err)
        self.assertEqual((len(self.stored()), self.rows()[0]["state"], self.rows()[0]["maybe_delivered"]), (1, "pending", 1))
        self.cli("outbox", "flush")
        self.assertEqual((len(self.stored()), self.rows()[0]["state"]), (1, "sent"))
        self.assertEqual(len([r for r in self.fake.requests if r[0] == "POST"]), 1)

    def test_stops_at_the_first_transient_failure(self):
        for n, start in enumerate(("08:00", "08:30", "09:00")):
            self.queue(f"texto {n}", start)
        self.fake.add_fault("POST", COMMENTS, "status", 503)
        _, err = self.cli("outbox", "flush", code=3)
        self.assertIn("Plane no responde", err)
        self.assertEqual(len([r for r in self.fake.requests if r[0] == "POST"]), 1)
        self.assertEqual([r["state"] for r in self.rows()], ["pending"] * 3)
        self.assertEqual([r["maybe_delivered"] for r in self.rows()], [1, 0, 0])
        self.assertIn("3 pendiente(s)", self.cli("outbox", "flush", code=3, env_set=OFF)[0])

    def test_continues_after_a_missing_ticket_and_keeps_text_and_worklog(self):
        self.warm()
        self.queue("para el ticket borrado", "08:00")
        self.queue("para el soporte", "08:30", ticket="OPS-13")
        self.queue("otro del borrado", "09:00")
        self.fake.fail = [("GET", r"/issues/%s/$" % ISSUE1, 404, {"detail": "borrado"})]
        out, _ = self.cli("outbox", "flush", code=1)
        self.assertIn("✖ #1 OMNIFY-1 falló: HTTP 404", out)
        self.assertEqual([r["state"] for r in self.rows()], ["failed", "sent", "failed"])
        self.assertIn("HTTP 404", self.rows()[0]["last_error"])
        self.assertIn("para el ticket borrado", self.rows()[0]["payload_json"])
        self.assertEqual(self.rows("SELECT plane_comment_id FROM worklogs WHERE ticket_id = 'OMNIFY-1'")[0]["plane_comment_id"], None)
        self.assertEqual(len([r for r in self.fake.requests if r[0] == "GET" and r[1].endswith(f"/issues/{ISSUE1}/")]), 1)
        self.assertEqual(len(self.stored(ISSUE_OPS)), 1)

    def test_a_definitive_post_error_fails_that_item_and_continues(self):
        self.queue("uno", "08:00")
        self.queue("dos", "08:30")
        self.fake.fail = [("POST", COMMENTS, 400, {"detail": "malo"})]
        out, _ = self.cli("outbox", "flush", code=1)
        self.assertEqual([r["state"] for r in self.rows()], ["failed", "failed"])
        self.assertEqual(len([r for r in self.fake.requests if r[0] == "POST"]), 2)
        self.fake.fail = []
        out, _ = self.cli("outbox", "flush", "--retry-failed")
        self.assertIn("2 publicado(s)", out)

    def test_unauthorized_stops_everything_with_exit_1(self):
        self.queue("uno", "08:00")
        self.queue("dos", "08:30")
        self.fake.fail = [("POST", COMMENTS, 401, {"detail": "no"})]
        _, err = self.cli("outbox", "flush", code=1)
        self.assertIn("401", err)
        self.assertEqual(len([r for r in self.fake.requests if r[0] == "POST"]), 1)
        self.assertEqual([r["state"] for r in self.rows()], ["pending", "pending"])

    def test_flush_probes_even_during_the_cooldown_and_closes_the_circuit(self):
        self.queue("uno")
        self.sb.write_circuit(opened_ago=1, level=3)
        self.cli("outbox", "flush")
        self.assertEqual(self.rows()[0]["state"], "sent")
        self.assertIsNone(self.sb.circuit_state()["opened_at"])

    def test_flush_without_plane_exits_3_and_sends_nothing(self):
        self.queue("uno")
        _, err = self.cli("outbox", "flush", code=3, env_set=OFF)
        self.assertIn("PLANE_OFFLINE=1", err)
        _, err = self.cli("outbox", "flush", code=3, env_set={"PLANE_BASE_URL": "{DEAD}"})
        self.assertIn("conexión rechazada", err)
        self.assertEqual(self.fake.requests, [])
        self.assertEqual(self.rows()[0]["state"], "pending")

    def test_limit_age_and_prune(self):
        for n, start in enumerate(("08:00", "08:30", "09:00")):
            self.queue(f"texto {n}", start)
        out, _ = self.cli("outbox", "flush", "--limit", "2")
        self.assertIn("2 publicado(s), 0 fallido(s), 1 pendiente(s)", out)
        old = "2020-01-01T00:00:00+00:00"
        self.sql("UPDATE outbox SET created_at = ? WHERE id = 3", old)
        out, _ = self.cli("outbox", "flush")
        self.assertIn("1 de más de 7 días omitido(s) (usa --include-old)", out)
        self.assertEqual(self.rows("SELECT state FROM outbox WHERE id = 3")[0]["state"], "pending")
        out, _ = self.cli("outbox", "flush", "--include-old")
        self.assertIn("1 publicado(s)", out)
        self.sql("UPDATE outbox SET updated_at = ? WHERE id = 1", old)
        self.cli("outbox", "flush")
        self.assertEqual([r["id"] for r in self.rows()], [2, 3])


class Processes(Base):
    def flush_process(self):
        return subprocess.Popen([sys.executable, gs.PLANE_PY, "outbox", "flush"], env=self.sb.env, cwd=self.sb.work, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)

    def test_two_concurrent_flushes_publish_each_item_exactly_once(self):
        for n in range(4):
            self.queue(f"texto {n}", f"08:{n:02d}")
        procs = [self.flush_process(), self.flush_process()]
        for proc in procs:
            _, err = proc.communicate(timeout=60)
            self.assertEqual(proc.returncode, 0, err)
        self.assertEqual(len(self.stored()), 4)
        self.assertEqual(len({c["external_id"] for c in self.stored()}), 4)
        self.assertEqual([r["state"] for r in self.rows()], ["sent"] * 4)
        self.assertEqual([r["attempts"] for r in self.rows()], [1] * 4)

    def test_killed_flush_is_resolved_after_its_lease_expires(self):
        self.queue("interrumpido")
        self.fake.add_fault("POST", COMMENTS, "delay", 2, n=1)
        proc = self.flush_process()
        deadline = time.time() + 20
        while not any(r[0] == "POST" for r in self.fake.requests) and time.time() < deadline:
            time.sleep(0.05)
        proc.kill()
        proc.communicate()
        self.assertEqual(self.rows()[0]["state"], "sending")
        out, _ = self.cli("outbox", "flush")
        self.assertIn("0 publicado(s), 0 fallido(s), 1 pendiente(s)", out)
        deadline = time.time() + 10
        while not self.fake.committed and time.time() < deadline:
            time.sleep(0.05)
        self.sql("UPDATE outbox SET lease_until = 1")
        out, _ = self.cli("outbox", "flush")
        self.assertIn("ya estaba publicado; no se reenvió", out)
        self.assertEqual((len(self.stored()), len([r for r in self.fake.requests if r[0] == "POST"]), self.rows()[0]["state"]), (1, 1, "sent"))


class ListDropNotice(Base):
    def test_list_shows_a_preview_and_never_the_payload(self):
        self.queue("x" * 200)
        out, _ = self.cli("outbox", "list", "--json")
        item = json.loads(out)[0]
        self.assertEqual((item["state"], item["ticket"], item["duration_minutes"], len(item["preview"])), ("pending", "OMNIFY-1", 20, 80))
        self.assertNotIn("payload_json", item)
        self.assertNotIn("dummy", out)
        text, _ = self.cli("outbox", "list")
        self.assertIn("#1 [pending] OMNIFY-1 · mm · 2026-10-21 08:00 · 20 min", text)
        self.assertNotIn("PLANE_WORKLOG_METADATA", text)
        self.cli("outbox", "flush")
        self.assertEqual(self.cli("outbox", "list")[0].strip(), "La cola está vacía.")
        self.assertEqual(json.loads(self.cli("outbox", "list", "--all", "--json")[0])[0]["state"], "sent")

    def test_drop_removes_the_provisional_worklog_unless_kept(self):
        self.queue("uno", "08:00")
        self.queue("dos", "08:30")
        self.cli("outbox", "drop", "1")
        self.cli("outbox", "drop", "2", "--keep-worklog", "--json")
        self.assertEqual([r["state"] for r in self.rows()], ["dropped", "dropped"])
        self.assertEqual([r["start_time"] for r in self.rows("SELECT start_time FROM worklogs")], ["08:30"])
        self.assertEqual(self.cli("outbox", "drop", "1", code=1)[1].strip(), "Error: el registro #1 está en estado dropped; solo se descartan los pendientes, en envío o fallidos.")
        self.assertIn("no existe el registro #9", self.cli("outbox", "drop", "9", code=1)[1])
        self.assertEqual(self.cli("outbox", "flush")[0].splitlines()[0], "Resumen: 0 publicado(s), 0 fallido(s), 0 pendiente(s).")
        self.assertEqual(self.stored(), [])

    def test_drop_of_a_possibly_delivered_item_needs_force(self):
        self.fake.add_fault("POST", COMMENTS, "commit_drop", n=1)
        self.cli("comment", "add", "OMNIFY-1", "--duration", "5", "-m", f"<p>dudoso</p>{block('08:00')}")
        _, err = self.cli("outbox", "drop", "1", code=1)
        self.assertIn("Puede que ya esté publicado en Plane", err)
        self.assertEqual(self.rows()[0]["state"], "pending")
        self.cli("outbox", "drop", "1", "--force")
        self.assertEqual(self.rows()[0]["state"], "dropped")

    def test_a_sent_item_cannot_be_dropped(self):
        self.queue("uno")
        self.cli("outbox", "flush")
        self.assertIn("estado sent", self.cli("outbox", "drop", "1", code=1)[1])
        self.assertEqual(self.rows("SELECT plane_comment_id FROM worklogs")[0]["plane_comment_id"], self.stored()[0]["id"])

    def test_notice_goes_to_stderr_once_and_never_for_outbox_commands(self):
        self.queue("uno")
        _, err = self.cli("labels")
        self.assertEqual(err.count("⏳ Outbox: 1 pendiente(s) de publicar. Ejecuta: plane-tracker outbox flush"), 1)
        self.assertEqual(self.cli("outbox", "list")[1], "")
        self.assertEqual(self.cli("list", env_drop=("PLANE_API_KEY",), code=1)[1].count("Outbox"), 0)
        self.sql("UPDATE outbox SET state = 'failed'")
        _, err = self.cli("labels")
        self.assertIn("⏳ Outbox: 0 pendiente(s) de publicar, 1 fallido(s) (revisa: plane-tracker outbox list). Ejecuta: plane-tracker outbox flush", err)

    def test_health_counts_the_queue(self):
        self.queue("uno")
        out, _ = self.cli("health")
        self.assertIn("Cola de salida: 1 pendiente(s), 0 fallido(s)", out)
        data = json.loads(self.cli("health", "--json")[0])
        self.assertEqual(data["outbox"], {"pending": 1, "failed": 0})


if __name__ == "__main__":
    unittest.main()
