"""Cola de salida de `comment add`: guardado previo, idempotencia, entrega ambigua y comandos que no se encolan."""
import json
import os
import socket
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402
from plane_cli import config, db, outbox  # noqa: E402
from plane_cli.api import PlaneUnavailable  # noqa: E402

ISSUE = "10000000-0000-4000-8000-000000000001"
COMMENTS = r"/comments/$"
BLOCK = '<!-- PLANE_WORKLOG_METADATA {"date": "2026-10-21", "start_time": "08:00", "duration_minutes": 20, "notes": "meta", "track": "mm"} -->'
ADD = ["comment", "add", "OMNIFY-1", "--duration", "5"]


def html_with_block(text):
    return f"<p>{text}</p>{BLOCK}"


class Cli(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.sb.fake.store_comments = True
        self.addCleanup(self.sb.close)

    def cli(self, *args, code=0, **kwargs):
        got, out, err = self.sb.run(list(args), **kwargs)
        self.assertNotIn("Traceback", err)
        self.assertEqual(got, code, err)
        return out, err

    def rows(self, table="outbox"):
        return self.sb.db_dump(f"SELECT * FROM {table} ORDER BY 1")

    def warm(self):
        self.cli("projects")
        self.sb.fake.requests.clear()

    def posts(self):
        return [r for r in self.sb.fake.requests if r[0] == "POST"]

    # --- publicación en línea ---------------------------------------------------
    def test_online_comment_is_idempotent_and_links_the_worklog(self):
        out, _ = self.cli(*ADD, "-m", "hola", "--json")
        result = json.loads(out)
        self.assertEqual(result["status"], "ok")
        comment = self.sb.fake.data["comments"][ISSUE][-1]
        item = self.rows()[0]
        self.assertTrue(comment["external_id"].startswith("pt-"))
        self.assertEqual((comment["external_source"], item["client_id"], item["state"]), ("plane-tracker", comment["external_id"], "sent"))
        self.assertIn(f'"client_id": "{item["client_id"]}"', comment["comment_html"])
        self.assertEqual(set(json.loads(item["payload_json"])), {"comment_html", "external_source", "external_id"})
        self.assertNotIn("dummy", item["payload_json"])
        self.assertEqual(self.rows("worklogs")[0]["plane_comment_id"], result["comment_id"])

    def test_retry_of_a_sent_comment_returns_the_same_result_without_posting(self):
        args = [*ADD, "-m", html_with_block("igual"), "--json"]
        first = json.loads(self.cli(*args)[0])
        second = json.loads(self.cli(*args)[0])
        self.assertEqual(first, second)
        self.assertEqual(len(self.posts()), 1)

    def test_same_key_with_other_text_is_rejected_with_the_exact_message(self):
        self.warm()
        self.sb.write_circuit(opened_ago=5)
        self.cli(*ADD, "-m", html_with_block("A"))
        _, err = self.cli(*ADD, "-m", html_with_block("B"), code=1)
        self.assertEqual(err.strip(), "Ya hay un registro en cola con ese ticket/track/fecha/inicio (#1). Publícalo con 'outbox flush' o descártalo con 'outbox drop 1'.")
        first = json.loads(self.cli(*ADD, "-m", html_with_block("A"), "--json")[0])
        self.assertEqual((first["status"], first["outbox_id"]), ("queued", 1))
        self.assertEqual(len(self.rows()), 1)

    # --- fallos de la entrega ---------------------------------------------------
    def test_read_timeout_on_post_queues_without_retrying(self):
        self.sb.fake.add_fault("POST", COMMENTS, "hang", 20)
        out, _ = self.cli(*ADD, "-m", "hola", "--json")
        self.assertEqual((json.loads(out)["status"], json.loads(out)["reason"]), ("queued", "read_timeout"))
        self.assertEqual(len(self.posts()), 1)
        item = self.rows()[0]
        self.assertEqual((item["state"], item["maybe_delivered"], item["attempts"]), ("pending", 1, 1))
        self.assertIsNone(self.rows("worklogs")[0]["plane_comment_id"])

    def test_response_lost_after_commit_keeps_the_ambiguity(self):
        self.sb.fake.add_fault("POST", COMMENTS, "commit_drop")
        out, _ = self.cli(*ADD, "-m", "hola", "--json")
        self.assertEqual(json.loads(out)["status"], "queued")
        self.assertEqual(len(self.sb.fake.committed), 1)
        self.assertEqual((self.rows()[0]["state"], self.rows()[0]["maybe_delivered"]), ("pending", 1))

    def test_circuit_open_queues_text_and_json(self):
        self.warm()
        self.sb.write_circuit(opened_ago=5)
        out, err = self.cli(*ADD, "-m", "hola", "--track", "t1")
        self.assertEqual(out.strip(), "⏳ En cola (#1): comentario para OMNIFY-1, 5 min. Plane no responde; el tiempo ya cuenta como registrado. Publícalo con: plane-tracker outbox flush")
        data = json.loads(self.cli(*ADD, "-m", "otro", "--track", "t2", "--json")[0])
        self.assertEqual((data["status"], data["action"], data["outbox_id"], data["issue"], data["duration_minutes"], data["reason"]),
                         ("queued", "comment", 2, "OMNIFY-1", 5, "circuit_open"))
        self.assertRegex(data["client_id"], r"^pt-[0-9a-f]{20}$")
        self.assertEqual(self.sb.fake.requests, [])
        self.assertEqual([r["plane_comment_id"] for r in self.rows("worklogs")], [None, None])
        self.assertEqual([r["maybe_delivered"] for r in self.rows()], [0, 0])

    def test_without_any_cache_it_still_queues(self):
        out, _ = self.cli(*ADD, "-m", "hola", "--json", env_set={"PLANE_OFFLINE": "1"})
        self.assertEqual(json.loads(out)["status"], "queued")
        self.assertEqual(self.sb.fake.requests, [])
        self.assertEqual(self.rows()[0]["ticket_ref"], "OMNIFY-1")

    def test_no_queue_env_fails_with_exit_3_and_leaves_nothing(self):
        self.warm()
        self.sb.write_circuit(opened_ago=5)
        _, err = self.cli(*ADD, "-m", "hola", code=3, env_set={"PLANE_NO_QUEUE": "1"})
        self.assertIn("Plane no responde", err)
        self.assertEqual((self.rows(), self.rows("worklogs")), ([], []))
        self.sb.fake.add_fault("POST", COMMENTS, "drop")
        self.sb.write_circuit(opened_ago=None, consec=0)
        self.cli(*ADD, "-m", "hola", code=3, env_set={"PLANE_NO_QUEUE": "1"})
        self.assertEqual((self.rows(), self.rows("worklogs")), ([], []))

    def test_definitive_error_leaves_no_residue(self):
        self.sb.fake.fail = [("POST", COMMENTS, 400, {"detail": "malo"})]
        _, err = self.cli(*ADD, "-m", "hola", code=1)
        self.assertIn(f"Error HTTP 400 en {self.sb.fake.base_url}/api/v1/workspaces/ws/projects/{gs.P1}/issues/{ISSUE}/comments/: ", err)
        self.assertEqual((self.rows(), self.rows("worklogs")), ([], []))
        self.assertEqual(len(self.posts()), 1)

    def test_queued_time_still_counts_as_registered(self):
        sb = gs.Sandbox(with_session=True)
        self.addCleanup(sb.close)
        base = ["worklog", "propose", "OMNIFY-1", "--agent", "claude", "--session", gs.SESSION, "--date", "2026-10-20", "--json"]
        before = json.loads(sb.run(base)[1])
        sb.run(["projects"])
        sb.write_circuit(opened_ago=5)
        code, out, err = sb.run(["comment", "add", "OMNIFY-1", "-m", "avance", "--accept-proposal", "--agent", "claude", "--session", gs.SESSION])
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("⏳ En cola"), out)
        after = json.loads(sb.run(base)[1])
        self.assertLess(after.get("minutes") or 0, before["minutes"])

    # --- límites ----------------------------------------------------------------
    def test_text_over_64_kb_is_rejected(self):
        _, err = self.cli(*ADD, "-m", "x" * (65 * 1024), code=1)
        self.assertIn("64 KB", err)
        self.assertEqual(self.rows(), [])

    def test_201st_open_item_is_rejected(self):
        self.cli("health")
        path = os.path.join(self.sb.home, ".cache", "plane", "worklogs.db")
        conn = sqlite3.connect(path)
        conn.executemany("INSERT INTO outbox (client_id, ticket_ref, payload_json, wl_ticket_id, wl_track, wl_date, wl_start_time, created_at, updated_at) "
                         "VALUES (?, 'X-1', '{}', 'X-1', 'main', '2026-10-01', ?, 'x', 'x')", [(f"pt-{i}", f"{i}") for i in range(200)])
        conn.commit()
        conn.close()
        _, err = self.cli(*ADD, "-m", "hola", code=1)
        self.assertIn("200", err)
        self.assertEqual(len(self.rows()), 200)

    # --- lo que nunca se encola -------------------------------------------------
    def test_other_writes_fail_fast_with_exit_3(self):
        self.warm()
        with open(os.path.join(self.sb.work, "adj.txt"), "w") as handle:
            handle.write("x")
        cid = "c1000000-0000-4000-8000-000000000001"
        commands = [["comment", "edit", "OMNIFY-1", "--comment-id", cid, "-m", "nuevo"], ["comment", "delete", "OMNIFY-1", "--comment-id", cid],
                    ["update", "OMNIFY-1", "--priority", "high"], ["link", "add", "OMNIFY-1", "https://example.com/x"], ["create", "[FIX] algo"],
                    ["attachment", "add", "OMNIFY-1", "adj.txt"], ["attachment", "list", "OMNIFY-1"], ["attachment", "delete", "OMNIFY-1", gs.P1],
                    ["attachment", "replace", "OMNIFY-1", gs.P1, "adj.txt"]]
        self.sb.write_circuit(opened_ago=5)
        for args in commands:
            with self.subTest(args=args[:2]):
                self.sb.fake.requests.clear()
                code, out, err = self.sb.run(args, timeout=10)
                self.assertEqual(code, 3, err)
                self.assertLess(self.sb.last_elapsed, 3)
                self.assertEqual(self.sb.fake.requests, [])
        self.assertEqual(self.rows(), [])


class Library(unittest.TestCase):
    """publish_comment y deliver directamente, sin proceso: conexión rechazada, búsqueda previa y reclamo."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake = gs.FakePlane()
        self.fake.store_comments = True
        patcher = mock.patch.object(config, "CACHE_DIR", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.fake.close)
        self.conn = db.get_db()
        db.init_db(self.conn)
        self.addCleanup(self.conn.close)

    def draft(self, base_url=None, text="<p>hola</p>", start="10:00"):
        meta = {"schema_version": "2.2", "date": "2026-10-30", "start_time": start, "duration_minutes": 5, "track": "main"}
        entry = {"id": None, "ticket_id": "OMNIFY-1", "track": "main", "date": "2026-10-30", "start_time": start, "end_time": "10:05", "duration_minutes": 5,
                 "plane_comment_id": None, "raw_payload": meta}
        issue = {"id": ISSUE, "name": "t", "sequence_id": 1}
        return outbox.Draft(base_url or self.fake.base_url, "k", gs.WS, gs.P1, issue, "OMNIFY-1", text, meta, entry)

    def item(self):
        return self.conn.execute("SELECT * FROM outbox ORDER BY id DESC").fetchone()

    def test_connection_refused_leaves_the_item_pending_and_not_delivered(self):
        result = outbox.publish_comment(self.conn, self.draft(dead_url()))
        self.assertEqual((result.state, result.reason), ("queued", "refused"))
        item = self.item()
        self.assertEqual((item["state"], item["maybe_delivered"], item["attempts"]), ("pending", 0, 1))
        self.assertIsNone(self.conn.execute("SELECT plane_comment_id FROM worklogs").fetchone()[0])

    def test_ambiguous_item_is_found_instead_of_resent(self):
        self.fake.add_fault("POST", COMMENTS, "commit_drop", n=1)
        first = outbox.publish_comment(self.conn, self.draft())
        self.assertEqual((first.state, self.item()["maybe_delivered"]), ("queued", 1))
        item = self.item()
        outcome = outbox.deliver(self.conn, item, lambda: (gs.P1, ISSUE), self.fake.base_url, "k", gs.WS)
        self.assertEqual(outcome[0::2], ("sent", "found"))
        self.assertEqual(len(self.fake.committed), 1)
        self.assertEqual(len([r for r in self.fake.requests if r[0] == "POST"]), 1)
        self.assertEqual(self.item()["state"], "sent")
        self.assertEqual(self.conn.execute("SELECT plane_comment_id FROM worklogs").fetchone()[0], outcome[1])

    def test_duplicate_external_id_conflict_marks_the_item_sent(self):
        self.fake.add_fault("POST", COMMENTS, "commit_drop", n=1)
        outbox.publish_comment(self.conn, self.draft())
        self.conn.execute("UPDATE outbox SET maybe_delivered = 0")  # sin pista previa: solo el 409 delata el duplicado
        self.conn.commit()
        outcome = outbox.deliver(self.conn, self.item(), lambda: (gs.P1, ISSUE), self.fake.base_url, "k", gs.WS)
        self.assertEqual(outcome[0::2], ("sent", "exists"))
        self.assertEqual(len(self.fake.committed), 1)

    def test_second_claim_gets_nothing_and_a_released_item_keeps_its_ambiguity(self):
        self.fake.add_fault("POST", COMMENTS, "drop")
        outbox.publish_comment(self.conn, self.draft())
        item = self.item()
        first = outbox.claim(self.conn, item["id"])
        self.assertEqual(first["state"], "pending")
        self.assertIsNone(outbox.claim(self.conn, item["id"]))
        outbox.release(self.conn, item["id"], first, PlaneUnavailable("refused", "no"))
        self.assertEqual((self.item()["state"], self.item()["maybe_delivered"]), ("pending", 1))

    def test_expired_lease_is_claimable_and_counts_as_ambiguous(self):
        self.fake.add_fault("POST", COMMENTS, "commit_drop", n=1)
        outbox.publish_comment(self.conn, self.draft())
        self.conn.execute("UPDATE outbox SET state = 'sending', lease_until = 1")
        self.conn.commit()
        outcome = outbox.deliver(self.conn, self.item(), lambda: (gs.P1, ISSUE), self.fake.base_url, "k", gs.WS)
        self.assertEqual(outcome[0::2], ("sent", "found"))
        self.assertEqual(len(self.fake.committed), 1)

    def test_a_live_lease_blocks_the_claim(self):
        self.fake.add_fault("POST", COMMENTS, "drop")
        outbox.publish_comment(self.conn, self.draft())
        self.conn.execute("UPDATE outbox SET state = 'sending', lease_until = ?", (config.now().timestamp() + 100,))
        self.conn.commit()
        self.assertEqual(outbox.deliver(self.conn, self.item(), lambda: (gs.P1, ISSUE), self.fake.base_url, "k", gs.WS), ("busy",))

    def test_client_id_ignores_the_hidden_block_and_follows_the_visible_text(self):
        a = outbox.make_client_id("OPS-1", "main", "2026-10-30", "10:00", "<p>x</p>" + BLOCK)
        self.assertEqual(a, outbox.make_client_id("OPS-1", "main", "2026-10-30", "10:00", "<p>x</p>"))
        self.assertNotEqual(a, outbox.make_client_id("OPS-1", "main", "2026-10-30", "10:01", "<p>x</p>"))
        self.assertNotEqual(a, outbox.make_client_id("OPS-1", "main", "2026-10-30", "10:00", "<p>y</p>"))


def dead_url():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{probe.getsockname()[1]}"
    probe.close()
    return url


if __name__ == "__main__":
    unittest.main()
