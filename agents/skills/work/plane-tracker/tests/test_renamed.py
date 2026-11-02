"""Nombres retirados, verbos ausentes o mal escritos: texto exacto, código 2 y una sugerencia que sí parsea."""
import contextlib
import io
import os
import shlex
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from plane_cli import renamed  # noqa: E402
from plane_cli.cli import build_parser, command_tree, main  # noqa: E402

UUID = "d0000000-0000-4000-8000-000000000001"
USE = "plane-tracker "

# (argv, texto exacto). Las sugerencias sin marcadores de posición (ISSUE, ID, FILE) deben parsear.
ROWS = [
    ("comment OPS-13 -m x --duration 5", "falta el verbo (add|edit|delete); ej: plane-tracker comment add OPS-13 -m x --duration 5"),
    ("comment -m x", "falta el verbo (add|edit|delete); ej: plane-tracker comment add -m x"),
    ("comment OPS-13 --comment-id " + UUID + " -m x",
     f"falta el verbo (add|edit|delete); ej: plane-tracker comment edit OPS-13 --comment-id {UUID} -m x"),
    ("comment OPS-13 --force --duration 5", "falta el verbo (add|edit|delete); ej: plane-tracker comment edit OPS-13 --force --duration 5"),
    ("comment", "falta el verbo (add|edit|delete); ej: plane-tracker comment add OPS-13 -m x --duration 5"),
    ("comment-edit OPS-13 -m x", "'comment-edit' ya no existe; usa: plane-tracker comment edit OPS-13 -m x"),
    ("comment-delete OPS-13", "'comment-delete' ya no existe; usa: plane-tracker comment delete OPS-13"),
    ("--json comment-edit OPS-13 -m x", "'comment-edit' ya no existe; usa: plane-tracker --json comment edit OPS-13 -m x"),
    ("attach OPS-13 a.txt b.txt", "'attach' ya no existe; usa: plane-tracker attachment add OPS-13 a.txt b.txt"),
    ("attach add OPS-13 a.txt", "'attach' ya no existe; usa: plane-tracker attachment add OPS-13 a.txt"),
    (f"attach OPS-13 a.txt --replace {UUID}", f"'attach --replace' ya no existe; usa: plane-tracker attachment replace OPS-13 {UUID} a.txt"),
    (f"attach --replace {UUID} OPS-13 a.txt", f"'attach --replace' ya no existe; usa: plane-tracker attachment replace OPS-13 {UUID} a.txt"),
    ("attach --replace", "'attach --replace' ya no existe; usa: plane-tracker attachment replace ISSUE ID FILE"),
    ("attachments", "'attachments' ya no existe; usa: plane-tracker attachment list"),
    ("attachments OPS-13", "'attachments' ya no existe; usa: plane-tracker attachment list OPS-13"),
    ("attachments list OPS-13", "'attachments' ya no existe; usa: plane-tracker attachment list OPS-13"),
    ("attachments OPS-13 --json", "'attachments' ya no existe; usa: plane-tracker attachment list OPS-13 --json"),
    (f"attachments OPS-13 --delete {UUID}", f"'attachments --delete' ya no existe; usa: plane-tracker attachment delete OPS-13 {UUID}"),
    ("attachments --delete", "'attachments --delete' ya no existe; usa: plane-tracker attachment delete ISSUE ID"),
    ("link OPS-13 https://x.example --title t", "falta el verbo (add); ej: plane-tracker link add OPS-13 https://x.example --title t"),
    ("focus OPS-13", "falta el verbo (set|clear|status); ej: plane-tracker focus set OPS-13"),
    ("focus --off", "'focus --off' ya no existe; usa: plane-tracker focus clear"),
    ("focus --status --json", "'focus --status' ya no existe; usa: plane-tracker focus status --json"),
    ("focus --agent claude --off", "'focus --off' ya no existe; usa: plane-tracker focus clear --agent claude"),
    ("propose-duration OPS-13 --json", "'propose-duration' ya no existe; usa: plane-tracker worklog propose OPS-13 --json"),
    ("report --check --week -p OPS", "'report --check' ya no existe; usa: plane-tracker worklog check --week -p OPS"),
    ("report --check --track main --sync", "'report --check' ya no existe; usa: plane-tracker worklog check"),
    ("report --flow --date 2026-10-14", "'report --flow' ya no existe; usa: plane-tracker report flow --from 2026-10-14"),
    ("report --sync", "'--sync' ya no existe; usa: plane-tracker report time --refresh"),
    ("report", "falta la vista (time|flow); ej: plane-tracker report time --week"),
    ("report --date 2026-10-20", "falta la vista (time|flow); ej: plane-tracker report time --from 2026-10-20"),
    ("report time --date 2026-10-20 --refresh", "'report time --date' ya no existe; usa: plane-tracker report time --from 2026-10-20 --refresh"),
    ("report flow --today", "'report flow --today' ya no existe; usa: plane-tracker report flow"),
    ("worklog check --date 2026-10-20 --json", "'worklog check --date' ya no existe; usa: plane-tracker worklog check --from 2026-10-20 --json"),
    ("report --flow --sync", "'report --flow' ya no existe; usa: plane-tracker report flow --refresh"),
    ("comment rm OPS-1", "'comment rm' no existe; usa: plane-tracker comment delete OPS-1"),
    ("comment update OPS-1 -m x", "'comment update' no existe; usa: plane-tracker comment edit OPS-1 -m x"),
    ("attachment ls OPS-1", "'attachment ls' no existe; usa: plane-tracker attachment list OPS-1"),
    ("focus stop", "'focus stop' no existe; usa: plane-tracker focus clear"),
    ("focus start OPS-1", "'focus start' no existe; usa: plane-tracker focus set OPS-1"),
    ("link create https://x.example", "'link create' no existe; usa: plane-tracker link add https://x.example"),
    ("comment ad OPS-1", "verbo 'ad' desconocido en 'comment'; ¿quisiste decir 'add'?"),
    ("atachment list OPS-1", "comando 'atachment' desconocido; ¿quisiste decir 'attachment'?"),
    ("attachment", "falta el verbo (add|list|delete|replace); ej: plane-tracker attachment list OPS-13"),
    ("worklog --week", "falta el verbo (propose|check); ej: plane-tracker worklog propose OPS-13"),
    ("outbox", "falta el verbo (list|flush|drop); ej: plane-tracker outbox flush"),
    ("outbox --json", "falta el verbo (list|flush|drop); ej: plane-tracker outbox flush"),
    ("outbox sync --limit 5", "'outbox sync' no existe; usa: plane-tracker outbox flush --limit 5"),
    ("outbox discard 3", "'outbox discard' no existe; usa: plane-tracker outbox drop 3"),
    ("search formulario", "'search' ya no existe; usa: plane-tracker list --text formulario"),
    ("search 'validaciones formulario' -p OPS --json --refresh", "'search' ya no existe; usa: plane-tracker list --text 'validaciones formulario' -p OPS --json --refresh"),
    ("--json search x", "'search' ya no existe; usa: plane-tracker --json list --text x"),
    ("search", "'search' ya no existe; usa: plane-tracker list --text TEXTO"),
    ("list enlaces", "'list' no acepta texto posicional; usa: plane-tracker list --text enlaces"),
    ("list a b -p OPS --open", "'list' no acepta texto posicional; usa: plane-tracker list --text 'a b' -p OPS --open"),
    ("outbox flsh", "verbo 'flsh' desconocido en 'outbox'; ¿quisiste decir 'flush'?"),
]

# Entradas válidas (o con error ajeno a la nomenclatura): no deben producir pista.
SILENT = ["", "--json", "-h", "--help", "get OPS-13", "list --json", "report time --week", "report flow --refresh", "report time --from 2026-10-20 --to 2026-10-22", "worklog check --from 2026-10-20", "comment add OPS-13 -m '--check'",
          "comment edit OPS-1 --force", "comment --json add OPS-1", "comment --help", "comment -h", "attachment list OPS-1", "attachment delete OPS-1 x",
          "focus set OPS-1", "outbox flush --retry-failed", "outbox drop 3 --force", "focus status --agent claude", "focus clear", "worklog check --week", "link add OPS-1 https://x.example",
          "list --text x", "list -p OPS --open --limit 5", "list --text 'a b'", "zzzzzz", "attachment list attachments", "comment add -m '--off'"]


def run_main(argv):
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            main(argv)
        except SystemExit as exc:
            return exc.code, err.getvalue()
    return None, err.getvalue()


GROUP_ROWS = [  # con `report` convertido en grupo (fase 5): la vista es obligatoria y ninguna entrada lanza KeyError
    ("report", "falta la vista (time|flow); ej: plane-tracker report time --week"),
    ("report --week", "falta la vista (time|flow); ej: plane-tracker report time --week"),
    ("report -p OPS --refresh", "falta la vista (time|flow); ej: plane-tracker report time -p OPS --refresh"),
    ("report --check", "'report --check' ya no existe; usa: plane-tracker worklog check"),
    ("report --flow --week", "'report --flow' ya no existe; usa: plane-tracker report flow --week"),
    ("report --sync", "'--sync' ya no existe; usa: plane-tracker report time --refresh"),
]
GROUP_SILENT = ["report time", "report flow --refresh", "report time --week", "report -h", "report --help", "--json report time"]


class Renamed(unittest.TestCase):
    def setUp(self):
        self.tree = command_tree(build_parser())

    def test_exact_text(self):
        for line, expected in ROWS:
            with self.subTest(argv=line):
                self.assertEqual(renamed.suggestion(shlex.split(line), self.tree), expected)

    def test_suggestions_parse(self):
        for line, expected in ROWS:
            if "usa: " not in expected and "ej: " not in expected:
                continue
            suggested = shlex.split(expected.split(USE, 1)[1])
            if any(word in suggested for word in ("ISSUE", "ID", "FILE")):
                continue
            with self.subTest(argv=line, suggestion=suggested):
                build_parser().parse_args(suggested)

    def test_main_exits_2_before_checking_the_environment(self):
        saved = {k: os.environ.pop(k) for k in ("PLANE_BASE_URL", "PLANE_API_KEY") if k in os.environ}
        try:
            for line, expected in ROWS:
                with self.subTest(argv=line):
                    code, err = run_main(shlex.split(line))
                    self.assertEqual(code, 2)
                    self.assertEqual(err.splitlines()[-1], f"plane-tracker: error: {expected}")  # avisos ajenos del GC no cuentan
        finally:
            os.environ.update(saved)

    def test_report_as_a_group_never_raises_and_requires_the_view(self):
        tree = {**self.tree, "report": ("time", "flow")}
        for line, expected in GROUP_ROWS:
            with self.subTest(argv=line):
                self.assertEqual(renamed.suggestion(shlex.split(line), tree), expected)
        for line in GROUP_SILENT:
            with self.subTest(argv=line):
                self.assertIsNone(renamed.suggestion(shlex.split(line), tree))

    def test_valid_input_has_no_hint(self):
        for line in SILENT:
            with self.subTest(argv=line):
                self.assertIsNone(renamed.suggestion(shlex.split(line), self.tree))


if __name__ == "__main__":
    unittest.main()
