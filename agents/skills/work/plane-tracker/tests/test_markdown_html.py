"""markdown_to_html: un caso por construcción soportada, comparado contra el golden."""
import os
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


if __name__ == "__main__":
    unittest.main()
