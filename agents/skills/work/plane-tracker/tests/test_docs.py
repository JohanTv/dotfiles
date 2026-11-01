"""Salvaguardas de docs/: front-matter completo, estado válido por tipo, ID único y coherente con el nombre,
enlaces relativos que resuelven e INDEX.md al día. Un ítem puede ser un archivo NNNN-slug.md o una carpeta NNNN-slug/
con README.md como entrada (el resto de sus documentos no lleva front-matter)."""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import docs_index as di  # noqa: E402

LINK_RE = re.compile(r"\[[^\]]*\]\((?!https?://|#|mailto:)([^)#\s]+)")


def markdown_files(root):
    for base, _dirs, names in os.walk(root):
        for name in sorted(names):
            if name.endswith(".md"):
                yield os.path.join(base, name)


class Docs(unittest.TestCase):
    def setUp(self):
        self.items = di.collect()

    def test_names_follow_the_convention(self):
        for kind, name, _meta in self.items:
            self.assertRegex(name, di.FILE_RE, f"docs/{kind}/{name}: se espera NNNN-slug-en-minusculas[.md]")

    def test_folder_items_have_a_readme_entry(self):
        for kind, name, _meta in self.items:
            if os.path.isdir(os.path.join(di.DOCS, kind, name)):
                self.assertTrue(os.path.exists(os.path.join(di.DOCS, kind, name, "README.md")), f"docs/{kind}/{name}/ necesita README.md")

    def test_front_matter_is_complete_and_state_is_valid_for_its_kind(self):
        for kind, name, meta in self.items:
            where = f"docs/{kind}/{name}"
            for key in di.REQUIRED:
                self.assertTrue(meta.get(key), f"{where}: falta `{key}` en el front-matter")
            self.assertIn(meta["status"], di.KINDS[kind][1], f"{where}: estado `{meta['status']}` no válido para {kind}")
            self.assertRegex(meta["created"], r"^\d{4}-\d{2}-\d{2}$", f"{where}: `created` debe ser YYYY-MM-DD")
            self.assertNotIn("ticket", meta, f"{where}: los documentos no llevan ticket (decisión 0008)")

    def test_ids_are_unique_across_kinds_and_match_the_name(self):
        seen = {}
        for kind, name, meta in self.items:
            self.assertEqual(meta.get("id"), name[:4], f"docs/{kind}/{name}: `id` no coincide con el prefijo del nombre")
            self.assertNotIn(name[:4], seen, f"ID {name[:4]} repetido: {seen.get(name[:4])} y {kind}/{name}")
            seen[name[:4]] = f"{kind}/{name}"

    def test_relative_links_resolve(self):
        for path in markdown_files(di.DOCS):
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for target in LINK_RE.findall(text):
                resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
                self.assertTrue(os.path.exists(resolved), f"{os.path.relpath(path, di.DOCS)}: enlace roto a {target}")

    def test_index_is_up_to_date(self):
        self.assertTrue(os.path.exists(di.INDEX), "falta docs/INDEX.md: ejecuta scripts/docs_index.py")
        with open(di.INDEX, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), di.render(self.items), "docs/INDEX.md no está al día: ejecuta scripts/docs_index.py")


class FrontMatter(unittest.TestCase):
    def test_parses_plain_yaml_with_optional_quotes(self):
        meta = di.parse_front_matter('---\nid: "0009"\ntitle: Algo: con dos puntos\nsummary: \'texto\'\n---\n# x\n')
        self.assertEqual(meta, {"id": "0009", "title": "Algo: con dos puntos", "summary": "texto"})

    def test_returns_empty_without_front_matter(self):
        self.assertEqual(di.parse_front_matter("# solo título\n"), {})


class FolderItems(unittest.TestCase):
    def test_folder_item_is_read_from_its_readme_and_linked_to_it(self):
        with tempfile.TemporaryDirectory() as docs:
            os.makedirs(os.path.join(docs, "rfcs", "0001-con-contexto"))
            os.makedirs(os.path.join(docs, "rfcs"), exist_ok=True)
            with open(os.path.join(docs, "rfcs", "0001-con-contexto", "README.md"), "w", encoding="utf-8") as handle:
                handle.write('---\nid: "0001"\ntitle: Con contexto\nstatus: borrador\ncreated: 2026-01-01\nsummary: resumen\n---\n')
            with open(os.path.join(docs, "rfcs", "0001-con-contexto", "contexto.md"), "w", encoding="utf-8") as handle:
                handle.write("sin front-matter\n")
            with open(os.path.join(docs, "rfcs", "0002-suelto.md"), "w", encoding="utf-8") as handle:
                handle.write('---\nid: "0002"\ntitle: Suelto\nstatus: borrador\ncreated: 2026-01-01\nsummary: otro\n---\n')
            items = di.collect(docs)
            self.assertEqual([(k, n, m.get("title")) for k, n, m in items], [("rfcs", "0001-con-contexto", "Con contexto"), ("rfcs", "0002-suelto.md", "Suelto")])
            text = di.render(items, docs)
            self.assertIn("(rfcs/0001-con-contexto/README.md)", text)
            self.assertIn("(rfcs/0002-suelto.md)", text)


if __name__ == "__main__":
    unittest.main()
