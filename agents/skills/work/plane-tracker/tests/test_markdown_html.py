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
    ("tarea", "- [ ] pendiente\n- [x] hecho"), ("bloque de código", "```python\nx = 1 < 2\n```\ndespués"),
    ("bloque sin lenguaje ni cierre", "```\nsin cerrar"), ("mezcla", "# T\n\ntexto\n- a\n- b\n\n1. x\n\n> q\n\n`c`"),
]


class MarkdownHtml(unittest.TestCase):
    def test_golden(self):
        out = []
        for name, source in CASES:
            out += [f"### {name}", repr(source), mdhtml.markdown_to_html(source), ""]
        gs.check_golden(self, "markdown_to_html", "\n".join(out))


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
