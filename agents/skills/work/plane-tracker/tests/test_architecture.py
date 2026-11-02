"""Pruebas de arquitectura (funciones de aptitud F1-F15 del RFC 0021): los principios de diseño convertidos en pruebas que fallan si se violan.

Se escriben antes que los módulos que vigilan. Un trinquete (F15) impide dejar saltada una prueba de una fase ya cerrada: la única forma de saltar
es `gate(Fn)`, que lee PHASES; CURRENT_PHASE avanza al cerrar cada fase del plan (docs/rfcs/0021-.../plan-de-migracion.md, tabla de Seguimiento).
Las pruebas de fases posteriores que aún dependen de código inexistente fallan con `pending()` en cuanto su fase se activa: hay que escribirlas entonces.
"""
import ast
import fnmatch
import glob
import importlib
import itertools
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import golden_support as gs  # noqa: E402
import test_structure as ts  # noqa: E402
from plane_cli import cli, coverage as cov_mod, envelope, errors, vocabulary as voc  # noqa: E402
from plane_cli.scope_flags import flags_for  # noqa: E402

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECISION = os.path.join(SKILL, "docs", "decisions", "0025-contrato-json-de-lectura.md")
PLAN = os.path.join(SKILL, "docs", "rfcs", "0021-arquitectura-de-lectura-consultas-y-vistas", "plan-de-migracion.md")
GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")

CURRENT_PHASE = 1
# Fase del plan en que cada función de aptitud pasa a estar activa. F3-golden es la mitad de F3 que necesita sobres reales (fase 1).
PHASES = {"F1": 0, "F2": 1, "F3": 0, "F3-golden": 1, "F4": 0, "F5": 1, "F6": 1, "F7": 1, "F8": 0, "F9": 1, "F10": 5, "F11": 5, "F12": 1, "F13": 0,
          "F14": 0, "F15": 0}
# F1: módulo (o patrón) -> módulos de plane_cli que puede importar (modelo de consulta §Dónde viven), desde la fase indicada.
DEPENDENCIES = {
    "config": ((), 0), "clock": ((), 0), "vocabulary": ((), 0), "errors": (("vocabulary",), 0), "timeutil": (("clock", "vocabulary"), 0),
    "coverage": (("vocabulary", "timeutil"), 0), "envelope": (("vocabulary", "coverage"), 0),
    "scope": (("vocabulary", "errors"), 1), "scope_flags": (("vocabulary", "config"), 1), "store_*": (("db", "coverage", "vocabulary"), 1),
    "freshness": (("resolve", "cache", "sync", "api", "coverage", "scope", "errors", "clock", "timeutil", "flow"), 1), "query_*": (("store_*", "scope", "coverage", "assignments", "outbox"), 1),
    "render_*": (("vocabulary", "timeutil", "coverage"), 1), "views": (("query_*", "render_*", "envelope", "coverage"), 1),
    "cmd_read": (("views", "scope", "scope_flags", "freshness", "errors"), 3), "cmd_report": (("views", "scope", "scope_flags", "freshness", "errors"), 5),
    "cmd_sync": (("views", "scope", "scope_flags", "freshness", "errors"), 6),
}
LAYER_ONE = {"config", "clock", "vocabulary", "errors"}
RENDER_FORBIDDEN = {"sqlite3", "os", "clock", "db", "api", "cache", "resolve", "freshness"}


def gate(fid):
    """Marca una prueba como la función de aptitud `fid`; solo se salta si su fase aún no llegó (la única vía de salto permitida)."""
    def wrap(fn):
        fn.fitness = fid
        if PHASES[fid] > CURRENT_PHASE:
            skipped = unittest.skip(f"{fid}: activa desde la fase {PHASES[fid]} (CURRENT_PHASE={CURRENT_PHASE})")(fn)
            skipped.fitness = fid
            return skipped
        return fn
    return wrap


# --- Lectura de la decisión del contrato y de los golden ----------------------------------------------------------------------------------
def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def section(text, heading):
    start = text.index(heading + "\n") + len(heading)
    found = re.search(r"\n#{2,3} ", text[start:])
    return text[start:start + found.start()] if found else text[start:]


def table_rows(text):
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in text.splitlines()
            if line.startswith("|") and not re.match(r"^\|[ :\-|]+\|$", line)]
    return rows[1:]  # sin el encabezado


def ticks(cell):
    return re.findall(r"`([^`]+)`", cell)


def bullet(text, label):
    line = next(l for l in text.splitlines() if l.startswith(f"- {label}:"))
    return ticks(line.split(":", 1)[1])


def golden_json_outputs():
    """[(archivo, comando, documento JSON de stdout)] de los golden cuyo comando lleva --json y cuya salida es JSON."""
    found = []
    for path in sorted(glob.glob(os.path.join(GOLDEN, "*.txt"))):
        for block in re.split(r"\n\n\$ ", "\n\n" + read(path)):
            m = re.match(r"plane\.py (.*)\n\[exit (\d+)\]\n--- stdout ---\n(.*?)\n--- stderr ---", block, re.S)
            if m and "--json" in m.group(1).split():
                try:
                    found.append((os.path.basename(path), m.group(1), json.loads(m.group(3))))
                except ValueError:
                    pass
    return found


def sample_row(family):
    kinds = {"str": "x", "int": 1, "num": 1.5, "bool": True, "list": [], "dict": {}}
    return {k: kinds[voc.field_spec(v)[0]] for k, v in voc.FAMILIES[family].items() if voc.field_spec(v)[2]}


def sample_result(view, rows=1, **cov):
    family, summary_family, _ = voc.VIEWS[view]
    summary = {k: ([] if voc.field_spec(v)[0] == "list" else (True if voc.field_spec(v)[0] == "bool" else 0)) for k, v in voc.SUMMARIES[summary_family].items()} if summary_family else None
    return cov_mod.Result(rows=[sample_row(family) for _ in range(rows)], total=rows, coverage=cov_mod.Coverage(source="cache", **cov), summary=summary)


def pending(fid, what):
    raise AssertionError(f"{fid} sin escribir: {what}. Esta función de aptitud está activa desde la fase {PHASES[fid]}: hay que implementarla.")


# vista -> argv de su comando (lo que F5, F6 y F7 recorren); `seed` prepara la caché de la vista y `attachment list` es una lectura de red (queda fuera de F5)
VIEW_COMMANDS = {"list": ["list"], "get": ["get", "OMNIFY-1"], "labels": ["labels"], "projects": ["projects"], "whoami": ["whoami"],
                 "attachment list": ["attachment", "list", "OMNIFY-1"], "outbox list": ["outbox", "list"]}
CACHE_VIEWS = {"list", "get", "labels", "projects"}  # vistas de caché: sobre una caché vencida dan stale y complete null
NON_DIMENSIONAL_FLAGS = {"-h", "--help", "--json"}  # flags que no son dimensiones ni controles (lista blanca de F2; cada vista declara además sus extra_flags)


def age_caches(sandbox, seconds):
    """Envejece todas las cachés de un Sandbox (tickets y su marca por proyecto, catálogos, miembros e instantáneas de `get`)."""
    import sqlite3
    conn = sqlite3.connect(os.path.join(sandbox.home, ".cache", "plane", "worklogs.db"))
    for table, column in (("issues_cache", "updated_at"), ("issue_sync", "as_of"), ("projects", "updated_at"), ("labels", "updated_at"), ("states", "updated_at"),
                          ("members", "updated_at"), ("issue_snapshots", "fetched_at")):
        conn.execute(f"UPDATE {table} SET {column} = {column} - ?", (seconds,))
    conn.commit()
    conn.close()


class Architecture(unittest.TestCase):
    # F1 ------------------------------------------------------------------------------------------------------------------------------
    @gate("F1")
    def test_f1_layers_and_allowed_dependencies(self):
        graph = ts.package_imports()
        for name, deps in graph.items():
            rule = next((r for pattern, r in sorted(DEPENDENCIES.items(), key=lambda kv: -len(kv[0])) if fnmatch.fnmatchcase(name, pattern)), None)
            if rule is None or CURRENT_PHASE < rule[1]:
                continue
            for dep in deps:
                self.assertTrue(any(fnmatch.fnmatchcase(dep, allowed) for allowed in rule[0]), f"{name} no puede importar {dep} (tabla F1)")
        for name in LAYER_ONE & set(graph):
            self.assertLessEqual(graph[name], LAYER_ONE, f"{name} es de la capa 1 y solo importa de la capa 1")

    # F2 ------------------------------------------------------------------------------------------------------------------------------
    @gate("F2")
    def test_f2_views_declare_only_vocabulary_dims_and_the_parser_has_only_their_flags(self):
        views = importlib.import_module("plane_cli.views")
        for view in views.VIEWS.values():
            self.assertLessEqual(set(view.dims), voc.DIMENSIONS, view.name)
            self.assertLessEqual(set(view.controls), voc.CONTROLS, view.name)
        root = cli._subparsers_of(cli.build_parser()).choices
        for view in views.VIEWS.values():
            parser = root[view.command[0]]
            for verb in view.command[1:]:
                parser = cli._subparsers_of(parser).choices[verb]
            declared = {opt for action in parser._actions for opt in action.option_strings}
            self.assertEqual(declared - NON_DIMENSIONAL_FLAGS, flags_for(view.dims, view.controls) | set(view.extra_flags), f"flags de `{view.name}` frente a sus dims, controls y extra_flags")

    # F3 ------------------------------------------------------------------------------------------------------------------------------
    @gate("F3")
    def test_f3_synthetic_envelopes_validate_and_drift_is_detected(self):
        for view, (_family, _summary, has_scope) in voc.VIEWS.items():
            doc = envelope.build(view, {"projects": ["PRJ"], "state": "open"} if has_scope else None, sample_result(view))
            self.assertEqual(envelope.validate(doc), [], view)
        good = envelope.build("list", {"state": "open"}, sample_result("list"))
        cases = {"campo fuera del vocabulario": lambda d: d["results"][0].update(nope=1), "falta schema": lambda d: d.pop("schema"),
                 "summary en list": lambda d: d.update(summary={"ok": True}),
                 "nota sin registrar": lambda d: d["notes"].append({"code": "inventada", "text": "x"}),
                 "aviso sin hint": lambda d: d["notes"].append({"code": "cache_stale", "text": "x"}),
                 "count distinto de len(results)": lambda d: d.update(count=5), "complete true con aviso": lambda d: (d["notes"].append(
                     {"code": "cache_stale", "text": "x", "hint": "h"}), d["coverage"].update(complete=True)),
                 "origen de cobertura no válido": lambda d: d["coverage"].update(source="web"), "tipo incorrecto": lambda d: d["results"][0].update(title=3)}
        for label, mutate in cases.items():
            doc = json.loads(envelope.dumps(good))
            mutate(doc)
            self.assertNotEqual(envelope.validate(doc), [], label)
        get_doc = envelope.build("get", None, sample_result("get"))
        get_doc["scope"] = {}
        self.assertNotEqual(envelope.validate(get_doc), [], "get no lleva scope")
        self.assertEqual(envelope.validate_error(errors.CliError("not_found", "x", "y").to_dict()), [])
        self.assertNotEqual(envelope.validate_error({**errors.CliError("not_found", "x").to_dict(), "exit": 2}), [])

    @gate("F3-golden")
    def test_f3_every_golden_envelope_validates(self):
        envelopes = [(f, c, d) for f, c, d in golden_json_outputs() if isinstance(d, dict) and d.get("schema") == voc.SCHEMA]
        self.assertTrue(envelopes, "ningún golden emite el sobre plane-tracker/1")
        for filename, command, doc in envelopes:
            self.assertEqual(envelope.validate(doc), [], f"{filename}: {command}")

    # F4 ------------------------------------------------------------------------------------------------------------------------------
    @gate("F4")
    def test_f4_vocabulary_matches_the_stable_contract(self):
        text = read(DECISION)
        for family, fields in voc.FAMILIES.items():
            expected = {k: v for k, v in fields.items() if family != "ticket_detail" or k not in voc.FAMILIES["ticket"]}
            actual = {ticks(r[0])[0]: ticks(r[1])[0] for r in table_rows(section(text, f"### Familia `{family}`"))}
            self.assertEqual(actual, expected, f"familia {family}")
        for family, fields in voc.SUMMARIES.items():
            actual = {ticks(r[0])[0]: ticks(r[1])[0] for r in table_rows(section(text, f"### Resumen `{family}`"))}
            self.assertEqual(actual, fields, f"resumen {family}")
        nested = {ticks(r[0])[0]: set(ticks(r[1])) for r in table_rows(section(text, "### Objetos anidados"))}
        self.assertEqual(nested, voc.NESTED)
        top = section(text, "## Sobre de lectura")
        self.assertEqual({ticks(r[0])[0] for r in table_rows(top)}, set(voc.ENVELOPE_KEYS))
        views = next(r for r in table_rows(top) if ticks(r[0]) == ["view"])
        self.assertEqual(set(ticks(views[2])), set(voc.VIEWS))
        for label, expected in (("Dimensiones", voc.DIMENSIONS), ("Controles", voc.CONTROLS), ("Claves de `scope`", voc.SCOPE_KEYS),
                                ("Relaciones de persona", voc.PERSON_RELATIONS), ("Estados", voc.STATES), ("Claves de `coverage`", voc.COVERAGE_KEYS),
                                ("Valores de `coverage.source`", voc.COVERAGE_SOURCES), ("Notas siempre visibles", voc.ALWAYS_SHOWN), ("Claves de `coverage.detail`", voc.DETAIL_KEYS)):
            self.assertEqual(set(bullet(top, label)), set(expected), label)

    @gate("F4")
    def test_f4_note_error_and_check_codes_are_registered_and_documented(self):
        text = read(DECISION)
        notes = {ticks(r[0])[0]: (r[1], r[2]) for r in table_rows(section(text, "## Registro de códigos de nota"))}
        self.assertEqual(notes, {code: (entry[0], entry[1]) for code, entry in voc.NOTES.items()})
        exits = {code: int(r[1]) for r in table_rows(section(text, "## Sobre de error")) if r[1].isdigit() for code in ticks(r[0])}
        self.assertEqual(exits, voc.ERRORS)
        checks = [ticks(r[0])[0] for r in table_rows(section(text, "## Códigos de comprobación (`worklog check`)"))]
        self.assertEqual(checks, list(voc.CHECK_CODES))

    @gate("F4")
    def test_f4_registry_is_well_formed(self):
        for code, (severity, origin, template, hint) in voc.NOTES.items():
            self.assertIn(severity, voc.SEVERITY_ORDER, code)
            self.assertIn(origin, voc.DERIVED_ORIGINS | {"vista", "envelope"}, code)
            self.assertEqual(template is not None, origin in voc.DERIVED_ORIGINS, f"{code}: solo las notas derivadas llevan plantilla")
            self.assertTrue(hint or severity == "info", f"{code}: un aviso necesita remedio")
        self.assertTrue(set(voc.ERRORS.values()) <= {1, 2, 3})
        for fields in itertools.chain(voc.FAMILIES.values(), voc.SUMMARIES.values()):
            for spec in fields.values():
                self.assertIn(voc.field_spec(spec)[0], ("str", "int", "num", "bool", "list", "dict"), spec)
        self.assertEqual(set(voc.BRIEF_FIELDS), {k for k, v in voc.FAMILIES["ticket"].items() if voc.field_spec(v)[2]})

    @gate("F4")
    def test_f4_vocabulary_covers_todays_json(self):
        """Cada campo de los JSON reales de hoy tiene nombre nuevo, está sustituido (REPLACES) o se descarta a propósito (DROPPED)."""
        def legacy(family):
            base = "ticket" if family == "ticket_detail" else family
            return {old for names in voc.REPLACES.get(base, {}).values() for old in names} | set(voc.DROPPED.get(base, ())) | set(voc.DROPPED.get(family, ()))

        def check(rows, family, where, unknown):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for key, value in row.items():
                    if key not in voc.FAMILIES[family] and key not in legacy(family):
                        unknown.add(f"{where}: {family}.{key}")
                    if key in voc.NESTED:
                        accepted = voc.NESTED[key] | {old for names in voc.REPLACES.get(key, {}).values() for old in names}
                        unknown.update(f"{where}: {key}.{sub}" for item in value if isinstance(item, dict) for sub in item if sub not in accepted)
                if isinstance(row.get("flow"), dict):
                    unknown.update(f"{where}: flow.{k}" for k in row["flow"] if k not in voc.FAMILIES["flow"])

        unknown = set()
        for filename, command, doc in golden_json_outputs():
            words = [w for w in command.split() if not w.startswith("-")]
            where = f"{filename}::{command[:50]}"
            if isinstance(doc, dict) and doc.get("schema") == voc.SCHEMA and doc.get("view") in voc.VIEWS:  # ya migrada al sobre: las filas son del vocabulario
                check(doc["results"], voc.VIEWS[doc["view"]][0], where, unknown)
                continue
            if words[0] == "list":
                check(doc["results"] if isinstance(doc, dict) else doc, "ticket", where, unknown)
            elif words[0] == "search":
                check(doc["results"], "ticket", where, unknown)
            elif words[0] == "get":
                check([doc], "ticket_detail", where, unknown)
            elif words[:2] == ["report", "flow"]:
                check(doc["tickets"], "flow", where, unknown)
                unknown.update(f"{where}: flow_summary.{k}" for k in doc["summary"] if k not in voc.SUMMARIES["flow_summary"])
            elif words[:2] == ["worklog", "check"]:
                check(doc["issues"], "check", where, unknown)
                unknown.update(f"{where}: check_summary.{k}" for k in ("ok", "unreachable") if k not in voc.SUMMARIES["check_summary"])
            elif words[0] == "report":
                check(doc, "hours", where, unknown)
            elif words[0] in ("labels", "projects"):
                check(doc, "label" if words[0] == "labels" else "project", where, unknown)
        self.assertEqual(sorted(unknown), [], "campos de hoy sin destino en el vocabulario")
        for family, mapping in voc.REPLACES.items():
            target = voc.NESTED.get(family) or voc.FAMILIES["ticket_detail" if family == "ticket" else family]
            self.assertLessEqual(set(mapping), set(target), f"REPLACES.{family} apunta a nombres inexistentes")

    # F5-F7 ---------------------------------------------------------------------------------------------------------------------------
    @gate("F5")
    def test_f5_cache_views_answer_offline_over_a_cache_older_than_the_ttl(self):
        for view, argv in VIEW_COMMANDS.items():
            if view == "attachment list":
                continue  # excepción declarada: es una auditoría de red por diseño
            sandbox = gs.Sandbox()
            self.addCleanup(sandbox.close)
            self.assertEqual(sandbox.run(argv)[0], 0, view)
            age_caches(sandbox, 2 * 86400 + 3600)  # más vieja que cualquier TTL: si no, la prueba no probaría nada
            before = len(sandbox.fake.requests)
            code, out, err = sandbox.run(argv + ["--json"], env_set={"PLANE_OFFLINE": "1"})
            self.assertEqual(code, 0, f"{view}: {err}")
            doc = json.loads(out)
            self.assertEqual(envelope.validate(doc), [], view)
            self.assertIn(doc["coverage"]["source"], ("cache", "local", "snapshot"), view)
            if view in CACHE_VIEWS:
                self.assertTrue(doc["coverage"]["stale"] and doc["coverage"]["complete"] is None, f"{view}: una caché vencida no es completa")
            self.assertEqual(len(sandbox.fake.requests), before, f"{view}: PLANE_OFFLINE=1 no puede tocar la red")

    @gate("F6")
    def test_f6_acquisition_only_issues_get_requests(self):
        for path in glob.glob(os.path.join(ts.PACKAGE, "freshness.py")) + glob.glob(os.path.join(ts.PACKAGE, "store_*.py")):
            for node in ast.walk(ast.parse(read(path))):
                if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "api_request":
                    methods = [k.value for k in node.keywords if k.arg == "method"] + node.args[2:3]
                    for method in methods:
                        self.assertTrue(isinstance(method, ast.Constant) and method.value == "GET", f"{os.path.basename(path)}:{node.lineno} usa un método distinto de GET")
        for view, argv in VIEW_COMMANDS.items():
            sandbox = gs.Sandbox()
            self.addCleanup(sandbox.close)
            for extra in ([], ["--refresh"], ["--all-projects", "--refresh"], ["--involved", "--refresh-history", "--budget", "2"]) if view == "list" else [[]]:
                self.assertEqual(sandbox.run(argv + extra)[0], 0, f"{view} {extra}")
            methods = {method for method, _path, _body in sandbox.fake.requests}
            self.assertLessEqual(methods, {"GET"}, f"{view}: una lectura solo puede emitir GET (`whoami` con PLANE_ACTOR_UUID no emite nada)")
        # `sync` y `attachment list` se suman a esta comprobación en las fases 6 y 3.

    @gate("F7")
    def test_f7_output_is_byte_identical_under_two_time_zones(self):
        for view, argv in VIEW_COMMANDS.items():
            sandbox = gs.Sandbox()
            self.addCleanup(sandbox.close)
            self.assertEqual(sandbox.run(argv)[0], 0)
            offline = {"PLANE_OFFLINE": "1"} if view != "attachment list" else {}
            outputs = {zone: sandbox.run(argv + ["--json"], env_set={"TZ": zone, **offline})[1] for zone in ("UTC", "America/Lima", "Asia/Tokyo", "UTC")}
            self.assertEqual(len(set(outputs.values())), 1, f"{view}: la salida cambia con la zona horaria o entre ejecuciones")

    # F8 ------------------------------------------------------------------------------------------------------------------------------
    @gate("F8")
    def test_f8_no_result_without_coverage_and_unverified_is_never_rendered_complete(self):
        with self.assertRaises(TypeError):
            cov_mod.Result(rows=[], total=0)
        with self.assertRaises(TypeError):
            cov_mod.Result(rows=[], total=0, coverage=None)
        with self.assertRaises(ValueError):
            cov_mod.Coverage(source="cache", complete=1)
        self.assertEqual(cov_mod.completeness_label(None), "no verificada")
        self.assertNotEqual(cov_mod.completeness_label(None), cov_mod.completeness_label(True))
        self.assertEqual(cov_mod.completeness_label(False), "incompleta")

    # F9 ------------------------------------------------------------------------------------------------------------------------------
    @gate("F9")
    def test_f9_renders_consume_only_the_envelope(self):
        for path in glob.glob(os.path.join(ts.PACKAGE, "render_*.py")):
            tree = ast.parse(read(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] + [a.name for a in node.names]
                    for name in names:
                        root = name.split(".")[-1] if name.startswith("plane_cli") else name.split(".")[0]
                        self.assertNotIn(root, RENDER_FORBIDDEN, f"{os.path.basename(path)} importa {name}")
                        self.assertFalse(root.startswith("store_"), f"{os.path.basename(path)} importa {name}")
                if isinstance(node, ast.FunctionDef):
                    self.assertNotIn("conn", [a.arg for a in node.args.args], f"{os.path.basename(path)}:{node.name} recibe conn")

    # F10-F11 -------------------------------------------------------------------------------------------------------------------------
    @gate("F10")
    def test_f10_report_time_summarizes_by_capacity_without_summing_defaults(self):
        pending("F10", "golden de report time con telemetría parcial: summary.by_capacity con undeclared, by_project, y provenance default fuera de los baldes declarados")

    @gate("F11")
    def test_f11_personal_views_default_to_the_actor_and_have_no_flag_for_others(self):
        pending("F11", "golden sin flags: scope.ticket_person o scope.hours_author igual al actor, y ningún flag para ver a otros")

    # F12 -----------------------------------------------------------------------------------------------------------------------------
    @gate("F12")
    def test_f12_count_respects_limit_and_total_is_always_present(self):
        # V20 (resuelto con la opción B): `truncated` es informativa pero siempre visible, así que también se exige sin --verbose.
        for filename, command, doc in golden_json_outputs():
            if isinstance(doc, dict) and doc.get("schema") == voc.SCHEMA and "view" in doc:
                self.assertIn("total", doc, f"{filename}: {command}")
                limit = (doc.get("scope") or {}).get("limit")
                self.assertTrue(limit is None or doc["count"] <= limit, f"{filename}: {command}")
                if doc["count"] < doc["total"]:
                    self.assertIn("truncated", [n["code"] for n in doc["notes"]], f"{filename}: {command}")

    # F13 -----------------------------------------------------------------------------------------------------------------------------
    @gate("F13")
    def test_f13_derived_notes_exist_only_when_coverage_implies_them_and_views_cannot_forge_them(self):
        facts = {"cache_stale": {"stale": True, "age_s": 3600}, "source_unavailable": {"unavailable": ("PRJ",)},
                 "source_forbidden": {"detail": {"forbidden": ["PRJ"]}}, "cache_capped": {"detail": {"capped": ["PRJ"]}},
                 "rate_budget_exhausted": {"detail": {"rate_budget_exhausted": True}}, "legacy_cache": {"detail": {"legacy": True}},
                 "assignment_snapshot": {"detail": {"assignment_snapshot": True}}, "history_partial": {"detail": {"history": {"verified": 1, "total": 2}}},
                 "hours_local_only": {"detail": {"hours_scope": "local"}}}
        result = lambda c: cov_mod.Result(rows=[], total=0, coverage=c)
        self.assertEqual(cov_mod.notes_from(cov_mod.Coverage(source="cache"), None, result(cov_mod.Coverage(source="cache"))), [])
        for code, kwargs in facts.items():
            cov = cov_mod.Coverage(source="cache", **kwargs)
            self.assertEqual([n["code"] for n in cov_mod.notes_from(cov, None, result(cov))], [code])
        cov = cov_mod.Coverage(source="cache")
        self.assertEqual([n["code"] for n in cov_mod.notes_from(cov, None, cov_mod.Result(rows=[{}], total=3, coverage=cov))], ["truncated"])
        self.assertEqual([n["code"] for n in cov_mod.notes_from(cov, {"projects": ["PRJ"]}, result(cov))], ["single_project"])
        self.assertEqual(set(facts) | {"truncated", "single_project"}, {c for c, e in voc.NOTES.items() if e[1] in voc.DERIVED_ORIGINS})
        for code in (c for c, e in voc.NOTES.items() if e[1] != "vista"):
            forged = cov_mod.Result(rows=[], total=0, coverage=cov, extra_notes=({"code": code, "text": "x"},))
            with self.assertRaises(ValueError, msg=code):
                cov_mod.build_notes(cov, None, forged)
        honest = cov_mod.Result(rows=[], total=0, coverage=cov, extra_notes=({"code": "hours_unsigned", "text": "2 registros sin autor"},))
        self.assertEqual(cov_mod.build_notes(cov, None, honest), [{"code": "hours_unsigned", "text": "2 registros sin autor", "hint": "plane-tracker report time --refresh"}])

    def test_f13_notes_are_ordered_and_info_needs_verbose(self):
        cov = cov_mod.Coverage(source="cache", stale=True, age_s=120, detail={"forbidden": ["B"], "assignment_snapshot": True})
        result = cov_mod.Result(rows=[], total=0, coverage=cov)
        self.assertEqual([n["code"] for n in cov_mod.build_notes(cov, None, result)], ["cache_stale", "source_forbidden"])
        self.assertEqual([n["code"] for n in cov_mod.build_notes(cov, None, result, verbose=True)], ["cache_stale", "source_forbidden", "assignment_snapshot"])

    def test_f13_always_shown_notes_survive_without_verbose_and_truncated_has_no_hint(self):
        cov = cov_mod.Coverage(source="cache")
        cut = cov_mod.Result(rows=[{}], total=3, coverage=cov, extra_notes=({"code": "text_looks_like_id", "text": "x", "hint": "plane-tracker get PRJ-1"},))
        notes = cov_mod.build_notes(cov, {"projects": ["PRJ", "OPS"]}, cut)
        self.assertEqual([n["code"] for n in notes], ["text_looks_like_id", "truncated"])
        self.assertNotIn("hint", [k for n in notes if n["code"] == "truncated" for k in n])
        self.assertEqual(voc.ALWAYS_SHOWN, {"truncated", "text_looks_like_id"})
        self.assertTrue(all(voc.NOTES[c][0] == "info" for c in voc.ALWAYS_SHOWN), "las siempre visibles son informativas; un aviso ya sale siempre")

    # F14 -----------------------------------------------------------------------------------------------------------------------------
    @gate("F14")
    def test_f14_complete_true_is_impossible_with_a_warn_note(self):
        flags = {"stale": (False, True), "unavailable": ((), ("A",)), "forbidden": ((), ["A"]), "capped": ((), ["A"]), "rate_budget_exhausted": (False, True),
                 "legacy": (False, True), "history": (None, {"verified": 1, "total": 2}, {"verified": 2, "total": 2}),
                 "hours_scope": (None, "local", "synced"), "count_mismatch": ((), ["A"]), "hours_verified": (None, False, True)}
        rules = {"list": cov_mod.complete_list, "time": cov_mod.complete_time, "flow": cov_mod.complete_flow}
        reached_true = set()
        for combo in itertools.product(*flags.values()):
            values = dict(zip(flags, combo))
            detail = {k: v for k, v in values.items() if k not in ("stale", "unavailable") and v not in (None, False, ())}
            base = cov_mod.Coverage(source="cache", stale=values["stale"], unavailable=values["unavailable"], detail=detail, age_s=10)
            warns = [n for n in cov_mod.notes_from(base, None, cov_mod.Result(rows=[], total=0, coverage=base)) if voc.NOTES[n["code"]][0] == "warn"]
            for name, rule in rules.items():
                if rule(base) is True:
                    reached_true.add(name)
                    self.assertEqual(warns, [], f"{name} dio complete=true con avisos {detail}")
        self.assertEqual(reached_true, set(rules), "cada regla debe poder dar True")
        doc = envelope.build("list", {"state": "open"}, sample_result("list", complete=True, stale=True))
        self.assertIsNot(doc["coverage"]["complete"], True)
        self.assertIn("internal", [n["code"] for n in doc["notes"]])

    def test_f14_complete_rules_per_view(self):
        c = lambda **kw: cov_mod.Coverage(source=kw.pop("source", "cache"), **kw)
        self.assertIs(cov_mod.complete_list(c()), True)
        self.assertIs(cov_mod.complete_list(c(unavailable=("A",))), False)
        cut = cov_mod.Result(rows=[{}], total=37, coverage=c())  # recortada pero con la fuente completa: complete no depende del límite
        self.assertIs(cov_mod.complete_list(cut.coverage), True)
        self.assertIs(cov_mod.complete_list(c(stale=True)), None)
        self.assertIs(cov_mod.complete_list(c(detail={"count_mismatch": ["A"], "legacy": True})), False)
        self.assertIs(cov_mod.complete_time(c(source="local")), None)  # marca global: no se puede saber
        self.assertIs(cov_mod.complete_time(c(detail={"hours_verified": True})), True)
        self.assertIs(cov_mod.complete_time(c(detail={"hours_verified": False})), False)
        self.assertIs(cov_mod.complete_flow(c(detail={"history": {"verified": 2, "total": 2}})), True)
        self.assertIs(cov_mod.complete_flow(c(detail={"history": {"verified": 1, "total": 2}})), False)
        self.assertIs(cov_mod.complete_agenda(c(), c()), None)
        self.assertIs(cov_mod.complete_agenda(c(), c(detail={"hours_verified": True})), True)
        self.assertIs(cov_mod.complete_agenda(c(unavailable=("A",)), c()), False)
        self.assertIs(cov_mod.complete_get(c(source="api"), True), True)
        self.assertIs(cov_mod.complete_get(c(source="snapshot"), True), None)
        self.assertIs(cov_mod.complete_get(c(source="api"), None), None)

    def test_coverage_merge(self):
        a = cov_mod.Coverage(source="cache", as_of="2026-11-02T10:00:00Z", age_s=60, complete=True, detail={"history": {"verified": 1, "total": 2}})
        b = cov_mod.Coverage(source="api", as_of="2026-11-02T09:00:00Z", age_s=600, complete=None, unavailable=("X",), stale=True,
                             detail={"history": {"verified": 3, "total": 3}})
        merged = cov_mod.Coverage.merge(a, b)
        self.assertEqual((merged.source, merged.as_of, merged.age_s, merged.complete, merged.stale, merged.unavailable),
                         ("mixed", "2026-11-02T09:00:00Z", 600, None, True, ("X",)))
        self.assertEqual(merged.detail["history"], {"verified": 4, "total": 5})
        self.assertIs(cov_mod.Coverage.merge(a, cov_mod.Coverage(source="cache", complete=False)).complete, False)
        self.assertEqual(cov_mod.Coverage.merge(a, a).source, "cache")
        self.assertIs(cov_mod.Coverage.merge(cov_mod.Coverage(source="cache", complete=True), cov_mod.Coverage(source="cache", complete=True)).complete, True)

    def test_envelope_serialization_is_compact_sorted_and_deterministic(self):
        doc = envelope.build("labels", {}, cov_mod.Result(rows=[{"id": "1", "name": "ñandú"}], total=1, coverage=cov_mod.Coverage(source="cache")))
        text = envelope.dumps(doc)
        self.assertEqual(text, envelope.dumps(json.loads(text)))
        self.assertNotIn(" ", text.replace("ñandú", ""))
        self.assertIn("ñandú", text)
        self.assertEqual(list(json.loads(text)), sorted(json.loads(text)))

    def test_cli_error_takes_its_exit_code_from_the_registry(self):
        for code, exit_code in voc.ERRORS.items():
            self.assertEqual(errors.CliError(code, "m").exit_code, exit_code)
        self.assertEqual(errors.CliError("http_error", "m", detail={"status": 404}).to_dict()["detail"], {"status": 404})
        self.assertEqual(errors.CliError("not_found", "falta", "usa get").render(), "falta\nusa get")
        with self.assertRaises(ValueError):
            errors.CliError("inventado", "m")


class Ratchet(unittest.TestCase):
    """F15: una prueba de una fase ya cerrada no puede seguir saltada."""

    @gate("F15")
    def test_f15_no_active_fitness_function_is_skipped_and_skipping_only_goes_through_gate(self):
        tagged = {}
        for cls in (Architecture, Ratchet):
            for name in dir(cls):
                method = getattr(cls, name)
                if getattr(method, "fitness", None):
                    tagged.setdefault(method.fitness, []).append(method)
                    if PHASES[method.fitness] <= CURRENT_PHASE:
                        self.assertFalse(getattr(method, "__unittest_skip__", False), f"{name} está saltada y su fase ya está activa")
        self.assertEqual(set(tagged), set(PHASES), "cada función de aptitud necesita al menos una prueba etiquetada con gate()")
        tree = ast.parse(read(__file__))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "gate":
                continue
            for sub in ast.walk(node):
                name = sub.attr if isinstance(sub, ast.Attribute) else sub.id if isinstance(sub, ast.Name) else ""
                self.assertNotIn(name, ("skip", "skipIf", "skipUnless", "expectedFailure", "skipTest", "SkipTest"), f"salto fuera de gate() en la línea {getattr(sub, "lineno", "?")}")

    @gate("F15")
    def test_f15_current_phase_matches_the_plan(self):
        rows = table_rows(section(read(PLAN), "## Seguimiento"))
        states = {int(r[0]): r[1] for r in rows if r[0].isdigit()}
        self.assertEqual(sorted(states), list(range(9)))
        self.assertTrue(set(states.values()) <= {"pendiente", "en curso", "cerrada"}, states)
        closed = [p for p, s in states.items() if s == "cerrada"]
        self.assertEqual(closed, list(range(len(closed))), "las fases se cierran en orden")
        self.assertEqual(CURRENT_PHASE, max(closed, default=0), "CURRENT_PHASE debe ser la última fase cerrada del plan")


if __name__ == "__main__":
    unittest.main()
