"""`--json` vale en la raíz, en cada grupo y en cada hoja que lo declara; repetido no falla y su posición no importa."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from plane_cli.cli import build_parser  # noqa: E402

PARSER = build_parser()

ON = [
    ["--json", "get", "OMNIFY-1"],
    ["get", "OMNIFY-1", "--json"],
    ["--json", "get", "OMNIFY-1", "--json"],
    ["get", "--json", "OMNIFY-1"],
    ["--json", "list"],
    ["list", "--json", "-p", "OPS"],
    ["--json", "report", "--date", "2026-10-20"],
    ["report", "--json", "--week"],
    ["--json", "search", "x"],
    ["search", "x", "--json", "--json"],
    ["labels", "--json"],
    ["--json", "projects"],
    ["health", "--json", "--hours", "2"],
    ["--json", "create", "T"],
    ["update", "OMNIFY-1", "--json"],
    ["--json", "comment", "OMNIFY-1", "-m", "x"],
    ["comment", "OMNIFY-1", "-m", "x", "--json"],
    ["propose-duration", "OMNIFY-1", "--json"],
    ["--json", "attachments", "OMNIFY-1"],
    ["focus", "--status", "--json"],
]
# Comandos cuya hoja no declara --json: solo vale el de la raíz y se ignora.
ROOT_ONLY = [["--json", "whoami"], ["--json", "handoff"], ["--json", "link", "OMNIFY-1", "https://x.example"]]


class JsonFlag(unittest.TestCase):
    def test_enabled_in_any_position(self):
        for argv in ON:
            with self.subTest(argv=argv):
                self.assertTrue(PARSER.parse_args(argv).json)

    def test_off_by_default(self):
        for argv in (["get", "OMNIFY-1"], ["list"], ["report"], ["comment", "OMNIFY-1", "-m", "x"], ["whoami"]):
            with self.subTest(argv=argv):
                self.assertFalse(getattr(PARSER.parse_args(argv), "json", False))

    def test_root_flag_is_accepted_by_leafs_without_their_own(self):
        for argv in ROOT_ONLY:
            with self.subTest(argv=argv):
                self.assertTrue(PARSER.parse_args(argv).json)


if __name__ == "__main__":
    unittest.main()
