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
    ("report --flow --date 2026-10-14", "'report --flow' ya no existe; usa: plane-tracker report flow --date 2026-10-14"),
    ("report --sync", "'--sync' ya no existe; usa: plane-tracker report --refresh"),
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
]

# Entradas válidas (o con error ajeno a la nomenclatura): no deben producir pista.
SILENT = ["", "--json", "-h", "--help", "get OPS-13", "list --json", "report --week", "report flow --refresh", "comment add OPS-13 -m '--check'",
          "comment edit OPS-1 --force", "comment --json add OPS-1", "comment --help", "comment -h", "attachment list OPS-1", "attachment delete OPS-1 x",
          "focus set OPS-1", "focus status --agent claude", "focus clear", "worklog check --week", "link add OPS-1 https://x.example",
          "zzzzzz", "attachment list attachments", "comment add -m '--off'"]


def run_main(argv):
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            main(argv)
        except SystemExit as exc:
            return exc.code, err.getvalue()
    return None, err.getvalue()


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

    def test_valid_input_has_no_hint(self):
        for line in SILENT:
            with self.subTest(argv=line):
                self.assertIsNone(renamed.suggestion(shlex.split(line), self.tree))


if __name__ == "__main__":
    unittest.main()
