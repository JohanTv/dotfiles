"""Vista `list`: orden total, alcance por proyectos accesibles, 403 como cobertura, presupuesto de tasa, recuento del servidor, texto y filas breves."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import clock_support  # noqa: E402
import golden_support as gs  # noqa: E402
from plane_cli import cache, config, db, query_issues  # noqa: E402
from plane_cli.errors import CliError  # noqa: E402
from plane_cli.scope import ProjectRef, Scope, resolve_scope  # noqa: E402
from plane_cli.views import VIEWS  # noqa: E402

P3 = "33333333-3333-4333-8333-333333333333"
P4 = "44444444-4444-4444-8444-444444444444"


class Cli(unittest.TestCase):
    def setUp(self):
        self.sb = gs.Sandbox()
        self.addCleanup(self.sb.close)

    def list(self, *args, ok=True, env_set=None):
        code, out, err = self.sb.run(["list", "--json", *args], env_set=env_set)
        if ok:
            self.assertEqual(code, 0, err)
        return code, (json.loads(out) if out.strip() else None), err

    def sql(self, statement, params=()):
        conn = sqlite3.connect(os.path.join(self.sb.home, ".cache", "plane", "worklogs.db"))
        conn.execute(statement, params)
        conn.commit()
        conn.close()

    def test_order_is_recency_with_null_last_and_ties_by_project_and_sequence(self):
        self.list("--all-projects")
        self.sql("UPDATE issues_cache SET plane_updated_at = NULL WHERE ticket_id = 'OMNIFY-3'")
        self.sql("UPDATE issues_cache SET plane_updated_at = '2026-10-15T12:00:00Z' WHERE ticket_id = 'OPS-13'")
        _, doc, _ = self.list("--all-projects", "--offline", "--brief")
        self.assertEqual([r["ticket"] for r in doc["results"]], ["OMNIFY-1", "OMNIFY-2", "OPS-13", "OMNIFY-3"])
        self.assertEqual(doc["scope"]["order"], "-updated,project,-sequence")

    def test_inaccessible_and_archived_projects_are_out_of_scope(self):
        self.sb.fake.data["projects"] += [{"id": P3, "identifier": "HID", "name": "Oculto", "is_member": False},
                                          {"id": P4, "identifier": "OLD", "name": "Viejo", "archived_at": "2026-01-01T00:00:00Z"}]
        _, doc, _ = self.list("--all-projects", "--brief")
        self.assertEqual(doc["scope"]["projects"], ["OMNIFY", "OPS"])
        code, doc, err = self.list("-p", "HID", ok=False)
        self.assertEqual((code, doc["code"]), (1, "unknown_project"))
        self.assertNotIn("HID", doc["hint"])
        self.assertFalse([p for m, p, _ in self.sb.fake.requests if P3 in p or P4 in p], "no se pide nada de proyectos sin acceso")

    def test_a_403_becomes_coverage_and_does_not_abort_the_rest(self):
        self.sb.fake.add_fault("GET", f"/projects/{gs.P2}/issues/$", "status", 403)
        code, doc, err = self.list("--all-projects", "--brief")
        self.assertEqual([r["project"] for r in doc["results"]], ["OMNIFY"] * 3)
        self.assertEqual(doc["coverage"]["detail"]["forbidden"], ["OPS"])
        self.assertIs(doc["coverage"]["complete"], False)
        self.assertIn("source_forbidden", [n["code"] for n in doc["notes"]])
        self.assertEqual(err, "")

    def test_rate_budget_stops_before_exhausting_and_keeps_the_stored_data(self):
        self.list("--all-projects")
        self.sql("UPDATE projects SET updated_at = updated_at - 200000")  # el catálogo vuelve a pedirse y trae las cabeceras de tasa
        self.sb.fake.extra_headers = {"X-RateLimit-Remaining": "2", "X-RateLimit-Reset": "1793620800"}
        before = len(self.sb.fake.requests)
        _, doc, err = self.list("--all-projects", "--refresh")
        self.assertEqual(len(doc["results"]), 4, "se sirve lo almacenado")
        self.assertTrue(doc["coverage"]["detail"]["rate_budget_exhausted"] and doc["coverage"]["stale"])
        self.assertIsNot(doc["coverage"]["complete"], True)
        self.assertEqual([p for m, p, _ in self.sb.fake.requests[before:] if "/issues/" in p], [])

    def test_server_count_decides_completeness(self):
        _, doc, _ = self.list("-p", "OMNIFY")
        self.assertIs(doc["coverage"]["complete"], True)
        self.sql("UPDATE issue_sync SET total_count = 9 WHERE project_id = ?", (gs.P1,))
        _, doc, _ = self.list("-p", "OMNIFY", "--offline")
        self.assertEqual(doc["coverage"]["detail"]["count_mismatch"], ["OMNIFY"])
        self.assertIs(doc["coverage"]["complete"], False)

    def test_text_combines_with_person_state_and_limit_and_flags_ids(self):
        _, doc, _ = self.list("--text", "sms", "--open", "--mine", "--all-projects")
        self.assertEqual((doc["total"], doc["results"]), (0, []))
        _, doc, _ = self.list("--text", "sms", "--open", "--all-projects")
        self.assertEqual([r["ticket"] for r in doc["results"]], ["OMNIFY-1"])
        _, doc, _ = self.list("--text", "bug", "--mine")
        self.assertEqual([r["ticket"] for r in doc["results"]], ["OMNIFY-2"])
        _, doc, _ = self.list("--text", "OMNIFY-2", "--verbose")
        self.assertEqual(doc["total"], 0)
        self.assertEqual([n["hint"] for n in doc["notes"] if n["code"] == "text_looks_like_id"], ["plane-tracker get OMNIFY-2"])
        self.assertEqual(doc["coverage"]["detail"]["text_fields"], ["title", "labels"])

    def test_brief_rows_have_only_the_brief_fields(self):
        _, doc, _ = self.list("--brief")
        self.assertEqual({k for r in doc["results"] for k in r}, {"ticket", "title", "state", "state_group", "project"})

    def test_plain_list_goes_through_the_cache_not_the_api_listing(self):
        self.list()
        self.assertFalse([p for m, p, _ in self.sb.fake.requests if "limit=" in p])
        before = len(self.sb.fake.requests)
        self.list()
        self.assertEqual(len(self.sb.fake.requests), before, "dentro del TTL no hay red")

    def test_text_output_is_a_render_of_the_same_envelope(self):
        _, doc, _ = self.list("--text", "backend")
        code, out, _ = self.sb.run(["list", "--text", "backend"])
        self.assertEqual(code, 0)
        self.assertIn(doc["results"][0]["ticket"], out)
        self.assertIn(doc["results"][0]["title"], out)


class Sync(unittest.TestCase):
    """cache.sync_project_issues: estados, recuento del servidor, recorte y presupuesto, sin red real."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        db.init_db(self.conn)
        self.clock = clock_support.Clock()
        patcher = self.clock.patch()
        patcher.start()
        self.addCleanup(patcher.stop)
        self.urls = []

    def page(self, n, total, more):
        return {"results": [{"id": f"i{n}-{k}", "sequence_id": n * 10 + k, "name": f"t{n}{k}", "priority": "low", "state": "s1", "assignees": [], "labels": []} for k in range(2)],
                "total_count": total, "next_page_results": more, "next_cursor": f"c{n}" if more else None}

    def sync(self, responder, **kwargs):
        def fake(url, key, **kw):
            self.urls.append(url)
            return responder(url)
        with mock.patch.object(cache, "api_request", side_effect=fake):
            return cache.sync_project_issues(self.conn, "http://x", "k", "ws", "p1", "PRJ", **kwargs)

    def test_asks_for_pages_of_100_without_description_and_stores_the_server_count(self):
        pages = iter([self.page(1, 4, True), self.page(2, 4, False)])
        states = {"results": [{"id": "s1", "name": "Todo", "group": "unstarted"}]}
        status, as_of = self.sync(lambda url: states if "/states/" in url else next(pages))
        self.assertEqual(status, "synced")
        issue_urls = [u for u in self.urls if "/issues/" in u]
        self.assertTrue(all("per_page=100" in u and "fields=" in u and "description" not in u for u in issue_urls))
        row = self.conn.execute("SELECT * FROM issue_sync WHERE project_id = 'p1'").fetchone()
        self.assertEqual((row["total_count"], row["fetched"], row["capped"], row["stale"]), (4, 4, 0, 0))

    def test_hitting_the_page_cap_is_persisted_as_capped(self):
        with mock.patch.object(cache, "ISSUES_MAX_PAGES", 2):
            pages = (self.page(n, 99, True) for n in range(1, 9))
            self.sync(lambda url: {"results": []} if "/states/" in url else next(pages))
        row = self.conn.execute("SELECT * FROM issue_sync").fetchone()
        self.assertEqual((row["capped"], row["fetched"], row["total_count"]), (1, 4, 99))

    def test_403_is_a_status_and_other_http_errors_are_cli_errors(self):
        def forbidden(url):
            raise urllib.error.HTTPError(url, 403, "no", {}, None)
        self.assertEqual(self.sync(forbidden)[0], "forbidden")

        def boom(url):
            raise urllib.error.HTTPError(url, 500, "boom", {}, None)
        with self.assertRaises(CliError) as ctx:
            self.sync(boom, force_refresh=True)
        self.assertEqual((ctx.exception.code, ctx.exception.detail), ("http_error", {"status": 500}))

    def test_budget_exhaustion_keeps_what_was_stored(self):
        states = {"results": [{"id": "s1", "name": "Todo", "group": "unstarted"}]}
        self.sync(lambda url: states if "/states/" in url else self.page(1, 2, False))
        self.clock.advance(cache.ISSUES_TTL + 1)
        with mock.patch.object(cache.api, "rate_limit", return_value={"remaining": 1, "reset": None}):
            status, as_of = self.sync(lambda url: states)
        self.assertEqual(status, "rate_limited")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM issues_cache").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT stale FROM issue_sync").fetchone()[0], 1)

    def test_offline_never_asks_and_reports_expiry(self):
        states = {"results": [{"id": "s1", "name": "Todo", "group": "unstarted"}]}
        self.sync(lambda url: states if "/states/" in url else self.page(1, 2, False))
        self.urls.clear()
        self.assertEqual(self.sync(lambda url: 1 / 0, offline=True)[0], "fresh")
        self.clock.advance(cache.ISSUES_TTL + 1)
        self.assertEqual(self.sync(lambda url: 1 / 0, offline=True)[0], "stale")
        self.assertEqual(self.urls, [])


class ScopeResolution(unittest.TestCase):
    class Cats:
        projects = (ProjectRef("PRJ", "u1", "Uno"), ProjectRef("OPS", "u2", "Dos"))
        default, actor = "PRJ", None

    class Args:
        project = all_projects = mine = created = involved = text = limit = open = offline = refresh = brief = None

    def resolve(self, **kwargs):
        args = self.Args()
        for key, value in kwargs.items():
            setattr(args, key, value)
        return resolve_scope(args, self.Cats, VIEWS["list"])

    def test_defaults_and_pure_validation(self):
        scope = self.resolve()
        self.assertEqual(([p.ident for p in scope.projects], scope.state, scope.limit, scope.order), (["PRJ"], "all", 20, "-updated,project,-sequence"))
        self.assertEqual([p.ident for p in self.resolve(all_projects=True).projects], ["PRJ", "OPS"])
        self.assertEqual(self.resolve(project="ops").projects[0].uuid, "u2")
        self.assertEqual(self.resolve(text="  hola  ", open=True).state, "open")

    def test_unknown_project_and_unknown_actor_are_cli_errors_with_a_hint(self):
        with self.assertRaises(CliError) as ctx:
            self.resolve(project="NOPE")
        self.assertEqual(ctx.exception.code, "unknown_project")
        self.assertIn("PRJ, OPS", ctx.exception.hint)
        with self.assertRaises(CliError) as ctx:
            self.resolve(mine=True)
        self.assertEqual(ctx.exception.code, "actor_unknown")

    def test_scope_document_only_carries_the_dimensions_of_the_view(self):
        doc = self.resolve(text="x", limit=5).to_dict(VIEWS["list"])
        self.assertEqual(doc, {"projects": ["PRJ"], "state": "all", "text": "x", "order": "rank,-sequence", "limit": 5})


if __name__ == "__main__":
    unittest.main()
