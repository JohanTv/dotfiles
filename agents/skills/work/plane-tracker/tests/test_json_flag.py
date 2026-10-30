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
    ["report", "flow", "--json"],
    ["--json", "search", "x"],
    ["search", "x", "--json", "--json"],
    ["labels", "--json"],
    ["--json", "projects"],
    ["health", "--json", "--hours", "2"],
    ["--json", "create", "T"],
    ["update", "OMNIFY-1", "--json"],
    ["--json", "comment", "add", "OMNIFY-1", "-m", "x"],
    ["comment", "add", "OMNIFY-1", "-m", "x", "--json"],
    ["comment", "--json", "add", "OMNIFY-1", "-m", "x"],
    ["--json", "comment", "--json", "add", "OMNIFY-1", "--json"],
    ["worklog", "propose", "OMNIFY-1", "--json"],
    ["worklog", "--json", "check"],
    ["worklog", "check", "--week", "--json"],
    ["--json", "attachment", "list", "OMNIFY-1"],
    ["attachment", "list", "--json"],
    ["focus", "status", "--json"],
    ["--json", "focus", "status"],
]
# Hojas que no declaran --json: solo vale el de la raíz o el del grupo, y se ignora.
ROOT_ONLY = [["--json", "whoami"], ["--json", "handoff"], ["--json", "link", "add", "OMNIFY-1", "https://x.example"],
             ["link", "--json", "add", "OMNIFY-1", "https://x.example"], ["--json", "focus", "clear"],
             ["--json", "comment", "edit", "OMNIFY-1"], ["comment", "--json", "delete"], ["--json", "attachment", "delete", "OMNIFY-1",
                                                                                           "d0000000-0000-4000-8000-000000000001"]]


class JsonFlag(unittest.TestCase):
    def test_enabled_in_any_position(self):
        for argv in ON:
            with self.subTest(argv=argv):
                self.assertTrue(PARSER.parse_args(argv).json)

    def test_off_by_default(self):
        for argv in (["get", "OMNIFY-1"], ["list"], ["report"], ["comment", "add", "OMNIFY-1", "-m", "x"], ["whoami"],
                     ["worklog", "check"], ["focus", "status"]):
            with self.subTest(argv=argv):
                self.assertFalse(getattr(PARSER.parse_args(argv), "json", False))

    def test_root_and_group_flags_are_accepted_by_leafs_without_their_own(self):
        for argv in ROOT_ONLY:
            with self.subTest(argv=argv):
                self.assertTrue(PARSER.parse_args(argv).json)


if __name__ == "__main__":
    unittest.main()
