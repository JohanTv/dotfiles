"""markdown_to_html: un caso por construcción soportada, comparado contra el golden."""
import os
import signal
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import golden_support as gs  # noqa: E402
from plane_cli import mdhtml  # noqa: E402

CASES = [
    ("vacío", ""), ("solo espacios", "   \n "), ("párrafo", "uno\ndos\n\ntres"), ("crlf", "a\r\nb\rc"),
    ("headings", "# H1\n## H2 **b**\n###### H6"), ("negrita cursiva", "a ***x*** **y** *z* ~~w~~"), ("código inline", "usa `a<b>&c` y **b**"),
    ("enlace", "[txt](https://x.example/a?b=1)"), ("escape", "a < b & c > d"), ("regla", "---\n***\n___"),
    ("lista", "- uno\n* dos **b**\n- tres"), ("lista ordenada", "1. a\n2. b\n10. c"), ("cita", "> uno\n> dos\n>tres"),
    ("tabla", "| a | b |\n|---|:--:|\n| 1 | **2** |\n| 3 | 4 |"), ("tabla sin cuerpo", "| a | b |\n|---|---|"),
    ("tarea", "- [ ] pendiente\n- [x] hecho"), ("tareas mezcladas", "- a\n- [ ] b\n* [X] **c**\n- d"), ("tarea vacía y sin espacio", "- [ ]\n- [x]hola"),
    ("DoD", "### DoD\n- [ ] criterio con `code`\n- [x] otro"), ("bloque de código", "```python\nx = 1 < 2\n```\ndespués"),
    ("bloque sin lenguaje ni cierre", "```\nsin cerrar"), ("mezcla", "# T\n\ntexto\n- a\n- b\n\n1. x\n\n> q\n\n`c`"),
]


class MarkdownHtml(unittest.TestCase):
    def test_golden(self):
        out = []
        for name, source in CASES:
            out += [f"### {name}", repr(source), mdhtml.markdown_to_html(source), ""]
        gs.check_golden(self, "markdown_to_html", "\n".join(out))


class TaskList(unittest.TestCase):
    """`- [ ]` y `- [x]` salen como la lista de tareas del editor de Plane (interactiva), no como una lista normal con el texto literal «[ ]»."""

    def test_task_items_use_the_editor_markup_and_the_checked_state(self):
        html = mdhtml.markdown_to_html("- [ ] pendiente\n- [x] hecho\n* [X] otra")
        self.assertTrue(html.startswith('<ul data-type="taskList">') and html.endswith("</ul>"))
        self.assertEqual(html.count('data-type="taskItem"'), 3)
        self.assertEqual([m for m in ("false", "true", "true") if f'data-checked="{m}"' in html], ["false", "true", "true"])
        self.assertEqual(html.count('<input type="checkbox" checked="checked">'), 2)
        self.assertNotIn("[ ]", html)
        self.assertNotIn("[x]", html)
        self.assertNotIn("disabled", html, "las casillas no deben quedar deshabilitadas")

    def test_the_checkbox_branch_is_reachable_before_the_plain_list(self):
        self.assertIn('data-type="taskList"', mdhtml.markdown_to_html("- [ ] x"))
        self.assertEqual(mdhtml.markdown_to_html("- x"), "<ul><li>x</li></ul>")

    def test_a_plain_list_and_a_task_list_stay_separate_blocks(self):
        html = mdhtml.markdown_to_html("- a\n- [ ] b\n- c")
        self.assertEqual(html.count("<ul"), 3)
        self.assertEqual(html.splitlines()[0], "<ul><li>a</li></ul>")
        self.assertIn("<p>b</p>", html.splitlines()[1])
        self.assertEqual(html.splitlines()[2], "<ul><li>c</li></ul>")

    def test_text_is_escaped_and_formatted_inside_the_item(self):
        html = mdhtml.markdown_to_html("- [ ] a < b **x** `c`")
        self.assertIn("<p>a &lt; b <strong>x</strong> <code>c</code></p>", html)

    def test_a_box_glued_to_the_text_is_not_a_task(self):
        self.assertEqual(mdhtml.markdown_to_html("- [x]hola"), "<ul><li>[x]hola</li></ul>")


class NoHang(unittest.TestCase):
    """Líneas que empiezan por tres de `|-*_` sin ser regla horizontal ni tabla deben terminar como párrafo."""

    def convert(self, source):
        def on_alarm(_signum, _frame):
            raise TimeoutError(f"markdown_to_html no termina con {source!r}")

        previous = signal.signal(signal.SIGALRM, on_alarm)
        signal.alarm(3)
        try:
            return mdhtml.markdown_to_html(source)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)

    def test_paragraphs_starting_with_block_like_prefixes(self):
        self.assertEqual(self.convert("***x*** texto"), "<p><strong><em>x</em></strong> texto</p>")
        self.assertEqual(self.convert("---x"), "<p>---x</p>")
        self.assertEqual(self.convert("|--"), "<p>|--</p>")
        self.assertEqual(self.convert("___a"), "<p>___a</p>")

    def test_following_lines_still_join_the_paragraph_or_start_a_block(self):
        self.assertEqual(self.convert("***x*** uno\ndos"), "<p><strong><em>x</em></strong> uno<br>dos</p>")
        self.assertEqual(self.convert("---x\n# T"), "<p>---x</p>\n<h1>T</h1>")


if __name__ == "__main__":
    unittest.main()
