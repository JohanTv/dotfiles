"""Vistas de lectura de la fase 3 (`get`, `labels`, `projects`, `whoami`, `attachment list`, `outbox list`): sobre, cobertura y adquisición."""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402
from plane_cli import coverage, envelope, query_misc  # noqa: E402

OFFLINE = {"PLANE_OFFLINE": "1"}


class Views(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)

    def run_json(self, *args, code=0, **kwargs):
        got, out, err = self.sb.run([*args, "--json"], **kwargs)
        self.assertEqual(got, code, err + out)
        return json.loads(out), err

    def requests(self, mark=0):
        return [p for _m, p, _b in self.sb.fake.requests[mark:]]

    def sql(self, statement, params=()):
        conn = sqlite3.connect(os.path.join(self.sb.home, ".cache", "plane", "worklogs.db"))
        conn.execute(statement, params)
        conn.commit()
        conn.close()

    # --- get ----------------------------------------------------------------------------------------------------------------------------
    def test_get_resolves_the_ticket_in_one_get_and_has_no_scope(self):
        doc, err = self.run_json("get", "OMNIFY-1")
        self.assertEqual(envelope.validate(doc), [])
        self.assertNotIn("scope", doc)
        self.assertEqual((doc["view"], doc["total"], doc["coverage"]["source"], doc["coverage"]["complete"]), ("get", 1, "api", True))
        paths = self.requests()
        self.assertEqual([p for p in paths if p.endswith("/issues/OMNIFY-1/")], ["/api/v1/workspaces/ws/issues/OMNIFY-1/"])
        self.assertFalse([p for p in paths if p.endswith("/issues/")], "ya no se recorre el listado del proyecto")
        row = doc["results"][0]
        self.assertEqual((row["ticket"], row["state"], row["state_group"], row["project"], row["labels"]), ("OMNIFY-1", "Progreso", "started", "OMNIFY", ["backend", "sms"]))
        self.assertEqual(row["assignees"], [{"id": gs.OTHER, "name": "otro"}])
        self.assertEqual(set(row["comments"][0]), {"id", "author", "created_at", "text"})
        self.assertNotIn("<", json.dumps(row["comments"]), "el texto de los comentarios va sin HTML ni bloques de telemetría")

    def test_get_falls_back_to_the_listing_when_the_label_endpoint_is_missing(self):
        self.sb.fake.fail = [("GET", r"/workspaces/ws/issues/OMNIFY-2/$", 404, {"detail": "no"})]
        doc, _ = self.run_json("get", "OMNIFY-2")
        self.assertEqual(doc["results"][0]["ticket"], "OMNIFY-2")
        self.assertTrue([p for p in self.requests() if p.endswith("/projects/%s/issues/" % gs.P1)])

    def test_get_options_shape_the_row_and_the_coverage(self):
        doc, _ = self.run_json("get", "OMNIFY-1", "--last", "1", "--no-description")
        row = doc["results"][0]
        self.assertEqual((len(row["comments"]), "description" in row, doc["coverage"]["detail"]["comments"]), (1, False, {"shown": 1, "total": 4}))
        self.assertIs(doc["coverage"]["complete"], True)
        doc, _ = self.run_json("get", "OMNIFY-1", "--no-comments")
        self.assertNotIn("comments", doc["results"][0])
        self.assertIs(doc["coverage"]["complete"], None, "sin leer los comentarios no se puede afirmar que el ticket esté completo")

    def test_labels_are_left_out_when_one_is_unknown_instead_of_guessed(self):
        self.run_json("get", "OMNIFY-1")
        self.sql("DELETE FROM labels WHERE name = 'sms'")
        doc, _ = self.run_json("get", "OMNIFY-1", env_set=OFFLINE)
        self.assertNotIn("labels", doc["results"][0])
        self.assertEqual((doc["coverage"]["source"], doc["coverage"]["stale"]), ("snapshot", True))

    def test_include_reads_only_what_was_asked_and_costs_one_get_each(self):
        self.sb.fake.data["links"] += [{"id": "l1", "title": "Doc", "url": "https://example.com/a", "created_at": "2026-10-01T10:00:00Z"}]
        mark = len(self.sb.fake.requests)
        doc, _ = self.run_json("get", "OMNIFY-1", "--include", "links")
        row = doc["results"][0]
        self.assertEqual(row["links"], [{"id": "l1", "title": "Doc", "url": "https://example.com/a", "created_at": "2026-10-01T10:00:00Z"}])
        self.assertNotIn("attachments", row)
        self.assertEqual(doc["coverage"]["detail"]["include"], ["links"])
        self.assertEqual(len([p for p in self.requests(mark) if p.endswith("/links/")]), 1)
        self.assertFalse([p for p in self.requests(mark) if "issue-attachments" in p])
        self.assertIs(doc["coverage"]["complete"], True)
        doc, _ = self.run_json("get", "OMNIFY-1", "--include", "attachments,links")
        self.assertEqual((doc["results"][0]["attachments"][0]["name"], doc["coverage"]["detail"]["include"]), ("informe.pdf", ["attachments", "links"]))
        doc, _ = self.run_json("get", "OMNIFY-1")
        self.assertFalse({"attachments", "links"} & set(doc["results"][0]), "sin pedirlos no se emiten")

    def test_an_empty_include_is_a_measured_empty_list(self):
        self.sb.fake.data["links"] = []
        doc, _ = self.run_json("get", "OMNIFY-1", "--include", "links")
        self.assertEqual(doc["results"][0]["links"], [])
        self.assertIs(doc["coverage"]["complete"], True)

    def test_relations_and_children_only_warn_and_all_covers_what_exists(self):
        mark = len(self.sb.fake.requests)
        doc, _ = self.run_json("get", "OMNIFY-1", "--include", "relations,children")
        warn = [n for n in doc["notes"] if n["code"] == "include_not_covered"]
        self.assertEqual(len(warn), 1)
        self.assertIn("relations, children", warn[0]["text"])
        self.assertIs(doc["coverage"]["complete"], None, "se pidió algo que no se entrega: no es completo")
        self.assertFalse([p for p in self.requests(mark) if p.endswith(("/links/", "/relations/")) or "issue-attachments" in p])
        doc, _ = self.run_json("get", "OMNIFY-1", "--all")
        row = doc["results"][0]
        self.assertTrue({"attachments", "links"} <= set(row))
        self.assertEqual(doc["coverage"]["detail"]["include"], ["attachments", "links"])
        self.assertIn("relations, children", [n for n in doc["notes"] if n["code"] == "include_not_covered"][0]["text"])
        self.assertEqual(envelope.validate(doc), [])

    def test_unknown_include_is_a_usage_error_with_the_options(self):
        code, out, err = self.sb.run(["get", "OMNIFY-1", "--include", "nope"])
        self.assertEqual(code, 2)
        self.assertIn("attachments, links, relations, children", err)

    def test_includes_cannot_be_read_offline_and_are_left_out(self):
        self.run_json("get", "OMNIFY-1")
        doc, _ = self.run_json("get", "OMNIFY-1", "--include", "links", env_set=OFFLINE)
        self.assertNotIn("links", doc["results"][0])
        self.assertIs(doc["coverage"]["complete"], None)

    # --- etiquetas ---
    def test_a_label_missing_from_the_cache_is_refreshed_once_while_online(self):
        self.run_json("get", "OMNIFY-1")  # llena la caché de etiquetas
        new = {"id": "1bnew000-0000-4000-8000-%s" % gs.P1[:12], "name": "nueva", "color": "#abcdef"}
        self.sb.fake.data["labels"][gs.P1].append(new)
        self.sb.fake.data["issues"][gs.P1][0]["labels"].append(new["id"])
        mark = len(self.sb.fake.requests)
        doc, _ = self.run_json("get", "OMNIFY-1")
        self.assertEqual(doc["results"][0]["labels"], ["backend", "sms", "nueva"])
        self.assertEqual(len([p for p in self.requests(mark) if p.endswith(f"/projects/{gs.P1}/labels/")]), 1, "un GET para ponerlas al día")
        mark = len(self.sb.fake.requests)
        self.run_json("get", "OMNIFY-1")
        self.assertFalse([p for p in self.requests(mark) if p.endswith("/labels/")], "con la caché al día no se vuelve a pedir")

    # --- catálogos ----------------------------------------------------------------------------------------------------------------------
    def test_catalogs_are_sorted_and_declare_their_project(self):
        doc, _ = self.run_json("labels", "-p", "OPS")
        self.assertEqual(doc["scope"], {"order": "name", "projects": ["OPS"]})
        self.assertEqual([r["name"] for r in doc["results"]], ["backend", "bug", "frontend", "sms"])
        doc, _ = self.run_json("projects")
        self.assertEqual([r["identifier"] for r in doc["results"]], ["OMNIFY", "OPS"])
        self.assertEqual((doc["coverage"]["complete"], doc["coverage"]["stale"]), (True, False))

    def test_catalog_errors_keep_their_message_and_exit_code(self):
        code, out, err = self.sb.run(["labels", "-p", "NOPE", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["code"], "unknown_project")
        self.sb.fake.fail = [("GET", r"/projects/%s/labels/$" % gs.P1, 404, {"detail": "nada"})]
        code, out, err = self.sb.run(["labels"])
        self.assertEqual(code, 1)
        self.assertIn("Error HTTP 404", err)

    # --- whoami -------------------------------------------------------------------------------------------------------------------------
    def test_whoami_reports_where_the_identity_comes_from(self):
        doc, _ = self.run_json("whoami")
        self.assertEqual(doc["results"][0]["source"], "actor_env")
        self.assertEqual((doc["coverage"]["source"], doc["coverage"]["complete"]), ("local", True))
        doc, _ = self.run_json("whoami", env_drop=("PLANE_ACTOR_UUID",), env_set={"PLANE_USERNAME": "tester"})
        self.assertEqual((doc["results"][0]["status"], doc["results"][0]["actor"], doc["coverage"]["source"]), ("ok", gs.ME, "api"))
        doc, _ = self.run_json("whoami", env_drop=("PLANE_ACTOR_UUID",), env_set={"PLANE_USERNAME": "nadie"}, code=1)
        self.assertEqual((doc["results"][0]["status"], doc["coverage"]["complete"]), ("unresolved", None))
        doc, _ = self.run_json("whoami", env_drop=("PLANE_ACTOR_UUID", "PLANE_USERNAME"))
        self.assertEqual((doc["results"][0]["status"], doc["results"][0]["source"]), ("unset", "unset"))

    # --- attachment list y outbox list --------------------------------------------------------------------------------------------------
    def test_attachment_list_is_a_network_read_without_scope(self):
        doc, _ = self.run_json("attachment", "list", "OMNIFY-1")
        self.assertEqual((doc["coverage"]["source"], doc["coverage"]["complete"], "scope" in doc), ("api", True, False))
        self.assertEqual(doc["results"][0]["ticket"], "OMNIFY-1")

    def test_attachment_list_is_not_complete_when_plane_announces_more_pages(self):
        cov = coverage.Coverage(source="api", complete=None)
        result = query_misc.attachments("PRJ-1", [{"id": "a", "attributes": {"name": "x", "size": 1}}], cov)
        self.assertEqual(envelope.build("attachment list", None, result)["coverage"]["complete"], None)

    def test_outbox_list_scope_follows_the_all_flag_and_an_empty_queue_is_complete(self):
        doc, _ = self.run_json("outbox", "list")
        self.assertEqual((doc["scope"], doc["total"], doc["coverage"]["source"], doc["coverage"]["complete"]), ({"order": "id", "state": "open"}, 0, "local", True))
        doc, _ = self.run_json("outbox", "list", "--all")
        self.assertEqual(doc["scope"]["state"], "all")


class Row(unittest.TestCase):
    def test_flow_minutes_may_be_fractional(self):
        row = {"ticket": "PRJ-1", "uuid": "u", "title": "t", "state": "s", "state_group": "started", "priority": "low", "project": "PRJ",
               "flow": {"outcome": "open", "lead_minutes": 1234.5, "cycle_active_minutes": 10.25, "worklogs": 1, "transitions": [{"at": "2026-10-10T09:00:00+00:00", "from": "?", "to": "Backlog"}]}}
        doc = envelope.build("get", None, coverage.Result(rows=[row], total=1, coverage=coverage.Coverage(source="api", complete=True)))
        self.assertEqual(envelope.validate(doc), [])
        self.assertNotIn("internal", [n["code"] for n in doc["notes"]])


if __name__ == "__main__":
    unittest.main()
