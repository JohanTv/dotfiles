"""Árbol de comandos: la forma exacta (y su orden en `--help`), el handler de cada hoja y la obligatoriedad del verbo."""
import argparse
import io
import os
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from plane_cli.cli import build_parser, command_tree  # noqa: E402

TREE = {
    "search": (), "get": (), "list": (), "create": (), "update": (),
    "comment": ("add", "edit", "delete"),
    "attachment": ("add", "list", "delete", "replace"),
    "link": ("add",),
    "outbox": ("list", "flush", "drop"),
    "focus": ("set", "clear", "status"),
    "worklog": ("propose", "check"),
    "report": (), "handoff": (), "labels": (), "projects": (), "whoami": (), "health": (),
}

LEAF_ARGS = {
    ("search",): ["q"], ("create",): ["t"], ("link", "add"): ["https://x.example"], ("focus", "set"): ["OMNIFY-1"], ("outbox", "drop"): ["1"],
    ("attachment", "add"): ["OMNIFY-1", "f"], ("attachment", "delete"): ["OMNIFY-1", "d0000000-0000-4000-8000-000000000001"],
    ("attachment", "replace"): ["OMNIFY-1", "d0000000-0000-4000-8000-000000000001", "f"],
}


def parse(argv):
    err = io.StringIO()
    try:
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            return build_parser().parse_args(argv), 0, err.getvalue()
    except SystemExit as exc:
        return None, exc.code, err.getvalue()


class SkillDocumentsEveryRoute(unittest.TestCase):
    """SKILL.md es lo que lee el agente: cada ruta de comando existente debe aparecer con el prefijo `plane-tracker`."""

    def test_every_route_is_cited(self):
        skill_path = os.path.join(os.path.dirname(__file__), "..", "SKILL.md")
        with open(skill_path, encoding="utf-8") as handle:
            skill = handle.read()
        # En las tablas Markdown las alternativas se escriben `a\\|b`: se normalizan antes de buscar.
        flat = skill.replace("\\|", "|")
        missing = []
        for command, verbs in command_tree(build_parser()).items():
            for route in ([f"{command} {verb}" for verb in verbs] or [command]):
                grouped = verbs and f"plane-tracker {command} " in flat and any(
                    re.search(rf"plane-tracker {command} [^`\n]*\b{verb}\b", flat) for verb in verbs if f"{command} {verb}" == route)
                if f"plane-tracker {route}" not in flat and not grouped:
                    missing.append(route)
        self.assertEqual(missing, [], f"rutas sin citar en SKILL.md: {missing}")


class CommandTree(unittest.TestCase):
    def test_tree_matches_the_naming_table_in_order(self):
        tree = command_tree(build_parser())
        self.assertEqual(list(tree.items()), list(TREE.items()))

    def test_every_leaf_has_a_handler_and_groups_do_not(self):
        for command, verbs in TREE.items():
            for path in ([(command, verb) for verb in verbs] or [(command,)]):
                with self.subTest(path=path):
                    args, code, _ = parse([*path, *LEAF_ARGS.get(path, [])])
                    self.assertEqual(code, 0)
                    self.assertTrue(callable(args.handler))
            if verbs:
                with self.subTest(group=command):
                    args, code, err = parse([command])
                    self.assertEqual(code, 2)
                    self.assertIn("required", err)
                    root = next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction))
                    self.assertIsNone(root.choices[command].get_default("handler"))

    def test_group_usage_lists_its_verbs(self):
        for command, verbs in TREE.items():
            if verbs:
                with self.subTest(group=command):
                    out = io.StringIO()
                    with redirect_stdout(out), self.assertRaises(SystemExit):
                        build_parser().parse_args([command, "--help"])
                    self.assertIn("{" + ",".join(verbs) + "}", out.getvalue())

    def test_one_line_helps_and_compact_global_help(self):
        def walk(parser, path):
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    for choice in action._choices_actions:
                        self.assertLessEqual(len(choice.help), 60, f"{path} {choice.dest}: {choice.help!r}")
                        self.assertFalse(choice.help.endswith("."), f"{path} {choice.dest}")
                    for name, child in action.choices.items():
                        walk(child, f"{path} {name}".strip())

        walk(build_parser(), "")
        root = build_parser()
        root.prog = "plane.py"
        self.assertLessEqual(len(root.format_help()) / 4, 280)

    def test_retired_names_are_not_registered(self):
        names = set(command_tree(build_parser()))
        for old in ("attach", "attachments", "comment-edit", "comment-delete", "propose-duration"):
            self.assertNotIn(old, names)

    def test_json_dest_is_unset_unless_given(self):
        args, _, _ = parse(["list"])
        self.assertFalse(hasattr(args, "json"))
        self.assertIsInstance(build_parser(), argparse.ArgumentParser)


if __name__ == "__main__":
    unittest.main()
