"""Límite de la bitácora de cierre y nota del reporte: reject_long_comment(), note_from() y visible_text()."""
import io
import os
import sys
import unittest
from contextlib import redirect_stderr

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from plane_cli.errors import CliError  # noqa: E402
from plane_cli.worklog import MAX_COMMENT_CHARS, note_from, reject_long_comment, visible_text  # noqa: E402


def rejected(text, allow_long=False):
    err = io.StringIO()
    try:
        with redirect_stderr(err):
            reject_long_comment(text, allow_long)
    except (SystemExit, CliError) as exc:
        code = exc.exit_code if isinstance(exc, CliError) else exc.code
        msg = exc.render() if isinstance(exc, CliError) else err.getvalue()
        return code, msg
    return None, err.getvalue()


class VisibleText(unittest.TestCase):
    def test_ignores_hidden_block_and_tags(self):
        text = "<p>Hola <b>mundo</b></p><!-- PLANE_WORKLOG_METADATA {\"a\": \"" + "x" * 900 + "\"} -->"
        self.assertEqual(visible_text(text), "Hola mundo")


class LongComment(unittest.TestCase):
    def test_at_the_limit_passes(self):
        self.assertEqual(rejected("a" * MAX_COMMENT_CHARS)[0], None)

    def test_over_the_limit_is_rejected_with_a_hint(self):
        code, err = rejected("a" * (MAX_COMMENT_CHARS + 1))
        self.assertEqual(code, 1)
        self.assertIn("--long", err)
        self.assertIn(str(MAX_COMMENT_CHARS + 1), err)

    def test_long_flag_allows_it(self):
        self.assertEqual(rejected("a" * 5000, allow_long=True)[0], None)

    def test_hidden_metadata_does_not_count(self):
        block = "<!-- PLANE_WORKLOG_METADATA {\"notes\": \"" + "x" * 2000 + "\"} -->"
        self.assertEqual(rejected("corto" + block)[0], None)


class NoteFrom(unittest.TestCase):
    def test_skips_headings_and_table_rows(self):
        self.assertEqual(note_from("### Título\n\n| a | b |\n| - | - |\ntexto real"), "texto real")

    def test_strips_bullet_and_bold(self):
        self.assertEqual(note_from("- **Hecho:** rebase listo"), "Hecho: rebase listo")

    def test_caps_at_120_chars(self):
        self.assertEqual(len(note_from("a" * 300)), 120)

    def test_falls_back_when_nothing_readable(self):
        self.assertEqual(note_from("### Solo título", "Nombre del ticket"), "Nombre del ticket")
        self.assertEqual(note_from("", "Nombre del ticket"), "Nombre del ticket")

    def test_html_comment_is_not_a_note(self):
        self.assertEqual(note_from("<!-- PLANE_WORKLOG_METADATA {} -->\nVisible"), "Visible")


if __name__ == "__main__":
    unittest.main()
