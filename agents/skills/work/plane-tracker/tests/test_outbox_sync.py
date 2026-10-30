"""Registros en cola frente a `report --refresh` (sync), `worklog check` y los avisos de `report`."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402

ISSUE1 = "10000000-0000-4000-8000-000000000001"
REMOTE = "c1000000-0000-4000-8000-000000000001"  # OMNIFY-1 · main · 2026-10-20 10:00 en el servidor falso
OFF = {"PLANE_OFFLINE": "1"}
BLOCK = '<!-- PLANE_WORKLOG_METADATA {"date": "%s", "start_time": "%s", "end_time": "%s", "duration_minutes": 60, "notes": "local", "track": "main"} -->'


class Base(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)

    def cli(self, *args, code=0, **kwargs):
        got, out, err = self.sb.run(list(args), **kwargs)
        self.assertNotIn("Traceback", err)
        self.assertEqual(got, code, err + out)
        return out, err

    def queue(self, text, date="2026-10-20", start="10:00"):
        out, _ = self.cli("comment", "add", "OMNIFY-1", "-m", f"<p>{text}</p>" + BLOCK % (date, start, f"{int(start[:2]) + 1:02d}:00"), "--json", env_set=OFF)
        return json.loads(out)["client_id"]

    def worklog(self, start="10:00", date="2026-10-20"):
        return self.sb.db_dump(f"SELECT * FROM worklogs WHERE ticket_id = 'OMNIFY-1' AND track = 'main' AND date = '{date}' AND start_time = '{start}'")[0]

    def item(self):
        return self.sb.db_dump("SELECT * FROM outbox ORDER BY id")[0]


class Sync(Base):
    def test_a_foreign_comment_with_the_same_key_does_not_overwrite_the_pending_row(self):
        self.queue("pendiente")
        _, err = self.cli("report", "--date", "2026-10-20", "--refresh")
        self.assertIn("1 comentario(s) de Plane no se sincronizaron: coinciden con un registro en cola", err)
        row = self.worklog()
        self.assertIsNone(row["plane_comment_id"])
        self.assertEqual(row["notes"], "local")
        self.assertEqual(self.item()["state"], "pending")
        self.assertEqual(len(self.sb.db_dump("SELECT 1 FROM worklogs")), 3)  # los demás comentarios sí se sincronizaron

    def test_the_same_client_id_links_the_comment_and_marks_the_item_sent(self):
        client_id = self.queue("pendiente")
        meta = {"date": "2026-10-20", "start_time": "10:00", "end_time": "11:00", "duration_minutes": 60, "track": "main", "notes": "local", "client_id": client_id}
        self.sb.fake.data["comments"][ISSUE1].append({"id": "c7000000-0000-4000-8000-000000000007", "actor": gs.ME, "created_by": gs.ME,
                                                      "created_at": "2026-10-20T11:05:00Z", "comment_html": "<p>pendiente</p>" + gs.meta_block(**meta)})
        self.cli("report", "--date", "2026-10-20", "--refresh")
        self.assertEqual((self.item()["state"], self.item()["plane_comment_id"]), ("sent", "c7000000-0000-4000-8000-000000000007"))
        self.assertEqual(self.worklog()["plane_comment_id"], "c7000000-0000-4000-8000-000000000007")
        out, _ = self.cli("outbox", "list")
        self.assertEqual(out.strip(), "La cola está vacía.")


class Check(Base):
    def test_pending_rows_are_a_warning_not_an_error(self):
        self.queue("pendiente", date="2026-10-21", start="08:00")
        out, _ = self.cli("worklog", "check", "--date", "2026-10-21", "--json")
        data = json.loads(out)
        self.assertEqual([i["code"] for i in data["issues"]], ["pending"])
        self.assertTrue(data["ok"])
        text, _ = self.cli("worklog", "check", "--date", "2026-10-21")
        self.assertIn("[pending] 2026-10-21 08:00 en cola de publicación", text)
        self.assertIn("0 inconsistencia(s), 1 aviso(s)", text)

    def test_an_unqueued_row_without_comment_stays_unlinked(self):
        self.queue("pendiente", date="2026-10-21", start="08:00")
        self.cli("outbox", "drop", "1", "--keep-worklog")
        data = json.loads(self.cli("worklog", "check", "--date", "2026-10-21", "--json")[0])
        self.assertEqual([i["code"] for i in data["issues"]], ["unlinked"])


class Report(Base):
    def test_report_warns_about_unpublished_rows_and_still_counts_them(self):
        self.queue("pendiente", date="2026-10-21", start="08:00")
        out, err = self.cli("report", "--date", "2026-10-21")
        self.assertIn("⏳ 1 registro(s) de este periodo siguen sin publicarse (outbox list).", err)
        self.assertIn("1h 00m", out)
        rows = json.loads(self.cli("report", "--date", "2026-10-21", "--json")[0])
        self.assertEqual((len(rows), rows[0]["plane_comment_id"]), (1, None))
        self.assertNotIn("sin publicarse", self.cli("report", "--date", "2026-10-22")[1])
        self.assertIn("sin publicarse", self.cli("report", "flow", "--date", "2026-10-21")[1])
        self.assertNotIn("sin publicarse", self.cli("report", "--date", "2026-10-21", "-p", "OPS")[1])


if __name__ == "__main__":
    unittest.main()
